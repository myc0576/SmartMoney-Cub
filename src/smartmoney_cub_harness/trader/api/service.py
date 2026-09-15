"""The trader product's service layer: one method per endpoint.

Why this file is separate from the route table: the product's rules live in one
place instead of being spread through HTTP plumbing. Every method takes a
resolved AuthContext first, every reply is wrapped with the execution ban, and
the store is only ever addressed with the caller's own tenant id.

No method accepts a user id, and no argument could name another tenant, so a
request has nowhere to put one. routes.py adapts HTTP onto these methods, which
is why a reviewer can read the product's behavior here without reading the
server.

One production choice is injectable: the market fetcher is replaceable, so the
journal, analytics, backtest, and replay paths can be exercised against recorded
bars with no network.

One ledger implementation: a tenant's stored trades go into the same fill
matcher the review workbench uses, and every metric comes from
smartmoney_cub_harness.analytics, so the journal and the backtester cannot
disagree about what a win rate means.
"""

from __future__ import annotations

import csv
import hashlib
import io
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import quote

from smartmoney_cub_harness import analytics
from smartmoney_cub_harness.fills import build_fill_ledger
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.auth import AuthContext
from smartmoney_cub_harness.trader.backtest import (
    BacktestResult,
    StrategySpec,
    run_backtest,
    validate_strategy,
)
from smartmoney_cub_harness.trader.market import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Bar,
    ProviderResult,
    fetch_bars,
    list_providers,
)
from smartmoney_cub_harness.trader.storage import StoreError, TenantStore

DEFAULT_INITIAL_CASH = 100_000.0

# Analytics reads the tenant's journal in pages this size. A journal larger than
# this is reported as truncated rather than silently averaged over a subset.
MAX_ANALYTICS_TRADES = 10_000

# Replay sessions are ephemeral by design: they hold one bar series for a
# browser to step through, and a restart is expected to lose them. The cap keeps
# a long-lived process from accumulating series without bound.
REPLAY_SESSION_LIMIT = 32
REPLAY_ID_PREFIX = "RPL"

PLAYBOOK_AUDIT_ACTION = "upsert_playbook"
PLAYBOOK_DIMENSIONS = ("tag", "regime")
PLAYBOOK_AUDIT_SCAN = 5_000
PLAYBOOK_ID_PREFIX = "PB"

BAR_FIELDS = ("open_time", "open", "high", "low", "close", "volume")


class TraderRequestError(Exception):
    """A request the product refuses, carrying the status the client should see.

    The route table maps this to an HTTP response, so the service never writes
    an HTTP code itself and the rules stay testable without a socket.
    """

    def __init__(self, message: str, *, status: int = 400, code: str = "bad_request") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def now_iso() -> str:
    """Wall-clock timestamp, matching the store's convention."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def coerce_int(
    value: Any,
    *,
    name: str,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    """Read one integer argument, refusing anything that is not one.

    A bad value is a client error naming the argument, never a silent default: a
    page of the wrong data is worse than a refusal.
    """
    if value is None or value == "":
        value = default
    if value is None:
        return None
    if isinstance(value, bool):
        raise TraderRequestError(f"{name} must be an integer, got {value!r}")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise TraderRequestError(f"{name} must be an integer, got {value!r}") from None
    if minimum is not None and number < minimum:
        raise TraderRequestError(f"{name} must be at least {minimum}, got {number}")
    if maximum is not None and number > maximum:
        raise TraderRequestError(f"{name} must be at most {maximum}, got {number}")
    return number


def coerce_float(value: Any, *, name: str, default: float | None = None) -> float | None:
    """Read one number argument, with the same refusal rule as coerce_int."""
    if value is None or value == "":
        value = default
    if value is None:
        return None
    if isinstance(value, bool):
        raise TraderRequestError(f"{name} must be a number, got {value!r}")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise TraderRequestError(f"{name} must be a number, got {value!r}") from None


def build_tenant_ledger(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build one review ledger from a tenant's stored trades.

    The workbench adapts fills through analytics.build_ledger, which keeps its
    eleven reviewed columns and drops tag annotations. Playbook scoring needs
    those tags, and a stored trade already carries every key the fill matcher
    reads, so the rows go into the same matcher directly. Every metric still
    comes from analytics.summarize, group_performance, and calendar_days, so the
    definition of a win rate or a drawdown stays in one place.
    """
    rows: list[dict[str, Any]] = []
    for trade in trades:
        row = dict(trade)
        # A stored row is a journal execution addressed by its own trade_id, and
        # the matcher addresses a fill by fill_id. Carrying the id across keeps
        # the ledger's fills addressable by the id the tenant imported, so a
        # review can point at the row it read back.
        if not row.get("fill_id") and row.get("trade_id"):
            row["fill_id"] = row["trade_id"]
        rows.append(row)
    return build_fill_ledger(rows)


