from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from smartmoney_cub_harness.fills import build_fill_ledger
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

# Every number here is derived from reviewed fills or from a ledger that was
# built from reviewed fills. Nothing is estimated from a screenshot the user has
# not confirmed.


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    if "T" in value or " " in value:
        value = value[:10]
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def build_ledger(fills: Iterable[dict[str, Any]]) -> dict[str, Any]:
    records = [
        {
            **fill,
            "成交日期": fill.get("trade_date"),
            "成交时间": fill.get("trade_time") or "",
            "证券代码": fill.get("symbol"),
            "证券名称": fill.get("name") or "",
            "操作": "买入" if str(fill.get("side")).upper() == "BUY" else "卖出",
            "成交均价": fill.get("price"),
            "成交数量": fill.get("quantity"),
            "手续费": fill.get("fee"),
            "买入理由": fill.get("thesis") or "",
            "止损价": fill.get("invalidation_price"),
            "情绪周期": fill.get("regime") or "",
        }
        for fill in fills
    ]
    return build_fill_ledger(records)


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def currency_breakdown(trips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trip in trips:
        buckets[str(trip.get("currency") or "UNKNOWN").strip().upper() or "UNKNOWN"].append(trip)
    return [{"currency": currency, "trade_count": len(items),
             "net_pnl": _round(sum(item["net_pnl"] for item in items)) if currency != "UNKNOWN" else None,
             "total_fees": _round(sum(item.get("fees") or 0 for item in items)) if currency != "UNKNOWN" else None}
            for currency, items in sorted(buckets.items())]


def summarize(ledger: dict[str, Any]) -> dict[str, Any]:
    """Compute review metrics, with the sample size attached to each aggregate."""
    trips = list(ledger.get("round_trips") or [])
    currencies = currency_breakdown(trips)
    mixed = len(currencies) > 1
    comparable = not currencies or (len(currencies) == 1 and currencies[0]['currency'] != 'UNKNOWN')
    wins = [trip for trip in trips if trip["net_pnl"] > 0]
    losses = [trip for trip in trips if trip["net_pnl"] < 0]
    flat = [trip for trip in trips if trip["net_pnl"] == 0]
    gross_profit = sum(trip["net_pnl"] for trip in wins)
    gross_loss = abs(sum(trip["net_pnl"] for trip in losses))
    total_pnl = sum(trip["net_pnl"] for trip in trips)
    total_fees = sum(trip.get("fees") or 0.0 for trip in trips)
    holding_days = [trip.get("holding_days") or 0 for trip in trips]
    return_pcts = [trip["return_pct"] for trip in trips]

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    curve: list[dict[str, Any]] = []
    for trip in sorted(trips, key=lambda item: item["exit_time"]):
        equity += trip["net_pnl"]
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
        curve.append(
            {
                "exit_time": trip["exit_time"],
                "symbol": trip["symbol"],
                "net_pnl": _round(trip["net_pnl"]),
                "cumulative_pnl": _round(equity),
            }
        )

    return {
        "schema": "smartmoney_cub_analytics.v1",
        "trade_count": len(trips),
        "win_count": len(wins),
        "loss_count": len(losses),
        "flat_count": len(flat),
        "win_rate": _round(len(wins) / len(trips) * 100) if trips else 0.0,
        # Profit factor is fixed as gross profit over the absolute gross loss so
        # the number means the same thing everywhere it is quoted.
        "profit_factor": _round(gross_profit / gross_loss) if gross_loss > 0 and comparable else None,
        "profit_factor_note": (
            "总盈利 / 总亏损绝对值"
            if gross_loss > 0
            else "当前样本没有亏损交易，无法计算"
        ),
        "currency": currencies[0]["currency"] if len(currencies) == 1 else None,
        "mixed_currency": mixed,
        "currency_breakdown": currencies,
        "aggregation_note": "FX rates or explicit currency required; monetary totals are not comparable" if not comparable else "single_currency",
        "total_net_pnl": _round(total_pnl) if comparable else None,
        "total_fees": _round(total_fees) if comparable else None,
        "gross_profit": _round(gross_profit) if comparable else None,
        "gross_loss": _round(gross_loss) if comparable else None,
        "avg_return_pct": _round(sum(return_pcts) / len(return_pcts)) if return_pcts else 0.0,
        "avg_win_pct": _round(sum(t["return_pct"] for t in wins) / len(wins)) if wins else 0.0,
        "avg_loss_pct": _round(sum(t["return_pct"] for t in losses) / len(losses)) if losses else 0.0,
        "avg_holding_days": _round(sum(holding_days) / len(holding_days)) if holding_days else 0.0,
        "max_drawdown": _round(max_drawdown) if comparable else None,
        "open_position_count": len(ledger.get("open_positions") or []),
        "sample_note": (
            "样本是自选的复盘历史，不是对照实验结果。"
            f"当前样本量 {len(trips)} 笔。"
        ),
        "equity_curve": curve if comparable else [],
        "safety": SAFETY_DECLARATION,
    }


def calendar_days(ledger: dict[str, Any], *, year: int, month: int) -> list[dict[str, Any]]:
    """Aggregate closed round trips by exit date for one month."""
    first = date(year, month, 1)
    last = (first + timedelta(days=31)).replace(day=1) - timedelta(days=1)
    buckets: dict[str, dict[str, Any]] = {}
    for trip in ledger.get("round_trips") or []:
        day = _parse_date(str(trip["exit_time"]).split(" ")[0])
        if day is None or not (first <= day <= last):
            continue
        key = day.isoformat()
        bucket = buckets.setdefault(
            key,
            {"date": key, "trade_count": 0, "net_pnl": 0.0, "win_count": 0, "trades": []},
        )
        bucket["trade_count"] += 1
        bucket["net_pnl"] = _round(bucket["net_pnl"] + trip["net_pnl"])
        if trip["net_pnl"] > 0:
            bucket["win_count"] += 1
        bucket["trades"].append(
            {
                "round_trip_id": trip["round_trip_id"],
                "symbol": trip["symbol"],
                "name": trip.get("name") or trip["symbol"],
                "net_pnl": _round(trip["net_pnl"]),
                "return_pct": trip["return_pct"],
                "currency": trip.get("currency") or "UNKNOWN",
                "fees": trip.get("fees") or 0,
            }
        )
    for bucket in buckets.values():
        currencies = currency_breakdown(bucket["trades"])
        bucket["currency_breakdown"] = currencies
        bucket["mixed_currency"] = len(currencies) > 1
        bucket["currency"] = currencies[0]["currency"] if len(currencies) == 1 else None
        if len(currencies) != 1 or currencies[0]['currency'] == 'UNKNOWN':
            bucket["net_pnl"] = None
    return [buckets[key] for key in sorted(buckets)]


def group_performance(
    ledger: dict[str, Any],
    *,
    dimension: str,
    symbol_names: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Break performance down by a reviewed field, keeping the sample size visible."""
    trips = list(ledger.get("round_trips") or [])
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trip in trips:
        key = _dimension_key(trip, dimension)
        buckets[key].append(trip)

    rows: list[dict[str, Any]] = []
    for key, group in buckets.items():
        wins = [trip for trip in group if trip["net_pnl"] > 0]
        losses = [trip for trip in group if trip["net_pnl"] < 0]
        gross_profit = sum(trip["net_pnl"] for trip in wins)
        gross_loss = abs(sum(trip["net_pnl"] for trip in losses))
        currencies = currency_breakdown(group)
        mixed = len(currencies) > 1
        comparable = len(currencies) == 1 and currencies[0]['currency'] != 'UNKNOWN'
        item: dict[str, Any] = {
            "key": key,
            "trade_count": len(group),
            "win_rate": _round(len(wins) / len(group) * 100) if group else 0.0,
            "net_pnl": _round(sum(trip["net_pnl"] for trip in group)) if comparable else None,
            "currency": currencies[0]["currency"] if len(currencies) == 1 else None,
            "mixed_currency": mixed,
            "currency_breakdown": currencies,
            "avg_return_pct": _round(sum(trip["return_pct"] for trip in group) / len(group)),
            "profit_factor": _round(gross_profit / gross_loss) if gross_loss > 0 and comparable else None,
            # A breakdown with too few trades is shown, but flagged, so a
            # single lucky trade never reads as a pattern.
            "small_sample": len(group) < 5,
        }
        if dimension == "symbol":
            resolved_name = ""
            resolved_st = False
            if symbol_names and key in symbol_names:
                meta = symbol_names[key]
                if isinstance(meta, dict):
                    resolved_name = str(meta.get("name") or "").strip()
                    resolved_st = bool(meta.get("is_st", False))
                elif isinstance(meta, str):
                    resolved_name = meta.strip()
            if not resolved_name:
                for trip in reversed(group):
                    trip_name = str(trip.get("name") or "").strip()
                    if trip_name and trip_name != key:
                        resolved_name = trip_name
                        break
            if "ST" in resolved_name.upper():
                resolved_st = True
            item["name"] = resolved_name
            item["is_st"] = resolved_st
        rows.append(item)
    rows.sort(key=lambda row: (-row["trade_count"], row["key"]))
    return rows


def _dimension_key(trip: dict[str, Any], dimension: str) -> str:
    if dimension == "symbol":
        return str(trip.get("symbol") or "unknown")
    if dimension == "regime":
        return str(trip.get("regime") or "未标注")
    if dimension == "weekday":
        day = _parse_date(str(trip["entry_time"]).split(" ")[0])
        return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][day.weekday()] if day else "未标注"
    if dimension == "holding":
        days = trip.get("holding_days") or 0
        if days <= 0:
            return "当日"
        if days == 1:
            return "次日"
        if days <= 3:
            return "2-3 日"
        if days <= 10:
            return "4-10 日"
        return "10 日以上"
    if dimension == "tag":
        tags = trip.get("tags") or []
        return str(tags[0]) if tags else "无标签"
    return "all"


DIMENSIONS = ("symbol", "regime", "weekday", "holding", "tag")


def analyze(fills: list[dict[str, Any]], *, year: int | None = None, month: int | None = None) -> dict[str, Any]:
    ledger = build_ledger(fills)
    today = date.today()
    year = year or today.year
    month = month or today.month
    summary = summarize(ledger)
    return {
        "status": "ok",
        "ledger_status": ledger.get("status"),
        "issues": ledger.get("issues") or [],
        "blocking_issues": [issue for issue in ledger.get("issues") or [] if issue.get("severity") == "error"],
        "summary": summary,
        "round_trips": ledger.get("round_trips") or [],
        "open_positions": ledger.get("open_positions") or [],
        "calendar": calendar_days(ledger, year=year, month=month),
        "calendar_year": year,
        "calendar_month": month,
        "breakdown": {dimension: group_performance(ledger, dimension=dimension) for dimension in DIMENSIONS},
        "safety": SAFETY_DECLARATION,
    }
