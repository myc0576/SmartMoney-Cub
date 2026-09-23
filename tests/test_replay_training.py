"""Synthetic replay: persistence, no future payloads, isolated next-bar fills."""
from copy import deepcopy

import pytest

from smartmoney_cub_harness.trader.replay import create_record, public_view, apply_action


def bars():
    return [{"symbol": "TOY", "interval": "1d", "open_time": f"2026-08-0{i + 1}",
             "open": 10 + i, "high": 12 + i, "low": 9 + i, "close": 11 + i, "volume": 100}
            for i in range(4)]


def record(mode="training"):
    return create_record(symbol="TOY", interval="1d", bars=bars(), provenance={"source": "inline"},
                         mode=mode, initial_cash=1000, account_id=None, fills=[
                             {"trade_id": "toy-future", "symbol": "TOY", "trade_date": "2026-08-03",
                              "trade_time": "10:00:00", "side": "BUY", "price": 12, "quantity": 1}])


def test_public_payload_never_contains_future_bars_or_actual_executions():
    source = record("review")
    view = public_view(source)
    assert len(view["bars"]) == 1
    assert view["markers"] == []
    assert "toy-future" not in str(view)
    assert "2026-08-04" not in str(view)
    stepped = apply_action(source, {"action": "seek", "index": 2})
    assert public_view(stepped)["markers"][0]["trade_id"] == "toy-future"


def test_simulation_fills_on_next_bar_and_has_an_independent_ledger():
    source = record()
    queued = apply_action(source, {"action": "simulate", "side": "BUY", "quantity": "0.5"})
    assert queued["training"]["fills"] == []
    next_bar = apply_action(queued, {"action": "step"})
    fill = next_bar["training"]["fills"][0]
    assert fill["price"] == 11
    assert fill["quantity"] == 0.5
    assert next_bar["training"]["cash"] == 994.5
    assert next_bar["training"]["position"] == 0.5
    assert source["training"]["fills"] == []
    assert public_view(next_bar)["markers"] == []


def test_rewind_creates_new_branch_without_rewriting_original():
    source = apply_action(apply_action(record(), {"action": "simulate", "side": "BUY", "quantity": 1}), {"action": "step"})
    original = deepcopy(source)
    rewound = apply_action(source, {"action": "rewind", "index": 0})
    assert source == original
    assert rewound["session_id"] != source["session_id"]
    assert rewound["parent_session_id"] == source["session_id"]
    assert rewound["training"]["fills"] == []
    assert rewound["training"]["orders"] == []
    assert rewound["training"]["cash"] == 1000


@pytest.mark.parametrize("quantity", [0, -1, "NaN", "Infinity", True])
def test_invalid_quantity_fails_closed(quantity):
    with pytest.raises(ValueError):
        apply_action(record(), {"action": "simulate", "side": "BUY", "quantity": quantity})


def test_review_does_not_accept_simulated_orders():
    with pytest.raises(ValueError, match="training"):
        apply_action(record("review"), {"action": "simulate", "side": "BUY", "quantity": 1})


def test_next_bar_unavailable_does_not_queue_unfillable_request():
    source = apply_action(record(), {"action": "seek", "index": 3})
    with pytest.raises(ValueError, match="end"):
        apply_action(source, {"action": "simulate", "side": "BUY", "quantity": 1})


def test_bar_validation_rejects_duplicate_or_invalid_values():
    invalid = bars()
    invalid[1]["open_time"] = invalid[0]["open_time"]
    with pytest.raises(ValueError):
        create_record(symbol="TOY", interval="1d", bars=invalid, provenance={}, mode="review",
                      initial_cash=1000, account_id=None, fills=[])
