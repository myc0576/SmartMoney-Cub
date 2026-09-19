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
            "name": f"tape_feed_{s_i}",
            "fetch_time": "2026-09-15T09:00:00Z",
            "available_at": "2026-09-15T09:00:00Z",
            "data_quality_flag": qual,
        }
        for s_i in range(num_srcs)
    ]

    if contra:
        gt_sufficiency = "contradictory"
    elif qual == "stale":
        gt_sufficiency = "partial" if num_srcs >= 2 else "insufficient"
    elif num_srcs >= 2 and qual == "ok":
        gt_sufficiency = "sufficient"
    elif num_srcs == 1:
        gt_sufficiency = "partial"
    else:
        gt_sufficiency = "insufficient"

    gt_counter = counter

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

    narrative_parts = [f"Trade execution log for asset {idx:02d} initiated during regular trading hours."]
    if contra:
        narrative_parts.append(
            "Initial scanner indicated strong buying pressure, but subsequent tick data showed heavy block liquidation at resistance."
        )
    elif num_srcs >= 2 and qual == "ok":
        narrative_parts.append(
            f"Pre-trade scan verified clean signals across {num_srcs} corroborating independent market feeds."
        )
    elif num_srcs == 1:
        narrative_parts.append(
            "Setup was derived from a single incoming feed without secondary confirmation."
        )
    else:
        narrative_parts.append(
            "Trade was executed without live source capture in the terminal journal."
        )

    if counter:
        narrative_parts.append(
            "Significant adverse block flow and heavy opposing limit orders were detected in the order book."
        )
    else:
        narrative_parts.append(
            "No conflicting order book imbalance or institutional block flow opposed the position."
        )

    if rule_vio:
        narrative_parts.append(
            "The account manager bypassed standard max-position sizing parameters and ignored the pre-set risk threshold."
        )
    elif timing_err:
        narrative_parts.append(
            "Position was entered prematurely well ahead of the confirmation bar and exit execution lagged the stop trigger."
        )
    elif qual == "stale":
        narrative_parts.append(
            "Data feed timestamps lagged the live matching engine by several update intervals."
        )

    narrative_parts.append(
        f"Position closed with an equity variation of {ret:+.1f}% representing a realized drawdown of ${loss:,.2f}."
    )
    post_trade_notes = " ".join(narrative_parts)

    state = {
        "case_id": case_id,
        "symbol": f"TR.{split.upper()[:2]}{idx:02d}",
        "decision_time": "2026-09-15T09:30:00Z",
        "available_at": "2026-09-15T09:30:00Z",
        "data_sources": data_sources,
        "loss_amount": loss,
        "return_pct": ret,
        "notes": post_trade_notes,
    }

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
            "name": f"sec_edgar_doc_{s_i}",
            "fetch_time": "2026-09-15T08:00:00Z",
            "available_at": "2026-09-15T08:00:00Z",
            "data_quality_flag": "ok",
        }
        for s_i in range(num_srcs)
    ]

    gt_supports = not contra and (idx % 3 != 0) and gap_flag != "critical"
    gt_contra = contra

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

    gt_gap = gap_flag

    prose_parts = [
        f"Periodic financial report excerpt for reporting entity {idx:02d}.",
        f"Consolidated statements report a top-line trajectory delta of {rev_change:+.1f}% year-over-year, while operating bottom-line earnings adjusted by {net_change:+.1f}% across audited segments.",
    ]
    if contra:
        prose_parts.append(
            "Management discussion notes accelerating core operational margins, yet the attached cash flow reconciliation reveals negative operational cash generation and unpaid vendor invoices."
        )
    elif gt_supports:
        prose_parts.append(
            "Management discussion and segment breakdown confirm that underlying unit volume and margin metrics fully align with the reported outlook."
        )
    else:
        prose_parts.append(
            "Footnotes highlight that reported gains were driven by one-off asset disposals rather than continuing core commercial activities."
        )

    if gap_flag == "critical":
        prose_parts.append(
            "Key financial footnotes omit revenue recognition policies, segment liability schedules, and required auditor sign-off."
        )
    elif gap_flag == "significant":
        prose_parts.append(
            "Omission of geographic revenue splits and off-balance sheet lease commitments impedes full comparative evaluation."
        )
    elif gap_flag == "minor":
        prose_parts.append(
            "Peripheral subsidiary reports omit supplemental regional breakdown notes."
        )
    else:
        prose_parts.append(
            "All statutory schedules, footnotes, accounting policy notes, and auditor reconciliations are exhaustively provided."
        )

    prose_parts.append(f"Filing packet includes verification across {num_srcs} independent regulatory document attachments.")
    filing_prose = " ".join(prose_parts)

    state = {
        "case_id": case_id,
        "symbol": f"FF.{split.upper()[:2]}{idx:02d}",
        "decision_time": "2026-09-15T08:30:00Z",
        "available_at": "2026-09-15T08:30:00Z",
        "data_sources": data_sources,
        "revenue_change_pct": rev_change,
        "net_income_change_pct": net_change,
        "filing_disclosure_excerpt": filing_prose,
    }

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

    gt_class = raw_cat
    if raw_cat == "macroeconomic":
        gt_scope = "cross-industry"
    elif raw_cat == "regulatory" and raw_scope == "firm-specific":
        gt_scope = "subsector"
    else:
        gt_scope = raw_scope

    if raw_cat == "technological":
        gt_duration = "structural"
    elif raw_cat == "regulatory" and raw_duration == "transitory":
        gt_duration = "medium-term"
    else:
        gt_duration = raw_duration

    gt_epistemic = raw_epistemic
    if raw_cat == "supply-chain":
        gt_sc = "direct"
    elif raw_cat in ("technological", "regulatory"):
        gt_sc = "indirect"
    else:
        gt_sc = raw_sc

    wire_parts = [f"Industrial wire report #{idx:02d} dispatched from sector monitoring desk."]
    if raw_cat == "regulatory":
        wire_parts.append(
            "State oversight commissions issued an enforceable statutory ruling mandating revised emissions compliance standards."
        )
    elif raw_cat == "technological":
        wire_parts.append(
            "A proprietary semiconductor architecture breakthrough demonstrated a tenfold leap in silicon computing efficiency."
        )
    elif raw_cat == "competitive":
        wire_parts.append(
            "A primary market challenger launched aggressive discounting to undercut market pricing across domestic channels."
        )
    elif raw_cat == "supply-chain":
        wire_parts.append(
            "Severe shipping bottlenecks and customs strikes halted transit at major marine freight hubs."
        )
    elif raw_cat == "macroeconomic":
        wire_parts.append(
            "Broad foreign exchange volatility and rising national interest burdens constrained aggregate industrial capital expenditure."
        )
    else:
        wire_parts.append(
            "An unscheduled executive transition and leadership reorganization was announced during the quarterly meeting."
        )

    if gt_scope == "cross-industry":
        wire_parts.append(
            "Implications cascade across modern manufacturing, distribution networks, banking, and consumer markets nationwide."
        )
    elif gt_scope == "broad-industry":
        wire_parts.append(
            "Every enterprise and vendor operating within the broader industrial group will need adjustments."
        )
    elif gt_scope == "subsector":
        wire_parts.append(
            "The development is concentrated specifically among specialized fabrication foundries."
        )
    else:
        wire_parts.append(
            "Operations at peer enterprises remain unaffected, with exposure limited strictly to the named enterprise."
        )

    if gt_duration == "structural":
        wire_parts.append(
            "Industry analysts project permanent architectural realignment across global markets spanning future decades."
        )
    elif gt_duration == "medium-term":
        wire_parts.append(
            "Market participants expect equilibrium to return over a horizon of several quarters."
        )
    elif gt_duration == "short-term":
        wire_parts.append(
            "Inventory cushions indicate operations will normalize within several weeks."
        )
    else:
        wire_parts.append(
            "The disruption represents a momentary trading halt that was resolved by day-end."
        )

    if raw_epistemic == "fact":
        wire_parts.append(
            "Verified by certified legal decrees, bill-of-lading manifests, and signed audit filings."
        )
    elif raw_epistemic == "management-view":
        wire_parts.append(
            "Asserted by corporate spokespersons and executive leadership during an unscheduled investor webcast."
        )
    else:
        wire_parts.append(
            "Extrapolated by sector commentary desks from ambient shipment flows and anonymous channel checks."
        )

    if gt_sc == "direct":
        wire_parts.append(
            "Immediate component delivery halts and assembly line stoppages were confirmed at tier-one plants."
        )
    elif gt_sc == "indirect":
        wire_parts.append(
            "Finished goods assembly continues uninterrupted, though upstream research cycles may face peripheral friction."
        )
    else:
        wire_parts.append(
            "Field monitors note that logistical telemetry data remains too sparse to gauge component availability."
        )

    wire_text = " ".join(wire_parts)

    state = {
        "event_id": f"EVT_{split.upper()[:2]}{idx:02d}",
        "decision_time": "2026-09-15T12:00:00Z",
        "available_at": "2026-09-15T12:00:00Z",
        "data_sources": [
            {
                "name": "industry_wire_feed",
                "fetch_time": "2026-09-15T11:55:00Z",
                "available_at": "2026-09-15T11:55:00Z",
                "data_quality_flag": "ok",
            }
        ],
        "event_wire_dispatch": wire_text,
    }

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

    gt_stance = raw_stance
    if raw_stance == "hawkish":
        gt_direction = "liquidity" if idx % 2 == 0 else "inflation"
    elif raw_stance == "dovish":
        gt_direction = "growth" if idx % 2 == 0 else "liquidity"
    else:
        gt_direction = raw_direction

    if raw_direction in ("policy", "liquidity") and raw_horizon == "immediate":
        gt_horizon = "near"
    else:
        gt_horizon = raw_horizon

    comm_parts = [f"Official monetary authority bulletin release #{idx:02d}."]
    if raw_stance == "hawkish":
        comm_parts.append(
            "The committee observed persistent consumer price pressures remaining substantially above the long-run objective, unanimously voting to tighten lending benchmarks and accelerate balance sheet runoff."
        )
    elif raw_stance == "dovish":
        comm_parts.append(
            "Noting rising unemployment indicators and weakening consumer demand, the board authorized an accommodative adjustment to lower short-term lending rates and purchase high-quality sovereign assets."
        )
    elif raw_stance == "neutral":
        comm_parts.append(
            "Current benchmark settings remain well-calibrated to balanced employment and price trends, warranting an unchanged policy rate while monitoring incoming indicators."
        )
    else:
        comm_parts.append(
            "Committee members diverged sharply, acknowledging firm cost pressures in services alongside emerging credit contraction, opting for a provisional split decision without forward commitment."
        )

    if gt_direction == "liquidity":
        comm_parts.append(
            "The primary operational adjustments target interbank reserve absorption, discount window facilities, and overnight repo volumes."
        )
    elif gt_direction == "inflation":
        comm_parts.append(
            "Deliberations centered squarely on anchoring medium-term price expectations and preventing wage-spiral passthrough."
        )
    elif gt_direction == "growth":
        comm_parts.append(
            "Strategic priorities focus on stimulating industrial investment and underwriting private sector credit formation."
        )
    else:
        comm_parts.append(
            "The communique emphasizes long-term institutional frameworks, statutory bank capital requirements, and systemic governance mandates."
        )

    if gt_horizon == "immediate":
        comm_parts.append(
            "Statutory rate adjustments and open-market interventions take effect with next-day clearing."
        )
    elif gt_horizon == "near":
        comm_parts.append(
            "Macroeconomic effects are projected to transmit through commercial credit channels across the next fiscal quarter."
        )
    elif gt_horizon == "medium":
        comm_parts.append(
            "Policy transmission is expected to influence capital investment decisions over an extended multi-year cycle."
        )
    else:
        comm_parts.append(
            "The legal statutes introduce permanent shifts to the fundamental architecture of the financial system."
        )

    policy_excerpt = " ".join(comm_parts)

    state = {
        "policy_id": f"BULLETIN_{split.upper()[:2]}{idx:02d}",
        "decision_time": "2026-09-15T14:00:00Z",
        "available_at": "2026-09-15T14:00:00Z",
        "data_sources": [
            {
                "name": "central_bank_bulletin",
                "fetch_time": "2026-09-15T13:45:00Z",
                "available_at": "2026-09-15T13:45:00Z",
                "data_quality_flag": "ok",
            }
        ],
        "statement_excerpt": policy_excerpt,
    }

    labels = {
        "policy_stance": gt_stance,
        "macro_direction": gt_direction,
        "impact_horizon": gt_horizon,
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
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
        print(f"Generated {len(cases)} cases for {track} at {out_path}")


if __name__ == "__main__":
    generate_all()
