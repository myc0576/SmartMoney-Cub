"""Daily CSV history for US and European symbols from Stooq.

Stooq is the long-history fallback: its download endpoint answers a plain CSV
file with a header and no key, which covers US and European daily history that
the A-share-centric sources do not. It is marked delayed because the page it
serves is a free, unadjusted, end-of-day snapshot.

The endpoint is also the least dependable of the four: it interposes a
JavaScript browser check, and answers with an HTML page instead of CSV when it
decides the caller is a robot. That case is detected by the absent CSV header
and reported as a MarketDataError that says what happened, rather than being
parsed into bars that do not exist.

Stooq's row order is Date,Open,High,Low,Close,Volume - the standard order, and
deliberately the opposite of the A-share sources above.

One request returns the whole history, so the requested window is applied here:
the download endpoint accepts d1 and d2 for quality data, but it only honours
them for a paid account, and a free request that silently ignores a date range
would look like a working filter.
"""

from __future__ import annotations

import urllib.parse

from smartmoney_cub_harness.trader.market.base import (
    DEFAULT_LIMIT,
    MarketDataError,
    ProviderResult,
    http_get,
    make_result,
    parse_float,
    prepare,
    provider_spec,
)

__all__ = ["CSV_URL", "PROVIDER", "StooqProvider", "bars", "stooq_symbol"]

PROVIDER_ID = "stooq"

CSV_URL = "https://stooq.com/q/d/l/"

HEADER = ("date", "open", "high", "low", "close", "volume")


def stooq_symbol(symbol: str) -> str:
    """Add the market suffix a bare ticker needs, and keep one that is present.

    A bare alphanumeric ticker is read as a US listing, which is what Stooq
    names with the .us suffix. A symbol that already carries a dot is handed
    over unchanged, so a European listing such as sap.de and a forex pair such
    as eurusd both reach the source exactly as written.
    """
    text = symbol.strip().lower()
    if not text:
        raise MarketDataError("symbol is required")
    if "." in text:
        return text
    if text.isalnum():
        return text + ".us"
    raise MarketDataError("stooq cannot read the symbol " + repr(symbol))


def build_url(symbol: str) -> str:
    return CSV_URL + "?" + urllib.parse.urlencode({"s": symbol, "i": "d"})


def parse_csv(body: str) -> tuple[list, list[str]]:
    """Parse the CSV body. An HTML answer means the browser check refused us."""
    provider = PROVIDER_ID
    text = body.lstrip("\ufeff").strip()
    if not text:
        raise MarketDataError(
            provider + " returned an empty body; refusing to report an empty series"
        )

    lowered = text[:400].lower()
    if lowered.startswith("<") or "<html" in lowered or "<!doctype" in lowered:
        raise MarketDataError(
            provider
            + " answered with an HTML page instead of CSV; the free download endpoint is "
            "rate limiting or serving its browser check"
        )

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise MarketDataError(
            provider + " returned no CSV rows; refusing to report an empty series"
        )

    header = [column.strip().lower() for column in lines[0].split(",")]
    if tuple(header[:6]) != HEADER:
        raise MarketDataError(
            provider + " returned a CSV header this module does not recognise: " + lines[0][:160]
        )

    rows: list[tuple[str, float, float, float, float, float]] = []
    skipped = 0
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 6:
            skipped += 1
            continue
        try:
            rows.append(
                (
                    parts[0].strip(),
                    parse_float(parts[1], provider=provider, field="open"),
                    parse_float(parts[2], provider=provider, field="high"),
                    parse_float(parts[3], provider=provider, field="low"),
                    parse_float(parts[4], provider=provider, field="close"),
                    parse_float(parts[5], provider=provider, field="volume"),
                )
            )
        except MarketDataError:
            # "No data" and holiday placeholders appear as literal text rows.
            skipped += 1
    if not rows:
        raise MarketDataError(
            provider + " returned a CSV file with no usable rows; the symbol may not exist"
        )

    warnings: list[str] = []
    if skipped:
        warnings.append(
            provider
            + " returned "
            + str(skipped)
            + " CSV row(s) that did not parse as bars and were dropped"
        )
    return rows, warnings


class StooqProvider:
    """The built-in Stooq source. Constructing it performs no I/O."""

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
        if interval != "1d":
            raise MarketDataError(
                "stooq serves daily CSV history only; requested " + repr(interval)
            )
        code = stooq_symbol(clean)
        rows, warnings = parse_csv(http_get(build_url(code)))
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


PROVIDER = StooqProvider()


def bars(
    symbol: str,
    interval: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ProviderResult:
    return PROVIDER.bars(symbol, interval, start=start, end=end, limit=limit)
