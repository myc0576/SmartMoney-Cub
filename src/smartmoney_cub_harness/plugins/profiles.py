from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

PLUGIN_ENTRY_SCHEMA = "smartmoney_cub_plugin_entry.v1"
PROFILE_SCHEMA = "smartmoney_cub_profile.v1"

PROFILE_DEFAULT_OFFLINE = "default-offline"
PROFILE_A_SHARE_REVIEW = "a-share-review"
PROFILE_RESEARCH = "research"
PROFILE_AI_OPTIONAL = "ai-optional"


@dataclass
class PluginEntry:
    """One plugin slot in the entry tree.

    The id field is stable across reloads so configuration patches keep applying
    to the same logical slot even when providers are swapped underneath.
    """

    id: str
    name: str
    enabled: bool = True
    group: str = "default"
    config: dict[str, Any] = field(default_factory=dict)
    required_services: list[str] = field(default_factory=list)
    optional_services: list[str] = field(default_factory=list)
    disabled_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLUGIN_ENTRY_SCHEMA,
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "group": self.group,
            "config": dict(self.config),
            "required_services": list(self.required_services),
            "optional_services": list(self.optional_services),
            "disabled_reason": self.disabled_reason,
            "safety": SAFETY_DECLARATION,
        }


@dataclass
class Bundle:
    """An ordered group of plugin entries."""

    name: str
    entries: list[PluginEntry] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "entries": [entry.to_dict() for entry in self.entries],
            "safety": SAFETY_DECLARATION,
        }


@dataclass
class Patch:
    """A user override applied on top of bundles: enable, disable, or reconfigure."""

    entry_id: str
    enabled: bool | None = None
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "enabled": self.enabled,
            "config": dict(self.config),
            "safety": SAFETY_DECLARATION,
        }


@dataclass
class Profile:
    """A named composition of bundles plus user patches."""

    name: str
    description: str = ""
    bundles: list[Bundle] = field(default_factory=list)
    patches: list[Patch] = field(default_factory=list)
    allow_network: bool = False
    allow_external_llm: bool = False
    allow_credentials: bool = False

    def resolve_entries(self) -> list[PluginEntry]:
        """Flatten bundles and apply patches in order."""
        resolved: dict[str, PluginEntry] = {}
        order: list[str] = []
        for bundle in self.bundles:
            for entry in bundle.entries:
                if entry.id not in resolved:
                    order.append(entry.id)
                resolved[entry.id] = PluginEntry(
                    id=entry.id,
                    name=entry.name,
                    enabled=entry.enabled,
                    group=entry.group,
                    config=dict(entry.config),
                    required_services=list(entry.required_services),
                    optional_services=list(entry.optional_services),
                    disabled_reason=entry.disabled_reason,
                )

        for patch in self.patches:
            entry = resolved.get(patch.entry_id)
            if entry is None:
                continue
            if patch.enabled is not None:
                entry.enabled = patch.enabled
                entry.disabled_reason = None if patch.enabled else "patched_disabled"
            entry.config.update(patch.config)

        return [resolved[identifier] for identifier in order]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROFILE_SCHEMA,
            "name": self.name,
            "description": self.description,
            "allow_network": self.allow_network,
            "allow_external_llm": self.allow_external_llm,
            "allow_credentials": self.allow_credentials,
            "bundles": [bundle.to_dict() for bundle in self.bundles],
            "patches": [patch.to_dict() for patch in self.patches],
            "entries": [entry.to_dict() for entry in self.resolve_entries()],
            "safety": SAFETY_DECLARATION,
        }


def _core_bundle() -> Bundle:
    return Bundle(
        name="core",
        description="Trusted offline core: local files, toy fixtures, and manual review.",
        entries=[
            PluginEntry(id="core.local-csv-import", name="Local CSV and 同花顺 import", group="import"),
            PluginEntry(id="core.toy-market-context", name="Offline toy market context", group="context"),
            PluginEntry(id="core.manual-journal", name="Manual journal memory", group="memory"),
            PluginEntry(id="core.static-html-report", name="Static HTML report renderer", group="report"),
        ],
    )


def _a_share_bundle() -> Bundle:
    return Bundle(
        name="a-share-review",
        description="A-share review helpers that stay offline by default.",
        entries=[
            PluginEntry(
                id="a-share.regime-cockpit",
                name="Sentiment regime cockpit",
                group="context",
            ),
            PluginEntry(
                id="a-share.fill-ledger",
                name="T+1 fill ledger and cost basis",
                group="import",
                required_services=["trade_import"],
            ),
        ],
    )


def _research_bundle() -> Bundle:
    return Bundle(
        name="research",
        description="Offline evaluation and replay seams. Disabled until a provider is installed.",
        entries=[
            PluginEntry(
                id="research.evaluator-slot",
                name="External evaluator slot",
                enabled=False,
                disabled_reason="no_provider_installed",
                group="evaluation",
                required_services=["evaluator"],
            ),
            PluginEntry(
                id="research.replay-slot",
                name="External replay slot",
                enabled=False,
                disabled_reason="no_provider_installed",
                group="replay",
                required_services=["replay"],
            ),
        ],
    )


def _ai_bundle() -> Bundle:
    return Bundle(
        name="ai-optional",
        description="Optional external model seams. Offline until the user opts in explicitly.",
        entries=[
            PluginEntry(
                id="ai.llm-provider-slot",
                name="Optional LLM provider",
                enabled=False,
                disabled_reason="network_and_external_llm_default_off",
                group="llm",
                required_services=["llm_provider"],
            ),
            PluginEntry(
                id="ai.agent-bridge-slot",
                name="Optional local agent bridge",
                enabled=False,
                disabled_reason="network_and_external_llm_default_off",
                group="agent",
                required_services=["agent_bridge"],
            ),
        ],
    )


BUILTIN_PROFILES: dict[str, Profile] = {
    PROFILE_DEFAULT_OFFLINE: Profile(
        name=PROFILE_DEFAULT_OFFLINE,
        description="Fully offline. No network, no external model, no credentials.",
        bundles=[_core_bundle()],
    ),
    PROFILE_A_SHARE_REVIEW: Profile(
        name=PROFILE_A_SHARE_REVIEW,
        description="Offline A-share review workflow for 同花顺 and broker CSV exports.",
        bundles=[_core_bundle(), _a_share_bundle()],
    ),
    PROFILE_RESEARCH: Profile(
        name=PROFILE_RESEARCH,
        description="Offline research and evaluation seams for installed third-party plugins.",
        bundles=[_core_bundle(), _research_bundle()],
    ),
    PROFILE_AI_OPTIONAL: Profile(
        name=PROFILE_AI_OPTIONAL,
        description="Opt-in external model and agent bridges; user supplies keys outside the repo.",
        bundles=[_core_bundle(), _research_bundle(), _ai_bundle()],
        allow_network=True,
        allow_external_llm=True,
    ),
}


def get_profile(name: str) -> Profile:
    profile = BUILTIN_PROFILES.get(name)
    if profile is None:
        raise KeyError(f"unknown profile: {name}")
    return profile
