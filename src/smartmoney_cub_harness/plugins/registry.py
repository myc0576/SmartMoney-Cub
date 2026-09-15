from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.plugins.lifecycle import PluginInstance, PluginState
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

PLUGIN_REGISTRY_SCHEMA = "smartmoney_cub_plugin_registry.v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class PluginStateStore:
    """SQLite-backed plugin state.

    Plugin identity, source provenance, and lifecycle state are persisted so an
    Evidence Pack can be tied back to the exact plugin build that produced it.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.db_path))
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS plugin_state (
                plugin_id TEXT PRIMARY KEY,
                name TEXT,
                version TEXT,
                state TEXT NOT NULL,
                kind TEXT,
                trust_level TEXT,
                source_repo TEXT,
                source_commit TEXT,
                source_tag TEXT,
                license TEXT,
                capabilities TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 0,
                installed_from TEXT,
                package_hash TEXT,
                manifest_json TEXT,
                last_error TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plugin_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def record(self, instance: PluginInstance, *, from_state: str | None = None, detail: str = "") -> None:
        manifest = instance.manifest or {}
        self._connection.execute(
            """
            INSERT INTO plugin_state (
                plugin_id, name, version, state, kind, trust_level, source_repo,
                source_commit, source_tag, license, capabilities, enabled,
                installed_from, package_hash, manifest_json, last_error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(plugin_id) DO UPDATE SET
                name = excluded.name,
                version = excluded.version,
                state = excluded.state,
                kind = excluded.kind,
                trust_level = excluded.trust_level,
                source_repo = excluded.source_repo,
                source_commit = excluded.source_commit,
                source_tag = excluded.source_tag,
                license = excluded.license,
                capabilities = excluded.capabilities,
                enabled = excluded.enabled,
                installed_from = excluded.installed_from,
                package_hash = excluded.package_hash,
                manifest_json = excluded.manifest_json,
                last_error = excluded.last_error,
                updated_at = excluded.updated_at
            """,
            (
                instance.plugin_id,
                manifest.get("name"),
                instance.version,
                instance.state,
                manifest.get("kind"),
                manifest.get("trust_level"),
                manifest.get("source_repo"),
                manifest.get("source_commit"),
                manifest.get("source_tag"),
                manifest.get("license"),
                json.dumps(instance.capabilities, ensure_ascii=False),
                int(instance.state not in (PluginState.DISABLED, PluginState.DISPOSED, PluginState.REVOKED)),
                manifest.get("installed_from"),
                manifest.get("package_hash"),
                json.dumps(manifest, ensure_ascii=False) if manifest else None,
                instance.last_error,
                _now_iso(),
            ),
        )
        self._connection.execute(
            "INSERT INTO plugin_event (plugin_id, from_state, to_state, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (instance.plugin_id, from_state, instance.state, detail, _now_iso()),
        )
        self._connection.commit()

    def get(self, plugin_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM plugin_state WHERE plugin_id = ?", (plugin_id,)
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["capabilities"] = json.loads(payload.get("capabilities") or "[]")
        payload["enabled"] = bool(payload.get("enabled"))
        # Expose the manifest as a nested object so callers never re-parse a string.
        raw_manifest = payload.pop("manifest_json", None)
        if raw_manifest:
            try:
                payload["manifest"] = json.loads(raw_manifest)
            except json.JSONDecodeError:
                payload["manifest"] = None
        else:
            payload["manifest"] = None
        payload["safety"] = SAFETY_DECLARATION
        return payload

    def list_all(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT plugin_id FROM plugin_state ORDER BY plugin_id"
        ).fetchall()
        return [record for record in (self.get(row["plugin_id"]) for row in rows) if record]

    def events(self, plugin_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM plugin_event WHERE plugin_id = ? ORDER BY id DESC LIMIT ?",
            (plugin_id, limit),
        ).fetchall()
        return [{**dict(row), "safety": SAFETY_DECLARATION} for row in rows]


@dataclass
class PluginRegistry:
    """In-memory view of every plugin the runtime discovered."""

    instances: dict[str, PluginInstance] = field(default_factory=dict)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def add(self, instance: PluginInstance) -> None:
        self.instances[instance.plugin_id] = instance

    def reject(self, *, plugin_id: str, reason: str, errors: list[str] | None = None) -> None:
        self.rejected.append(
            {
                "plugin_id": plugin_id,
                "reason": reason,
                "errors": errors or [],
                "safety": SAFETY_DECLARATION,
            }
        )

    def get(self, plugin_id: str) -> PluginInstance | None:
        return self.instances.get(plugin_id)

    def duplicate_ids(self) -> list[str]:
        return sorted(identifier for identifier, instance in self.instances.items() if not instance.plugin_id)

    def list_all(self) -> list[dict[str, Any]]:
        return [instance.status() for instance in sorted(self.instances.values(), key=lambda i: i.plugin_id)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLUGIN_REGISTRY_SCHEMA,
            "plugins": self.list_all(),
            "rejected": list(self.rejected),
            "safety": SAFETY_DECLARATION,
        }
