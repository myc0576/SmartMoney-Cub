from smartmoney_cub_harness.analytics import summarize, group_performance, calendar_days
from smartmoney_cub_harness.fills import build_fill_ledger, ledger_to_analysis_trades


def ledger():
    return {"round_trips": [{"round_trip_id": "RT-" + currency, "symbol": "TOY", "currency": currency,
                             "net_pnl": pnl, "fees": 1, "return_pct": 2, "holding_days": 1,
                             "entry_time": "2026-08-01T15:00:00Z", "exit_time": "2026-08-02T15:00:00Z"}
                            for currency, pnl in (("USD", 10), ("JPY", 1000))]}


def test_mixed_currency_totals_are_not_summed_without_fx():
    summary = summarize(ledger())
    assert summary["total_net_pnl"] is None
    assert summary["profit_factor"] is None
    assert summary["equity_curve"] == []
    assert summary["trade_count"] == 2
    assert summary["mixed_currency"] is True
    assert {c["currency"]: c["net_pnl"] for c in summary["currency_breakdown"]} == {"USD": 10, "JPY": 1000}


def test_unknown_currency_is_not_a_comparable_unit_even_in_one_bucket():
    data = ledger()
    for trip in data['round_trips']:
        trip['currency'] = 'UNKNOWN'
    result = summarize(data)
    assert result['total_net_pnl'] is None
    assert result['profit_factor'] is None
    assert result['equity_curve'] == []
    assert result['currency_breakdown'][0]['net_pnl'] is None
    assert group_performance(data, dimension='symbol')[0]['net_pnl'] is None
    assert calendar_days(data, year=2026, month=8)[0]['net_pnl'] is None


def test_breakdown_and_calendar_keep_iso_dates_and_currency_boundaries():
    row = group_performance(ledger(), dimension="symbol")[0]
    assert row["net_pnl"] is None
    assert len(row["currency_breakdown"]) == 2
    day = calendar_days(ledger(), year=2026, month=8)[0]
    assert day["date"] == "2026-08-02"
    assert day["net_pnl"] is None
    assert day["trade_count"] == 2


def test_real_fill_matching_preserves_currency_account_and_instrument():
    fills = []
    for currency in ("USD", "JPY"):
        for side, day, price in (("BUY", "01", 10), ("SELL", "02", 11)):
            fills.append({"fill_id": currency + side, "account_id": currency,
                          "symbol": "TOY", "instrument_id": "TOY-" + currency,
                          "side": side, "trade_date": "2026-08-" + day,
                          "trade_time": "12:00:00", "quantity": 1, "price": price,
                          "currency": currency, "market": "UNKNOWN", "fee": 0})
    actual = build_fill_ledger(fills, market="UNKNOWN")
    assert {(t["account_id"], t["instrument_id"], t["currency"]) for t in actual["round_trips"]} == {
        ("USD", "TOY-USD", "USD"), ("JPY", "TOY-JPY", "JPY")}
    assert summarize(actual)["mixed_currency"] is True
    assert summarize(actual)["total_net_pnl"] is None
    assert {t["currency"] for t in ledger_to_analysis_trades(actual)} == {"USD", "JPY"}
    assert {t["account_id"] for t in ledger_to_analysis_trades(actual)} == {"USD", "JPY"}
