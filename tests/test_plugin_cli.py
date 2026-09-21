from __future__ import annotations

import json
from pathlib import Path

from smartmoney_cub_harness.cli import main
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

TOY_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "examples" / "toy_plugin"
TOY_MANIFEST = TOY_PLUGIN_DIR / "plugin.json"

DECISION_TIME = "2026-09-10T15:00:00+08:00"
AVAILABLE_AT = "2026-09-10T14:00:00+08:00"


def _run(capsys, *argv: str) -> dict:
    code = main(list(argv))
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    payload["_exit_code"] = code
    return payload


def test_cli_plugin_inspect_and_catalog(capsys) -> None:
    inspected = _run(capsys, "plugin", "inspect", str(TOY_MANIFEST))
    assert inspected["_exit_code"] == 0
    assert inspected["status"] == "ok"
    assert inspected["safety"] == SAFETY_DECLARATION

    catalog = _run(capsys, "plugin", "catalog")
    assert catalog["_exit_code"] == 0
    assert catalog["schema"] == "smartmoney_cub_plugin_catalog.v2"
    assert catalog["entries"]


def test_cli_plugin_inspect_rejects_unsafe_manifest(capsys, tmp_path: Path) -> None:
    payload = json.loads(TOY_MANIFEST.read_text(encoding="utf-8"))
    payload["capabilities"] = ["order_execution"]
    path = tmp_path / "plugin.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run(capsys, "plugin", "inspect", str(path))
    assert result["_exit_code"] == 2
    assert result["status"] == "invalid"
    assert any("forbidden_capability" in error for error in result["validation"]["errors"])


def test_cli_plugin_list_doctor_enable_disable_run(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "plugins.db")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"symbol": "600111", "return_pct": -8.5}), encoding="utf-8")

    listing = _run(capsys, "plugin", "list", "--plugin-dir", str(TOY_PLUGIN_DIR), "--state-db", db)
    assert listing["_exit_code"] == 0
    assert listing["plugins"][0]["plugin_id"] == "toy.review-tagger"

    doctor = _run(capsys, "plugin", "doctor", "--plugin-dir", str(TOY_PLUGIN_DIR), "--state-db", db)
    assert doctor["_exit_code"] == 0
    assert doctor["sandbox_verified"] is False

    disabled = _run(capsys, "plugin", "disable", "toy.review-tagger", "--state-db", db)
    assert disabled["_exit_code"] == 0
    assert disabled["plugin"]["state"] == "DISABLED"

    refused = _run(
        capsys,
        "plugin",
        "run",
        "toy.review-tagger",
        "--request",
        str(request_path),
        "--decision-time",
        DECISION_TIME,
        "--available-at",
        AVAILABLE_AT,
        "--state-db",
        db,
    )
    assert refused["_exit_code"] == 2
    assert refused["status"] == "not_enabled"

    enabled = _run(
        capsys, "plugin", "enable", "toy.review-tagger", "--plugin-dir", str(TOY_PLUGIN_DIR), "--state-db", db
    )
    assert enabled["plugin"]["state"] == "ACTIVE"

    executed = _run(
        capsys,
        "plugin",
        "run",
        "toy.review-tagger",
        "--request",
        str(request_path),
        "--decision-time",
        DECISION_TIME,
        "--available-at",
        AVAILABLE_AT,
        "--state-db",
        db,
    )
    assert executed["_exit_code"] == 0
    assert executed["envelope"]["review_only"] is True
    assert executed["envelope"]["safety"] == SAFETY_DECLARATION


def test_cli_plugin_run_rejects_future_data(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "plugins.db")
    result = _run(
        capsys,
        "plugin",
        "run",
        "toy.review-tagger",
        "--decision-time",
        DECISION_TIME,
        "--available-at",
        "2026-09-11T15:00:00+08:00",
        "--plugin-dir",
        str(TOY_PLUGIN_DIR),
        "--state-db",
        db,
    )
    assert result["_exit_code"] == 2
    assert result["error"]["code"] == "EvidenceEnvelopeError"


def test_cli_profile_show_and_dump(capsys, tmp_path: Path) -> None:
    shown = _run(capsys, "profile", "show", "default-offline")
    assert shown["_exit_code"] == 0
    assert shown["allow_network"] is False

    output = tmp_path / "profiles.json"
    dumped = _run(capsys, "profile", "dump", "--output", str(output))
    assert dumped["_exit_code"] == 0
    assert output.exists()
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert set(stored["profiles"]) == {"default-offline", "a-share-review", "research", "ai-optional"}
    assert stored["safety"] == SAFETY_DECLARATION


def test_cli_plugin_remove_keeps_audit_trail(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "plugins.db")
    _run(capsys, "plugin", "doctor", "--plugin-dir", str(TOY_PLUGIN_DIR), "--state-db", db)
    removed = _run(capsys, "plugin", "remove", "toy.review-tagger", "--state-db", db)
    assert removed["_exit_code"] == 0
    assert removed["state"] == "REVOKED"
    logs = _run(capsys, "plugin", "logs", "toy.review-tagger", "--state-db", db)
    assert logs["events"]
    assert logs["state"]["state"] == "REVOKED"


def test_cli_plugin_install_refuses_remote_sources(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "plugins.db")
    for source in (
        "https://github.com/akfamily/akshare",
        "git+https://github.com/foo/bar",
        "http://example.com/plugin.zip",
    ):
        result = _run(capsys, "plugin", "install", source, "--state-db", db)
        assert result["_exit_code"] == 2
        assert result["status"] == "not_found"
        assert result["error"]["code"] == "path_missing"


def test_cli_plugin_install_registers_local_plugin_disabled(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "plugins.db")
    installed = _run(capsys, "plugin", "install", str(TOY_PLUGIN_DIR), "--state-db", db)
    assert installed["_exit_code"] == 0
    assert installed["downloaded"] is False
    assert installed["installed"][0]["state"] == "DISABLED"

    refused = _run(
        capsys,
        "plugin",
        "run",
        "toy.review-tagger",
        "--decision-time",
        DECISION_TIME,
        "--available-at",
        AVAILABLE_AT,
        "--state-db",
        db,
    )
    assert refused["status"] == "not_enabled"


def test_cli_plugin_install_reports_missing_path(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "plugins.db")
    result = _run(capsys, "plugin", "install", str(tmp_path / "nope"), "--state-db", db)
    assert result["_exit_code"] == 2
    assert result["status"] == "not_found"
    assert result["error"]["code"] == "path_missing"


def test_cli_plugin_run_records_evidence_into_workspace(capsys, tmp_path: Path) -> None:
    plugin_db = str(tmp_path / "plugins.db")
    workspace_db = str(tmp_path / "workspace.db")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"symbol": "600111", "return_pct": -9.0}), encoding="utf-8")

    _run(capsys, "plugin", "doctor", "--plugin-dir", str(TOY_PLUGIN_DIR), "--state-db", plugin_db)
    executed = _run(
        capsys,
        "plugin",
        "run",
        "toy.review-tagger",
        "--request",
        str(request_path),
        "--decision-time",
        DECISION_TIME,
        "--available-at",
        AVAILABLE_AT,
        "--workspace-db",
        workspace_db,
        "--state-db",
        plugin_db,
    )
    assert executed["_exit_code"] == 0
    assert executed["recorded_evidence"]["status"] == "ok"
    assert executed["recorded_evidence"]["review_only"] is True

    summary = _run(capsys, "workspace", "summary", "--db", workspace_db)
    assert summary["summary"]["evidence_count"] == 1

