"""The deterministic event-driven backtest engine.

The engine walks exactly one bar series, once, in the order it was given. Every
decision at bar i reads only closed bars up to and including i, and an order
raised at bar i is filled from bar i+1 by default, so a signal can never be
acted on with information the decision did not have. That is the whole of the
look-ahead protection: it is structural, not a filter applied afterward.

Everything downstream of the DSL is a closed dispatch over frozen vocabularies:
a function per indicator kind, a predicate per comparison operator, a formula
per sizing kind. Strategy text never becomes Python, no expression is assembled
from a payload, and nothing in this module can build code at run time. A payload
the engine does not understand is rejected by dsl.validate_strategy before a
single bar is read.

Bars arrive as any object carrying open_time, open, high, low, close, and
volume. The engine deliberately does not import the market-data layer: a bar is
a narrow input contract here, which keeps the backtest independent of where the
series came from and lets the two ship separately.

Position direction is long. The frozen DSL has no direction key, so a short
would be a vocabulary addition, not an engine option.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.backtest.dsl import (
    ConditionSpec,
    IndicatorSpec,
    RuleSpec,
    StrategyError,
    StrategySpec,
    validate_strategy,
)
from smartmoney_cub_harness.trader.backtest.metrics import compute_metrics, duration_years

BACKTEST_SCHEMA = "smartmoney_cub_backtest.v1"

# One error type for the whole layer: a payload rejected by the DSL and a run
# refused by the engine both raise this, so a caller catches one thing.
BacktestError = StrategyError

FILL_NEXT_OPEN = "next_open"
FILL_SAME_CLOSE = "same_close"

LONG = "long"


@runtime_checkable
class Bar(Protocol):
    """The minimal bar contract the engine accepts.

    Attribute access only, and no import of the market-data package, so the
    backtester is independently testable and reusable.
    """

    open_time: Any
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class BacktestResult:
    """The full, deterministic output of one run.

    Flat scalars and plain containers only, so equality across two runs is
    exact and so the same object serializes to byte-identical JSON.
    """

    schema: str
    strategy_name: str
    symbol: str
    interval: str
    fill: str
    initial_cash: float
    final_equity: float
    trades: tuple[dict[str, Any], ...]
    open_positions: tuple[dict[str, Any], ...]
    equity_curve: tuple[dict[str, Any], ...]
    metrics: dict[str, Any]
    bar_count: int
    first_open_time: Any
    last_open_time: Any
    safety: str = SAFETY_DECLARATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "interval": self.interval,
            "fill": self.fill,
            "initial_cash": self.initial_cash,
            "final_equity": self.final_equity,
            "trades": [dict(trade) for trade in self.trades],
            "open_positions": [dict(position) for position in self.open_positions],
            "equity_curve": [dict(point) for point in self.equity_curve],
            "metrics": dict(self.metrics),
            "bar_count": self.bar_count,
            "first_open_time": self.first_open_time,
            "last_open_time": self.last_open_time,
            "safety": self.safety,
        }


@dataclass
class _Position:
    side: str
    quantity: int
    entry_price: float
    entry_index: int
    entry_time: Any
    entry_fee: float
    stop_price: float | None
    target_price: float | None
    risk_per_share: float | None


@dataclass
class _PendingOrder:
    """An intent formed at one bar and filled at the next.

    Keeping the signal bar on the order is what makes the fill bar provably
    later than the decision bar, and it is the only place that relationship is
    enforced.

    The order carries no prices. Its stop, target, and size all follow from the
    price it fills at and the bar it fills on, so none of them can be anchored
    to a close the strategy never got to trade.
    """

    kind: str
    signal_index: int


def run_backtest(
    spec: StrategySpec | Mapping[str, Any],
    bars: Sequence[Bar] | Iterable[Bar],
    *,
    initial_cash: float,
    fees_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> BacktestResult:
    """Run one strategy over one bar series and return a full result.

    Deterministic by construction: one pass over the bars in the order given,
    no wall-clock read, no randomness, no iteration whose order depends on
    anything but this code. Identical inputs produce an identical result.

    A mapping is validated here and a spec object is used as given, so the
    interface accepts both without duplicating the DSL.
    """
    strategy = spec if isinstance(spec, StrategySpec) else validate_strategy(spec)
    engine = _Engine(
        strategy=strategy,
        bars=list(bars),
        initial_cash=float(initial_cash),
        fees_bps=float(fees_bps),
        slippage_bps=float(slippage_bps),
    )
    return engine.run()


class _Engine:
    def __init__(
        self,
        *,
        strategy: StrategySpec,
        bars: list[Any],
        initial_cash: float,
        fees_bps: float,
        slippage_bps: float,
    ) -> None:
        self.strategy = strategy
        self.bars = bars
        self.initial_cash = initial_cash
        self.fees_bps = fees_bps
        self.slippage_bps = slippage_bps
        self.cash = initial_cash
        self.position: _Position | None = None
        self.pending: _PendingOrder | None = None
        self.trades: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []
        self.exposure_bars = 0
        self.series = _build_indicator_series(strategy.indicators, bars)
        self.min_bars = strategy.filters.min_bars
        self.same_close = strategy.fill == FILL_SAME_CLOSE

    def run(self) -> BacktestResult:
        for index, bar in enumerate(self.bars):
            self._fill_pending(index, bar)
            if self.position is not None:
                self._exit_on_barrier(index, bar)
            self._signal(index, bar)
            self._mark_to_market(index, bar)

        final_equity = self._equity(self.bars[-1].close if self.bars else self.initial_cash)
        metrics = compute_metrics(
            self.trades,
            initial_cash=self.initial_cash,
            final_equity=final_equity,
            exposure_bars=self.exposure_bars,
            total_bars=len(self.bars),
            years=duration_years(len(self.bars), self.strategy.universe.interval),
        )
        return BacktestResult(
            schema=BACKTEST_SCHEMA,
            strategy_name=self.strategy.name,
            symbol=self.strategy.universe.symbol,
            interval=self.strategy.universe.interval,
            fill=self.strategy.fill,
            initial_cash=_money(self.initial_cash),
            final_equity=_money(final_equity),
            trades=tuple(dict(trade) for trade in self.trades),
            open_positions=tuple(self._open_positions()),
            equity_curve=tuple(dict(point) for point in self.equity_curve),
            metrics=metrics,
            bar_count=len(self.bars),
            first_open_time=self.bars[0].open_time if self.bars else None,
            last_open_time=self.bars[-1].open_time if self.bars else None,
        )

    # -- fills ---------------------------------------------------------------

    def _fill_pending(self, index: int, bar: Any) -> None:
        """Fill an order raised on an earlier bar, at this bar's open."""
        order = self.pending
        if order is None or index <= order.signal_index:
            return
        self.pending = None
        price = float(bar.open)
        if order.kind == "exit":
            self._close_position(index, price, bar.open_time, reason="exit_signal")
            return
        self._open_position(order, index, price, bar.open_time)

    def _open_position(self, order: _PendingOrder, index: int, raw_price: float, open_time: Any) -> None:
        fill_price = _price(_apply_slippage(raw_price, LONG, is_entry=True, slippage_bps=self.slippage_bps))
        # Stop, target, and risk are resolved once, from the fill bar. Sizing
        # reads the same risk, so the quantity placed and the stop recorded can
        # never measure against different ATR bars under an atr_multiple stop.
        stop_price, target_price, risk_per_share = _levels_from(
            self.strategy, self.series, index, fill_price
        )
        quantity = self._size(fill_price, risk_per_share)
        if quantity <= 0:
            return
        notional = fill_price * quantity
        fee = _money(_fee(notional, self.fees_bps))
        if self.cash - notional - fee < 0:
            # The next bar gapped beyond what the sizing was willing to fund;
            # a backtest that pretends the fill happened anyway would claim
            # leverage this engine does not model.
            return
        self.cash -= notional + fee
        self.position = _Position(
            side=LONG,
            quantity=quantity,
            entry_price=fill_price,
            entry_index=index,
            entry_time=open_time,
            entry_fee=fee,
            stop_price=stop_price,
            target_price=target_price,
            risk_per_share=risk_per_share,
        )

    def _exit_on_barrier(self, index: int, bar: Any) -> None:
        """Close on the first stop or target this bar reaches.

        The barrier is a level the strategy set, not an exchange order, so a
        bar that gaps past it fills at the open. Pretending every barrier fills
        at its exact price would overstate a gapped loss.
        """
        position = self.position
        if position is None:
            return
        barrier = _barrier_price(position, bar)
        if barrier is None:
            return
        price, reason = barrier
        self._close_position(index, price, bar.open_time, reason=reason)

    def _close_position(self, index: int, raw_price: float, exit_time: Any, *, reason: str) -> None:
        position = self.position
        if position is None:
            return
        fill_price = _price(
            _apply_slippage(raw_price, position.side, is_entry=False, slippage_bps=self.slippage_bps)
        )
        quantity = position.quantity
        notional = fill_price * quantity
        exit_fee = _money(_fee(notional, self.fees_bps))
        if position.side == LONG:
            gross = (fill_price - position.entry_price) * quantity
            self.cash += notional - exit_fee
        else:
            gross = (position.entry_price - fill_price) * quantity
            self.cash -= notional + exit_fee
        fees = _money(position.entry_fee + exit_fee)
        net_pnl = _money(gross - fees)
        risk = position.risk_per_share
        self.trades.append(
            {
                "trade_index": len(self.trades) + 1,
                "symbol": self.strategy.universe.symbol,
                "side": position.side,
                "quantity": quantity,
                "entry_time": position.entry_time,
                "entry_price": _price(position.entry_price),
                "exit_time": exit_time,
                "exit_price": _price(fill_price),
                "gross_pnl": _money(gross),
                "fees": fees,
                "fees_entry": position.entry_fee,
                "fees_exit": exit_fee,
                "net_pnl": net_pnl,
                "return_pct": _pct(net_pnl, position.entry_price * quantity + position.entry_fee),
                "entry_index": position.entry_index,
                "exit_index": index,
                "hold_bars": max(1, index - position.entry_index),
                "exit_reason": reason,
                "risk_per_share": _price(risk) if risk else None,
                "r_multiple": _round(net_pnl / (risk * quantity), 4) if risk else None,
                # The journal pairs a round trip from two dated fills, so the
                # bar positions are carried through and dated by the metrics
                # layer, which is where the synthetic ledger is built.
                "entry_day": position.entry_index,
                "exit_day": index,
            }
        )
        self.position = None

    def _size(self, fill_price: float, risk_per_share: float | None) -> int:
        """Share quantity for an entry filled at this price.

        The risk distance is passed in rather than recomputed: under an
        atr_multiple stop the distance depends on the bar it is measured from,
        and the same call is what records the stop on the position.
        """
        sizing = self.strategy.sizing
        if sizing.kind == "fixed_quantity":
            return int(sizing.value)
        equity = self._equity(fill_price)
        if fill_price <= 0:
            return 0
        if sizing.kind == "fixed_fraction":
            return int(equity * sizing.value / fill_price)
        # risk_percent: the fraction is the share of equity lost if the stop is
        # hit, so quantity follows from that same stop distance.
        if not risk_per_share or risk_per_share <= 0:
            return 0
        return int(equity * sizing.value / risk_per_share)

    # -- signals -------------------------------------------------------------

    def _signal(self, index: int, bar: Any) -> None:
        if self.pending is not None:
            return
        if self.position is None:
            if index < self.min_bars:
                return
            if not _rule_holds(self.strategy.entry, self.series, index):
                return
            self._act(self._entry_order(index), index, bar)
            return
        if not _rule_holds(self.strategy.exit, self.series, index):
            return
        self._act(
            _PendingOrder(kind="exit", signal_index=index),
            index,
            bar,
        )

    def _act(self, order: _PendingOrder, index: int, bar: Any) -> None:
        """Either fill at this bar's close or queue for the next open."""
        if not self.same_close:
            self.pending = order
            return
        price = float(bar.close)
        if order.kind == "exit":
            self._close_position(index, price, bar.open_time, reason="exit_signal")
        else:
            self._open_position(order, index, price, bar.open_time)

    def _entry_order(self, index: int) -> _PendingOrder:
        return _PendingOrder(kind="entry", signal_index=index)

    # -- bookkeeping ---------------------------------------------------------

    def _equity(self, price: float) -> float:
        equity = self.cash
        position = self.position
        if position is not None:
            if position.side == LONG:
                equity += position.quantity * price
            else:
                equity -= position.quantity * price
        return equity

    def _mark_to_market(self, index: int, bar: Any) -> None:
        equity = _money(self._equity(float(bar.close)))
        if self.position is not None:
            self.exposure_bars += 1
        self.equity_curve.append(
            {
                "bar_index": index,
                "open_time": bar.open_time,
                "close": _price(bar.close),
                "equity": equity,
                "cash": _money(self.cash),
                "position_quantity": self.position.quantity if self.position else 0,
            }
        )

    def _open_positions(self) -> list[dict[str, Any]]:
        position = self.position
        if position is None:
            return []
        close = float(self.bars[-1].close)
        unrealized = (close - position.entry_price) * position.quantity
        return [
            {
                "symbol": self.strategy.universe.symbol,
                "side": position.side,
                "quantity": position.quantity,
                "entry_time": position.entry_time,
                "entry_price": _price(position.entry_price),
                "last_close": _price(close),
                "stop_price": _price(position.stop_price) if position.stop_price else None,
                "target_price": _price(position.target_price) if position.target_price else None,
                "unrealized_pnl": _money(unrealized),
                "status": "open_at_end_of_series",
            }
        ]


