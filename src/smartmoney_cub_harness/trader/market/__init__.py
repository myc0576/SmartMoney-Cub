"""Market data providers: four keyless sources behind one normalized shape.

The public surface is three calls and two types: fetch_bars() gets a series,
list_providers() describes what is available, and Bar and ProviderResult carry
the data and its provenance. Everything else in this package is an
implementation detail of one source.

Providers are imported lazily, on the first fetch for that provider, so
importing this package costs nothing and performs no network access. That
matters because the package is imported on every application start, including
offline and in CI, where a module-level client for four remote endpoints would
be both slow and wrong.

Callers pass a canonical interval (1m, 5m, 15m, 30m, 60m, 1d, 1w, 1M) and a
symbol in the source's own convention; each provider translates both. Ranges
are inclusive ISO-8601 dates, and limit caps the bars returned, keeping the
most recent ones. A provider raises MarketDataError rather than returning an
empty list, so an upstream failure never looks like a quiet market.
"""

from __future__ import annotations

import importlib
from typing import Any

from smartmoney_cub_harness.trader.market.base import (
    CANONICAL_INTERVALS,
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SOURCE_QUALITIES,
    Bar,
    MarketDataError,
    MarketDataProvider,
    PROVIDER_SPECS,
    ProviderResult,
    catalog_entry,
    provider_spec,
)

__all__ = [
    "Bar",
    "CANONICAL_INTERVALS",
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MarketDataError",
    "MarketDataProvider",
    "PROVIDERS",
    "ProviderResult",
    "SOURCE_QUALITIES",
    "fetch_bars",
    "fetch_symbol_metadata",
    "get_provider",
    "list_providers",
]

def fetch_symbol_metadata(symbols: list[str]) -> dict[str, dict[str, Any]]:
    """Resolve current names and ST status for a list of symbols."""
    from smartmoney_cub_harness.trader.market.symbols import fetch_symbol_metadata as _fetch

    return _fetch(symbols)


# The catalogue is built from metadata only, so listing providers never imports
# a provider module and never touches the network.
PROVIDERS: tuple[dict[str, Any], ...] = tuple(catalog_entry(spec) for spec in PROVIDER_SPECS)


def list_providers() -> list[dict[str, Any]]:
    """Describe the built-in sources: id, label, markets, key, quality, text."""
    return [dict(entry) for entry in PROVIDERS]


def get_provider(provider_id: str) -> MarketDataProvider:
    """Resolve and import one provider module."""
    spec = provider_spec(provider_id)
    module = importlib.import_module(spec["module"])
    return module.PROVIDER


def fetch_bars(
    provider_id: str,
    symbol: str,
    interval: str,
    *,
    start: str | None = None,
    end: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ProviderResult:
    """Fetch one normalized series from one provider.

    Raises MarketDataError when the provider is unknown, the arguments do not
    fit the provider, or the source does not answer with usable bars.
    """
    provider = get_provider(provider_id)
    return provider.bars(symbol, interval, start=start, end=end, limit=limit)
