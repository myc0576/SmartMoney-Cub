from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.plugins.catalog import catalog_index, catalog_payload
from smartmoney_cub_harness.plugins.curated_catalog import curated_catalog_payload
from smartmoney_cub_harness.plugins.lifecycle import PluginState
from smartmoney_cub_harness.plugins.manifest import parse_manifest, validate_manifest
from smartmoney_cub_harness.plugins.profiles import BUILTIN_PROFILES, get_profile
from smartmoney_cub_harness.plugins.registry import PluginStateStore
from smartmoney_cub_harness.plugins.runtime import PluginRuntime
from smartmoney_cub_harness.safety import redact
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

DEFAULT_STATE_DB = "state/plugins/plugin_state.db"


def _read_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("plugin manifest must be a JSON object")
    return payload


def _runtime(profile_name: str, state_db: str | None) -> PluginRuntime:
    profile = get_profile(profile_name)
    store = PluginStateStore(state_db or DEFAULT_STATE_DB)
    runtime = PluginRuntime(profile=profile, state_store=store)
    # Restore previously installed plugins so commands such as disable, logs, and
    # remove work without re-supplying --plugin-dir.
    runtime.hydrate()
    return runtime


def plugin_list(
    *, profile_name: str = "default-offline", plugin_dirs: list[str] | None = None, state_db: str | None = None
) -> dict[str, Any]:
    runtime = _runtime(profile_name, state_db)
    discovery = runtime.discover(plugin_dirs or [])
    return {
        "status": "ok",
        "profile": runtime.profile.name,
        "plugins": runtime.registry.list_all(),
        "rejected": discovery["rejected"],
        "installed_entry_points": discovery["entry_points"],
        "safety": SAFETY_DECLARATION,
    }


def plugin_inspect(manifest_path: str) -> dict[str, Any]:
    payload = _read_json(manifest_path)
    validation = validate_manifest(payload)
    result: dict[str, Any] = {
        "status": "ok" if validation["ok"] else "invalid",
        "manifest_path": str(redact(str(manifest_path))),
        "validation": validation,
        "safety": SAFETY_DECLARATION,
    }
    if validation["ok"]:
        manifest = parse_manifest(payload)
        result["manifest"] = manifest.to_dict()
        result["network_required"] = manifest.network_required
        result["requires_credentials"] = manifest.requires_credentials
    return result


def plugin_enable(
    plugin_id: str,
    *,
    profile_name: str = "default-offline",
    plugin_dirs: list[str] | None = None,
    state_db: str | None = None,
) -> dict[str, Any]:
    runtime = _runtime(profile_name, state_db)
    runtime.discover(plugin_dirs or [])
    if runtime.registry.get(plugin_id) is None:
        return {
            "status": "not_found",
            "plugin_id": plugin_id,
            "safety": SAFETY_DECLARATION,
        }
    instance = runtime.activate(plugin_id, enabled=True)
    return {
        "status": "ok",
        "plugin": instance.status(),
        "safety": SAFETY_DECLARATION,
    }


def plugin_disable(
    plugin_id: str, *, state_db: str | None = None, profile_name: str = "default-offline"
) -> dict[str, Any]:
    runtime = _runtime(profile_name, state_db)
    if runtime.registry.get(plugin_id) is None:
        return {"status": "not_found", "plugin_id": plugin_id, "safety": SAFETY_DECLARATION}
    instance = runtime.deactivate(plugin_id)
    return {"status": "ok", "plugin": instance.status(), "safety": SAFETY_DECLARATION}


def plugin_remove(plugin_id: str, *, state_db: str | None = None) -> dict[str, Any]:
    store = PluginStateStore(state_db or DEFAULT_STATE_DB)
    record = store.get(plugin_id)
    if record is None:
        return {"status": "not_found", "plugin_id": plugin_id, "safety": SAFETY_DECLARATION}
    # Removal revokes the entry and keeps the audit trail intact.
    from smartmoney_cub_harness.plugins.lifecycle import PluginInstance, PluginState

    instance = PluginInstance(
        plugin_id=plugin_id,
        version=str(record.get("version") or "unknown"),
        manifest=record,
        capabilities=list(record.get("capabilities") or []),
        state=PluginState.REVOKED,
    )
    store.record(instance, from_state=record.get("state"), detail="remove:revoked")
    return {
        "status": "ok",
        "plugin_id": plugin_id,
        "state": PluginState.REVOKED,
        "note": "plugin entry revoked; audit trail retained",
        "safety": SAFETY_DECLARATION,
    }


