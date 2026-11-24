from __future__ import annotations

from smartmoney_cub_harness.trader.api.service import TraderService
from smartmoney_cub_harness.trader.auth.identity import LOCAL_CONTEXT
from smartmoney_cub_harness.trader.storage import open_store


def _fill(trade_id: str, side: str, date: str, price: float, fee: float) -> dict[str, object]:
    return {
        "trade_id": trade_id,
        "account_id": "ACC-REPORT",
        "symbol": "TOY-REPORT",
        "name": "Toy report instrument",
        "side": side,
        "trade_date": date,
        "trade_time": "10:00:00",
        "price": price,
        "quantity": 1.0,
        "fee": fee,
        "currency": "USD",
    }


def test_report_metrics_are_server_derived_for_summary_and_calendar(tmp_path) -> None:
    store = open_store(tmp_path, mode="local")
    service = TraderService(store, resume_watch=False)
    try:
        service.import_trades(LOCAL_CONTEXT, rows=[
            _fill("R-1-B", "BUY", "2026-09-01", 10.0, 1.0),
            _fill("R-1-S", "SELL", "2026-09-03", 15.0, 1.0),
            _fill("R-2-B", "BUY", "2026-09-04", 20.0, 1.0),
            _fill("R-2-S", "SELL", "2026-09-05", 18.0, 1.0),
        ])

        summary = service.analytics_summary(LOCAL_CONTEXT)["summary"]
        assert summary["trade_count"] == 2
        assert summary["total_net_pnl"] == -1.0
        assert summary["expectancy"] == -0.5
        assert summary["fee_share"] == "80.0%"

        calendar = service.calendar(LOCAL_CONTEXT, year=2026, month=9)
        assert calendar["best_day"]["date"] == "2026-09-03"
        assert calendar["worst_day"]["date"] == "2026-09-05"
        assert calendar["profitable_day_count"] == 1
        assert calendar["loss_day_count"] == 1
    finally:
        service.close()
        store.close()


def test_report_metrics_preserve_empty_sample_semantics(tmp_path) -> None:
    store = open_store(tmp_path, mode="local")
    service = TraderService(store, resume_watch=False)
    try:
        summary = service.analytics_summary(LOCAL_CONTEXT)["summary"]
        calendar = service.calendar(LOCAL_CONTEXT, year=2026, month=9)
        assert summary["expectancy"] == 0.0
        assert summary["fee_share"] == "—"
        assert calendar["best_day"] is None
        assert calendar["worst_day"] is None
        assert calendar["profitable_day_count"] == 0
        assert calendar["loss_day_count"] == 0
    finally:
        service.close()
        store.close()