def _rule_holds(rule: RuleSpec, series: Mapping[str, list[float]], index: int) -> bool:
    """A conjunction: every condition must hold.

    A condition whose series is not warm yet does not hold, so a period-20
    average cannot accidentally participate before it has 20 bars behind it.
    """
    return all(_condition_holds(condition, series, index) for condition in rule.conditions)


def _condition_holds(condition: ConditionSpec, series: Mapping[str, list[float]], index: int) -> bool:
    values = [series[operand.indicator_id] for operand in condition.operands]
    if any(not _warm(value, index) for value in values):
        return False
    operator = condition.operator
    if operator == "gt":
        return values[0][index] > values[1][index]
    if operator == "lt":
        return values[0][index] < values[1][index]
    if operator == "gte":
        return values[0][index] >= values[1][index]
    if operator == "lte":
        return values[0][index] <= values[1][index]
    if operator == "crosses_above":
        if not _warm(values[0], index - 1) or not _warm(values[1], index - 1):
            return False
        return values[0][index - 1] <= values[1][index - 1] and values[0][index] > values[1][index]
    if operator == "crosses_below":
        if not _warm(values[0], index - 1) or not _warm(values[1], index - 1):
            return False
        return values[0][index - 1] >= values[1][index - 1] and values[0][index] < values[1][index]
    if operator == "is_true":
        return values[0][index] > 0
    raise AssertionError(f"unhandled operator {operator!r}")


