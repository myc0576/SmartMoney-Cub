from __future__ import annotations

from smartmoney_cub_harness.plugin_marketplace import MarketplaceStore, official_catalog
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_official_catalog_contains_complete_review_chain():
    entries = official_catalog()
    assert len(entries) == 21
    assert {entry["category"] for entry in entries} == {"数据", "绩效与风险", "研究与评估", "Agent"}
    assert all(entry["source"] == "smartmoney-cub/official-curated" for entry in entries)
    assert all(entry["safety"] == SAFETY_DECLARATION for entry in entries)


def test_typesafe_skill_entry_provenance_and_safety():
    entries = official_catalog()
    skill_entries = [e for e in entries if e["plugin_id"] == "typesafe-ai-skills"]
    assert len(skill_entries) == 1
    entry = skill_entries[0]
    assert entry["kind"] == "skill"
    assert entry["source_repo"] == "https://github.com/typesafe-ai/skills"
    assert entry["source_commit"] == "65a39f393687675ce170e6094757de20370365b9"
    assert entry["license"] == "MIT"
    assert entry["requires_credentials"] is True
    assert entry["safety"] == SAFETY_DECLARATION
    assert entry["provenance"] == {
        "skills/typesafe-ai/SKILL.md": "71ea90d7906c6554c4f4c460ef7361b2d26f59116ccdae986dc6d997b9389f52",
        "skills/typesafe-ai/LICENSE": "835f233f1d6ed84a9b9a351aba0689b47644a4137d6316911fc7957bde523b02",
    }
    forbidden_execution = ("order", "cancel", "trade", "broker", "account", "execution")
    for item in entries:
        for perm in item.get("permissions", []):
            lowered = perm.lower()
            assert not any(fragment in lowered for fragment in forbidden_execution), (
                f"Entry {item['plugin_id']} declares execution permission: {perm}"
            )


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