def plugin_install(
    source: str,
    *,
    profile_name: str = "default-offline",
    state_db: str | None = None,
    permissions_confirmed: bool = True,
    credentials: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register or install a plugin.

    If source matches a plugin_id in the curated catalog, route to PluginInstaller.
    Otherwise, maintain existing local directory discovery and registration behavior.
    """
    clean_source = source.strip()
    whitelist = catalog_index()

    if clean_source in whitelist:
        from smartmoney_cub_harness.plugin_installer import PluginInstaller
        from smartmoney_cub_harness.plugin_marketplace import MarketplaceStore

        entry = whitelist[clean_source]
        db_path = Path(state_db or DEFAULT_STATE_DB)
        state_store = PluginStateStore(db_path)
        # Derive root for installer and credentials from state_db parent
        installer_root = db_path.parent.parent if db_path.parent.name == "plugins" else db_path.parent
        installer = PluginInstaller(installer_root)
        install_res = installer.install(
            entry,
            permissions_confirmed=permissions_confirmed,
            credentials=credentials,
            config=config,
        )
        if install_res.get("status") == "ok":
            market_store = MarketplaceStore(installer_root, state_store=state_store)
            rec = market_store.install_record(
                entry,
                health=install_res.get("health", {"healthy": True}),
                config_keys=list(config.keys()) if config else [],
            )
            return {
                "status": "ok",
                "installed": [rec],
                "steps": install_res.get("steps", []),
                "health": install_res.get("health", {}),
                "downloaded": entry.get("install", {}).get("kind") != "builtin",
                "safety": SAFETY_DECLARATION,
            }
        return {
            "status": "error",
            "steps": install_res.get("steps", []),
            "error": install_res.get("error", "install_failed"),
            "safety": SAFETY_DECLARATION,
        }

    path = Path(clean_source).expanduser()
    if not path.exists():
        return {
            "status": "not_found",
            "error": {"code": "path_missing", "message": f"no such path or catalog plugin: {source}"},
            "safety": SAFETY_DECLARATION,
        }

    runtime = _runtime(profile_name, state_db)
    discovery = runtime.discover([str(path)])
    installed = [item for item in discovery["discovered"]]
    if not installed:
        return {
            "status": "rejected",
            "rejected": discovery["rejected"],
            "safety": SAFETY_DECLARATION,
        }

    activations = [
        runtime.activate(item["plugin_id"], enabled=False).status() for item in installed
    ]
    return {
        "status": "ok",
        "installed": activations,
        "rejected": discovery["rejected"],
        "note": "registered as INSTALLED and left disabled; run 'smcub plugin enable <id>' to activate",
        "downloaded": False,
        "safety": SAFETY_DECLARATION,
    }


def plugin_doctor(
    *, profile_name: str = "default-offline", plugin_dirs: list[str] | None = None, state_db: str | None = None
) -> dict[str, Any]:
    runtime = _runtime(profile_name, state_db)
    runtime.discover(plugin_dirs or [])
    # Doctor reports the tree; it must not silently re-enable plugins a user disabled.
    for instance in list(runtime.registry.instances.values()):
        if instance.state in {PluginState.DISABLED, PluginState.REVOKED, PluginState.DEPRECATED}:
            continue
        runtime.activate(instance.plugin_id, enabled=True)
    return runtime.doctor()


def plugin_logs(plugin_id: str, *, state_db: str | None = None, limit: int = 50) -> dict[str, Any]:
    store = PluginStateStore(state_db or DEFAULT_STATE_DB)
    return {
        "status": "ok",
        "plugin_id": plugin_id,
        "state": store.get(plugin_id),
        "events": store.events(plugin_id, limit=limit),
        "safety": SAFETY_DECLARATION,
    }


def profile_show(profile_name: str) -> dict[str, Any]:
    profile = get_profile(profile_name)
    return {"status": "ok", **profile.to_dict()}


def plugin_catalog() -> dict[str, Any]:
    """Show curated external projects and the boundary each one must respect."""
    payload = catalog_payload()
    payload["curated_finance"] = curated_catalog_payload()
    payload["safety"] = SAFETY_DECLARATION
    return payload


def profile_dump(*, output_path: str | None = None) -> dict[str, Any]:
    payload = {
        "status": "ok",
        "profiles": {name: profile.to_dict() for name, profile in BUILTIN_PROFILES.items()},
        "safety": SAFETY_DECLARATION,
    }
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(redact(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        payload["output"] = str(path)
    return payload


def profile_reload(
    *, profile_name: str = "default-offline", plugin_dirs: list[str] | None = None, state_db: str | None = None
) -> dict[str, Any]:
    """Explicitly rebuild the plugin tree. HMR is intentionally not enabled in v1."""
    runtime = _runtime(profile_name, state_db)
    discovery = runtime.discover(plugin_dirs or [])
    activation = []
    # Reload re-resolves the tree but leaves explicitly disabled plugins disabled.
    for instance in list(runtime.registry.instances.values()):
        if instance.state in {PluginState.DISABLED, PluginState.REVOKED, PluginState.DEPRECATED}:
            activation.append(instance.status())
            continue
        activation.append(runtime.activate(instance.plugin_id, enabled=True).status())
    return {
        "status": "ok",
        "profile": runtime.profile.name,
        "reloaded": True,
        "discovered": discovery["discovered"],
        "activation": activation,
        "hot_reload": False,
        "safety": SAFETY_DECLARATION,
    }


def plugin_run(
    plugin_id: str,
    *,
    capability: str | None = None,
    request_path: str | None = None,
    workspace_db: str | None = None,
    case_id: str | None = None,
    decision_time: str | None = None,
    available_at: str | None = None,
    data_source: str = "",
    data_quality: str = "ok",
    result_kind: str = "review_observation",
    profile_name: str = "default-offline",
    plugin_dirs: list[str] | None = None,
    state_db: str | None = None,
) -> dict[str, Any]:
    """Execute one plugin capability and return a wrapped evidence envelope.

    Time fields are required: an output without an explicit available_at cannot be
    trusted as known at decision time, so the run is refused instead of guessed.
    """
    if not available_at:
        return {
            "status": "error",
            "error": {"code": "available_at_required", "message": "provide --available-at as an ISO timestamp"},
            "safety": SAFETY_DECLARATION,
        }
    if not decision_time:
        return {
            "status": "error",
            "error": {
                "code": "decision_time_required",
                "message": "provide --decision-time so provenance can be checked for future leakage",
            },
            "safety": SAFETY_DECLARATION,
        }

    runtime = _runtime(profile_name, state_db)
    runtime.discover(plugin_dirs or [])
    instance = runtime.registry.get(plugin_id)
    if instance is None:
        return {"status": "not_found", "plugin_id": plugin_id, "safety": SAFETY_DECLARATION}

    # A disabled or revoked plugin must be explicitly re-enabled first; running it
    # must never silently flip its lifecycle back on.
    if instance.state in {PluginState.DISABLED, PluginState.REVOKED, PluginState.DEPRECATED}:
        return {
            "status": "not_enabled",
            "error": {
                "code": "plugin_not_enabled",
                "message": f"plugin {plugin_id} is {instance.state}; run 'smcub plugin enable {plugin_id}' first",
            },
            "plugin": instance.status(),
            "safety": SAFETY_DECLARATION,
        }

    target_capability = capability or (instance.capabilities[0] if instance.capabilities else "")
    if not target_capability:
        return {
            "status": "error",
            "error": {"code": "no_capability", "message": "plugin declares no capability to run"},
            "safety": SAFETY_DECLARATION,
        }

    activation = runtime.activate(plugin_id, enabled=True)
    if not activation.is_serving:
        return {
            "status": "blocked",
            "plugin": activation.status(),
            "safety": SAFETY_DECLARATION,
        }

    request: dict[str, Any] = {}
    if request_path:
        request = _read_json(request_path)

    try:
        envelope = runtime.execute(
            plugin_id=plugin_id,
            capability=target_capability,
            request=request,
            decision_time=decision_time,
            available_at=available_at,
            data_source=data_source,
            data_quality=data_quality,
            result_kind=result_kind,
        )
    except Exception as exc:
        return {
            "status": "error",
            "error": {"code": type(exc).__name__, "message": str(exc)},
            "safety": SAFETY_DECLARATION,
        }

    recorded: dict[str, Any] | None = None
    if workspace_db and envelope.get("error") is None:
        from smartmoney_cub_harness.workspace import Workspace

        try:
            workspace = Workspace(workspace_db)
            try:
                recorded = workspace.record_evidence(envelope, case_id=case_id)
            finally:
                workspace.close()
        except ValueError as exc:
            recorded = {
                "status": "error",
                "error": {"code": "evidence_not_recorded", "message": str(exc)},
                "safety": SAFETY_DECLARATION,
            }

    return {
        "status": "ok" if envelope.get("error") is None else "failed",
        "envelope": envelope,
        "recorded_evidence": recorded,
        "evidence_path": None,
        "safety": SAFETY_DECLARATION,
    }


def plugin_detail(
    plugin_id: str,
    *,
    profile_name: str = "default-offline",
    plugin_dirs: list[str] | None = None,
    state_db: str | None = None,
) -> dict[str, Any]:
    runtime = _runtime(profile_name, state_db)
    runtime.discover(plugin_dirs or [])
    instance = runtime.registry.get(plugin_id)
    store = PluginStateStore(state_db or DEFAULT_STATE_DB)
    record = store.get(plugin_id)
    config = store.get_config(plugin_id)
    events = store.events(plugin_id, limit=20)

    if instance is None and record is None:
        return {"status": "not_found", "plugin_id": plugin_id, "safety": SAFETY_DECLARATION}

    status_dict = instance.status() if instance is not None else record
    return {
        "status": "ok",
        "plugin_id": plugin_id,
        "plugin": status_dict,
        "manifest": (instance.manifest if instance else (record.get("manifest") if record else None)) or {},
        "config": config,
        "events": events,
        "safety": SAFETY_DECLARATION,
    }


def plugin_configure(
    plugin_id: str,
    config: dict[str, Any],
    *,
    state_db: str | None = None,
) -> dict[str, Any]:
    store = PluginStateStore(state_db or DEFAULT_STATE_DB)
    store.set_config(plugin_id, config)
    return {
        "status": "ok",
        "plugin_id": plugin_id,
        "config": config,
        "safety": SAFETY_DECLARATION,
    }