def _warm(series: list[float], index: int) -> bool:
    return 0 <= index < len(series) and math.isfinite(series[index])


def _levels_from(
    strategy: StrategySpec,
    series: Mapping[str, list[float]],
    index: int,
    close: float,
) -> tuple[float | None, float | None, float | None]:
    """Absolute stop and target prices for an entry at this bar, plus the
    per-share risk that sizing and the R multiple both measure against."""
    stop = strategy.stop
    stop_price: float | None = None
    if stop.kind == "percent":
        stop_price = close * (1.0 - stop.value / 100.0)
    elif stop.kind == "atr_multiple":
        atr_id = strategy.atr_indicator_id
        atr_series = series.get(atr_id) if atr_id else None
        if atr_series is not None and _warm(atr_series, index) and atr_series[index] > 0:
            stop_price = close - stop.value * atr_series[index]
    if stop_price is not None and stop_price <= 0:
        stop_price = None
    risk_per_share = (close - stop_price) if stop_price is not None else None

    target = strategy.target
    target_price: float | None = None
    if target.kind == "percent":
        target_price = close * (1.0 + target.value / 100.0)
    elif target.kind == "r_multiple" and risk_per_share:
        target_price = close + target.value * risk_per_share
    return stop_price, target_price, risk_per_share


def _barrier_price(position: _Position, bar: Any) -> tuple[float, str] | None:
    """The first barrier this bar reaches, stop before target.

    Both levels are checked against the same bar, and the stop wins a tie: a
    bar that touched both cannot say which came first, and taking the
    pessimistic reading is the honest one.
    """
    open_price = float(bar.open)
    if position.side == LONG:
        if position.stop_price is not None and float(bar.low) <= position.stop_price:
            return (min(open_price, position.stop_price), "stop")
        if position.target_price is not None and float(bar.high) >= position.target_price:
            return (max(open_price, position.target_price), "target")
        return None
    if position.stop_price is not None and float(bar.high) >= position.stop_price:
        return (max(open_price, position.stop_price), "stop")
    if position.target_price is not None and float(bar.low) <= position.target_price:
        return (min(open_price, position.target_price), "target")
    return None


