"""Symbol metadata and ST status resolution for A-shares, ETFs, and foreign listings.

Resolves stock abbreviations, fund names, and real-time Special Treatment (ST/*ST)
status using public keyless quote endpoints (Tencent with Eastmoney fallback).

Results are cached in local storage so offline runs remain fully functional.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

__all__ = [
    "fetch_symbol_metadata",
    "to_market_prefix",
]

USER_AGENT = "Mozilla/5.0 (compatible; smartmoney-cub-harness/0.1; read-only market data)"
REQUEST_TIMEOUT_SECONDS = 6.0


def to_market_prefix(symbol: str) -> str:
    """Convert a raw 6-digit A-share code or ticker to exchange-prefixed form."""
    s = str(symbol).strip()
    if not s:
        return ""
    if s.startswith(("sh", "sz", "bj", "us", "hk")):
        return s.lower()
    # Shanghai: 6xxxxx (stocks/STAR), 588xxx (STAR ETF), 51xxxx/56xxxx (ETFs), 204xxx (repos)
    if s.startswith(("6", "5", "9", "204")):
        return "sh" + s
    # Shenzhen: 00xxxx (main), 30xxxx (ChiNext), 159xxx/16xxxx (funds), 131xxx (repos)
    if s.startswith(("0", "1", "2", "3")):
        return "sz" + s
    # Beijing: 4xxxxx, 8xxxxx, 920xxx
    if s.startswith(("4", "8", "920")):
        return "bj" + s
    # US tickers
    if s.isalpha():
        return "us" + s.upper()
    return s


def fetch_symbol_metadata(symbols: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Batch-resolve symbol names and ST risk status.

    Returns a mapping of symbol -> {"symbol": str, "name": str, "is_st": bool, "updated_at": str}.
    Never raises on network failures; returns an empty mapping if offline.
    """
    clean = [str(s).strip() for s in symbols if str(s).strip()]
    if not clean:
        return {}

    # Query in batches of 60 to prevent URL length limits
    batch_size = 60
    results: dict[str, dict[str, Any]] = {}
    now_str = datetime.now(timezone.utc).isoformat()

    for i in range(0, len(clean), batch_size):
        batch = clean[i : i + batch_size]
        batch_results = _fetch_tencent_batch(batch, now_str)
        # Fallback to Eastmoney for any symbols that failed
        missing = [s for s in batch if s not in batch_results]
        if missing:
            em_results = _fetch_eastmoney_batch(missing, now_str)
            batch_results.update(em_results)
        results.update(batch_results)

    return results


def _fetch_tencent_batch(symbols: Sequence[str], now_str: str) -> dict[str, dict[str, Any]]:
    """Batch query Tencent qt.gtimg.cn."""
    prefixed = [to_market_prefix(s) for s in symbols if to_market_prefix(s)]
    if not prefixed:
        return {}

    url = "http://qt.gtimg.cn/q=" + ",".join(prefixed)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
            text = raw.decode("gbk", errors="replace")
    except Exception:
        return {}

    out: dict[str, dict[str, Any]] = {}
    for line in text.strip().split(";"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("~")
        if len(parts) > 2:
            code = parts[2].strip()
            name = parts[1].strip()
            if code and name:
                is_st = bool("ST" in name.upper())
                out[code] = {
                    "symbol": code,
                    "name": name,
                    "is_st": is_st,
                    "source": "tencent",
                    "updated_at": now_str,
                }
    return out


def _fetch_eastmoney_batch(symbols: Sequence[str], now_str: str) -> dict[str, dict[str, Any]]:
    """Fallback batch query Eastmoney push2.eastmoney.com."""
    secids: list[str] = []
    for s in symbols:
        pre = to_market_prefix(s)
        if pre.startswith("sh"):
            secids.append("1." + s)
        elif pre.startswith("sz"):
            secids.append("0." + s)
        elif pre.startswith("bj"):
            secids.append("0." + s)
    if not secids:
        return {}

    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f12,f14&secids="
        + ",".join(secids)
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        return {}

    out: dict[str, dict[str, Any]] = {}
    diff = (payload.get("data") or {}).get("diff") or []
    for item in diff:
        code = str(item.get("f12") or "").strip()
        name = str(item.get("f14") or "").strip()
        if code and name:
            is_st = bool("ST" in name.upper())
            out[code] = {
                "symbol": code,
                "name": name,
                "is_st": is_st,
                "source": "eastmoney",
                "updated_at": now_str,
            }
    return out
