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


def test_installer_refuses_removed_vnpy(tmp_path: Path) -> None:
    installer = PluginInstaller(tmp_path)
    entry = {"plugin_id": "vnpy"}
    res = installer.install(entry, permissions_confirmed=True)
    assert res["status"] == "error"
    assert res["error"] == "not_in_whitelist"
    assert res["steps"][0]["step"] == "permissions"
    assert res["steps"][0]["status"] == "refused"


def test_managed_credentials_required_and_external_credentials_rejected(tmp_path: Path, monkeypatch) -> None:
    installer = PluginInstaller(tmp_path)
    def no_download(*args, **kwargs):
        raise AssertionError("credential validation must happen before any download")
    monkeypatch.setattr(subprocess, "run", no_download)
    result = installer.install(catalog_index()["fred"], permissions_confirmed=True)
    assert result["error"] == "credentials_required"
    result = installer.install(catalog_index()["tradingagents"], permissions_confirmed=True,
                               credentials={"API_KEY": "toy-secret"})
    assert result["error"] == "external_credentials_not_accepted"
    assert not (tmp_path / "credentials.json").exists()


def test_failed_install_does_not_persist_credentials(tmp_path: Path, monkeypatch) -> None:
    installer = PluginInstaller(tmp_path)
    monkeypatch.setattr(installer, "_ensure_venv", lambda: tmp_path / "python")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess([], 1, "", "toy failure"))
    result = installer.install(catalog_index()["fred"], permissions_confirmed=True,
                               credentials={"FRED_API_KEY": "toy-secret"})
    assert result["status"] == "error"
    assert not (tmp_path / "credentials.json").exists()


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


def test_source_only_companion_probe_does_not_import_external_code(tmp_path: Path, monkeypatch) -> None:
    installer = PluginInstaller(tmp_path)
    entry = catalog_index()["tradingagents"]
    source = installer.sources_dir / "tradingagents"
    (source / ".git").mkdir(parents=True)
    def no_execution(*args, **kwargs):
        raise AssertionError("companion source must not execute")
    monkeypatch.setattr(subprocess, "run", no_execution)
    result = installer.probe(entry)
    assert result["healthy"] is True
    assert result["runtime_integrated"] is False


def test_existing_source_checkout_is_not_destroyed_by_reinstallation(tmp_path: Path, monkeypatch) -> None:
    installer = PluginInstaller(tmp_path)
    entry = catalog_index()["tradingagents"]
    source = installer.sources_dir / "tradingagents"
    (source / ".git").mkdir(parents=True)
    note = source / "user-note.txt"
    note.write_text("toy user work")
    def no_download(*args, **kwargs):
        raise AssertionError("existing source must not be replaced")
    monkeypatch.setattr(subprocess, "run", no_download)
    result = installer.install(entry, permissions_confirmed=True)
    assert result["status"] == "ok"
    assert note.read_text() == "toy user work"
