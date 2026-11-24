"""Official, version-pinned plugin market metadata and install state.

The market is unified with PluginStateStore (state/plugins/plugin_state.db) as the
single source of truth for installation state. MarketplaceStore delegates installed
status queries to PluginStateStore and aligns legacy marketplace.json records.
"""

from __future__ import annotations

import copy
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.plugins.catalog import (
    CATEGORY_ORDER,
    catalog_entries,
    catalog_index,
)
from smartmoney_cub_harness.plugins.catalog_contract import (
    CATALOG_SCHEMA,
    LEVEL_COMPANION,
    STATE_AVAILABLE,
    STATE_DISABLED,
    STATE_ENABLED,
    STATE_ERROR,
    STATE_INSTALLED,
)
from smartmoney_cub_harness.plugins.lifecycle import PluginInstance, PluginState
from smartmoney_cub_harness.plugins.manifest import PLUGIN_MANIFEST_SCHEMA, validate_manifest
from smartmoney_cub_harness.plugins.registry import PluginStateStore
from smartmoney_cub_harness.plugins.types import (
    DataTimeSemantics,
    PluginKind,
    SUPPORTED_API_RANGE,
    TrustLevel,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _runtime_integrated(
    entry: dict[str, Any], record: dict[str, Any] | None = None, health: dict[str, Any] | None = None
) -> bool:
    """Return whether this catalog item has a harness runtime adapter.

    A companion can be installed as documentation or a source checkout, but it
    never becomes callable merely because its files exist on disk.
    """
    if entry.get("level") == LEVEL_COMPANION:
        return False
    if health is not None and "runtime_integrated" in health:
        return health["runtime_integrated"] is True
    manifest = (record or {}).get("manifest")
    if isinstance(manifest, dict) and "runtime_integrated" in manifest:
        return manifest["runtime_integrated"] is True
    return True


def _project_record(entry: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Project persisted lifecycle state into honest market-facing flags."""
    rec_state = record.get("state")
    runtime_integrated = _runtime_integrated(entry, record)
    is_enabled = bool(record.get("enabled"))

    if rec_state in (PluginState.REVOKED, PluginState.DEPRECATED):
        derived_state = STATE_AVAILABLE
    elif rec_state in (PluginState.FAILED, "FAILED", "ERROR"):
        derived_state = STATE_ERROR
    elif rec_state in (PluginState.ACTIVE, PluginState.ENABLED, PluginState.SERVING, "ACTIVE", "ENABLED", "SERVING"):
        derived_state = STATE_ENABLED if is_enabled and runtime_integrated else STATE_INSTALLED
    elif rec_state in (PluginState.INSTALLED, "INSTALLED"):
        derived_state = STATE_INSTALLED
    elif rec_state in (PluginState.DISABLED, "DISABLED"):
        derived_state = STATE_DISABLED
    else:
        derived_state = STATE_INSTALLED if runtime_integrated and is_enabled else STATE_DISABLED

    installed = derived_state != STATE_AVAILABLE
    active = bool(installed and runtime_integrated and is_enabled and derived_state == STATE_ENABLED)
    enabled = bool(installed and runtime_integrated and is_enabled)
    callable_ = active
    if not installed:
        callable_reason = "not_installed"
    elif not runtime_integrated:
        callable_reason = (
            "companion_only_no_runtime_adapter"
            if entry.get("level") == LEVEL_COMPANION
            else "no_runtime_adapter"
        )
    elif not active:
        callable_reason = "disabled_or_inactive"
    else:
        callable_reason = None

    result = {
        **record,
        "state": derived_state,
        "installed": installed,
        "active": active,
        "callable": callable_,
        "runtime_integrated": runtime_integrated,
        "enabled": enabled,
        "mounted": active,
        "callable_reason": callable_reason,
        "health": "error" if derived_state == STATE_ERROR else ("healthy" if installed else "pending"),
        "last_error": record.get("last_error"),
        "updated_at": record.get("updated_at") or _now(),
    }
    return result


class MarketplaceStore:
    """Marketplace store integrating curated catalog with PluginStateStore."""

    def __init__(self, root: str | Path, state_store: PluginStateStore | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "marketplace.json"
        self._explicit_state_store = state_store
        self._lock = threading.RLock()

    def _get_state_store(self) -> PluginStateStore:
        if self._explicit_state_store is not None:
            return self._explicit_state_store
        db_candidates = [
            self.root / "plugins" / "plugin_state.db",
            self.root.parent / "plugins" / "plugin_state.db",
            Path("state/plugins/plugin_state.db"),
        ]
        for c in db_candidates:
            if c.is_file():
                return PluginStateStore(c)
        default_db = Path("state/plugins/plugin_state.db")
        return PluginStateStore(default_db)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": "smartmoney_cub_marketplace.v1", "installed": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"schema": "smartmoney_cub_marketplace.v1", "installed": {}}

    def _save(self, value: dict[str, Any]) -> None:
        value["safety"] = SAFETY_DECLARATION
        self.path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _clean_legacy_state(self, valid_plugin_ids: set[str]) -> dict[str, Any]:
        """Align marketplace.json so legacy fake states don't conflict with PluginStateStore."""
        state = self._load()
        installed = state.get("installed", {})
        dirty = False
        to_del = []
        for pid, data in list(installed.items()):
            if pid not in valid_plugin_ids:
                to_del.append(pid)
                dirty = True
        for pid in to_del:
            installed.pop(pid, None)
        if dirty:
            state["installed"] = installed
            self._save(state)
        return installed

    def view(self) -> dict[str, Any]:
        """Generate market view unified with PluginStateStore as source of truth."""
        with self._lock:
            state_store = self._get_state_store()
            installed_records = {r["plugin_id"]: r for r in state_store.list_all()}
            self._clean_legacy_state(set(installed_records.keys()))

            raw_entries = catalog_entries()
            catalog = []
            installed_list = []

            for entry in raw_entries:
                pid = entry["plugin_id"]
                item = copy.deepcopy(entry)
                rec = installed_records.get(pid)

                if rec is not None:
                    projection = _project_record(entry, rec)
                    item.update(projection)
                    if projection["installed"]:
                        installed_list.append(copy.deepcopy(item))
                else:
                    runtime_integrated = _runtime_integrated(item)
                    item.update({
                        "state": STATE_AVAILABLE,
                        "installed": False,
                        "active": False,
                        "callable": False,
                        "runtime_integrated": runtime_integrated,
                        "enabled": False,
                        "mounted": False,
                        "callable_reason": "not_installed",
                        "health": "pending",
                        "last_error": None,
                        "updated_at": None,
                    })

                catalog.append(item)

            by_cat: dict[str, int] = {}
            for item in catalog:
                cat = str(item.get("category"))
                by_cat[cat] = by_cat.get(cat, 0) + 1

            return {
                "schema": CATALOG_SCHEMA,
                "source": "official-curated",
                "categories": list(CATEGORY_ORDER),
                "catalog": catalog,
                "installed": installed_list,
                "counts": {
                    "total": len(catalog),
                    "installed": len(installed_list),
                    "active": sum(1 for item in catalog if item.get("active")),
                    "callable": sum(1 for item in catalog if item.get("callable")),
                    "by_category": by_cat,
                },
                "policy": (
                    "目录只描述上游来源与安装方式。安装由用户在工作台逐项确认后触发，"
                    "非静默、非后台；高风险项目（自带下单能力）永不安装。"
                ),
                "safety": SAFETY_DECLARATION,
            }

    def install_record(
        self,
        entry: dict[str, Any],
        *,
        health: dict[str, Any],
        config_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        """Record verified install directly into PluginStateStore."""
        with self._lock:
            plugin_id = str(entry["plugin_id"])
            name = str(entry.get("name") or plugin_id)
            version = "1.0.0"
            capabilities = list(entry.get("capabilities") or ["market_context"])
            runtime_integrated = _runtime_integrated(entry, health=health)
            active = bool(health.get("healthy") and runtime_integrated)
            healthy = health.get("healthy") is True
            initial_state = PluginState.ACTIVE if active else (PluginState.INSTALLED if healthy else PluginState.FAILED)

            manifest = {
                "schema": PLUGIN_MANIFEST_SCHEMA,
                "plugin_id": plugin_id,
                "name": name,
                "version": version,
                "source_repo": str(entry.get("repo") or "https://github.com/smartmoney-cub"),
                "license": str(entry.get("license") or "MIT"),
                "kind": PluginKind.COMPANION,
                "trust_level": TrustLevel.REVIEW_ONLY,
                "api_range": SUPPORTED_API_RANGE,
                "capabilities": capabilities,
                "data_time_semantics": DataTimeSemantics.HISTORICAL_EXPORT,
                "runtime_integrated": runtime_integrated,
                "catalog_level": entry.get("level"),
                "safety": SAFETY_DECLARATION,
            }

            validation = validate_manifest(manifest)
            if not validation["ok"]:
                raise ValueError(f"constructed manifest is invalid: {validation['errors']}")

            instance = PluginInstance(
                plugin_id=plugin_id,
                version=version,
                state=initial_state,
                manifest=manifest,
                capabilities=capabilities,
            )

            store = self._get_state_store()
            store.record(instance, from_state=STATE_AVAILABLE, detail="installed_via_marketplace")

            # Update marketplace.json cache
            st = self._load()
            rec = {
                "plugin_id": plugin_id,
                "state": STATE_ENABLED if active else (STATE_INSTALLED if healthy else STATE_ERROR),
                "installed": True,
                "active": active,
                "callable": active,
                "runtime_integrated": runtime_integrated,
                "enabled": active,
                "mounted": active,
                "callable_reason": None if active else (
                    "companion_only_no_runtime_adapter"
                    if entry.get("level") == LEVEL_COMPANION
                    else "no_runtime_adapter"
                ),
                "health": "healthy" if healthy else "error",
                "config_keys": config_keys or [],
                "updated_at": _now(),
                "safety": SAFETY_DECLARATION,
            }
            st.setdefault("installed", {})[plugin_id] = rec
            self._save(st)
            return rec

    def revoke_record(self, plugin_id: str) -> None:
        """Revoke plugin from PluginStateStore and clear marketplace.json cache."""
        with self._lock:
            store = self._get_state_store()
            existing = store.get(plugin_id)
            if existing:
                instance = PluginInstance(
                    plugin_id=plugin_id,
                    version=str(existing.get("version") or "1.0.0"),
                    state=PluginState.REVOKED,
                    manifest=existing.get("manifest"),
                    capabilities=list(existing.get("capabilities") or []),
                )
                store.record(instance, from_state=existing.get("state"), detail="revoked_via_marketplace")

            st = self._load()
            if "installed" in st and plugin_id in st["installed"]:
                st["installed"].pop(plugin_id, None)
                self._save(st)

    def install(self, plugin_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Record an install that has already passed its health check.

        There is deliberately no "configuration required" branch. The wizard
        holds its own state on the client, so an interrupted or unconfirmed
        install leaves nothing here; a half-configured entry can never be read
        back because it is never written. Permission confirmation is therefore a
        precondition of this call, not a state it can return.
        """
        whitelist = catalog_index()
        entry = whitelist.get(plugin_id)
        if entry is None:
            raise KeyError(plugin_id)
        if not config or not config.get("permissions_confirmed"):
            return {
                "status": "permissions_required",
                "plugin_id": plugin_id,
                "error": "installation requires explicit read-only permission confirmation",
                "safety": SAFETY_DECLARATION,
            }
        rec = self.install_record(entry, health={"healthy": True}, config_keys=sorted(config.keys()))
        return {"status": "ok", "plugin": rec, "mounted": rec["mounted"], "safety": SAFETY_DECLARATION}
    def update(self, plugin_id: str, *, confirm: bool = False) -> dict[str, Any]:
        with self._lock:
            store = self._get_state_store()
            rec = store.get(plugin_id)
            if rec is None:
                raise KeyError(plugin_id)
            if not confirm:
                return {"status": "confirmation_required", "plugin": rec, "available_version": "1.0.0", "safety": SAFETY_DECLARATION}
            return {"status": "ok", "plugin": rec, "rollback_available": True, "safety": SAFETY_DECLARATION}

    def set_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            store = self._get_state_store()
            rec = store.get(plugin_id)
            if rec is None:
                raise KeyError(plugin_id)
            entry = catalog_index().get(plugin_id, {})
            if enabled and not _runtime_integrated(entry, rec):
                return {
                    "status": "not_callable",
                    "plugin": _project_record(entry, rec),
                    "error": "companion has no runtime adapter",
                    "safety": SAFETY_DECLARATION,
                }
            new_state = PluginState.ACTIVE if enabled else PluginState.DISABLED
            instance = PluginInstance(
                plugin_id=plugin_id,
                version=str(rec.get("version") or "1.0.0"),
                state=new_state,
                manifest=rec.get("manifest"),
                capabilities=list(rec.get("capabilities") or []),
            )
            store.record(instance, from_state=rec.get("state"), detail=f"set_enabled:{enabled}")
            updated_rec = store.get(plugin_id) or {}
            plugin_info = _project_record(entry, updated_rec)
            return {"status": "ok", "plugin": plugin_info, "safety": SAFETY_DECLARATION}
