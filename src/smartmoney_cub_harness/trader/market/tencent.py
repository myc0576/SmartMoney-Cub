"""A-share, Hong Kong, and US bars from Tencent's fqkline endpoint.

Tencent is the second A-share source and the only built-in source for Hong Kong
and US listings. It answers one request per symbol and quotes the market in the
symbol prefix (sh, sz, hk, us), which is why the prefix is required here rather
than inferred from the code: the same six digits are a different company in a
different market.

The payload nests arrays under a key whose name carries the interval and the
adjustment: qfqday for forward-adjusted daily, qfqweek, qfqmonth, and day for
the unadjusted daily series. This module asks for the forward-adjusted series
and falls back to the unadjusted key when the source does not offer one, which
is what it does for Hong Kong and US symbols. The response also carries an
unrelated quotes object; the parsing below reads only the series key, so a
change to the quote block cannot alter a bar.

Rows are date, open, close, high, low, volume - the same non-OHLC order as
Eastmoney, and the same trap, so the positional mapping is explicit here too.

Tencent serves daily, weekly, and monthly bars through this endpoint but
answers "bad params" for minute intervals, so a minute request is refused here
with a message that names a source that does serve it rather than being sent
upstream to fail obscurely.
"""

from __future__ import annotations

import urllib.parse

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

__all__ = ["PROVIDER", "KLINES_URL", "TencentProvider", "bars", "market_prefix", "symbol_code"]

PROVIDER_ID = "tencent"

KLINES_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

# The interval names this endpoint understands, and the adjusted series key it
# answers with. The unadjusted name is the same word without the qfq prefix.
INTERVAL_NAMES = {"1d": "day", "1w": "week", "1M": "month"}

# Tencent prefixes every symbol with its market.
PREFIXES = ("sh", "sz", "hk", "us")

# A single request returns at most this many bars and the endpoint silently
# ignores larger limits, so a bigger request is capped and warned about rather
# than quietly returning a short page.
PAGE_SIZE = 640


def market_prefix(symbol: str) -> tuple[str, str]:
    """Split a symbol into its market prefix and bare code.

    A bare six-digit code is read as a mainland listing, with the same first
    digit rule Eastmoney uses: 5, 6, and 9 are Shanghai and the rest Shenzhen.
    """
    text = symbol.strip()
    if not text:
        raise MarketDataError("symbol is required")
    lowered = text.lower()
    if lowered[:2] in PREFIXES and len(text) > 2:
        return lowered[:2], text[2:].upper()

    upper = text.upper()
    if "." in upper:
        head, _, tail = upper.partition(".")
        if tail in ("SH", "SS", "SHANGHAI") and head.isdigit():
            return "sh", head
        if tail in ("SZ", "SHENZHEN") and head.isdigit():
            return "sz", head
        if tail in ("HK",) and head.isdigit():
            return "hk", head
        if tail in ("US",) and head:
            return "us", head
        raise MarketDataError("tencent cannot read the symbol suffix in " + repr(symbol))

    if upper.isdigit() and len(upper) == 6:
        return ("sh" if upper[0] in ("5", "6", "9") else "sz"), upper
    if upper.isdigit() and len(upper) <= 5:
        # Hong Kong codes are up to five digits.
        return "hk", upper
    if upper.isalnum():
        return "us", upper
    raise MarketDataError("tencent cannot read the symbol " + repr(symbol))


def symbol_code(symbol: str) -> str:
    prefix, code = market_prefix(symbol)
    return prefix + code


def build_url(code: str, *, interval: str, start: str | None, end: str | None, limit: int) -> str:
    if is_intraday(interval):
        raise MarketDataError(
            "tencent serves daily, weekly, and monthly bars only; "
            "use eastmoney for A-share minutes or binance for crypto minutes"
        )
    span = min(limit, PAGE_SIZE)
    param = ",".join(
        [code, INTERVAL_NAMES[interval], start or "", end or "", str(span), "qfq"]
    )
    return KLINES_URL + "?" + urllib.parse.urlencode({"param": param})


def series_key(interval: str) -> str:
    return "qfq" + INTERVAL_NAMES[interval]


def parse_row(entry: object, *, provider: str) -> tuple[str, float, float, float, float, float]:
    """Read one row: date, open, close, high, low, volume."""
    if not isinstance(entry, list) or len(entry) < 6:
        raise MarketDataError(provider + " returned a malformed row: " + repr(entry))
    stamp = str(entry[0]).strip()
    if " " in stamp:
        stamp = stamp.replace(" ", "T")
    if "T" in stamp and len(stamp) == 16:
        stamp = stamp + ":00"
    return (
        stamp,
        parse_float(entry[1], provider=provider, field="open"),
        parse_float(entry[3], provider=provider, field="high"),
        parse_float(entry[4], provider=provider, field="low"),
        parse_float(entry[2], provider=provider, field="close"),
        parse_float(entry[5], provider=provider, field="volume"),
    )


def parse_payload(body: str, *, code: str, interval: str) -> tuple[list, list[str]]:
    provider = PROVIDER_ID
    payload = decode_json(body, provider=provider)
    if not isinstance(payload, dict):
        raise MarketDataError(provider + " returned an unexpected payload: " + snippet(body))

    block = payload.get("data")
    if not isinstance(block, dict):
        raise MarketDataError(
            provider + " returned no data object for " + code + ": " + snippet(body)
        )
    symbol_block = block.get(code)
    if not isinstance(symbol_block, dict):
        raise MarketDataError(
            provider + " returned no series for " + code + ": " + snippet(body)
        )

    # The adjusted key is the one we asked for; the unadjusted key is what the
    # source answers with for markets where it publishes no adjusted series.
    adjusted = series_key(interval)
    entries = symbol_block.get(adjusted)
    warnings: list[str] = []
    if not isinstance(entries, list) or not entries:
        unadjusted = INTERVAL_NAMES[interval]
        fallback = symbol_block.get(unadjusted)
        if isinstance(fallback, list) and fallback:
            entries = fallback
            warnings.append(
                provider
                + " served the unadjusted "
                + unadjusted
                + " series; corporate actions are not applied"
            )
        else:
            raise MarketDataError(
                provider
                + " returned no "
                + adjusted
                + " series for "
                + code
                + "; refusing to report an empty series"
            )

    rows = [parse_row(entry, provider=provider) for entry in entries]
    return rows, warnings


class TencentProvider:
    """The built-in Tencent source. Constructing it performs no I/O."""

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
        code = symbol_code(clean)
        url = build_url(code, interval=interval, start=start, end=end, limit=limit)
        body = http_get(url)
        rows, warnings = parse_payload(body, code=code, interval=interval)
        if limit > PAGE_SIZE:
            warnings.append(
                "tencent answers at most "
                + str(PAGE_SIZE)
                + " bars per request; asked for "
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


PROVIDER = TencentProvider()


def bars(
    symbol: str,
    interval: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ProviderResult:
    return PROVIDER.bars(symbol, interval, start=start, end=end, limit=limit)
