from __future__ import annotations
import re
from typing import Any
from smartmoney_cub_harness.benchmark.cases import (
    TRACK_FINANCIAL_FILINGS, TRACK_INDUSTRY_EVENTS, TRACK_MACRO_POLICY, TRACK_TRADING_REVIEW, BenchmarkCase,
)

def baseline_predictions(case: BenchmarkCase) -> dict[str, Any]:
    """Produce honest heuristic rule-based baseline predictions from observable evidence.
    A heuristic baseline relies on simple cues (source counts, return magnitude, headline words).
    It makes realistic errors on complex or nuanced cases.
    """
    state = case.state
    track = case.track

    if track == TRACK_TRADING_REVIEW:
        sources = state.get("data_sources", [])
        loss = float(state.get("loss_amount", 0.0))
        ret = float(state.get("return_pct", 0.0))
        notes = str(state.get("notes", "")).lower()
        has_stale = any(s.get("data_quality_flag") == "stale" for s in sources if isinstance(s, dict))

        # 1. Evidence sufficiency
        if len(sources) >= 2 and not has_stale:
            sufficiency = "sufficient"
        elif len(sources) >= 1:
            sufficiency = "partial"
        else:
            sufficiency = "insufficient"

        # 2. Major counter evidence
        has_counter = ("adverse" in notes or "opposing" in notes)

        # 3. Failure mode
        if "bypassed" in notes or "threshold" in notes:
            failure_mode = "discipline"
        elif has_stale:
            failure_mode = "data-quality"
        elif len(sources) == 0:
            failure_mode = "insufficient-evidence"
        elif "prematurely" in notes:
            failure_mode = "timing"
        elif ret < -5.0:
            failure_mode = "thesis"
        else:
            failure_mode = "luck"

        # 4. Review priority
        if loss > 3000 or ret < -12.0:
            priority = 5
        elif loss > 1500 or ret < -6.0:
            priority = 4
        elif loss > 400 or ret < 0:
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
        sources = state.get("data_sources", [])
        sources_count = len(sources)
        rev_change = abs(float(state.get("revenue_change_pct", 0.0)))
        net_change = abs(float(state.get("net_income_change_pct", 0.0)))
        max_change = max(rev_change, net_change)
        prose = str(state.get("filing_disclosure_excerpt", "")).lower()

        contra = ("negative operational" in prose or "unpaid" in prose)
        supports = (not contra and "confirm" in prose)

        if max_change >= 25.0:
            materiality = "high"
        elif max_change >= 10.0:
            materiality = "medium"
        elif max_change >= 2.0:
            materiality = "low"
        else:
            materiality = "immaterial"

        if "omit" in prose or "omission" in prose:
            info_gap = "significant"
        elif "supplemental" in prose:
            info_gap = "minor"
        else:
            info_gap = "none"

        if contra:
            evidence_quality = 1
        elif sources_count >= 3:
            evidence_quality = 4
        elif sources_count >= 2:
            evidence_quality = 3
        else:
            evidence_quality = 2

        return {
            "disclosure_supports_conclusion": supports,
            "internal_contradiction": contra,
            "materiality_of_change": materiality,
            "evidence_quality": evidence_quality,
            "information_gap": info_gap,
        }

    if track == TRACK_INDUSTRY_EVENTS:
        wire = str(state.get("event_wire_dispatch", "")).lower()

        # Honest keyword heuristic for industry-events
        if "emissions" in wire or "statutory" in wire:
            event_class = "regulatory"
        elif "semiconductor" in wire or "silicon" in wire:
            event_class = "technological"
        elif "discounting" in wire or "challenger" in wire:
            event_class = "competitive"
        elif "shipping" in wire or "freight" in wire:
            event_class = "supply-chain"
        elif "foreign exchange" in wire:
            event_class = "macroeconomic"
        else:
            event_class = "other"

        if "nationwide" in wire or "modern manufacturing" in wire:
            scope = "cross-industry"
        elif "broader industrial" in wire:
            scope = "broad-industry"
        elif "foundries" in wire:
            scope = "subsector"
        else:
            scope = "firm-specific"

        # Naive rule baseline defaults short disruptions to short-term, missing nuanced transitory cases
        if "permanent" in wire or "decades" in wire:
            dur = "structural"
        elif "quarters" in wire:
            dur = "medium-term"
        else:
            dur = "short-term"

        if "certified" in wire:
            epistemic = "fact"
        elif "spokespersons" in wire or "webcast" in wire:
            epistemic = "management-view"
        else:
            epistemic = "inference"

        if "stoppages" in wire or "halts" in wire:
            sc_impact = "direct"
        elif "upstream" in wire:
            sc_impact = "indirect"
        else:
            sc_impact = "insufficient"

        return {
            "event_class": event_class,
            "impact_scope": scope,
            "duration": dur,
            "epistemic_status": epistemic,
            "supply_chain_impact": sc_impact,
        }

    if track == TRACK_MACRO_POLICY:
        excerpt = str(state.get("statement_excerpt", "")).lower()

        if "tighten" in excerpt or "price pressures" in excerpt:
            stance = "hawkish"
        elif "accommodative" in excerpt or "lower" in excerpt:
            stance = "dovish"
        elif "unchanged" in excerpt:
            stance = "neutral"
        else:
            stance = "mixed"

        if "reserve" in excerpt or "repo" in excerpt:
            direction = "liquidity"
        elif "expectations" in excerpt or "wage" in excerpt:
            direction = "inflation"
        elif "investment" in excerpt or "credit" in excerpt:
            direction = "growth"
        else:
            direction = "policy"

        if "next-day" in excerpt:
            horizon = "immediate"
        elif "quarter" in excerpt:
            horizon = "near"
        elif "multi-year" in excerpt:
            horizon = "medium"
        else:
            horizon = "structural"

        return {
            "policy_stance": stance,
            "macro_direction": direction,
            "impact_horizon": horizon,
        }

    raise ValueError(f"unknown track {track}")