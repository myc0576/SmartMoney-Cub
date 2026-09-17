from __future__ import annotations

import json

import pytest

from smartmoney_cub_harness.governance import GovernanceStore, is_explicit_rule_change
from smartmoney_cub_harness.workbench.server import WorkbenchService
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_first_import_creates_editable_profile_and_baseline_draft(tmp_path):
    store = GovernanceStore(tmp_path)
    result = store.create_baseline_from_import(
        source_snapshot="doc-1",
        sample_count=12,
        facts={"trade_count": 12, "facts_only": True},
    )
    assert result["created"] is True
    assert result["profile"]["status"] == "current"
    assert result["strategy"]["status"] == "baseline_draft"
    assert result["strategy"]["profile_id"] == result["profile"]["profile_id"]
    assert result["safety"] == SAFETY_DECLARATION
    assert store.create_baseline_from_import(
        source_snapshot="doc-2", sample_count=13, facts={"trade_count": 13}
    )["created"] is False


def test_profile_edit_is_immutable_and_stales_dependent_strategy(tmp_path):
    store = GovernanceStore(tmp_path)
    created = store.create_baseline_from_import(
        source_snapshot="doc-1", sample_count=25, facts={"style": "intraday"}
    )
    edited = store.edit_profile(created["profile"]["profile_id"], {"facts": {"style": "swing"}})
    assert edited["profile"]["profile_id"] != created["profile"]["profile_id"]
    assert edited["profile"]["status"] == "current"
    assert edited["stale_strategy_ids"] == [created["strategy"]["strategy_id"]]
    assert store.strategies()[0]["status"] == "stale"


def test_chat_creates_challenger_only_for_explicit_rule_change_and_evaluates(tmp_path):
    store = GovernanceStore(tmp_path)
    store.create_baseline_from_import(
        source_snapshot="doc-1", sample_count=25, facts={"trade_count": 25}
    )
    ordinary = store.create_challenger_from_chat(text="最近亏损有什么共同点？", rules=[])
    assert ordinary["created"] is False
    created = store.create_challenger_from_chat(
        text="请新增规则：连续两次亏损后暂停交易",
        rules=[{"rule": "连续两次亏损后暂停交易"}],
        metrics={"sample_count": 25, "false_alert_rate": 0.1, "missed_opportunity_rate": 0.1},
    )
    assert created["created"] is True
    assert created["evaluation"]["status"] == "passed"
    assert created["strategy"]["status"] == "challenger"
    assert store.request_promotion(created["strategy"]["strategy_id"])["status"] == "pending_confirmation"


def test_promotion_requires_note_and_keeps_history_for_rollback(tmp_path):
    store = GovernanceStore(tmp_path)
    store.create_baseline_from_import(source_snapshot="doc", sample_count=25, facts={"trade_count": 25})
    challenger = store.create_challenger_from_chat(
        text="生成规则：降低追涨频率",
        rules=[{"rule": "降低追涨频率"}],
        metrics={"sample_count": 25},
    )
    request = store.request_promotion(challenger["strategy"]["strategy_id"])
    with pytest.raises(ValueError):
        store.confirm_promotion(request["promotion_id"], " ")
    promoted = store.confirm_promotion(request["promotion_id"], "我已查看同样本评估结果")
    assert promoted["strategy"]["status"] == "champion"
    assert promoted["event"]["kind"] == "champion_promoted"
    rolled = store.rollback(challenger["strategy"]["strategy_id"], "回滚到已确认版本")
    assert rolled["strategy"]["status"] == "champion"
    saved = json.loads((tmp_path / "governance.json").read_text())
    assert saved["safety"] == SAFETY_DECLARATION


@pytest.mark.parametrize("text", ["新增规则", "修改规则", "create challenger", "普通讨论"])
def test_explicit_intent_classifier(text):
    assert is_explicit_rule_change(text) is (text != "普通讨论")


def test_workbench_stream_emits_structured_challenger_artifact(tmp_path):
    service = WorkbenchService(tmp_path)
    try:
        session = service.create_session({"title": "测试", "provider_id": "offline"})["session"]
        events = service.stream_turn(session["session_id"], {"text": "新增规则：连续亏损后暂停"})
        first = next(events)
        assert first["kind"] == "artifact"
        assert first["artifact"]["created"] is True
        assert first["safety"] == SAFETY_DECLARATION
    finally:
        service.close()
