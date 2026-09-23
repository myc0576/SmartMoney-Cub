"""Contract tests for the market data provider layer.

The tests never touch the network. Each provider is exercised against a
recorded response body with the HTTP layer stubbed, so the assertions pin the
parsing contract rather than the mood of a public endpoint. One live smoke test
runs only when SMARTMONEY_LIVE_MARKET=1 is set.

Fixture provenance:

* Tencent daily, Tencent Hong Kong, and Binance klines are verbatim captures
  taken 2026-09-13 with the documented URLs.
* Eastmoney daily is the capture recorded in the task brief. That recording
  carried one kline followed by an ellipsis, so the primary fixture keeps that
  one kline byte for byte and adds the neighbouring sessions in the same
  7-column shape; those extra values are the same-symbol rows from the Tencent
  capture, which reproduces Eastmoney's 2026-09-09 row digit for digit
  (38.90, 38.90, 39.15, 38.68, 257917). The older derived rows stop at the
  volume column because the turnover figure for those sessions was not
  recorded; the parser ignores that column anyway.
* Stooq CSV is a hand-written file in the documented header format, and the
  HTML body is a verbatim capture of what the free endpoint returns when it
  serves its browser check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest

from smartmoney_cub_harness.trader.market import (
    PROVIDERS,
    Bar,
    MarketDataError,
    MarketDataProvider,
    ProviderResult,
    fetch_bars,
    get_provider,
    list_providers,
)
from smartmoney_cub_harness.trader.market import base
from smartmoney_cub_harness.trader.market import binance, eastmoney, stooq, tencent

REPO_ROOT = Path(__file__).resolve().parents[1]

PROVIDER_IDS = ("eastmoney", "tencent", "stooq", "binance")

EASTMONEY_DAILY_KLINE = "2026-09-09,38.90,38.90,39.15,38.68,257917,1002239676.00"

EASTMONEY_DAILY = json.dumps(
    {
        "data": {
            "code": "600111",
            "market": 1,
            "name": "北方稀土",
            "klines": [
                "2026-09-07,38.51,38.80,38.90,38.41,225499",
                "2026-09-08,38.80,39.04,39.23,38.70,278735",
                EASTMONEY_DAILY_KLINE,
                "2026-09-10,38.66,38.18,38.66,38.10,262646",
                "2026-09-11,37.89,37.48,37.90,36.93,368848",
            ],
        }
    },
    ensure_ascii=False,
)

TENCENT_DAILY = json.dumps(
    {
        "data": {
            "sh600111": {
                "qfqday": [
                    ["2026-09-07", "38.510", "38.800", "38.900", "38.410", "225499.000"],
                    ["2026-09-08", "38.800", "39.040", "39.230", "38.700", "278735.000"],
                    ["2026-09-09", "38.900", "38.900", "39.150", "38.680", "257917.000"],
                    ["2026-09-10", "38.660", "38.180", "38.660", "38.100", "262646.000"],
                    ["2026-09-11", "37.890", "37.480", "37.900", "36.930", "368848.000"],
                ],
                "version": "18",
            }
        }
    }
)

# Hong Kong and US symbols come back under the unadjusted key, and the Hong
# Kong rows carry a seventh element that is corporate-action commentary.
TENCENT_HONG_KONG = json.dumps(
    {
        "data": {
            "hk00700": {
                "day": [
                    [
                        "2026-09-09",
                        "436.200",
                        "434.000",
                        "438.400",
                        "432.800",
                        "17643957.000",
                        {"cqr": "2026-09-09", "HGcontent": "回购23.10万股，均价434.768港元"},
                    ],
                    [
                        "2026-09-10",
                        "430.000",
                        "425.600",
                        "430.800",
                        "425.000",
                        "22333165.000",
                        {"cqr": "2026-09-10", "HGcontent": ""},
                    ],
                ],
                "version": "16",
            }
        }
    },
    ensure_ascii=False,
)

STOOQ_CSV = "\n".join(
    [
        "Date,Open,High,Low,Close,Volume",
        "2026-09-08,238.9,240.1,237.4,239.5,41000000",
        "2026-09-09,239.6,241.2,238.8,240.4,38200000",
        "2026-09-10,240.5,242.0,239.1,241.8,45100000",
        "2026-09-11,241.7,243.3,240.2,242.9,39800000",
    ]
)

# Stooq pads a series with text rows the way a holiday or a halted session
# appears; those rows are dropped and counted rather than parsed into bars.
STOOQ_CSV_WITH_TEXT_ROW = STOOQ_CSV + "\nNo data\n2026-09-12,242.8,244.0,241.9,243.6,37100000"

STOOQ_BROWSER_CHECK = (
    '<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="robots" '
    'content="noindex,nofollow"></head><body><noscript>This site requires JavaScript '
    "to verify your browser. Please enable JavaScript and reload.</noscript></body></html>"
)

BINANCE_KLINES = json.dumps(
    [
        [
            1788912000000,
            "78455.80000000",
            "79760.00000000",
            "77770.00000000",
            "78306.43000000",
            "14129.92027000",
            1788998399999,
            "1114730666.15220270",
            3338369,
            "6620.08219000",
            "522307227.44916110",
            "0",
        ],
        [
            1788998400000,
            "78306.43000000",
            "78564.39000000",
            "76464.00000000",
            "76568.72000000",
            "15320.36904000",
            1789084799999,
            "1188117943.77201960",
            3080707,
            "6426.97352000",
            "498398012.04048190",
            "0",
        ],
        [
            1789084800000,
            "76568.73000000",
            "79890.00000000",
            "76046.58000000",
            "77225.70000000",
            "19713.27729000",
            1789171199999,
            "1528809492.09930950",
            3614263,
            "9852.15345000",
            "764153169.81810270",
            "0",
        ],
    ]
)

PAYLOADS = {
    "eastmoney": EASTMONEY_DAILY,
    "tencent": TENCENT_DAILY,
    "stooq": STOOQ_CSV,
    "binance": BINANCE_KLINES,
}

SYMBOLS = {
    "eastmoney": "600111",
    "tencent": "sh600111",
    "stooq": "aapl.us",
    "binance": "BTCUSDT",
}


class _StubResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_StubResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _stub(monkeypatch: pytest.MonkeyPatch, body: str, seen: list | None = None) -> None:
    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None):
        if seen is not None:
            seen.append(request)
        return _StubResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def _fetch(monkeypatch: pytest.MonkeyPatch, provider_id: str, body: str, **kwargs) -> ProviderResult:
    _stub(monkeypatch, body)
    return fetch_bars(provider_id, SYMBOLS[provider_id], "1d", **kwargs)


def test_eastmoney_reads_the_recorded_payload_with_the_documented_field_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The kline order is date, open, close, high, low: close precedes high."""
    _stub(monkeypatch, EASTMONEY_DAILY)

    result = fetch_bars("eastmoney", "600111", "1d")

    assert isinstance(result, ProviderResult)
    assert result.provider_id == "eastmoney"
    assert result.symbol == "600111"
    assert result.interval == "1d"
    assert result.source_quality == "aggregator"

    recorded = result.bars[2]
    assert recorded.open_time == "2026-09-09"
    assert recorded.open == 38.90
    assert recorded.close == 38.90
    assert recorded.high == 39.15
    assert recorded.low == 38.68
    assert recorded.volume == 257917
    # The turnaround column is not a Bar field.
    assert not hasattr(recorded, "amount")

    # A misread order would put the close where the high is on the 2026-09-11 row.
    last = result.bars[-1]
    assert last.open_time == "2026-09-11"
    assert (last.open, last.close, last.high, last.low) == (37.89, 37.48, 37.90, 36.93)
    assert [bar.open_time for bar in result.bars] == sorted(bar.open_time for bar in result.bars)


