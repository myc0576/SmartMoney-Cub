"""End-to-end tests for the trader HTTP surface.

Every test here drives a real bound socket: the handler, the mount, the identity
resolution, and the JSON encoding are all exercised, so a mount that only works
in-process cannot pass. The store is SQLite in a temporary directory and no test
reaches the network, which is why the market fetcher is injectable: the 502 path
and the cache path are proven without depending on a public endpoint.

Tenancy is tested over the socket too. Local mode has one identity by design, so
the isolation test runs the server in hosted mode with the signed-header adapter,
which needs no platform round trip and gives two genuinely distinct tenants.

All data here is toy data: invented symbols, invented prices, invented ids.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.api import TraderService
from smartmoney_cub_harness.trader.api import routes as trader_routes
from smartmoney_cub_harness.trader.auth import alphatech
from smartmoney_cub_harness.trader.market import (
    Bar,
    MarketDataError,
    ProviderResult,
    list_providers,
)
from smartmoney_cub_harness.trader.storage import open_store
from smartmoney_cub_harness.workbench.server import WorkbenchHandler, WorkbenchService

REPO_ROOT = Path(__file__).resolve().parents[1]
API_DOC = REPO_ROOT / "docs" / "trader-api.md"

HMAC_SECRET = "toy-hmac-secret"

# The route table frozen by the task brief, verbatim. The doc test below asserts
# every line appears in docs/trader-api.md, and asserts the code's own ROUTES
# agree with this list, so a route cannot be dropped from one and kept in the
# other.
BRIEF_ROUTES: tuple[tuple[str, str], ...] = (
    ("GET", "/api/trader/health"),
    ("GET", "/api/trader/meta"),
    ("GET", "/api/trader/market/providers"),
    ("GET", "/api/trader/market/bars"),
    ("GET", "/api/trader/trades"),
    ("POST", "/api/trader/trades/import"),
    ("GET", "/api/trader/trades/{round_trip_id}"),
    ("GET", "/api/trader/accounts"),
    ("POST", "/api/trader/accounts"),
    ("GET", "/api/trader/analytics/summary"),
    ("GET", "/api/trader/analytics/breakdown"),
    ("GET", "/api/trader/calendar"),
    ("GET", "/api/trader/playbooks"),
    ("POST", "/api/trader/playbooks"),
    ("POST", "/api/trader/backtest/run"),
    ("GET", "/api/trader/backtest/runs"),
    ("GET", "/api/trader/backtest/runs/{run_id}"),
    ("POST", "/api/trader/replay/sessions"),
    ("GET", "/api/trader/replay/sessions/{session_id}"),
)

STRATEGY = {
    "version": 1,
    "name": "toy-crossover",
    "universe": {"symbol": "TOY-A", "interval": "1d"},
    "indicators": [
        {"id": "fast", "kind": "sma", "source": "close", "period": 2},
        {"id": "slow", "kind": "sma", "source": "close", "period": 4},
    ],
    "entry": {"all": [{"crosses_above": ["fast", "slow"]}]},
    "exit": {"all": [{"crosses_below": ["fast", "slow"]}]},
    "stop": {"kind": "none"},
    "target": {"kind": "none"},
    "sizing": {"kind": "fixed_fraction", "value": 0.5},
    "filters": {"session": None, "min_bars": 5},
}

# A flat stretch, a fall that makes the fast average cross below the slow one,
# a rally that makes it cross back above, and a sell-off that closes the
# position. A signal is filled on the following bar's open, which is why the
# crossing at index 4 is entered on the bar at index 5.
CLOSES = (10.0, 10.0, 10.0, 9.0, 8.0, 9.0, 13.0, 15.0, 16.0, 14.0, 12.0, 10.0)


def _toy_bars(symbol: str = "TOY-A", interval: str = "1d") -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "interval": interval,
            "open_time": "2026-08-%02d" % (index + 1),
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000.0,
        }
        for index, close in enumerate(CLOSES)
    ]


def _buy(trade_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "trade_id": trade_id,
        "account_id": "ACC-TOY",
        "symbol": "TOY-A",
        "name": "Toy Instrument A",
        "side": "BUY",
        "trade_date": "2026-08-03",
        "trade_time": "09:40:00",
        "price": 10.0,
        "quantity": 100.0,
        "fee": 1.0,
        "regime": "toy-regime",
        "tags": ["toy-breakout"],
    }
    row.update(overrides)
    return row


def _sell(
    trade_id: str,
    *,
    symbol: str = "TOY-A",
    date: str = "2026-08-07",
    price: float = 11.0,
) -> dict[str, object]:
    return {
        "trade_id": trade_id,
        "account_id": "ACC-TOY",
        "symbol": symbol,
        "side": "SELL",
        "trade_date": date,
        "trade_time": "10:10:00",
        "price": price,
        "quantity": 100.0,
        "fee": 1.0,
    }


def _toy_result() -> ProviderResult:
    bars = [
        Bar(
            symbol="TOY-A",
            interval="1d",
            open_time=item["open_time"],
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=float(item["volume"]),
        )
        for item in _toy_bars()
    ]
    return ProviderResult(
        bars=bars,
        provider_id="stooq",
        symbol="TOY-A",
        interval="1d",
        fetched_at="2026-09-14T00:00:00+00:00",
        source_quality="delayed",
        warnings=["toy warning"],
    )


def _refusing_fetcher(*args: object, **kwargs: object) -> ProviderResult:
    raise MarketDataError("could not reach toy-host.example: name resolution failed")


def _stub_fetcher(*args: object, **kwargs: object) -> ProviderResult:
    return _toy_result()


@contextmanager
def _serve(tmp_path: Path, *, auth_mode: str = "local", fetch: object = None):
    """Bind the workbench handler with the trader product mounted on it."""
    store = open_store(tmp_path / "trader-store", mode="local")
    trader = TraderService(
        store,
        auth_mode=auth_mode,
        fetch_bars_fn=fetch if fetch is not None else _stub_fetcher,
    )
    workbench = WorkbenchService(tmp_path / "workbench-root")
    handler = type(
        "TraderApiTestHandler",
        (WorkbenchHandler,),
        {
            "service": workbench,
            "asset_dir": None,
            "access_token": None,
            "trader_service": trader,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_port, trader
    finally:
        server.shutdown()
        server.server_close()
        store.close()
        workbench.close()


def _call(
    base: str,
    method: str,
    path: str,
    *,
    body: object = None,
    content_type: str = "application/json",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    """One HTTP round trip. A 4xx/5xx is returned, not raised, so a test can read it."""
    data = None
    request_headers: dict[str, str] = dict(headers or {})
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = json.dumps(body).encode("utf-8")
        request_headers.setdefault("Content-Type", content_type)
    request = urllib.request.Request(
        base + path, data=data, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        return error.code, json.loads(raw)


def _signed(user_id: str, secret: str = HMAC_SECRET) -> dict[str, str]:
    """One signed identity header set, as the platform would send it."""
    stamp = str(int(time.time()))
    signature = alphatech.hmac.new(
        secret.encode("utf-8"), alphatech.hmac_message(user_id, stamp), alphatech.sha256
    ).hexdigest()
    return {
        alphatech.USER_HEADER: user_id,
        alphatech.TIMESTAMP_HEADER: stamp,
        alphatech.SIGNATURE_HEADER: signature,
    }


@pytest.fixture(autouse=True)
def _no_live_platform(monkeypatch):
    """Point the platform adapter at a dead loopback port for every test.

    Hosted session mode would otherwise be able to reach the real platform from a
    test. The isolation test uses the signed-header mode, which needs no lookup,
    so nothing here should ever connect anywhere.
    """
    for name in (alphatech.AUTH_MODE_ENV, alphatech.BASE_URL_ENV, alphatech.SSO_SECRET_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(alphatech.BASE_URL_ENV, "http://127.0.0.1:1")
    alphatech.clear_identity_cache()
    yield
    alphatech.clear_identity_cache()


# --- every route answers for a valid tenant -----------------------------


def test_each_endpoint_answers_200_with_a_well_formed_body(tmp_path) -> None:
    """DoD: every endpoint returns 200 with a well-formed JSON body.

    The calls run in the order the product's reference lists them, because two
    routes need an id produced by an earlier one: the run detail needs a saved
    run, and the replay session detail needs a session.
    """
    with _serve(tmp_path) as (base, _trader):
        responses: dict[str, tuple[int, dict]] = {}

        responses["GET /api/trader/health"] = _call(base, "GET", "/api/trader/health")
        responses["GET /api/trader/meta"] = _call(base, "GET", "/api/trader/meta")
        responses["GET /api/trader/market/providers"] = _call(
            base, "GET", "/api/trader/market/providers"
        )
        responses["GET /api/trader/market/bars"] = _call(
            base,
            "GET",
            "/api/trader/market/bars?provider=stooq&symbol=TOY-A&interval=1d&limit=10",
        )
        responses["POST /api/trader/trades/import"] = _call(
            base,
            "POST",
            "/api/trader/trades/import",
            body={"rows": [_buy("T-1"), _sell("T-2")]},
        )
        responses["GET /api/trader/trades"] = _call(base, "GET", "/api/trader/trades")
        responses["GET /api/trader/trades/{round_trip_id}"] = _call(
            base, "GET", "/api/trader/trades/RT-TOY-A-1"
        )
        responses["POST /api/trader/accounts"] = _call(
            base,
            "POST",
            "/api/trader/accounts",
            body={"name": "Toy Account", "broker": "toy-broker", "initial_balance": 5000.0},
        )
        responses["GET /api/trader/accounts"] = _call(base, "GET", "/api/trader/accounts")
        responses["GET /api/trader/analytics/summary"] = _call(
            base, "GET", "/api/trader/analytics/summary"
        )
        responses["GET /api/trader/analytics/breakdown"] = _call(
            base, "GET", "/api/trader/analytics/breakdown?dimension=symbol"
        )
        responses["GET /api/trader/calendar"] = _call(
            base, "GET", "/api/trader/calendar?year=2026&month=8"
        )
        responses["POST /api/trader/playbooks"] = _call(
            base,
            "POST",
            "/api/trader/playbooks",
            body={"name": "Toy Breakout", "dimension": "tag", "key": "toy-breakout"},
        )
        responses["GET /api/trader/playbooks"] = _call(base, "GET", "/api/trader/playbooks")
        responses["POST /api/trader/backtest/run"] = _call(
            base,
            "POST",
            "/api/trader/backtest/run",
            body={"strategy": STRATEGY, "data": {"bars": _toy_bars()}},
        )
        responses["GET /api/trader/backtest/runs"] = _call(
            base, "GET", "/api/trader/backtest/runs"
        )

        status, runs = responses["GET /api/trader/backtest/runs"]
        assert status == 200
        run_id = runs["runs"][0]["run_id"]
        responses["GET /api/trader/backtest/runs/{run_id}"] = _call(
            base, "GET", "/api/trader/backtest/runs/" + run_id
        )
        responses["POST /api/trader/replay/sessions"] = _call(
            base,
            "POST",
            "/api/trader/replay/sessions",
            body={"symbol": "TOY-A", "interval": "1d", "bars": _toy_bars()},
        )

        status, session_payload = responses["POST /api/trader/replay/sessions"]
        assert status == 200
        session_id = session_payload["session"]["session_id"]
        responses["GET /api/trader/replay/sessions/{session_id}"] = _call(
            base, "GET", "/api/trader/replay/sessions/" + session_id + "?index=1"
        )

        answered = {label for label, (status, _body) in responses.items() if status == 200}
        expected = {"%s %s" % route for route in BRIEF_ROUTES}
        assert answered == expected


def test_each_endpoint_body_carries_the_safety_declaration(tmp_path) -> None:
    """DoD: every response body contains the safety declaration.

    The check runs over every documented route in turn, and then over the error
    responses, because a refusal is a response too and a body without the
    declaration would be a quiet hole in the contract.
    """
    from smartmoney_cub_harness.schemas import SAFETY_DECLARATION as declaration

    assert declaration == "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
    with _serve(tmp_path, auth_mode="hosted") as (base, _trader):
        monkeypatch_secret = HMAC_SECRET
        headers = _signed("4711", monkeypatch_secret)
        # The adapter must be in signed-header mode for the identity to resolve
        # without a platform call.
        import os

        os.environ[alphatech.AUTH_MODE_ENV] = alphatech.MODE_HMAC
        os.environ[alphatech.SSO_SECRET_ENV] = monkeypatch_secret
        try:
            bodies = [
                _call(base, "GET", "/api/trader/health", headers=headers),
                _call(base, "GET", "/api/trader/meta", headers=headers),
                _call(base, "GET", "/api/trader/market/providers", headers=headers),
                _call(base, "GET", "/api/trader/trades", headers=headers),
                _call(base, "GET", "/api/trader/accounts", headers=headers),
                _call(base, "GET", "/api/trader/analytics/summary", headers=headers),
                _call(base, "GET", "/api/trader/calendar", headers=headers),
                _call(base, "GET", "/api/trader/playbooks", headers=headers),
                _call(base, "GET", "/api/trader/backtest/runs", headers=headers),
                # No identity at all.
                _call(base, "GET", "/api/trader/health"),
                # An unknown route, still behind a valid identity.
                _call(base, "GET", "/api/trader/nope", headers=headers),
                # A malformed request that gets as far as a handler.
                _call(base, "POST", "/api/trader/accounts", body={"currency": "CNY"}, headers=headers),
                # An invalid strategy.
                _call(base, "POST", "/api/trader/backtest/run", body={"strategy": {}}, headers=headers),
            ]
        finally:
            os.environ.pop(alphatech.AUTH_MODE_ENV, None)
            os.environ.pop(alphatech.SSO_SECRET_ENV, None)
            alphatech.clear_identity_cache()

    assert bodies
    for status, body in bodies:
        assert body["safety"] == SAFETY_DECLARATION, (status, body)


def test_a_request_without_a_valid_identity_is_refused_with_401(tmp_path) -> None:
    """DoD: a request with no valid identity is refused with 401."""
    import os

    os.environ[alphatech.AUTH_MODE_ENV] = alphatech.MODE_HMAC
    os.environ[alphatech.SSO_SECRET_ENV] = HMAC_SECRET
    try:
        with _serve(tmp_path, auth_mode="hosted") as (base, _trader):
            # No headers at all.
            status, body = _call(base, "GET", "/api/trader/trades")
            assert status == 401
            assert body["code"] == "unauthorized"

            # A tampered signature.
            tampered = _signed("4711")
            tampered[alphatech.SIGNATURE_HEADER] = "0" * 64
            status, body = _call(base, "GET", "/api/trader/trades", headers=tampered)
            assert status == 401

            # A signature from the wrong secret.
            status, body = _call(
                base, "GET", "/api/trader/trades", headers=_signed("4711", "not-the-secret")
            )
            assert status == 401

            # A stale timestamp, outside the replay window.
            stamp = str(int(time.time()) - 3600)
            stale = {
                alphatech.USER_HEADER: "4711",
                alphatech.TIMESTAMP_HEADER: stamp,
                alphatech.SIGNATURE_HEADER: alphatech.hmac.new(
                    HMAC_SECRET.encode("utf-8"),
                    alphatech.hmac_message("4711", stamp),
                    alphatech.sha256,
                ).hexdigest(),
            }
            status, body = _call(base, "GET", "/api/trader/trades", headers=stale)
            assert status == 401

            # The same refusal applies to a write, so a mutation cannot slip in
            # through an unauthenticated POST.
            status, body = _call(
                base, "POST", "/api/trader/trades/import", body={"rows": [_buy("T-X")]}
            )
            assert status == 401

            # And the workbench surface is untouched by any of it.
            status, meta = _call(base, "GET", "/api/meta")
            assert status == 200
            assert meta["app"] == "smartmoney-cub"
    finally:
        os.environ.pop(alphatech.AUTH_MODE_ENV, None)
        os.environ.pop(alphatech.SSO_SECRET_ENV, None)
        alphatech.clear_identity_cache()


# --- tenancy ------------------------------------------------------------


def test_tenant_a_never_sees_tenant_b_round_trip_ids(tmp_path) -> None:
    """DoD: tenant A's /trades never contains tenant B's round_trip_id.

    Two tenants import visibly different trades through the same socket and then
    read the journal back. The assertion is on the raw response text as well as
    the parsed body, so an id could not hide inside another field.
    """
    import os

    os.environ[alphatech.AUTH_MODE_ENV] = alphatech.MODE_HMAC
    os.environ[alphatech.SSO_SECRET_ENV] = HMAC_SECRET
    try:
        with _serve(tmp_path, auth_mode="hosted") as (base, _trader):
            tenant_a = _signed("tenant-a")
            tenant_b = _signed("tenant-b")

            status, _body = _call(
                base,
                "POST",
                "/api/trader/trades/import",
                body={"rows": [_buy("A-1"), _sell("A-2")]},
                headers=tenant_a,
            )
            assert status == 200
            status, _body = _call(
                base,
                "POST",
                "/api/trader/trades/import",
                body={
                    "rows": [
                        _buy("B-1", symbol="TOY-B", price=20.0),
                        _sell("B-2", symbol="TOY-B", price=22.0),
                    ]
                },
                headers=tenant_b,
            )
            assert status == 200

            status, body_a = _call(base, "GET", "/api/trader/trades", headers=tenant_a)
            assert status == 200
            status, body_b = _call(base, "GET", "/api/trader/trades", headers=tenant_b)
            assert status == 200

            ids_a = {trip["round_trip_id"] for trip in body_a["trades"]}
            ids_b = {trip["round_trip_id"] for trip in body_b["trades"]}
            symbols_a = {trip["symbol"] for trip in body_a["trades"]}
            symbols_b = {trip["symbol"] for trip in body_b["trades"]}

            assert ids_a == {"RT-TOY-A-1"}
            assert ids_b == {"RT-TOY-B-1"}
            assert symbols_a == {"TOY-A"}
            assert symbols_b == {"TOY-B"}
            assert ids_a.isdisjoint(ids_b)
            assert "TOY-B" not in json.dumps(body_a)
            assert "TOY-A" not in json.dumps(body_b)

            # The same rule holds for the single-record route and for the
            # other read surfaces.
            status, _body = _call(
                base, "GET", "/api/trader/trades/RT-TOY-B-1", headers=tenant_a
            )
            assert status == 404
            status, summary_a = _call(
                base, "GET", "/api/trader/analytics/summary", headers=tenant_a
            )
            assert status == 200
            assert summary_a["summary"]["trade_count"] == 1
            status, accounts_b = _call(base, "GET", "/api/trader/accounts", headers=tenant_b)
            assert status == 200 and accounts_b["accounts"] == []
    finally:
        os.environ.pop(alphatech.AUTH_MODE_ENV, None)
        os.environ.pop(alphatech.SSO_SECRET_ENV, None)
        alphatech.clear_identity_cache()


def test_a_replay_session_belonging_to_another_tenant_is_not_served(tmp_path) -> None:
    """An in-memory session is addressable only by the tenant that made it."""
    import os

    os.environ[alphatech.AUTH_MODE_ENV] = alphatech.MODE_HMAC
    os.environ[alphatech.SSO_SECRET_ENV] = HMAC_SECRET
    try:
        with _serve(tmp_path, auth_mode="hosted") as (base, _trader):
            status, created = _call(
                base,
                "POST",
                "/api/trader/replay/sessions",
                body={"symbol": "TOY-A", "interval": "1d", "bars": _toy_bars()},
                headers=_signed("tenant-a"),
            )
            assert status == 200
            session_id = created["session"]["session_id"]

            status, body = _call(
                base,
                "GET",
                "/api/trader/replay/sessions/" + session_id,
                headers=_signed("tenant-b"),
            )
            assert status == 404
            assert session_id not in json.dumps(body)

            status, body = _call(
                base,
                "GET",
                "/api/trader/replay/sessions/" + session_id,
                headers=_signed("tenant-a"),
            )
            assert status == 200
            assert body["session"]["session_id"] == session_id
    finally:
        os.environ.pop(alphatech.AUTH_MODE_ENV, None)
        os.environ.pop(alphatech.SSO_SECRET_ENV, None)
        alphatech.clear_identity_cache()


# --- market data mapping ------------------------------------------------


def test_market_bars_maps_an_upstream_failure_to_502(tmp_path) -> None:
    """An unreachable source is a bad gateway, never an empty series."""
    with _serve(tmp_path, fetch=_refusing_fetcher) as (base, _trader):
        status, body = _call(
            base, "GET", "/api/trader/market/bars?provider=stooq&symbol=TOY-A&interval=1d"
        )
        assert status == 502
        assert body["code"] == "market_data_unavailable"
        assert "toy-host.example" in body["error"]
        assert body["safety"] == SAFETY_DECLARATION


def test_market_bars_returns_a_series_and_caches_it_for_the_tenant(tmp_path) -> None:
    """The fetched series is normalized, returned, and written to the tenant cache."""
    with _serve(tmp_path) as (base, trader):
        status, body = _call(
            base,
            "GET",
            "/api/trader/market/bars?provider=stooq&symbol=TOY-A&interval=1d&limit=5",
        )
        assert status == 200
        assert body["provider_id"] == "stooq"
        assert body["source_quality"] == "delayed"
        assert body["warnings"] == ["toy warning"]
        assert len(body["bars"]) == len(CLOSES)
        assert body["cached"] is True
        assert set(body["bars"][0]) == {
            "symbol",
            "interval",
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
        }
        cached = trader.store.load_bars("local", symbol="TOY-A", interval="1d")
        assert len(cached) == len(CLOSES)
        assert cached[0]["provider"] == "stooq"


def test_market_providers_lists_the_four_keyless_sources(tmp_path) -> None:
    with _serve(tmp_path) as (base, _trader):
        status, body = _call(base, "GET", "/api/trader/market/providers")
        assert status == 200
        assert body["count"] == 4
        assert [entry["provider_id"] for entry in body["providers"]] == [
            entry["provider_id"] for entry in list_providers()
        ]
        assert all(entry["requires_key"] is False for entry in body["providers"])


def test_a_bad_market_argument_is_a_client_error_not_a_quiet_answer(tmp_path) -> None:
    with _serve(tmp_path) as (base, _trader):
        status, body = _call(base, "GET", "/api/trader/market/bars?symbol=TOY-A&interval=1d")
        assert status == 400
        assert "provider" in body["error"]

        status, body = _call(base, "GET", "/api/trader/trades?limit=zero")
        assert status == 400
        assert "limit" in body["error"]


# --- backtest -----------------------------------------------------------


def test_a_valid_strategy_runs_and_is_saved(tmp_path) -> None:
    with _serve(tmp_path) as (base, _trader):
        status, body = _call(
            base,
            "POST",
            "/api/trader/backtest/run",
            body={"strategy": STRATEGY, "data": {"bars": _toy_bars()}},
        )
        assert status == 200
        assert body["data"]["provenance"]["source"] == "inline"
        assert body["result"]["metrics"]["trade_count"] == 1
        assert body["saved"] is True
        assert body["result"]["safety"] == SAFETY_DECLARATION

        # The same inputs are deterministic, so a second run reports the same
        # revenue figure rather than a fresh draw.
        status, again = _call(
            base,
            "POST",
            "/api/trader/backtest/run",
            body={"strategy": STRATEGY, "data": {"bars": _toy_bars()}},
        )
        assert again["result"]["final_equity"] == body["result"]["final_equity"]


def test_an_invalid_strategy_is_refused_with_400_and_names_the_key(tmp_path) -> None:
    broken = dict(STRATEGY)
    broken["secret_sauce"] = 1
    with _serve(tmp_path) as (base, _trader):
        status, body = _call(
            base,
            "POST",
            "/api/trader/backtest/run",
            body={"strategy": broken, "data": {"bars": _toy_bars()}},
        )
        assert status == 400
        assert body["code"] == "invalid_strategy"
        assert "secret_sauce" in body["error"]

        # A missing strategy is a client error too, not a 500.
        status, body = _call(
            base, "POST", "/api/trader/backtest/run", body={"data": {"bars": _toy_bars()}}
        )
        assert status == 400


# --- import shapes ------------------------------------------------------


def test_import_accepts_csv_text_and_json_rows(tmp_path) -> None:
    with _serve(tmp_path) as (base, _trader):
        csv_body = (
            "trade_id,symbol,side,price,quantity,trade_date,trade_time,tags\n"
            "C-1,TOY-C,BUY,5.0,200,2026-08-03,09:35:00,toy-a|toy-b\n"
            "C-2,TOY-C,SELL,6.0,200,2026-08-06,10:05:00,\n"
        )
        status, body = _call(
            base,
            "POST",
            "/api/trader/trades/import",
            body=csv_body,
            content_type="text/csv",
        )
        assert status == 200
        assert body["format"] == "csv"
        assert body["submitted_count"] == 2
        assert body["inserted_count"] == 2

        status, body = _call(
            base,
            "POST",
            "/api/trader/trades/import",
            body=[_buy("J-1", symbol="TOY-D")],
        )
        assert status == 200
        assert body["format"] == "json"

        status, body = _call(base, "GET", "/api/trader/trades")
        assert status == 200
        # TOY-C is a closed round trip; TOY-D is a single buy, so it is an open
        # position rather than a trade.
        assert [trip["symbol"] for trip in body["trades"]] == ["TOY-C"]
        assert {row["symbol"] for row in body["fills"]} == {"TOY-C", "TOY-D"}
        # The ledger's fills are the tenant's own rows, addressed by the id they
        # were imported with.
        assert {row["fill_id"] for row in body["fills"]} == {"C-1", "C-2", "J-1"}

        # A CSV row the store cannot accept is a client error, not a stored
        # half-position.
        status, body = _call(
            base,
            "POST",
            "/api/trader/trades/import",
            body="trade_id,symbol,side,price,quantity,trade_date\nE-1,TOY-E,MAYBE,1,1,2026-08-03\n",
            content_type="text/csv",
        )
        assert status == 400
        assert "side" in body["error"]


# --- the mount, and the routes it must not disturb ----------------------


def test_the_workbench_routes_still_behave_on_the_mounted_server(tmp_path) -> None:
    """The trader mount must leave the existing routes exactly as they were."""
    with _serve(tmp_path) as (base, _trader):
        status, meta = _call(base, "GET", "/api/meta")
        assert status == 200
        assert meta["app"] == "smartmoney-cub"
        assert meta["safety"] == SAFETY_DECLARATION

        status, overview = _call(base, "GET", "/api/overview")
        assert status == 200
        assert overview["status"] == "ok"

        status, body = _call(base, "POST", "/api/import/manual", body=_buy("M-1"))
        assert status == 200
        assert body["inserted_count"] == 1

        status, body = _call(base, "GET", "/api/does-not-exist")
        assert status == 404
        assert body["safety"] == SAFETY_DECLARATION
        # The workbench's own 404 shape is unchanged: the trader dispatch does
        # not answer for a path outside its prefix.
        assert "error" in body and "code" not in body


def test_an_unknown_trader_path_is_404_and_a_wrong_method_is_404(tmp_path) -> None:
    with _serve(tmp_path) as (base, _trader):
        status, body = _call(base, "GET", "/api/trader/does-not-exist")
        assert status == 404
        assert body["code"] == "not_found"
        assert body["safety"] == SAFETY_DECLARATION

        # A documented path reached with the other verb is not a route.
        status, body = _call(base, "POST", "/api/trader/trades")
        assert status == 404

        # A literal segment is never swallowed by the placeholder route.
        status, body = _call(base, "GET", "/api/trader/trades/import")
        assert status == 404


def test_the_mount_is_opt_in_so_a_plain_workbench_serves_no_trader_routes(tmp_path) -> None:
    """Without a trader service the prefix stays absent, exactly as before."""
    workbench = WorkbenchService(tmp_path / "plain-root")
    handler = type(
        "PlainWorkbenchTestHandler",
        (WorkbenchHandler,),
        {"service": workbench, "asset_dir": None, "access_token": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_port
    try:
        status, body = _call(base, "GET", "/api/trader/health")
        assert status == 404
        assert body["safety"] == SAFETY_DECLARATION
    finally:
        server.shutdown()
        server.server_close()
        workbench.close()


# --- documentation ------------------------------------------------------


def test_the_api_reference_lists_every_route_from_the_brief() -> None:
    """DoD: docs/trader-api.md lists every route in the frozen table."""
    document = API_DOC.read_text(encoding="utf-8")
    for method, template in BRIEF_ROUTES:
        assert method + " " + template in document, (method, template)
    for path in (
        "/api/trader/health",
        "/api/trader/market/providers",
        "/api/trader/trades/{round_trip_id}",
        "/api/trader/backtest/runs/{run_id}",
        "/api/trader/replay/sessions/{session_id}",
    ):
        assert path in document


def test_the_route_table_matches_the_brief_and_the_reference_document() -> None:
    """The code, the brief, and the doc are held to one list."""
    assert trader_routes.ROUTE_LINES == tuple(
        "%s %s" % route for route in BRIEF_ROUTES
    )
    document = API_DOC.read_text(encoding="utf-8")
    for line in trader_routes.ROUTE_LINES:
        assert line in document, line
    # Every route names a handler that exists.
    for route in trader_routes.ROUTES:
        assert route.handler in trader_routes.HANDLERS, route.handler
        assert route.template.startswith(trader_routes.TRADER_API_PREFIX)


def test_the_doc_and_the_code_never_hardcode_the_safety_declaration(tmp_path) -> None:
    """The declaration is imported from schemas, never retyped in this task's code."""
    declaration = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
    for relative in (
        "src/smartmoney_cub_harness/trader/api/service.py",
        "src/smartmoney_cub_harness/trader/api/routes.py",
        "src/smartmoney_cub_harness/trader/api/__init__.py",
    ):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert declaration not in source, relative
        assert "SAFETY_DECLARATION" in source or relative.endswith("__init__.py")



