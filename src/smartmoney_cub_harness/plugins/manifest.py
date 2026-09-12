from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from smartmoney_cub_harness.plugins.types import (
    CapabilityName,
    DataTimeSemantics,
    PluginKind,
    TrustLevel,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

PLUGIN_MANIFEST_SCHEMA = "smartmoney_cub_plugin_manifest.v1"

REQUIRED_MANIFEST_FIELDS = (
    "schema",
    "plugin_id",
    "name",
    "version",
    "source_repo",
    "license",
    "kind",
    "trust_level",
    "api_range",
    "capabilities",
    "data_time_semantics",
    "safety",
)

# Every plugin output and manifest must carry the read-only declaration.
FORBIDDEN_CAPABILITY_FRAGMENTS = ("order", "cancel", "trade_execution", "account_mutation", "broker")


class ManifestError(ValueError):
    """Raised when a plugin manifest cannot be trusted to load."""


@dataclass
class PluginManifest:
    plugin_id: str
    name: str
    version: str
    source_repo: str
    license: str
    kind: str
    trust_level: str
    api_range: str
    capabilities: list[str]
    data_time_semantics: str
    source_commit: str | None = None
    source_tag: str | None = None
    maintainer: str | None = None
    entrypoint: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    required_permissions: list[str] = field(default_factory=list)
    network_required: bool = False
    credential_requirements: list[str] = field(default_factory=list)
    supported_markets: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    required_services: list[str] = field(default_factory=list)
    optional_services: list[str] = field(default_factory=list)
    health_check: str | None = None
    provenance_policy: str = "evidence_envelope_required"
    description: str = ""
    safety: str = SAFETY_DECLARATION

    @property
    def is_networked(self) -> bool:
        return bool(self.network_required)

    @property
    def requires_credentials(self) -> bool:
        return bool(self.credential_requirements)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLUGIN_MANIFEST_SCHEMA,
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "source_repo": self.source_repo,
            "source_commit": self.source_commit,
            "source_tag": self.source_tag,
            "license": self.license,
            "maintainer": self.maintainer,
            "kind": self.kind,
            "trust_level": self.trust_level,
            "api_range": self.api_range,
            "entrypoint": self.entrypoint,
            "capabilities": list(self.capabilities),
            "provides": list(self.provides),
            "required_services": list(self.required_services),
            "optional_services": list(self.optional_services),
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "required_permissions": list(self.required_permissions),
            "network_required": self.network_required,
            "credential_requirements": list(self.credential_requirements),
            "supported_markets": list(self.supported_markets),
            "data_time_semantics": self.data_time_semantics,
            "health_check": self.health_check,
            "provenance_policy": self.provenance_policy,
            "description": self.description,
            "safety": self.safety,
        }


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_api_range(value: str) -> str:
    """Normalize a declared compatibility range into a comparable constraint."""
    if not _is_non_empty_string(value):
        raise ManifestError("api_range must be a non-empty string such as '>=1,<2'")
    return value.strip()


def _major_bounds(api_range: str) -> tuple[int | None, int | None]:
    lower: int | None = None
    upper: int | None = None
    for part in api_range.split(","):
        token = part.strip()
        for operator in (">=", ">", "<=", "<"):
            if not token.startswith(operator):
                continue
            number_text = token[len(operator) :].strip()
            if not number_text.isdigit():
                continue
            number = int(number_text)
            if operator in (">=", ">"):
                lower = number + 1 if operator == ">" else number
            else:
                upper = number if operator == "<" else number + 1
            break
    return lower, upper


def api_range_is_compatible(api_range: str, host_api_version: str) -> bool:
    lower, upper = _major_bounds(api_range)
    try:
        host_major = int(str(host_api_version).split(".")[0])
    except (TypeError, ValueError):
        return False
    if lower is not None and host_major < lower:
        return False
    if upper is not None and host_major >= upper:
        return False
    return True


