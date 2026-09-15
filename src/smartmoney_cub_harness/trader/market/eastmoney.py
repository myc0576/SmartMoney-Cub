"""A-share bars from Eastmoney's kline endpoint.

Eastmoney is the default source for Shanghai and Shenzhen listings because its
kline endpoint answers one request per symbol with no key and no cookie, and
because the secid scheme (1 for Shanghai, 0 for Shenzhen) makes the market
explicit instead of guessed from the code.

The payload is a list of comma-joined strings whose field order is date, open,
close, high, low, volume, amount. Close comes second and high comes third,
which is not the OHLC order most people expect: reading that payload
positionally is the single easiest way to ship a chart with the close and the
high swapped, so the positional mapping lives in one function below.

Volume is reported in lots (手), the unit the exchange publishes for A-shares;
the amount column is turnover in currency and is dropped, since Bar has no
field for it and inventing one would break the shared shape.

Intraday bars are requested with fqt=1 (forward adjusted) like daily bars.
Adjustment is meaningless for a single session, but keeping one value for the
whole provider means a caller cannot get adjusted dailies and unadjusted
minutes from the same series by accident.
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
    make_result,
    parse_float,
    prepare,
    provider_spec,
    snippet,
)

__all__ = ["EastmoneyProvider", "KLINES_URL", "PROVIDER", "bars", "secid_for", "klt_for"]

PROVIDER_ID = "eastmoney"

KLINES_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

# klt is Eastmoney's interval code. 1/5/15/30/60 are minutes, 101/102/103 are
# day/week/month.
KLT = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
    "1d": "101",
    "1w": "102",
    "1M": "103",
}

# Shanghai is market 1 and Shenzhen is market 0. The first digit of the code
# decides for a bare six-digit symbol: 6 and 9 are Shanghai listings, 5 is a
# Shanghai fund, and 0/1/2/3 are Shenzhen. An explicit prefix always wins, so
# an index such as 000001 in Shanghai can be requested as sh000001.
SHANGHAI_PREFIXES = ("5", "6", "9")

# fields2 is the kline field order: date, open, close, high, low, volume, amount.
FIELDS2 = "f51,f52,f53,f54,f55,f56,f57"
FIELDS1 = "f1,f2,f3,f4,f5"

END_OF_TIME = "20500101"


def secid_for(symbol: str) -> str:
    """Map a symbol to Eastmoney's secid, which is market dot code."""
    text = symbol.strip().upper()
    if not text:
        raise MarketDataError("symbol is required")

    # Already qualified: "1.600111" or "0.000001".
    if "." in text:
        head, _, tail = text.partition(".")
        if head in ("0", "1") and tail.isdigit():
            return head + "." + tail
        # Suffix form: "600111.SH".
        if tail in ("SH", "SS", "SHANGHAI") and head.isdigit():
            return "1." + head
        if tail in ("SZ", "SHENZHEN") and head.isdigit():
            return "0." + head
        raise MarketDataError(
            "eastmoney serves Shanghai and Shenzhen securities only; cannot read symbol "
            + repr(symbol)
        )

    if text.startswith("SH") and text[2:].isdigit():
        return "1." + text[2:]
    if text.startswith("SZ") and text[2:].isdigit():
        return "0." + text[2:]

    if not text.isdigit() or len(text) != 6:
        raise MarketDataError(
            "eastmoney needs a six-digit A-share code, optionally prefixed with sh or sz, got "
            + repr(symbol)
        )
    market = "1" if text[0] in SHANGHAI_PREFIXES else "0"
    return market + "." + text


def klt_for(interval: str) -> str:
    code = KLT.get(interval)
    if code is None:  # pragma: no cover - normalize_interval rejects these first
        raise MarketDataError("eastmoney does not serve interval " + repr(interval))
    return code


def build_url(
    secid: str,
    *,
    interval: str,
    start: str | None,
    end: str | None,
    limit: int,
) -> str:
    query = {
        "secid": secid,
        "fields1": FIELDS1,
        "fields2": FIELDS2,
        "klt": klt_for(interval),
        "fqt": "1",
        "end": end.replace("-", "")[:8] if end else END_OF_TIME,
        "lmt": str(limit),
    }
    if start:
        # Eastmoney takes a day, not a time, so an intraday window is widened
        # to its start date upstream and narrowed exactly by build_bars below.
        query["beg"] = start.replace("-", "")[:8]
    return KLINES_URL + "?" + urllib.parse.urlencode(query)


def session_date() -> str:
    """The current trading date in the exchange's own clock (UTC+8)."""
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()


def parse_kline(entry: object, *, provider: str) -> tuple[str, float, float, float, float, float]:
    """Read one kline string. The field order is date, open, close, high, low."""
    if not isinstance(entry, str):
        raise MarketDataError(provider + " returned a kline that is not a string: " + repr(entry))
    parts = entry.split(",")
    if len(parts) < 6:
        raise MarketDataError(provider + " returned a kline with too few fields: " + repr(entry))
    stamp = parts[0].strip()
    if " " in stamp:
        stamp = stamp.replace(" ", "T")
    if "T" in stamp and len(stamp) == 16:
        stamp = stamp + ":00"
    return (
        stamp,
        parse_float(parts[1], provider=provider, field="open"),
        parse_float(parts[3], provider=provider, field="high"),
        parse_float(parts[4], provider=provider, field="low"),
        parse_float(parts[2], provider=provider, field="close"),
        parse_float(parts[5], provider=provider, field="volume"),
    )


def parse_payload(body: str, *, interval: str, today: str) -> tuple[list, list[str]]:
    provider = PROVIDER_ID
    payload = decode_json(body, provider=provider)
    if not isinstance(payload, dict):
        raise MarketDataError(provider + " returned an unexpected payload: " + snippet(body))
    data = payload.get("data")
    if not isinstance(data, dict):
        # Eastmoney answers {"rc":0,"data":null} for a code it does not know.
        raise MarketDataError(
            provider + " returned no data object; the symbol may not exist: " + snippet(body)
        )
    klines = data.get("klines")
    if not isinstance(klines, list) or not klines:
        raise MarketDataError(
            provider
            + " returned an empty kline list for "
            + str(data.get("code") or "the requested symbol")
            + "; refusing to report an empty series"
        )

    rows = [parse_kline(entry, provider=provider) for entry in klines]
    warnings: list[str] = []
    if interval == "1d" and rows and rows[-1][0][:10] == today:
        warnings.append(
            "the last bar is dated today and may be an unfinished session; re-fetch after the close"
        )
    return rows, warnings


class EastmoneyProvider:
    """The built-in Eastmoney source. Constructing it performs no I/O."""

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
        url = build_url(
            secid_for(clean), interval=interval, start=start, end=end, limit=limit
        )
        body = http_get(url)
        rows, warnings = parse_payload(body, interval=interval, today=session_date())
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


PROVIDER = EastmoneyProvider()


def bars(
    symbol: str,
    interval: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ProviderResult:
    return PROVIDER.bars(symbol, interval, start=start, end=end, limit=limit)