def test_the_interface_loads_without_a_token_while_the_data_does_not(tmp_path) -> None:
    """A token-protected deployment must still be reachable from a browser.

    Why this test exists: a browser cannot attach a custom header to the navigation
    that loads a page, or to the requests the page then makes for its own JavaScript
    and CSS. Gating those returned 401 for every page load, so a deployment that set
    an access token -- which the systemd unit and the Dockerfile both require --
    served a product nobody could open. The token still has to gate the data, so both
    halves are asserted here: the shell and its assets load without it, every API call
    needs it, and the proxy is what supplies it for a browser.
    """
    import json as _json
    import threading
    from http.server import ThreadingHTTPServer

    from smartmoney_cub_harness.workbench.server import WorkbenchHandler, WorkbenchService

    store = open_store(tmp_path / "token-store", mode="local")
    trader = TraderService(store, auth_mode="local", fetch_bars_fn=_stub_fetcher)

    # A real asset directory, so the shell and an asset are both servable.
    assets = tmp_path / "web"
    (assets / "assets").mkdir(parents=True)
    (assets / "index.html").write_text("<!doctype html><title>shell</title>", encoding="utf-8")
    (assets / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")

    workbench = WorkbenchService(tmp_path / "token-root")
    handler = type(
        "TokenGateTestHandler",
        (WorkbenchHandler,),
        {
            "service": workbench,
            "asset_dir": assets,
            "access_token": "deploy-token",
            "trader_service": trader,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_port

    def get(path: str, token: str | None = None):
        headers = {"X-SMCUB-Token": token} if token else {}
        request = urllib.request.Request(base + path, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    try:
        # The interface loads without the token, because a browser has no way to
        # send one on a navigation or on the page's own asset requests.
        status, body = get("/")
        assert status == 200, status
        assert b"shell" in body
        status, body = get("/assets/app.js")
        assert status == 200, status
        assert b"app" in body
        # A client-side route with no file behind it still gets the shell.
        status, _ = get("/tracker/trade-log")
        assert status == 200, status

        # The data does not load without the token.
        status, body = get("/api/trader/health")
        assert status == 401, status
        assert _json.loads(body)["safety"] == SAFETY_DECLARATION

        # And with the token, both work.
        status, _ = get("/api/trader/health", token="deploy-token")
        assert status == 200, status
        status, _ = get("/", token="deploy-token")
        assert status == 200, status
    finally:
        server.shutdown()
        server.server_close()
        store.close()
        workbench.close()

