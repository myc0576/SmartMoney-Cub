from __future__ import annotations

import pytest
from smartmoney_cub_harness.jev import (
    TRACK_FINANCIAL_FILINGS,
    TRACK_IDS,
    TRACK_INDUSTRY_EVENTS,
    TRACK_MACRO_POLICY,
    TRACK_TRADING_REVIEW,
    JevQuestion,
    available_tracks,
    build_questions,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_available_tracks_order_and_content():
    tracks = available_tracks()
    assert tracks == (
        "trading-review",
        "financial-filings",
        "industry-events",
        "macro-policy",
    )
    assert tracks == TRACK_IDS


def test_unknown_track_raises_value_error():
    with pytest.raises(ValueError, match="unknown track"):
        build_questions("nonexistent-track")


def test_jev_question_dataclass_validation():
    # Valid questions
    q_choice = JevQuestion("q1", "choice", "Pick one", choices=("A", "B"))
    assert q_choice.choices == ("A", "B")

    q_noul = JevQuestion("q2", "noul", "Yes or no")
    assert q_noul.kind == "noul"

    q_score = JevQuestion("q3", "score", "Rate 1-5", scale_min=1, scale_max=5, levels=("Low", "Medium", "High", "Very high", "Critical"))
    assert q_score.scale_min == 1
    assert q_score.scale_max == 5

    # Invalid kind
    with pytest.raises(ValueError, match="invalid question kind"):
        JevQuestion("q_bad", "free_text", "Invalid")

    # Choice question without choices
    with pytest.raises(ValueError, match="must provide non-empty choices"):
        JevQuestion("q_bad_choice", "choice", "Choice without choices")

    # Score question without proper bounds
    with pytest.raises(ValueError, match="scale_min < scale_max"):
        JevQuestion("q_bad_score", "score", "Score bad", scale_min=5, scale_max=1)


def test_trading_review_track_questions():
    questions = build_questions(TRACK_TRADING_REVIEW)
    assert len(questions) == 4

    by_id = {q.question_id: q for q in questions}
    assert "evidence_sufficiency" in by_id
    assert "major_counter_evidence" in by_id
    assert "failure_mode" in by_id
    assert "review_priority" in by_id

    # All questions must be strictly in allowed kinds
    assert all(q.kind in ("noul", "choice", "score") for q in questions)

    # Verify failure_mode semantics
    fm = by_id["failure_mode"]
    assert fm.kind == "choice"
    assert set(fm.choices) == {
        "discipline",
        "timing",
        "data-quality",
        "thesis",
        "luck",
        "insufficient-evidence",
    }

    # Verify review priority score scale
    rp = by_id["review_priority"]
    assert rp.kind == "score"
    assert rp.scale_min == 1
    assert rp.scale_max == 5


def test_financial_filings_track_questions():
    questions = build_questions(TRACK_FINANCIAL_FILINGS)
    assert len(questions) == 5

    by_id = {q.question_id: q for q in questions}
    assert "disclosure_supports_conclusion" in by_id
    assert "internal_contradiction" in by_id
    assert "materiality_of_change" in by_id
    assert "evidence_quality" in by_id
    assert "information_gap" in by_id

    assert all(q.kind in ("noul", "choice", "score") for q in questions)
    assert by_id["disclosure_supports_conclusion"].kind == "noul"
    assert by_id["internal_contradiction"].kind == "noul"
    assert by_id["evidence_quality"].kind == "score"
    assert by_id["materiality_of_change"].kind == "choice"
    assert by_id["information_gap"].kind == "choice"


def test_industry_events_track_questions():
    questions = build_questions(TRACK_INDUSTRY_EVENTS)
    assert len(questions) == 5

    by_id = {q.question_id: q for q in questions}
    assert "event_class" in by_id
    assert "impact_scope" in by_id
    assert "duration" in by_id
    assert "epistemic_status" in by_id
    assert "supply_chain_impact" in by_id

    # Epistemic status: fact vs management view vs inference
    ep = by_id["epistemic_status"]
    assert ep.kind == "choice"
    assert set(ep.choices) == {"fact", "management-view", "inference"}

    # Supply chain impact: direct / indirect / insufficient
    sc = by_id["supply_chain_impact"]
    assert sc.kind == "choice"
    assert set(sc.choices) == {"direct", "indirect", "insufficient"}

    # Absolute requirement: NO price direction question in industry-events
    assert all("price" not in q.question_id.lower() for q in questions)
    assert all("direction" not in q.question_id.lower() for q in questions)


def test_macro_policy_track_questions():
    questions = build_questions(TRACK_MACRO_POLICY)
    assert len(questions) == 4

    by_id = {q.question_id: q for q in questions}
    assert "policy_stance" in by_id
    assert "macro_direction" in by_id
    assert "impact_horizon" in by_id
    assert "available_at_decision_time" in by_id

    ps = by_id["policy_stance"]
    assert set(ps.choices) == {"hawkish", "dovish", "neutral", "mixed"}

    md = by_id["macro_direction"]
    assert set(md.choices) == {"inflation", "growth", "liquidity", "policy"}

    ih = by_id["impact_horizon"]
    assert set(ih.choices) == {"immediate", "near", "medium", "structural"}

    avail_q = by_id["available_at_decision_time"]
    assert avail_q.kind == "noul"


def test_deterministic_temporality_check_passes_when_valid():
    state = {
        "decision_time": "2026-06-01T15:00:00Z",
        "available_at": "2026-06-01T14:30:00Z",
        "data_sources": [
            {"name": "filing_feed", "available_at": "2026-06-01T14:00:00Z"}
        ],
    }
    questions = build_questions(TRACK_TRADING_REVIEW, state=state)
    assert len(questions) > 0


def test_deterministic_temporality_check_fails_on_future_leakage():
    state = {
        "decision_time": "2026-06-01T15:00:00Z",
        "available_at": "2026-06-01T16:00:00Z",  # in the future!
    }
    with pytest.raises(ValueError, match="future_leakage"):
        build_questions(TRACK_TRADING_REVIEW, state=state)


def test_deterministic_temporality_check_fails_on_nested_source_future_leakage():
    state = {
        "decision_time": "2026-06-01T15:00:00Z",
        "data_sources": [
            {"name": "valid_source", "available_at": "2026-06-01T14:00:00Z"},
            {"name": "leaked_source", "available_at": "2026-06-01T15:01:00Z"},
        ],
    }
    with pytest.raises(ValueError, match="future_leakage"):
        build_questions(TRACK_FINANCIAL_FILINGS, state=state)

def test_score_question_without_levels_raises():
    with pytest.raises(ValueError, match="must provide non-empty levels rubric"):
        JevQuestion("q_no_levels", "score", "Rate severity", scale_min=1, scale_max=5)

    with pytest.raises(ValueError, match="must provide non-empty levels rubric"):
        JevQuestion("q3", "score", "Rate severity", scale_min=1, scale_max=5)

    with pytest.raises(ValueError, match="levels count .* must match scale range"):
        JevQuestion(
            "q_mismatched_levels",
            "score",
            "Rate severity",
            scale_min=1,
            scale_max=5,
            levels=("Level 1", "Level 2"),  # Only 2 levels for a 1..5 scale (needs 5)
        )


def test_score_question_api_payload_carries_real_rubric_not_placeholders():
    captured_payloads = []

    def mock_client(req):
        body = json.loads(req.data.decode("utf-8"))
        captured_payloads.append(body)
        return {
            "model": "jev-1.13.0",
            "answers": {
                "review_priority": {
                    "type": "score",
                    "score": 3.0,
                    "confidence": 0.9,
                    "legend": {"0": "L1", "1": "L2", "2": "L3", "3": "L4", "4": "L5"},
                    "probabilities": {"0": 0.0, "1": 0.0, "2": 0.1, "3": 0.8, "4": 0.1},
                }
            },
            "usage": {"input_tokens": 150, "output_tokens": 20},
        }

    from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend
    import json
    backend = TypeSafeDirectJevBackend(api_key="mock-key", http_client=mock_client)
    rubric = (
        "Routine profitable trade with normal execution; minimal review needed",
        "Acceptable execution or minor loss within expected variance",
        "Moderate loss or minor timing issue requiring standard retrospective",
        "Significant loss, thesis breakdown, or stale data requiring prompt review",
        "Severe loss, catastrophic drawdown, or explicit risk rule violation requiring immediate escalation",
    )
    q = JevQuestion("review_priority", "score", "Rate priority", scale_min=1, scale_max=5, levels=rubric)

    decision = backend.evaluate({"notes": "Trade with thesis error"}, (q,), decision_time="2026-06-01T15:00:00Z")

    assert len(captured_payloads) == 1
    sent_criteria = captured_payloads[0]["questions"]["review_priority"]["criteria"]
    # Must match real rubric descriptions exactly
    assert sent_criteria == list(rubric)
    # Must NOT be dummy placeholder strings
    for item in sent_criteria:
        assert not item.startswith("Level ")
