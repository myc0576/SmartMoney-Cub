"""Evidence-backed, multi-axis attribution; behavior is not trading intent.

Orders identify holding and position construction. Entry shape needs an actual
pre-entry, point-in-time context. No winning outcome or timestamp can establish
intent, psychological state, or a durable edge. Confirmation is stored by the
service separately, so deterministic evidence can always be recomputed.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
from math import isfinite
from typing import Any, Mapping, Sequence

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

VERSION = "behavior-attribution.v1"


def _stamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _shape(trip: Mapping[str, Any], context: Mapping[str, Any]) -> tuple[list[str], list[dict], list[str]]:
    decision = _stamp(trip.get("entry_time"))
    available = _stamp(context.get("available_at"))
    if not context or context.get("data_quality") != "point_in_time":
        return [], [], ["verified_pre_entry_market_context_required"]
    if not decision or not available:
        return [], [], ["availability_timestamp_required"]
    try:
        if available > decision:
            return [], [], ["future_context_rejected"]
        bars = list(context.get("bars") or [])
        if len(bars) < 20:
            return [], [], ["at_least_20_pre_entry_bars_required"]
        times = [_stamp(bar.get("available_at")) for bar in bars]
        if any(stamp is None or stamp > decision for stamp in times):
            return [], [], ["future_or_unknown_bar_availability_rejected"]
        if any(a >= b for a, b in zip(times, times[1:])):
            return [], [], ["chronological_context_required"]
    except TypeError:
        return [], [], ["timezone_alignment_required"]
    try:
        closes = [float(bar["close"]) for bar in bars[-20:]]
        highs = [float(bar["high"]) for bar in bars[-20:]]
        lows = [float(bar["low"]) for bar in bars[-20:]]
        entry = float(trip["entry_price"])
        if not all(isfinite(v) for v in closes + highs + lows + [entry]):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        return [], [], ["valid_pre_entry_prices_required"]
    direction = -1 if str(trip.get("side") or "").upper() in ("SHORT", "SELL") else 1
    mean = sum(closes) / 20
    slope = sum(closes[-5:]) / 5 - sum(closes[:5]) / 5
    labels = []
    if direction * slope > 0 and direction * (closes[-1] - mean) > 0:
        labels.append("trend_following")
    if (direction > 0 and entry > max(highs)) or (direction < 0 and entry < min(lows)):
        labels.append("breakout")
    # A counter-trend entry after a large deviation is only a hypothesis.
    variance = sum((close - mean) ** 2 for close in closes) / len(closes)
    if variance > 0 and direction * (entry - mean) < -(variance ** 0.5) and direction * slope < 0:
        labels.append("mean_reversion")
    evidence = [{"field": "pre_entry_mean_20", "observed": mean},
                {"field": "pre_entry_slope", "observed": slope},
                {"field": "prior_range", "observed": [min(lows), max(highs)]},
                {"field": "entry_price", "observed": entry},
                {"field": "context_available_at", "observed": context["available_at"]}]
    return labels, evidence, [] if labels else ["entry_shape_not_distinguishable"]


def attribute_patterns(ledger: Mapping[str, Any], *, trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    trips = list(ledger.get("round_trips") or [])
    raw = {str(trade.get("trade_id") or trade.get("fill_id")): trade for trade in trades}
    candidates: list[dict[str, Any]] = []
    counts: dict[str, Counter] = {axis: Counter() for axis in ("holding_horizon", "entry_shape", "sizing")}

    def add(trip, axis, label, evidence, missing, status="observed"):
        trade_ids = sorted({str(lot.get("lot_fill_id")) for lot in trip.get("matched_lots", []) if lot.get("lot_fill_id")})
        identity = "|".join((VERSION, str(trip.get("account_id", "")), str(trip.get("round_trip_id", "")), axis, label))
        candidates.append({
            "pattern_id": "PAT-" + sha256(identity.encode()).hexdigest()[:24],
            "round_trip_id": trip.get("round_trip_id"), "account_id": trip.get("account_id"),
            "axis": axis, "label": label, "status": status, "confidence": "low" if missing else "medium",
            "evidence": evidence, "trade_ids": trade_ids, "missing_data": missing,
            "version": VERSION, "invalidation": "Recompute when source fills, timestamps, or entry context are corrected.",
            "time_stop": "Review at the next journal review; this is not a live signal.",
            "give_up": "Do not assign a strategy when evidence is incomplete or the user rejects the hypothesis.",
            "data_source": "tenant_journal_ledger", "available_at": str(trip.get("exit_time") or "unknown"),
            "data_quality": "observed_execution" if status == "observed" else "pre_entry_candidate",
            "safety": SAFETY_DECLARATION,
        })
        counts[axis][label] += 1

    for trip in trips:
        entry_raw, exit_raw = str(trip.get("entry_time") or ""), str(trip.get("exit_time") or "")
        entry, exit_ = _stamp(entry_raw), _stamp(exit_raw)
        horizon, missing, seconds = "date_unknown", [], None
        if entry and exit_:
            days = (exit_.date() - entry.date()).days
            if days >= 0:
                horizon = "intraday" if days == 0 else "overnight_short" if days <= 2 else "swing" if days <= 20 else "position"
                if len(entry_raw) > 10 and len(exit_raw) > 10:
                    try:
                        seconds = (exit_ - entry).total_seconds()
                    except TypeError:
                        missing.append("timezone_alignment_required")
                    if seconds is not None and 0 <= seconds <= 900:
                        horizon = "brief_intraday"
                else:
                    missing.append("execution_time_required_for_scalping_hypothesis")
        else:
            missing.append("entry_and_exit_dates_required")
        add(trip, "holding_horizon", horizon, [{"field": "entry_time", "observed": entry_raw},
            {"field": "exit_time", "observed": exit_raw}, {"field": "holding_seconds", "observed": seconds}], missing)
        lots = {str(lot.get("lot_fill_id")) for lot in trip.get("matched_lots") or [] if lot.get("lot_fill_id")}
        add(trip, "sizing", "multiple_entry_fills" if len(lots) > 1 else "single_entry_fill",
            [{"field": "entry_fill_count", "observed": len(lots)}], ["order_ids_required_to_distinguish_scaling_from_partial_fills"])
        first_id = next((str(lot.get("lot_fill_id")) for lot in trip.get("matched_lots") or [] if lot.get("lot_fill_id")), "")
        source = raw.get(first_id, {})
        provenance = source.get("provenance") if isinstance(source.get("provenance"), Mapping) else {}
        context = provenance.get("entry_context") if isinstance(provenance.get("entry_context"), Mapping) else {}
        shapes, evidence, shape_missing = _shape(trip, context)
        for label in shapes or ["unknown_entry_shape"]:
            add(trip, "entry_shape", label, evidence, shape_missing, status="inferred")
    axes = {}
    for axis, distribution in counts.items():
        largest = distribution.most_common(1)
        dominant = largest[0][0] if largest and largest[0][1] >= len(trips) * 0.6 and len(trips) >= 20 else None
        axes[axis] = {"counts": dict(distribution), "dominant": dominant,
                      "label": dominant or ("insufficient_sample" if len(trips) < 20 else "mixed")}
    return {"profile": {"sample_count": len(trips), "account_count": len({trip.get("account_id") for trip in trips}),
                        "axes": axes, "data_quality": "small_sample" if len(trips) < 20 else "descriptive",
                        "limitations": ["Behavior is not intent; confirm or reject candidate labels.",
                                        "Holding horizon and entry strategy are independent axes.",
                                        "Orders alone cannot establish trend, breakout, or mean-reversion intent.",
                                        "Positive historical returns do not establish a durable edge."]},
            "candidates": candidates, "version": VERSION, "safety": SAFETY_DECLARATION}
