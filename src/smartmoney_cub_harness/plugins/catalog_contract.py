"""Frozen contract for the merged plugin catalog and the install channel.

Both the marketplace interface and the installer build against this module, so
the field names, the install discriminator, and the state vocabulary live in one
place. The catalog itself is data; this file only describes its shape.

The catalog answers one question honestly: for each curated project, how does a
user actually obtain it? Three answers exist, and the discriminator records
which one applies rather than leaving the interface to guess.
"""

from __future__ import annotations

from typing import Any, Final

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

CATALOG_SCHEMA: Final[str] = "smartmoney_cub_plugin_catalog.v2"

# How a curated project is obtained. The installer switches on this value and
# never parses a user-supplied string, so an unknown kind is a hard refusal
# rather than a best-effort guess.
INSTALL_PYPI: Final[str] = "pypi"
INSTALL_GIT: Final[str] = "git"
INSTALL_BUILTIN: Final[str] = "builtin"
INSTALL_KINDS: Final[tuple[str, ...]] = (INSTALL_PYPI, INSTALL_GIT, INSTALL_BUILTIN)

# Lifecycle states a market entry can report. Only INSTALLED and ENABLED imply
# code exists on this machine and passed its health check. There is deliberately
# no "configuring" state: an interrupted wizard leaves nothing behind, so a
# half-installed plugin can never be observed.
STATE_AVAILABLE: Final[str] = "AVAILABLE"
STATE_INSTALLED: Final[str] = "INSTALLED"
STATE_ENABLED: Final[str] = "ENABLED"
STATE_DISABLED: Final[str] = "DISABLED"
STATE_ERROR: Final[str] = "ERROR"
MARKET_STATES: Final[tuple[str, ...]] = (
    STATE_AVAILABLE,
    STATE_INSTALLED,
    STATE_ENABLED,
    STATE_DISABLED,
    STATE_ERROR,
)

# Capability names a curated entry may advertise. The list is the harness's own
# vocabulary; an entry that needs a new name adds it here first, which is what
# keeps a curated project from smuggling in an execution-flavoured capability.
CATALOG_CAPABILITIES: Final[tuple[str, ...]] = (
    "market_context",
    "trade_import",
    "reviewer",
    "challenger",
    "evaluator",
    "replay",
    "report_renderer",
    "memory",
    "agent_bridge",
)

FORBIDDEN_CAPABILITY_FRAGMENTS: Final[tuple[str, ...]] = (
    "order",
    "cancel",
    "trade_execution",
    "account_mutation",
    "broker",
)

# Integration levels. A project is never promoted to a higher level just by
# appearing in this catalog.
LEVEL_COMPANION: Final[str] = "companion"
LEVEL_ADAPTER: Final[str] = "adapter"
LEVELS: Final[tuple[str, ...]] = (LEVEL_COMPANION, LEVEL_ADAPTER)


def install_spec(kind: str, **payload: Any) -> dict[str, Any]:
    """Build a validated install discriminator for a catalog entry."""
    if kind not in INSTALL_KINDS:
        raise ValueError("unknown install kind: " + str(kind))
    spec: dict[str, Any] = {"kind": kind}
    if kind == INSTALL_PYPI:
        package = str(payload.get("package") or "").strip()
        module = str(payload.get("module") or "").strip()
        if not package or not module:
            raise ValueError("a pypi install needs both a package and an import module")
        spec["package"] = package
        spec["module"] = module
        spec["version"] = str(payload.get("version") or "").strip() or None
    elif kind == INSTALL_GIT:
        repo = str(payload.get("repo") or "").strip()
        module = str(payload.get("module") or "").strip()
        if not repo.startswith("https://github.com/"):
            raise ValueError("a git install needs an https github repository: " + repo)
        if not module:
            raise ValueError("a git install needs an import module for its health check")
        spec["repo"] = repo
        spec["module"] = module
        spec["tag"] = str(payload.get("tag") or "").strip() or None
    else:
        spec["note"] = str(payload.get("note") or "bundled with the harness").strip()
    return spec


