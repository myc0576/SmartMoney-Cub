"""Normalized shapes and shared helpers for the market data providers.

Why one shape: the four built-in sources speak four dialects - comma-joined
strings inside nested JSON (Eastmoney), arrays inside nested JSON (Tencent and
Binance), and CSV (Stooq). Backtests, replay, and the HTTP surface should never
learn which dialect a series came from, so every provider returns the same Bar
objects wrapped in a ProviderResult that records provenance: which provider
answered, when we asked, and how authoritative the source is.

Importing this module performs no I/O, and neither does importing the package:
fetch_bars imports a provider module on first use.

Volume stays in the source's own unit. Eastmoney and Tencent report A-share
lots, Binance reports the base asset, and Stooq reports shares; rescaling would
invent a share count the source never published.

open_time is ISO-8601 in the bar's own session clock: a calendar date for daily
and longer intervals, and YYYY-MM-DDTHH:MM:SS for intraday bars, which is the
form the sources themselves publish. No timezone is invented for a source that
does not state one: Binance bars are UTC, A-share bars are the exchange session
clock. Market codes are cn (Shanghai and Shenzhen), hk, us, eu, and crypto.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable, Protocol, runtime_checkable

__all__ = [
    "Bar",
    "CANONICAL_INTERVALS",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MarketDataError",
    "MarketDataProvider",
    "PROVIDER_SPECS",
    "ProviderResult",
    "SOURCE_QUALITIES",
    "USER_AGENT",
    "build_bars",
    "build_request",
    "catalog_entry",
    "clean_symbol",
    "decode_json",
    "http_get",
    "is_intraday",
    "iso_utc_now",
    "make_result",
    "normalize_bound",
    "normalize_interval",
    "normalize_limit",
    "parse_float",
    "prepare",
    "provider_spec",
    "snippet",
]

# Whether a source can actually answer a request from where this process runs.
#
# This is deliberately not part of the provider's identity: the same catalogue is
# shipped everywhere, and which endpoints answer depends on the network the
# process is on. Binance refuses requests from some regions with HTTP 451, and
# stooq.com failed its TLS handshake from the machine this was verified on. A
# picker that lists them as ordinary choices turns a network fact into a mystery
# failure, so the catalogue states the availability and why.
AVAILABILITY_AVAILABLE = "available"
AVAILABILITY_UNAVAILABLE = "unavailable"
AVAILABILITY_RESTRICTED = "restricted"

# Identify ourselves honestly. A blank or improvised User-Agent is what gets a
# keyless endpoint to refuse a request outright.
USER_AGENT = "Mozilla/5.0 (compatible; smartmoney-cub-harness/0.1; read-only market data)"

REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_LIMIT = 500
MAX_LIMIT = 5000

SOURCE_QUALITIES = ("exchange", "aggregator", "delayed")

# The interval vocabulary every provider accepts. The sources spell the same
# interval differently (day, qfqday, 1d), so callers use these names and each
# provider translates them.
CANONICAL_INTERVALS = ("1m", "5m", "15m", "30m", "60m", "1d", "1w", "1M")
_INTERVAL_ALIASES = {
    "1min": "1m",
    "min": "1m",
    "minute": "1m",
    "5min": "5m",
    "15min": "15m",
    "30min": "30m",
    "60min": "60m",
    "1h": "60m",
    "hour": "60m",
    "d": "1d",
    "1day": "1d",
    "day": "1d",
    "daily": "1d",
    "w": "1w",
    "1week": "1w",
    "week": "1w",
    "weekly": "1w",
    "mo": "1M",
    "1mo": "1M",
    "1month": "1M",
    "month": "1M",
    "monthly": "1M",
}

Row = tuple[str, float, float, float, float, float]


class MarketDataError(RuntimeError):
    """Raised when a provider cannot return a usable series.

    A provider never answers a failure with an empty bar list: an empty result
    would be indistinguishable from a market with no sessions, and a review
    built on a silent gap is worse than a review that stopped.
    """


@dataclass(frozen=True, slots=True)
class Bar:
    """One normalized OHLCV bar. Frozen so a fetched series cannot be edited."""

    symbol: str
    interval: str
    open_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProviderResult:
    """A fetched series plus the provenance a review needs to trust it."""

    bars: list[Bar]
    provider_id: str
    symbol: str
    interval: str
    fetched_at: str
    source_quality: str
    warnings: list[str]
    available_at: str | None = None
    decision_time: str | None = None
    historical_evidence: str = "unverified"

    def __post_init__(self) -> None:
        if self.available_at and self.decision_time:
            try:
                available = datetime.fromisoformat(self.available_at.replace("Z", "+00:00"))
                decision = datetime.fromisoformat(self.decision_time.replace("Z", "+00:00"))
                if available > decision:
                    raise MarketDataError("available_at is later than decision_time")
            except (ValueError, TypeError):
                raise MarketDataError("availability and decision timestamps must have comparable timezone precision") from None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "symbol": self.symbol,
            "interval": self.interval,
            "fetched_at": self.fetched_at,
            "source_quality": self.source_quality,
            "warnings": list(self.warnings),
            "available_at": self.available_at,
            "decision_time": self.decision_time,
            "historical_evidence": self.historical_evidence,
            "bars": [bar.to_dict() for bar in self.bars],
        }


@runtime_checkable
class MarketDataProvider(Protocol):
    """The surface a built-in source implements. One protocol, four dialects."""

    provider_id: str
    label: str
    markets: tuple[str, ...]
    requires_key: bool
    source_quality: str
    description: str

    def bars(
        self,
        symbol: str,
        interval: str,
        *,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> ProviderResult: ...


# The catalog is the single source of truth for provider metadata: it describes
# a provider without importing it, which keeps list_providers() free of module
# imports and keeps a provider list cheap for the UI to render.
PROVIDER_SPECS: tuple[dict[str, Any], ...] = (
    {
        "provider_id": "eastmoney",
        "label": "Eastmoney (东方财富)",
        "markets": ("cn",),
        "requires_key": False,
        "source_quality": "aggregator",
        "description": (
            "Shanghai and Shenzhen stocks, ETFs, and indices. Daily to 60-minute "
            "klines, forward adjusted (fqt=1)."
        ),
        "module": "smartmoney_cub_harness.trader.market.eastmoney",
    },
    {
        "provider_id": "tencent",
        "label": "Tencent quotes (腾讯行情)",
        "markets": ("cn", "hk", "us"),
        "requires_key": False,
        "source_quality": "aggregator",
        "description": (
            "A-share, Hong Kong, and US listings. Daily, weekly, and monthly "
            "bars, forward adjusted where the source offers it."
        ),
        "module": "smartmoney_cub_harness.trader.market.tencent",
    },
    {
        "provider_id": "stooq",
        "label": "Stooq",
        "markets": ("us", "eu"),
        "requires_key": False,
        "source_quality": "delayed",
        "description": (
            "Daily CSV history for US and European symbols. Free and unadjusted; "
            "the page is delayed and sometimes rate limited."
        ),
        # Verified on 2026-09-21: the TLS handshake to stooq.com fails
        # (UNEXPECTED_EOF_WHILE_READING), so no request through it can succeed.
        # The source stays in the catalogue because the failure may be
        # network-specific, and a reader is owed the reason rather than a
        # silently missing option.
        "availability": AVAILABILITY_UNAVAILABLE,
        "availability_reason": "stooq.com 的 TLS 握手在当前网络失败，取不到行情",
        "module": "smartmoney_cub_harness.trader.market.stooq",
    },
    {
        "provider_id": "binance",
        "label": "Binance spot",
        "markets": ("crypto",),
        "requires_key": False,
        "source_quality": "exchange",
        "description": (
            "Binance spot klines from the exchange itself. 1-minute to 1-month "
            "intervals, no key required for public market data."
        ),
        # Verified on 2026-09-21: api.binance.com answers HTTP 451 from this
        # region, which is a refusal by the exchange rather than a bug here.
        "availability": AVAILABILITY_RESTRICTED,
        "availability_reason": "币安按地区拒绝服务（HTTP 451），当前地区取不到行情",
        "module": "smartmoney_cub_harness.trader.market.binance",
    },
)


def provider_spec(provider_id: str) -> dict[str, Any]:
    wanted = str(provider_id or "").strip().lower()
    for spec in PROVIDER_SPECS:
        if spec["provider_id"] == wanted:
            return spec
    known = ", ".join(spec["provider_id"] for spec in PROVIDER_SPECS)
    raise MarketDataError(
        "unknown market data provider " + repr(provider_id) + "; known providers: " + known
    )


def catalog_entry(spec: dict[str, Any]) -> dict[str, Any]:
    """The public catalogue shape. The module path stays internal."""
    return {
        "provider_id": spec["provider_id"],
        "label": spec["label"],
        "markets": list(spec["markets"]),
        "requires_key": spec["requires_key"],
        "source_quality": spec["source_quality"],
        "description": spec["description"],
        # A source with no declared availability is assumed reachable: absence of
        # a finding is not a finding, and the two sources known to fail say so in
        # their own spec.
        "availability": spec.get("availability", AVAILABILITY_AVAILABLE),
        "availability_reason": spec.get("availability_reason", ""),
    }


def iso_utc_now() -> str:
    """Fetch time as an ISO-8601 UTC string, to the second."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def snippet(body: str, limit: int = 160) -> str:
    """A short, single-line quote of a payload for an error message."""
    collapsed = " ".join((body or "").split())
    return collapsed[:limit]


