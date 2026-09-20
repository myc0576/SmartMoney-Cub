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

TARGET_SIX_REPOS = (
    "https://github.com/akfamily/akshare",
    "https://github.com/microsoft/qlib",
    "https://github.com/amazon-science/chronos-forecasting",
    "https://github.com/google-research/timesfm",
    "https://github.com/Nixtla/neuralforecast",
    "https://github.com/AI4Finance-Foundation/FinRobot",
)

NEW_COMPANION_PROJECTS = (
    "amazon-science/chronos-forecasting",
    "google-research/timesfm",
    "Nixtla/neuralforecast",
    "AI4Finance-Foundation/FinRobot",
)


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


def test_new_companion_projects_registered_with_boundaries_and_license() -> None:
    entries_by_project = {entry.project: entry for entry in CATALOG_ENTRIES}
    for project_name in NEW_COMPANION_PROJECTS:
        assert project_name in entries_by_project, f"Missing project: {project_name}"
        entry = entries_by_project[project_name]
        assert entry.level == LEVEL_COMPANION, project_name
        assert entry.license == "Apache-2.0", project_name
        assert entry.boundary.strip(), project_name
        assert "read-only" in entry.boundary.lower(), project_name
        assert "review evidence" in entry.boundary.lower(), project_name
        assert "no automatic champion promotion" in entry.boundary.lower(), project_name
        for capability in entry.capabilities:
            lowered = capability.lower()
            assert not any(fragment in lowered for fragment in FORBIDDEN_CAPABILITIES), project_name


def test_companion_entries_never_claim_execution_and_runtime_plugin_absent() -> None:
    payload = catalog_payload()
    entries = payload["entries"]
    levels = {entry["level"] for entry in entries}
    assert LEVEL_RUNTIME_PLUGIN not in levels
    assert payload["counts"][LEVEL_RUNTIME_PLUGIN] == 0

    for entry in entries:
        if entry["level"] == LEVEL_COMPANION:
            for cap in entry["capabilities"]:
                lowered = cap.lower()
                assert not any(fragment in lowered for fragment in FORBIDDEN_CAPABILITIES), entry["project"]
                assert "execution" not in lowered, entry["project"]


def test_target_six_open_source_projects_discoverable_in_payload() -> None:
    payload = catalog_payload()
    payload_repos = {entry["repo"]: entry for entry in payload["entries"]}
    for repo_url in TARGET_SIX_REPOS:
        assert repo_url in payload_repos, f"Target repo not found in catalog payload: {repo_url}"
        entry = payload_repos[repo_url]
        assert entry["safety"] == SAFETY_DECLARATION
        assert entry["license"] in ("MIT", "Apache-2.0")
