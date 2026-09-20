from __future__ import annotations

from smartmoney_cub_harness.plugin_marketplace import MarketplaceStore, official_catalog
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_official_catalog_contains_complete_review_chain():
    entries = official_catalog()
    assert len(entries) == 24
    assert {entry["category"] for entry in entries} == {"数据", "绩效与风险", "研究与评估", "Agent"}
    assert all(entry["source"] == "smartmoney-cub/official-curated" for entry in entries)
    assert all(entry["safety"] == SAFETY_DECLARATION for entry in entries)


def test_target_six_open_source_projects_provenance_and_safety():
    entries = {entry["plugin_id"]: entry for entry in official_catalog()}
    expected_provenance = {
        "akshare": {
            "source_repo": "https://github.com/akfamily/akshare",
            "source_commit": "0191689d57c667b7c7a198fd0cf97316837ef311",
            "license": "MIT",
        },
        "qlib-factor-evaluator": {
            "source_repo": "https://github.com/microsoft/qlib",
            "source_commit": "be725493eb1a6bbb42bf11b37aa7669f59610ff1",
            "license": "MIT",
        },
        "chronos-forecasting": {
            "source_repo": "https://github.com/amazon-science/chronos-forecasting",
            "source_commit": "10afa9ebe016e514f9d7dc1aa873f66af57e116b",
            "license": "Apache-2.0",
        },
        "timesfm": {
            "source_repo": "https://github.com/google-research/timesfm",
            "source_commit": "e31dadd84cb26bd5153fde6687502b8312e918fb",
            "license": "Apache-2.0",
        },
        "neuralforecast": {
            "source_repo": "https://github.com/Nixtla/neuralforecast",
            "source_commit": "344aaffd504245ff661bd9e211f220f9214a1876",
            "license": "Apache-2.0",
        },
        "finrobot": {
            "source_repo": "https://github.com/AI4Finance-Foundation/FinRobot",
            "source_commit": "6d6ccd32c1b8b1904dc656cf06897438aba3daec",
            "license": "Apache-2.0",
        },
    }

    for plugin_id, facts in expected_provenance.items():
        assert plugin_id in entries
        entry = entries[plugin_id]
        assert entry["source_repo"] == facts["source_repo"]
        assert entry["source_commit"] == facts["source_commit"]
        assert entry["license"] == facts["license"]
        # A pinned default-branch head is only meaningful next to the date it was
        # read. Without this the catalog cannot tell a fresh pin from a stale one.
        assert entry["source_checked_at"] == "2026-09-20"
        assert entry["latest_release"]
        assert entry["requires_credentials"] is False
        assert entry["safety"] == SAFETY_DECLARATION

    # Verify the four new projects exist and have expected categories
    assert entries["chronos-forecasting"]["category"] == "研究与评估"
    assert entries["timesfm"]["category"] == "研究与评估"
    assert entries["neuralforecast"]["category"] == "研究与评估"
    assert entries["finrobot"]["category"] == "Agent"

    # Verify no entry declares execution-only permissions or capabilities
    forbidden_terms = ("order", "cancel", "trade_execution", "account_mutation", "broker")
    for entry in entries.values():
        for perm in entry.get("permissions", []):
            perm_lower = perm.lower()
            assert not any(term in perm_lower for term in forbidden_terms)
            assert "trade" not in perm_lower or "read" in perm_lower
            assert "exec" not in perm_lower
        assert entry["safety"] == SAFETY_DECLARATION


def test_install_requires_configuration_then_mounts_immediately(tmp_path):
    market = MarketplaceStore(tmp_path)
    pending = market.install("quantstats")
    assert pending["status"] == "configuration_required"
    assert pending["plugin"]["state"] == "CONFIGURING"
    assert pending["plugin"]["mounted"] is False
    active = market.install("quantstats", {"permissions_confirmed": True})
    assert active["status"] == "ok"
    assert active["plugin"]["state"] == "ACTIVE"
    assert active["mounted"] is True


def test_update_needs_confirmation_and_enable_disable_are_explicit(tmp_path):
    market = MarketplaceStore(tmp_path)
    market.install("akshare", {"permissions_confirmed": True})
    assert market.update("akshare")["status"] == "confirmation_required"
    assert market.update("akshare", confirm=True)["rollback_available"] is True
    disabled = market.set_enabled("akshare", False)
    assert disabled["plugin"]["state"] == "DISABLED"
    enabled = market.set_enabled("akshare", True)
    assert enabled["plugin"]["mounted"] is True
