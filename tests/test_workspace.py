from __future__ import annotations

from pathlib import Path

import pytest

from smartmoney_cub_harness.plugins.envelope import build_evidence_envelope
from smartmoney_cub_harness.plugins.types import ResultKind
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workspace import Workspace

DECISION_TIME = "2026-09-10T15:00:00+08:00"
AVAILABLE_AT = "2026-09-10T14:00:00+08:00"


def _workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path / "workspace.db")


def _alert_case(workspace: Workspace, case_id: str = "CASE-1", **overrides: object) -> dict:
    payload = {
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
    payload.update(overrides)
    return workspace.add_case(**payload)


def test_workspace_records_and_reads_a_case(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    record = _alert_case(workspace)
    assert record["case_id"] == "CASE-1"
    assert record["symbol"] == "600111"
    assert record["safety"] == SAFETY_DECLARATION
    assert record["give_up_conditions"] == ["pattern failed"]
    assert record["tags"] == ["mainline"]


def test_non_silent_observation_requires_full_contract(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ValueError) as excinfo:
        workspace.add_case(
            case_id="CASE-BAD",
            symbol="600111",
            action="ALERT",
            decision_time=DECISION_TIME,
        )
    message = str(excinfo.value)
    for field in (
        "invalidation_price",
        "time_stop",
        "give_up_conditions",
        "data_source",
        "available_at",
        "data_quality_flag",
    ):
        assert field in message


def test_workspace_blocks_future_leakage(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ValueError) as excinfo:
        _alert_case(workspace, available_at="2026-09-11T15:00:00+08:00")
    assert "future leakage" in str(excinfo.value)


def test_silent_decision_needs_no_risk_contract(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    record = workspace.add_case(
        case_id="CASE-SILENT",
        symbol="600111",
        action="SILENT",
        decision_time=DECISION_TIME,
    )
    assert record["action"] == "SILENT"


def test_avoid_and_empty_position_are_first_class_actions(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    for index, action in enumerate(("BUY", "SELL", "HOLD", "FLAT", "AVOID", "NO_DECISION")):
        record = _alert_case(workspace, case_id=f"CASE-{index}", action=action)
        assert record["action"] == action


def test_harness_decision_labels_are_accepted_too(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    for index, action in enumerate(("ALERT", "WATCH", "EMPTY_POSITION", "ERROR")):
        record = _alert_case(workspace, case_id=f"HARNESS-{index}", action=action)
        assert record["action"] == action


def test_unknown_action_is_rejected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ValueError):
        _alert_case(workspace, action="MOON")


def test_naive_timestamps_are_rejected(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ValueError):
        _alert_case(workspace, decision_time="2026-09-10T15:00:00")


def test_list_cases_filters(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _alert_case(workspace, case_id="CASE-1", symbol="600111", regime="生长")
    _alert_case(workspace, case_id="CASE-2", symbol="600222", regime="衰退", action="AVOID")
    assert len(workspace.list_cases()) == 2
    assert [case["case_id"] for case in workspace.list_cases(symbol="600222")] == ["CASE-2"]
    assert [case["case_id"] for case in workspace.list_cases(action="AVOID")] == ["CASE-2"]
    assert [case["case_id"] for case in workspace.list_cases(regime="生长")] == ["CASE-1"]


def test_outcome_recording_requires_existing_case(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(KeyError):
        workspace.record_outcome(case_id="MISSING", horizon="d1", return_pct=1.0)


def test_outcome_does_not_mutate_the_frozen_case(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _alert_case(workspace)
    workspace.record_outcome(
        case_id="CASE-1", horizon="d1", return_pct=4.2, max_adverse_excursion_pct=-1.1
    )
    case = workspace.get_case("CASE-1")
    # Post-decision data must not rewrite what was known at decision time.
    assert "return_pct" not in case
    assert case["available_at"] == AVAILABLE_AT
    outcomes = workspace.list_outcomes("CASE-1")
    assert outcomes[0]["return_pct"] == 4.2


def _envelope(result_kind: str = ResultKind.REVIEW_OBSERVATION) -> dict:
    return build_evidence_envelope(
        plugin_id="toy.review-tagger",
        plugin_version="0.1.0",
        source_ref="toy@abc",
        capability="reviewer",
        result_kind=result_kind,
        request={"symbol": "600111"},
        output={"observations": []},
        decision_time=DECISION_TIME,
        available_at=AVAILABLE_AT,
        data_source="toy_fixture",
        data_quality="ok",
    )


def test_plugin_evidence_is_persisted_with_provenance(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _alert_case(workspace)
    result = workspace.record_evidence(_envelope(), case_id="CASE-1")
    assert result["status"] == "ok"
    assert result["review_only"] is True
    records = workspace.list_evidence(case_id="CASE-1")
    assert len(records) == 1
    assert records[0]["plugin_id"] == "toy.review-tagger"
    assert records[0]["envelope"]["safety"] == SAFETY_DECLARATION


def test_invalid_evidence_is_refused(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    broken = _envelope()
    broken["champion_mutated"] = True
    with pytest.raises(ValueError):
        workspace.record_evidence(broken)


def test_model_opinion_evidence_stays_review_only(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.record_evidence(_envelope(ResultKind.MODEL_OPINION))
    record = workspace.list_evidence()[0]
    assert record["review_only"] is True
    assert record["result_kind"] == ResultKind.MODEL_OPINION


def test_champion_rule_requires_human_note(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ValueError) as excinfo:
        workspace.set_rule_state(rule_id="RULE-1", status="champion")
    assert "explicit human confirmation note" in str(excinfo.value)

    result = workspace.set_rule_state(
        rule_id="RULE-1", status="champion", promotion_note="reviewed 25 samples manually"
    )
    assert result["rule_status"] == "champion"
    rule = workspace.get_rule("RULE-1")
    assert rule["promotion_note"] == "reviewed 25 samples manually"
    assert rule["promoted_at"] is not None


def test_rule_state_rejects_unknown_status(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ValueError):
        workspace.set_rule_state(rule_id="RULE-X", status="godmode")


def test_challenger_state_does_not_require_note(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.set_rule_state(rule_id="RULE-2", status="challenger", title="candidate")
    assert workspace.get_rule("RULE-2")["status"] == "challenger"
    assert workspace.list_rules(status="champion") == []


def test_list_rules_with_blockers_carries_the_frozen_thresholds(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.set_rule_state(
        rule_id="RULE-WEAK",
        status="challenger",
        metrics={"sample_count": 3, "future_leakage_count": 1},
    )
    workspace.set_rule_state(
        rule_id="RULE-STRONG",
        status="promotion_recommended",
        metrics={
            "sample_count": 30,
            "false_alert_rate": 0.1,
            "missed_opportunity_rate": 0.1,
            "future_leakage_count": 0,
            "risk_contract_violation_rate": 0.0,
        },
    )

    # list_rules orders by rule_id, so look the rows up by id rather than by position.
    by_id = {rule["rule_id"]: rule for rule in workspace.list_rules_with_blockers()}
    weak, strong = by_id["RULE-WEAK"], by_id["RULE-STRONG"]
    assert weak["promotion_blockers"] == ["sample_count_below_20", "future_leakage_detected"]
    assert weak["promotion_recommendable"] is False
    assert strong["promotion_blockers"] == []
    assert strong["promotion_recommendable"] is True

    # The status filter still applies to the enriched listing.
    only_challengers = workspace.list_rules_with_blockers(status="challenger")
    assert [rule["rule_id"] for rule in only_challengers] == ["RULE-WEAK"]


def test_promote_rule_keeps_blockers_advisory_and_records_the_note(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.set_rule_state(
        rule_id="RULE-3",
        status="challenger",
        family="toy",
        title="thin sample",
        metrics={"sample_count": 2},
    )

    # A thin sample cannot make a promotion RECOMMENDATION, but only the human
    # note gates the champion row. The contract separates those two decisions.
    result = workspace.promote_rule(rule_id="RULE-3", note="reviewed by hand")
    assert result["rule_status"] == "champion"
    assert result["promotion_blockers"] == ["sample_count_below_20"]
    assert result["blockers_are_advisory"] is True
    assert workspace.get_rule("RULE-3")["family"] == "toy"
    assert workspace.get_rule("RULE-3")["title"] == "thin sample"


def test_promote_rule_without_a_note_refuses_and_writes_nothing(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.set_rule_state(rule_id="RULE-4", status="challenger")

    with pytest.raises(ValueError) as excinfo:
        workspace.promote_rule(rule_id="RULE-4", note="   ")
    assert "explicit human confirmation note" in str(excinfo.value)
    assert workspace.get_rule("RULE-4")["status"] == "challenger"
    assert workspace.summary()["champion_rule_count"] == 0


def test_reject_rule_records_rejection_without_losing_the_rule_description(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace.set_rule_state(
        rule_id="RULE-5",
        status="promotion_recommended",
        family="toy",
        title="candidate",
        metrics={"sample_count": 25},
    )

    result = workspace.reject_rule(rule_id="RULE-5")
    assert result["rule_status"] == "rejected"
    rule = workspace.get_rule("RULE-5")
    assert rule["family"] == "toy"
    assert rule["title"] == "candidate"
    assert rule["metrics"]["sample_count"] == 25


def test_summary_reports_sample_size_and_statistical_limits(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _alert_case(workspace)
    workspace.record_outcome(case_id="CASE-1", horizon="d1", return_pct=2.0)
    workspace.record_outcome(case_id="CASE-1", horizon="d3", return_pct=-1.0)
    summary = workspace.summary()
    assert summary["case_count"] == 1
    assert summary["outcome_count"] == 2
    assert summary["sample_count"] == 2
    assert summary["mean_return_pct"] == 0.5
    assert "cannot support confident conclusions" in summary["statistical_limits"]
    assert summary["safety"] == SAFETY_DECLARATION


def test_workspace_persists_across_connections(tmp_path: Path) -> None:
    db = tmp_path / "workspace.db"
    first = Workspace(db)
    _alert_case(first)
    first.close()

    second = Workspace(db)
    assert second.get_case("CASE-1") is not None
    second.close()
