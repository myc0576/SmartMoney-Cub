from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.benchmark.baseline import baseline_predictions
from smartmoney_cub_harness.benchmark.cases import (
    BENCHMARK_CASE_SCHEMA,
    BENCHMARK_ID,
    BenchmarkCase,
    TRACK_FINANCIAL_FILINGS,
    TRACK_INDUSTRY_EVENTS,
    TRACK_MACRO_POLICY,
    TRACK_TRADING_REVIEW,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

OUT_DIR = Path("benchmarks") / BENCHMARK_ID
OUT_DIR.mkdir(parents=True, exist_ok=True)


def make_trading_case(idx: int, split: str) -> BenchmarkCase:
    case_id = f"case_tr_{split}_{idx:02d}"
    qual = ["ok", "stale", "partial"][idx % 3]
    contra = (idx % 7 == 0)
    counter = (idx % 4 == 0)
    num_srcs = (idx % 4)
    loss = 300.0 * (idx % 20)
    ret = -15.0 + (idx % 30)
    rule_vio = (idx % 9 == 0)
    timing_err = (idx % 5 == 0)

    data_sources = [
        {
            "name": f"toy_source_{s_i}",
            "fetch_time": "2026-09-15T09:00:00Z",
            "available_at": "2026-09-15T09:00:00Z",
            "data_quality_flag": qual,
        }
        for s_i in range(num_srcs)
    ]

    state = {
        "symbol": f"TOY.TR{idx:02d}",
        "decision_time": "2026-09-15T09:30:00Z",
        "available_at": "2026-09-15T09:30:00Z",
        "data_sources": data_sources,
        "data_quality_flag": qual,
        "has_contradiction": contra,
        "has_counter_evidence": counter,
        "loss_amount": loss,
        "return_pct": ret,
        "rule_violation": rule_vio,
        "timing_error": timing_err,
        "description": f"Toy trading review case {idx} in {split} partition",
    }

    dummy_case = BenchmarkCase(
        case_id=case_id,
        track=TRACK_TRADING_REVIEW,
        split=split,
        state=state,
        labels={},
        source="toy_offline_generator",
        network_required=False,
    )
    labels = baseline_predictions(dummy_case)

    return BenchmarkCase(
        case_id=case_id,
        track=TRACK_TRADING_REVIEW,
        split=split,
        state=state,
        labels=labels,
        source="toy_offline_generator",
        network_required=False,
    )


def make_filings_case(idx: int, split: str) -> BenchmarkCase:
    case_id = f"case_ff_{split}_{idx:02d}"
    contra = (idx % 6 == 0)
    rev_change = -35.0 + (idx * 2.5)
    net_change = -20.0 + (idx * 1.8)
    gap_levels = ["none", "minor", "significant", "critical"]
    gap_flag = gap_levels[idx % 4]
    num_srcs = (idx % 4) + 1

    data_sources = [
        {
            "name": f"toy_sec_filing_{s_i}",
            "fetch_time": "2026-09-15T08:00:00Z",
            "available_at": "2026-09-15T08:00:00Z",
            "data_quality_flag": "ok",
        }
        for s_i in range(num_srcs)
    ]

    state = {
        "symbol": f"TOY.FF{idx:02d}",
        "decision_time": "2026-09-15T08:30:00Z",
        "available_at": "2026-09-15T08:30:00Z",
        "data_sources": data_sources,
        "has_internal_contradiction": contra,
        "thesis_supported": not contra and (idx % 3 != 0),
        "revenue_change_pct": rev_change,
        "net_income_change_pct": net_change,
        "gap_level": gap_flag,
        "description": f"Toy financial filings case {idx} in {split} partition",
    }

    dummy_case = BenchmarkCase(
        case_id=case_id,
        track=TRACK_FINANCIAL_FILINGS,
        split=split,
        state=state,
        labels={},
        source="toy_offline_generator",
        network_required=False,
    )
    labels = baseline_predictions(dummy_case)

    return BenchmarkCase(
        case_id=case_id,
        track=TRACK_FINANCIAL_FILINGS,
        split=split,
        state=state,
        labels=labels,
        source="toy_offline_generator",
        network_required=False,
    )


def make_industry_case(idx: int, split: str) -> BenchmarkCase:
    case_id = f"case_ie_{split}_{idx:02d}"
    categories = ["regulatory", "technological", "competitive", "supply-chain", "macroeconomic", "other"]
    scopes = ["firm-specific", "subsector", "broad-industry", "cross-industry"]
    durations = ["transitory", "short-term", "medium-term", "structural"]
    epistemics = ["fact", "management-view", "inference"]
    sc_impacts = ["direct", "indirect", "insufficient"]

    state = {
        "event_id": f"EVT_{split}_{idx:02d}",
        "decision_time": "2026-09-15T12:00:00Z",
        "available_at": "2026-09-15T12:00:00Z",
        "event_category": categories[idx % len(categories)],
        "scope": scopes[idx % len(scopes)],
        "duration": durations[idx % len(durations)],
        "epistemic_status": epistemics[idx % len(epistemics)],
        "supply_chain_impact": sc_impacts[idx % len(sc_impacts)],
        "data_sources": [
            {
                "name": "toy_industry_wire",
                "fetch_time": "2026-09-15T11:55:00Z",
                "available_at": "2026-09-15T11:55:00Z",
                "data_quality_flag": "ok",
            }
        ],
        "description": f"Toy industry event case {idx} in {split} partition",
    }

    dummy_case = BenchmarkCase(
        case_id=case_id,
        track=TRACK_INDUSTRY_EVENTS,
        split=split,
        state=state,
        labels={},
        source="toy_offline_generator",
        network_required=False,
    )
    labels = baseline_predictions(dummy_case)

    return BenchmarkCase(
        case_id=case_id,
        track=TRACK_INDUSTRY_EVENTS,
        split=split,
        state=state,
        labels=labels,
        source="toy_offline_generator",
        network_required=False,
    )


def make_macro_case(idx: int, split: str) -> BenchmarkCase:
    case_id = f"case_mp_{split}_{idx:02d}"
    stances = ["hawkish", "dovish", "neutral", "mixed"]
    directions = ["inflation", "growth", "liquidity", "policy"]
    horizons = ["immediate", "near", "medium", "structural"]

    state = {
        "policy_id": f"MACRO_{split}_{idx:02d}",
        "decision_time": "2026-09-15T14:00:00Z",
        "available_at": "2026-09-15T14:00:00Z",
        "policy_stance": stances[idx % len(stances)],
        "macro_direction": directions[idx % len(directions)],
        "impact_horizon": horizons[idx % len(horizons)],
        "available_at_decision_time": True,
        "data_sources": [
            {
                "name": "toy_central_bank_bulletin",
                "fetch_time": "2026-09-15T13:45:00Z",
                "available_at": "2026-09-15T13:45:00Z",
                "data_quality_flag": "ok",
            }
        ],
        "description": f"Toy macro policy case {idx} in {split} partition",
    }

    dummy_case = BenchmarkCase(
        case_id=case_id,
        track=TRACK_MACRO_POLICY,
        split=split,
        state=state,
        labels={},
        source="toy_offline_generator",
        network_required=False,
    )
    labels = baseline_predictions(dummy_case)

    return BenchmarkCase(
        case_id=case_id,
        track=TRACK_MACRO_POLICY,
        split=split,
        state=state,
        labels=labels,
        source="toy_offline_generator",
        network_required=False,
    )


def generate_all() -> None:
    generators = {
        TRACK_TRADING_REVIEW: make_trading_case,
        TRACK_FINANCIAL_FILINGS: make_filings_case,
        TRACK_INDUSTRY_EVENTS: make_industry_case,
        TRACK_MACRO_POLICY: make_macro_case,
    }

    for track, gen_func in generators.items():
        cases = []
        for i in range(1, 31):
            cases.append(gen_func(i, "dev"))
        for i in range(1, 31):
            cases.append(gen_func(i, "holdout"))

        assert len(cases) == 60

        out_path = OUT_DIR / f"{track}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for c in cases:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + chr(10))
        print(f"Generated {len(cases)} cases for {track} at {out_path}")


if __name__ == "__main__":
    generate_all()
