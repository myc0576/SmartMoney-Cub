"""Metadata and configuration helpers for the control setup surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from smartmoney_cub_harness.agent.providers import (
    PROVIDER_CATALOG,
    install_provider,
    load_credentials,
    load_settings,
    public_provider_view,
    update_provider,
)
from smartmoney_cub_harness.plugin_cli import plugin_configure
from smartmoney_cub_harness.plugins.catalog import catalog_index
from smartmoney_cub_harness.plugins.registry import PluginStateStore
from smartmoney_cub_harness.plugin_marketplace import _project_record, _runtime_integrated
from smartmoney_cub_harness.trader.connections.manifests import get_manifest
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _kind(kind: str) -> str:
    value = str(kind).strip().lower()
    aliases = {"providers": "provider", "connections": "connection", "plugins": "plugin"}
    value = aliases.get(value, value)
    if value not in {"provider", "connection", "plugin"}:
        raise ValueError("kind must be provider, providers, connection, connections, or plugin")
    return value


def _https_links(*items: Any) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, Mapping):
            label, url = item.get("label", "Official setup"), item.get("url", "")
        else:
            label, url = "Official setup", item
        parsed = urlparse(str(url))
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            continue
        links.append({"label": str(label), "url": str(url)})
    return links


def _provider_info(identifier: str, root: Path) -> dict[str, Any]:
    settings = load_settings(root)
    catalog = PROVIDER_CATALOG.get(identifier, {})
    entry = settings.get("providers", {}).get(identifier) or catalog
    if not entry:
        raise KeyError(f"unknown provider: {identifier}")
    credentials = load_credentials(root)
    stored = (credentials.get("providers") or {}).get(identifier) or {}
    required = []
    if entry.get("requires_key", True):
        required.append({"name": "api_key", "secret": True, "required": True})
        if entry.get("env_key"):
            required.append({"name": "env_key", "value": str(entry["env_key"]), "secret": False, "required": False, "reference": True})
    required.append({"name": "base_url", "value": str(entry.get("base_url") or ""), "secret": False, "required": entry.get("protocol") != "offline"})
    # Catalog defaults describe an available option, not a configured route.
    has_config = bool(stored.get("api_key")) or (
        identifier in settings.get("providers", {}) and identifier not in PROVIDER_CATALOG
    )
    status = "configured_unverified" if has_config else "not_configured"
    links = _https_links(entry.get("portal_url"))
    return {
        "kind": "provider", "identifier": identifier, "name": entry.get("label", identifier),
        "status": status, "required_fields": required, "official_links": links,
        "next_steps": (["Provide the required fields, then verify the provider route."] if status == "not_configured" else ["Verify the provider route before use."]),
        "provider": public_provider_view(identifier, credentials=credentials, settings=settings),
        "safety": SAFETY_DECLARATION,
    }


def _connection_info(identifier: str, root: Path) -> dict[str, Any]:
    manifest = get_manifest(identifier)
    fields = [{"name": name, "secret": name not in {"directory", "symbols", "account_id"}, "required": True} for name in manifest.auth.fields]
    status = "not_configured"
    # ConnectionManager stores one private credential file per user hash. Read
    # only the provider keys from existing files; never create or deserialize a
    # store merely to answer a metadata query.
    for state_hint in root.glob("*/connection_credentials.json"):
        try:
            import json
            payload = json.loads(state_hint.read_text(encoding="utf-8"))
            providers = payload.get("providers", {}) if isinstance(payload, Mapping) else {}
            if identifier in providers:
                status = "configured_unverified"
                break
        except (OSError, ValueError, TypeError):
            continue
    links = _https_links(*(link.to_dict() for link in manifest.official_links))
    return {
        "kind": "connection", "identifier": identifier, "name": manifest.name,
        "status": status, "required_fields": fields, "official_links": links,
        "next_steps": (["Provide the required fields and verify read-only access."] if status == "not_configured" else ["Verify read-only access before syncing."]),
        "connection": manifest.to_dict(), "safety": SAFETY_DECLARATION,
    }


def _plugin_info(identifier: str, root: Path) -> dict[str, Any]:
    entry = catalog_index().get(identifier)
    state_db = root / "state" / "plugins" / "plugin_state.db"
    record = None
    if state_db.is_file():
        store = PluginStateStore(state_db)
        try:
            record = store.get(identifier)
        finally:
            store.close()
    if not entry and not record:
        raise KeyError(f"unknown plugin: {identifier}")
    manifest = (record or {}).get("manifest") or {}
    level = str((entry or {}).get("level") or manifest.get("level") or "adapter")
    installed = record is not None
    projection = _project_record(entry or manifest, record) if record else None
    active = bool(projection and projection["active"])
    runtime_integrated = projection["runtime_integrated"] if projection else _runtime_integrated(entry or manifest)
    callable_now = bool(projection["callable"]) if projection else False
    reason = projection["callable_reason"] if projection else "not_installed"
    requirements = list((entry or {}).get("credential_requirements") or [])
    fields = [{"name": str(item.get("name", "credential")), "label": str(item.get("label", item.get("name", "credential"))), "secret": True, "required": bool(item.get("required", True))} for item in requirements]
    links = _https_links((entry or {}).get("repo"), (entry or {}).get("docs_url"), *((item.get("obtain_url") for item in requirements)))
    return {
        "kind": "plugin", "identifier": identifier, "name": (entry or manifest).get("name", identifier),
        "status": "configured_unverified" if installed else "not_configured",
        "installed": installed, "active": active, "callable": callable_now,
        "runtime_integrated": runtime_integrated, "callable_reason": reason,
        "level": level, "required_fields": fields, "official_links": links,
        "next_steps": (["Install and enable the plugin, then verify its runtime adapter."] if not installed else ["Verify plugin health before use."]),
        "safety": SAFETY_DECLARATION,
    }


def setup_info(kind: str, identifier: str, root: Path) -> dict[str, Any]:
    normalized = _kind(kind)
    root = Path(root)
    if not identifier or not str(identifier).strip():
        return _directory(normalized, root)
    try:
        if normalized == "provider":
            return _provider_info(identifier, root)
        if normalized == "connection":
            return _connection_info(identifier, root)
        return _plugin_info(identifier, root)
    except KeyError:
        directory = _directory(normalized, root)
        directory["requested_identifier"] = str(identifier)
        directory["status"] = "unknown_identifier"
        directory["next_steps"] = ["Choose one of available_identifiers and request setup information."]
        return directory


def _directory(kind: str, root: Path) -> dict[str, Any]:
    """Return an actionable directory response when no item was selected."""
    if kind == "provider":
        identifiers = sorted(set(PROVIDER_CATALOG) | set(load_settings(root).get("providers", {})))
    elif kind == "connection":
        from smartmoney_cub_harness.trader.connections.manifests import list_manifests
        identifiers = [item.provider_id for item in list_manifests()]
    else:
        identifiers = sorted(catalog_index())
    return {
        "kind": kind,
        "status": "action_required",
        "required": "identifier",
        "available_identifiers": identifiers,
        "next_steps": [f"Choose a {kind} identifier and request setup information."],
        "safety": SAFETY_DECLARATION,
    }


def configure(kind: str, identifier: str, root: Path, values: dict[str, Any]) -> dict[str, Any]:
    """Delegate configuration to existing service APIs and return redacted metadata."""
    if not isinstance(values, dict):
        raise TypeError("values must be a dict")
    normalized = _kind(kind)
    payload = dict(values)
    if normalized == "provider":
        if identifier in load_settings(root).get("providers", {}):
            result = update_provider(root, identifier, **{key: value for key, value in payload.items() if key in {"display_name", "base_url", "protocol", "models", "default_model", "api_key", "clear_key"}})
        else:
            result = install_provider(root, identifier, from_catalog=bool(payload.pop("from_catalog", True)), **{key: value for key, value in payload.items() if key in {"label", "base_url", "protocol", "api_key", "models", "display_name"}})
        return _redact_result(result)
    if normalized == "plugin":
        state_db = payload.pop("state_db", str(Path(root) / "state" / "plugins" / "plugin_state.db"))
        result = plugin_configure(identifier, payload, state_db=state_db)
        return _redact_result(result)
    controller = payload.pop("controller", None)
    context = payload.pop("context", None)
    if controller is None or context is None:
        raise ValueError("connection configuration requires an existing controller and context")
    return _redact_result(controller.connect(context, identifier, {"credentials": payload.pop("credentials", {}), "config": payload}))


def _redact_result(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): ("[REDACTED]" if any(token in str(key).lower() for token in ("key", "token", "secret", "password", "credential", "auth")) else _redact_result(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_result(item) for item in value]
    return value
