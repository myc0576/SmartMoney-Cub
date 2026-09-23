"""Read existing MetaTrader terminal state; never log in or invoke execution.

The operator signs in with an investor password in the terminal. The Python
bridge verifies connection and a disabled account trading permission each read.
It cannot identify which password was used; this limitation is explicit.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from .manifests import get_manifest
from .models import (ConnectionAccount, ConnectionCursor, CredentialBundle, EventPage,
                     NormalizedEvent, NormalizedPosition, ScopeValidation)
from .protocol import PermissionConnectionError


def _field(value, key, default=None):
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


class MetaTraderInvestorConnection:
    def __init__(self, terminal: Any, credentials: CredentialBundle, *, page_size: int = 1000):
        self.terminal, self._credentials = terminal, credentials
        self.page_size = max(1, min(page_size, 1000))
        self._disconnected = False

    def metadata(self):
        return get_manifest("metatrader-investor")

    def bind_credentials(self, credentials):
        if credentials.provider_id != "metatrader-investor":
            raise ValueError("credential_provider_mismatch")
        self._credentials = credentials

    def validate_read_access(self, credentials=None):
        if self._disconnected:
            return ScopeValidation(False, "denied", issues=("connection_disconnected",))
        try:
            terminal, account = self.terminal.terminal_info(), self.terminal.account_info()
            connected = _field(terminal, "connected") is True
            disabled = _field(account, "trade_allowed") is False
        except Exception:
            return ScopeValidation(False, "unknown", issues=("terminal_read_failed",))
        if not connected or not disabled:
            return ScopeValidation(False, "denied", required=("read",),
                                   issues=("connected_trade_disabled_terminal_required",))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",),
                               issues=("password_type_not_exposed_by_terminal_api",))

    def _require(self):
        if not self.validate_read_access().allowed:
            raise PermissionConnectionError("investor_terminal_read_access_required")
        return self.terminal.account_info()

    @staticmethod
    def _account_id(account):
        return str(_field(account, "server", "")) + ":" + str(_field(account, "login", ""))

    def list_accounts(self, credentials=None):
        account = self._require()
        return (ConnectionAccount(self._account_id(account), "MetaTrader terminal account",
                                  "metatrader-investor", "multi_asset", _field(account, "currency"), ("read",)),)

    def read_events(self, cursor=None, credentials=None):
        account = self._require()
        state = json.loads(cursor.token) if cursor and cursor.token else {}
        if cursor and cursor.provider_id != "metatrader-investor":
            raise ValueError("cursor_provider_mismatch")
        # Keep a fixed upper boundary while paging. A new sync rescans for broker
        # corrections; stable ticket IDs make replay idempotent.
        end = datetime.fromisoformat(state["until"]) if state.get("until") else datetime.now(timezone.utc)
        deals = self.terminal.history_deals_get(datetime(1970, 1, 1, tzinfo=timezone.utc), end)
        if deals is None:
            raise RuntimeError("terminal_history_unavailable")
        deals = sorted(deals, key=lambda d: (int(_field(d, "time_msc", 0)), int(_field(d, "ticket", 0))))
        offset = int(state.get("offset", 0))
        selected = deals[offset:offset + self.page_size]
        events = tuple(self._event(deal, account) for deal in selected)
        next_cursor = None
        if offset + len(selected) < len(deals):
            next_cursor = ConnectionCursor("metatrader-investor", json.dumps({"until": end.isoformat(), "offset": offset + len(selected)}))
        return EventPage(events, next_cursor, None if next_cursor else ConnectionCursor("metatrader-investor"))

    def _event(self, deal, account):
        deal_type, entry = _field(deal, "type"), _field(deal, "entry")
        symbol = str(_field(deal, "symbol") or "unknown")
        info = self.terminal.symbol_info(symbol) if symbol != "unknown" else None
        profit_currency = _field(info, "currency_profit")
        account_currency = _field(account, "currency")
        commission = Decimal(str(_field(deal, "commission", 0)))
        fee = Decimal(str(_field(deal, "fee", 0)))
        milliseconds = _field(deal, "time_msc")
        timestamp = datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat() if milliseconds else None
        # A reversing deal requires splitting against its position history. Keep
        # it visible as unmapped rather than silently opening a wrong position.
        known = deal_type in (0, 1) and entry in (0, 1, 3) and info is not None
        side = ("BUY" if deal_type == 0 else "SELL") + ("_OPEN" if entry == 0 else "_CLOSE") if known else None
        metadata = {"multiplier": _field(info, "trade_contract_size"),
                    "position_id": _field(deal, "position_id"), "order_id": _field(deal, "order"),
                    "timezone": "UTC", "time_precision": "millisecond",
                    "position_effect": "OPEN" if entry == 0 else "CLOSE",
                    "fee_components": [{"amount": str(-commission - fee), "currency": account_currency}],
                    "reported_profit": _field(deal, "profit"), "swap": _field(deal, "swap"),
                    "account_currency": account_currency, "deal_entry": entry}
        # Broker corrections may change costs, timing or instrument metadata
        # without changing the immutable deal ticket.
        revision = hashlib.sha256(json.dumps({
            "type": deal_type, "entry": entry, "symbol": symbol,
            "volume": _field(deal, "volume"), "price": _field(deal, "price"),
            "occurred_at": timestamp, "commission": str(commission), "fee": str(fee),
            "currency": profit_currency, "metadata": metadata,
        }, sort_keys=True, default=str).encode()).hexdigest()
        return NormalizedEvent(str(_field(deal, "ticket")), revision,
                               self._account_id(account), "source_declared", symbol,
                               "fill" if known else "unmapped_deal", side, _field(deal, "volume"),
                               _field(deal, "price"), profit_currency,
                               -commission - fee if profit_currency == account_currency else None,
                               timestamp, datetime.now(timezone.utc).isoformat(),
                               "ok" if known and profit_currency == account_currency else "requires_mapping",
                               "metatrader-investor", metadata)

    def read_positions(self, credentials=None):
        account = self._require()
        positions = self.terminal.positions_get()
        if positions is None:
            raise RuntimeError("terminal_positions_unavailable")
        return tuple(NormalizedPosition(self._account_id(account), "source_declared", str(_field(p, "symbol")),
                                        Decimal(str(_field(p, "volume"))) * (-1 if _field(p, "type") == 1 else 1),
                                        _field(p, "price_open"), currency=_field(account, "currency"),
                                        source="metatrader-investor", metadata={"quantity_unit": "lot"}) for p in positions)

    def disconnect(self):
        # Do not change terminal login/account state, even on disconnect.
        self._disconnected = True
        self._credentials = None
