import pytest

from smartmoney_cub_harness.trader.storage import open_store, StoreError
from smartmoney_cub_harness.trader.storage.sqlite_store import SQLiteTenantStore
from smartmoney_cub_harness.trader.storage.postgres_store import PostgresTenantStore


def row(**changes):
    return {"symbol": "TOY", "account_id": "toy", "side": "BUY", "trade_date": "2026-01-01",
            "price": "123.123456789123456789", "quantity": "0.000000001234567891234", "fee": "0.00000000000000012", **changes}


def test_store_retains_exact_decimal_sources(tmp_path):
    store = open_store(tmp_path / "toy.db")
    store.migrate()
    store.create_user("toy")
    store.insert_trades("toy", [row()])
    stored = store.list_trades("toy")[0]
    assert stored["price_exact"] == row()["price"]
    assert stored["quantity_exact"] == row()["quantity"]
    assert stored["fee_exact"] == row()["fee"]
    store.close()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", True])
def test_both_engines_reject_nonfinite_prices(value):
    for engine in (SQLiteTenantStore, PostgresTenantStore):
        with pytest.raises(StoreError):
            engine._normalize_trade("toy", row(price=value))


def test_economic_import_identity_distinguishes_exact_precision_and_contract():
    for engine in (SQLiteTenantStore, PostgresTenantStore):
        a = engine._normalize_trade("toy", row(instrument_id="toy-1"))
        b = engine._normalize_trade("toy", row(instrument_id="toy-2"))
        c = engine._normalize_trade("toy", row(instrument_id="toy-1", price="123.123456789123456788"))
        assert len({a["trade_id"], b["trade_id"], c["trade_id"]}) == 3