def _build_indicator_series(
    indicators: Iterable[IndicatorSpec],
    bars: Sequence[Any],
) -> dict[str, list[float]]:
    """One aligned series per declared indicator.

    Every series is the same length as the bars, with nan before it is warm.
    nan is the engine's "not available yet" marker, and every read passes the
    warm check before it is compared.
    """
    series: dict[str, list[float]] = {}
    for indicator in indicators:
        source = [float(getattr(bar, indicator.source)) for bar in bars]
        series[indicator.id] = _indicator_values(indicator, source, bars)
    return series


def _indicator_values(indicator: IndicatorSpec, source: list[float], bars: Sequence[Any]) -> list[float]:
    kind = indicator.kind
    period = indicator.period
    if kind in ("sma", "volume_sma"):
        return _sma(source, period)
    if kind == "ema":
        return _ema(source, period)
    if kind == "highest":
        return _rolling_extreme(source, period, max)
    if kind == "lowest":
        return _rolling_extreme(source, period, min)
    if kind == "rsi":
        return _rsi(source, period)
    if kind == "atr":
        return _atr(bars, period)
    raise AssertionError(f"unhandled indicator kind {kind!r}")


def _sma(source: list[float], period: int) -> list[float]:
    values: list[float] = [math.nan] * len(source)
    window = 0.0
    for index, value in enumerate(source):
        window += value
        if index >= period:
            window -= source[index - period]
        if index >= period - 1:
            values[index] = window / period
    return values


