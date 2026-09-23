"""Insight engine: deterministic mistake clustering and edge extraction.

Designed for global journals to describe recurring behaviors and candidate
performance groups without inferring intent. Purely deterministic, offline-capable, and
strictly adhering to the read-only execution ban and observation contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from smartmoney_cub_harness.analytics import DIMENSIONS, group_performance
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

CLUSTER_KINDS: tuple[str, ...] = (
    "broken_invalidation_unstopped",
    "early_morning_exit",
    "one_day_holding",
    "revenge_reentry",
)

EDGE_DIMENSIONS: tuple[str, ...] = ("tag", "regime", "holding")

OBSERVATION_FALLBACK = "unknown"


def _parse_iso_or_parts(date_str: str, time_str: str = "") -> datetime | None:
    text = f"{date_str} {time_str}".strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
        "%Y%m%d %H%M%S",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_time_or_fallback(dt: datetime | None) -> str:
    return dt.isoformat(timespec="seconds") if dt else OBSERVATION_FALLBACK


def _round(val: float, digits: int = 2) -> float:
    return round(float(val), digits)


def cluster_mistakes(
    ledger: Mapping[str, Any],
    *,
    trades: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Cluster closed round trips and raw trade executions into candidate mistake clusters."""
    round_trips = list(ledger.get("round_trips") or [])
    raw_trades = list(trades or [])

    # Map trade_id -> raw trade info
    trade_by_id: dict[str, Mapping[str, Any]] = {
        str(t.get("trade_id") or t.get("fill_id")): t
        for t in raw_trades
        if t.get("trade_id") or t.get("fill_id")
    }

    # Buckets for each mistake kind
    buckets: dict[str, list[dict[str, Any]]] = {kind: [] for kind in CLUSTER_KINDS}
    evidence_map: dict[str, list[dict[str, Any]]] = {kind: [] for kind in CLUSTER_KINDS}

    # 1. Evaluate round trips
    for trip in round_trips:
        rt_id = str(trip.get("round_trip_id", ""))
        matched_lots = list(trip.get("matched_lots") or [])

        # Collect associated trade_ids
        trip_trade_ids: list[str] = []
        for lot in matched_lots:
            lot_fill_id = str(lot.get("lot_fill_id", ""))
            if lot_fill_id:
                trip_trade_ids.append(lot_fill_id)

        inval_price = trip.get("invalidation_price")
        exit_price = trip.get("exit_price")
        net_pnl = float(trip.get("net_pnl") or 0.0)

        # Kind A: 跌破 invalidation_price 未离场 (exit_price < invalidation_price 且亏损)
        if inval_price is not None and exit_price is not None:
            try:
                inv_val = float(inval_price)
                ext_val = float(exit_price)
                short = str(trip.get("side") or "").upper() in ("SHORT", "SELL")
                if (ext_val > inv_val if short else ext_val < inv_val) and net_pnl < 0:
                    buckets["broken_invalidation_unstopped"].append(trip)
                    evidence_map["broken_invalidation_unstopped"].append({
                        "field": "exit_price",
                        "comparator": ">" if short else "<",
                        "threshold": inv_val,
                        "observed": ext_val,
                        "round_trip_id": rt_id,
                    })
            except (ValueError, TypeError):
                pass

        # Kind B: 开盘 15 分钟内平仓 (exit_time between 09:30:00 and 09:45:00)
        exit_time_str = str(trip.get("exit_time") or "").strip()
        time_part = ""
        if " " in exit_time_str:
            time_part = exit_time_str.split(" ", 1)[1]
        elif "T" in exit_time_str:
            time_part = exit_time_str.split("T", 1)[1]

        # Session-open rules need a declared market/session. A global journal
        # cannot interpret every 09:30 as the opening of a Chinese exchange.
        source_market = str(trip.get("market") or next((trade_by_id[fid].get("market") for fid in trip_trade_ids if fid in trade_by_id and trade_by_id[fid].get("market")), ""))
        if time_part and source_market == "CN-A":
            # Normalize to HH:MM:SS
            parts = time_part.split(":")
            if len(parts) >= 2:
                try:
                    hh = int(parts[0])
                    mm = int(parts[1])
                except ValueError:
                    continue
                # 09:30:00 to 09:45:00
                if hh == 9 and 30 <= mm <= 45:
                    buckets["early_morning_exit"].append(trip)
                    evidence_map["early_morning_exit"].append({
                        "field": "exit_time",
                        "comparator": "between",
                        "threshold": "09:30:00 - 09:45:00",
                        "observed": time_part,
                        "round_trip_id": rt_id,
                    })

        # Kind C: 持仓仅 1 日 (holding_days == 1)
        holding_days = int(trip.get("holding_days") or 0)
        if holding_days == 1:
            buckets["one_day_holding"].append(trip)
            evidence_map["one_day_holding"].append({
                "field": "holding_days",
                "comparator": "==",
                "threshold": 1,
                "observed": holding_days,
                "round_trip_id": rt_id,
            })

    # Kind D: 连续亏损后 10 分钟内再次开仓 (Revenge reentry)
    # Check if a BUY occurs within 10 minutes of a losing SELL
    # Sort all executions chronologically
    sorted_trades: list[tuple[datetime, Mapping[str, Any]]] = []
    for t in raw_trades:
        if not t.get("trade_time"):
            continue
        dt = _parse_iso_or_parts(str(t.get("trade_date") or ""), str(t.get("trade_time") or ""))
        if dt:
            sorted_trades.append((dt, t))
    sorted_trades.sort(key=lambda x: x[0].isoformat())

    # Find losing exit times from round_trips
    losing_exits: list[tuple[datetime, str, str, str]] = []
    for trip in round_trips:
        if float(trip.get("net_pnl") or 0.0) < 0:
            dt = _parse_iso_or_parts(str(trip.get("exit_time") or ""))
            if dt and len(str(trip.get("exit_time") or "")) > 10:
                lot_ids = [str(lot.get("lot_fill_id") or "") for lot in trip.get("matched_lots") or []]
                account = str(trip.get("account_id") or next((trade_by_id[fid].get("account_id", "") for fid in lot_ids if fid in trade_by_id), ""))
                losing_exits.append((dt, str(trip.get("round_trip_id") or ""), account, str(trip.get("symbol") or "")))

    revenge_trips: list[dict[str, Any]] = []
    for exit_dt, rt_id, account_id, symbol in losing_exits:
        for buy_dt, buy_trade in sorted_trades:
            if str(buy_trade.get("account_id") or "") != account_id or str(buy_trade.get("symbol") or "") != symbol:
                continue
            if str(buy_trade.get("side", "")).upper() == "BUY":
                try:
                    delta_sec = (buy_dt - exit_dt).total_seconds()
                except TypeError:
                    continue
                if 0 <= delta_sec <= 600:  # within 10 minutes
                    # Link to the round_trip containing this buy, or synthesized trip
                    buy_id = str(buy_trade.get("trade_id") or buy_trade.get("fill_id"))
                    matching_trip = None
                    for trip in round_trips:
                        for lot in trip.get("matched_lots") or []:
                            if str(lot.get("lot_fill_id")) == buy_id:
                                matching_trip = trip
                                break
                        if matching_trip:
                            break
                    target_obj = matching_trip if matching_trip else {
                        "round_trip_id": f"RT-REVENGE-{buy_id}",
                        "net_pnl": 0.0,
                        "return_pct": 0.0,
                        "entry_time": str(buy_trade.get("trade_date") or "") + " " + str(buy_trade.get("trade_time") or ""),
                        "currency": buy_trade.get("currency", "UNKNOWN"),
                        "matched_lots": [{"lot_fill_id": buy_id}],
                    }
                    if target_obj not in buckets["revenge_reentry"]:
                        buckets["revenge_reentry"].append(target_obj)
                        evidence_map["revenge_reentry"].append({
                            "field": "time_since_last_loss",
                            "comparator": "<=",
                            "threshold": "600s",
                            "observed": f"{int(delta_sec)}s",
                            "prior_loss_round_trip": rt_id,
                            "reentry_trade_id": buy_id,
                        })

    meta_info: dict[str, tuple[str, str]] = {
        "broken_invalidation_unstopped": ("离场价越过记录的失效价", "需核对跳空、滑点与原始计划；仅凭成交价不能判定未执行止损。"),
        "early_morning_exit": ("已知开盘时段内平仓", "没有交易计划或本人确认，不将开盘时段平仓归因为情绪。"),
        "one_day_holding": ("隔日平仓", "持仓一天是行为特征，不自动视为错误。"),
        "revenge_reentry": ("同账户同标的亏损后短时间再入场", "需本人确认交易动机，不从时间接近推断冲动或翻本。"),
    }

    clusters: list[dict[str, Any]] = []
    for kind in CLUSTER_KINDS:
        trips = buckets[kind]
        if not trips:
            continue

        label_seed, default_give_up = meta_info[kind]

        all_trade_ids: set[str] = set()
        timestamps: list[datetime] = []
        for trip in trips:
            for lot in trip.get("matched_lots") or []:
                fid = str(lot.get("lot_fill_id") or "")
                if fid:
                    all_trade_ids.add(fid)
            et = _parse_iso_or_parts(str(trip.get("entry_time") or ""))
            if et:
                timestamps.append(et)
            xt = _parse_iso_or_parts(str(trip.get("exit_time") or ""))
            if xt:
                timestamps.append(xt)

        ordered_times = sorted(_format_time_or_fallback(stamp) for stamp in timestamps)
        first_at = ordered_times[0] if ordered_times else "unknown"
        last_at = ordered_times[-1] if ordered_times else "unknown"

        net_pnl_sum = sum(float(t.get("net_pnl") or 0.0) for t in trips)
        currencies = {str(t.get("currency") or "UNKNOWN") for t in trips}
        ret_pct_avg = (
            sum(float(t.get("return_pct") or 0.0) for t in trips) / len(trips)
            if trips
            else 0.0
        )

        cluster: dict[str, Any] = {
            "cluster_id": f"CLUST-{kind}",
            "kind": kind,
            "label_seed": label_seed,
            "trade_ids": sorted(all_trade_ids),
            "count": len(trips),
            "net_pnl": _round(net_pnl_sum) if len(currencies) <= 1 else None,
            "currency": next(iter(currencies)) if len(currencies) == 1 else None,
            "mixed_currency": len(currencies) > 1,
            "avg_return_pct": _round(ret_pct_avg),
            "first_at": first_at,
            "last_at": last_at,
            "evidence": evidence_map[kind],
            # Non-silent observation contract fields (AGENTS.md #5)
            "invalidation": "系统录入更早的真实止损动作或更新该笔交易的执行计划时失效",
            "time_stop": "次月复盘审查或该错误模式连续 30 天未再次触发",
            "give_up": default_give_up,
            "data_source": "tenant_journal_ledger",
            "available_at": last_at if last_at != OBSERVATION_FALLBACK else "unknown",
            "data_quality": "observed_behavior_not_psychological_attribution",
        }
        clusters.append(cluster)

    return clusters


