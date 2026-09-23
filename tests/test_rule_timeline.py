import json
from pathlib import Path
import threading
import urllib.request
from http.server import ThreadingHTTPServer
import pytest

from smartmoney_cub_harness.workspace import Workspace
from smartmoney_cub_harness.evolution_ledger import append_ledger_event
from smartmoney_cub_harness.workbench.server import WorkbenchService, WorkbenchHandler, ApiError
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

def test_timeline_http_endpoint_dispatch(tmp_path: Path):
    db_path = tmp_path / "workspace" / "review.db"
    service = WorkbenchService(tmp_path, workspace_db=str(db_path))
    handler = type("H", (WorkbenchHandler,), {"service": service, "protocol_version": "HTTP/1.1"})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/rules/timeline") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ok"
            assert "timeline" in data
            assert data["safety"] == SAFETY_DECLARATION
    finally:
        server.shutdown()
        server.server_close()
        service.close()

def test_timeline_empty_ledger_and_no_rules(tmp_path: Path):
    db_path = tmp_path / "workspace" / "review.db"
    service = WorkbenchService(tmp_path, workspace_db=str(db_path))
    try:
        timeline = service.rules_timeline()
        assert timeline["status"] == "ok"
        assert timeline["timeline"] == []
        assert timeline["safety"] == SAFETY_DECLARATION
    finally:
        service.close()

def test_timeline_single_rule_multiple_events_and_promotion(tmp_path: Path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    db_path = workspace_dir / "review.db"
    ledger_path = workspace_dir / "evolution_ledger.jsonl"

    ws = Workspace(db_path)
    ws.set_rule_state(
        rule_id="r_holding_1d",
        family="holding_period",
        title="避免次日平仓",
        status="challenger",
        metrics={"sample_count": 25, "condition": "holding_days == 1"},
    )
    ws.close()

    append_ledger_event(
        ledger_path,
        "candidate_discovered",
        {"rule_id": "r_holding_1d", "title": "避免次日平仓", "family": "holding_period", "detail": "复盘发现次日胜率异常偏低"},
    )
    append_ledger_event(
        ledger_path,
        "challenger_rule_proposed",
        {"rule_id": "r_holding_1d", "sample_count": 25, "family": "holding_period", "title": "避免次日平仓"},
    )

    service = WorkbenchService(tmp_path, workspace_db=str(db_path))
    try:
        res = service.rules_timeline()
        assert res["status"] == "ok"
        assert len(res["timeline"]) == 1
        item = res["timeline"][0]
        assert item["rule_id"] == "r_holding_1d"
        assert item["status"] == "challenger"
        assert len(item["events"]) >= 2
        event_names = [e["event"] for e in item["events"]]
        assert "candidate_discovered" in event_names
        assert "challenger_rule_proposed" in event_names

        promote_res = service.promote_rule("r_holding_1d", {"note": "经人工回溯近一个月交割单，胜率显著提升，确认晋级。"})
        assert promote_res["status"] == "ok"

        res_after = service.rules_timeline()
        item_after = res_after["timeline"][0]
        assert item_after["status"] == "champion"
        assert item_after["promotion_note"] == "经人工回溯近一个月交割单，胜率显著提升，确认晋级。"
        events_after = [e["event"] for e in item_after["events"]]
        assert "champion_promoted" in events_after or "promotion_confirmation_recorded" in events_after
    finally:
        service.close()

def test_timeline_out_of_order_ledger_sorting(tmp_path: Path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    db_path = workspace_dir / "review.db"
    ledger_path = workspace_dir / "evolution_ledger.jsonl"

    ws = Workspace(db_path)
    ws.set_rule_state(
        rule_id="r_order",
        family="time_exit",
        title="时序测试",
        status="challenger",
        metrics={"sample_count": 10},
    )
    ws.close()

    with ledger_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({
            "schema": "smartmoney_cub_evolution_ledger.v1",
            "event": "challenger_verified",
            "rule_id": "r_order",
            "created_at": "2026-09-20T12:00:00+08:00",
            "safety": SAFETY_DECLARATION,
        }) + "\n")
        f.write(json.dumps({
            "schema": "smartmoney_cub_evolution_ledger.v1",
            "event": "challenger_rule_proposed",
            "rule_id": "r_order",
            "created_at": "2026-09-18T10:00:00+08:00",
            "safety": SAFETY_DECLARATION,
        }) + "\n")
        f.write(json.dumps({
            "schema": "smartmoney_cub_evolution_ledger.v1",
            "event": "candidate_discovered",
            "rule_id": "r_order",
            "created_at": "2026-09-15T09:00:00+08:00",
            "safety": SAFETY_DECLARATION,
        }) + "\n")

    service = WorkbenchService(tmp_path, workspace_db=str(db_path))
    try:
        res = service.rules_timeline()
        events = res["timeline"][0]["events"]
        assert [e["event"] for e in events] == [
            "candidate_discovered",
            "challenger_rule_proposed",
            "challenger_verified",
        ]
    finally:
        service.close()

def test_timeline_evidence_fallback_and_confidence(tmp_path: Path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    db_path = workspace_dir / "review.db"

    ws = Workspace(db_path)
    ws.set_rule_state(
        rule_id="r_no_condition",
        family="other",
        title="无条件规则",
        status="challenger",
        metrics={},
    )
    ws.close()

    service = WorkbenchService(tmp_path, workspace_db=str(db_path))
    try:
        res = service.rules_timeline()
        item = res["timeline"][0]
        evidence = item["evidence"]
        assert evidence["trade_ids"] == []
        assert evidence["trigger_count"] == 0
        assert evidence["confidence"] in ("none", "low")
        assert evidence["source"] == "unassociated"
    finally:
        service.close()

def test_promotion_requires_non_empty_note(tmp_path: Path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    db_path = workspace_dir / "review.db"

    ws = Workspace(db_path)
    ws.set_rule_state(
        rule_id="r_gate",
        family="risk",
        title="硬门禁测试",
        status="challenger",
        metrics={"sample_count": 30},
    )
    ws.close()

    service = WorkbenchService(tmp_path, workspace_db=str(db_path))
    try:
        with pytest.raises(ApiError) as exc_info:
            service.promote_rule("r_gate", {"note": ""})
        assert "说明" in str(exc_info.value) or "note_required" in getattr(exc_info.value, "code", "")

        with pytest.raises(ApiError) as exc_info2:
            service.promote_rule("r_gate", {"note": "   "})
        assert "说明" in str(exc_info2.value) or "note_required" in getattr(exc_info2.value, "code", "")
    finally:
        service.close()

