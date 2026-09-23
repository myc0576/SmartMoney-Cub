"""Local connection lifecycle manager.

The manager is deliberately provider-agnostic. It owns the local credential
references and durable sync state, while each adapter owns only its read calls.
The public status is always redacted; credentials never cross the DTO boundary.
"""

from __future__ import annotations

import json
import os
import threading
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from smartmoney_cub_harness.safety import REDACTED
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

from .models import ConnectionCursor, CredentialBundle, SyncResult, event_from_dict
from .protocol import ReadOnlyConnection
from .sync import SyncEngine, SyncState, event_key


@dataclass
class _ManagedConnection:
    connection: ReadOnlyConnection
    credentials: CredentialBundle | None = None
    state: SyncState = field(default_factory=SyncState)
    revoked: bool = False
    scope: Any = None


class ConnectionManager:
    """Register read-only adapters and keep their local sync lifecycle."""

    def __init__(
        self,
        *,
        state_path: str | Path | None = None,
        credentials_path: str | Path | None = None,
    ) -> None:
        self.state_path = Path(state_path) if state_path is not None else None
        self.credentials_path = (
            Path(credentials_path)
            if credentials_path is not None
            else (self.state_path.with_name("connection_credentials.json") if self.state_path else None)
        )
        self._lock = threading.RLock()
        self._connections: dict[str, _ManagedConnection] = {}
        self._load_state()
        self._load_credentials()

    def register(self, connection: ReadOnlyConnection) -> None:
        provider_id = connection.metadata().provider_id
        managed = self._connections.get(provider_id)
        if managed is None:
            managed = _ManagedConnection(connection)
            saved = getattr(self, "_saved_state", {}).get("connections", {}).get(provider_id, {})
            try:
                managed.state.cursor = ConnectionCursor.decode(saved.get("cursor"))
                managed.state.events = {
                    event_key(event_from_dict(item)): event_from_dict(item)
                    for item in saved.get("events", ())
                    if isinstance(item, Mapping) and item.get("external_id")
                }
            except (AttributeError, TypeError, ValueError):
                managed.state.cursor = None
            managed.revoked = bool(saved.get("revoked", False)) if isinstance(saved, Mapping) else False
            managed.scope = saved.get("scope") if isinstance(saved, Mapping) else None
            restored = self.credentials(provider_id)
            managed.credentials = restored
            binder = getattr(connection, "bind_credentials", None)
            if restored is not None and callable(binder):
                binder(restored)
            self._connections[provider_id] = managed
        else:
            managed.connection = connection
            managed.revoked = False

    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._connections))

    def set_credentials(self, provider_id: str, credentials: CredentialBundle) -> None:
        managed = self._require(provider_id)
        if credentials.provider_id != provider_id:
            raise ValueError("credential provider does not match connection")
        managed.credentials = credentials
        managed.revoked = False
        managed.scope = None
        binder = getattr(managed.connection, "bind_credentials", None)
        if callable(binder):
            binder(credentials)
        self._saved_credentials[provider_id] = credentials
        self._save_credentials()
        self._save_state()

    def clear_credentials(self, provider_id: str) -> None:
        managed = self._require(provider_id)
        managed.credentials = None
        self._saved_credentials.pop(provider_id, None)
        self._save_credentials()
        self._save_state()

    def credentials(self, provider_id: str) -> CredentialBundle | None:
        """Return a local-only bundle for rebuilding an adapter after restart."""
        managed = self._connections.get(provider_id)
        if managed is not None and managed.credentials is not None:
            return managed.credentials
        return self._saved_credentials.get(provider_id)

    def restore_credentials(self, provider_id: str) -> CredentialBundle | None:
        return self.credentials(provider_id)

    def records(self, provider_id: str) -> tuple[Any, ...]:
        """Return the normalized dedupe set in stable external-id order."""
        managed = self._require(provider_id)
        return tuple(managed.state.events[key] for key in sorted(managed.state.events))

    def validate_read_access(self, provider_id: str):
        managed = self._require(provider_id)
        if managed.revoked:
            return managed.connection.validate_read_access(None)
        return managed.connection.validate_read_access(managed.credentials)

    def sync(
        self,
        provider_id: str,
        *,
        cursor: ConnectionCursor | str | Mapping[str, Any] | None = None,
        max_attempts: int = 3,
        max_pages: int = 10000,
    ) -> SyncResult:
        managed = self._require(provider_id)
        if managed.revoked:
            return SyncResult(provider_id=provider_id, cursor=None, blocked=True, errors=("connection_revoked",))
        result = SyncEngine(
            managed.connection,
            credentials=managed.credentials,
            state=managed.state,
            max_attempts=max_attempts,
            max_pages=max_pages,
        ).sync(cursor)
        managed.scope = result.scope
        self._save_credentials()  # adapters may rotate short-lived OAuth tokens
        self._save_state()
        return result

    def disconnect(self, provider_id: str) -> SyncResult:
        managed = self._connections.get(provider_id)
        errors = []
        if managed is not None:
            try:
                managed.connection.disconnect()
                if getattr(managed.connection, "remote_revocation_pending", False):
                    errors.append("remote_revocation_pending_use_provider_settings")
            except Exception:
                errors.append("remote_revocation_pending_use_provider_settings")
            managed.credentials = None
            managed.state = SyncState()
            managed.revoked = True
        elif provider_id not in self._saved_credentials:
            raise KeyError("connection_not_configured")
        self._saved_credentials.pop(provider_id, None)
        self._save_credentials()
        self._saved_state = getattr(self, "_saved_state", {})
        self._saved_state.setdefault("connections", {}).pop(provider_id, None)
        self._save_state()
        return SyncResult(provider_id=provider_id, cursor=None, disconnected=True, errors=tuple(errors))

    def revoke(self, provider_id: str) -> SyncResult:
        return self.disconnect(provider_id)

    def status(self, provider_id: str) -> dict[str, Any]:
        managed = self._require(provider_id)
        required = list(managed.connection.metadata().required_scopes)
        if managed.scope is not None:
            scope = managed.scope.to_dict() if hasattr(managed.scope, "to_dict") else dict(managed.scope)
        elif managed.credentials is not None and not managed.revoked:
            scope = {
                "allowed": False,
                "status": "unverified",
                "required": required,
                "granted": [],
                "missing": required,
                "issues": ["scope_validation_required"],
                "safety": SAFETY_DECLARATION,
            }
        else:
            scope = {
                "allowed": False,
                "status": "missing",
                "required": required,
                "granted": [],
                "missing": required,
                "issues": [],
                "safety": SAFETY_DECLARATION,
            }
        return {
            "provider_id": provider_id,
            "connected": managed.credentials is not None and not managed.revoked,
            "revoked": managed.revoked,
            "credential_fields": sorted(str(key) for key in (managed.credentials.values if managed.credentials else {})),
            "credential_values": REDACTED,
            "cursor": managed.state.cursor.to_dict() if managed.state.cursor else None,
            "event_count": len(managed.state.events),
            "scope": scope,
            "safety": SAFETY_DECLARATION,
        }

    def _require(self, provider_id: str) -> _ManagedConnection:
        try:
            return self._connections[str(provider_id)]
        except KeyError as exc:
            raise KeyError(f"connection is not registered: {provider_id}") from exc

    def _load_state(self) -> None:
        if self.state_path is None or not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        # Only non-secret cursor metadata is restorable before an adapter is
        # registered. Event bodies are intentionally not loaded without a
        # provider-specific schema; the manager can safely start from cursor.
        self._saved_state = payload if isinstance(payload, dict) else {}

    def _load_credentials(self) -> None:
        self._saved_credentials: dict[str, CredentialBundle] = {}
        if self.credentials_path is None or not self.credentials_path.exists():
            return
        try:
            payload = json.loads(self.credentials_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        providers = payload.get("providers", {}) if isinstance(payload, Mapping) else {}
        if not isinstance(providers, Mapping):
            return
        for provider_id, item in providers.items():
            if not isinstance(item, Mapping) or not isinstance(item.get("values"), Mapping):
                continue
            self._saved_credentials[str(provider_id)] = CredentialBundle(
                str(provider_id),
                dict(item["values"]),
                dict(item.get("permissions") or {}),
                item.get("expires_at"),
            )

    @staticmethod
    def _write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass
        descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)

    def _save_credentials(self) -> None:
        if self.credentials_path is None:
            return
        payload = {
            "schema": "smartmoney_cub_connection_credentials.v1",
            "providers": {
                provider_id: {
                    "values": dict(bundle.values),
                    "permissions": dict(bundle.permissions),
                    "expires_at": bundle.expires_at,
                }
                for provider_id, bundle in self._saved_credentials.items()
            },
            "safety": SAFETY_DECLARATION,
        }
        self._write_private_json(self.credentials_path, payload)

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        payload = {
            "schema": "smartmoney_cub_connection_manager.v1",
            "connections": {
                **getattr(self, "_saved_state", {}).get("connections", {}),
                **{
                provider_id: {
                    "cursor": managed.state.cursor.to_dict() if managed.state.cursor else None,
                    "events": [event.to_dict() for event in managed.state.events.values()],
                    "revoked": managed.revoked,
                    "scope": managed.scope.to_dict() if hasattr(managed.scope, "to_dict") else managed.scope,
                }
                for provider_id, managed in self._connections.items()
                },
            },
            "safety": SAFETY_DECLARATION,
        }
        self._write_private_json(self.state_path, payload)
        self._saved_state = payload