def parse_delimited_rows(text: str) -> list[dict[str, Any]]:
    """Parse a CSV body into row mappings.

    A tag cell arrives as one field and the store keeps a list, so a delimited
    tag cell is split here rather than landing as a list of characters.
    """
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise TraderRequestError("the CSV body has no header row")
    rows: list[dict[str, Any]] = []
    for raw in reader:
        row: dict[str, Any] = {}
        for key, value in raw.items():
            if key is None:
                continue
            name = str(key).strip()
            if isinstance(value, str):
                value = value.strip()
            if name == "tags" and isinstance(value, str):
                row[name] = [
                    part.strip()
                    for part in value.replace("|", ";").split(";")
                    if part.strip()
                ]
            else:
                row[name] = value
        rows.append(row)
    return rows


def parse_import_payload(
    body: str, *, content_type: str = "", payload: Any = None
) -> tuple[list[dict[str, Any]], str]:
    """Accept the two import shapes the product promises: CSV text or JSON.

    Returns the rows and the format that carried them, so a caller can report
    which one was read instead of leaving a client to guess.
    """
    lowered = (content_type or "").lower()
    text = body or ""
    if payload is None and text.strip():
        if "csv" in lowered or text.lstrip()[:1] not in ("{", "["):
            return parse_delimited_rows(text), "csv"

    if payload is None:
        raise TraderRequestError("the request body is empty")
    if isinstance(payload, list):
        rows: Any = payload
    elif isinstance(payload, Mapping):
        if isinstance(payload.get("csv"), str):
            return parse_delimited_rows(str(payload["csv"])), "csv"
        rows = payload.get("rows")
        if rows is None:
            rows = payload.get("trades")
        if rows is None:
            rows = payload.get("fills")
        if rows is None:
            raise TraderRequestError("the JSON body needs a rows, trades, or fills list")
    else:
        raise TraderRequestError(
            "the import body must be a JSON object or array, or CSV text"
        )

    if not isinstance(rows, list):
        raise TraderRequestError("rows must be a list")
    cleaned: list[dict[str, Any]] = []
    for position, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise TraderRequestError(f"row {position} is not an object")
        cleaned.append(dict(row))
    if not cleaned:
        raise TraderRequestError("no trade rows were supplied")
    return cleaned, "json"


@dataclass
class _ReplaySession:
    """One in-memory replay session, owned by exactly one tenant."""

    user_id: str
    record: dict[str, Any] = field(default_factory=dict)