@pytest.mark.parametrize("provider_id", PROVIDER_IDS)
def test_every_provider_normalizes_to_the_same_bar_shape(
    monkeypatch: pytest.MonkeyPatch, provider_id: str
) -> None:
    result = _fetch(monkeypatch, provider_id, PAYLOADS[provider_id])

    assert result.bars, provider_id + " returned no bars"
    fields = set(Bar.__dataclass_fields__)
    for bar in result.bars:
        assert isinstance(bar, Bar)
        assert set(bar.to_dict()) == fields
        assert isinstance(bar.open_time, str) and bar.open_time
        for name in ("open", "high", "low", "close", "volume"):
            assert isinstance(getattr(bar, name), float)
        # The bar carries the request identity, not the source's own symbol text.
        assert bar.symbol == SYMBOLS[provider_id]
        assert bar.interval == "1d"
    assert [bar.open_time for bar in result.bars] == sorted(bar.open_time for bar in result.bars)

    assert result.provider_id == provider_id
    assert result.source_quality in ("exchange", "aggregator", "delayed")
    assert result.warnings == []
    assert datetime.fromisoformat(result.fetched_at).utcoffset() is not None
    assert result.fetched_at.endswith("+00:00")
    assert set(result.to_dict()) == {
        "bars",
        "provider_id",
        "symbol",
        "interval",
        "fetched_at",
        "source_quality",
        "warnings",
        "available_at",
        "decision_time",
        "historical_evidence",
    }
    assert result.available_at is None
    assert result.historical_evidence == "unverified"


