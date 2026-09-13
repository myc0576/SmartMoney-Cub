"""Backtest engine and the JSON rule DSL that drives it.

Strategies are JSON data validated against a frozen key whitelist. Nothing in
this package turns a payload into Python, and the engine is a closed dispatch
over the same vocabulary the validator accepts, so a strategy that cannot be
validated cannot run.

    from smartmoney_cub_harness.trader.backtest import load_strategy, run_backtest

    spec = load_strategy(strategy_json)
    result = run_backtest(spec, bars, initial_cash=100_000.0, fees_bps=2.0)

The engine accepts any bar object carrying open_time, open, high, low, close,
and volume. It does not import the market-data layer, so the two ship and are
tested independently.
"""

from __future__ import annotations

from smartmoney_cub_harness.trader.backtest.dsl import (
    ConditionSpec,
    FilterSpec,
    IndicatorSpec,
    Operand,
    RuleSpec,
    SizingSpec,
    StopSpec,
    StrategyError,
    StrategySpec,
    TargetSpec,
    UniverseSpec,
    load_strategy,
    validate_strategy,
)
from smartmoney_cub_harness.trader.backtest.engine import (
    BACKTEST_SCHEMA,
    BacktestError,
    BacktestResult,
    Bar,
    run_backtest,
)
from smartmoney_cub_harness.trader.backtest.metrics import compute_metrics, duration_years, trade_ledger

__all__ = [
    "BACKTEST_SCHEMA",
    "BacktestError",
    "BacktestResult",
    "Bar",
    "ConditionSpec",
    "FilterSpec",
    "IndicatorSpec",
    "Operand",
    "RuleSpec",
    "SizingSpec",
    "StopSpec",
    "StrategyError",
    "StrategySpec",
    "TargetSpec",
    "UniverseSpec",
    "compute_metrics",
    "duration_years",
    "load_strategy",
    "run_backtest",
    "trade_ledger",
    "validate_strategy",
]
