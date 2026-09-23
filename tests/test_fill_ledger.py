from __future__ import annotations

from smartmoney_cub_harness.fills import (
    DEFAULT_FEE_POLICY,
    build_fill_ledger,
    estimate_fees,
    ledger_to_analysis_trades,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _buy(symbol: str, date: str, price: float, qty: int, **extra: object) -> dict:
    row = {
        "date": date,
        "time": "09:40:00",
        "symbol": symbol,
        "name": symbol,
        "side": "BUY",
        "price": price,
        "quantity": qty,
    }
    row.update(extra)
    return row


def _sell(symbol: str, date: str, price: float, qty: int, **extra: object) -> dict:
    row = {
        "date": date,
        "time": "14:00:00",
        "symbol": symbol,
        "name": symbol,
        "side": "SELL",
        "price": price,
        "quantity": qty,
    }
    row.update(extra)
    return row


def _issue_codes(ledger: dict) -> set[str]:
    return {issue["code"] for issue in ledger["issues"]}


def test_simple_round_trip_is_matched_across_days() -> None:
    ledger = build_fill_ledger([_buy("600111", "2026-09-01", 10.0, 1000), _sell("600111", "2026-09-02", 11.0, 1000)])
    assert ledger["status"] == "ok"
    assert ledger["counts"]["round_trips"] == 1
    trip = ledger["round_trips"][0]
    assert trip["entry_price"] == 10.0
    assert trip["exit_price"] == 11.0
    assert trip["holding_days"] == 1
    assert trip["net_pnl"] > 0
    assert trip["safety"] if "safety" in trip else True
    assert ledger["safety"] == SAFETY_DECLARATION


def test_t_plus_one_same_day_sell_is_blocked() -> None:
    ledger = build_fill_ledger([_buy("000001", "2026-09-01", 10.0, 1000), _sell("000001", "2026-09-01", 11.0, 1000)], market="CN-A")
    assert ledger["status"] == "needs_review"
    assert "t_plus_one_violation" in _issue_codes(ledger)
    assert ledger["counts"]["round_trips"] == 0


def test_sell_without_position_is_blocked_not_invented() -> None:
    ledger = build_fill_ledger([_sell("600519", "2026-09-02", 1500.0, 100)])
    assert ledger["status"] == "needs_review"
    assert "sell_without_position" in _issue_codes(ledger)
    assert ledger["round_trips"] == []


def test_partial_close_keeps_remaining_position_open() -> None:
    ledger = build_fill_ledger(
        [
            _buy("600111", "2026-09-01", 10.0, 1000),
            _sell("600111", "2026-09-02", 11.0, 400),
        ]
    )
    assert ledger["counts"]["round_trips"] == 1
    assert ledger["round_trips"][0]["quantity"] == 400
    assert ledger["round_trips"][0]["exit_complete"] is True
    open_positions = ledger["open_positions"]
    assert len(open_positions) == 1
    assert open_positions[0]["quantity"] == 600
    assert "unpaired_buy" in _issue_codes(ledger)


def test_batched_buys_match_first_in_first_out() -> None:
    ledger = build_fill_ledger(
        [
            _buy("600111", "2026-09-01", 10.0, 1000),
            _buy("600111", "2026-09-02", 9.0, 1000),
            _sell("600111", "2026-09-03", 12.0, 1000),
        ]
    )
    trip = ledger["round_trips"][0]
    # FIFO must attribute the oldest lot, then report the assumption.
    assert trip["entry_price"] == 10.0
    assert trip["cost_basis_assumed"] is False
    assert "cost_basis_assumed_fifo" in _issue_codes(ledger)
    remaining = ledger["open_positions"][0]
    assert remaining["quantity"] == 1000
    assert remaining["avg_cost"] == 9.0


def test_sell_spanning_multiple_lots_is_flagged_as_assumed_basis() -> None:
    ledger = build_fill_ledger(
        [
            _buy("600111", "2026-09-01", 10.0, 1000),
            _buy("600111", "2026-09-02", 9.0, 1000),
            _sell("600111", "2026-09-03", 12.0, 1500),
        ]
    )
    trip = ledger["round_trips"][0]
    assert trip["cost_basis_assumed"] is True
    assert len(trip["matched_lots"]) == 2


def test_oversell_is_blocked() -> None:
    ledger = build_fill_ledger(
        [
            _buy("600111", "2026-09-01", 10.0, 500),
            _sell("600111", "2026-09-02", 11.0, 800),
        ]
    )
    assert ledger["status"] == "needs_review"
    assert "oversell" in _issue_codes(ledger)


def test_duplicate_fill_rows_are_not_double_counted() -> None:
    row = _buy("600111", "2026-09-01", 10.0, 1000)
    ledger = build_fill_ledger([row, dict(row)])
    assert ledger["counts"]["fills"] == 1
    assert "duplicate_fill" in _issue_codes(ledger)


def test_zero_quantity_and_invalid_price_are_blocked() -> None:
    ledger = build_fill_ledger(
        [
            _buy("600111", "2026-09-01", 10.0, 0),
            _buy("600222", "2026-09-01", 0.0, 1000),
        ]
    )
    assert ledger["status"] == "needs_review"
    codes = _issue_codes(ledger)
    assert "zero_quantity" in codes
    assert "invalid_price" in codes


def test_unknown_side_is_blocked() -> None:
    ledger = build_fill_ledger(
        [{"date": "2026-09-01", "symbol": "600111", "name": "x", "side": "TRANSFER", "price": 10.0, "quantity": 100}]
    )
    assert ledger["status"] == "needs_review"
    assert "unknown_side" in _issue_codes(ledger)


def test_missing_symbol_is_blocked() -> None:
    ledger = build_fill_ledger([{"date": "2026-09-01", "side": "BUY", "price": 10.0, "quantity": 100}])
    assert "missing_symbol" in _issue_codes(ledger)


def test_non_trade_rows_are_skipped_as_warning_only() -> None:
    ledger = build_fill_ledger(
        [
            {"date": "2026-09-01", "action": "银行转证券", "price": 0, "quantity": 0},
            _buy("600111", "2026-09-01", 10.0, 1000),
            _sell("600111", "2026-09-02", 11.0, 1000),
        ]
    )
    assert ledger["status"] == "ok"
    assert "non_trade_row" in _issue_codes(ledger)
    assert ledger["counts"]["round_trips"] == 1


def test_limit_board_and_suspension_markers_are_surfaced() -> None:
    ledger = build_fill_ledger(
        [
            _buy("600111", "2026-09-01", 10.0, 1000, remark="涨停一字"),
            _buy("600222", "2026-09-01", 5.0, 1000, remark="停牌"),
        ]
    )
    codes = _issue_codes(ledger)
    assert "limit_board_fill" in codes
    assert "suspended_or_no_trade" in codes


def test_fees_are_estimated_when_not_declared_and_used_when_declared() -> None:
    estimated = build_fill_ledger([_buy("600111", "2026-09-01", 10.0, 1000)], market="CN-A")
    assert "fees_estimated" in _issue_codes(estimated)

    declared = build_fill_ledger(
        [_buy("600111", "2026-09-01", 10.0, 1000, commission=5.0, transfer_fee=0.1)]
    )
    assert "fees_estimated" not in _issue_codes(declared)

    fees = estimate_fees("SELL", 10.0, 1000, DEFAULT_FEE_POLICY)
    # Stamp duty applies on the sell side only.
    assert fees["stamp_duty"] > 0
    buy_fees = estimate_fees("BUY", 10.0, 1000, DEFAULT_FEE_POLICY)
    assert buy_fees["stamp_duty"] == 0


def test_fees_reduce_realised_return() -> None:
    gross = build_fill_ledger(
        [
            _buy("600111", "2026-09-01", 10.0, 1000, commission=0.0, transfer_fee=0.0),
            _sell("600111", "2026-09-02", 11.0, 1000, commission=0.0, stamp_duty=0.0, transfer_fee=0.0),
        ]
    )
    with_fees = build_fill_ledger(
        [
            _buy("600111", "2026-09-01", 10.0, 1000),
            _sell("600111", "2026-09-02", 11.0, 1000),
        ], market="CN-A"
    )
    assert with_fees["round_trips"][0]["net_pnl"] < gross["round_trips"][0]["net_pnl"]


def test_chinese_broker_export_headers_are_understood() -> None:
    ledger = build_fill_ledger(
        [
            {
                "成交日期": "2026-09-01",
                "成交时间": "09:40:00",
                "证券代码": "600111",
                "证券名称": "北方稀土",
                "买卖标志": "证券买入",
                "成交均价": "10.00",
                "成交数量": "1000",
                "买入理由": "主线龙头",
            },
            {
                "成交日期": "2026-09-02",
                "成交时间": "14:00:00",
                "证券代码": "600111",
                "证券名称": "北方稀土",
                "买卖标志": "证券卖出",
                "成交均价": "11.00",
                "成交数量": "1000",
            },
        ]
    )
    assert ledger["status"] == "ok"
    trip = ledger["round_trips"][0]
    assert trip["symbol"] == "600111"
    assert trip["name"] == "北方稀土"
    assert trip["thesis"] == "主线龙头"


def test_unsupported_cost_basis_falls_back_to_fifo_with_warning() -> None:
    ledger = build_fill_ledger(
        [_buy("600111", "2026-09-01", 10.0, 1000), _sell("600111", "2026-09-02", 11.0, 1000)],
        cost_basis="lifo",
    )
    assert "cost_basis_assumed_fifo" in _issue_codes(ledger)
    assert ledger["counts"]["round_trips"] == 1


def test_ledger_projects_to_analysis_trades() -> None:
    ledger = build_fill_ledger(
        [_buy("600111", "2026-09-01", 10.0, 1000, thesis="主线"), _sell("600111", "2026-09-02", 11.0, 1000)]
    )
    trades = ledger_to_analysis_trades(ledger)
    assert len(trades) == 1
    assert trades[0]["symbol"] == "600111"
    assert trades[0]["volume"] == 1000
    assert trades[0]["thesis"] == "主线"
    assert trades[0]["cost_basis_assumed"] is False


def test_ledger_never_emits_order_or_execution_fields() -> None:
    ledger = build_fill_ledger(
        [_buy("600111", "2026-09-01", 10.0, 1000), _sell("600111", "2026-09-02", 11.0, 1000)]
    )
    serialised = str(ledger).lower()
    for forbidden in ("place_order", "cancel_order", "broker_api", "account_number"):
        assert forbidden not in serialised


def test_empty_input_yields_empty_ledger() -> None:
    ledger = build_fill_ledger([])
    assert ledger["status"] == "ok"
    assert ledger["counts"]["fills"] == 0
    assert ledger["round_trips"] == []


def test_fractional_quantity_and_global_instrument_metadata_round_trip() -> None:
    ledger = build_fill_ledger(
        [{"date": "2026-09-01", "symbol": "TOY-ETF", "side": "BUY", "price": 10, "quantity": 0.25,
          "currency": "USD", "multiplier": 100, "time_precision": "millisecond"}],
        market="US",
    )
    fill = ledger["fills"][0]
    assert fill["quantity"] == 0.25
    assert fill["currency"] == "USD"
    assert fill["multiplier"] == 100.0
    assert fill["time_precision"] == "millisecond"
    assert fill["trade_time"] == ""
    assert ledger["safety"] == SAFETY_DECLARATION


def test_non_cn_policy_allows_same_day_fractional_close() -> None:
    ledger = build_fill_ledger(
        [_buy("TOY-ETF", "2026-09-01", 10, 0.25), _sell("TOY-ETF", "2026-09-01", 11, 0.25)],
        market="US", market_policy="none",
    )
    assert ledger["status"] == "ok"
    assert ledger["round_trips"][0]["quantity"] == 0.25


def test_account_and_currency_scope_are_not_cross_matched() -> None:
    ledger = build_fill_ledger([
        _buy("TOY", "2026-09-01", 10, 1, account_id="A", currency="USD"),
        _sell("TOY", "2026-09-02", 11, 1, account_id="B", currency="USD"),
    ], market="US", market_policy="none")
    assert "sell_without_position" in _issue_codes(ledger)


def test_identical_economic_fills_in_distinct_accounts_are_retained() -> None:
    ledger = build_fill_ledger([
        _buy("TOY", "2026-09-01", 10, 1, account_id="A", currency="USD"),
        _buy("TOY", "2026-09-01", 10, 1, account_id="B", currency="USD"),
    ], market="US", market_policy="none")
    assert ledger["counts"]["fills"] == 2
    assert {(row["account_id"], row["quantity"]) for row in ledger["open_positions"]} == {
        ("A", 1.0), ("B", 1.0)
    }
    assert len({row["position_id"] for row in ledger["open_positions"]}) == 2


def test_explicit_fractional_short_open_and_cover_uses_multiplier() -> None:
    ledger = build_fill_ledger([
        _sell("FUT-X", "2026-09-01", 100, 0.5, side="SELL_OPEN", time="09:00:00", instrument_id="FUT-X-SEP", account_id="A", currency="USD", multiplier=10, fee=0),
        _buy("FUT-X", "2026-09-01", 90, 0.5, side="BUY_CLOSE", instrument_id="FUT-X-SEP", account_id="A", currency="USD", multiplier=10, fee=0),
    ], market="FUTURES", allow_shorts=True)
    assert ledger["status"] == "ok"
    trip = ledger["round_trips"][0]
    assert trip["position_side"] == "SHORT"
    assert trip["quantity"] == 0.5
    assert trip["multiplier"] == 10
    assert trip["gross_pnl"] == 50
    assert ledger["open_positions"] == []


def test_partial_short_cover_keeps_negative_signed_position_then_closes() -> None:
    ledger = build_fill_ledger([
        _sell("FUT-X", "2026-09-01", 100, 1.5, side="SELL_OPEN", time="09:00:00", account_id="A", currency="USD", multiplier=10, fee=0),
        _buy("FUT-X", "2026-09-01", 90, 0.5, side="BUY_CLOSE", account_id="A", currency="USD", multiplier=10, fee=0),
    ], market="FUTURES", allow_shorts=True)
    assert ledger["open_positions"][0]["position_side"] == "SHORT"
    assert ledger["open_positions"][0]["quantity"] == -1.0


def test_short_cover_before_open_is_not_future_matched() -> None:
    ledger = build_fill_ledger([
        _buy("FUT-X", "2026-09-01", 90, 0.5, side="BUY_CLOSE", time="09:00:00", account_id="A", currency="USD", multiplier=10, fee=0),
        _sell("FUT-X", "2026-09-01", 100, 0.5, side="SELL_OPEN", time="09:40:00", account_id="A", currency="USD", multiplier=10, fee=0),
    ], market="FUTURES", allow_shorts=True)
    assert "sell_without_position" in _issue_codes(ledger)
    assert ledger["round_trips"] == []


def test_unknown_market_does_not_apply_cn_t_plus_one() -> None:
    ledger = build_fill_ledger([_buy("TOY", "2026-09-01", 10, 1), _sell("TOY", "2026-09-01", 11, 1)], market="unknown")
    assert "t_plus_one_violation" not in _issue_codes(ledger)
    assert ledger["counts"]["round_trips"] == 1