@pytest.mark.parametrize(
    ("provider_id", "body"),
    [
        ("eastmoney", json.dumps({"data": None})),
        ("eastmoney", json.dumps({"data": {"code": "600111", "klines": []}})),
        ("eastmoney", "<html>nope</html>"),
        ("tencent", json.dumps({"code": 1, "msg": "bad params", "data": {"sh600111": {"version": "16"}}})),
        ("tencent", json.dumps({"data": {"sh600111": {"qfqday": []}}})),
        ("tencent", "not json at all"),
        ("stooq", ""),
        ("stooq", STOOQ_BROWSER_CHECK),
        ("stooq", "Date,Open\n2026-09-11,1,2"),
        ("stooq", "Date,Open,High,Low,Close,Volume\nNo data"),
        ("stooq", "no header here at all"),
        ("binance", "[]"),
        ("binance", json.dumps({"code": -1121, "msg": "Invalid symbol."})),
    ],
)
def test_a_malformed_or_empty_payload_raises_and_never_returns_an_empty_series(
    monkeypatch: pytest.MonkeyPatch, provider_id: str, body: str
) -> None:
    _stub(monkeypatch, body)

    with pytest.raises(MarketDataError) as error:
        fetch_bars(provider_id, SYMBOLS[provider_id], "1d")

    assert str(error.value).strip()


def test_the_catalog_describes_four_keyless_sources_with_the_frozen_keys() -> None:
    catalog = list_providers()

    assert len(catalog) == 4
    assert [entry["provider_id"] for entry in catalog] == list(PROVIDER_IDS)
    for entry in catalog:
        assert set(entry) == {
            "provider_id",
            "label",
            "markets",
            "requires_key",
            "source_quality",
            "description",
            # The two keys that were added when a verified failure needed to be
            # stated rather than hidden: a source that cannot answer says so.
            "availability",
            "availability_reason",
        }
        assert entry["requires_key"] is False
        assert entry["label"] and entry["description"]
        assert entry["markets"]
        # Every source declares an availability, and the ones that are not
        # available carry a reason. A source marked unavailable without a reason
        # would be a dead option the reader cannot act on.
        assert entry["availability"] in {"available", "unavailable", "restricted"}
        if entry["availability"] != "available":
            assert entry["availability_reason"]
    # The two sources verified unreachable from this network keep their place in
    # the catalogue: the failure may be network-specific, and a silently missing
    # option is worse than one that explains itself.
    marked = {entry["provider_id"]: entry["availability"] for entry in catalog}
    assert marked["stooq"] == "unavailable"
    assert marked["binance"] == "restricted"
    assert marked["eastmoney"] == "available"
    assert marked["tencent"] == "available"
    quality = {entry["provider_id"]: entry["source_quality"] for entry in catalog}
    assert quality == {
        "binance": "exchange",
        "eastmoney": "aggregator",
        "tencent": "aggregator",
        "stooq": "delayed",
    }
    assert PROVIDERS == tuple(catalog)


