from __future__ import annotations

import subprocess
from pathlib import Path

from smartmoney_cub_harness.plugin_cli import plugin_list
from smartmoney_cub_harness.plugin_marketplace import MarketplaceStore
from smartmoney_cub_harness.plugins.catalog import catalog_index
from smartmoney_cub_harness.plugins.catalog_contract import STATE_ENABLED
from smartmoney_cub_harness.plugins.registry import PluginStateStore
from smartmoney_cub_harness.workbench.server import WorkbenchService


def test_permission_not_confirmed_does_not_write_state(tmp_path: Path) -> None:
    service = WorkbenchService(tmp_path)
    state_db = tmp_path / "plugins" / "plugin_state.db"
    store = PluginStateStore(state_db)
    service.marketplace._explicit_state_store = store

    payload = {
        "plugin_id": "akshare",
        "permissions_confirmed": False,
    }
    res = service.install_plugin(payload)
    assert res["status"] == "error"
    assert res["error"] == "permissions_not_confirmed"

    # No record in PluginStateStore
    assert store.get("akshare") is None

    # No record in marketplace.view() installed list
    view = service.marketplace.view()
    ak_item = next(item for item in view["catalog"] if item["plugin_id"] == "akshare")
    assert ak_item["installed"] is False
    assert ak_item["state"] == "AVAILABLE"
    assert view["counts"]["installed"] == 0


def test_health_check_failure_does_not_write_installed_state(tmp_path: Path, monkeypatch) -> None:
    service = WorkbenchService(tmp_path)
    state_db = tmp_path / "plugins" / "plugin_state.db"
    store = PluginStateStore(state_db)
    service.marketplace._explicit_state_store = store

    # Mock subprocess run to succeed during pip
    def fake_run(cmd, *args, **kwargs):
        class FakeRes:
            returncode = 0
            stdout = ""
            stderr = ""
        return FakeRes()

    monkeypatch.setattr(subprocess, "run", fake_run)

    # But mock probe to fail
    from smartmoney_cub_harness.plugin_installer import PluginInstaller
    def fake_probe(self, entry, timeout=60):
        return {"status": "error", "healthy": False, "detail": "probe import failed"}

    monkeypatch.setattr(PluginInstaller, "probe", fake_probe)

    payload = {
        "plugin_id": "quantstats",
        "permissions_confirmed": True,
    }
    res = service.install_plugin(payload)
    assert res["status"] == "error"
    assert res["error"] == "health_check_failed"

    # Must not write to store
    assert store.get("quantstats") is None
    view = service.marketplace.view()
    qs_item = next(item for item in view["catalog"] if item["plugin_id"] == "quantstats")
    assert qs_item["installed"] is False
    assert qs_item["state"] == "AVAILABLE"


def test_successful_install_visible_in_plugin_list_and_marketplace(tmp_path: Path) -> None:
    service = WorkbenchService(tmp_path)
    state_db = tmp_path / "plugins" / "plugin_state.db"
    store = PluginStateStore(state_db)
    service.marketplace._explicit_state_store = store

    # Builtin install succeeds without mocks
    payload = {
        "plugin_id": "tencent-quotes",
        "permissions_confirmed": True,
    }
    res = service.install_plugin(payload)
    assert res["status"] == "ok"
    assert res["plugin"]["plugin_id"] == "tencent-quotes"
    assert res["plugin"]["installed"] is True
    assert res["plugin"]["state"] == STATE_ENABLED

    # Verify plugin_list() can see tencent-quotes
    listing = plugin_list(state_db=str(state_db))
    pids = [p["plugin_id"] for p in listing["plugins"]]
    assert "tencent-quotes" in pids

    # Verify marketplace view has state ENABLED and installed True
    view = service.marketplace.view()
    tq_item = next(item for item in view["catalog"] if item["plugin_id"] == "tencent-quotes")
    assert tq_item["installed"] is True
    assert tq_item["state"] == STATE_ENABLED
    assert tq_item["enabled"] is True
    assert tq_item["mounted"] is True
    assert view["counts"]["installed"] == 1


def test_interrupted_or_cancelled_wizard_leaves_no_residual_state(tmp_path: Path) -> None:
    service = WorkbenchService(tmp_path)
    state_db = tmp_path / "plugins" / "plugin_state.db"
    store = PluginStateStore(state_db)
    service.marketplace._explicit_state_store = store

    # When user cancels or never calls install_plugin, no CONFIGURING fake state is saved
    view = service.marketplace.view()
    assert view["counts"]["installed"] == 0
    assert all(item["state"] == "AVAILABLE" for item in view["catalog"])
    assert store.list_all() == []

