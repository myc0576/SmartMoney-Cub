"""The intentionally narrow read-only connector protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    ConnectionAccount,
    ConnectionCursor,
    ConnectionManifest,
    CredentialBundle,
    EventPage,
    NormalizedPosition,
    ScopeValidation,
)


class ConnectionError(RuntimeError):
    """Base error for local connector failures."""


class TransientConnectionError(ConnectionError):
    """A bounded retry may be useful; the caller must never retry forever."""


class PermissionConnectionError(ConnectionError):
    """The provider did not grant the required read scope."""


@runtime_checkable
class ReadOnlyConnection(Protocol):
    """Adapter surface; mutating exchange/broker methods are deliberately absent."""

    def metadata(self) -> ConnectionManifest: ...

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation: ...

    def list_accounts(
        self, credentials: CredentialBundle | None = None
    ) -> tuple[ConnectionAccount, ...]: ...

    def read_events(
        self,
        cursor: ConnectionCursor | None = None,
        credentials: CredentialBundle | None = None,
    ) -> EventPage: ...

    def read_positions(
        self, credentials: CredentialBundle | None = None
    ) -> tuple[NormalizedPosition, ...]: ...

    def disconnect(self) -> None: ...

