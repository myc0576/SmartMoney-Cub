"""Backtest metrics, computed through the journal's own analytics.

A backtest and the journal must not disagree about what a win rate or a drawdown
is. So each closed trade is rendered into a two-fill ledger and every shared
metric is read back out of smartmoney_cub_harness.analytics.summarize rather
than recomputed here. The numbers this module derives on its own are only the
ones analytics has no opinion about: expectancy in currency, R multiple, CAGR,
exposure, and the equity curve.

The synthetic ledger is unambiguous by construction: one buy, then one sell, one
symbol, two different days. That pairing is what the journal's ledger accepts as
a round trip. A short is expressed by the direction of the entry and exit
condition, not by a negative quantity, which the ledger would refuse as an
oversell.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable, Mapping

from smartmoney_cub_harness.analytics import build_ledger, summarize
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

BACKTEST_SCHEMA = "smartmoney_cub_backtest.v1"

# Bars per year by interval, used only to annualize a return. An interval that
# is not listed yields no CAGR rather than a guessed year length.
BARS_PER_YEAR = {
    "1m": 252 * 240,
    "5m": 252 * 48,
    "15m": 252 * 16,
    "30m": 252 * 8,
    "60m": 252 * 4,
    "1h": 252 * 4,
    "1d": 252,
    "1w": 52,
    "1mo": 12,
}

# The synthetic fills are dated from a fixed epoch so a rerun produces exactly
# the same ledger bytes. The dates are bookkeeping, not a claim about a calendar.
LEDGER_EPOCH = date(1970, 1, 2)

# Each round trip is dated into its own window of consecutive days, later than
# every window before it. That matters because the journal pairs a sale with the
# oldest open lot: two trades on the same symbol that shared a day range could
# cross-match, and the point of this ledger is that each round trip stands for
# exactly the trade that produced it. A trade that entered and exited inside one
# bar still gets two days, because the journal pairs a round trip from two dated
# fills.
LEDGER_DAY_GAP = 1


def _date_text(day_index: int) -> str:
    # Offset by one so bar 0 and bar 1 do not land on the same calendar day,
    # which the ledger would read as a same-day sell and refuse to pair.
    return (LEDGER_EPOCH + timedelta(days=int(day_index) + 1)).isoformat()


def _round(value: float, digits: int) -> float:
    return round(float(value), digits)


def _synthetic_fills(trades: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One buy and one sell per closed trade, in the shape the ledger reads.

    Fees are declared per side, exactly as the engine charged them, so the
    ledger's round trip costs the same as the trade did. The key is "fee",
    which is the column analytics.build_ledger carries through as the fill's
    declared commission; a "commission" key here would be dropped on the way.
    """
    rows: list[dict[str, Any]] = []
    cursor = 0
    for index, trade in enumerate(trades, start=1):
        held = int(trade.get("hold_bars", 0))
        entry_day = cursor
        exit_day = cursor + max(1, held)
        cursor = exit_day + LEDGER_DAY_GAP
        symbol = str(trade.get("symbol") or "TOY")
        entry_fee, exit_fee = _side_fees(trade)
        quantity = int(trade["quantity"])
        rows.append(
            {
                "fill_id": f"BT-{index}-BUY",
                "symbol": symbol,
                "name": symbol,
                "side": "BUY",
                "trade_date": _date_text(entry_day),
                "trade_time": "09:30:00",
                "price": float(trade["entry_price"]),
                "quantity": quantity,
                "fee": entry_fee,
            }
        )
        rows.append(
            {
                "fill_id": f"BT-{index}-SELL",
                "symbol": symbol,
                "name": symbol,
                "side": "SELL",
                "trade_date": _date_text(exit_day),
                "trade_time": "15:00:00",
                "price": float(trade["exit_price"]),
                "quantity": quantity,
                "fee": exit_fee,
            }
        )
    return rows


def _side_fees(trade: Mapping[str, Any]) -> tuple[float, float]:
    """The two fill fees for one trade.

    The engine records what it actually charged on each leg. A trade built
    elsewhere only carries a total, which is split evenly; splitting an
    odd number of cents is a rounding question, not an accounting one, since
    the ledger only ever sums the two.
    """
    if trade.get("fees_entry") is not None and trade.get("fees_exit") is not None:
        return float(trade["fees_entry"]), float(trade["fees_exit"])
    total = float(trade.get("fees") or 0.0)
    entry_fee = _round(total / 2, 4)
    return entry_fee, _round(total - entry_fee, 4)


