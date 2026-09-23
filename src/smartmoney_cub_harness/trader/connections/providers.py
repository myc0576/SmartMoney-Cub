"""Optional transport-backed adapters.

These adapters do not create clients, discover credentials, or perform network
I/O. A host injects a provider SDK/HTTP transport explicitly. The wrappers
expose only read methods and normalize structural responses into journal DTOs.
"""

from __future__ import annotations

import csv
import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .manifests import get_manifest
from .models import (
    ConnectionAccount,
    ConnectionCursor,
    ConnectionManifest,
    CredentialBundle,
    EventPage,
    NormalizedEvent,
    NormalizedPosition,
    ScopeValidation,
    validate_read_scope,
)
from .protocol import PermissionConnectionError


class StructuralTransport(Protocol):
    """A caller-owned SDK/HTTP bridge returning decoded structural objects."""

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> Any: ...


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        for key in ("data", "items", "results", "activities", "trades", "positions", "accounts"):
            nested = value.get(key)
            if isinstance(nested, (list, tuple)):
                return tuple(item for item in nested if isinstance(item, Mapping))
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _first(row: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


def _event(provider: str, row: Mapping[str, Any], index: int) -> NormalizedEvent:
    external_id = _first(row, "external_id", "id", "transaction_id", "trade_id", "execution_id", default=f"{provider}-row-{index}")
    return NormalizedEvent(
        external_id=str(external_id),
        revision=str(_first(row, "revision", "version", "updated_at", default="1")),
        account_id=str(_first(row, "account_id", "accountId", "account", default="unknown-account")),
        asset=str(_first(row, "asset", "asset_class", "assetClass", default="unknown")),
        symbol=str(_first(row, "symbol", "ticker", "instrument", default="unknown")),
        event_type=str(_first(row, "event_type", "type", "activity_type", default="fill")),
        side=_first(row, "side", "action", "buy_sell"),
        quantity=_first(row, "quantity", "units", "qty"),
        price=_first(row, "price", "execution_price", "fill_price"),
        currency=_first(row, "currency", "currency_code", "ccy"),
        fee=_first(row, "fee", "fees", "commission"),
        occurred_at=_first(row, "occurred_at", "trade_date", "date", "timestamp"),
        available_at=_first(row, "available_at", "settlement_date", "date", "timestamp"),
        data_quality=str(_first(row, "data_quality", default="ok")),
        source=provider,
        metadata={str(key): value for key, value in row.items() if key not in {"api_key", "secret", "token", "password"}},
    )


def _position(provider: str, row: Mapping[str, Any], index: int) -> NormalizedPosition:
    return NormalizedPosition(
        account_id=str(_first(row, "account_id", "accountId", "account", default="unknown-account")),
        asset=str(_first(row, "asset", "asset_class", "assetClass", default="unknown")),
        symbol=str(_first(row, "symbol", "ticker", "instrument", default="unknown")),
        quantity=_first(row, "quantity", "units", "qty", default="0"),
        average_price=_first(row, "average_price", "avg_price", "averagePrice"),
        market_value=_first(row, "market_value", "marketValue", "value"),
        currency=_first(row, "currency", "currency_code", "ccy"),
        as_of=_first(row, "as_of", "timestamp", "updated_at"),
        data_quality=str(_first(row, "data_quality", default="ok")),
        source=provider,
        metadata={str(key): value for key, value in row.items() if key not in {"api_key", "secret", "token", "password"}},
    )


@dataclass
class TransportConnection:
    """Generic structural transport adapter used by provider-specific wrappers."""

    provider_id: str
    transport: StructuralTransport
    credentials: CredentialBundle | None = None

    def __post_init__(self) -> None:
        self._manifest = get_manifest(self.provider_id)
        self._disconnected = False

    def metadata(self) -> ConnectionManifest:
        return self._manifest

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        return validate_read_scope(self._manifest.required_scopes, credentials or self.credentials, provider_id=self.provider_id)

    def _require_access(self, credentials: CredentialBundle | None) -> None:
        if self._disconnected:
            raise PermissionConnectionError("connection is disconnected")
        if not self.validate_read_access(credentials).allowed:
            raise PermissionConnectionError("read access is not verified")

    def _call(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        return self.transport.call(method, params or {})

    def list_accounts(self, credentials: CredentialBundle | None = None) -> tuple[ConnectionAccount, ...]:
        self._require_access(credentials)
        return tuple(
            ConnectionAccount(
                account_id=str(_first(row, "account_id", "id", "accountId", default=f"{self.provider_id}-{index}")),
                display_name=str(_first(row, "display_name", "name", "accountName", default="Connected account")),
                provider=self.provider_id,
                asset_class=str(_first(row, "asset_class", "assetClass", default="unknown")),
                currency=_first(row, "currency", "currency_code"),
                permissions=("read",),
            )
            for index, row in enumerate(_rows(self._call("list_accounts")), start=1)
        )

    def read_events(self, cursor: ConnectionCursor | None = None, credentials: CredentialBundle | None = None) -> EventPage:
        self._require_access(credentials)
        params = {"cursor": cursor.token} if cursor else {}
        payload = self._call("read_events", params)
        rows = _rows(payload)
        next_token = _first(_mapping(payload), "next_cursor", "nextCursor", "cursor")
        next_cursor = ConnectionCursor(self.provider_id, str(next_token)) if next_token else None
        errors = tuple(str(item) for item in (_mapping(payload).get("errors") or ()) if item)
        checkpoint = next_cursor
        return EventPage(
            events=tuple(_event(self.provider_id, row, index) for index, row in enumerate(rows)),
            next_cursor=next_cursor,
            checkpoint_cursor=checkpoint,
            partial=bool(errors),
            errors=errors,
        )

    def read_positions(self, credentials: CredentialBundle | None = None) -> tuple[NormalizedPosition, ...]:
        self._require_access(credentials)
        return tuple(_position(self.provider_id, row, index) for index, row in enumerate(_rows(self._call("read_positions"))))

    def disconnect(self) -> None:
        self._disconnected = True


class CCXTReadOnlyConnection(TransportConnection):
    """CCXT wrapper with a strict read-method allowlist."""

    def __init__(self, exchange: Any, provider_id: str, credentials: CredentialBundle | None = None) -> None:
        if provider_id not in {"ccxt-binance", "ccxt-okx"}:
            raise ValueError("CCXTReadOnlyConnection requires a supported CCXT provider id")
        self.exchange = exchange

        class _ExchangeTransport:
            def call(_, method: str, params: Mapping[str, Any] | None = None) -> Any:
                allowed = {"list_accounts": "fetch_balance", "read_events": "fetch_my_trades", "read_positions": "fetch_balance"}
                target = allowed.get(method)
                if target is None:
                    raise ValueError(f"unsupported read method: {method}")
                function = getattr(exchange, target, None)
                if not callable(function):
                    raise RuntimeError(f"CCXT exchange lacks read method: {target}")
                return function(params or {})

        super().__init__(provider_id, _ExchangeTransport(), credentials)

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        """Require the exchange's private key restriction/config response."""

        supplied = credentials or self.credentials
        if supplied is None:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=("credentials_required",))
        method_names = (
            ("fetch_api_restrictions", "sapi_get_account_apirestrictions", "private_get_sapi_v1_account_apirestrictions")
            if self.provider_id == "ccxt-binance"
            else ("fetch_account_config", "private_get_account_config", "account_config")
        )
        permission_method = next(
            (getattr(self.exchange, name, None) for name in method_names if callable(getattr(self.exchange, name, None))),
            None,
        )
        if permission_method is None:
            return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("private_permission_endpoint_unavailable",))
        try:
            payload = permission_method({})
        except Exception as exc:
            return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=(f"permission_check_failed:{type(exc).__name__}",))
        rows = payload.get("data") if isinstance(payload, Mapping) else None
        row = rows[0] if isinstance(rows, (list, tuple)) and rows and isinstance(rows[0], Mapping) else payload
        if not isinstance(row, Mapping):
            return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("exchange_permissions_unknown",))
        if self.provider_id == "ccxt-binance":
            reading = row.get("enableReading")
            mutation_flags = [
                row.get("enableSpotAndMarginTrading"),
                row.get("enableMargin"),
                row.get("enableFutures"),
                row.get("enableWithdrawals"),
                row.get("enableInternalTransfer"),
                row.get("enablePortfolioMarginTrading"),
            ]
            if reading is not True or any(flag is None for flag in mutation_flags):
                return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("binance_api_restrictions_incomplete",))
            if any(bool(flag) for flag in mutation_flags):
                return ScopeValidation(False, "denied", required=("read",), missing=("read",), issues=("binance_key_has_mutating_permission",))
            return ScopeValidation(True, "verified", required=("read",), granted=("read",))
        permission = row.get("perm")
        if not isinstance(permission, str):
            return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=("okx_account_config_incomplete",))
        permissions = {item.strip().lower() for item in permission.split(",") if item.strip()}
        if "read_only" not in permissions:
            return ScopeValidation(False, "denied", required=("read",), missing=("read",), issues=("okx_read_only_permission_missing",))
        if permissions & {"trade", "withdraw"}:
            return ScopeValidation(False, "denied", required=("read",), missing=("read",), issues=("okx_key_has_mutating_permission",))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))


