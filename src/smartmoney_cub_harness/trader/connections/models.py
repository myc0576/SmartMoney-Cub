"""Read-only connection contracts used by the global journal.

Optional transports are initialized only after explicit user connection. Adapters
receive local/server-side credentials and return normalized records with enough
provenance for a caller to decide whether a record is usable as journal data.
Values which may contain secrets never appear in the public DTOs.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from smartmoney_cub_harness.safety import REDACTED, redact
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

CONNECTION_MANIFEST_SCHEMA = "smartmoney_cub_connection_manifest.v1"
CONNECTION_CURSOR_SCHEMA = "smartmoney_cub_connection_cursor.v1"
CONNECTION_SYNC_SCHEMA = "smartmoney_cub_connection_sync.v1"

_FORBIDDEN_WORDS = ("order", "cancel", "trade_execution", "account_mutation", "broker")


def _decimal(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("invalid_decimal_value")
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("invalid_decimal_value")
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid_decimal_value") from None


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class OfficialLink:
    label: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {"label": self.label, "url": self.url}


@dataclass(frozen=True, slots=True)
class AuthSpec:
    """How a user obtains read access; secrets stay outside this DTO."""

    mode: str
    fields: tuple[str, ...] = ()
    secret_storage: str = "local_server_only"
    read_only: bool = True
    scopes: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.read_only:
            raise ValueError("connection auth must be read-only")
        for scope in self.scopes:
            lowered = scope.lower()
            if any(fragment in lowered for fragment in _FORBIDDEN_WORDS):
                raise ValueError(f"forbidden auth scope: {scope}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "fields": list(self.fields),
            "secret_storage": self.secret_storage,
            "read_only": self.read_only,
            "scopes": list(self.scopes),
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class HistorySpec:
    start: str | None = None
    end: str | None = None
    precision: str = "unknown"
    timezones: tuple[str, ...] = ()
    incremental: bool = True
    max_page_size: int = 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "precision": self.precision,
            "timezones": list(self.timezones),
            "incremental": self.incremental,
            "max_page_size": self.max_page_size,
        }


@dataclass(frozen=True, slots=True)
class ValidationStatus:
    status: str = "unverified"
    checked_at: str | None = None
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "checked_at": self.checked_at, "issues": list(self.issues)}


@dataclass(frozen=True, slots=True)
class ConnectionManifest:
    provider_id: str
    name: str
    description: str
    official_links: tuple[OfficialLink, ...]
    auth: AuthSpec
    supported_assets: tuple[str, ...]
    capabilities: tuple[str, ...] = ("read_accounts", "read_events", "read_positions")
    history: HistorySpec = field(default_factory=HistorySpec)
    validation: ValidationStatus = field(default_factory=ValidationStatus)
    network_required: bool = False
    safety: str = SAFETY_DECLARATION
    schema: str = CONNECTION_MANIFEST_SCHEMA

    def __post_init__(self) -> None:
        if self.safety != SAFETY_DECLARATION:
            raise ValueError("invalid connection safety declaration")
        if not self.provider_id.strip():
            raise ValueError("provider_id is required")
        if not self.official_links:
            raise ValueError("at least one official link is required")
        for capability in self.capabilities:
            lowered = capability.lower()
            if any(fragment in lowered for fragment in _FORBIDDEN_WORDS):
                raise ValueError(f"forbidden capability: {capability}")

    @property
    def required_scopes(self) -> tuple[str, ...]:
        return self.auth.scopes

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "provider_id": self.provider_id,
            "name": self.name,
            "description": self.description,
            "official_links": [link.to_dict() for link in self.official_links],
            "auth": self.auth.to_dict(),
            "supported_assets": list(self.supported_assets),
            "capabilities": list(self.capabilities),
            "history": self.history.to_dict(),
            "validation": self.validation.to_dict(),
            "network_required": self.network_required,
            "safety": self.safety,
        }


@dataclass(frozen=True, slots=True)
class CredentialBundle:
    """Private credential input; values are deliberately omitted from output."""

    provider_id: str
    values: Mapping[str, Any] = field(default_factory=dict, repr=False)
    permissions: Mapping[str, bool | None] = field(default_factory=dict, repr=False)
    expires_at: str | None = None

    def redacted(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "fields": sorted(str(key) for key in self.values),
            "permissions": {str(key): value for key, value in self.permissions.items()},
            "expires_at": self.expires_at,
            "secret_values": REDACTED,
            "safety": SAFETY_DECLARATION,
        }

    def to_dict(self) -> dict[str, Any]:
        return self.redacted()


@dataclass(frozen=True, slots=True)
class ScopeValidation:
    allowed: bool
    status: str
    required: tuple[str, ...] = ()
    granted: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()
    safety: str = SAFETY_DECLARATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "required": list(self.required),
            "granted": list(self.granted),
            "missing": list(self.missing),
            "issues": list(self.issues),
            "safety": self.safety,
        }


def validate_read_scope(
    required: tuple[str, ...] | list[str], credentials: CredentialBundle | None, *, provider_id: str
) -> ScopeValidation:
    """Validate scopes without ever treating unknown permission as consent."""

    required_tuple = tuple(str(item) for item in required)
    if not required_tuple:
        return ScopeValidation(True, "verified", safety=SAFETY_DECLARATION)
    if credentials is None:
        return ScopeValidation(
            False,
            "missing",
            required=required_tuple,
            missing=required_tuple,
            issues=(f"credentials_required:{provider_id}",),
        )
    if credentials.provider_id != provider_id:
        return ScopeValidation(
            False,
            "denied",
            required=required_tuple,
            missing=required_tuple,
            issues=("credential_provider_mismatch",),
        )
    granted: list[str] = []
    unknown: list[str] = []
    denied: list[str] = []
    for scope in required_tuple:
        value = credentials.permissions.get(scope)
        if value is True:
            granted.append(scope)
        elif value is False:
            denied.append(scope)
        else:
            unknown.append(scope)
    if denied:
        return ScopeValidation(
            False,
            "denied",
            required_tuple,
            tuple(granted),
            tuple(denied),
            tuple(f"scope_denied:{scope}" for scope in denied),
        )
    if unknown:
        return ScopeValidation(
            False,
            "unknown",
            required_tuple,
            tuple(granted),
            tuple(unknown),
            tuple(f"scope_unknown:{scope}" for scope in unknown),
        )
    return ScopeValidation(True, "verified", required_tuple, tuple(granted), ())


@dataclass(frozen=True, slots=True)
class ConnectionAccount:
    account_id: str
    display_name: str
    provider: str
    asset_class: str = "unknown"
    currency: str | None = None
    permissions: tuple[str, ...] = ()
    status: str = "active"
    safety: str = SAFETY_DECLARATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "display_name": self.display_name,
            "provider": self.provider,
            "asset_class": self.asset_class,
            "currency": self.currency,
            "permissions": list(self.permissions),
            "status": self.status,
            "safety": self.safety,
        }


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    external_id: str
    revision: str | int
    account_id: str
    asset: str
    symbol: str
    event_type: str
    side: str | None = None
    quantity: Decimal | int | float | str | None = None
    price: Decimal | int | float | str | None = None
    currency: str | None = None
    fee: Decimal | int | float | str | None = None
    occurred_at: str | None = None
    available_at: str | None = None
    data_quality: str = "ok"
    source: str = "unknown"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    safety: str = SAFETY_DECLARATION

    def __post_init__(self) -> None:
        if self.safety != SAFETY_DECLARATION:
            raise ValueError("invalid event safety declaration")
        _decimal(self.quantity)
        _decimal(self.price)
        _decimal(self.fee)

    def to_dict(self) -> dict[str, Any]:
        return {
            "external_id": self.external_id,
            "revision": str(self.revision),
            "account_id": self.account_id,
            "asset": self.asset,
            "symbol": self.symbol,
            "event_type": self.event_type,
            "side": self.side,
            "quantity": None if self.quantity is None else format(_decimal(self.quantity), "f"),
            "price": None if self.price is None else format(_decimal(self.price), "f"),
            "currency": self.currency,
            "fee": None if self.fee is None else format(_decimal(self.fee), "f"),
            "occurred_at": self.occurred_at,
            "available_at": self.available_at,
            "data_quality": self.data_quality,
            "source": self.source,
            "metadata": redact(_json_value(dict(self.metadata))),
            "safety": self.safety,
        }


@dataclass(frozen=True, slots=True)
class NormalizedPosition:
    account_id: str
    asset: str
    symbol: str
    quantity: Decimal | int | float | str | None
    average_price: Decimal | int | float | str | None = None
    market_value: Decimal | int | float | str | None = None
    currency: str | None = None
    as_of: str | None = None
    data_quality: str = "ok"
    source: str = "unknown"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    safety: str = SAFETY_DECLARATION

    def to_dict(self) -> dict[str, Any]:
        def render(value: Any) -> str | None:
            return None if value is None else format(_decimal(value), "f")

        return {
            "account_id": self.account_id,
            "asset": self.asset,
            "symbol": self.symbol,
            "quantity": render(self.quantity),
            "average_price": render(self.average_price),
            "market_value": render(self.market_value),
            "currency": self.currency,
            "as_of": self.as_of,
            "data_quality": self.data_quality,
            "source": self.source,
            "metadata": redact(_json_value(dict(self.metadata))),
            "safety": self.safety,
        }


@dataclass(frozen=True, slots=True)
class EventPage:
    events: tuple[NormalizedEvent, ...] = ()
    next_cursor: "ConnectionCursor | None" = None
    checkpoint_cursor: "ConnectionCursor | None" = None
    partial: bool = False
    errors: tuple[str, ...] = ()
    safety: str = SAFETY_DECLARATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [event.to_dict() for event in self.events],
            "next_cursor": self.next_cursor.to_dict() if self.next_cursor else None,
            "checkpoint_cursor": self.checkpoint_cursor.to_dict() if self.checkpoint_cursor else None,
            "partial": self.partial,
            "errors": list(self.errors),
            "safety": self.safety,
        }


@dataclass(frozen=True, slots=True)
class ConnectionCursor:
    provider_id: str
    token: str = ""
    revision: str | None = None
    as_of: str | None = None
    schema: str = CONNECTION_CURSOR_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "provider_id": self.provider_id,
            "token": self.token,
            "revision": self.revision,
            "as_of": self.as_of,
            "safety": SAFETY_DECLARATION,
        }

    def encode(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(payload).decode().rstrip("=")

    @classmethod
    def decode(cls, value: str | Mapping[str, Any] | None) -> "ConnectionCursor | None":
        if value is None or value == "":
            return None
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            payload = dict(value)
        else:
            padded = str(value) + "=" * (-len(str(value)) % 4)
            try:
                payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
            except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("invalid durable connection cursor") from exc
        if payload.get("schema") not in (None, CONNECTION_CURSOR_SCHEMA):
            raise ValueError("invalid cursor schema")
        if payload.get("safety") not in (None, SAFETY_DECLARATION):
            raise ValueError("invalid cursor safety")
        provider_id = str(payload.get("provider_id") or "")
        if not provider_id:
            raise ValueError("cursor provider_id is required")
        return cls(provider_id, str(payload.get("token") or ""), payload.get("revision"), payload.get("as_of"))


@dataclass(frozen=True, slots=True)
class SyncResult:
    provider_id: str
    cursor: ConnectionCursor | None
    accounts: tuple[ConnectionAccount, ...] = ()
    events: tuple[NormalizedEvent, ...] = ()
    positions: tuple[NormalizedPosition, ...] = ()
    duplicate_count: int = 0
    updated_count: int = 0
    partial: bool = False
    blocked: bool = False
    errors: tuple[str, ...] = ()
    attempts: int = 0
    disconnected: bool = False
    scope: ScopeValidation | None = None
    safety: str = SAFETY_DECLARATION
    schema: str = CONNECTION_SYNC_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "provider_id": self.provider_id,
            "cursor": self.cursor.to_dict() if self.cursor else None,
            "accounts": [account.to_dict() for account in self.accounts],
            "events": [event.to_dict() for event in self.events],
            "positions": [position.to_dict() for position in self.positions],
            "duplicate_count": self.duplicate_count,
            "updated_count": self.updated_count,
            "partial": self.partial,
            "blocked": self.blocked,
            "errors": list(self.errors),
            "attempts": self.attempts,
            "disconnected": self.disconnected,
            "scope": self.scope.to_dict() if self.scope else None,
            "safety": self.safety,
        }


def event_from_dict(payload: Mapping[str, Any]) -> NormalizedEvent:
    return NormalizedEvent(
        external_id=str(payload["external_id"]),
        revision=str(payload.get("revision", "1")),
        account_id=str(payload.get("account_id") or "unknown-account"),
        asset=str(payload.get("asset") or "unknown"),
        symbol=str(payload.get("symbol") or "unknown"),
        event_type=str(payload.get("event_type") or "unknown"),
        side=payload.get("side"),
        quantity=payload.get("quantity"),
        price=payload.get("price"),
        currency=payload.get("currency"),
        fee=payload.get("fee"),
        occurred_at=payload.get("occurred_at"),
        available_at=payload.get("available_at"),
        data_quality=str(payload.get("data_quality") or "unknown"),
        source=str(payload.get("source") or "unknown"),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {},
        safety=str(payload.get("safety") or SAFETY_DECLARATION),
    )
