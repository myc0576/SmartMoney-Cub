from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from smartmoney_cub_harness.plugin_installer import PluginInstaller
from smartmoney_cub_harness.plugin_marketplace import MarketplaceStore
from smartmoney_cub_harness.plugins.catalog import catalog_index
from smartmoney_cub_harness.plugins.registry import PluginStateStore


LAUNCHER = Path(__file__).resolve().parents[1] / "npm" / "bin" / "smartmoney-cub.js"


def _market(tmp_path: Path) -> MarketplaceStore:
    store = PluginStateStore(tmp_path / "plugins" / "plugin_state.db")
    return MarketplaceStore(tmp_path, state_store=store)


def test_marketplace_distinguishes_adapter_callability_from_companion_install(tmp_path: Path) -> None:
    market = _market(tmp_path)
    companion = catalog_index()["tradingagents"]

    record = market.install_record(
        companion,
        health={"healthy": True, "runtime_integrated": False},
    )

    assert record["installed"] is True
    assert record["active"] is False
    assert record["callable"] is False
    assert record["runtime_integrated"] is False
    assert record["state"] == "INSTALLED"
    assert record["callable_reason"] == "companion_only_no_runtime_adapter"

    item = next(row for row in market.view()["catalog"] if row["plugin_id"] == "tradingagents")
    assert item["installed"] is True
    assert item["active"] is False
    assert item["callable"] is False
    assert item["enabled"] is False
    assert item["mounted"] is False


def test_marketplace_keeps_builtin_adapter_callable(tmp_path: Path) -> None:
    market = _market(tmp_path)
    adapter = catalog_index()["tencent-quotes"]

    record = market.install_record(
        adapter,
        health={"healthy": True, "runtime_integrated": True},
    )

    assert record["installed"] is True
    assert record["active"] is True
    assert record["callable"] is True
    assert record["runtime_integrated"] is True
    assert record["state"] == "ENABLED"


def test_marketplace_keeps_failed_health_visible(tmp_path: Path) -> None:
    market = _market(tmp_path)

    record = market.install_record(
        catalog_index()["tencent-quotes"],
        health={"healthy": False, "runtime_integrated": True},
    )

    assert record["state"] == "ERROR"
    assert record["installed"] is True
    assert record["active"] is False
    assert record["callable"] is False
    assert record["health"] == "error"


def test_marketplace_cannot_enable_companion_without_runtime_adapter(tmp_path: Path) -> None:
    market = _market(tmp_path)
    market.install_record(
        catalog_index()["tradingagents"],
        health={"healthy": True, "runtime_integrated": False},
    )

    result = market.set_enabled("tradingagents", True)

    assert result["status"] == "not_callable"
    assert result["plugin"]["active"] is False
    assert result["plugin"]["callable"] is False
    assert result["plugin"]["mounted"] is False


def test_installer_rejects_plugin_root_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "plugins").symlink_to(outside, target_is_directory=True)
    installer = PluginInstaller(tmp_path)

    with pytest.raises(PermissionError, match="symlink"):
        installer._ensure_within_root(installer.venv_dir)


def test_installer_rejects_malformed_health_probe_module(tmp_path: Path, monkeypatch) -> None:
    installer = PluginInstaller(tmp_path)
    installer.venv_dir.mkdir(parents=True)
    python_bin = installer._venv_python()
    python_bin.parent.mkdir(parents=True, exist_ok=True)
    python_bin.write_text("toy", encoding="utf-8")
    called = False

    def unexpected_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("malformed module must be rejected before subprocess execution")

    monkeypatch.setattr(subprocess, "run", unexpected_run)
    entry = {"install": {"kind": "pypi", "module": "safe;__import__('os')"}}

    result = installer.probe(entry)

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert "module" in result["detail"]
    assert called is False


def test_installer_uses_argv_and_keeps_install_target_inside_plugin_root(tmp_path: Path, monkeypatch) -> None:
    installer = PluginInstaller(tmp_path)
    python_bin = installer.venv_dir / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("toy", encoding="utf-8")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command: list[str], **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(installer, "_ensure_venv", lambda: installer._ensure_within_root(python_bin))
    monkeypatch.setattr("smartmoney_cub_harness.plugin_installer.subprocess.run", fake_run)
    monkeypatch.setattr("smartmoney_cub_harness.plugin_installer.shutil.which", lambda _: None)
    monkeypatch.setattr(
        installer,
        "probe",
        lambda entry, timeout=60: {"status": "ok", "healthy": True, "runtime_integrated": True},
    )

    result = installer.install(catalog_index()["quantstats"], permissions_confirmed=True)

    assert result["status"] == "ok"
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == [str(python_bin), "-m", "pip", "install", "quantstats"]
    assert kwargs["shell"] is False
    assert Path(command[0]).resolve().is_relative_to(installer.plugins_dir.resolve())


def _make_fake_venv(tmp_path: Path, body: str, *, cli: bool = True) -> tuple[Path, Path]:
    home = tmp_path / "smcub-home"
    bin_dir = home / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    python = bin_dir / "python"
    python.write_text(body, encoding="utf-8")
    python.chmod(0o755)
    if cli:
        smcub = bin_dir / "smcub"
        smcub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        smcub.chmod(0o755)
    return home, python


def test_npm_launcher_forwards_arguments_and_exit_code(tmp_path: Path) -> None:
    log_path = tmp_path / "args.log"
    body = f'''#!/bin/sh
printf '%s\n' "$@" > "{log_path}"
exit 23
'''
    home, _ = _make_fake_venv(tmp_path, body)
    env = {**os.environ, "SMCUB_HOME": str(home)}

    result = subprocess.run(
        ["node", str(LAUNCHER), "plugin", "list", "--label", "value with spaces"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 23
    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "-m",
        "smartmoney_cub_harness.cli",
        "plugin",
        "list",
        "--label",
        "value with spaces",
    ]


def test_npm_launcher_reports_missing_installed_cli_without_pypi_fallback(tmp_path: Path) -> None:
    marker = tmp_path / "unexpected-python-use"
    body = f'''#!/bin/sh
printf used > "{marker}"
exit 0
'''
    home, python = _make_fake_venv(tmp_path, body, cli=False)
    env = {**os.environ, "SMCUB_HOME": str(home)}

    result = subprocess.run(
        ["node", str(LAUNCHER), "workbench"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing the installed CLI" in result.stderr
    assert "PyPI" in result.stderr
    assert not marker.exists()
    assert python.exists()


def test_npm_launcher_forwards_termination_signal_and_exit_status(tmp_path: Path) -> None:
    started = tmp_path / "started"
    body = f'''#!/bin/sh
touch "{started}"
trap 'exit 143' TERM INT
while :; do sleep 1; done
'''
    home, _ = _make_fake_venv(tmp_path, body)
    env = {**os.environ, "SMCUB_HOME": str(home)}
    process = subprocess.Popen(
        ["node", str(LAUNCHER), "workbench"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 3
        while not started.exists() and time.time() < deadline:
            time.sleep(0.02)
        assert started.exists()
        process.send_signal(signal.SIGTERM)
        return_code = process.wait(timeout=3)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)

    assert return_code == 143
