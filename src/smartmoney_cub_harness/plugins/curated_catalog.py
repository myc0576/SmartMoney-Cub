"""Curated finance plugin descriptors and local catalog state.

This module is deliberately a catalog boundary.  It records metadata and
explicit user lifecycle events; it never downloads, imports, or executes an
upstream project.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

CURATED_MANIFEST_SCHEMA = "smartmoney_cub_curated_plugin_manifest.v1"
CURATED_CATALOG_SCHEMA = "smartmoney_cub_curated_finance_catalog.v1"

CURATED_MANIFEST_FIELDS = (
    "schema",
    "id",
    "name",
    "version",
    "source",
    "commit",
    "license",
    "declared_network",
    "capabilities",
    "permissions",
    "installed",
    "enabled",
    "update",
    "health",
    "profile_reload",
    "safety",
)

_FORBIDDEN_TERMS = (
    "shell",
    "filesystem",
    "file_system",
    "fs",
    "web",
    "http",
    "workflow",
    "subagent",
    "agent_team",
    "agent-team",
    "broker",
    "order",
    "trade",
    "account",
    "credential",
    "cookie",
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,127}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class CuratedManifestError(ValueError):
    """Raised when a curated descriptor is not safe to admit to the catalog."""


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _forbidden(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9_-]+", "_", value.lower())
    return any(term in normalized for term in _FORBIDDEN_TERMS)


def _timestamp(value: Any, *, allow_none: bool = True) -> bool:
    if value is None and allow_none:
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _metadata_result(
    *,
    payload: Any,
    errors: list[str],
) -> dict[str, Any]:
    return {
        "ok": not errors,
        "errors": errors,
        "safety": SAFETY_DECLARATION,
        "manifest_schema": CURATED_MANIFEST_SCHEMA,
        "plugin_id": payload.get("id") if isinstance(payload, dict) else None,
    }


def validate_curated_manifest(payload: Any) -> dict[str, Any]:
    """Strictly validate a curated descriptor without loading its source."""

    if not isinstance(payload, dict):
        return _metadata_result(payload=payload, errors=["manifest_not_object"])

    errors: list[str] = []
    expected = set(CURATED_MANIFEST_FIELDS)
    for field_name in CURATED_MANIFEST_FIELDS:
        if field_name not in payload:
            errors.append(f"missing_{field_name}")
    for field_name in sorted(set(payload) - expected):
        errors.append(f"unknown_field:{field_name}")

    if payload.get("schema") != CURATED_MANIFEST_SCHEMA:
        errors.append("invalid_schema")
    if payload.get("safety") != SAFETY_DECLARATION:
        errors.append("invalid_safety")

    for field_name in ("id", "name", "version", "source", "commit", "license"):
        value = payload.get(field_name)
        if not _non_empty(value):
            errors.append(f"empty_{field_name}")
    if _non_empty(payload.get("id")) and _ID_RE.fullmatch(payload["id"]) is None:
        errors.append("invalid_id")
    if _non_empty(payload.get("version")) and _VERSION_RE.fullmatch(payload["version"]) is None:
        errors.append("invalid_version")
    if _non_empty(payload.get("source")) and (
        "\n" in payload["source"] or payload["source"].startswith(("/", "~"))
    ):
        errors.append("source_must_not_be_absolute_path")
    if _non_empty(payload.get("commit")) and any(char.isspace() for char in payload["commit"]):
        errors.append("invalid_commit")

    if not isinstance(payload.get("declared_network"), bool):
        errors.append("invalid_declared_network")

    for field_name in ("capabilities", "permissions"):
        values = payload.get(field_name)
        if not isinstance(values, list) or not values or not all(_non_empty(item) for item in values):
            errors.append(f"invalid_{field_name}")
            continue
        for value in values:
            if _forbidden(value):
                errors.append(f"forbidden_{field_name[:-1]}:{value}")

    if not isinstance(payload.get("installed"), bool):
        errors.append("invalid_installed")
    if not isinstance(payload.get("enabled"), bool):
        errors.append("invalid_enabled")
    if payload.get("enabled") is True and payload.get("installed") is not True:
        errors.append("enabled_requires_installed")

    update = payload.get("update")
    if not isinstance(update, dict):
        errors.append("invalid_update")
    else:
        for field_name in ("available", "version", "commit", "checked_at", "safety"):
            if field_name not in update:
                errors.append(f"missing_update_{field_name}")
        if not isinstance(update.get("available"), bool):
            errors.append("invalid_update_available")
        if not _non_empty(update.get("version")):
            errors.append("empty_update_version")
        if not _non_empty(update.get("commit")):
            errors.append("empty_update_commit")
        if not _timestamp(update.get("checked_at")):
            errors.append("invalid_update_checked_at")
        if update.get("safety") != SAFETY_DECLARATION:
            errors.append("invalid_update_safety")

    health = payload.get("health")
    if not isinstance(health, dict):
        errors.append("invalid_health")
    else:
        for field_name in ("status", "checked_at", "executed_upstream", "safety"):
            if field_name not in health:
                errors.append(f"missing_health_{field_name}")
        if health.get("status") not in {"unknown", "ok", "error", "disabled"}:
            errors.append("invalid_health_status")
        if not _timestamp(health.get("checked_at")):
            errors.append("invalid_health_checked_at")
        if health.get("executed_upstream") is not False:
            errors.append("health_must_not_execute_upstream")
        if health.get("safety") != SAFETY_DECLARATION:
            errors.append("invalid_health_safety")

    reload_metadata = payload.get("profile_reload")
    if not isinstance(reload_metadata, dict):
        errors.append("invalid_profile_reload")
    else:
        for field_name in ("reloadable", "last_event", "explicit_boundary", "safety"):
            if field_name not in reload_metadata:
                errors.append(f"missing_profile_reload_{field_name}")
        if reload_metadata.get("reloadable") is not True:
            errors.append("profile_reload_not_supported")
        if not _timestamp(reload_metadata.get("last_event")):
            errors.append("invalid_profile_reload_last_event")
        if reload_metadata.get("explicit_boundary") is not True:
            errors.append("profile_reload_must_be_explicit")
        if reload_metadata.get("safety") != SAFETY_DECLARATION:
            errors.append("invalid_profile_reload_safety")

    return _metadata_result(payload=payload, errors=errors)


@dataclass
class CuratedFinancePluginDescriptor:
    id: str
    name: str
    version: str
    source: str
    commit: str
    license: str
    declared_network: bool
    capabilities: list[str]
    permissions: list[str]
    installed: bool = False
    enabled: bool = False
    update: dict[str, Any] = field(default_factory=dict)
    health: dict[str, Any] = field(default_factory=dict)
    profile_reload: dict[str, Any] = field(default_factory=dict)
    safety: str = SAFETY_DECLARATION

    def __post_init__(self) -> None:
        payload = self.to_manifest()
        result = validate_curated_manifest(payload)
        if not result["ok"]:
            raise CuratedManifestError("; ".join(result["errors"]))

    def to_manifest(self) -> dict[str, Any]:
        update = dict(self.update) or {
            "available": False,
            "version": self.version,
            "commit": self.commit,
            "checked_at": None,
            "safety": SAFETY_DECLARATION,
        }
        health = dict(self.health) or {
            "status": "unknown",
            "checked_at": None,
            "executed_upstream": False,
            "safety": SAFETY_DECLARATION,
        }
        profile_reload = dict(self.profile_reload) or {
            "reloadable": True,
            "last_event": None,
            "explicit_boundary": True,
            "safety": SAFETY_DECLARATION,
        }
        return {
            "schema": CURATED_MANIFEST_SCHEMA,
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "commit": self.commit,
            "license": self.license,
            "declared_network": self.declared_network,
            "capabilities": list(self.capabilities),
            "permissions": list(self.permissions),
            "installed": self.installed,
            "enabled": self.enabled,
            "update": update,
            "health": health,
            "profile_reload": profile_reload,
            "safety": self.safety,
        }


CuratedPluginDescriptor = CuratedFinancePluginDescriptor


def parse_curated_manifest(payload: Any) -> CuratedFinancePluginDescriptor:
    result = validate_curated_manifest(payload)
    if not result["ok"]:
        raise CuratedManifestError("; ".join(result["errors"]))
    return CuratedFinancePluginDescriptor(
        id=payload["id"],
        name=payload["name"],
        version=payload["version"],
        source=payload["source"],
        commit=payload["commit"],
        license=payload["license"],
        declared_network=payload["declared_network"],
        capabilities=list(payload["capabilities"]),
        permissions=list(payload["permissions"]),
        installed=payload["installed"],
        enabled=payload["enabled"],
        update=copy.deepcopy(payload["update"]),
        health=copy.deepcopy(payload["health"]),
        profile_reload=copy.deepcopy(payload["profile_reload"]),
        safety=payload["safety"],
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _response(status: str, *, plugin: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    response: dict[str, Any] = {"status": status, **extra}
    if plugin is not None:
        response["plugin"] = plugin
    response["safety"] = SAFETY_DECLARATION
    return response


class CuratedFinancePluginCatalog:
    """An in-memory, explicit state machine for curated plugin metadata."""

    def __init__(self, descriptors: Iterable[CuratedFinancePluginDescriptor] = ()) -> None:
        self._plugins: dict[str, CuratedFinancePluginDescriptor] = {}
        self._events: list[dict[str, Any]] = []
        for descriptor in descriptors:
            if descriptor.id in self._plugins:
                raise CuratedManifestError(f"duplicate_id:{descriptor.id}")
            self._plugins[descriptor.id] = parse_curated_manifest(descriptor.to_manifest())

    def _get(self, plugin_id: str) -> CuratedFinancePluginDescriptor:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise KeyError(f"unknown curated plugin: {plugin_id}") from exc

    def _record(self, plugin_id: str, action: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        self._events.append(
            {
                "plugin_id": plugin_id,
                "action": action,
                "from": before,
                "to": after,
                "executed_upstream": False,
                "safety": SAFETY_DECLARATION,
            }
        )

    def get(self, plugin_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._get(plugin_id).to_manifest())

    def list(self) -> list[dict[str, Any]]:
        return [self.get(plugin_id) for plugin_id in sorted(self._plugins)]

    def events(self, plugin_id: str | None = None) -> list[dict[str, Any]]:
        events = self._events if plugin_id is None else [item for item in self._events if item["plugin_id"] == plugin_id]
        return copy.deepcopy(events)

    def install(self, plugin_id: str) -> dict[str, Any]:
        descriptor = self._get(plugin_id)
        before = descriptor.to_manifest()
        descriptor.installed = True
        descriptor.enabled = False
        after = descriptor.to_manifest()
        self._record(plugin_id, "install", before, after)
        return _response("installed", plugin=after, downloaded=False, executed_upstream=False)

    def enable(self, plugin_id: str) -> dict[str, Any]:
        descriptor = self._get(plugin_id)
        if not descriptor.installed:
            return _response("refused", plugin=descriptor.to_manifest(), error={"code": "not_installed"})
        before = descriptor.to_manifest()
        descriptor.enabled = True
        after = descriptor.to_manifest()
        self._record(plugin_id, "enable", before, after)
        return _response("enabled", plugin=after, executed_upstream=False)

    def disable(self, plugin_id: str) -> dict[str, Any]:
        descriptor = self._get(plugin_id)
        before = descriptor.to_manifest()
        descriptor.enabled = False
        after = descriptor.to_manifest()
        self._record(plugin_id, "disable", before, after)
        return _response("disabled", plugin=after, executed_upstream=False)

    def record_update(self, plugin_id: str, *, version: str, commit: str) -> dict[str, Any]:
        descriptor = self._get(plugin_id)
        if not _VERSION_RE.fullmatch(version) or not _non_empty(commit) or any(char.isspace() for char in commit):
            return _response("refused", plugin=descriptor.to_manifest(), error={"code": "invalid_update_metadata"})
        before = descriptor.to_manifest()
        descriptor.update = {
            "available": True,
            "version": version,
            "commit": commit,
            "checked_at": _now_iso(),
            "safety": SAFETY_DECLARATION,
        }
        after = descriptor.to_manifest()
        self._record(plugin_id, "record_update", before, after)
        return _response("update_available", plugin=after, fetched=False, executed_upstream=False)

    def update(self, plugin_id: str) -> dict[str, Any]:
        descriptor = self._get(plugin_id)
        metadata = descriptor.update or {}
        if metadata.get("available") is not True:
            return _response("refused", plugin=descriptor.to_manifest(), error={"code": "no_update_available"})
        before = descriptor.to_manifest()
        descriptor.version = str(metadata["version"])
        descriptor.commit = str(metadata["commit"])
        descriptor.enabled = False
        descriptor.update = {
            "available": False,
            "version": descriptor.version,
            "commit": descriptor.commit,
            "checked_at": metadata.get("checked_at"),
            "safety": SAFETY_DECLARATION,
        }
        after = descriptor.to_manifest()
        self._record(plugin_id, "update", before, after)
        return _response("updated", plugin=after, fetched=False, executed_upstream=False)

    def health(self, plugin_id: str) -> dict[str, Any]:
        descriptor = self._get(plugin_id)
        before = descriptor.to_manifest()
        descriptor.health = {
            "status": "ok" if descriptor.installed else "disabled",
            "checked_at": _now_iso(),
            "executed_upstream": False,
            "note": "metadata-only catalog health; upstream was not loaded",
            "safety": SAFETY_DECLARATION,
        }
        after = descriptor.to_manifest()
        self._record(plugin_id, "health", before, after)
        return _response(descriptor.health["status"], plugin=after, health=after["health"], executed_upstream=False)

    def profile_reload(self, profile_name: str) -> dict[str, Any]:
        if not _non_empty(profile_name):
            return _response("refused", error={"code": "profile_name_required"})
        event = {
            "profile": profile_name,
            "explicit": True,
            "boundary": "catalog_to_runtime",
            "executed_upstream": False,
            "timestamp": _now_iso(),
            "safety": SAFETY_DECLARATION,
        }
        for descriptor in self._plugins.values():
            metadata = dict(descriptor.profile_reload)
            metadata["last_event"] = event["timestamp"]
            metadata["safety"] = SAFETY_DECLARATION
            descriptor.profile_reload = metadata
        self._events.append({"plugin_id": "*", "action": "profile_reload", "event": event, "safety": SAFETY_DECLARATION})
        return _response("profile_reload_requested", event=event, plugins=self.list())

    def payload(self) -> dict[str, Any]:
        return {
            "schema": CURATED_CATALOG_SCHEMA,
            "plugins": self.list(),
            "events": self.events(),
            "policy": "metadata-only; install, update, and health never fetch or execute upstream projects",
            "safety": SAFETY_DECLARATION,
        }


def _toy_descriptor(
    *, id: str, name: str, capabilities: list[str], permissions: list[str]
) -> CuratedFinancePluginDescriptor:
    return CuratedFinancePluginDescriptor(
        id=id,
        name=name,
        version="0.1.0",
        source="builtin://smartmoney-cub/toy-fixtures",
        commit="toy-offline-2026-09-16",
        license="MIT",
        declared_network=False,
        capabilities=capabilities,
        permissions=permissions,
    )


CURATED_FINANCE_PLUGINS: tuple[CuratedFinancePluginDescriptor, ...] = (
    _toy_descriptor(
        id="smartmoney.tradingagents-toy",
        name="TradingAgents-style multi-role toy evidence",
        capabilities=["reviewer", "challenger"],
        permissions=["redacted_review_envelope", "toy_offline_fixture"],
    ),
    _toy_descriptor(
        id="smartmoney.evaluator-memory-challenger-toy",
        name="Evaluator/memory/challenger toy evidence",
        capabilities=["evaluator", "memory", "challenger"],
        permissions=["redacted_review_envelope", "toy_offline_fixture"],
    ),
)


def curated_catalog_payload() -> dict[str, Any]:
    return CuratedFinancePluginCatalog(CURATED_FINANCE_PLUGINS).payload()