class IBKRFlexConnection(TransportConnection):
    """Flex adapter: trigger/fetch are supplied by the caller's report transport."""

    def __init__(self, transport: StructuralTransport, credentials: CredentialBundle | None = None) -> None:
        super().__init__("ibkr-flex", transport, credentials)

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        supplied = credentials or self.credentials
        if supplied is None:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=("credentials_required",))
        if supplied.permissions.get("read") is not True:
            return ScopeValidation(False, "unknown" if supplied.permissions.get("read") is None else "denied", required=("read",), missing=("read",), issues=("flex_read_permission_not_verified",))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))


class MetaTraderInvestorConnection(TransportConnection):
    def __init__(self, transport: StructuralTransport, credentials: CredentialBundle | None = None) -> None:
        super().__init__("metatrader-investor", transport, credentials)

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        supplied = credentials or self.credentials
        if supplied is None:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=("credentials_required",))
        if supplied.permissions.get("read") is not True:
            return ScopeValidation(False, "unknown" if supplied.permissions.get("read") is None else "denied", required=("read",), missing=("read",), issues=("investor_mode_not_verified",))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))


class SnapTradePersonalMCPConnection(TransportConnection):
    def __init__(self, transport: StructuralTransport, credentials: CredentialBundle | None = None) -> None:
        super().__init__("snaptrade-personal-mcp", transport, credentials)

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        supplied = credentials or self.credentials
        if supplied is None:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=("credentials_required",))
        if supplied.permissions.get("read") is not True:
            return ScopeValidation(False, "unknown" if supplied.permissions.get("read") is None else "denied", required=("read",), missing=("read",), issues=("snaptrade_read_scope_not_verified",))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))


