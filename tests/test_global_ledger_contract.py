"""Global-market journal policy using toy executions only."""
from smartmoney_cub_harness.fills import build_fill_ledger
from decimal import Decimal
import json


def pair(**extra):
    return [{"fill_id": side, "symbol": "TOY", "account_id": "toy", "currency": "USD",
             "trade_date": "2026-09-01", "trade_time": clock, "side": side,
             "price": price, "quantity": 1, **extra}
            for side, clock, price in [("BUY", "10:00:00", 10), ("SELL", "11:00:00", 11)]]


def test_unspecified_market_never_inherits_chinese_t1_or_fees():
    result = build_fill_ledger(pair())
    assert result["market"] == "UNKNOWN"
    assert len(result["round_trips"]) == 1
    assert result["round_trips"][0]["fees"] == 0
    assert result["round_trips"][0]["fees_known"] is False
    assert any(i["code"] == "fees_unknown" for i in result["issues"])
    assert not any(i["code"] in ("fees_estimated", "t_plus_one_violation") for i in result["issues"])


def test_cn_t1_is_applied_per_fill_in_a_mixed_market_ledger():
    result = build_fill_ledger(pair(market="US") + pair(market="CN-A", account_id="cn"))
    assert [t["account_id"] for t in result["round_trips"]] == ["toy"]
    assert any(i["code"] == "t_plus_one_violation" for i in result["issues"])
    assert any(i["code"] == "fees_estimated" for i in result["issues"])


def test_declared_non_cn_or_unknown_market_overrides_legacy_default():
    for declared in ("US", "UNKNOWN"):
        result = build_fill_ledger(pair(market=declared), market="CN-A")
        assert len(result["round_trips"]) == 1
        assert result["round_trips"][0]["fees"] == 0
        assert not any(i["code"] == "fees_estimated" for i in result["issues"])


def test_explicit_cn_default_remains_compatible_for_legacy_imports():
    result = build_fill_ledger(pair(), market="CN-A")
    assert result["round_trips"] == []
    assert any(i["code"] == "t_plus_one_violation" for i in result["issues"])


def test_declared_global_fees_are_kept_and_not_marked_unknown():
    result = build_fill_ledger(pair(market="US", fee=0.1))
    assert result["round_trips"][0]["fees"] == 0.2
    assert result["round_trips"][0]["fees_known"] is True
    assert not any(i["code"] in ("fees_unknown", "fees_estimated") for i in result["issues"])


def test_decimal_partial_closes_leave_no_ghost_position_or_oversell():
    buy, sell = pair(market="US", fee=0)
    rows = [dict(buy, quantity=0.3, quantity_exact="0.3"),
            dict(sell, fill_id="s1", quantity=0.1, quantity_exact="0.1"),
            dict(sell, fill_id="s2", trade_time="12:00:00", quantity=0.2, quantity_exact="0.2")]
    ledger = build_fill_ledger(rows)
    assert ledger["status"] == "ok"
    assert ledger["open_positions"] == []
    assert [t["quantity"] for t in ledger["round_trips"]] == [0.1, 0.2]
    assert sum(Decimal(t["quantity_exact"]) for t in ledger["round_trips"]) == Decimal("0.3")


def test_tiny_crypto_profit_and_fees_survive_partial_allocation():
    buy, sell = pair(market="CRYPTO", fee=0)
    rows = [dict(buy, price_exact="0.00000001", quantity_exact="0.3", fee_exact="0.000000003"),
            dict(sell, fill_id="s1", price_exact="0.00000003", quantity_exact="0.1"),
            dict(sell, fill_id="s2", trade_time="12:00:00", price_exact="0.00000003", quantity_exact="0.2")]
    ledger = build_fill_ledger(rows)
    trips = ledger["round_trips"]
    assert sum(Decimal(t["net_pnl_exact"]) for t in trips) == Decimal("0.000000003")
    assert sum(Decimal(t["fees_exact"]) for t in trips) == Decimal("0.000000003")
    assert all(t["net_pnl"] > 0 for t in trips)
    json.dumps(ledger, allow_nan=False)


def test_exact_prices_survive_lossy_numeric_dto_and_multiplier():
    buy, sell = pair(market="US", fee=0, price=10, quantity=1, multiplier=100)
    ledger = build_fill_ledger([dict(buy, price_exact="10.000000000000000001"),
                                dict(sell, price_exact="10.000000000000000002")])
    trip = ledger["round_trips"][0]
    assert Decimal(trip["gross_pnl_exact"]) == Decimal("0.000000000000000100")
    assert Decimal(trip["entry_price_exact"]) == Decimal("10.000000000000000001")
    assert Decimal(ledger["fills"][0]["price_exact"]) == Decimal("10.000000000000000001")


def test_absent_exact_fee_stays_unknown_despite_numeric_zero_compatibility():
    ledger = build_fill_ledger(pair(market="US", fee=0, fee_exact=None))
    assert ledger["round_trips"][0]["fees_known"] is False
    assert any(i["code"] == "fees_unknown" for i in ledger["issues"])


def test_fee_remainder_is_conserved_for_three_partial_closes():
    buy, sell = pair(market="US", fee=0)
    ledger = build_fill_ledger([dict(buy, quantity_exact="3", fee_exact="0.00000001"),
        *[dict(sell, fill_id=f"s{i}", trade_time=f"1{i}:00:00", quantity_exact="1") for i in range(3)]])
    assert sum(Decimal(t["fees_exact"]) for t in ledger["round_trips"]) == Decimal("0.00000001")
    assert ledger["open_positions"] == []


def test_round_trip_id_is_stable_when_unrelated_history_is_inserted():
    base = pair(market="US", fee=0)
    extra = [dict(base[0], fill_id="other-buy", symbol="OTHER"),
             dict(base[1], fill_id="other-sell", symbol="OTHER")]
    direct = build_fill_ledger(base)
    with_history = build_fill_ledger(extra + base)
    assert direct["round_trips"][0]["round_trip_id"] == with_history["round_trips"][1]["round_trip_id"]


def test_offset_timestamps_are_ordered_by_instant_not_text():
    rows = [
        {"fill_id": "buy", "symbol": "TOY", "side": "BUY", "price": 10, "quantity": 1,
         "trade_date": "2026-09-01", "trade_time": "09:30:00+00:00", "market": "US", "fee": 0},
        {"fill_id": "sell", "symbol": "TOY", "side": "SELL", "price": 11, "quantity": 1,
         "trade_date": "2026-09-01", "trade_time": "10:00:00+02:00", "market": "US", "fee": 0},
    ]
    ledger = build_fill_ledger(rows)
    assert ledger["round_trips"] == []
    assert any(issue["code"] == "sell_without_position" for issue in ledger["issues"])


def test_long_and_short_positions_remain_separate_for_same_instrument():
    rows = [
        {"fill_id": "long", "symbol": "TOY", "side": "BUY", "position_effect": "OPEN", "price": 10,
         "quantity": 1, "trade_date": "2026-09-01", "trade_time": "10:00:00", "market": "US", "fee": 0},
        {"fill_id": "short", "symbol": "TOY", "side": "SELL", "position_effect": "OPEN", "price": 12,
         "quantity": 2, "trade_date": "2026-09-01", "trade_time": "10:01:00", "market": "US", "fee": 0},
    ]
    ledger = build_fill_ledger(rows, allow_shorts=True)
    assert {(position["position_side"], position["quantity"]) for position in ledger["open_positions"]} == {("LONG", 1), ("SHORT", -2)}
