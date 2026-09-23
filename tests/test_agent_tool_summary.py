import json
import pytest
from smartmoney_cub_harness.agent.tool_summary import summarize_tool_result, get_tool_title
from smartmoney_cub_harness.agent.tools import TOOL_SPECS
from smartmoney_cub_harness.store import Store
from smartmoney_cub_harness.agent.runtime import ReviewAgentRuntime, MAX_CONTEXT_BYTES

def test_all_tool_specs_have_title_and_summary():
    tool_names = [s["function"]["name"] for s in TOOL_SPECS]
    assert len(tool_names) == 9
    for name in tool_names:
        title = get_tool_title(name)
        assert isinstance(title, str) and len(title) > 0
        summary_info = summarize_tool_result(name, {}, {"status": "ok"}, 12.5)
        assert summary_info["title"] == title
        assert summary_info["status"] == "ok"
        assert summary_info["duration_ms"] == 12.5
        assert isinstance(summary_info["summary"], str) and len(summary_info["summary"]) > 0
        assert isinstance(summary_info["stats"], dict)

def test_tool_summary_numbers_match_result_and_no_hallucination():
    # 1. list_trades
    res_trades = {"status": "ok", "count": 15, "returned": 10, "trades": []}
    s = summarize_tool_result("list_trades", {}, res_trades, 10.0)
    assert "15" in s["summary"]
    assert "10" in s["summary"]
    assert s["stats"]["count"] == 15
    assert s["stats"]["returned"] == 10

    # 2. get_trade
    res_trade = {
        "status": "ok",
        "trade": {"symbol": "600519", "net_pnl": 1250.0, "return_pct": 5.2, "holding_days": 3}
    }
    s = summarize_tool_result("get_trade", {"round_trip_id": "rt_1"}, res_trade, 15.0)
    assert "600519" in s["summary"]
    assert "1250" in s["summary"]
    assert "5.2" in s["summary"]
    assert s["stats"]["symbol"] == "600519"
    assert s["stats"]["net_pnl"] == 1250.0

    # 3. analytics_summary
    res_analytics = {
        "status": "ok",
        "summary": {"trade_count": 28, "win_rate": 64.3, "total_net_pnl": 5800.0}
    }
    s = summarize_tool_result("analytics_summary", {}, res_analytics, 20.0)
    assert "28" in s["summary"]
    assert "64.3" in s["summary"]
    assert "5800" in s["summary"]
    assert s["stats"]["trade_count"] == 28

    # 4. calendar_month
    res_cal = {"status": "ok", "year": 2026, "month": 9, "days": [{}, {}]}
    s = summarize_tool_result("calendar_month", {"year": 2026, "month": 9}, res_cal, 8.0)
    assert "2026" in s["summary"]
    assert "9" in s["summary"]
    assert "2" in s["summary"]

    # 5. open_positions
    res_pos = {"status": "ok", "count": 4, "positions": [1, 2, 3, 4]}
    s = summarize_tool_result("open_positions", {}, res_pos, 5.0)
    assert "4" in s["summary"]
    assert s["stats"]["count"] == 4

    # 6. list_rules
    res_rules = {"status": "ok", "count": 7, "rules": []}
    s = summarize_tool_result("list_rules", {}, res_rules, 5.0)
    assert "7" in s["summary"]
    assert s["stats"]["count"] == 7

    # 7. list_review_cases
    res_cases = {"status": "ok", "count": 12, "cases": []}
    s = summarize_tool_result("list_review_cases", {}, res_cases, 5.0)
    assert "12" in s["summary"]
    assert s["stats"]["count"] == 12

    # 8. propose_challenger_rule
    res_prop = {
        "status": "ok",
        "rule": {"rule_id": "R-101", "rule_status": "challenger"},
        "metrics": {"sample_count": 8, "blockers": ["sample_count_below_20"]}
    }
    s = summarize_tool_result("propose_challenger_rule", {"rule_id": "R-101"}, res_prop, 30.0)
    assert "R-101" in s["summary"]
    assert "8" in s["summary"]
    assert "1" in s["summary"]
    assert s["stats"]["sample_count"] == 8

    # 9. data_quality_report
    res_dq = {
        "status": "ok",
        "ledger_status": "valid",
        "blocking_issue_count": 0,
        "open_position_count": 3
    }
    s = summarize_tool_result("data_quality_report", {}, res_dq, 10.0)
    assert "0" in s["summary"]
    assert "3" in s["summary"]
    assert s["stats"]["blocking_issue_count"] == 0

def test_unknown_tool_and_error_fallback():
    # Unknown tool without error
    s = summarize_tool_result("custom_unknown_tool", {"foo": "bar"}, {"status": "ok", "custom_field": 123}, 10.0)
    assert s["status"] == "ok"
    assert "custom_unknown_tool" in s["title"]
    assert isinstance(s["summary"], str)

    # Tool with error
    err_res = {"status": "error", "error": {"code": "not_found", "message": "trade not found"}}
    s_err = summarize_tool_result("get_trade", {"round_trip_id": "missing"}, err_res, 5.0)
    assert s_err["status"] == "error"
    assert "失败" in s_err["summary"] or "错误" in s_err["summary"] or "not found" in s_err["summary"]

    # Non-dict result
    s_raw = summarize_tool_result("unknown", {}, "raw string result", 5.0)
    assert s_raw["status"] == "ok"
    assert isinstance(s_raw["summary"], str)