class TraderService:
    """The trader product's endpoints, one method per endpoint, AuthContext first.

    The service holds no shared journal state, so two tenants can be served by
    one process without sharing a row: every store call carries ctx.user_id, and
    a replay session records its owner and is served only to that owner.
    """

    def __init__(
        self,
        store: TenantStore,
        *,
        auth_mode: str = "local",
        fetch_bars_fn: Callable[..., ProviderResult] | None = None,
    ) -> None:
        self.store = store
        self.auth_mode = str(auth_mode or "local").strip().lower()
        self._fetch_bars = fetch_bars_fn or fetch_bars
        self._replay_lock = threading.Lock()
        self._replay_sessions: dict[str, _ReplaySession] = {}
        # The store is the product's own journal, so its schema is created on
        # open. Both engines make this call idempotent.
        self.store.migrate()

    # ---- helpers -------------------------------------------------------

    def _ensure_tenant(self, ctx: AuthContext) -> dict[str, Any]:
        """Create the tenant row on first write.

        A read works without it (a missing tenant has no rows), but a write
        fails closed in the store on an unknown user, so a write provisions
        first.
        """
        existing = self.store.get_user(ctx.user_id)
        if existing is not None:
            return existing
        return self.store.create_user(
            ctx.user_id, tenant_id=ctx.tenant_id, display_name=ctx.display_name
        )

    def _fills(
        self,
        ctx: AuthContext,
        *,
        account_id: str | None = None,
        symbol: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = MAX_ANALYTICS_TRADES,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """This tenant's trades, filtered. The tenant predicate is the store's."""
        return self.store.list_trades(
            ctx.user_id,
            account_id=account_id,
            symbol=symbol,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )

    def _ledger(self, ctx: AuthContext, **filters: Any) -> dict[str, Any]:
        return build_tenant_ledger(self._fills(ctx, **filters))

    def _resolve_bars(
        self,
        ctx: AuthContext,
        *,
        symbol: str,
        interval: str,
        provider: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
        cached: bool = False,
        inline: Any = None,
    ) -> tuple[list[Bar], dict[str, Any]]:
        """Resolve one bar series for a tenant: inline, cached, or from a provider.

        A fetched series is cached in the tenant's own store together with its
        provider and fetch time, so a replay or a rerun can work offline and a
        review can still say where the bars came from.
        """
        if inline is not None:
            bars = self._inline_bars(inline, symbol=symbol, interval=interval)
            return bars, self._provenance("inline")

        if cached:
            bars = self._cached_bars(
                ctx, symbol=symbol, interval=interval, start=start, end=end, limit=limit
            )
            if not bars:
                raise TraderRequestError(
                    "no cached bars for " + symbol + " " + interval + "; fetch them first"
                )
            return bars, self._provenance("cache")

        if provider:
            result = self._fetch_bars(
                provider, symbol, interval, start=start, end=end, limit=limit
            )
            provenance = {
                "source": "provider",
                "provider_id": result.provider_id,
                "source_quality": result.source_quality,
                "fetched_at": result.fetched_at,
                "warnings": list(result.warnings),
                "cached": self._cache_bars(ctx, result),
            }
            return list(result.bars), provenance

        bars = self._cached_bars(
            ctx, symbol=symbol, interval=interval, start=start, end=end, limit=limit
        )
        if bars:
            return bars, self._provenance("cache")
        raise TraderRequestError(
            "no bars to run on: pass bars, a provider, or cached data"
        )

    @staticmethod
    def _provenance(source: str) -> dict[str, Any]:
        return {
            "source": source,
            "provider_id": "",
            "source_quality": "",
            "fetched_at": "",
            "warnings": [],
        }

    def _inline_bars(self, raw: Any, *, symbol: str, interval: str) -> list[Bar]:
        if not isinstance(raw, list) or not raw:
            raise TraderRequestError("bars must be a non-empty list")
        bars: list[Bar] = []
        for position, item in enumerate(raw):
            if not isinstance(item, Mapping):
                raise TraderRequestError(f"bars[{position}] is not an object")
            missing = [name for name in BAR_FIELDS if item.get(name) in (None, "")]
            if missing:
                raise TraderRequestError(
                    f"bars[{position}] is missing " + ", ".join(missing)
                )
            try:
                bars.append(
                    Bar(
                        symbol=str(item.get("symbol") or symbol),
                        interval=str(item.get("interval") or interval),
                        open_time=str(item["open_time"]),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=float(item["volume"]),
                    )
                )
            except (TypeError, ValueError):
                raise TraderRequestError(
                    f"bars[{position}] has a non-numeric price or volume"
                ) from None
        return bars

    def _cached_bars(
        self,
        ctx: AuthContext,
        *,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> list[Bar]:
        """This tenant's cached bars, read back through the store's own scope."""
        rows = self.store.load_bars(
            ctx.user_id, symbol=symbol, interval=interval, start=start, end=end, limit=limit
        )
        return [
            Bar(
                symbol=str(row["symbol"]),
                interval=str(row["interval"]),
                open_time=str(row["open_time"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for row in rows
        ]

    def _cache_bars(self, ctx: AuthContext, result: ProviderResult) -> bool:
        """Cache a fetched series. A cache failure never fails the fetch."""
        if not result.bars:
            return False
        try:
            self._ensure_tenant(ctx)
            self.store.save_bars(
                ctx.user_id,
                [
                    {
                        **bar.to_dict(),
                        "provider": result.provider_id,
                        "fetched_at": result.fetched_at,
                    }
                    for bar in result.bars
                ],
            )
        except (StoreError, TypeError, ValueError):
            return False
        return True

    # ---- liveness and metadata -----------------------------------------

    def health(self, ctx: AuthContext) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "trader",
            "auth_mode": self.auth_mode,
            "user_id": ctx.user_id,
            "tenant_id": ctx.tenant_id,
            "safety": SAFETY_DECLARATION,
        }

    def meta(self, ctx: AuthContext) -> dict[str, Any]:
        return {
            "status": "ok",
            "app": "smartmoney-cub-trader",
            "tenant": {
                "user_id": ctx.user_id,
                "tenant_id": ctx.tenant_id,
                "display_name": ctx.display_name,
                "mode": ctx.mode,
            },
            "auth_mode": self.auth_mode,
            "storage_engine": getattr(self.store, "engine", "unknown"),
            "market_data_mode": "on_demand",
            "capabilities": [
                "journal",
                "analytics",
                "market_data",
                "backtest",
                "replay",
                "playbooks",
            ],
            "safety": SAFETY_DECLARATION,
        }

    # ---- market data ---------------------------------------------------

    def market_providers(self, ctx: AuthContext) -> dict[str, Any]:
        providers = list_providers()
        return {
            "status": "ok",
            "count": len(providers),
            "providers": providers,
            "safety": SAFETY_DECLARATION,
        }

    def market_bars(
        self,
        ctx: AuthContext,
        *,
        provider: str,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> dict[str, Any]:
        """Fetch one series on demand and cache it in this tenant's store."""
        if not provider:
            raise TraderRequestError("provider is required")
        if not symbol:
            raise TraderRequestError("symbol is required")
        if not interval:
            raise TraderRequestError("interval is required")
        result = self._fetch_bars(
            provider, symbol, interval, start=start, end=end, limit=limit
        )
        payload = dict(result.to_dict())
        payload["status"] = "ok"
        payload["cached"] = self._cache_bars(ctx, result)
        payload["safety"] = SAFETY_DECLARATION
        return payload

    # ---- journal -------------------------------------------------------

    def list_trades(
        self,
        ctx: AuthContext,
        *,
        account_id: str | None = None,
        symbol: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> dict[str, Any]:
        """This tenant's journal: their fills, and the round trips they close.

        Round trips are matched inside the tenant's own page of trades, which is
        why another tenant's round_trip_id cannot appear here: the matcher never
        sees another tenant's rows.
        """
        fills = self._fills(
            ctx,
            account_id=account_id,
            symbol=symbol,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
        ledger = build_tenant_ledger(fills)
        return {
            "status": "ok",
            "count": len(ledger["round_trips"]),
            "trades": ledger["round_trips"],
            "fills": ledger["fills"],
            "open_positions": ledger["open_positions"],
            "issues": ledger["issues"],
            "ledger_status": ledger["status"],
            "filters": {
                "account_id": account_id or "",
                "symbol": symbol or "",
                "from": start or "",
                "to": end or "",
                "limit": limit,
                "offset": offset,
            },
            "safety": SAFETY_DECLARATION,
        }

    def get_trade(self, ctx: AuthContext, round_trip_id: str) -> dict[str, Any]:
        """One round trip, matched inside this tenant's own ledger."""
        if not round_trip_id:
            raise TraderRequestError("a round trip id is required")
        ledger = self._ledger(ctx)
        trip = next(
            (
                item
                for item in ledger["round_trips"]
                if item["round_trip_id"] == round_trip_id
            ),
            None,
        )
        if trip is None:
            raise TraderRequestError(
                f"no round trip {round_trip_id!r} for this tenant",
                status=404,
                code="not_found",
            )
        return {
            "status": "ok",
            "trade": trip,
            "issues": [
                issue
                for issue in ledger["issues"]
                if issue.get("symbol") == trip["symbol"]
            ],
            "safety": SAFETY_DECLARATION,
        }

    def import_trades(
        self,
        ctx: AuthContext,
        *,
        rows: Sequence[Mapping[str, Any]],
        source_format: str = "json",
    ) -> dict[str, Any]:
        """Import the tenant's own executions. Re-importing a trade corrects it."""
        if not rows:
            raise TraderRequestError("no trade rows were supplied")
        self._ensure_tenant(ctx)
        payload = dict(self.store.insert_trades(ctx.user_id, rows))
        payload["status"] = "ok"
        payload["format"] = source_format
        payload["submitted_count"] = len(rows)
        payload["safety"] = SAFETY_DECLARATION
        return payload

    # ---- accounts ------------------------------------------------------

    def list_accounts(self, ctx: AuthContext) -> dict[str, Any]:
        accounts = self.store.list_accounts(ctx.user_id)
        return {
            "status": "ok",
            "count": len(accounts),
            "accounts": accounts,
            "safety": SAFETY_DECLARATION,
        }

    def upsert_account(self, ctx: AuthContext, account: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(account, Mapping):
            raise TraderRequestError("the request body must be a JSON object")
        has_name = bool(str(account.get("name") or "").strip())
        has_id = bool(str(account.get("account_id") or "").strip())
        if not has_name and not has_id:
            raise TraderRequestError("an account needs a name or an account_id")
        self._ensure_tenant(ctx)
        record = self.store.upsert_account(ctx.user_id, account)
        return {"status": "ok", "account": record, "safety": SAFETY_DECLARATION}

    # ---- analytics -----------------------------------------------------

    def analytics_summary(
        self,
        ctx: AuthContext,
        *,
        start: str | None = None,
        end: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        ledger = self._ledger(ctx, start=start, end=end, account_id=account_id)
        return {
            "status": "ok",
            "summary": analytics.summarize(ledger),
            "counts": ledger["counts"],
            "ledger_status": ledger["status"],
            "filters": {
                "from": start or "",
                "to": end or "",
                "account_id": account_id or "",
            },
            "safety": SAFETY_DECLARATION,
        }

    def analytics_breakdown(
        self,
        ctx: AuthContext,
        *,
        dimension: str | None = None,
        start: str | None = None,
        end: str | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        requested = [dimension] if dimension else list(analytics.DIMENSIONS)
        unknown = sorted({name for name in requested if name not in analytics.DIMENSIONS})
        if unknown:
            raise TraderRequestError(
                "unknown dimension "
                + ", ".join(unknown)
                + "; known dimensions: "
                + ", ".join(analytics.DIMENSIONS)
            )
        ledger = self._ledger(ctx, start=start, end=end)
        symbol_meta: dict[str, dict[str, Any]] = {}
        if "symbol" in requested:
            symbols = list({
                trip["symbol"]
                for trip in ledger.get("round_trips") or []
                if trip.get("symbol")
            })
            load_fn = getattr(self.store, "load_symbol_metadata", None)
            if callable(load_fn):
                symbol_meta = load_fn(symbols)
            missing = [s for s in symbols if s not in symbol_meta or not symbol_meta[s].get("name")]
            to_fetch = symbols if refresh else missing
            if to_fetch:
                try:
                    from smartmoney_cub_harness.trader.market.symbols import fetch_symbol_metadata

                    fresh = fetch_symbol_metadata(to_fetch)
                    if fresh:
                        save_fn = getattr(self.store, "save_symbol_metadata", None)
                        if callable(save_fn):
                            save_fn(list(fresh.values()))
                        update_fn = getattr(self.store, "update_trade_names", None)
                        if callable(update_fn):
                            update_fn(ctx.user_id, {s: v["name"] for s, v in fresh.items()}, force=refresh)
                        symbol_meta.update(fresh)
                except Exception:
                    pass

        return {
            "status": "ok",
            "dimension": dimension or "all",
            "breakdown": {
                name: analytics.group_performance(
                    ledger,
                    dimension=name,
                    symbol_names=symbol_meta if name == "symbol" else None,
                )
                for name in requested
            },
            "symbol_meta": symbol_meta,
            "dimensions": list(analytics.DIMENSIONS),
            "filters": {"from": start or "", "to": end or ""},
            "safety": SAFETY_DECLARATION,
        }

    def calendar(
        self, ctx: AuthContext, *, year: int | None = None, month: int | None = None
    ) -> dict[str, Any]:
        today = datetime.now(timezone.utc).astimezone()
        resolved_year = year or today.year
        resolved_month = month or today.month
        if not 1 <= resolved_month <= 12:
            raise TraderRequestError("month must be between 1 and 12")
        ledger = self._ledger(ctx)
        return {
            "status": "ok",
            "year": resolved_year,
            "month": resolved_month,
            "days": analytics.calendar_days(
                ledger, year=resolved_year, month=resolved_month
            ),
            "safety": SAFETY_DECLARATION,
        }

    # ---- playbooks -----------------------------------------------------

    def _playbook_definitions(self, ctx: AuthContext) -> dict[str, dict[str, Any]]:
        """Read this tenant's declared playbooks, the newest declaration winning.

        The v1 store has no playbooks table, so a declaration is written to the
        tenant's own append-only audit trail and read back from it. The read is
        defensive: a store without that query falls back to journal-derived
        playbooks instead of failing.
        """
        reader = getattr(self.store, "list_audit", None)
        if reader is None:
            return {}
        try:
            entries = reader(ctx.user_id, limit=PLAYBOOK_AUDIT_SCAN)
        except (StoreError, TypeError, ValueError):
            return {}
        definitions: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if str(entry.get("action") or "") != PLAYBOOK_AUDIT_ACTION:
                continue
            detail = entry.get("detail")
            if not isinstance(detail, Mapping):
                continue
            playbook_id = str(entry.get("record_id") or detail.get("playbook_id") or "")
            if not playbook_id or playbook_id in definitions:
                continue
            definitions[playbook_id] = {
                **{key: value for key, value in detail.items()},
                "updated_at": str(entry.get("created_at") or ""),
            }
        return definitions

    @staticmethod
    def _playbook_id(dimension: str, key: str) -> str:
        return PLAYBOOK_ID_PREFIX + "-" + dimension + "-" + quote(key, safe="_-")

    def _journal_playbooks(self, ctx: AuthContext) -> dict[str, dict[str, Any]]:
        """Playbooks observed in this tenant's own journal, scored by analytics."""
        ledger = self._ledger(ctx)
        found: dict[str, dict[str, Any]] = {}
        for dimension in PLAYBOOK_DIMENSIONS:
            for row in analytics.group_performance(ledger, dimension=dimension):
                key = str(row["key"])
                found[self._playbook_id(dimension, key)] = {
                    "name": key,
                    "dimension": dimension,
                    "key": key,
                    "trade_count": row["trade_count"],
                    "win_rate": row["win_rate"],
                    "net_pnl": row["net_pnl"],
                    "avg_return_pct": row["avg_return_pct"],
                    "profit_factor": row["profit_factor"],
                    "small_sample": row["small_sample"],
                }
        return found

    def playbooks(self, ctx: AuthContext) -> dict[str, Any]:
        """Declared playbooks, each scored against this tenant's own journal."""
        journal = self._journal_playbooks(ctx)
        definitions = self._playbook_definitions(ctx)
        records: list[dict[str, Any]] = []
        for playbook_id, detail in sorted(definitions.items()):
            key = str(detail.get("key") or "")
            stats = journal.get(playbook_id, {})
            records.append(
                {
                    "playbook_id": playbook_id,
                    "name": str(detail.get("name") or key or playbook_id),
                    "dimension": str(detail.get("dimension") or ""),
                    "key": key,
                    "description": str(detail.get("description") or ""),
                    "rules": list(detail.get("rules") or []),
                    "defined": True,
                    "updated_at": str(detail.get("updated_at") or ""),
                    "trade_count": stats.get("trade_count", 0),
                    "win_rate": stats.get("win_rate", 0.0),
                    "net_pnl": stats.get("net_pnl", 0.0),
                    "avg_return_pct": stats.get("avg_return_pct", 0.0),
                    "profit_factor": stats.get("profit_factor"),
                    "small_sample": stats.get("small_sample", True),
                    "has_journal_data": bool(stats),
                }
            )
        declared = set(definitions)
        for playbook_id, stats in sorted(
            journal.items(), key=lambda item: (-item[1]["trade_count"], item[0])
        ):
            if playbook_id in declared:
                continue
            records.append(
                {
                    "playbook_id": playbook_id,
                    "name": stats["name"],
                    "dimension": stats["dimension"],
                    "key": stats["key"],
                    "description": "",
                    "rules": [],
                    "defined": False,
                    "updated_at": "",
                    "trade_count": stats["trade_count"],
                    "win_rate": stats["win_rate"],
                    "net_pnl": stats["net_pnl"],
                    "avg_return_pct": stats["avg_return_pct"],
                    "profit_factor": stats["profit_factor"],
                    "small_sample": stats["small_sample"],
                    "has_journal_data": True,
                }
            )
        return {
            "status": "ok",
            "count": len(records),
            "playbooks": records,
            "definitions": len(definitions),
            "dimensions": list(PLAYBOOK_DIMENSIONS),
            "scoring": "analytics.group_performance over the tenant's own ledger",
            "safety": SAFETY_DECLARATION,
        }

    def upsert_playbook(
        self, ctx: AuthContext, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Declare one playbook for this tenant and return its scored view."""
        if not isinstance(payload, Mapping):
            raise TraderRequestError("the request body must be a JSON object")
        name = str(payload.get("name") or "").strip()
        dimension = str(payload.get("dimension") or "tag").strip() or "tag"
        key = str(payload.get("key") or "").strip()
        if dimension not in PLAYBOOK_DIMENSIONS:
            raise TraderRequestError(
                "dimension must be one of " + ", ".join(PLAYBOOK_DIMENSIONS)
            )
        if not name and not key:
            raise TraderRequestError("a playbook needs a name or a key")
        key = key or name
        name = name or key
        playbook_id = str(payload.get("playbook_id") or "").strip() or self._playbook_id(
            dimension, key
        )
        rules = payload.get("rules") or []
        if not isinstance(rules, list):
            raise TraderRequestError("rules must be a list")
        detail = {
            "playbook_id": playbook_id,
            "name": name,
            "dimension": dimension,
            "key": key,
            "description": str(payload.get("description") or "").strip(),
            "rules": rules,
        }
        self._ensure_tenant(ctx)
        self.store.audit(
            ctx.user_id, PLAYBOOK_AUDIT_ACTION, record_id=playbook_id, detail=detail
        )
        view = next(
            (
                record
                for record in self.playbooks(ctx)["playbooks"]
                if record["playbook_id"] == playbook_id
            ),
            None,
        )
        return {
            "status": "ok",
            "playbook": view or {**detail, "defined": True},
            "safety": SAFETY_DECLARATION,
        }

    # ---- backtest ------------------------------------------------------

    def backtest_run(self, ctx: AuthContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a strategy, resolve its bars, run it, and save the run.

        Nothing here executes caller-supplied code: the strategy is data
        validated against the frozen DSL, and the engine is a closed dispatch
        over the same vocabulary.
        """
        if not isinstance(payload, Mapping):
            raise TraderRequestError("the request body must be a JSON object")
        strategy_payload = payload.get("strategy")
        if strategy_payload is None:
            raise TraderRequestError("strategy is required")
        if not isinstance(strategy_payload, Mapping):
            raise TraderRequestError("strategy must be a JSON object")
        spec: StrategySpec = validate_strategy(strategy_payload)

        data = payload.get("data") or {}
        if not isinstance(data, Mapping):
            raise TraderRequestError("data must be a JSON object")
        symbol = str(data.get("symbol") or spec.universe.symbol)
        interval = str(data.get("interval") or spec.universe.interval)
        inline = data.get("bars") if data.get("bars") is not None else payload.get("bars")
        provider = data.get("provider") or payload.get("provider")
        limit = coerce_int(
            data.get("limit") if data.get("limit") is not None else payload.get("limit"),
            name="limit",
            default=DEFAULT_LIMIT,
            minimum=1,
            maximum=MAX_LIMIT,
        )
        initial_cash = coerce_float(
            payload.get("initial_cash"), name="initial_cash", default=DEFAULT_INITIAL_CASH
        )
        if initial_cash is None or initial_cash <= 0:
            raise TraderRequestError("initial_cash must be a positive number")
        fees_bps = coerce_float(payload.get("fees_bps"), name="fees_bps", default=0.0)
        slippage_bps = coerce_float(
            payload.get("slippage_bps"), name="slippage_bps", default=0.0
        )

        bars, provenance = self._resolve_bars(
            ctx,
            symbol=symbol,
            interval=interval,
            provider=str(provider) if provider else None,
            start=data.get("start") or payload.get("start"),
            end=data.get("end") or payload.get("end"),
            limit=limit or DEFAULT_LIMIT,
            cached=bool(data.get("cached")),
            inline=inline,
        )
        if not bars:
            raise TraderRequestError("the bar series is empty; nothing to run")

        result: BacktestResult = run_backtest(
            spec,
            bars,
            initial_cash=float(initial_cash),
            fees_bps=float(fees_bps or 0.0),
            slippage_bps=float(slippage_bps or 0.0),
        )
        result_payload = result.to_dict()
        should_save = payload.get("save") is not False
        run_id = ""
        if should_save:
            run_id = self._save_run(ctx, spec=spec, result_payload=result_payload)
        return {
            "status": "ok",
            "run_id": run_id,
            "saved": bool(run_id),
            "data": {
                "symbol": symbol,
                "interval": interval,
                "bar_count": len(bars),
                "provenance": provenance,
            },
            "result": result_payload,
            "safety": SAFETY_DECLARATION,
        }

    def _save_run(
        self,
        ctx: AuthContext,
        *,
        spec: StrategySpec,
        result_payload: Mapping[str, Any],
    ) -> str:
        """Persist one run for this tenant, storing the canonical spec."""
        self._ensure_tenant(ctx)
        saved = self.store.save_backtest_run(
            ctx.user_id,
            {
                "strategy_name": spec.name,
                "symbol": spec.universe.symbol,
                "interval": spec.universe.interval,
                "started_at": now_iso(),
                "metrics": result_payload.get("metrics") or {},
                "equity_curve": result_payload.get("equity_curve") or [],
                "spec": spec.to_dict(),
            },
        )
        return str(saved.get("run_id") or "")

    def backtest_runs(self, ctx: AuthContext, *, limit: int = 100) -> dict[str, Any]:
        runs = self.store.list_backtest_runs(ctx.user_id, limit=limit)
        return {
            "status": "ok",
            "count": len(runs),
            "runs": [
                {
                    "run_id": run["run_id"],
                    "strategy_name": run["strategy_name"],
                    "symbol": run["symbol"],
                    "interval": run["interval"],
                    "started_at": run["started_at"],
                    "created_at": run["created_at"],
                    "metrics": run["metrics"],
                }
                for run in runs
            ],
            "safety": SAFETY_DECLARATION,
        }

    def backtest_run_detail(self, ctx: AuthContext, run_id: str) -> dict[str, Any]:
        if not run_id:
            raise TraderRequestError("a run id is required")
        runs = self.store.list_backtest_runs(ctx.user_id, limit=1_000)
        run = next((item for item in runs if item["run_id"] == run_id), None)
        if run is None:
            raise TraderRequestError(
                f"no backtest run {run_id!r} for this tenant",
                status=404,
                code="not_found",
            )
        return {"status": "ok", "run": run, "safety": SAFETY_DECLARATION}

    # ---- replay --------------------------------------------------------

    def create_replay_session(
        self, ctx: AuthContext, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Hold one bar series for this tenant to step through."""
        if not isinstance(payload, Mapping):
            raise TraderRequestError("the request body must be a JSON object")
        symbol = str(payload.get("symbol") or "").strip()
        interval = str(payload.get("interval") or "").strip()
        if not symbol or not interval:
            raise TraderRequestError("symbol and interval are required")
        limit = coerce_int(
            payload.get("limit"),
            name="limit",
            default=DEFAULT_LIMIT,
            minimum=1,
            maximum=MAX_LIMIT,
        )
        bars, provenance = self._resolve_bars(
            ctx,
            symbol=symbol,
            interval=interval,
            provider=str(payload.get("provider") or "") or None,
            start=payload.get("start"),
            end=payload.get("end"),
            limit=limit or DEFAULT_LIMIT,
            cached=bool(payload.get("cached")),
            inline=payload.get("bars"),
        )
        if not bars:
            raise TraderRequestError("the bar series is empty; nothing to replay")
        index = coerce_int(
            payload.get("index"), name="index", default=0, minimum=0, maximum=len(bars) - 1
        )
        session_id = self._new_session_id()
        record: dict[str, Any] = {
            "session_id": session_id,
            "symbol": symbol,
            "interval": interval,
            "source": provenance["source"],
            "provider_id": provenance.get("provider_id", ""),
            "source_quality": provenance.get("source_quality", ""),
            "fetched_at": provenance.get("fetched_at", ""),
            "warnings": list(provenance.get("warnings") or []),
            "created_at": now_iso(),
            "frame_count": len(bars),
            "index": index or 0,
            "bars": [bar.to_dict() for bar in bars],
        }
        session = _ReplaySession(user_id=ctx.user_id, record=record)
        with self._replay_lock:
            self._replay_sessions[session_id] = session
            while len(self._replay_sessions) > REPLAY_SESSION_LIMIT:
                oldest = next(iter(self._replay_sessions))
                self._replay_sessions.pop(oldest, None)
        return {
            "status": "ok",
            "session": {**record, "ephemeral": True},
            "safety": SAFETY_DECLARATION,
        }

    def replay_session(
        self, ctx: AuthContext, session_id: str, *, index: int | None = None
    ) -> dict[str, Any]:
        """Return one replay session, stepped to an optional frame index.

        A session owned by another tenant is reported as missing rather than
        forbidden: the answer must not confirm that an id exists elsewhere.
        """
        if not session_id:
            raise TraderRequestError("a session id is required")
        with self._replay_lock:
            session = self._replay_sessions.get(session_id)
        if session is None or session.user_id != ctx.user_id:
            raise TraderRequestError(
                "no such replay session for this tenant",
                status=404,
                code="not_found",
            )
        record = dict(session.record)
        frame: dict[str, Any] | None = None
        if index is not None:
            bars = record.get("bars") or []
            if index < 0 or index >= len(bars):
                raise TraderRequestError(
                    "index must be between 0 and " + str(max(len(bars) - 1, 0))
                )
            record["index"] = index
            with self._replay_lock:
                session.record["index"] = index
            frame = bars[index]
        return {
            "status": "ok",
            "session": record,
            "frame": frame,
            "ephemeral": True,
            "safety": SAFETY_DECLARATION,
        }

    def _new_session_id(self) -> str:
        with self._replay_lock:
            counter = len(self._replay_sessions)
        token = hashlib.sha256(
            (now_iso() + ":" + str(counter)).encode("utf-8")
        ).hexdigest()[:12]
        return REPLAY_ID_PREFIX + "-" + token