class VezgoConnection(TransportConnection):
    def __init__(self, transport: StructuralTransport, credentials: CredentialBundle | None = None) -> None:
        super().__init__("vezgo", transport, credentials)

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        supplied = credentials or self.credentials
        if supplied is None:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=("credentials_required",))
        if supplied.permissions.get("read") is not True:
            return ScopeValidation(False, "unknown" if supplied.permissions.get("read") is None else "denied", required=("read",), missing=("read",), issues=("vezgo_read_permission_not_verified",))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))


class LocalStatementConnection(TransportConnection):
    """Read user-selected CSV/JSON files; it never logs into or exports from brokers."""

    def __init__(self, directory: str | Path, credentials: CredentialBundle | None = None) -> None:
        self.directory = Path(directory)
        if not self.directory.exists() or not self.directory.is_dir():
            raise ValueError("statement directory must exist and be a directory")

        statement_directory = self.directory

        class _DirectoryTransport:
            def call(_, method: str, params: Mapping[str, Any] | None = None) -> Any:
                if method == "list_accounts":
                    return [{"id": "local-statement", "name": "Local statements", "asset_class": "unknown"}]
                if method == "read_positions":
                    return []
                if method != "read_events":
                    raise ValueError(f"unsupported local statement method: {method}")
                rows: list[dict[str, Any]] = []
                for path in sorted(statement_directory.iterdir()):
                    if path.suffix.lower() == ".json":
                        payload = json.loads(path.read_text(encoding="utf-8"))
                        rows.extend(dict(row) for row in _rows(payload))
                    elif path.suffix.lower() == ".csv":
                        with path.open(newline="", encoding="utf-8") as handle:
                            rows.extend(dict(row) for row in csv.DictReader(handle))
                return rows

        super().__init__("local-statement-directory", _DirectoryTransport(), credentials)

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        supplied = credentials or self.credentials
        if supplied is None:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=("credentials_required",))
        if supplied.permissions.get("read") is not True:
            return ScopeValidation(False, "unknown" if supplied.permissions.get("read") is None else "denied", required=("read",), missing=("read",), issues=("statement_directory_not_verified",))
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))

    def _fingerprint(self) -> str:
        parts: list[str] = []
        for path in sorted(self.directory.iterdir()):
            if path.suffix.lower() not in {".csv", ".json"}:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            parts.append(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}")
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()

    def read_events(self, cursor: ConnectionCursor | None = None, credentials: CredentialBundle | None = None) -> EventPage:
        self._require_access(credentials)
        fingerprint = self._fingerprint()
        checkpoint = ConnectionCursor("local-statement-directory", fingerprint, revision=fingerprint)
        if cursor is not None and cursor.provider_id != "local-statement-directory":
            raise ValueError("cursor provider mismatch")
        if cursor is not None and cursor.token == fingerprint:
            return EventPage(checkpoint_cursor=checkpoint)
        page = super().read_events(None, credentials)
        return EventPage(
            events=page.events,
            next_cursor=None,
            checkpoint_cursor=checkpoint,
            partial=page.partial,
            errors=page.errors,
        )