def _ema(source: list[float], period: int) -> list[float]:
    values: list[float] = [math.nan] * len(source)
    if len(source) < period:
        return values
    multiplier = 2.0 / (period + 1.0)
    previous = sum(source[:period]) / period
    values[period - 1] = previous
    for index in range(period, len(source)):
        previous = (source[index] - previous) * multiplier + previous
        values[index] = previous
    return values


def _rolling_extreme(source: list[float], period: int, chooser: Any) -> list[float]:
    values: list[float] = [math.nan] * len(source)
    for index in range(period - 1, len(source)):
        values[index] = chooser(source[index - period + 1 : index + 1])
    return values


def _rsi(source: list[float], period: int) -> list[float]:
    """Wilder's RSI: seeded with the simple average of the first period of
    changes, then smoothed. This is what the indicator name means everywhere
    else, so a strategy ported in does not silently change character."""
    values: list[float] = [math.nan] * len(source)
    if len(source) <= period:
        return values
    gains = 0.0
    losses = 0.0
    for index in range(1, period + 1):
        change = source[index] - source[index - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    average_gain = gains / period
    average_loss = losses / period
    values[period] = _rsi_value(average_gain, average_loss)
    for index in range(period + 1, len(source)):
        change = source[index] - source[index - 1]
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
        values[index] = _rsi_value(average_gain, average_loss)
    return values


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0.0:
        return 100.0 if average_gain > 0 else 50.0
    return 100.0 - (100.0 / (1.0 + average_gain / average_loss))


def _atr(bars: Sequence[Any], period: int) -> list[float]:
    """Wilder's ATR over the true range.

    The first bar has no previous close, so its true range is its own range.
    """
    values: list[float] = [math.nan] * len(bars)
    if not bars or len(bars) < period:
        return values
    true_ranges: list[float] = []
    for index, bar in enumerate(bars):
        high = float(bar.high)
        low = float(bar.low)
        if index == 0:
            true_ranges.append(high - low)
            continue
        previous_close = float(bars[index - 1].close)
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    previous = sum(true_ranges[:period]) / period
    values[period - 1] = previous
    for index in range(period, len(true_ranges)):
        previous = (previous * (period - 1) + true_ranges[index]) / period
        values[index] = previous
    return values


def _fee(notional: float, fees_bps: float) -> float:
    return abs(notional) * fees_bps / 10000.0


def _apply_slippage(price: float, side: str, *, is_entry: bool, slippage_bps: float) -> float:
    """Slippage always works against the position.

    A buy pays up and a sell receives less, so the adjustment depends on which
    leg of the trade this is, not only on the direction of the position.
    """
    adjustment = price * slippage_bps / 10000.0
    buying = (side == LONG) == is_entry
    return price + adjustment if buying else price - adjustment


def _money(value: float) -> float:
    return round(float(value), 2)


def _price(value: float) -> float:
    return round(float(value), 4)


def _round(value: float, digits: int) -> float:
    return round(float(value), digits)


def _pct(numerator: float, denominator: float) -> float:
    return round(numerator / denominator * 100.0, 2) if denominator else 0.0


__all__ = [
    "BACKTEST_SCHEMA",
    "BacktestError",
    "BacktestResult",
    "Bar",
    "run_backtest",
]