def validate_manifest(payload: Any, *, host_api_version: str = "1") -> dict[str, Any]:
    """Validate a plugin manifest payload without raising.

    Returns a result object that always carries the safety declaration.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "errors": ["manifest_not_object"],
            "warnings": [],
            "safety": SAFETY_DECLARATION,
        }

    for field_name in REQUIRED_MANIFEST_FIELDS:
        if field_name not in payload:
            errors.append(f"missing_{field_name}")

    if payload.get("schema") not in (None, PLUGIN_MANIFEST_SCHEMA):
        errors.append("invalid_manifest_schema")

    if payload.get("safety") != SAFETY_DECLARATION:
        errors.append("missing_or_invalid_safety_declaration")

    for field_name in ("plugin_id", "name", "version", "source_repo", "license"):
        if field_name in payload and not _is_non_empty_string(payload.get(field_name)):
            errors.append(f"empty_{field_name}")

    if "plugin_id" in payload and _is_non_empty_string(payload.get("plugin_id")):
        identifier = str(payload["plugin_id"])
        if not all(character.isalnum() or character in "-_." for character in identifier):
            errors.append("invalid_plugin_id")

    kind = payload.get("kind")
    if kind is not None and kind not in PluginKind.ALL:
        errors.append("invalid_kind")

    trust_level = payload.get("trust_level")
    if trust_level is not None and trust_level not in TrustLevel.ALL:
        errors.append("invalid_trust_level")

    semantics = payload.get("data_time_semantics")
    if semantics is not None and semantics not in DataTimeSemantics.ALL:
        errors.append("invalid_data_time_semantics")

    capabilities = payload.get("capabilities")
    if capabilities is not None:
        if not isinstance(capabilities, list) or not capabilities:
            errors.append("capabilities_not_non_empty_list")
        else:
            for capability in capabilities:
                if not _is_non_empty_string(capability):
                    errors.append("invalid_capability_name")
                    continue
                lowered = str(capability).lower()
                if any(fragment in lowered for fragment in FORBIDDEN_CAPABILITY_FRAGMENTS):
                    errors.append(f"forbidden_capability:{capability}")

    api_range = payload.get("api_range")
    if api_range is not None:
        try:
            normalized = _parse_api_range(str(api_range))
            if not api_range_is_compatible(normalized, host_api_version):
                errors.append(f"incompatible_api_range:{normalized}")
        except ManifestError as exc:
            errors.append(f"invalid_api_range:{exc}")

    required_permissions = payload.get("required_permissions")
    if required_permissions is not None:
        if not isinstance(required_permissions, list):
            errors.append("required_permissions_not_list")
        else:
            for permission in required_permissions:
                lowered = str(permission).lower()
                if any(fragment in lowered for fragment in FORBIDDEN_CAPABILITY_FRAGMENTS):
                    errors.append(f"forbidden_permission:{permission}")

    if payload.get("network_required") and not payload.get("credential_requirements"):
        warnings.append("network_enabled_without_declared_credentials")

    if payload.get("network_required") is False and payload.get("credential_requirements"):
        warnings.append("credentials_declared_but_network_disabled")

    if payload.get("kind") == PluginKind.SUBPROCESS and not payload.get("entrypoint"):
        errors.append("subprocess_plugin_requires_entrypoint")

    if payload.get("kind") in (PluginKind.ENTRY_POINT, PluginKind.LOCAL_PATH) and not payload.get("entrypoint"):
        warnings.append("no_entrypoint_declared")

    if not payload.get("source_commit") and not payload.get("source_tag"):
        warnings.append("no_source_commit_or_tag_recorded")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "plugin_id": payload.get("plugin_id"),
        "safety": SAFETY_DECLARATION,
    }


def parse_manifest(payload: Any, *, host_api_version: str = "1") -> PluginManifest:
    """Validate and convert a manifest payload, raising ManifestError on failure."""
    result = validate_manifest(payload, host_api_version=host_api_version)
    if not result["ok"]:
        raise ManifestError("; ".join(result["errors"]))

    def as_list(key: str) -> list[str]:
        value = payload.get(key)
        return [str(item) for item in value] if isinstance(value, list) else []

    return PluginManifest(
        plugin_id=str(payload["plugin_id"]),
        name=str(payload["name"]),
        version=str(payload["version"]),
        source_repo=str(payload["source_repo"]),
        license=str(payload["license"]),
        kind=str(payload["kind"]),
        trust_level=str(payload["trust_level"]),
        api_range=str(payload["api_range"]),
        capabilities=as_list("capabilities"),
        data_time_semantics=str(payload["data_time_semantics"]),
        source_commit=payload.get("source_commit"),
        source_tag=payload.get("source_tag"),
        maintainer=payload.get("maintainer"),
        entrypoint=payload.get("entrypoint"),
        input_schema=payload.get("input_schema"),
        output_schema=payload.get("output_schema"),
        required_permissions=as_list("required_permissions"),
        network_required=bool(payload.get("network_required", False)),
        credential_requirements=as_list("credential_requirements"),
        supported_markets=as_list("supported_markets"),
        provides=as_list("provides"),
        required_services=as_list("required_services"),
        optional_services=as_list("optional_services"),
        health_check=payload.get("health_check"),
        provenance_policy=str(payload.get("provenance_policy") or "evidence_envelope_required"),
        description=str(payload.get("description") or ""),
    )


def known_capability(name: str) -> bool:
    return name in CapabilityName.ALL