def test_an_unknown_provider_or_argument_is_refused_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list = []
    _stub(monkeypatch, EASTMONEY_DAILY, seen)

    with pytest.raises(MarketDataError) as unknown:
        fetch_bars("nasdaq", "600111", "1d")
    assert "nasdaq" in str(unknown.value)

    with pytest.raises(MarketDataError) as interval:
        fetch_bars("eastmoney", "600111", "3h")
    assert "3h" in str(interval.value)

    with pytest.raises(MarketDataError):
        fetch_bars("eastmoney", "600111", "1d", limit=0)
    with pytest.raises(MarketDataError):
        fetch_bars("eastmoney", "600111", "1d", start="last tuesday")
    with pytest.raises(MarketDataError):
        fetch_bars("eastmoney", "", "1d")

    # The provider refuses minute bars upstream of the request, and stooq
    # serves daily only.
    with pytest.raises(MarketDataError) as minutes:
        fetch_bars("tencent", "sh600111", "60m")
    assert "eastmoney" in str(minutes.value)
    with pytest.raises(MarketDataError):
        fetch_bars("stooq", "aapl.us", "1w")

    assert seen == []


@pytest.mark.parametrize("provider_id", PROVIDER_IDS)
def test_every_request_carries_a_real_user_agent(monkeypatch: pytest.MonkeyPatch, provider_id: str) -> None:
    seen: list = []
    _stub(monkeypatch, PAYLOADS[provider_id], seen)

    fetch_bars(provider_id, SYMBOLS[provider_id], "1d")

    assert len(seen) == 1
    agent = seen[0].get_header("User-agent")
    assert agent and agent == base.USER_AGENT
    assert "smartmoney" in agent
    assert seen[0].get_method() == "GET"


def test_a_range_and_a_limit_are_applied_to_the_served_page(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, EASTMONEY_DAILY)
    windowed = fetch_bars("eastmoney", "600111", "1d", start="2026-09-08", end="2026-09-10")
    assert [bar.open_time for bar in windowed.bars] == [
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
    ]

    _stub(monkeypatch, EASTMONEY_DAILY)
    trimmed = fetch_bars("eastmoney", "600111", "1d", limit=2)
    assert [bar.open_time for bar in trimmed.bars] == ["2026-09-10", "2026-09-11"]
    assert any("trimmed" in note for note in trimmed.warnings)

    _stub(monkeypatch, EASTMONEY_DAILY)
    outside = fetch_bars("eastmoney", "600111", "1d", start="2027-01-01")
    assert outside.bars == []
    assert any("no bars between" in note for note in outside.warnings)


