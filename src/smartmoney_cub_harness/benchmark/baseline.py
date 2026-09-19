from __future__ import annotations

from typing import Any

from smartmoney_cub_harness.benchmark.cases import (
    TRACK_FINANCIAL_FILINGS,
    TRACK_INDUSTRY_EVENTS,
    TRACK_MACRO_POLICY,
    TRACK_TRADING_REVIEW,
    BenchmarkCase,
)


def baseline_predictions(case: BenchmarkCase) -> dict[str, Any]:
    """Produce deterministic rule-based baseline predictions for a BenchmarkCase."""
    state = case.state
    track = case.track

    if track == TRACK_TRADING_REVIEW:
        # Rules:
        # 1. evidence_sufficiency: if data_sources length >= 2 and data_quality_flag == 'ok': sufficient,
        #    elif data_sources length >= 1: partial, else insufficient.
        #    If contradiction flag in state: contradictory.
        # 2. major_counter_evidence: bool, check if state['has_counter_evidence'] or 'counter_evidence' in state
        # 3. failure_mode: based on return or state cues
        # 4. review_priority: 1..5 based on severity or loss
        sources = state.get("data_sources", [])
        has_contra = bool(state.get("has_contradiction", False))
        has_counter = bool(state.get("has_counter_evidence", False))
        ret = float(state.get("return_pct", 0.0))
        loss = float(state.get("loss_amount", 0.0))
        qual = state.get("data_quality_flag", "ok")

        if has_contra:
            sufficiency = "contradictory"
        elif len(sources) >= 2 and qual == "ok":
            sufficiency = "sufficient"
        elif len(sources) >= 1:
            sufficiency = "partial"
        else:
            sufficiency = "insufficient"

        if state.get("rule_violation"):
            failure_mode = "discipline"
        elif qual in ("stale", "partial", "error"):
            failure_mode = "data-quality"
        elif len(sources) == 0:
            failure_mode = "insufficient-evidence"
        elif state.get("timing_error"):
            failure_mode = "timing"
        elif ret < -5.0:
            failure_mode = "thesis"
        else:
            failure_mode = "luck"

        if loss > 5000 or ret < -10.0:
            priority = 5
        elif loss > 2000 or ret < -5.0:
            priority = 4
        elif loss > 500 or ret < 0:
            priority = 3
        elif ret > 5.0:
            priority = 1
        else:
            priority = 2

        return {
            "evidence_sufficiency": sufficiency,
            "major_counter_evidence": has_counter,
            "failure_mode": failure_mode,
            "review_priority": priority,
        }

    if track == TRACK_FINANCIAL_FILINGS:
        # Questions: disclosure_supports_conclusion, internal_contradiction, materiality_of_change, evidence_quality, information_gap
        contra = bool(state.get("has_internal_contradiction", False))
        rev_change = abs(float(state.get("revenue_change_pct", 0.0)))
        net_change = abs(float(state.get("net_income_change_pct", 0.0)))
        max_change = max(rev_change, net_change)
        sources_count = len(state.get("data_sources", []))
        gap_flag = state.get("gap_level", "none")

        supports = bool(state.get("thesis_supported", not contra))

        if max_change >= 30.0:
            materiality = "high"
        elif max_change >= 10.0:
            materiality = "medium"
        elif max_change >= 2.0:
            materiality = "low"
        else:
            materiality = "immaterial"

        if sources_count >= 3 and not contra:
            evidence_quality = 5
        elif sources_count >= 2 and not contra:
            evidence_quality = 4
        elif sources_count >= 1 and not contra:
            evidence_quality = 3
        elif contra:
            evidence_quality = 1
        else:
            evidence_quality = 2

        info_gap = gap_flag if gap_flag in ("none", "minor", "significant", "critical") else "minor"

        return {
            "disclosure_supports_conclusion": supports,
            "internal_contradiction": contra,
            "materiality_of_change": materiality,
            "evidence_quality": evidence_quality,
            "information_gap": info_gap,
        }

    if track == TRACK_INDUSTRY_EVENTS:
        # Questions: event_class, impact_scope, duration, epistemic_status, supply_chain_impact
        raw_cat = state.get("event_category", "other")
        if raw_cat in ("regulatory", "technological", "competitive", "supply-chain", "macroeconomic", "other"):
            event_class = raw_cat
        else:
            event_class = "other"

        scope = state.get("scope", "firm-specific")
        if scope not in ("firm-specific", "subsector", "broad-industry", "cross-industry"):
            scope = "firm-specific"

        dur = state.get("duration", "short-term")
        if dur not in ("transitory", "short-term", "medium-term", "structural"):
            dur = "short-term"

        epistemic = state.get("epistemic_status", "fact")
        if epistemic not in ("fact", "management-view", "inference"):
            epistemic = "fact"

        sc_impact = state.get("supply_chain_impact", "indirect")
        if sc_impact not in ("direct", "indirect", "insufficient"):
            sc_impact = "indirect"

        return {
            "event_class": event_class,
            "impact_scope": scope,
            "duration": dur,
            "epistemic_status": epistemic,
            "supply_chain_impact": sc_impact,
        }

    if track == TRACK_MACRO_POLICY:
        # Questions: policy_stance, macro_direction, impact_horizon, available_at_decision_time
        stance = state.get("policy_stance", "neutral")
        if stance not in ("hawkish", "dovish", "neutral", "mixed"):
            stance = "neutral"

        direction = state.get("macro_direction", "growth")
        if direction not in ("inflation", "growth", "liquidity", "policy"):
            direction = "growth"

        horizon = state.get("impact_horizon", "near")
        if horizon not in ("immediate", "near", "medium", "structural"):
            horizon = "near"

        avail_at_dt = bool(state.get("available_at_decision_time", True))

        return {
            "policy_stance": stance,
            "macro_direction": direction,
            "impact_horizon": horizon,
            "available_at_decision_time": avail_at_dt,
        }

    raise ValueError(f"unknown track '{track}'")