def catalog_entry(
    *,
    plugin_id: str,
    name: str,
    category: str,
    description: str,
    repo: str,
    install: dict[str, Any],
    license_name: str,
    level: str,
    capabilities: list[str],
    requires_credentials: bool,
    network_required: bool,
    execution_risk: str,
    boundary: str,
    docs_url: str | None = None,
    credential_mode: str = "none",
    credential_requirements: list[dict[str, Any]] | None = None,
    credential_setup_url: str | None = None,
) -> dict[str, Any]:
    """Build one catalog entry, refusing anything outside the contract."""
    kind = str(install.get("kind") or "")
    if kind not in INSTALL_KINDS:
        raise ValueError(plugin_id + ": unknown install kind " + repr(kind))
    if not plugin_id or not name or not category:
        raise ValueError("a catalog entry needs an id, a name, and a category")
    if not repo:
        raise ValueError(plugin_id + ": every entry names its upstream or its builtin origin")
    if not license_name:
        raise ValueError(plugin_id + ": a license claim is required")
    if level not in LEVELS:
        raise ValueError(plugin_id + ": unknown level " + repr(level))
    if not capabilities:
        raise ValueError(plugin_id + ": capabilities must not be empty")
    for capability in capabilities:
        lowered = capability.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_CAPABILITY_FRAGMENTS):
            raise ValueError(plugin_id + ": forbidden capability " + repr(capability))
    if execution_risk not in ("low", "medium", "high"):
        raise ValueError(plugin_id + ": execution risk must be low, medium, or high")
    if execution_risk == "high" and level != LEVEL_COMPANION:
        # A project whose own code can place orders stays a companion: the
        # harness may read its reports, never host it as a runtime plugin.
        raise ValueError(plugin_id + ": high execution risk must stay a companion")
    if credential_mode not in ("none", "managed_local", "external_only"):
        raise ValueError(plugin_id + ": unknown credential mode")
    requirements = credential_requirements or []
    if credential_mode == "managed_local" and not requirements:
        raise ValueError(plugin_id + ": managed credentials need named requirements")
    for requirement in requirements:
        if not requirement.get("name") or not str(requirement.get("obtain_url", "")).startswith("https://"):
            raise ValueError(plugin_id + ": credential requires a name and official HTTPS obtain URL")
    return {
        "plugin_id": plugin_id,
        "name": name,
        "category": category,
        "description": description,
        "repo": repo,
        "docs_url": docs_url,
        "install": install,
        "license": license_name,
        "level": level,
        "capabilities": list(capabilities),
        "requires_credentials": bool(requires_credentials),
        "credential_mode": credential_mode,
        "credential_requirements": [dict(item) for item in requirements],
        "credential_setup_url": credential_setup_url,
        "network_required": bool(network_required),
        "execution_risk": execution_risk,
        "boundary": boundary,
        "source": "smartmoney-cub/official-curated",
        "safety": SAFETY_DECLARATION,
    }


def manual_install_command(entry: dict[str, Any]) -> str:
    """The upstream-native command for an entry, shown in the interface.

    The marketplace installs through its own venv, so this is not always the
    command the button runs; it is what the interface shows so a user can
    reproduce the install themselves, which is the point of naming the upstream
    project on the card.
    """
    spec = entry.get("install") if isinstance(entry.get("install"), dict) else {}
    kind = spec.get("kind")
    if kind == INSTALL_PYPI:
        package = str(spec.get("package") or "")
        version = spec.get("version")
        return "pip install " + package + "==" + str(version) if version else "pip install " + package
    if kind == INSTALL_GIT:
        tag = spec.get("tag")
        suffix = " --branch " + str(tag) if tag else ""
        return "git clone --depth 1" + suffix + " " + str(spec.get("repo") or "")
    return str(spec.get("note") or "bundled with the harness")
