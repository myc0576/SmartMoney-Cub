"""Optional Vezgo portfolio reads using user-owned developer credentials.

Only token creation and an exact GET allowlist are implemented. Linking broker
accounts remains on the vendor's authorization UI; no account mutation endpoint
is exposed. Ambiguous multi-leg swaps remain raw events requiring mapping.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

from .manifests import get_manifest
from .models import (ConnectionAccount, ConnectionCursor, CredentialBundle, EventPage,
                     NormalizedEvent, NormalizedPosition, ScopeValidation)
from .protocol import PermissionConnectionError, TransientConnectionError
from .http import open_without_redirect


class VezgoTransport:
    _READ_PATH = re.compile(r"/accounts(?:/[^/]+/transactions)?\Z")

    @staticmethod
    def _request(request):
        try:
            with open_without_redirect(request, timeout=20) as response:
                return json.loads(response.read(16 * 1024 * 1024))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise PermissionConnectionError("vezgo_authorization_expired_or_denied") from None
            raise TransientConnectionError("vezgo_http_failure") from None
        except (OSError, ValueError):
            raise TransientConnectionError("vezgo_response_unavailable") from None

    def authenticate(self, values):
        body = json.dumps({"clientId": values["client_id"], "secret": values["client_secret"]}).encode()
        response = self._request(urllib.request.Request("https://api.vezgo.com/v1/auth/token", data=body,
            headers={"Content-Type": "application/json", "loginName": values["login_name"]}, method="POST"))
        if not isinstance(response, dict) or not response.get("token"):
            raise PermissionConnectionError("vezgo_token_missing")
        return str(response["token"])

    def get(self, path, token, params=None):
        if not self._READ_PATH.fullmatch(path):
            raise ValueError("vezgo_read_path_not_allowed")
        query = "?" + urllib.parse.urlencode(params) if params else ""
        return self._request(urllib.request.Request("https://api.vezgo.com/v1" + path + query,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, method="GET"))


class VezgoConnection:
    def __init__(self, transport, credentials: CredentialBundle):
        self.transport, self._credentials = transport, credentials
        self._token = None
        self._accounts = ()
        self._disconnected = False

    def metadata(self):
        return get_manifest("vezgo")

    def bind_credentials(self, credentials):
        if credentials.provider_id != "vezgo":
            raise ValueError("credential_provider_mismatch")
        self._credentials = credentials

    def validate_read_access(self, credentials=None):
        values = (credentials or self._credentials).values if (credentials or self._credentials) else {}
        if self._disconnected or any(not values.get(key) for key in ("client_id", "client_secret", "login_name")):
            return ScopeValidation(False, "missing", issues=("vezgo_developer_credentials_required",))
        try:
            # Reauthenticate each sync rather than storing a short-lived user
            # bearer token. Successful read is evidence, not a client boolean.
            self._token = self.transport.authenticate(values)
            accounts = self.transport.get("/accounts", self._token)
            if not isinstance(accounts, list):
                raise ValueError("invalid_accounts")
            self._accounts = tuple(accounts)
        except Exception:
            self._token = None
            return ScopeValidation(False, "denied", issues=("vezgo_account_read_not_verified",))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",),
                               issues=("portfolio_read_api_only",))

    def _require(self):
        if self._disconnected or not self._token:
            if not self.validate_read_access().allowed:
                raise PermissionConnectionError("vezgo_read_access_required")

    def list_accounts(self, credentials=None):
        self._require()
        return tuple(ConnectionAccount(str(a["id"]), str(a.get("name") or "Vezgo account"), "vezgo", "crypto",
                                       a.get("fiat_ticker"), ("read",)) for a in self._accounts)

    def read_events(self, cursor=None, credentials=None):
        self._require()
        if cursor and cursor.provider_id != "vezgo":
            raise ValueError("cursor_provider_mismatch")
        state = json.loads(cursor.token) if cursor and cursor.token else {}
        ids = state.get("accounts") or [str(a["id"]) for a in self._accounts]
        index, last = int(state.get("index", 0)), str(state.get("last", ""))
        if index >= len(ids):
            return EventPage(checkpoint_cursor=ConnectionCursor("vezgo"))
        account_id = ids[index]
        rows = self.transport.get("/accounts/" + urllib.parse.quote(account_id, safe="") + "/transactions",
                                  self._token, {"from": "1970-01-01", "last": last, "limit": 1000})
        if not isinstance(rows, list):
            raise ValueError("vezgo_transactions_invalid")
        if rows:
            next_last = str(rows[-1].get("id") or "")
            if not next_last or next_last == last:
                raise ValueError("vezgo_pagination_stalled")
            next_index = index
        else:
            next_index, next_last = index + 1, ""
        next_cursor = ConnectionCursor("vezgo", json.dumps({"accounts": ids, "index": next_index, "last": next_last})) if next_index < len(ids) else None
        return EventPage(tuple(self.normalize(row, account_id) for row in rows), next_cursor,
                         None if next_cursor else ConnectionCursor("vezgo"))

    @staticmethod
    def normalize(row, account_id):
        parts = row.get("parts") or []
        sent = [p for p in parts if p.get("direction") == "sent"]
        received = [p for p in parts if p.get("direction") == "received"]
        quote_assets = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "USDT", "USDC"}
        side, base, quote = None, None, None
        if row.get("transaction_type") == "trade" and len(sent) == len(received) == 1:
            if sent[0].get("ticker") in quote_assets and received[0].get("ticker") not in quote_assets:
                side, base, quote = "BUY", received[0], sent[0]
            elif received[0].get("ticker") in quote_assets and sent[0].get("ticker") not in quote_assets:
                side, base, quote = "SELL", sent[0], received[0]
        quantity = Decimal(str(base["amount"])) if base else None
        known = quantity is not None and quantity.is_finite() and quantity > 0
        currency = quote.get("ticker") if known else None
        components = row.get("fees") or []
        fee_known = all(f.get("ticker") == currency for f in components)
        fee = sum((Decimal(str(f["amount"])) for f in components), Decimal(0)) if fee_known and known else None
        milliseconds = row.get("confirmed_at") or row.get("initiated_at")
        timestamp = datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat() if milliseconds else None
        revision = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:24]
        return NormalizedEvent(str(row["id"]), revision, account_id, "crypto",
                               str(base["ticker"]) + "/" + currency if known else "unknown",
                               "fill" if known else ("unmapped_trade" if row.get("transaction_type") == "trade" else str(row.get("transaction_type", "unknown"))),
                               side if known else None, quantity if known else None,
                               Decimal(str(quote["amount"])) / quantity if known else None, currency, fee,
                               timestamp, datetime.now(timezone.utc).isoformat(),
                               "ok" if known and fee_known else "requires_mapping", "vezgo",
                               {"parts": parts, "fee_components": components, "time_precision": "millisecond", "timezone": "UTC"})

    def read_positions(self, credentials=None):
        self._require()
        return tuple(NormalizedPosition(str(a["id"]), "crypto", str(balance["ticker"]), balance.get("amount"),
                                        market_value=balance.get("fiat_value"), currency=balance.get("fiat_ticker"),
                                        source="vezgo") for a in self._accounts for balance in a.get("balances", []) if balance.get("ticker"))

    def disconnect(self):
        self._token, self._credentials, self._accounts = None, None, ()
        self._disconnected = True
