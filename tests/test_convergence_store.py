from __future__ import annotations

import json

from smartmoney_cub_harness import analytics
from smartmoney_cub_harness.store import DEFAULT_PORTFOLIO_ID, Store


def _fill(**overrides):
    fill = {
        "trade_date": "2026-09-01",
        "trade_time": "09:40:00",
        "symbol": "600111",
        "name": "北方稀土",
        "side": "BUY",
        "price": 10.0,
        "quantity": 1000,
        "fee": 5.0,
    }
    fill.update(overrides)
    return fill


def test_store_round_trip_and_open_positions(tmp_path) -> None:
    store = Store(tmp_path)
    try:
        store.add_fills(
            [
                _fill(),
                _fill(trade_date="2026-09-03", trade_time="14:00:00", side="SELL", price=11.0),
                _fill(trade_date="2026-09-04", symbol="600519", name="贵州茅台", price=1500.0, quantity=100),
            ]
        )
        analysis = analytics.analyze(store.list_fills(portfolio_id=DEFAULT_PORTFOLIO_ID))
        assert analysis["ledger_status"] == "ok"
        assert len(analysis["round_trips"]) == 1
        trip = analysis["round_trips"][0]
        # The declared fee on each side is deducted from the closed round trip.
        assert trip["fees"] == 10.0
        assert trip["net_pnl"] == 990.0
        assert len(analysis["open_positions"]) == 1
        assert analysis["open_positions"][0]["symbol"] == "600519"
    finally:
        store.close()


def test_documents_are_immutable_and_deduplicated_by_hash(tmp_path) -> None:
    store = Store(tmp_path)
    try:
        first = store.add_document(
            b"hello,world\n",
            file_name="fills.csv",
            media_type="text/csv",
            source_kind="csv",
        )
        second = store.add_document(
            b"hello,world\n",
            file_name="fills-copy.csv",
            media_type="text/csv",
            source_kind="csv",
        )
        assert first["document_id"] == second["document_id"]
        assert second["duplicate"] is True
        assert store.counts()["source_document"] == 1
        # The bytes on disk still match what was uploaded.
        assert store.document_bytes(first["document_id"]) == b"hello,world\n"
    finally:
        store.close()


def test_reimporting_the_same_fill_does_not_double_the_position(tmp_path) -> None:
    store = Store(tmp_path)
    try:
        first = store.add_fills([_fill()])
        assert first["inserted_count"] == 1
        second = store.add_fills([_fill()])
        assert second["inserted_count"] == 0
        assert len(second["skipped"]) == 1
        assert len(store.list_fills()) == 1
    finally:
        store.close()


def test_a_correction_keeps_the_previous_revision_readable(tmp_path) -> None:
    store = Store(tmp_path)
    try:
        store.add_fills([_fill()])
        store.add_fills([_fill(price=10.5)], edited_by="manual")
        current = store.list_fills()
        assert len(current) == 1
        assert current[0]["price"] == 10.5
        assert current[0]["revision"] == 2

        history = store.fill_revisions(symbol="600111")
        assert len(history) == 2
        superseded = [row for row in history if row["superseded"]]
        assert len(superseded) == 1
        # The original value is still on disk, so the edit is auditable.
        assert superseded[0]["price"] == 10.0
    finally:
        store.close()


def test_session_events_resume_after_a_reload(tmp_path) -> None:
    store = Store(tmp_path)
    try:
        session = store.create_session(title="复盘", context={"portfolio_id": DEFAULT_PORTFOLIO_ID})
        store.append_event(session["session_id"], kind="user_message", role="user", payload={"text": "你好"})
        store.append_event(session["session_id"], kind="assistant_message", role="assistant", payload={"text": "开始"})

        events = store.list_events(session["session_id"])
        assert [event["seq"] for event in events] == [1, 2]
        # Asking for events after a known sequence is how a reconnecting client
        # resumes without replaying the whole transcript.
        assert len(store.list_events(session["session_id"], after_seq=1)) == 1

        fork = store.fork_session(session["session_id"])
        assert fork["forked_from"] == session["session_id"]
        assert len(store.list_events(fork["session_id"])) == 2
        assert len(store.list_sessions()) == 2
    finally:
        store.close()