def test_context_payload_truncation_when_exceeding_limit(tmp_path):
    store = Store(tmp_path)
    try:
        runtime = ReviewAgentRuntime(store)
        # Normal small payload
        normal_payload = runtime.context_payload({})
        assert normal_payload.get("context_truncated") is not True

        # Generate large mock context
        huge_open_positions = [{"symbol": f"SYM_{i}", "notes": "x" * 500} for i in range(200)]
        huge_calendar = [{"date": f"2026-09-{i%30+1:02d}", "detail": "y" * 500} for i in range(200)]
        huge_context = {
            "portfolio": {"portfolio_id": "test_p"},
            "summary": {"trade_count": 1000},
            "open_positions": huge_open_positions,
            "ledger_status": "ok",
            "blocking_issues": [],
            "calendar": huge_calendar,
        }
        degraded = runtime._enforce_context_size_limit(huge_context)
        raw_size = len(json.dumps(huge_context, ensure_ascii=False).encode("utf-8"))
        assert raw_size > MAX_CONTEXT_BYTES
        assert degraded.get("context_truncated") is True
        assert "truncation_reason" in degraded
        degraded_size = len(json.dumps(degraded, ensure_ascii=False).encode("utf-8"))
        assert degraded_size <= MAX_CONTEXT_BYTES
    finally:
        store.close()


def test_runtime_yields_and_persists_tool_summary_fields(tmp_path):
    store = Store(tmp_path / "state")
    try:
        from smartmoney_cub_harness.agent.providers import save_credentials, ALPHATECH_PROVIDER_ID
        save_credentials(
            tmp_path / "state",
            {"providers": {ALPHATECH_PROVIDER_ID: {"api_key": "test-key", "base_url": "http://127.0.0.1:9999"}}},
        )
        runtime = ReviewAgentRuntime(store, credentials_root=str(tmp_path / "state"))
        session = store.create_session(title="测试工具摘要事件")
        session_id = session["session_id"]

        # Run turn with mock tool calls by testing the loop or checking store events
        # We can simulate the events appended during runtime._provider_turn or test via tool call directly
        # Let's inspect session_events when tools are invoked:
        # We can invoke toolbox and check summarize_tool_result integration directly in a turn
        # or mock stream_chat_with_route_chain to yield a tool call:
        from unittest.mock import patch

        fake_call = {
            "name": "open_positions",
            "arguments": json.dumps({"portfolio_id": "default"}),
            "call_id": "call_test_123",
        }

        def mock_stream(*args, **kwargs):
            yield {"kind": "tool_call", "call": fake_call}
            yield {"kind": "done"}

        with patch("smartmoney_cub_harness.agent.runtime.stream_chat_with_route_chain", side_effect=mock_stream):
            # First round yields tool_call, then second round completes
            # Make second call return plain text
            def mock_stream_two_rounds(*args, **kwargs):
                nonlocal round_count
                round_count += 1
                if round_count == 1:
                    yield {"kind": "tool_call", "call": fake_call}
                else:
                    yield {"kind": "delta", "text": "分析完毕"}
                    yield {"kind": "done"}

            round_count = 0
            with patch("smartmoney_cub_harness.agent.runtime.stream_chat_with_route_chain", side_effect=mock_stream_two_rounds):
                events = list(runtime.run_turn(session_id, "查看当前持仓"))

        # Check yielded events
        tool_call_events = [e for e in events if e["kind"] == "tool_call"]
        assert len(tool_call_events) == 1
        assert tool_call_events[0]["title"] == "查询当前持仓"
        assert tool_call_events[0]["call_id"] == "call_test_123"

        tool_result_events = [e for e in events if e["kind"] == "tool_result"]
        assert len(tool_result_events) == 1
        res_evt = tool_result_events[0]
        assert res_evt["step_summary"] == "查询到 0 个当前未了结持仓"
        assert res_evt["stats"] == {"count": 0}
        assert res_evt["status"] == "ok"
        assert isinstance(res_evt["duration_ms"], float)

        # Check persisted session_events
        persisted_events = store.list_events(session_id)
        p_tool_call = [e for e in persisted_events if e["kind"] == "tool_call"]
        assert len(p_tool_call) == 1
        assert p_tool_call[0]["payload"]["title"] == "查询当前持仓"
        assert p_tool_call[0]["payload"]["name"] == "open_positions"

        p_tool_res = [e for e in persisted_events if e["kind"] == "tool_result"]
        assert len(p_tool_res) == 1
        p_res_payload = p_tool_res[0]["payload"]
        assert p_res_payload["step_summary"] == "查询到 0 个当前未了结持仓"
        assert p_res_payload["stats"] == {"count": 0}
        assert p_res_payload["status"] == "ok"
        assert isinstance(p_res_payload["duration_ms"], float)
        assert "result" in p_res_payload
    finally:
        store.close()
