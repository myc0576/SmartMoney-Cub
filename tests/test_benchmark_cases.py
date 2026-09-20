from __future__ import annotations

import json
from pathlib import Path
import pytest

from smartmoney_cub_harness.benchmark.cases import (
    BENCHMARK_CASE_SCHEMA,
    BENCHMARK_ID,
    CASES_PER_TRACK,
    DEV_PER_TRACK,
    HOLDOUT_PER_TRACK,
    TRACK_FINANCIAL_FILINGS,
    TRACK_IDS,
    TRACK_INDUSTRY_EVENTS,
    TRACK_MACRO_POLICY,
    TRACK_TRADING_REVIEW,
    BenchmarkCase,
    load_cases,
    load_track,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_track_ids_contract():
    assert TRACK_IDS == (
        "trading-review",
        "financial-filings",
        "industry-events",
        "macro-policy",
    )
    assert CASES_PER_TRACK == 60
    assert DEV_PER_TRACK == 30
    assert HOLDOUT_PER_TRACK == 30


def test_load_all_four_tracks():
    total_cases = 0
    for track in TRACK_IDS:
        cases = load_track(track)
        assert len(cases) == 60
        dev_cases = [c for c in cases if c.split == "dev"]
        holdout_cases = [c for c in cases if c.split == "holdout"]
        assert len(dev_cases) == 30
        assert len(holdout_cases) == 30

        for c in cases:
            assert c.track == track
            assert c.benchmark_id == BENCHMARK_ID
            assert c.schema == BENCHMARK_CASE_SCHEMA
            assert c.safety == SAFETY_DECLARATION
            assert c.network_required is False
            assert isinstance(c.state, dict)
            assert isinstance(c.labels, dict)
            assert len(c.labels) > 0
            assert "toy" in c.source.lower() or "toy" in str(c.state).lower()

        total_cases += len(cases)

    assert total_cases == 240


def test_future_leakage_rejected():
    invalid_state = {
        "decision_time": "2026-09-15T10:00:00Z",
        "available_at": "2026-09-15T11:00:00Z",  # Future leakage!
    }
    with pytest.raises(ValueError, match="future leakage"):
        BenchmarkCase(
            case_id="case_invalid_01",
            track=TRACK_TRADING_REVIEW,
            split="dev",
            state=invalid_state,
            labels={"review_priority": 1},
        )


def test_network_required_true_rejected():
    with pytest.raises(ValueError, match="network_required must be False"):
        BenchmarkCase(
            case_id="case_net_01",
            track=TRACK_TRADING_REVIEW,
            split="dev",
            state={"decision_time": "2026-09-15T10:00:00Z"},
            labels={"review_priority": 1},
            network_required=True,
        )


def test_safety_declaration_mismatch_rejected():
    with pytest.raises(ValueError, match="safety declaration mismatch"):
        BenchmarkCase(
            case_id="case_safety_01",
            track=TRACK_TRADING_REVIEW,
            split="dev",
            state={},
            labels={},
            safety="UNSAFE_DECLARATION",
        )


def test_ground_truth_labels_are_independent_from_baseline_predictions():
    from smartmoney_cub_harness.benchmark.baseline import baseline_predictions

    # Defend against regression to circularity:
    # Ensure that ground truth labels across the benchmark are NOT identical to baseline predictions
    total_checked = 0
    mismatched_cases = 0

    for track in TRACK_IDS:
        cases = load_track(track)
        for c in cases:
            pred = baseline_predictions(c)
            total_checked += 1
            if pred != c.labels:
                mismatched_cases += 1

    # At least 25% of cases should have baseline predictions diverge from gold ground truth
    mismatch_ratio = mismatched_cases / total_checked
    assert mismatch_ratio >= 0.25, (
        f"Circularity defect detected: mismatch ratio {mismatch_ratio:.2%} is too low. "
        "Ground truth labels must be independently authored, not identical to baseline."
    )

def test_no_gold_label_leakage_in_case_states():
    """Ensure zero answer leakage from labels into state across all benchmark cases."""
    from smartmoney_cub_harness.benchmark.cases import TRACK_IDS, load_track
    import re

    total_checked = 0
    leaked = []

    for track_id in TRACK_IDS:
        cases = load_track(track_id)
        for c in cases:
            for q_id, gold_val in c.labels.items():
                total_checked += 1
                if q_id in c.state:
                    leaked.append(f"{c.case_id}: label key {q_id} present in state")
                    continue
                if isinstance(gold_val, str) and gold_val in c.state:
                    leaked.append(f"{c.case_id}: label value {gold_val} present as key in state")
                    continue
                for sk, sv in c.state.items():
                    if sk in ("notes", "filing_disclosure_excerpt", "event_wire_dispatch", "statement_excerpt"):
                        continue
                    if type(sv) is type(gold_val) and sv == gold_val:
                        leaked.append(f"{c.case_id}: label value {gold_val} matches state[{sk}]")
                        break
                if isinstance(gold_val, str):
                    narrative = str(
                        c.state.get("notes")
                        or c.state.get("filing_disclosure_excerpt")
                        or c.state.get("event_wire_dispatch")
                        or c.state.get("statement_excerpt")
                        or ""
                    )
                    if re.search(r"\b" + re.escape(gold_val) + r"\b", narrative, re.IGNORECASE):
                        leaked.append(f"{c.case_id}: string label {gold_val} leaked into narrative")

    assert total_checked == 1020
    assert len(leaked) == 0, f"Found {len(leaked)} leaked labels across benchmark cases: {leaked[:5]}"