def test_a_full_page_whose_first_bar_is_after_the_start_is_reported_as_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A short page is not the same as a complete one, and says so."""
    _stub(monkeypatch, EASTMONEY_DAILY)

    result = fetch_bars("eastmoney", "600111", "1d", start="2026-01-01", limit=3)

    assert result.bars[0].open_time == "2026-09-09"
    assert any("truncated" in note for note in result.warnings)


def test_a_tencent_page_that_hits_its_own_ceiling_warns_instead_of_shortening_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, TENCENT_DAILY)
    result = fetch_bars("tencent", "sh600111", "1d", limit=800)
    assert len(result.bars) == 5
    assert any("at most 640" in note for note in result.warnings)


def test_tencent_serves_hong_kong_from_the_unadjusted_key_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, TENCENT_HONG_KONG)

    result = fetch_bars("tencent", "hk00700", "1d")

    assert [bar.open_time for bar in result.bars] == ["2026-09-09", "2026-09-10"]
    assert result.bars[0].close == 434.0 and result.bars[0].volume == 17643957
    assert any("unadjusted" in note for note in result.warnings)


def test_stooq_drops_a_text_row_and_reports_how_many_it_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, STOOQ_CSV_WITH_TEXT_ROW)

    result = fetch_bars("stooq", "aapl.us", "1d")

    assert [bar.open_time for bar in result.bars] == [
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
        "2026-09-11",
        "2026-09-12",
    ]
    assert result.bars[0].high == 240.1 and result.bars[0].low == 237.4
    assert any("1 CSV row(s)" in note for note in result.warnings)


def test_binance_stamps_utc_windows_and_keeps_intraday_times(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, BINANCE_KLINES)
    daily = fetch_bars("binance", "BTCUSDT", "1d")
    # The first kline's open time is 1788912000000, which is 2026-09-09T00:00:00Z.
    assert daily.bars[0].open_time == "2026-09-09"
    assert daily.bars[0].open == 78455.8
    assert daily.bars[0].high == 79760.0
    assert daily.bars[0].low == 77770.0
    assert daily.bars[0].close == 78306.43
    assert daily.bars[1].open_time == "2026-09-10"
    assert daily.bars[1].high == 78564.39
    assert daily.bars[1].low == 76464.0
    assert daily.bars[1].close == 76568.72
    assert daily.bars[-1].open_time == "2026-09-11"

    _stub(monkeypatch, BINANCE_KLINES)
    intraday = fetch_bars("binance", "BTC-USDT", "5m")
    assert intraday.interval == "5m"
    # An intraday series keeps the clock even when the bar lands on midnight.
    assert intraday.bars[0].open_time == "2026-09-09T00:00:00"
    assert intraday.bars[1].open_time == "2026-09-10T00:00:00"
    assert intraday.bars[0].open_time != daily.bars[0].open_time


def test_binance_reports_an_exchange_refusal_by_its_message(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, json.dumps({"code": -1121, "msg": "Invalid symbol."}))
    with pytest.raises(MarketDataError) as error:
        fetch_bars("binance", "NOTAPAIR", "1d")
    assert "Invalid symbol." in str(error.value)


def test_a_bumped_page_size_is_reported_as_a_truncated_page(monkeypatch: pytest.MonkeyPatch) -> None:
    body = json.dumps(
        [
            [1788912000000 + index * 60000, "1", "2", "0.5", "1.5", "10", 1788912059999]
            for index in range(1000)
        ]
    )
    _stub(monkeypatch, body)
    result = fetch_bars("binance", "BTCUSDT", "1m", limit=1000)
    assert len(result.bars) == 1000
    assert any("full 1000-bar page" in note for note in result.warnings)


def test_range_bounds_reach_each_upstream_in_its_own_notation() -> None:
    """The window the caller describes has to survive the trip upstream."""
    eastmoney_url = eastmoney.build_url(
        "1.600111", interval="1d", start="2026-09-01", end="2026-09-11", limit=30
    )
    assert "beg=20260901" in eastmoney_url and "end=20260911" in eastmoney_url
    assert "klt=101" in eastmoney_url and "fqt=1" in eastmoney_url
    # No bound means "everything up to now", which Eastmoney spells 20500101.
    assert "end=20500101" in eastmoney.build_url(
        "1.600111", interval="1d", start=None, end=None, limit=30
    )

    tencent_url = tencent.build_url(
        "sh600111", interval="1d", start="2026-09-01", end="2026-09-11", limit=30
    )
    assert "param=sh600111%2Cday%2C2026-09-01%2C2026-09-11%2C30%2Cqfq" in tencent_url

    binance_url = binance.build_url(
        "BTCUSDT", interval="1d", start="2026-09-01", end="2026-09-11", limit=30
    )
    assert "startTime=1788220800000" in binance_url
    # An upper bound is inclusive of the whole named day: 2026-09-11 ends at
    # 23:59:59.999 UTC, which is the last millisecond of 1789084800000's day.
    assert "endTime=1789171199999" in binance_url
    assert "interval=1d" in binance_url

    assert stooq.build_url("aapl.us").endswith("?s=aapl.us&i=d")


def test_symbol_translation_matches_each_source_convention() -> None:
    assert eastmoney.secid_for("600111") == "1.600111"
    assert eastmoney.secid_for("sh600111") == "1.600111"
    assert eastmoney.secid_for("000001") == "0.000001"
    assert eastmoney.secid_for("600111.SH") == "1.600111"
    assert eastmoney.klt_for("1d") == "101"
    assert eastmoney.klt_for("60m") == "60"

    assert tencent.symbol_code("sh600111") == "sh600111"
    assert tencent.symbol_code("600111") == "sh600111"
    assert tencent.symbol_code("000001") == "sz000001"
    assert tencent.symbol_code("hk00700") == "hk00700"
    assert tencent.symbol_code("AAPL") == "usAAPL"
    assert tencent.series_key("1d") == "qfqday"
    assert tencent.series_key("1M") == "qfqmonth"

    assert stooq.stooq_symbol("AAPL") == "aapl.us"
    assert stooq.stooq_symbol("sap.de") == "sap.de"
    assert binance.binance_symbol("btc-usdt") == "BTCUSDT"
    assert binance.binance_symbol("eth/usdt") == "ETHUSDT"


def test_every_provider_object_satisfies_the_shared_protocol() -> None:
    """The protocol is the contract later tasks code against, not just a docstring."""
    for provider_id in PROVIDER_IDS:
        provider = get_provider(provider_id)
        assert isinstance(provider, MarketDataProvider)
        assert provider.provider_id == provider_id
        assert provider.requires_key is False
        assert provider.source_quality in base.SOURCE_QUALITIES
        assert isinstance(provider.markets, tuple) and provider.markets
        assert provider.label and provider.description
    with pytest.raises(MarketDataError):
        get_provider("bloomberg")


def test_a_bar_and_a_result_are_immutable_records() -> None:
    bar = Bar(
        symbol="600111",
        interval="1d",
        open_time="2026-09-11",
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
    )
    with pytest.raises(Exception):
        bar.close = 9.0  # type: ignore[misc]
    result = ProviderResult(
        bars=[bar],
        provider_id="eastmoney",
        symbol="600111",
        interval="1d",
        fetched_at="2026-09-13T00:00:00+00:00",
        source_quality="aggregator",
        warnings=[],
    )
    assert result.to_dict()["bars"][0]["close"] == 1.5
    # The dict is a snapshot: mutating it cannot reach back into the result.
    result.to_dict()["warnings"].append("mutated")
    assert result.warnings == []


def test_an_unfinished_session_is_flagged_rather_than_silently_included(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The last bar of a live session is a partial bar and has to say so."""
    body = json.dumps(
        {
            "data": {
                "code": "600111",
                "klines": [
                    "2026-09-10,38.66,38.18,38.66,38.10,262646",
                    eastmoney.session_date() + ",37.89,37.48,37.90,36.93,368848",
                ],
            }
        }
    )
    _stub(monkeypatch, body)

    result = fetch_bars("eastmoney", "600111", "1d")

    assert len(result.bars) == 2
    assert any("unfinished session" in note for note in result.warnings)
    # A weekly series has no live-session concept, so it is not flagged.
    _stub(monkeypatch, body)
    weekly = fetch_bars("eastmoney", "600111", "1w")
    assert weekly.warnings == []


