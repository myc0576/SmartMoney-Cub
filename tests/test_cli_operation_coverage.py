"""Executable coverage for the WebUI business-operation CLI surface."""

from __future__ import annotations

import base64
import json

from smartmoney_cub_harness.control_operations import OPERATIONS
from smartmoney_cub_harness.control_runtime import ControlRuntime
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _bars() -> list[dict[str, object]]:
    return [
        {"symbol": "TOY-CLI", "interval": "1d", "open_time": f"2026-09-{day:02d}",
         "open": close, "high": close + 0.5, "low": close - 0.5,
         "close": close, "volume": 1000}
        for day, close in enumerate((10.0, 10.0, 11.0, 12.0, 11.0, 10.0), 1)
    ]


def _fill(side: str = "BUY", trade_id: str = "toy-cli-buy") -> dict[str, object]:
    return {"trade_id": trade_id, "account_id": "TOY-ACCOUNT", "symbol": "TOY-CLI",
            "name": "Toy CLI Instrument", "side": side, "trade_date": "2026-09-01",
            "trade_time": "09:30:00", "price": 10.0 if side == "BUY" else 11.0,
            "quantity": 10.0, "fee": 0.1}


def _assert_safe(value: object) -> None:
    assert SAFETY_DECLARATION in json.dumps(value, ensure_ascii=False)


def test_operation_registry_has_requested_webui_and_local_groups() -> None:
    expected = {"import.upload", "import.commit-reviewed", "governance.profile-create",
                "governance.challenger", "governance.evaluate", "governance.request-promotion",
                "governance.confirm-promotion", "assistant.create", "assistant.update",
                "assistant.fork", "assistant.scope", "assistant.package", "plugin.catalog",
                "plugin.list", "plugin.configure", "backtest.run", "replay.create", "replay.step"}
    assert expected <= set(OPERATIONS)
    assert all(op.describe()["safety"] == SAFETY_DECLARATION for op in OPERATIONS.values())


def test_import_upload_and_commit_reviewed_use_shared_workbench(tmp_path) -> None:
    runtime = ControlRuntime(state_dir=tmp_path / "state")
    try:
        raw = json.dumps([_fill()]).encode()
        uploaded = runtime.execute("import.upload", {"file_name": "toy-cli.json",
            "media_type": "application/json", "content_base64": base64.b64encode(raw).decode()})
        committed = runtime.execute("import.commit-reviewed", {"extraction_id": uploaded["extraction"]["extraction_id"]})
        assert committed["inserted_count"] == 1
        assert runtime.execute("journal.list")["fills"]
        _assert_safe(uploaded); _assert_safe(committed)
    finally:
        runtime.close()


def test_governance_challenger_evaluation_and_human_confirmation(tmp_path) -> None:
    runtime = ControlRuntime(state_dir=tmp_path / "state", confirmed=True)
    metrics = {"sample_count": 20, "false_alert_rate": 0, "missed_opportunity_rate": 0,
               "future_leakage_count": 0, "risk_contract_violation_rate": 0}
    try:
        runtime.execute("governance.profile-create", {"source_snapshot": "toy-cli"})
        challenger = runtime.execute("governance.challenger", {"text": "创建 challenger：toy evidence",
            "family": "toy-cli", "rules": [{"rule": "toy evidence required", "evidence_required": True}], "metrics": metrics})
        strategy_id = challenger["strategy"]["strategy_id"]
        evaluation = runtime.execute("governance.evaluate", {"strategy_id": strategy_id, "metrics": metrics})
        assert evaluation["evaluation"]["status"] == "passed"
        request = runtime.execute("governance.request-promotion", {"strategy_id": strategy_id})
        confirmed = runtime.execute("governance.confirm-promotion", {"promotion_id": request["promotion"]["promotion_id"], "note": "Toy evidence reviewed by a human."})
        assert confirmed["strategy"]["status"] == "champion"
        _assert_safe(confirmed)
    finally:
        runtime.close()