def decode_json(body: str, *, provider: str) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError as error:
        raise MarketDataError(
            provider + " did not answer with JSON (" + str(error) + "): " + snippet(body)
        ) from error


def parse_float(value: Any, *, provider: str, field: str) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as error:
        raise MarketDataError(
            provider + " returned a non-numeric " + field + ": " + repr(value)
        ) from error


def clean_symbol(symbol: str) -> str:
    text = symbol.strip() if isinstance(symbol, str) else ""
    if not text:
        raise MarketDataError("symbol is required")
    return text


def is_intraday(interval: str) -> bool:
    return interval not in ("1d", "1w", "1M")


def normalize_interval(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketDataError("interval is required")
    text = value.strip()
    if text in CANONICAL_INTERVALS:
        return text
    alias = _INTERVAL_ALIASES.get(text.lower())
    if alias:
        return alias
    raise MarketDataError(
        "unsupported interval "
        + repr(value)
        + "; supported intervals: "
        + ", ".join(CANONICAL_INTERVALS)
    )


def normalize_limit(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise MarketDataError("limit must be an integer, got " + repr(value)) from error
    if number < 1:
        raise MarketDataError("limit must be at least 1")
    if number > MAX_LIMIT:
        raise MarketDataError("limit must be at most " + str(MAX_LIMIT))
    return number


def normalize_bound(value: Any, *, field: str) -> str | None:
    """Accept an ISO-8601 date, optionally with a time, as a range bound."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        date.fromisoformat(text[:10])
    except ValueError as error:
        raise MarketDataError(
            field + " must be an ISO-8601 date such as 2026-09-01, got " + repr(value)
        ) from error
    if len(text) > 10:
        try:
            datetime.fromisoformat(text)
        except ValueError as error:
            raise MarketDataError(
                field + " must be an ISO-8601 date or timestamp, got " + repr(value)
            ) from error
    return text


def prepare(
    symbol: str,
    interval: str,
    *,
    start: str | None,
    end: str | None,
    limit: int,
) -> tuple[str, str, str | None, str | None, int]:
    """Validate the public arguments once, so every provider agrees on them."""
    return (
        clean_symbol(symbol),
        normalize_interval(interval),
        normalize_bound(start, field="start"),
        normalize_bound(end, field="end"),
        normalize_limit(limit),
    )


def build_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        method="GET",
    )


def http_get(url: str, *, timeout: float = REQUEST_TIMEOUT_SECONDS) -> str:
    """GET a URL and return its body as text.

    Every failure becomes a MarketDataError that names the host and, when the
    server answered with an HTTP error, quotes the start of its body: a keyless
    endpoint that starts refusing traffic says so in that body.
    """
    host = urllib.parse.urlsplit(url).netloc or url
    request = build_request(url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = snippet(error.read().decode("utf-8", errors="replace"))
        except Exception:  # pragma: no cover - the body may already be consumed
            detail = ""
        raise MarketDataError(
            "HTTP " + str(error.code) + " from " + host + (" : " + detail if detail else "")
        ) from error
    except urllib.error.URLError as error:
        raise MarketDataError("could not reach " + host + ": " + str(error.reason)) from error
    except (TimeoutError, OSError) as error:
        raise MarketDataError("request to " + host + " failed: " + str(error)) from error
    if not raw:
        raise MarketDataError("empty response body from " + host)
    return raw.decode("utf-8", errors="replace")


def _within_range(open_time: str, start: str | None, end: str | None, *, intraday: bool) -> bool:
    if start:
        if intraday:
            low = start if len(start) > 10 else start + "T00:00:00"
            if open_time < low:
                return False
        elif open_time[:10] < start[:10]:
            return False
    if end:
        if intraday:
            high = end if len(end) > 10 else end + "T23:59:59"
            if open_time > high:
                return False
        elif open_time[:10] > end[:10]:
            return False
    return True


def build_bars(
    rows: Iterable[Row],
    *,
    symbol: str,
    interval: str,
    start: str | None,
    end: str | None,
    limit: int,
    warnings: Iterable[str] = (),
) -> tuple[list[Bar], list[str]]:
    """Order, filter, and trim parsed rows, reporting anything suspicious.

    Providers hand over rows in the order the source sent them. Ordering, range
    filtering, trimming, and the warnings that describe each of those live here
    so all four sources behave identically.
    """
    notes = [note for note in warnings if note]
    intraday = is_intraday(interval)

    ordered: list[Bar] = []
    seen: set[str] = set()
    for open_time, open_, high, low, close, volume in rows:
        if open_time in seen:
            continue
        seen.add(open_time)
        ordered.append(
            Bar(
                symbol=symbol,
                interval=interval,
                open_time=open_time,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    ordered.sort(key=lambda bar: bar.open_time)

    selected = [
        bar for bar in ordered if _within_range(bar.open_time, start, end, intraday=intraday)
    ]
    if ordered and not selected:
        notes.append(
            "no bars between "
            + (start or "the beginning of the series")
            + " and "
            + (end or "the end of the series")
            + "; the source returned "
            + str(len(ordered))
            + " bars outside that range"
        )

    if len(selected) > limit:
        notes.append(
            "trimmed " + str(len(selected) - limit) + " older bars to honour limit=" + str(limit)
        )
        selected = selected[-limit:]

    if (
        start
        and selected
        and len(selected) == limit
        and selected[0].open_time[:10] > start[:10]
    ):
        notes.append(
            "the source returned a full page of "
            + str(limit)
            + " bars whose earliest bar is "
            + selected[0].open_time
            + ", later than the requested start "
            + start[:10]
            + "; the page may be truncated"
        )

    return selected, notes


def make_result(
    *,
    provider_id: str,
    source_quality: str,
    symbol: str,
    interval: str,
    rows: Iterable[Row],
    start: str | None,
    end: str | None,
    limit: int,
    warnings: Iterable[str] = (),
) -> ProviderResult:
    bars, notes = build_bars(
        rows,
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
        limit=limit,
        warnings=warnings,
    )
    return ProviderResult(
        bars=bars,
        provider_id=provider_id,
        symbol=symbol,
        interval=interval,
        fetched_at=iso_utc_now(),
        source_quality=source_quality,
        warnings=notes,
    )
