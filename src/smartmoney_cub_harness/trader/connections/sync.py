"""Deterministic read-only pagination, retries, and revision-aware sync."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from .models import (
    ConnectionAccount,
    ConnectionCursor,
    CredentialBundle,
    NormalizedEvent,
    NormalizedPosition,
    ScopeValidation,
    SyncResult,
)
from .protocol import ReadOnlyConnection, TransientConnectionError


def _revision(value: str | int) -> str:
    return str(value)


def event_key(event: NormalizedEvent) -> str:
    """Provider execution IDs are often unique only within an account."""
    return hashlib.sha256(json.dumps([event.source, event.account_id, event.metadata.get("instrument_id") or event.symbol, event.external_id]).encode()).hexdigest()


@dataclass
class SyncState:
    """Local state suitable for persisting by a caller between runs.

    The state contains normalized records and a durable cursor only. Credentials
    are intentionally not part of this object.
    """

    cursor: ConnectionCursor | None = None
    events: dict[str, NormalizedEvent] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cursor": self.cursor.to_dict() if self.cursor else None,
            "events": [event.to_dict() for event in self.events.values()],
        }


class SyncEngine:
    """Run a connector without ever exposing a mutating provider surface."""

    def __init__(
        self,
        connection: ReadOnlyConnection,
        *,
        credentials: CredentialBundle | None = None,
        state: SyncState | None = None,
        max_attempts: int = 3,
        max_pages: int = 10000,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        self.connection = connection
        self.credentials = credentials
        self.state = state or SyncState()
        self.max_attempts = max_attempts
        self.max_pages = max_pages
        self._disconnected = False

    @property
    def provider_id(self) -> str:
        return self.connection.metadata().provider_id

    def _scope(self) -> ScopeValidation:
        return self.connection.validate_read_access(self.credentials)

    def sync(self, cursor: ConnectionCursor | str | dict[str, Any] | None = None) -> SyncResult:
        supplied = ConnectionCursor.decode(cursor)
        if supplied is not None and supplied.provider_id != self.provider_id:
            raise ValueError("cursor provider does not match adapter")
        starting_cursor = supplied or self.state.cursor
        if starting_cursor is not None and starting_cursor.provider_id != self.provider_id:
            raise ValueError("stored cursor provider does not match adapter")

        scope = self._scope()
        if not scope.allowed:
            return SyncResult(
                provider_id=self.provider_id,
                cursor=starting_cursor,
                partial=False,
                blocked=True,
                errors=scope.issues or ("read_scope_not_verified",),
                scope=scope,
            )

        if self._disconnected:
            return SyncResult(provider_id=self.provider_id, cursor=starting_cursor, disconnected=True, scope=scope)

        cursor_now = starting_cursor
        committed_cursor = starting_cursor
        output: list[NormalizedEvent] = []
        duplicate_count = 0
        updated_count = 0
        errors: list[str] = []
        partial = False
        attempts_total = 0

        for _page_number in range(self.max_pages):
            page = None
            page_attempts = 0
            while page_attempts < self.max_attempts:
                page_attempts += 1
                attempts_total += 1
                try:
                    page = self.connection.read_events(cursor_now, self.credentials)
                    break
                except TransientConnectionError as exc:
                    if page_attempts >= self.max_attempts:
                        errors.append(f"retry_exhausted:{type(exc).__name__}")
                except Exception as exc:  # adapters must make a partial failure visible
                    errors.append(f"read_events_failed:{type(exc).__name__}")
                    partial = True
                    break
            if page is None:
                partial = True
                break

            if page.events:
                for event in page.events:
                    identity = event_key(event)
                    previous = self.state.events.get(identity)
                    if previous is None:
                        self.state.events[identity] = event
                        output.append(event)
                    elif _revision(previous.revision) == _revision(event.revision):
                        duplicate_count += 1
                    else:
                        self.state.events[identity] = event
                        output.append(event)
                        updated_count += 1

            if page.errors:
                errors.extend(str(error) for error in page.errors)
            partial = partial or page.partial
            next_cursor = page.next_cursor
            if not page.partial and not page.errors:
                # A cursor becomes durable only after the complete page has
                # been consumed. If a later page fails, resume at this point.
                committed_cursor = page.checkpoint_cursor or next_cursor or committed_cursor
            if next_cursor is None:
                cursor_now = None
                break
            cursor_now = next_cursor
        else:
            partial = True
            errors.append(f"max_pages_exceeded:{self.max_pages}")

        # Persist the last cursor only when the page stream completed. On a
        # partial page, keeping the prior cursor allows a safe resume/retry.
        if not partial:
            self.state.cursor = committed_cursor
        else:
            self.state.cursor = committed_cursor

        accounts: tuple[ConnectionAccount, ...] = ()
        positions: tuple[NormalizedPosition, ...] = ()
        try:
            accounts = tuple(self.connection.list_accounts(self.credentials))
            positions = tuple(self.connection.read_positions(self.credentials))
        except Exception as exc:
            partial = True
            errors.append(f"account_or_position_read_failed:{type(exc).__name__}")

        return SyncResult(
            provider_id=self.provider_id,
            cursor=self.state.cursor,
            accounts=accounts,
            events=tuple(output),
            positions=positions,
            duplicate_count=duplicate_count,
            updated_count=updated_count,
            partial=partial,
            errors=tuple(errors),
            attempts=attempts_total,
            scope=scope,
        )

    def disconnect(self) -> SyncResult:
        self.connection.disconnect()
        self._disconnected = True
        self.credentials = None
        self.state.cursor = None
        return SyncResult(provider_id=self.provider_id, cursor=None, disconnected=True)
