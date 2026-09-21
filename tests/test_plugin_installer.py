from __future__ import annotations

import subprocess
from pathlib import Path
import pytest

from smartmoney_cub_harness.plugin_installer import PluginInstaller
from smartmoney_cub_harness.plugins.catalog import catalog_index
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_installer_refuses_unknown_plugin_id(tmp_path: Path) -> None:
    installer = PluginInstaller(tmp_path)
    fake_entry = {"plugin_id": "malicious-plugin", "install": {"kind": "pypi", "package": "foo"}}
    res = installer.install(fake_entry, permissions_confirmed=True)
    assert res["status"] == "error"
    assert res["error"] == "not_in_whitelist"
    assert res["steps"][0]["step"] == "permissions"
    assert res["steps"][0]["status"] == "refused"
    assert res["safety"] == SAFETY_DECLARATION


def test_installer_refuses_when_permissions_not_confirmed(tmp_path: Path) -> None:
    installer = PluginInstaller(tmp_path)
    entry = catalog_index()["tencent-quotes"]
    res = installer.install(entry, permissions_confirmed=False)
    assert res["status"] == "error"
    assert res["error"] == "permissions_not_confirmed"
    assert res["steps"][0]["step"] == "permissions"
    assert res["steps"][0]["status"] == "failed"
    assert "只读权限" in res["steps"][0]["detail"]
    assert res["safety"] == SAFETY_DECLARATION


def test_installer_refuses_high_execution_risk_vnpy(tmp_path: Path) -> None:
    installer = PluginInstaller(tmp_path)
    entry = catalog_index()["vnpy"]
    res = installer.install(entry, permissions_confirmed=True)
    assert res["status"] == "error"
    assert res["error"] == "execution_risk_high_refused"
    assert res["steps"][0]["step"] == "permissions"
    assert res["steps"][0]["status"] == "refused"
    assert "永不安装" in res["steps"][0]["detail"]


def test_installer_builtin_skips_download_and_verifies_health(tmp_path: Path) -> None:
    installer = PluginInstaller(tmp_path)
    entry = catalog_index()["multi-agent-trade-review"]
    res = installer.install(entry, permissions_confirmed=True)
    assert res["status"] == "ok"
    assert len(res["steps"]) == 3
    assert res["steps"][0]["step"] == "permissions"
    assert res["steps"][0]["status"] == "ok"
    assert res["steps"][1]["step"] == "fetch"
    assert res["steps"][1]["status"] == "skipped"
    assert res["steps"][2]["step"] == "health"
    assert res["steps"][2]["status"] == "ok"
    assert res["health"]["healthy"] is True


def test_installer_path_traversal_refused(tmp_path: Path) -> None:
    installer = PluginInstaller(tmp_path)
    outside = tmp_path.parent / "outside_dir"
    with pytest.raises(PermissionError, match="Path outside plugin root"):
        installer._ensure_within_root(outside)


def test_installer_health_probe_failure_reported(tmp_path: Path, monkeypatch) -> None:
    installer = PluginInstaller(tmp_path)
    entry = catalog_index()["akshare"]

    # Mock subprocess.run for pip install to succeed
    def fake_run(cmd, *args, **kwargs):
        class FakeRes:
            returncode = 0
            stdout = "Successfully installed"
            stderr = ""
        return FakeRes()

    monkeypatch.setattr(subprocess, "run", fake_run)

    # But mock probe to fail
    def fake_probe(e, timeout=60):
        return {
            "status": "error",
            "healthy": False,
            "detail": "import failed: No module named akshare",
            "safety": SAFETY_DECLARATION,
        }

    monkeypatch.setattr(installer, "probe", fake_probe)

    res = installer.install(entry, permissions_confirmed=True)
    assert res["status"] == "error"
    assert res["error"] == "health_check_failed"
    assert res["steps"][-1]["step"] == "health"
    assert res["steps"][-1]["status"] == "failed"
    assert "No module named akshare" in res["steps"][-1]["detail"]


def test_installer_pypi_success_path(tmp_path: Path, monkeypatch) -> None:
    installer = PluginInstaller(tmp_path)
    entry = catalog_index()["quantstats"]

    def fake_run(cmd, *args, **kwargs):
        class FakeRes:
            returncode = 0
            stdout = "Successfully installed"
            stderr = ""
        return FakeRes()

    monkeypatch.setattr(subprocess, "run", fake_run)

    def fake_probe(e, timeout=60):
        return {
            "status": "ok",
            "healthy": True,
            "detail": "module quantstats imported successfully",
            "safety": SAFETY_DECLARATION,
        }

    monkeypatch.setattr(installer, "probe", fake_probe)

    res = installer.install(entry, permissions_confirmed=True)
    assert res["status"] == "ok"
    assert res["steps"][0]["step"] == "permissions"
    assert res["steps"][0]["status"] == "ok"
    assert res["steps"][1]["step"] == "fetch"
    assert res["steps"][1]["status"] == "ok"
    assert res["steps"][2]["step"] == "health"
    assert res["steps"][2]["status"] == "ok"
    assert res["health"]["healthy"] is True


def test_installer_uninstall_cleans_resources(tmp_path: Path) -> None:
    installer = PluginInstaller(tmp_path)
    git_dir = installer.sources_dir / "tradingagents"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "README.md").write_text("dummy", encoding="utf-8")
    assert git_dir.exists()

    res = installer.uninstall("tradingagents")
    assert res["status"] == "ok"
    assert not git_dir.exists()