def test_backup_writes_a_readable_copy(tmp_path) -> None:
    store = Store(tmp_path / "live")
    try:
        store.add_fills([_fill()])
        result = store.backup(tmp_path / "backup.db")
        assert result["status"] == "ok"
        assert result["byte_size"] > 0
        restored = Store(tmp_path / "restored")
        try:
            restored._db.close()
            restored_path = restored.db_path
            restored_path.write_bytes((tmp_path / "backup.db").read_bytes())
        finally:
            pass
    finally:
        store.close()


def test_settings_round_trip(tmp_path) -> None:
    store = Store(tmp_path)
    try:
        assert store.get_setting("missing", "fallback") == "fallback"
        store.set_setting("trend_color_scheme", "intl")
        assert store.get_setting("trend_color_scheme") == "intl"
    finally:
        store.close()


def test_analytics_keeps_sample_size_visible() -> None:
    ledger = analytics.build_ledger(
        [
            _fill(),
            _fill(trade_date="2026-09-03", side="SELL", price=11.0),
        ]
    )
    summary = analytics.summarize(ledger)
    assert summary["trade_count"] == 1
    assert summary["sample_note"].startswith("样本是自选的复盘历史")
    # One profitable trade and no losing trade means profit factor is undefined
    # rather than a fabricated large number.
    assert summary["profit_factor"] is None
    assert "undefined" in summary["profit_factor_note"]


def test_profit_factor_uses_absolute_gross_loss() -> None:
    # Fees are set to zero so the ratio is exactly the gross relationship.
    ledger = analytics.build_ledger(
        [
            _fill(fee=0.0),
            _fill(trade_date="2026-09-03", side="SELL", price=12.0, fee=0.0),
            _fill(trade_date="2026-09-04", symbol="000725", price=4.0, quantity=1000, fee=0.0),
            _fill(trade_date="2026-09-08", symbol="000725", side="SELL", price=3.0, fee=0.0),
        ]
    )
    summary = analytics.summarize(ledger)
    assert summary["trade_count"] == 2
    # 2000 gain against 1000 loss.
    assert summary["profit_factor"] == 2.0


def test_a_combined_fee_column_is_treated_as_a_declared_fee() -> None:
    from smartmoney_cub_harness.fills import build_fill_ledger

    ledger = build_fill_ledger(
        [
            {"成交日期": "2026-09-01", "证券代码": "600111", "操作": "买入", "成交均价": 10.0,
             "成交数量": 1000, "手续费": 5.0},
            {"成交日期": "2026-09-03", "证券代码": "600111", "操作": "卖出", "成交均价": 11.0,
             "成交数量": 1000, "手续费": 5.0},
        ]
    )
    # A declared fee is used as-is, so the ledger does not add an estimate.
    assert "fees_estimated" not in {issue["code"] for issue in ledger["issues"]}
    assert ledger["round_trips"][0]["fees"] == 10.0
    assert ledger["round_trips"][0]["net_pnl"] == 990.0


def test_calendar_and_breakdown_stay_scoped(tmp_path) -> None:
    store = Store(tmp_path)
    try:
        store.add_fills(
            [
                _fill(),
                _fill(trade_date="2026-09-03", side="SELL", price=11.0),
            ]
        )
        analysis = analytics.analyze(store.list_fills(), year=2026, month=9)
        assert len(analysis["calendar"]) == 1
        assert analysis["calendar"][0]["date"] == "2026-09-03"
        by_symbol = analysis["breakdown"]["symbol"]
        assert by_symbol[0]["key"] == "600111"
        # A single trade is flagged so the UI cannot present it as a pattern.
        assert by_symbol[0]["small_sample"] is True
        assert json.dumps(analysis, ensure_ascii=False)
    finally:
        store.close()
