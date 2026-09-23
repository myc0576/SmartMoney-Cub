"""Offline toy adapters for every supported connection family."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

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


@dataclass
class FixtureConnection:
    """A deterministic in-memory adapter; it intentionally performs no I/O."""

    provider_id: str
    _accounts: tuple[ConnectionAccount, ...] = ()
    _events: tuple[NormalizedEvent, ...] = ()
    _positions: tuple[NormalizedPosition, ...] = ()
    page_size: int = 2
    fail_pages: frozenset[int] = frozenset()
    _disconnected: bool = False

    def __post_init__(self) -> None:
        self._manifest = get_manifest(self.provider_id)
        self._events = tuple(self._events)
        self._accounts = tuple(self._accounts)
        self._positions = tuple(self._positions)

    def metadata(self) -> ConnectionManifest:
        return self._manifest

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        return validate_read_scope(self._manifest.required_scopes, credentials, provider_id=self.provider_id)

    def _require_access(self, credentials: CredentialBundle | None) -> ScopeValidation:
        scope = self.validate_read_access(credentials)
        if not scope.allowed:
            raise PermissionConnectionError("read access is not verified")
        return scope

    def list_accounts(self, credentials: CredentialBundle | None = None) -> tuple[ConnectionAccount, ...]:
        self._require_access(credentials)
        if self._disconnected:
            return ()
        return self._accounts

    def read_events(
        self,
        cursor: ConnectionCursor | None = None,
        credentials: CredentialBundle | None = None,
    ) -> EventPage:
        self._require_access(credentials)
        if self._disconnected:
            return EventPage()
        if cursor and cursor.provider_id != self.provider_id:
            raise ValueError("cursor provider does not match adapter")
        offset = int(cursor.token or 0) if cursor else 0
        page = offset // max(1, self.page_size)
        if page in self.fail_pages:
            return EventPage(partial=True, errors=(f"fixture_page_failure:{page}",))
        chunk = self._events[offset : offset + max(1, self.page_size)]
        next_offset = offset + len(chunk)
        next_cursor = (
            ConnectionCursor(self.provider_id, str(next_offset), revision=str(next_offset))
            if next_offset < len(self._events)
            else None
        )
        checkpoint = ConnectionCursor(self.provider_id, str(next_offset), revision=str(next_offset))
        return EventPage(events=chunk, next_cursor=next_cursor, checkpoint_cursor=checkpoint)

    def read_positions(self, credentials: CredentialBundle | None = None) -> tuple[NormalizedPosition, ...]:
        self._require_access(credentials)
        return () if self._disconnected else self._positions

    def disconnect(self) -> None:
        self._disconnected = True


def _event(provider: str, index: int, symbol: str, *, revision: str = "1") -> NormalizedEvent:
    return NormalizedEvent(
        external_id=f"{provider}-evt-{index}",
        revision=revision,
        account_id="fixture-account",
        asset="crypto" if provider.startswith("ccxt") else "stocks",
        symbol=symbol,
        event_type="fill",
        side="buy",
        quantity="1.25",
        price="100.00",
        currency="USD",
        fee="0.10",
        occurred_at=f"2026-01-01T00:00:0{index}Z",
        available_at=f"2026-01-01T00:00:0{index}Z",
        source=provider,
    )


def fixture_adapter(provider_id: str, *, page_size: int = 2, fail_pages: Iterable[int] = ()) -> FixtureConnection:
    """Return a synthetic adapter for tests and demos, never a live provider."""

    events = tuple(_event(provider_id, index, "BTC/USDT" if provider_id.startswith("ccxt") else "AAPL") for index in range(1, 5))
    account = ConnectionAccount("fixture-account", "Toy account", provider_id, "crypto" if provider_id.startswith("ccxt") else "equity", "USD", ("read",))
    position = NormalizedPosition("fixture-account", account.asset_class, "BTC/USDT" if provider_id.startswith("ccxt") else "AAPL", "1.25", "100", "125", "USD", "2026-01-01T00:00:00Z", source=provider_id)
    return FixtureConnection(provider_id, (account,), events, (position,), page_size, frozenset(fail_pages))


def all_fixture_adapters() -> tuple[FixtureConnection, ...]:
    return tuple(fixture_adapter(manifest.provider_id) for manifest in (get_manifest(item) for item in (
        "ccxt-binance", "ccxt-okx", "ibkr-flex", "metatrader-investor", "local-statement-directory", "snaptrade-personal-mcp", "vezgo"
    )))
