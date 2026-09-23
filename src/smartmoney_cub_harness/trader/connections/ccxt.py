"""Direct, strictly read-only CCXT account adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from .manifests import get_manifest
from .models import (
    ConnectionAccount,
    ConnectionCursor,
    CredentialBundle,
    EventPage,
    NormalizedEvent,
    NormalizedPosition,
    ScopeValidation,
)
from .protocol import PermissionConnectionError


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _iso_millis(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat(timespec="milliseconds")
    except (TypeError, ValueError, OSError):
        return str(value)


class CCXTConnection:
    """Wrap a caller-owned CCXT exchange and expose read operations only."""

    def __init__(
        self,
        provider_id: str,
        exchange: Any,
        credentials: CredentialBundle,
        *,
        symbols: list[str] | tuple[str, ...],
        since: int | None = None,
        limit: int = 1000,
        account_id: str | None = None,
    ) -> None:
        if provider_id not in {"ccxt-binance", "ccxt-okx"}:
            raise ValueError("unsupported CCXT provider")
        if not symbols or not all(isinstance(symbol, str) and symbol.strip() for symbol in symbols):
            raise ValueError("CCXT symbols must be a non-empty list")
        if limit < 1 or limit > 1000:
            raise ValueError("CCXT page limit must be between 1 and 1000")
        self.provider_id = provider_id
        self._exchange = exchange
        self._credentials = credentials
        self._symbols = tuple(symbols)
        self._since = int(since) if since is not None else None
        self._limit = int(limit)
        self._account_id = account_id or provider_id
        self._disconnected = False
        self._last_scope: ScopeValidation | None = None

    def metadata(self):
        return get_manifest(self.provider_id)

    def bind_credentials(self, credentials: CredentialBundle) -> None:
        if credentials.provider_id != self.provider_id:
            raise ValueError("credential provider mismatch")
        self._credentials = credentials
        values = credentials.values
        if hasattr(self._exchange, "apiKey"):
            self._exchange.apiKey = values.get("api_key")
        if hasattr(self._exchange, "secret"):
            self._exchange.secret = values.get("api_secret")
        if hasattr(self._exchange, "password"):
            self._exchange.password = values.get("passphrase")
        self._last_scope = None

    def _missing_credentials(self, credentials: CredentialBundle) -> tuple[str, ...]:
        required = ["api_key", "api_secret"]
        if self.provider_id == "ccxt-okx":
            required.append("passphrase")
        return tuple(field for field in required if not str(credentials.values.get(field) or "").strip())

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        supplied = credentials or self._credentials
        if supplied is None or supplied.provider_id != self.provider_id:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=("credentials_required",))
        missing = self._missing_credentials(supplied)
        if missing:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=tuple(f"missing_field:{field}" for field in missing))
        try:
            checker = getattr(self._exchange, "check_required_credentials", None)
            if callable(checker):
                checker()
            if self.provider_id == "ccxt-binance":
                method = next(
                    (
                        getattr(self._exchange, name, None)
                        for name in (
                            "fetch_api_restrictions",
                            "sapiGetAccountApiRestrictions",
                            "privateGetSapiV1AccountApiRestrictions",
                        )
                        if callable(getattr(self._exchange, name, None))
                    ),
                    None,
                )
                if not callable(method):
                    return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("binance_permission_endpoint_unavailable",))
                payload = method({})
                scope = self._validate_binance(payload)
            else:
                method = next(
                    (
                        getattr(self._exchange, name, None)
                        for name in ("fetch_account_config", "privateGetAccountConfig", "account_config")
                        if callable(getattr(self._exchange, name, None))
                    ),
                    None,
                )
                if not callable(method):
                    return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("okx_permission_endpoint_unavailable",))
                payload = method({})
                scope = self._validate_okx(payload)
        except Exception as exc:
            scope = ScopeValidation(
                False,
                "unknown",
                required=("read",),
                missing=("read",),
                issues=(f"private_permission_check_failed:{type(exc).__name__}",),
            )
        self._last_scope = scope
        return scope

    @staticmethod
    def _validate_binance(payload: Any) -> ScopeValidation:
        if not isinstance(payload, Mapping) or payload.get("enableReading") is not True:
            return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("binance_read_permission_unknown",))
        required_flags = ("enableSpotAndMarginTrading", "enableWithdrawals", "enableMargin", "enableFutures")
        if any(flag not in payload for flag in required_flags):
            return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("binance_restrictions_incomplete",))
        mutation_flags = (
            *required_flags,
            "enableInternalTransfer",
            "permitsUniversalTransfer",
            "enableVanillaOptions",
            "enableFixApiTrade",
            "enablePortfolioMarginTrading",
        )
        granted = tuple(flag for flag in mutation_flags if payload.get(flag) is True)
        if granted:
            return ScopeValidation(False, "denied", required=("read",), missing=("read",), issues=tuple(f"mutating_permission:{flag}" for flag in granted))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))

    @staticmethod
    def _validate_okx(payload: Any) -> ScopeValidation:
        if not isinstance(payload, Mapping):
            return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("okx_config_not_object",))
        data = payload.get("data")
        row = data[0] if isinstance(data, list) and data and isinstance(data[0], Mapping) else payload
        permission = row.get("perm") if isinstance(row, Mapping) else None
        if not isinstance(permission, str):
            return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("okx_permission_unknown",))
        permissions = {item.strip().lower() for item in permission.split(",") if item.strip()}
        if "read_only" not in permissions:
            return ScopeValidation(False, "denied", required=("read",), missing=("read",), issues=("okx_read_only_missing",))
        mutating = permissions & {"trade", "withdraw"}
        if mutating:
            return ScopeValidation(False, "denied", required=("read",), missing=("read",), issues=tuple(f"mutating_permission:{item}" for item in sorted(mutating)))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))

    def _require_access(self, credentials: CredentialBundle | None) -> None:
        if self._disconnected:
            raise PermissionConnectionError("connection_disconnected")
        scope = self._last_scope if credentials is None and self._last_scope else self.validate_read_access(credentials)
        if not scope.allowed:
            raise PermissionConnectionError("read_access_not_verified")

    def list_accounts(self, credentials: CredentialBundle | None = None) -> tuple[ConnectionAccount, ...]:
        self._require_access(credentials)
        balance = self._exchange.fetch_balance(params={})
        info = balance.get("info") if isinstance(balance, Mapping) else {}
        account_id = str(
            (info.get("uid") or info.get("accountId") or info.get("acctId"))
            if isinstance(info, Mapping)
            else self._account_id
        )
        if account_id in {"", "None"}:
            account_id = self._account_id
        # Use the same identity for accounts and executions. Explicit caller
        # mapping is stable even when a provider omits uid from its balance DTO.
        return (ConnectionAccount(self._account_id, self.provider_id, self.provider_id, "crypto", None, ("read",)),)

    def _cursor_payload(self, cursor: ConnectionCursor | None) -> dict[str, Any]:
        if cursor is None or not cursor.token:
            return {"symbol_index": 0, "since": self._since}
        if cursor.provider_id != self.provider_id:
            raise ValueError("cursor provider mismatch")
        try:
            payload = json.loads(cursor.token)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid CCXT cursor") from exc
        if not isinstance(payload, dict):
            raise ValueError("invalid CCXT cursor")
        return payload

    def _cursor(self, symbol_index: int, since: int | None) -> ConnectionCursor:
        token = json.dumps({"symbol_index": symbol_index, "since": since}, sort_keys=True, separators=(",", ":"))
        return ConnectionCursor(self.provider_id, token, revision=str(since) if since is not None else None)

    def read_events(self, cursor: ConnectionCursor | None = None, credentials: CredentialBundle | None = None) -> EventPage:
        self._require_access(credentials)
        state = self._cursor_payload(cursor)
        index = int(state.get("symbol_index", 0))
        since = state.get("since")
        since = int(since) if since is not None else None
        if index >= len(self._symbols):
            checkpoint = ConnectionCursor(self.provider_id)
            return EventPage(checkpoint_cursor=checkpoint)
        symbol = self._symbols[index]
        params = {}
        if self.provider_id == "ccxt-binance" and state.get("from_id") is not None:
            params["fromId"] = state["from_id"]
        rows = self._exchange.fetch_my_trades(symbol, since, self._limit, params)
        if not isinstance(rows, list):
            raise ValueError("CCXT fetch_my_trades must return a list")
        events = tuple(self._normalize_trade(symbol, row, offset) for offset, row in enumerate(rows) if isinstance(row, Mapping))
        timestamps = [int(row["timestamp"]) for row in rows if isinstance(row, Mapping) and row.get("timestamp") is not None]
        if len(rows) >= self._limit and timestamps:
            if self.provider_id == "ccxt-binance" and all(str(row.get("id", "")).isdigit() for row in rows):
                next_state = ConnectionCursor(self.provider_id, json.dumps({"symbol_index": index, "since": None, "from_id": max(int(row["id"]) for row in rows) + 1}))
            else:
                # Inclusive boundary avoids dropping fills sharing a millisecond.
                # A saturated boundary that cannot advance is an explicit gap,
                # never a silently successful history truncation.
                if since is not None and max(timestamps) <= since:
                    return EventPage(events, partial=True, errors=("timestamp_boundary_saturated_use_statement_import",))
                next_state = self._cursor(index, max(timestamps))
        else:
            next_state = self._cursor(index + 1, self._since)
        next_cursor = next_state if index + 1 < len(self._symbols) or len(rows) >= self._limit else None
        checkpoint = next_state if next_cursor else ConnectionCursor(self.provider_id)
        return EventPage(events=events, next_cursor=next_cursor, checkpoint_cursor=checkpoint)

    def _normalize_trade(self, symbol: str, row: Mapping[str, Any], offset: int) -> NormalizedEvent:
        safe = {
            "id": row.get("id"),
            "order": row.get("order"),
            "timestamp": row.get("timestamp"),
            "datetime": row.get("datetime"),
            "symbol": row.get("symbol") or symbol,
            "side": row.get("side"),
            "amount": row.get("amount"),
            "price": row.get("price"),
            "cost": row.get("cost"),
            "takerOrMaker": row.get("takerOrMaker"),
            "fee": row.get("fee"),
        }
        identity = str(row.get("id") or f"synthetic-{_canonical_hash(safe)}")
        fee = row.get("fee") if isinstance(row.get("fee"), Mapping) else {}
        quote_currency = str(row.get("symbol") or symbol).split("/")[-1].split(":")[0]
        occurred = row.get("datetime") or _iso_millis(row.get("timestamp"))
        return NormalizedEvent(
            external_id=identity,
            revision=_canonical_hash(safe),
            account_id=self._account_id,
            asset="crypto",
            symbol=str(row.get("symbol") or symbol),
            event_type="fill",
            side=str(row.get("side")) if row.get("side") is not None else None,
            quantity=row.get("amount"),
            price=row.get("price"),
            currency=quote_currency,
            fee=fee.get("cost") if fee.get("currency") == quote_currency else None,
            occurred_at=str(occurred) if occurred else None,
            available_at=str(row.get("available_at") or row.get("settlement_date")) if (row.get("available_at") or row.get("settlement_date")) else None,
            source=self.provider_id,
            metadata={"order_id": row.get("order"), "liquidity": row.get("takerOrMaker"), "cost": row.get("cost"),
                      "fee_components": [dict(fee)] if fee else [], "timezone": "UTC", "time_precision": "millisecond"},
        )

    def read_positions(self, credentials: CredentialBundle | None = None) -> tuple[NormalizedPosition, ...]:
        self._require_access(credentials)
        balance = self._exchange.fetch_balance(params={})
        totals = balance.get("total") if isinstance(balance, Mapping) else {}
        if not isinstance(totals, Mapping):
            return ()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return tuple(
            NormalizedPosition(self._account_id, "crypto", str(currency), quantity, currency=str(currency), as_of=now, source=self.provider_id)
            for currency, quantity in totals.items()
            if quantity not in (None, 0, 0.0, "0", "0.0")
        )

    def disconnect(self) -> None:
        self._credentials = None
        self._last_scope = None
        self._disconnected = True