def trade_ledger(trades: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The synthetic review ledger for a backtest's closed trades.

    Public so a test can hand the same fills to the journal and to the engine's
    metrics and prove the two produce the same numbers.
    """
    return build_ledger(_synthetic_fills(trades))


def duration_years(bars: int, interval: str) -> float | None:
    """Horizon in years for CAGR, from the bar count and the bar interval."""
    per_year = BARS_PER_YEAR.get(str(interval))
    if not per_year or bars <= 0:
        return None
    return bars / per_year


def compute_metrics(
    trades: Iterable[Mapping[str, Any]],
    *,
    initial_cash: float,
    final_equity: float,
    exposure_bars: int,
    total_bars: int,
    years: float | None,
) -> dict[str, Any]:
    """Assemble the metric block of a backtest result.

    Win rate, profit factor, drawdown, trade counts, and total fees come from
    analytics.summarize over the synthetic ledger. Everything else is either a
    currency figure analytics does not report or a figure analytic does not
    model (R multiple, CAGR, exposure).
    """
    closed = list(trades)
    summary = summarize(trade_ledger(closed))

    wins = [trade for trade in closed if float(trade["net_pnl"]) > 0]
    losses = [trade for trade in closed if float(trade["net_pnl"]) < 0]
    gross_profit = sum(float(trade["net_pnl"]) for trade in wins)
    gross_loss = abs(sum(float(trade["net_pnl"]) for trade in losses))
    total_pnl = float(final_equity) - float(initial_cash)

    # Expectancy is the average net result per closed trade. analytics models
    # it as a total, not a per-trade figure, so it is derived here from
    # analytics' own totals rather than from a second set of numbers.
    expectancy = (summary["total_net_pnl"] / summary["trade_count"]) if summary["trade_count"] else 0.0
    r_multiples = _r_multiples(closed)

    cagr: float | None = None
    if years is not None and years > 0 and initial_cash > 0 and final_equity > 0:
        cagr = ((float(final_equity) / float(initial_cash)) ** (1.0 / years) - 1.0) * 100

    # Drawdown as a share of starting equity, so it reads on the same scale as
    # the journal's max_drawdown when the account is a single position account.
    worst_drawdown = float(summary["max_drawdown"])
    max_drawdown_pct = (abs(worst_drawdown) / initial_cash * 100) if initial_cash else 0.0
    return {
        "schema": BACKTEST_SCHEMA,
        "trade_count": summary["trade_count"],
        "win_count": summary["win_count"],
        "loss_count": summary["loss_count"],
        "flat_count": summary["flat_count"],
        "win_rate": summary["win_rate"],
        "profit_factor": summary["profit_factor"],
        "expectancy": _round(expectancy, 4),
        "avg_win": _round(gross_profit / len(wins), 2) if wins else 0.0,
        "avg_loss": _round(-(gross_loss / len(losses)), 2) if losses else 0.0,
        "avg_r_multiple": _round(sum(r_multiples) / len(r_multiples), 4) if r_multiples else None,
        "gross_profit": _round(gross_profit, 2),
        "gross_loss": _round(gross_loss, 2),
        "total_net_pnl": _round(total_pnl, 2),
        "total_return_pct": _round((total_pnl / initial_cash * 100) if initial_cash else 0.0, 2),
        "total_fees": summary["total_fees"],
        "max_drawdown": _round(worst_drawdown, 2),
        "max_drawdown_pct": _round(max_drawdown_pct, 2),
        "cagr_pct": _round(cagr, 2) if cagr is not None else None,
        "initial_cash": _round(initial_cash, 2),
        "final_equity": _round(final_equity, 2),
        "exposure_pct": _round((exposure_bars / total_bars * 100) if total_bars else 0.0, 2),
        "avg_holding_days": summary["avg_holding_days"],
        "safety": SAFETY_DECLARATION,
    }


def _r_multiples(trades: list[Mapping[str, Any]]) -> list[float]:
    """R multiple per trade, from the risk the engine recorded at entry.

    A trade with no stop has no risk denominator, so it contributes nothing
    rather than an invented multiple.
    """
    values: list[float] = []
    for trade in trades:
        risk_per_share = trade.get("risk_per_share")
        quantity = int(trade.get("quantity", 0))
        if not risk_per_share or quantity <= 0:
            continue
        values.append(float(trade["net_pnl"]) / (float(risk_per_share) * quantity))
    return values


__all__ = [
    "BACKTEST_SCHEMA",
    "BARS_PER_YEAR",
    "compute_metrics",
    "duration_years",
    "trade_ledger",
]
