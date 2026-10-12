from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from onchain_helpers import toy_snapshot
from smartmoney_cub_harness.cli import main
from smartmoney_cub_harness.evidence_pack import replay_evidence_pack
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _sealed_manifest(root: Path, raw: bytes) -> None:
    root.mkdir(exist_ok=True)
    (root / "evidence_pack.json").write_bytes(raw)
    (root / "evidence_pack.sha256").write_text(hashlib.sha256(raw).hexdigest(), encoding="ascii")


def test_import_cli_reports_missing_snapshot_without_creating_output(tmp_path, capsys):
    output = tmp_path / "out"
    assert main(["build-onchain-evidence-pack", str(output), "--snapshot", str(tmp_path / "missing.json")]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["evidence_status"] == "invalid"
    assert result["safety"] == SAFETY_DECLARATION
    assert not output.exists()


def test_dispatch_rejects_duplicate_schema_in_sealed_json(tmp_path):
    _sealed_manifest(tmp_path, b'{"schema":"smartmoney_cub_evidence_pack.v1","schema":"unknown"}')
    report = replay_evidence_pack(tmp_path)
    assert report["evidence_status"] != "verified"
    assert "invalid_pack:malformed_json" in report["result_mismatches"]


@pytest.mark.parametrize("schema", [None, [], {}, 1, True, "smartmoney_cub_onchain_evidence_pack.v2"])
def test_dispatch_rejects_unknown_or_nonstring_version(tmp_path, schema):
    _sealed_manifest(tmp_path, json.dumps({"schema": schema}).encode())
    result = replay_evidence_pack(tmp_path)
    assert result["evidence_status"] != "verified"


def test_replay_report_symlink_is_not_followed(tmp_path):
    pack = tmp_path / "pack"
    _sealed_manifest(pack, b'{"schema":"unknown"}')
    sentinel = tmp_path / "sentinel.json"
    sentinel.write_text("unchanged", encoding="utf-8")
    try:
        (pack / "replay_report.json").symlink_to(sentinel)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    result = replay_evidence_pack(pack)
    assert result["evidence_status"] != "verified"
    assert sentinel.read_text(encoding="utf-8") == "unchanged"


def test_import_and_existing_replay_cli_are_offline_and_deterministic(tmp_path, capsys, monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("offline CLI attempted network access")

    monkeypatch.setattr(socket, "socket", deny_network)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(toy_snapshot()), encoding="utf-8")
    output = tmp_path / "pack"
    assert main(["build-onchain-evidence-pack", str(output), "--snapshot", str(snapshot)]) == 0
    pack = json.loads(capsys.readouterr().out)
    assert pack["schema"] == "smartmoney_cub_onchain_evidence_pack.v1"
    assert main(["replay-evidence-pack", str(output)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert [c["verdict"] for c in first["claims"]] == [
        "supported", "contradicted", "supported", "supported", "insufficient_evidence"]
    assert first["safety"] == SAFETY_DECLARATION
    assert main(["replay-evidence-pack", str(output)]) == 0
    assert json.loads(capsys.readouterr().out) == first
    before = (output / "evidence_pack.json").read_bytes()
    assert main(["build-onchain-evidence-pack", str(output), "--snapshot", str(snapshot)]) == 2
    assert json.loads(capsys.readouterr().out)["evidence_status"] == "invalid"
    assert (output / "evidence_pack.json").read_bytes() == before
    (output / "receipt.json").unlink()
    assert main(["replay-evidence-pack", str(output)]) == 2
    invalid = json.loads(capsys.readouterr().out)
    assert invalid["evidence_status"] == "invalid" and invalid["claims"] == []


@pytest.mark.parametrize("raw", [
    "[]", '{"schema":"unknown"}',
    '{"schema":"smartmoney_cub_onchain_snapshot.v1","schema":"unknown"}',
    '{"chain_id":NaN}',
])
def test_import_rejects_bad_json_and_schema_before_writing(tmp_path, capsys, raw):
    source = tmp_path / "input.json"
    source.write_text(raw, encoding="utf-8")
    output = tmp_path / "pack"
    assert main(["build-onchain-evidence-pack", str(output), "--snapshot", str(source)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["errors"]
    assert not output.exists()


def test_module_cli_smoke_with_network_blocked(tmp_path):
    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps(toy_snapshot()), encoding="utf-8")
    pack = tmp_path / "pack"
    runner = (
        "import runpy,sys; "
        "sys.addaudithook(lambda event,args: (_ for _ in ()).throw(AssertionError('network forbidden')) "
        "if event.startswith('socket.') else None); "
        "sys.argv=['smcub',*sys.argv[1:]]; "
        "runpy.run_module('smartmoney_cub_harness.cli',run_name='__main__')"
    )
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"), PYTHONUTF8="1")
    for args in [
        ["build-onchain-evidence-pack", str(pack), "--snapshot", str(source)],
        ["replay-evidence-pack", str(pack)],
    ]:
        result = subprocess.run([sys.executable, "-c", runner, *args], capture_output=True, text=True, env=env)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["safety"] == SAFETY_DECLARATION


@pytest.mark.parametrize("failure", ["seal", "json", "version"])
def test_dispatch_failure_does_not_write_through_report_hardlink(tmp_path, failure):
    pack = tmp_path / "pack"
    _sealed_manifest(pack, b'{"schema":"unknown"}')
    if failure == "seal":
        (pack / "evidence_pack.sha256").write_text("0" * 64, encoding="ascii")
    elif failure == "json":
        raw = b'{"schema":'
        _sealed_manifest(pack, raw)
    sentinel = tmp_path / "external.txt"
    sentinel.write_text("must remain unchanged", encoding="utf-8")
    try:
        (pack / "replay_report.json").hardlink_to(sentinel)
    except OSError as exc:
        pytest.skip(f"hardlink creation unavailable: {exc}")
    assert replay_evidence_pack(pack)["evidence_status"] != "verified"
    assert sentinel.read_text(encoding="utf-8") == "must remain unchanged"


def test_dispatch_failure_with_report_directory_returns_error_without_traceback(tmp_path, capsys):
    _sealed_manifest(tmp_path, b'{"schema":"unknown"}')
    (tmp_path / "replay_report.json").mkdir()
    assert main(["replay-evidence-pack", str(tmp_path)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["evidence_status"] != "verified"
    assert (tmp_path / "replay_report.json").is_dir()


def test_replay_nonexistent_directory_returns_error_without_creating_it(tmp_path, capsys):
    root = tmp_path / "missing"
    assert main(["replay-evidence-pack", str(root)]) == 2
    assert json.loads(capsys.readouterr().out)["evidence_status"] != "verified"
    assert not root.exists()
