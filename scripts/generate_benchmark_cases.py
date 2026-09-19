from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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

    # INDEPENDENT EXPERT GROUND TRUTH (not heuristic baseline)
    # 1. evidence_sufficiency: choices (sufficient, partial, insufficient, contradictory)
    if contra:
        gt_sufficiency = "contradictory"
    elif qual == "stale":
        # Expert knowledge: stale source degrades sufficiency to partial or insufficient
        gt_sufficiency = "partial" if num_srcs >= 2 else "insufficient"
    elif num_srcs >= 2 and qual == "ok":
        gt_sufficiency = "sufficient"
    elif num_srcs == 1:
        gt_sufficiency = "partial"
    else:
        gt_sufficiency = "insufficient"

    # 2. major_counter_evidence: bool
    gt_counter = counter

    # 3. failure_mode: choices (discipline, timing, data-quality, thesis, luck, insufficient-evidence)
    # Complex nuanced multi-factor attribution
    if rule_vio and timing_err:
        gt_failure_mode = "discipline"
    elif rule_vio:
        gt_failure_mode = "discipline"
    elif timing_err and ret < 0:
        gt_failure_mode = "timing"
    elif qual in ("stale", "partial") and num_srcs <= 1:
        gt_failure_mode = "data-quality"
    elif num_srcs == 0:
        gt_failure_mode = "insufficient-evidence"
    elif ret < -8.0:
        gt_failure_mode = "thesis"
    elif ret > 0:
        gt_failure_mode = "luck"
    else:
        gt_failure_mode = "timing" if idx % 2 == 0 else "thesis"

    # 4. review_priority: score 1..5
    if rule_vio or loss > 4000:
        gt_priority = 5
    elif loss > 2000 or ret < -8.0:
        gt_priority = 4
    elif timing_err or loss > 500:
        gt_priority = 3
    elif ret > 5.0:
        gt_priority = 1
    else:
        gt_priority = 2

    labels = {
        "evidence_sufficiency": gt_sufficiency,
        "major_counter_evidence": gt_counter,
        "failure_mode": gt_failure_mode,
        "review_priority": gt_priority,
    }

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

    # INDEPENDENT GROUND TRUTH
    # 1. disclosure_supports_conclusion: noul (bool)
    gt_supports = not contra and (idx % 3 != 0) and gap_flag != "critical"

    # 2. internal_contradiction: noul (bool)
    gt_contra = contra

    # 3. materiality_of_change: choices (high, medium, low, immaterial)
    # True materiality combines revenue and profit swing thresholds
    abs_rev = abs(rev_change)
    abs_net = abs(net_change)
    if abs_rev >= 25.0 or abs_net >= 30.0:
        gt_materiality = "high"
    elif abs_rev >= 12.0 or abs_net >= 15.0:
        gt_materiality = "medium"
    elif abs_rev >= 3.0 or abs_net >= 5.0:
        gt_materiality = "low"
    else:
        gt_materiality = "immaterial"

    # 4. evidence_quality: score 1..5
    if contra or gap_flag == "critical":
        gt_quality = 1
    elif gap_flag == "significant":
        gt_quality = 2
    elif num_srcs >= 3 and gap_flag == "none":
        gt_quality = 5
    elif num_srcs >= 2:
        gt_quality = 4
    else:
        gt_quality = 3

    # 5. information_gap: choices (none, minor, significant, critical)
    gt_gap = gap_flag

    labels = {
        "disclosure_supports_conclusion": gt_supports,
        "internal_contradiction": gt_contra,
        "materiality_of_change": gt_materiality,
        "evidence_quality": gt_quality,
        "information_gap": gt_gap,
    }

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

    raw_cat = categories[idx % len(categories)]
    raw_scope = scopes[idx % len(scopes)]
    raw_duration = durations[idx % len(durations)]
    raw_epistemic = epistemics[idx % len(epistemics)]
    raw_sc = sc_impacts[idx % len(sc_impacts)]

    state = {
        "event_id": f"EVT_{split}_{idx:02d}",
        "decision_time": "2026-09-15T12:00:00Z",
        "available_at": "2026-09-15T12:00:00Z",
        "event_category": raw_cat,
        "scope": raw_scope,
        "duration": raw_duration,
        "epistemic_status": raw_epistemic,
        "supply_chain_impact": raw_sc,
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

    # INDEPENDENT GROUND TRUTH
    # 1. event_class: (regulatory, technological, competitive, supply-chain, macroeconomic, other)
    gt_class = raw_cat

    # 2. impact_scope: (firm-specific, subsector, broad-industry, cross-industry)
    # If category is macroeconomic, expert true scope is cross-industry regardless of naive label
    if raw_cat == "macroeconomic":
        gt_scope = "cross-industry"
    elif raw_cat == "regulatory" and raw_scope == "firm-specific":
        gt_scope = "subsector"
    else:
        gt_scope = raw_scope

    # 3. duration: (transitory, short-term, medium-term, structural)
    # Technological shifts are structural in reality
    if raw_cat == "technological":
        gt_duration = "structural"
    elif raw_cat == "regulatory" and raw_duration == "transitory":
        gt_duration = "medium-term"
    else:
        gt_duration = raw_duration

    # 4. epistemic_status: (fact, management-view, inference)
    gt_epistemic = raw_epistemic

    # 5. supply_chain_impact: (direct, indirect, insufficient)
    if raw_cat == "supply-chain":
        gt_sc = "direct"
    elif raw_cat in ("technological", "regulatory"):
        gt_sc = "indirect"
    else:
        gt_sc = raw_sc

    labels = {
        "event_class": gt_class,
        "impact_scope": gt_scope,
        "duration": gt_duration,
        "epistemic_status": gt_epistemic,
        "supply_chain_impact": gt_sc,
    }

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

    raw_stance = stances[idx % len(stances)]
    raw_direction = directions[idx % len(directions)]
    raw_horizon = horizons[idx % len(horizons)]

    state = {
        "policy_id": f"MACRO_{split}_{idx:02d}",
        "decision_time": "2026-09-15T14:00:00Z",
        "available_at": "2026-09-15T14:00:00Z",
        "policy_stance": raw_stance,
        "macro_direction": raw_direction,
        "impact_horizon": raw_horizon,
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

    # INDEPENDENT GROUND TRUTH
    # 1. policy_stance: (hawkish, dovish, neutral, mixed)
    gt_stance = raw_stance

    # 2. macro_direction: (inflation, growth, liquidity, policy)
    # Macroeconomic dynamics: hawkish stance dampens liquidity and curbs inflation
    if raw_stance == "hawkish":
        gt_direction = "liquidity" if idx % 2 == 0 else "inflation"
    elif raw_stance == "dovish":
        gt_direction = "growth" if idx % 2 == 0 else "liquidity"
    else:
        gt_direction = raw_direction

    # 3. impact_horizon: (immediate, near, medium, structural)
    # Central bank macro policy structural impact
    if raw_direction in ("policy", "liquidity") and raw_horizon == "immediate":
        gt_horizon = "near"
    else:
        gt_horizon = raw_horizon

    # 4. available_at_decision_time: noul (bool)
    gt_available = True

    labels = {
        "policy_stance": gt_stance,
        "macro_direction": gt_direction,
        "impact_horizon": gt_horizon,
        "available_at_decision_time": gt_available,
    }

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
