from __future__ import annotations

import json
from pathlib import Path

from smartmoney_cub_harness.cli import main
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

DECISION_TIME = "2026-09-10T15:00:00+08:00"
AVAILABLE_AT = "2026-09-10T14:00:00+08:00"


def _run(capsys, *argv: str) -> dict:
    code = main(list(argv))
    payload = json.loads(capsys.readouterr().out)
    payload["_exit_code"] = code
    return payload


def _case_payload(case_id: str = "C1") -> dict:
    return {
        "case_id": case_id,
        "symbol": "600111",
        "action": "ALERT",
        "decision_time": DECISION_TIME,
        "thesis": "mainline leader",
        "invalidation_price": 9.5,
        "time_stop": "D1 close",
        "give_up_conditions": ["pattern failed"],
        "data_source": "toy_source",
        "available_at": AVAILABLE_AT,
        "data_quality_flag": "ok",
        "regime": "生长",
        "tags": ["mainline"],
    }


def test_cli_workspace_add_show_and_list(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "workspace.db")
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(_case_payload(), ensure_ascii=False), encoding="utf-8")

    added = _run(capsys, "workspace", "add-case", str(case_path), "--db", db)
    assert added["_exit_code"] == 0
    assert added["case"]["case_id"] == "C1"
    assert added["case"]["safety"] == SAFETY_DECLARATION

    shown = _run(capsys, "workspace", "show-case", "C1", "--db", db)
    assert shown["_exit_code"] == 0
    assert shown["case"]["symbol"] == "600111"

    listed = _run(capsys, "workspace", "list-cases", "--db", db, "--symbol", "600111")
    assert listed["count"] == 1


def test_cli_workspace_rejects_incomplete_observation(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "workspace.db")
    case_path = tmp_path / "bad.json"
    case_path.write_text(
        json.dumps({"case_id": "C2", "symbol": "1", "action": "ALERT", "decision_time": DECISION_TIME}),
        encoding="utf-8",
    )
    result = _run(capsys, "workspace", "add-case", str(case_path), "--db", db)
    assert result["_exit_code"] == 2
    assert result["error"]["code"] == "ValueError"
    assert "invalidation_price" in result["error"]["message"]


def test_cli_workspace_blocks_future_leakage(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "workspace.db")
    payload = _case_payload("C3")
    payload["available_at"] = "2026-09-11T15:00:00+08:00"
    case_path = tmp_path / "leak.json"
    case_path.write_text(json.dumps(payload), encoding="utf-8")
    result = _run(capsys, "workspace", "add-case", str(case_path), "--db", db)
    assert result["_exit_code"] == 2
    assert "future leakage" in result["error"]["message"]


def test_cli_workspace_record_outcome_and_summary(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "workspace.db")
    case_path = tmp_path / "case.json"
    case_path.write_text(json.dumps(_case_payload()), encoding="utf-8")
    _run(capsys, "workspace", "add-case", str(case_path), "--db", db)

    outcome = _run(
        capsys,
        "workspace",
        "record-outcome",
        "C1",
        "--horizon",
        "d1",
        "--return-pct",
        "3.5",
        "--db",
        db,
    )
    assert outcome["_exit_code"] == 0

    summary = _run(capsys, "workspace", "summary", "--db", db)
    assert summary["_exit_code"] == 0
    assert summary["summary"]["case_count"] == 1
    assert summary["summary"]["sample_count"] == 1
    assert summary["summary"]["safety"] == SAFETY_DECLARATION


def test_cli_workspace_import_csv_reports_ledger_quality(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "workspace.db")
    csv_path = tmp_path / "fills.csv"
    rows = [
        "成交日期,成交时间,证券代码,证券名称,操作,成交均价,成交数量",
        "2026-09-01,09:40:00,600111,北方稀土,买入,10.00,1000",
        "2026-09-02,14:00:00,600111,北方稀土,卖出,11.00,1000",
    ]
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    imported = _run(capsys, "workspace", "import-csv", str(csv_path), "--db", db)
    assert imported["_exit_code"] == 0
    assert imported["imported"] == 1
    assert imported["ledger_status"] == "ok"

    cases = _run(capsys, "workspace", "list-cases", "--db", db, "--action", "IMPORTED")
    assert cases["count"] == 1


def test_cli_workspace_import_ambiguous_csv_flags_needs_review(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "workspace.db")
    csv_path = tmp_path / "bad.csv"
    rows = [
        "成交日期,成交时间,证券代码,证券名称,操作,成交均价,成交数量",
        "2026-09-02,10:00:00,600519,贵州茅台,卖出,1500.00,100",
    ]
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    imported = _run(capsys, "workspace", "import-csv", str(csv_path), "--db", db)
    assert imported["ledger_status"] == "needs_review"
    assert any(issue["code"] == "sell_without_position" for issue in imported["issues"])


def test_cli_share_pack_writes_static_html(capsys, tmp_path: Path) -> None:
    out_dir = tmp_path / "pack"
    result = _run(capsys, "share-pack", "--output", str(out_dir), "--write")
    assert result["_exit_code"] == 0
    assert result["data_origin"] == "demo_fixture"
    assert result["upload"] is False
    html = (out_dir / "share_pack.html").read_text(encoding="utf-8")
    assert SAFETY_DECLARATION in html
    assert (out_dir / "share_audit.json").exists()
    assert (out_dir / "share_pack.sha256").exists()
