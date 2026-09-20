from __future__ import annotations

from smartmoney_cub_harness.plugins.catalog import (
    CATALOG_ENTRIES,
    LEVEL_ADAPTER,
    LEVEL_COMPANION,
    LEVEL_RUNTIME_PLUGIN,
    LEVELS,
    catalog_payload,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

FORBIDDEN_CAPABILITIES = ("order", "cancel", "trade_execution", "account_mutation", "broker")


def test_catalog_declares_levels_and_safety() -> None:
    payload = catalog_payload()
    assert payload["schema"] == "smartmoney_cub_plugin_catalog.v1"
    assert payload["safety"] == SAFETY_DECLARATION
    assert set(payload["counts"]) == set(LEVELS)
    assert "installed" in payload["policy"]
    assert "user-initiated" in payload["policy"]


def test_catalog_never_declares_execution_capabilities() -> None:
    for entry in CATALOG_ENTRIES:
        for capability in entry.capabilities:
            lowered = capability.lower()
            assert not any(fragment in lowered for fragment in FORBIDDEN_CAPABILITIES), entry.project


def test_high_execution_risk_projects_stay_companion_only() -> None:
    for entry in CATALOG_ENTRIES:
        if entry.execution_risk == "high":
            assert entry.level == LEVEL_COMPANION, entry.project
            assert entry.capabilities == [], entry.project


def test_catalog_entries_carry_a_boundary_and_license() -> None:
    for entry in CATALOG_ENTRIES:
        assert entry.boundary.strip(), entry.project
        assert entry.license.strip(), entry.project
        assert entry.level in LEVELS, entry.project


def test_catalog_includes_reference_adapters_and_companions() -> None:
    levels = {entry["level"] for entry in catalog_payload()["entries"]}
    assert LEVEL_ADAPTER in levels
    assert LEVEL_COMPANION in levels
    # Nothing ships as a bundled runtime plugin in the core release.
    assert LEVEL_RUNTIME_PLUGIN not in levels


def test_networked_catalog_entries_are_flagged() -> None:
    networked = [entry for entry in CATALOG_ENTRIES if entry.project.startswith("akfamily")]
    assert networked
    assert networked[0].network_required is True


def test_typesafe_skills_companion_entry() -> None:
    payload = catalog_payload()
    matches = [e for e in payload["entries"] if "typesafe" in e["repo"].lower()]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["project"] == "typesafe-ai/skills"
    assert entry["level"] == LEVEL_COMPANION
    assert entry["license"] == "MIT"
    assert entry["boundary"].strip()
    assert "TYPESAFE_API_KEY" in entry["boundary"]
    assert "review evidence or a challenger candidate" in entry["boundary"]
    assert "order intent" in entry["boundary"]
    for capability in entry["capabilities"]:
        lowered = capability.lower()
        assert not any(fragment in lowered for fragment in FORBIDDEN_CAPABILITIES), (
            f"TypeSafe entry declares forbidden capability: {capability}"
        )
