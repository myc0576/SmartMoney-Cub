from __future__ import annotations

from smartmoney_cub_harness.plugin_marketplace import MarketplaceStore
from smartmoney_cub_harness.plugins.catalog import catalog_entries, catalog_index
from smartmoney_cub_harness.plugins.registry import PluginStateStore
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

# The market is a projection of the curated catalog plus the one store that
# records what is actually installed. These tests anchor that shape: an entry
# must name a real upstream, and nothing may be reported installed until a
# health check has passed and the state store has a record.


def _market(tmp_path):
    store = PluginStateStore(tmp_path / "plugins" / "plugin_state.db")
    return MarketplaceStore(tmp_path, state_store=store)


def test_catalog_entries_name_a_real_upstream_and_install_way():
    entries = catalog_entries()
    assert entries
    for entry in entries:
        assert entry["repo"], entry["plugin_id"]
        assert entry["license"], entry["plugin_id"]
        assert entry["install"]["kind"] in ("pypi", "git", "builtin"), entry["plugin_id"]
        assert entry["manual_command"], entry["plugin_id"]
        assert entry["safety"] == SAFETY_DECLARATION


def test_pypi_and_git_entries_declare_a_health_module():
    for entry in catalog_entries():
        kind = entry["install"]["kind"]
        if kind in ("pypi", "git"):
            assert entry["install"].get("module"), entry["plugin_id"]


def test_view_reports_every_catalog_entry_as_available_when_nothing_is_installed(tmp_path):
    market = _market(tmp_path)
    view = market.view()
    assert view["schema"] == "smartmoney_cub_plugin_catalog.v2"
    assert view["safety"] == SAFETY_DECLARATION
    assert view["counts"]["total"] == len(catalog_entries())
    for item in view["catalog"]:
        assert item["installed"] is False
        assert item["state"] == "AVAILABLE"


def test_install_requires_permission_confirmation_before_it_records_anything(tmp_path):
    market = _market(tmp_path)
    refused = market.install("quantstats", {})
    assert refused["status"] == "permissions_required"
    # Nothing was written, so the market still reads as uninstalled.
    view = market.view()
    entry = next(item for item in view["catalog"] if item["plugin_id"] == "quantstats")
    assert entry["installed"] is False
    assert entry["state"] == "AVAILABLE"


def test_confirmed_install_records_into_the_single_source_of_truth(tmp_path):
    market = _market(tmp_path)
    result = market.install("quantstats", {"permissions_confirmed": True})
    assert result["status"] == "ok"

    # The store, not marketplace.json, is what makes this entry installed.
    store = PluginStateStore(tmp_path / "plugins" / "plugin_state.db")
    record = store.get("quantstats")
    assert record is not None
    assert record["manifest"]["capabilities"] == catalog_index()["quantstats"]["capabilities"]

    entry = next(item for item in market.view()["catalog"] if item["plugin_id"] == "quantstats")
    assert entry["installed"] is True
    assert entry["state"] == "ENABLED"


def test_no_half_installed_state_exists_anywhere_in_the_vocabulary(tmp_path):
    """A wizard that is abandoned must leave no state to observe."""
    market = _market(tmp_path)
    view = market.view()
    states = {item["state"] for item in view["catalog"]}
    assert "CONFIGURING" not in states
    assert states == {"AVAILABLE"}
    # And the market never invents a pending record of its own.
    assert not (tmp_path / "marketplace.json").exists() or not market._load().get("installed")


def test_enable_disable_round_trip_through_the_state_store(tmp_path):
    market = _market(tmp_path)
    market.install("akshare", {"permissions_confirmed": True})
    disabled = market.set_enabled("akshare", False)
    assert disabled["plugin"]["state"] == "DISABLED"
    assert disabled["plugin"]["mounted"] is False
    enabled = market.set_enabled("akshare", True)
    assert enabled["plugin"]["mounted"] is True
    entry = next(item for item in market.view()["catalog"] if item["plugin_id"] == "akshare")
    assert entry["state"] == "ENABLED"


def test_revoke_removes_the_record(tmp_path):
    market = _market(tmp_path)
    market.install("akshare", {"permissions_confirmed": True})
    market.revoke_record("akshare")
    store = PluginStateStore(tmp_path / "plugins" / "plugin_state.db")
    assert store.get("akshare")["state"] == "REVOKED"
    entry = next(item for item in market.view()["catalog"] if item["plugin_id"] == "akshare")
    assert entry["installed"] is False


def test_unknown_plugin_id_is_refused(tmp_path):
    market = _market(tmp_path)
    try:
        market.install("not-in-the-catalog", {"permissions_confirmed": True})
    except KeyError:
        return
    raise AssertionError("an id outside the catalog must be refused")
