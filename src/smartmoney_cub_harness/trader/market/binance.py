"""Spot klines from the Binance public REST API.

Binance is the only built-in source that is the exchange itself rather than an
aggregator, which is why it is marked exchange quality: the bar it publishes is
the bar its matching engine printed.

The payload is a list of positional arrays whose field order is openTimeMs,
open, high, low, close, volume, closeTime and five more columns. This is the
one built-in source that already speaks OHLC order, so the positional mapping
is short - but the timestamps are epoch milliseconds in UTC, and the whole
series has to be converted before it can sit beside a daily A-share series.

Daily and longer bars are stamped at the open of their UTC window, which is
what the exchange reports ("1d" opens at 00:00 UTC). The timestamp is not
shifted into an exchange timezone: inventing a session boundary for a market
that never closes would be worse than naming the boundary we actually got.

The public endpoint needs no key, but it is regional: binance.com answers HTTP
451 in some jurisdictions. That failure is reported with the status code rather
than retried against mirrors, so a caller learns the truth about where the
request came from.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone

from smartmoney_cub_harness.trader.market.base import (
    DEFAULT_LIMIT,
    MarketDataError,
    ProviderResult,
    decode_json,
    http_get,
    is_intraday,
    make_result,
    parse_float,
    prepare,
    provider_spec,
    snippet,
)

__all__ = ["KLINES_URL", "PROVIDER", "BinanceProvider", "bars", "binance_symbol"]

PROVIDER_ID = "binance"

KLINES_URL = "https://api.binance.com/api/v3/klines"

# Binance interval codes are the canonical ones, so this map only exists to
# document the endpoint's vocabulary.
INTERVALS = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "60m": "1h",
    "1d": "1d",
    "1w": "1w",
    "1M": "1M",
}

# The endpoint caps a single page at 1000 rows.
PAGE_SIZE = 1000


def binance_symbol(symbol: str) -> str:
    """Uppercase the pair and accept the BTC-USDT and BTC/USDT spellings."""
    text = symbol.strip().upper()
    if not text:
        raise MarketDataError("symbol is required")
    for separator in ("-", "/", "_"):
        if separator in text:
            text = text.replace(separator, "")
    if not text.isalnum():
        raise MarketDataError("binance cannot read the symbol " + repr(symbol))
    return text


def build_url(symbol: str, *, interval: str, start: str | None, end: str | None, limit: int) -> str:
    query: dict[str, str] = {
        "symbol": symbol,
        "interval": INTERVALS[interval],
        "limit": str(min(limit, PAGE_SIZE)),
    }
    if start:
        query["startTime"] = str(epoch_ms(start))
    if end:
        query["endTime"] = str(epoch_ms(end, end_of_day=True))
    return KLINES_URL + "?" + urllib.parse.urlencode(query)


def epoch_ms(value: str, *, end_of_day: bool = False) -> int:
    """A range bound as epoch milliseconds.

    A bare date is read as 00:00 UTC, or as the last millisecond of that UTC
    day for an upper bound, so "end=2026-09-11" includes the 11th.
    """
    text = value.strip()
    try:
        if len(text) == 10:
            moment = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
            if end_of_day:
                moment = moment + timedelta(days=1) - timedelta(milliseconds=1)
        else:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise MarketDataError("binance cannot read the timestamp " + repr(value)) from error
    return int(moment.timestamp() * 1000)


def stamp(open_time_ms: object, *, provider: str, intraday: bool) -> str:
    try:
        milliseconds = int(open_time_ms)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise MarketDataError(
            provider + " returned a non-numeric open time: " + repr(open_time_ms)
        ) from error
    moment = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
    if not intraday and milliseconds % 86_400_000 == 0:
        return moment.date().isoformat()
    # A naive UTC wall-clock, matching the timestamp form the other providers
    # publish, so a series can be compared and sorted as plain strings.
    return moment.strftime("%Y-%m-%dT%H:%M:%S")


def parse_row(
    entry: object, *, provider: str, intraday: bool
) -> tuple[str, float, float, float, float, float]:
    """Read one kline array: openTime, open, high, low, close, volume."""
    if not isinstance(entry, list) or len(entry) < 6:
        raise MarketDataError(provider + " returned a malformed kline: " + repr(entry))
    return (
        stamp(entry[0], provider=provider, intraday=intraday),
        parse_float(entry[1], provider=provider, field="open"),
        parse_float(entry[2], provider=provider, field="high"),
        parse_float(entry[3], provider=provider, field="low"),
        parse_float(entry[4], provider=provider, field="close"),
        parse_float(entry[5], provider=provider, field="volume"),
    )


def parse_payload(body: str, *, interval: str) -> tuple[list, list[str]]:
    provider = PROVIDER_ID
    payload = decode_json(body, provider=provider)
    if isinstance(payload, dict):
        message = payload.get("msg") or payload.get("message") or ""
        raise MarketDataError(
            provider
            + " refused the request (code "
            + str(payload.get("code"))
            + "): "
            + str(message)
        )
    if not isinstance(payload, list) or not payload:
        raise MarketDataError(
            provider + " returned no klines; refusing to report an empty series: " + snippet(body)
        )
    intraday = is_intraday(interval)
    rows = [parse_row(entry, provider=provider, intraday=intraday) for entry in payload]
    warnings: list[str] = []
    if len(rows) >= PAGE_SIZE:
        warnings.append(
            "the response filled a full "
            + str(PAGE_SIZE)
            + "-bar page; older bars may exist beyond it"
        )
    return rows, warnings


class BinanceProvider:
    """The built-in Binance source. Constructing it performs no I/O."""

    provider_id = PROVIDER_ID
    label = provider_spec(PROVIDER_ID)["label"]
    markets = provider_spec(PROVIDER_ID)["markets"]
    requires_key = provider_spec(PROVIDER_ID)["requires_key"]
    source_quality = provider_spec(PROVIDER_ID)["source_quality"]
    description = provider_spec(PROVIDER_ID)["description"]

    def bars(
        self,
        symbol: str,
        interval: str,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> ProviderResult:
        clean, interval, start, end, limit = prepare(
            symbol, interval, start=start, end=end, limit=limit
        )
        code = binance_symbol(clean)
        url = build_url(code, interval=interval, start=start, end=end, limit=limit)
        rows, warnings = parse_payload(http_get(url), interval=interval)
        if limit > PAGE_SIZE:
            warnings.append(
                "binance answers at most "
                + str(PAGE_SIZE)
                + " klines per request; asked for "
                + str(limit)
                + ", so the older bars were not requested"
            )
        return make_result(
            provider_id=self.provider_id,
            source_quality=self.source_quality,
            symbol=clean,
            interval=interval,
            rows=rows,
            start=start,
            end=end,
            limit=limit,
            warnings=warnings,
        )


PROVIDER = BinanceProvider()


def bars(
    symbol: str,
    interval: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ProviderResult:
    return PROVIDER.bars(symbol, interval, start=start, end=end, limit=limit)