def test_assistant_lifecycle_scope_and_structured_review_package(tmp_path) -> None:
    runtime = ControlRuntime(state_dir=tmp_path / "state")
    try:
        session = runtime.execute("assistant.create", {"title": "Toy CLI review", "provider_id": "offline",
            "context": {"decision_time": "2026-09-01T10:00:00+08:00", "case_ids": ["toy-case"]}})["session"]
        session_id = session["session_id"]
        updated = runtime.execute("assistant.update", {"session_id": session_id, "title": "Updated toy review"})
        forked = runtime.execute("assistant.fork", {"session_id": session_id, "title": "Toy fork"})
        scope = runtime.execute("assistant.scope", {"session_id": session_id})
        confirmed = runtime.execute("assistant.confirm-scope", {"session_id": session_id, "review_id": session_id})
        proposal = {"candidate_role": "challenger", "rule_id": "TOY-CLI-1", "rationale": "toy",
                    "champion_mutated": False, "core_rules_mutated": False}
        from smartmoney_cub_harness.review_contracts import StructuredReviewPackage
        package = {"schema": "smartmoney_cub_structured_review_package.v2", "safety": SAFETY_DECLARATION, "review_id": session_id, "scope": scope["envelope"]["scope"], "envelope": scope["envelope"],
                   "observations": [{"action_label": "WATCH", "invalidation_price": "unknown", "time_stop": "next session",
                                     "give_up_conditions": ["toy evidence incomplete"], "data_source": "toy_fixture",
                                     "available_at": "2026-09-01T10:00:00+08:00", "data_quality_flag": "ok"}],
                   "evidence": [], "challenger_proposals": [proposal]}
        package = StructuredReviewPackage.from_dict(package).to_dict()
        saved = runtime.execute("assistant.package", {"session_id": session_id, "review_package": package})
        assert updated["session"]["title"] == "Updated toy review"
        assert forked["session"]["session_id"] != session_id
        assert confirmed["phase"] == "scope_confirmed"
        assert saved["phase"] == "completed"
        _assert_safe(saved)
    finally:
        runtime.close()


def test_plugin_registry_read_and_local_config_are_callable(tmp_path) -> None:
    runtime = ControlRuntime(state_dir=tmp_path / "state", confirmed=True)
    try:
        listed = runtime.execute("plugin.list")
        catalog = runtime.execute("plugin.catalog")
        assert listed["status"] in {"ok", "unavailable"}
        assert catalog["catalog"]
        configured = runtime.execute("plugin.configure", {"plugin_id": "tencent-quotes", "config": {"mode": "toy"}})
        assert configured["status"] in {"ok", "not_found", "error", "permissions_required"}
        _assert_safe(catalog)
    finally:
        runtime.close()


def test_offline_backtest_and_replay_are_persisted_without_network(tmp_path) -> None:
    runtime = ControlRuntime(state_dir=tmp_path / "state")
    spec = {"version": 1, "name": "toy-cli", "universe": {"symbol": "TOY-CLI", "interval": "1d"},
            "indicators": [{"id": "fast", "kind": "sma", "source": "close", "period": 1}],
            "entry": {"all": [{"gte": ["fast", "fast"]}]}, "exit": {"all": [{"gte": ["fast", "fast"]}]},
            "stop": {"kind": "none"}, "target": {"kind": "none"},
            "sizing": {"kind": "fixed_quantity", "value": 1}, "filters": {"session": None, "min_bars": 1}, "fill": "same_close"}
    try:
        backtest = runtime.execute("backtest.run", {"strategy": spec, "bars": _bars(), "initial_cash": 1000})
        runs = runtime.execute("backtest.list")
        run_id = backtest.get("run_id") or backtest.get("run", {}).get("run_id")
        detail = runtime.execute("backtest.show", {"run_id": run_id})
        replay = runtime.execute("replay.create", {"symbol": "TOY-CLI", "interval": "1d", "bars": _bars(), "mode": "training"})
        stepped = runtime.execute("replay.step", {"session_id": replay["session"]["session_id"]})
        assert runs["runs"]
        assert detail["run"]["run_id"] == run_id
        assert stepped["session"]["cursor"] == 1
        _assert_safe(backtest)
    finally:
        runtime.close()
