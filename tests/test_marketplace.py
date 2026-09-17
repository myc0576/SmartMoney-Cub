from __future__ import annotations

from smartmoney_cub_harness.plugin_marketplace import MarketplaceStore, official_catalog
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_official_catalog_contains_complete_review_chain():
    entries = official_catalog()
    assert len(entries) == 20
    assert {entry["category"] for entry in entries} == {"数据", "绩效与风险", "研究与评估", "Agent"}
    assert all(entry["source"] == "smartmoney-cub/official-curated" for entry in entries)
    assert all(entry["safety"] == SAFETY_DECLARATION for entry in entries)


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
