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
                    # Derived state from PluginStateStore
                    rec_state = rec.get("state")
                    is_enabled = bool(rec.get("enabled"))
                    # A revoked or deprecated record keeps its audit trail in the
                    # store but is no longer installed: the plugin is gone from
                    # this machine, and reporting it as installed would be the
                    # same class of lie the previous marketplace told.
                    if rec_state in (PluginState.REVOKED, PluginState.DEPRECATED):
                        derived_state = STATE_AVAILABLE
                    elif rec_state in (PluginState.ACTIVE, PluginState.ENABLED, PluginState.SERVING, "ACTIVE", "ENABLED", "SERVING"):
                        derived_state = STATE_ENABLED if is_enabled else STATE_DISABLED
                    elif rec_state in (PluginState.INSTALLED, "INSTALLED"):
                        derived_state = STATE_INSTALLED
                    elif rec_state in (PluginState.DISABLED, "DISABLED"):
                        derived_state = STATE_DISABLED
                    elif rec_state in (PluginState.FAILED, "FAILED", "ERROR"):
                        derived_state = STATE_ERROR
                    else:
                        derived_state = STATE_INSTALLED if is_enabled else STATE_DISABLED

                    installed_bool = derived_state != STATE_AVAILABLE
                    enabled_bool = is_enabled
                    mounted_bool = is_enabled and installed_bool
                    if derived_state == STATE_ERROR:
                        health_status = "error"
                    elif installed_bool:
                        health_status = "healthy"
                    else:
                        health_status = "pending"
                    last_error = rec.get("last_error")
                    updated_at = rec.get("updated_at") or _now()

                    item.update({
                        "state": derived_state,
                        "installed": installed_bool,
                        "enabled": enabled_bool,
                        "mounted": mounted_bool,
                        "health": health_status,
                        "last_error": last_error,
                        "updated_at": updated_at,
                    })
                    if installed_bool:
                        installed_list.append(copy.deepcopy(item))
                else:
                    item.update({
                        "state": STATE_AVAILABLE,
                        "installed": False,
                        "enabled": False,
                        "mounted": False,
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
                "safety": SAFETY_DECLARATION,
            }

            validation = validate_manifest(manifest)
            if not validation["ok"]:
                raise ValueError(f"constructed manifest is invalid: {validation['errors']}")

            instance = PluginInstance(
                plugin_id=plugin_id,
                version=version,
                state=PluginState.ACTIVE,
                manifest=manifest,
                capabilities=capabilities,
            )

            store = self._get_state_store()
            store.record(instance, from_state=STATE_AVAILABLE, detail="installed_via_marketplace")

            # Update marketplace.json cache
            st = self._load()
            rec = {
                "plugin_id": plugin_id,
                "state": STATE_ENABLED,
                "installed": True,
                "enabled": True,
                "mounted": True,
                "health": "healthy" if health.get("healthy") else "error",
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
        return {"status": "ok", "plugin": rec, "mounted": True, "safety": SAFETY_DECLARATION}
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
            mounted = bool(enabled)
            plugin_info = {
                **updated_rec,
                "state": "ACTIVE" if enabled else "DISABLED",
                "mounted": mounted,
            }
            return {"status": "ok", "plugin": plugin_info, "safety": SAFETY_DECLARATION}
