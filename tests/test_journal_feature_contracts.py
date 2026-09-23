"""Real HTTP regression coverage for previously incomplete journal features."""
from test_trader_api import _serve, _call, _toy_bars, _buy, _sell, STRATEGY
from smartmoney_cub_harness.trader.api import TraderService
from smartmoney_cub_harness.trader.auth import resolve_identity


def test_analytics_reads_beyond_one_page_without_losing_the_opening_fill(tmp_path):
    with _serve(tmp_path) as (_, service):
        ctx = resolve_identity({}, mode='local')
        service.import_trades(ctx, rows=[
            {**_buy('toy-buy'), 'quantity': 10001, 'currency': 'USD'},
            *[{**_sell('toy-sell-' + str(i)), 'quantity': 1, 'currency': 'USD'} for i in range(10001)],
        ])
        result = service.list_trades(ctx)
        assert result['count'] == 10001
        assert sum(t['quantity'] for t in result['trades']) == len(result['trades'])
        assert service.insight_patterns(ctx)['truncated'] is False


def test_replay_survives_service_restart_and_never_sends_future_bars(tmp_path):
    with _serve(tmp_path) as (base, service):
        status, result = _call(base, "POST", "/api/trader/replay/sessions", body={
            "symbol": "TOY-A", "interval": "1d", "bars": _toy_bars(), "mode": "training"})
        assert status == 200, result
        session = result["session"]
        assert len(session["bars"]) == 1
        session_id = session["session_id"]
        status, queued = _call(base, "POST", f"/api/trader/replay/sessions/{session_id}/actions",
                               body={"action": "simulate", "side": "BUY", "quantity": "0.5"})
        assert status == 200, queued
        assert queued["session"]["training"]["fills"] == []
        status, stepped = _call(base, "POST", f"/api/trader/replay/sessions/{session_id}/actions",
                                body={"action": "step"})
        assert status == 200
        assert len(stepped["session"]["training"]["fills"]) == 1
        assert service.store.list_trades("local") == []
        restarted = TraderService(service.store)
        loaded = restarted.replay_session(resolve_identity({}, mode="local"), session_id)
        assert loaded["session"]["cursor"] == 1
        assert loaded["ephemeral"] is False
        assert len(loaded["session"]["bars"]) == 2


def test_playbook_all_authored_fields_survive_reload(tmp_path):
    authored = {"name": "Toy breakout", "setup": "Toy setup", "entry_rules": ["Toy entry"],
                "exit_rules": ["Toy exit"], "risk_rules": ["Toy risk"], "tags": ["toy-tag"]}
    with _serve(tmp_path) as (base, _):
        status, saved = _call(base, "POST", "/api/trader/playbooks", body=authored)
        assert status == 200, saved
        status, loaded = _call(base, "GET", "/api/trader/playbooks")
        assert status == 200
        book = next(b for b in loaded["playbooks"] if b["playbook_id"] == saved["playbook"]["playbook_id"])
        for key, value in authored.items():
            assert book[key] == value


def test_backtest_saved_detail_preserves_trade_evidence(tmp_path):
    with _serve(tmp_path) as (base, _):
        status, ran = _call(base, "POST", "/api/trader/backtest/run", body={
            "strategy": STRATEGY, "bars": _toy_bars()})
        assert status == 200, ran
        status, saved = _call(base, "GET", "/api/trader/backtest/runs/" + ran["run_id"])
        assert status == 200
        assert saved["run"]["trades"] == ran["result"]["trades"]
        assert saved["run"]["provenance"]["source"] == "inline"


def test_backtest_cannot_silently_ignore_symbol_controls(tmp_path):
    with _serve(tmp_path) as (base, _):
        status, refused = _call(base, "POST", "/api/trader/backtest/run", body={
            "strategy": STRATEGY, "symbol": "OTHER-TOY", "bars": _toy_bars()})
        assert status == 400
        assert "symbol" in refused["error"]


def test_inline_future_availability_is_refused(tmp_path):
    bars = _toy_bars()
    bars[0].update(available_at="2026-08-02T00:00:00Z", decision_time="2026-08-01T00:00:00Z")
    with _serve(tmp_path) as (base, _):
        status, result = _call(base, "POST", "/api/trader/replay/sessions", body={
            "symbol": "TOY-A", "interval": "1d", "bars": bars})
        assert status == 400
        assert "available_at" in result["error"]


def test_cached_series_retains_source_provenance_without_inventing_historical_availability(tmp_path):
    with _serve(tmp_path) as (base, _):
        status, fetched = _call(base, "GET", "/api/trader/market/bars?provider=stooq&symbol=TOY-A&interval=1d")
        assert status == 200
        status, replay = _call(base, "POST", "/api/trader/replay/sessions", body={
            "symbol": "TOY-A", "interval": "1d", "cached": True})
        assert status == 200, replay
        assert replay["session"]["provider_id"] == "stooq"
        assert replay["session"]["fetched_at"] == fetched["fetched_at"]
        assert replay["session"]["historical_evidence"] == "unverified"


def test_pattern_decisions_persist_without_promoting_rules(tmp_path):
    with _serve(tmp_path) as (base, service):
        status, _ = _call(base, "POST", "/api/trader/trades/import", body={"rows": [_buy("toy-buy"), _sell("toy-sell")]})
        assert status == 200
        status, profile = _call(base, "GET", "/api/trader/insight/patterns")
        assert status == 200, profile
        candidate = profile["candidates"][0]
        status, confirmed = _call(base, "POST", "/api/trader/insight/patterns/decisions", body={
            "pattern_id": candidate["pattern_id"], "action": "confirm", "label": "My toy style"})
        assert status == 200, confirmed
        restarted = TraderService(service.store)
        loaded = restarted.insight_patterns(resolve_identity({}, mode="local"))
        item = next(c for c in loaded["candidates"] if c["pattern_id"] == candidate["pattern_id"])
        assert item["status"] == "confirmed"
        assert item["label"] == "My toy style"
        assert item["original_label"] == candidate["label"]
        assert service.store.list_documents("local", "champion") == []
        status, refused = _call(base, "POST", "/api/trader/insight/patterns/decisions", body={
            "pattern_id": "PAT-other-tenant", "action": "confirm"})
        assert status == 404


def test_report_date_filter_preserves_opening_cost_basis(tmp_path):
    with _serve(tmp_path) as (base, _):
        status, _ = _call(base, "POST", "/api/trader/trades/import", body={"rows": [
            _buy("before-window", trade_date="2026-07-20"), _sell("in-window", date="2026-08-07")]})
        assert status == 200
        status, summary = _call(base, "GET", "/api/trader/analytics/summary?from=2026-08-01&to=2026-08-31")
        assert status == 200
        assert summary["summary"]["trade_count"] == 1
        status, trades = _call(base, "GET", "/api/trader/trades?from=2026-08-01&to=2026-08-31")
        assert status == 200
        assert trades["count"] == 1