def test_a_non_json_body_names_the_provider_that_produced_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, "<html><body>gateway timeout</body></html>")
    with pytest.raises(MarketDataError) as error:
        fetch_bars("tencent", "sh600111", "1d")
    assert "tencent" in str(error.value)
    assert "JSON" in str(error.value)


def test_no_provider_module_is_imported_by_the_catalog() -> None:
    """The catalogue must not be the reason a provider module loads."""
    script = (
        "import sys, smartmoney_cub_harness.trader.market as market;"
        "print(len(market.list_providers()));"
        "print([name for name in ('pandas', 'numpy', 'requests') if name in sys.modules]);"
        "print([name for name in sys.modules if name.startswith('smartmoney_cub_harness.trader.market.')"
        " and not name.endswith(('__init__', '.base'))])"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.strip().splitlines()
    assert lines[0] == "4"
    assert lines[1] == "[]"
    assert lines[2] == "[]"


def test_the_documented_catalogue_call_prints_four() -> None:
    script = (
        "from smartmoney_cub_harness.trader.market import list_providers;"
        "print(len(list_providers()))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "4"


LIVE_SYMBOLS = {
    "eastmoney": "600111",
    "tencent": "sh600111",
    "stooq": "aapl.us",
    "binance": "BTCUSDT",
}


@pytest.mark.skipif(
    os.environ.get("SMARTMONEY_LIVE_MARKET") != "1",
    reason="set SMARTMONEY_LIVE_MARKET=1 to exercise the live endpoints",
)
@pytest.mark.parametrize("provider_id", PROVIDER_IDS)
def test_live_smoke(provider_id: str) -> None:
    result = fetch_bars(provider_id, LIVE_SYMBOLS[provider_id], "1d", limit=5)
    assert result.bars
    assert all(bar.high >= bar.low for bar in result.bars)
