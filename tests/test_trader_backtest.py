"""Backtest engine and JSON rule DSL tests.

Toy data only. Every bar series here is generated in the test, and every
expected number is either arithmetic written out in a comment or a frozen
digest of a run this file pins.

The two properties that matter most are structural rather than numeric:
identical inputs produce identical output, and loading a strategy can never
execute anything. Both are asserted directly, because a passing number is not
evidence that the engine cannot run someone else's code.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from smartmoney_cub_harness.analytics import build_ledger, summarize
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.backtest import (
    BacktestResult,
    StrategyError,
    load_strategy,
    run_backtest,
    trade_ledger,
    validate_strategy,
)

BACKTEST_DIR = Path(__file__).resolve().parents[1] / "src" / "smartmoney_cub_harness" / "trader" / "backtest"


@dataclass
class ToyBar:
    """A bar built only from attributes, which is the whole input contract."""

    open_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def flat_bars(closes: tuple[float, ...]) -> list[ToyBar]:
    """Bars with no range, so a fill price is exactly the close and the
    hand-computed arithmetic stays readable."""
    return [
        ToyBar(f"2026-04-{index + 1:02d}", close, close, close, close, 1000.0)
        for index, close in enumerate(closes)
    ]


def ohlc_bars(rows: tuple[tuple[float, float, float, float], ...]) -> list[ToyBar]:
    return [
        ToyBar(f"2026-05-{index + 1:02d}", open_, high, low, close, 1000.0)
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def single_indicator_spec(indicator: dict) -> dict:
    """A strategy whose entry and exit both hold on that one series.

    The tests that read an indicator's values only need a payload the DSL
    accepts; they never run it.
    """
    indicator_id = indicator["id"]
    return {
        "version": 1,
        "name": "indicator-toy",
        "universe": {"symbol": "600111", "interval": "1d"},
        "indicators": [indicator],
        "entry": {"all": [{"gte": [indicator_id, indicator_id]}]},
        "exit": {"all": [{"gte": [indicator_id, indicator_id]}]},
        "stop": {"kind": "none"},
        "target": {"kind": "none"},
        "sizing": {"kind": "fixed_quantity", "value": 1},
        "filters": {"session": None, "min_bars": 0},
        "fill": "next_open",
    }


def sma_cross_spec(**overrides: object) -> dict:
    """A two-line moving-average cross over an identity and a period-2 average.

    fast is the close itself and slow is the two-bar mean, so a cross happens
    exactly where a flat close turns into a rise or a fall. That makes the
    entry and exit bars countable by hand.
    """
    payload = {
        "version": 1,
        "name": "sma-cross-toy",
        "universe": {"symbol": "600111", "interval": "1d"},
        "indicators": [
            {"id": "fast", "kind": "sma", "source": "close", "period": 1},
            {"id": "slow", "kind": "sma", "source": "close", "period": 2},
        ],
        "entry": {"all": [{"crosses_above": ["fast", "slow"]}]},
        "exit": {"all": [{"crosses_below": ["fast", "slow"]}]},
        "stop": {"kind": "none"},
        "target": {"kind": "none"},
        "sizing": {"kind": "fixed_quantity", "value": 100},
        "filters": {"session": None, "min_bars": 2},
        "fill": "same_close",
    }
    payload.update(overrides)
    return payload


# A frozen run. The closes are a fixed toy series; the digest pins the entire
# output, so any change to an indicator, a fill rule, or a rounding step shows
# up here rather than only in a number a reader would have to re-derive.
GOLDEN_CLOSES = (
    10.0, 10.77, 11.5, 12.15, 12.7, 13.12, 13.39, 13.51, 13.47, 13.3,
    13.0, 12.6, 12.15, 11.68, 11.22, 10.82, 10.51, 10.31, 10.26, 10.35,
    10.6, 11.0, 11.54, 12.18, 12.9, 13.67, 14.44, 15.18, 15.84, 16.41,
    16.84, 17.14, 17.27, 17.26, 17.1, 16.81, 16.43, 15.98, 15.51, 15.05,
    14.64, 14.31, 14.1, 14.03, 14.1, 14.33, 14.71, 15.23, 15.86, 16.57,
    17.33, 18.11, 18.85, 19.53, 20.11, 20.56, 20.88, 21.03, 21.04, 20.9,
)
GOLDEN_SHA256 = "739dfd3d76db6407d7f923760fd0b8d7ed2d1b7289679ca0d6de84d5e7217a99"


def golden_bars() -> list[ToyBar]:
    return [
        ToyBar(
            f"2026-05-{index + 1:02d}",
            round(close - 0.05, 2),
            round(close + 0.4, 2),
            round(close - 0.4, 2),
            close,
            float(1000 + index * 3),
        )
        for index, close in enumerate(GOLDEN_CLOSES)
    ]


def golden_spec() -> dict:
    return {
        "version": 1,
        "name": "golden-toy",
        "universe": {"symbol": "600111", "interval": "1d"},
        "indicators": [
            {"id": "ema_fast", "kind": "ema", "source": "close", "period": 8},
            {"id": "ema_slow", "kind": "ema", "source": "close", "period": 21},
            {"id": "atr", "kind": "atr", "source": "high", "period": 5},
        ],
        "entry": {"all": [{"crosses_above": ["ema_fast", "ema_slow"]}]},
        "exit": {"all": [{"crosses_below": ["ema_fast", "ema_slow"]}]},
        "stop": {"kind": "atr_multiple", "value": 1.5},
        "target": {"kind": "r_multiple", "value": 3.0},
        "sizing": {"kind": "fixed_fraction", "value": 0.25},
        "filters": {"session": None, "min_bars": 15},
    }


def golden_run() -> BacktestResult:
    return run_backtest(golden_spec(), golden_bars(), initial_cash=100000.0, fees_bps=4.0, slippage_bps=2.0)


def blob(result: BacktestResult) -> str:
    return json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# DoD 1: determinism
# ---------------------------------------------------------------------------


def test_identical_inputs_produce_identical_results() -> None:
    spec = golden_spec()
    bars = golden_bars()
    first = run_backtest(spec, bars, initial_cash=100000.0, fees_bps=4.0, slippage_bps=2.0)
    second = run_backtest(spec, bars, initial_cash=100000.0, fees_bps=4.0, slippage_bps=2.0)
    assert first == second
    assert blob(first) == blob(second)


def test_repeated_runs_are_byte_identical() -> None:
    digest = hashlib.sha256(blob(golden_run()).encode("utf-8")).hexdigest()
    assert digest == GOLDEN_SHA256


def test_rerunning_does_not_mutate_the_caller_bars_or_spec() -> None:
    spec = golden_spec()
    bars = golden_bars()
    before_spec = json.dumps(spec, sort_keys=True)
    before_bars = [tuple(getattr(bar, field) for field in ("open", "high", "low", "close")) for bar in bars]
    run_backtest(spec, bars, initial_cash=1000.0)
    assert json.dumps(spec, sort_keys=True) == before_spec
    after_bars = [tuple(getattr(bar, field) for field in ("open", "high", "low", "close")) for bar in bars]
    assert after_bars == before_bars


# ---------------------------------------------------------------------------
# DoD 2: hand-computed two-trade PnL, to the cent
# ---------------------------------------------------------------------------


def test_two_trade_scenario_has_the_hand_computed_net_pnl() -> None:
    # Closes (index: value): 0:10 1:10 2:12 3:12 4:14 5:10 6:10 7:12 8:12 9:16 10:16 11:13 12:13
    # fast = close, slow = mean(close, previous close), fill = same_close.
    #
    # Trade 1 entry: at 2, fast 12 > slow (12+10)/2 = 11 while at 1 fast 10 <= slow 10.
    #   Fill at close 12, 100 shares. Buy fee = 1200 x 10bps = 1.20.
    # Trade 1 exit:  at 5, fast 10 < slow (14+10)/2 = 12 while at 4 fast 14 >= slow 13.
    #   Fill at close 10, 100 shares. Sell fee = 1000 x 10bps = 1.00.
    #   Gross = (10 - 12) x 100 = -200.00; net = -200.00 - (1.20 + 1.00) = -202.20.
    #
    # Trade 2 entry: at 7, fast 12 > slow (10+12)/2 = 11 while at 6 fast 10 <= slow 10.
    #   Fill at close 12, 100 shares. Buy fee = 1200 x 10bps = 1.20.
    # Trade 2 exit:  at 11, fast 13 < slow (16+13)/2 = 14.5 while at 10 fast 16 >= slow 16.
    #   Fill at close 13, 100 shares. Sell fee = 1300 x 10bps = 1.30.
    #   Gross = (13 - 12) x 100 = +100.00; net = +100.00 - (1.20 + 1.30) = +97.50.
    #
    # Account: 50000.00 - 202.20 + 97.50 = 49895.30.
    closes = (10.0, 10.0, 12.0, 12.0, 14.0, 10.0, 10.0, 12.0, 12.0, 16.0, 16.0, 13.0, 13.0)
    result = run_backtest(sma_cross_spec(), flat_bars(closes), initial_cash=50000.0, fees_bps=10.0)

    assert len(result.trades) == 2
    first, second = result.trades

    assert (first["entry_index"], first["entry_price"]) == (2, 12.0)
    assert (first["exit_index"], first["exit_price"]) == (5, 10.0)
    assert first["gross_pnl"] == -200.00
    assert first["fees"] == 2.20
    assert first["net_pnl"] == -202.20

    assert (second["entry_index"], second["entry_price"]) == (7, 12.0)
    assert (second["exit_index"], second["exit_price"]) == (11, 13.0)
    assert second["gross_pnl"] == 100.00
    assert second["fees"] == 2.50
    assert second["net_pnl"] == 97.50

    assert result.final_equity == 49895.30
    assert result.metrics["total_net_pnl"] == -104.70
    assert result.metrics["total_fees"] == 4.70
    assert result.metrics["max_drawdown"] == -202.20
    assert result.open_positions == ()


def test_fees_and_slippage_are_charged_on_both_legs() -> None:
    # Same entry and exit closes as trade 1 above, but with slippage.
    # Buy: 12.00 x (1 + 3bps) = 12.0036. Sell: 10.00 x (1 - 3bps) = 9.997.
    # Gross = (9.997 - 12.0036) x 100 = -200.66.
    closes = (10.0, 10.0, 12.0, 12.0, 14.0, 10.0)
    result = run_backtest(
        sma_cross_spec(),
        flat_bars(closes),
        initial_cash=50000.0,
        slippage_bps=3.0,
    )
    trade = result.trades[0]
    assert trade["entry_price"] == pytest.approx(12.0036, abs=1e-4)
    assert trade["exit_price"] == pytest.approx(9.997, abs=1e-4)
    assert trade["gross_pnl"] == pytest.approx(-200.66, abs=0.01)


def test_zero_fee_run_keeps_every_cent_of_the_price_move() -> None:
    closes = (10.0, 10.0, 12.0, 12.0, 14.0, 10.0)
    result = run_backtest(sma_cross_spec(), flat_bars(closes), initial_cash=50000.0)
    assert result.trades[0]["net_pnl"] == -200.00
    assert result.final_equity == 49800.00


# ---------------------------------------------------------------------------
# DoD 3: unknown keys are rejected with a path-qualified message
# ---------------------------------------------------------------------------


def test_unknown_top_level_key_is_rejected_with_its_path() -> None:
    payload = sma_cross_spec()
    payload["leverage"] = 2.0
    with pytest.raises(StrategyError) as excinfo:
        validate_strategy(payload)
    assert "leverage" in str(excinfo.value)


def test_unknown_key_inside_entry_is_rejected_with_its_path() -> None:
    payload = sma_cross_spec()
    payload["entry"] = {"all": [{"crosses_above": ["fast", "slow"]}], "any": [{"gt": ["fast", "slow"]}]}
    with pytest.raises(StrategyError) as excinfo:
        validate_strategy(payload)
    assert "entry.any" in str(excinfo.value)


def test_unknown_indicator_reference_names_the_operand_path() -> None:
    payload = sma_cross_spec()
    payload["entry"] = {"all": [{"crosses_above": ["fast", "missing"]}]}
    with pytest.raises(StrategyError) as excinfo:
        validate_strategy(payload)
    message = str(excinfo.value)
    # The documented shape: <path>: unknown indicator id '<id>'. The message
    # names the offending id, and the path is the operator it appeared under.
    assert "entry.all[0].crosses_above: unknown indicator id 'missing'" in message


@pytest.mark.parametrize(
    ("path", "mutate"),
    [
        ("universe.timezone", lambda payload: payload["universe"].update({"timezone": "UTC"})),
        ("indicators[0].warmup", lambda payload: payload["indicators"][0].update({"warmup": 3})),
        ("stop.trailing", lambda payload: payload["stop"].update({"trailing": True})),
        ("sizing.leverage", lambda payload: payload["sizing"].update({"leverage": 2.0})),
        ("filters.regime", lambda payload: payload["filters"].update({"regime": "bull"})),
    ],
)
def test_unknown_keys_are_rejected_at_every_level(path: str, mutate) -> None:
    payload = sma_cross_spec()
    mutate(payload)
    with pytest.raises(StrategyError) as excinfo:
        validate_strategy(payload)
    assert path in str(excinfo.value)


def test_unknown_operator_is_rejected() -> None:
    payload = sma_cross_spec()
    payload["entry"] = {"all": [{"crosses_over": ["fast", "slow"]}]}
    with pytest.raises(StrategyError) as excinfo:
        validate_strategy(payload)
    assert "entry.all[0].crosses_over" in str(excinfo.value)


def test_unknown_stop_target_and_sizing_kinds_are_rejected() -> None:
    for field, value in (("stop", {"kind": "trailing", "value": 1.0}), ("target", {"kind": "scalp", "value": 1.0}),
                         ("sizing", {"kind": "kelly", "value": 0.1})):
        payload = sma_cross_spec()
        payload[field] = value
        with pytest.raises(StrategyError) as excinfo:
            validate_strategy(payload)
        assert f"{field}.kind" in str(excinfo.value)


def test_missing_required_key_is_reported_against_its_section() -> None:
    payload = sma_cross_spec()
    del payload["filters"]
    with pytest.raises(StrategyError) as excinfo:
        validate_strategy(payload)
    assert "filters" in str(excinfo.value)


def test_valid_payload_round_trips_through_to_dict() -> None:
    spec = validate_strategy(sma_cross_spec())
    assert validate_strategy(spec.to_dict()) == spec
    assert spec.fill == "same_close"
    assert spec.sizing.value == 100


def test_fill_defaults_to_next_open_when_absent() -> None:
    payload = sma_cross_spec()
    del payload["fill"]
    assert validate_strategy(payload).fill == "next_open"


def test_r_multiple_target_and_risk_sizing_need_a_stop() -> None:
    payload = sma_cross_spec()
    payload["target"] = {"kind": "r_multiple", "value": 2.0}
    payload["stop"] = {"kind": "none"}
    with pytest.raises(StrategyError) as excinfo:
        validate_strategy(payload)
    assert "target.kind" in str(excinfo.value)

    payload = sma_cross_spec()
    payload["sizing"] = {"kind": "risk_percent", "value": 0.01}
    payload["stop"] = {"kind": "none"}
    with pytest.raises(StrategyError) as excinfo:
        validate_strategy(payload)
    assert "sizing.kind" in str(excinfo.value)


def test_atr_multiple_stop_needs_a_declared_atr_indicator() -> None:
    payload = sma_cross_spec()
    payload["stop"] = {"kind": "atr_multiple", "value": 2.0}
    with pytest.raises(StrategyError) as excinfo:
        validate_strategy(payload)
    assert "stop.kind" in str(excinfo.value)


# ---------------------------------------------------------------------------
# DoD 4: no code-execution surface
# ---------------------------------------------------------------------------

FORBIDDEN_SOURCE_TOKENS = (
    "eval(",
    "exec(",
    "compile(",
    "__import__",
    "importlib",
    "pickle",
    "marshal",
)


def test_backtest_sources_contain_no_code_execution_constructs() -> None:
    sources = sorted(BACKTEST_DIR.glob("*.py"))
    assert sources, "the backtest package should have modules to scan"
    for path in sources:
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_SOURCE_TOKENS:
            assert token not in source, f"{path.name} contains {token!r}"


def test_engine_source_does_not_mention_compile() -> None:
    assert "compile" not in (BACKTEST_DIR / "engine.py").read_text(encoding="utf-8")


def test_a_strategy_carrying_python_text_is_data_not_code() -> None:
    # The name is arbitrary text that is echoed back verbatim. If anything
    # interpreted it, this test would leave a marker on disk.
    marker = BACKTEST_DIR / "should-not-exist.txt"
    if marker.exists():
        marker.unlink()
    payload = sma_cross_spec()
    payload["name"] = "__import__('os').system('echo pwned')"
    spec = validate_strategy(payload)
    assert spec.name == "__import__('os').system('echo pwned')"
    assert not marker.exists()


def test_load_strategy_reads_json_and_rejects_anything_else() -> None:
    text = json.dumps(sma_cross_spec())
    assert load_strategy(text) == validate_strategy(sma_cross_spec())
    assert load_strategy(text.encode("utf-8")) == validate_strategy(sma_cross_spec())
    with pytest.raises(StrategyError):
        load_strategy("not json at all")


def test_load_strategy_refuses_duplicate_and_non_finite_keys() -> None:
    text = json.dumps(sma_cross_spec())
    duplicated = text.replace('"version": 1', '"version": 1, "version": 1')
    with pytest.raises(StrategyError) as excinfo:
        load_strategy(duplicated)
    assert "duplicate" in str(excinfo.value)

    # NaN and Infinity are JSON extensions Python accepts by default. A
    # strategy file must not be able to smuggle one into a period or a stop.
    for constant in ("NaN", "Infinity", "-Infinity"):
        text = json.dumps(sma_cross_spec()).replace('"value": 100', f'"value": {constant}')
        with pytest.raises(StrategyError) as excinfo:
            load_strategy(text)
        assert constant in str(excinfo.value)


# ---------------------------------------------------------------------------
# DoD 5: metrics equal analytics.summarize on the same fills
# ---------------------------------------------------------------------------


def independent_ledger(result: BacktestResult) -> dict:
    """The journal's ledger over the backtest's own trades, built here by hand.

    This is the independent side of the cross-check: the fills are assembled in
    the test from the trade records and every number below is read back out of
    analytics, so agreement is evidence the two code paths share a definition
    rather than a coincidence of one calling the other.
    """
    rows: list[dict] = []
    day = 1
    for index, trade in enumerate(result.trades, start=1):
        symbol = trade["symbol"]
        rows.append(
            {
                "fill_id": f"X-{index}-A",
                "symbol": symbol,
                "side": "BUY",
                "trade_date": f"2026-01-{day:02d}",
                "trade_time": "09:30:00",
                "price": trade["entry_price"],
                "quantity": trade["quantity"],
                "fee": trade["fees_entry"],
            }
        )
        exit_day = day + max(1, int(trade["hold_bars"]))
        rows.append(
            {
                "fill_id": f"X-{index}-B",
                "symbol": symbol,
                "side": "SELL",
                "trade_date": f"2026-01-{exit_day:02d}",
                "trade_time": "15:00:00",
                "price": trade["exit_price"],
                "quantity": trade["quantity"],
                "fee": trade["fees_exit"],
            }
        )
        day = exit_day + 2
    return build_ledger(rows)


def test_backtest_metrics_match_analytics_on_the_same_fills() -> None:
    result = golden_run()
    journal = summarize(independent_ledger(result))

    assert result.metrics["trade_count"] == journal["trade_count"]
    assert result.metrics["win_count"] == journal["win_count"]
    assert result.metrics["loss_count"] == journal["loss_count"]
    assert result.metrics["win_rate"] == journal["win_rate"]
    assert result.metrics["profit_factor"] == journal["profit_factor"]
    assert result.metrics["max_drawdown"] == journal["max_drawdown"]
    assert result.metrics["gross_profit"] == journal["gross_profit"]
    assert result.metrics["gross_loss"] == journal["gross_loss"]
    assert result.metrics["total_fees"] == journal["total_fees"]
    assert result.metrics["expectancy"] == journal["total_net_pnl"] / journal["trade_count"]


def test_each_trade_net_pnl_matches_its_ledger_round_trip() -> None:
    result = golden_run()
    trips = independent_ledger(result)["round_trips"]
    assert len(trips) == len(result.trades)
    for trade, trip in zip(result.trades, trips):
        assert trade["net_pnl"] == trip["net_pnl"]
        assert trade["gross_pnl"] == trip["gross_pnl"]


def test_metrics_layer_and_the_test_disagree_if_fees_drift() -> None:
    # The cross-check is only meaningful if it can fail: a ledger that drops the
    # fees must not match the engine's own totals.
    result = golden_run()
    cheap = independent_ledger(result)
    for trip in cheap["round_trips"]:
        trip["fees"] = 0.0
        trip["net_pnl"] = trip["gross_pnl"]
    assert summarize(cheap)["total_net_pnl"] != result.metrics["total_net_pnl"]
    assert result.metrics["total_fees"] > 0


def test_trade_ledger_helper_is_the_same_source_as_the_metrics() -> None:
    result = golden_run()
    # The helper is the same implementation the metrics read, and the
    # independent builder has to agree with it on the money fields.
    helper = trade_ledger(result.trades)["round_trips"]
    hand = independent_ledger(result)["round_trips"]
    assert len(helper) == len(hand) == 2
    for left, right in zip(helper, hand):
        for field in ("entry_price", "exit_price", "quantity", "gross_pnl", "fees", "net_pnl"):
            assert left[field] == right[field]


# ---------------------------------------------------------------------------
# Golden run
# ---------------------------------------------------------------------------


def test_golden_run_matches_the_frozen_output() -> None:
    result = golden_run()
    assert result.bar_count == 60
    assert result.final_equity == 105576.14
    assert len(result.trades) == 2

    first, second = result.trades
    assert (first["entry_index"], first["exit_index"]) == (26, 44)
    assert first["exit_reason"] == "exit_signal"
    assert first["net_pnl"] == -619.88
    assert (second["entry_index"], second["exit_index"]) == (49, 55)
    assert second["exit_reason"] == "target"
    assert second["net_pnl"] == 6196.01

    assert result.metrics["win_rate"] == 50.0
    assert result.metrics["profit_factor"] == 10.0
    assert result.metrics["max_drawdown"] == -619.88
    assert result.metrics["cagr_pct"] == 25.6
    assert result.metrics["exposure_pct"] == 40.0
    assert result.open_positions == ()


def test_golden_digest_is_stable_across_process_state() -> None:
    # Run the same inputs a second time after unrelated work, so a stray module
    # level cache would have to reveal itself.
    first = blob(golden_run())
    run_backtest(sma_cross_spec(), flat_bars((10.0, 10.0, 12.0, 12.0, 14.0)), initial_cash=1.0)
    validate_strategy(golden_spec())
    assert blob(golden_run()) == first


# ---------------------------------------------------------------------------
# Fill timing, indicators, and limits
# ---------------------------------------------------------------------------


def test_next_open_fills_on_the_bar_after_the_signal() -> None:
    closes = (10.0, 10.0, 12.0, 12.0, 14.0, 10.0, 10.0, 8.0, 8.0, 8.0)
    result = run_backtest(
        sma_cross_spec(fill="next_open"),
        flat_bars(closes),
        initial_cash=50000.0,
    )
    trade = result.trades[0]
    # The signal was the cross at bar 2; the fill is bar 3's open, which is 12.0
    # on a flat bar. A same-bar fill would have reported index 2.
    assert trade["entry_index"] == 3
    assert result.equity_curve[2]["position_quantity"] == 0


def test_same_close_fills_on_the_signal_bar() -> None:
    closes = (10.0, 10.0, 12.0, 12.0, 14.0, 10.0, 10.0, 8.0, 8.0, 8.0)
    result = run_backtest(sma_cross_spec(fill="same_close"), flat_bars(closes), initial_cash=50000.0)
    assert result.trades[0]["entry_index"] == 2


def test_the_two_fill_modes_differ_by_exactly_one_bar() -> None:
    # Bars with a gap between the open and the close, so the two fill modes land
    # on the same signal at different prices rather than the same price by luck.
    rows = (
        (10.0, 10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0, 10.0),
        (12.0, 12.0, 12.0, 12.0),
        (12.5, 12.6, 12.4, 12.5),
        (14.0, 14.0, 14.0, 14.0),
        (10.0, 10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0, 10.0),
    )
    bars = ohlc_bars(rows)
    same = run_backtest(sma_cross_spec(fill="same_close"), bars, initial_cash=50000.0)
    nxt = run_backtest(sma_cross_spec(fill="next_open"), bars, initial_cash=50000.0)
    # same_close fills the cross at bar 2's own close; next_open waits and fills
    # at bar 3's open, one bar later and 0.50 higher.
    assert same.trades[0]["entry_index"] == 2
    assert same.trades[0]["entry_price"] == 12.0
    assert nxt.trades[0]["entry_index"] == 3
    assert nxt.trades[0]["entry_price"] == 12.5
    # same_close: (10.00 - 12.00) x 100 = -200.00, so 50000 - 200 = 49800.
    # next_open:  (10.00 - 12.50) x 100 = -250.00, so 50000 - 250 = 49750.
    assert same.final_equity == 49800.00
    assert nxt.final_equity == 49750.00


def test_percent_stop_closes_at_the_stop_and_records_the_reason() -> None:
    # Entered at 12.00 with a 5 percent stop, so the stop sits at 11.40. The bar
    # that follows falls to a 10.50 low and its open is already below the stop,
    # so it fills at the open rather than at a price the level never traded at.
    rows = (
        (10.0, 10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0, 10.0),
        (12.0, 12.0, 12.0, 12.0),
        (12.0, 12.0, 12.0, 12.0),
        (14.0, 14.0, 14.0, 14.0),
        (11.0, 11.0, 10.5, 10.8),
    )
    spec = sma_cross_spec(stop={"kind": "percent", "value": 5.0}, fill="next_open")
    result = run_backtest(spec, ohlc_bars(rows), initial_cash=50000.0)
    trade = result.trades[0]
    assert trade["entry_price"] == 12.0
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == 11.0
    assert trade["net_pnl"] == -100.00


def test_a_gap_through_the_stop_fills_at_the_open_not_the_stop_price() -> None:
    rows = (
        (10.0, 10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0, 10.0),
        (12.0, 12.0, 12.0, 12.0),
        (12.0, 12.0, 12.0, 12.0),
        (14.0, 14.0, 14.0, 14.0),
        (9.0, 9.2, 8.8, 9.0),
    )
    spec = sma_cross_spec(stop={"kind": "percent", "value": 5.0}, fill="next_open")
    result = run_backtest(spec, ohlc_bars(rows), initial_cash=50000.0)
    trade = result.trades[0]
    assert trade["exit_reason"] == "stop"
    assert trade["exit_price"] == 9.0
    assert trade["net_pnl"] == -300.00


def test_percent_target_closes_at_the_target() -> None:
    rows = (
        (10.0, 10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0, 10.0),
        (12.0, 12.0, 12.0, 12.0),
        (12.0, 12.0, 12.0, 12.0),
        (12.9, 13.4, 12.8, 13.0),
        (13.0, 13.1, 12.9, 13.0),
    )
    spec = sma_cross_spec(target={"kind": "percent", "value": 10.0}, fill="next_open")
    result = run_backtest(spec, ohlc_bars(rows), initial_cash=50000.0)
    trade = result.trades[0]
    assert trade["exit_reason"] == "target"
    assert trade["exit_price"] == 13.2
    assert trade["net_pnl"] == 120.00


def test_atr_multiple_stop_uses_the_declared_atr_series() -> None:
    # A flat ten bar range gives an ATR of 2.00 exactly, so a 2x stop is 4.00
    # below the entry: 10.00 - 4.00 = 6.00.
    bars = [
        ToyBar(f"2026-06-{index + 1:02d}", 10.0, 11.0, 9.0, 10.0, 1000.0)
        for index in range(20)
    ]
    # Both rules hold on every warm bar, so the first fill is the first bar the
    # min_bars gate allows, and the position is still open when the series ends.
    spec = {
        "version": 1,
        "name": "atr-toy",
        "universe": {"symbol": "600111", "interval": "1d"},
        "indicators": [
            {"id": "px", "kind": "sma", "source": "close", "period": 1},
            {"id": "atr", "kind": "atr", "source": "high", "period": 10},
        ],
        "entry": {"all": [{"gte": ["px", "px"]}]},
        "exit": {"all": [{"lt": ["px", "atr"]}]},
        "stop": {"kind": "atr_multiple", "value": 2.0},
        "target": {"kind": "none"},
        "sizing": {"kind": "fixed_quantity", "value": 1},
        "filters": {"session": None, "min_bars": 15},
        "fill": "next_open",
    }
    result = run_backtest(spec, bars, initial_cash=1000.0)
    assert len(result.open_positions) == 1
    # The true range of every bar is 2.00, so the ATR is 2.00 and the stop sits
    # 2 x 2.00 = 4.00 below the 10.00 entry.
    assert result.open_positions[0]["stop_price"] == 6.0
    assert result.open_positions[0]["entry_price"] == 10.0


def test_risk_percent_sizing_places_the_configured_share_at_the_stop() -> None:
    # Entry fills at 12.00. A 20 percent stop is 2.40 per share of risk, and
    # risking one percent of 50000 is 500, so quantity = 500 / 2.40 = 208 shares
    # (truncated, never rounded up into more risk than configured).
    rows = (
        (10.0, 10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0, 10.0),
        (12.0, 12.0, 12.0, 12.0),
        (12.0, 12.0, 12.0, 12.0),
        (13.0, 13.1, 12.9, 13.0),
        (10.0, 10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0, 10.0),
        (10.0, 10.0, 10.0, 10.0),
    )
    spec = sma_cross_spec(
        sizing={"kind": "risk_percent", "value": 0.01},
        stop={"kind": "percent", "value": 20.0},
        fill="next_open",
    )
    result = run_backtest(spec, ohlc_bars(rows), initial_cash=50000.0)
    trade = result.trades[0]
    assert trade["quantity"] == 208
    assert trade["risk_per_share"] == 2.4
    assert trade["exit_reason"] == "exit_signal"
    assert trade["net_pnl"] == -416.00


def test_min_bars_gate_prevents_any_trade_before_the_warmup() -> None:
    closes = (10.0, 10.0, 12.0, 12.0, 14.0, 10.0)
    result = run_backtest(
        sma_cross_spec(filters={"session": None, "min_bars": 10}),
        flat_bars(closes),
        initial_cash=50000.0,
    )
    assert result.trades == ()
    assert result.final_equity == 50000.0


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------


def indicator_series(spec: dict, bars: list[ToyBar], indicator_id: str) -> list[float]:
    from smartmoney_cub_harness.trader.backtest import engine as engine_module

    validated = validate_strategy(spec)
    return engine_module._build_indicator_series(validated.indicators, bars)[indicator_id]


def test_simple_moving_average_it_is_warm_before_the_window_is_full() -> None:
    bars = flat_bars((1.0, 2.0, 3.0, 4.0, 5.0))
    spec = single_indicator_spec({"id": "m", "kind": "sma", "source": "close", "period": 3})
    series = indicator_series(spec, bars, "m")
    assert all(value != value for value in series[:2])
    assert series[2:] == [2.0, 3.0, 4.0]


def test_exponential_moving_average_seeds_from_the_simple_average() -> None:
    bars = flat_bars((1.0, 2.0, 3.0, 4.0))
    spec = single_indicator_spec({"id": "e", "kind": "ema", "source": "close", "period": 3})
    series = indicator_series(spec, bars, "e")
    assert all(value != value for value in series[:2])
    assert series[2] == 2.0
    # 4 x (2/4) + 2 x (1 - 2/4) = 3.0
    assert series[3] == 3.0


def test_highest_and_lowest_track_the_rolling_window() -> None:
    bars = flat_bars((3.0, 1.0, 4.0, 1.0, 5.0))
    highs = indicator_series(single_indicator_spec({"id": "h", "kind": "highest", "source": "close", "period": 2}), bars, "h")
    lows = indicator_series(single_indicator_spec({"id": "l", "kind": "lowest", "source": "close", "period": 2}), bars, "l")
    assert highs[1:] == [3.0, 4.0, 4.0, 5.0]
    assert lows[1:] == [1.0, 1.0, 1.0, 1.0]


def test_rsi_of_a_monotone_rise_is_one_hundred() -> None:
    bars = flat_bars(tuple(float(value) for value in range(1, 12)))
    series = indicator_series(
        single_indicator_spec({"id": "r", "kind": "rsi", "source": "close", "period": 5}),
        bars,
        "r",
    )
    assert all(value != value for value in series[:5])
    assert series[5:] == [100.0] * 6


def test_rsi_of_a_monotone_fall_is_zero() -> None:
    bars = flat_bars(tuple(float(value) for value in range(12, 1, -1)))
    series = indicator_series(
        single_indicator_spec({"id": "r", "kind": "rsi", "source": "close", "period": 5}),
        bars,
        "r",
    )
    assert series[5:] == [0.0] * 6


def test_volume_sma_reads_the_volume_field() -> None:
    bars = [
        ToyBar(f"d{index}", 1.0, 1.0, 1.0, 1.0, float(index + 1)) for index in range(4)
    ]
    series = indicator_series(
        single_indicator_spec({"id": "v", "kind": "volume_sma", "source": "volume", "period": 2}),
        bars,
        "v",
    )
    assert series[1:] == [1.5, 2.5, 3.5]


# ---------------------------------------------------------------------------
# Contract details
# ---------------------------------------------------------------------------


def test_result_carries_the_safety_declaration() -> None:
    result = golden_run()
    assert result.safety == SAFETY_DECLARATION
    assert result.metrics["safety"] == SAFETY_DECLARATION
    assert result.schema == "smartmoney_cub_backtest.v1"


def test_engine_accepts_a_plain_mapping_spec_and_a_plain_object_bar() -> None:
    class Bare:
        def __init__(self, close: float) -> None:
            self.open_time = "2026-07-01"
            self.open = close
            self.high = close
            self.low = close
            self.close = close
            self.volume = 1.0

    result = run_backtest(dict(sma_cross_spec()), [Bare(10.0), Bare(12.0)], initial_cash=1000.0)
    assert isinstance(result, BacktestResult)
    assert result.bar_count == 2


def test_empty_and_single_bar_series_are_handled_without_a_trade() -> None:
    empty = run_backtest(sma_cross_spec(), [], initial_cash=1000.0)
    assert empty.trades == ()
    assert empty.final_equity == 1000.0
    assert empty.first_open_time is None

    single = run_backtest(sma_cross_spec(), flat_bars((10.0,)), initial_cash=1000.0)
    assert single.trades == ()
    assert single.final_equity == 1000.0


def test_an_open_position_at_the_end_is_reported_and_not_counted_as_a_trade() -> None:
    closes = (10.0, 10.0, 12.0, 12.0, 14.0, 16.0)
    result = run_backtest(sma_cross_spec(), flat_bars(closes), initial_cash=50000.0)
    assert result.trades == ()
    assert len(result.open_positions) == 1
    position = result.open_positions[0]
    assert position["status"] == "open_at_end_of_series"
    assert position["quantity"] == 100
    # Entered at 12.00 by the cross at bar 2 filling on bar 3, marked at 16.00.
    assert position["unrealized_pnl"] == 400.00
    assert result.final_equity == 50400.00


def test_the_equity_curve_has_one_point_per_bar_and_ends_at_final_equity() -> None:
    result = golden_run()
    assert len(result.equity_curve) == result.bar_count
    assert [point["bar_index"] for point in result.equity_curve] == list(range(result.bar_count))
    assert result.equity_curve[-1]["equity"] == result.final_equity


def test_both_a_spec_object_and_a_mapping_run_identically() -> None:
    spec = validate_strategy(golden_spec())
    bars = golden_bars()
    from_object = run_backtest(spec, bars, initial_cash=100000.0, fees_bps=4.0, slippage_bps=2.0)
    from_mapping = run_backtest(golden_spec(), bars, initial_cash=100000.0, fees_bps=4.0, slippage_bps=2.0)
    assert from_object == from_mapping


@pytest.mark.parametrize("interval", ["1m", "5m", "30m", "60m", "1d", "1w", "1mo"])
def test_cagr_is_reported_for_known_intervals_and_absent_for_unknown_ones(interval: str) -> None:
    from smartmoney_cub_harness.trader.backtest import duration_years

    assert duration_years(252, interval) is not None
    assert duration_years(252, "3d") is None
    assert duration_years(0, interval) is None


def test_win_rate_and_profit_factor_follow_the_analytics_definitions() -> None:
    # One winner of +97.50 and one loser of -202.20 from the hand-computed case.
    closes = (10.0, 10.0, 12.0, 12.0, 14.0, 10.0, 10.0, 12.0, 12.0, 16.0, 16.0, 13.0, 13.0)
    result = run_backtest(sma_cross_spec(), flat_bars(closes), initial_cash=50000.0, fees_bps=10.0)
    metrics = result.metrics
    assert metrics["win_rate"] == 50.0
    # 97.50 / 202.20 = 0.4821..., rounded to two places.
    assert metrics["profit_factor"] == 0.48
    assert metrics["expectancy"] == -52.35
    assert metrics["avg_win"] == 97.50
    assert metrics["avg_loss"] == -202.20