def extract_edges(ledger: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Extract profitable edges categorized by tag, regime, holding from ledger performance."""
    edges: list[dict[str, Any]] = []

    for dim in EDGE_DIMENSIONS:
        breakdowns = group_performance(dict(ledger), dimension=dim)
        for row in breakdowns:
            key = str(row.get("key", ""))
            trade_count = int(row.get("trade_count", 0))
            if trade_count == 0:
                continue

            edge_id = f"EDGE-{dim}-{key}"
            edge: dict[str, Any] = {
                "edge_id": edge_id,
                "dimension": dim,
                "key": key,
                "name": row.get("name") if "name" in row else key,
                "trade_count": trade_count,
                "win_rate": _round(row.get("win_rate", 0.0)),
                "net_pnl": _round(row["net_pnl"]) if row.get("net_pnl") is not None else None,
                "currency": row.get("currency"),
                "mixed_currency": row.get("mixed_currency", False),
                "currency_breakdown": row.get("currency_breakdown", []),
                "avg_return_pct": _round(row.get("avg_return_pct", 0.0)),
                "profit_factor": (
                    _round(row["profit_factor"])
                    if row.get("profit_factor") is not None
                    else None
                ),
                "small_sample": bool(row.get("small_sample", True)),
                # Non-silent observation contract fields (AGENTS.md #5)
                "performance_class": "not_comparable" if row.get("mixed_currency") else "positive_sample" if float(row.get("net_pnl") or 0) > 0 else "negative_or_flat_sample",
                "edge_status": "unvalidated_hypothesis",
                "invalidation": "当来源数据、分组口径或费用修正时重新计算；不得仅凭历史盈利宣称稳定优势。",
                "time_stop": "当季度末或该维度下无新增样本超 60 个交易日",
                "give_up": f"该 {dim} 维度的策略优势衰减，盈亏比失衡",
                "data_source": "tenant_journal_ledger",
                "available_at": max((str(t.get("exit_time") or "unknown") for t in ledger.get("round_trips") or []), default="unknown"),
                "data_quality": (
                    "small_sample_preliminary" if row.get("small_sample") else "descriptive_not_validated_edge"
                ),
            }
            edges.append(edge)

    return edges
