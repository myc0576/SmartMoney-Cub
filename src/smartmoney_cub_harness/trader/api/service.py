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
import math
import threading
from pathlib import Path
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
from smartmoney_cub_harness.trader.replay import create_record, public_view, apply_action

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

# Readable names for the deterministic mistake triggers, so the interface can
# report the ones that found nothing without hard-coding a second copy of the
# vocabulary. The keys match the clustering module's CLUSTER_KINDS.
_CLUSTER_LABELS = {
    "broken_invalidation_unstopped": "跌破止损线未离场",
    "early_morning_exit": "开盘 15 分钟内平仓",
    "one_day_holding": "持仓仅 1 日",
    "revenge_reentry": "亏损后 10 分钟内再次开仓",
}

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
        number = float(value)
        if not math.isfinite(number):
            raise ValueError()
        return number
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
    return build_fill_ledger(rows, market="UNKNOWN", allow_shorts=True)


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
        connection_root: str | Path | None = None,
        connection_factory: Callable | None = None,
    ) -> None:
        self.store = store
        self.auth_mode = str(auth_mode or "local").strip().lower()
        self._fetch_bars = fetch_bars_fn or fetch_bars
        self._replay_lock = threading.RLock()
        # The store is the product's own journal, so its schema is created on
        # open. Both engines make this call idempotent.
        self.store.migrate()
        from smartmoney_cub_harness.trader.connections.controller import ConnectionController
        database_path = getattr(store, "database_path", None)
        inferred_root = Path(database_path).parent / "connections" if database_path and str(database_path) != ":memory:" else None
        self.connections = ConnectionController(self, Path(connection_root) if connection_root else inferred_root, connection_factory)
        self.connections.resume_local_watch()

    def close(self) -> None:
        self.connections.close()

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
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Read the complete matching history, not just the newest fill page.

        A ledger needs the older opening fills to match newer closes. Explicit
        limits are only for callers requesting a bounded raw-fill page.
        """
        filters = dict(account_id=account_id, symbol=symbol, start=start, end=end)
        if limit is not None:
            return self.store.list_trades(ctx.user_id, **filters, limit=limit, offset=offset)
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        while True:
            page = self.store.list_trades(ctx.user_id, **filters, limit=MAX_ANALYTICS_TRADES, offset=offset)
            for row in page:
                identity = str(row['trade_id'])
                if identity in seen:
                    raise TraderRequestError('journal_changed_during_read; retry after synchronization completes')
                seen.add(identity)
            rows.extend(page)
            if len(page) < MAX_ANALYTICS_TRADES:
                return rows
            offset += len(page)

    def _ledger(self, ctx: AuthContext, **filters: Any) -> dict[str, Any]:
        start = filters.pop("start", None)
        ledger = build_tenant_ledger(self._fills(ctx, **filters))
        return self._closed_window(ledger, start)

    @staticmethod
    def _closed_window(ledger: dict[str, Any], start: str | None) -> dict[str, Any]:
        # Openings before a report window still establish the closing cost basis.
        # Filter completed trips only after matching the account's full history.
        if start:
            ledger["round_trips"] = [trip for trip in ledger["round_trips"]
                                     if str(trip.get("exit_time") or "")[:10] >= start[:10]]
            ledger["counts"] = {**ledger["counts"], "round_trips": len(ledger["round_trips"])}
        return ledger

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
            return bars, self._cached_provenance(ctx, symbol, interval)

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
                "available_at": result.available_at,
                "decision_time": result.decision_time,
                "historical_evidence": result.historical_evidence,
                "cached": self._cache_bars(ctx, result),
            }
            return list(result.bars), provenance

        bars = self._cached_bars(
            ctx, symbol=symbol, interval=interval, start=start, end=end, limit=limit
        )
        if bars:
            return bars, self._cached_provenance(ctx, symbol, interval)
        raise TraderRequestError(
            "no bars to run on: pass bars, a provider, or cached data"
        )

    @staticmethod
    def _provenance(source: str) -> dict[str, Any]:
        return {
            "source": source,
            "provider_id": "",
            "source_quality": "unverified",
            "fetched_at": "",
            "warnings": [],
            "available_at": None,
            "decision_time": None,
            "historical_evidence": "unverified",
        }

    def _cached_provenance(self, ctx: AuthContext, symbol: str, interval: str) -> dict[str, Any]:
        document = self.store.get_document(ctx.user_id, "bar_provenance", symbol + ":" + interval)
        record = document["payload"] if document else None
        return {**(record or self._provenance("cache")), "source": "cache"}

    def _inline_bars(self, raw: Any, *, symbol: str, interval: str) -> list[Bar]:
        if not isinstance(raw, list) or not raw:
            raise TraderRequestError("bars must be a non-empty list")
        bars: list[Bar] = []
        for position, item in enumerate(raw):
            if not isinstance(item, Mapping):
                raise TraderRequestError(f"bars[{position}] is not an object")
            if item.get("available_at") and item.get("decision_time"):
                try:
                    available = datetime.fromisoformat(str(item["available_at"]).replace("Z", "+00:00"))
                    decision = datetime.fromisoformat(str(item["decision_time"]).replace("Z", "+00:00"))
                    if available > decision:
                        raise TraderRequestError("available_at is later than decision_time")
                except (ValueError, TypeError):
                    raise TraderRequestError("availability timestamps must have comparable timezone precision") from None
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
            self.store.put_document(ctx.user_id, "bar_provenance", result.symbol + ":" + result.interval, {
                "source": "provider", "provider_id": result.provider_id,
                "source_quality": result.source_quality, "fetched_at": result.fetched_at,
                "available_at": result.available_at, "decision_time": result.decision_time,
                "historical_evidence": result.historical_evidence,
                "metadata_scope": "latest_fetch", "warnings": list(result.warnings),
            })
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

        Paging applies to the ROUND TRIPS, not to the fills behind them, and the
        difference decides whether the list works. A round trip is produced by
        matching a buy against a later sell, so a page of N fills closes fewer
        than N round trips, and a page of the newest fills closes almost none
        because the sells sit further back. Reading the newest 24 fills and
        calling the result the newest trades reported zero trades over a journal
        holding hundreds -- which is exactly what the overview page showed.

        So the ledger is built from the whole filtered window and the page is
        taken from the matched round trips. The offset follows the same rule. The
        filters still restrict the rows the matcher sees, so another tenant's
        round trip still cannot appear here.
        """
        fills = self._fills(
            ctx,
            account_id=account_id,
            symbol=symbol,
            start=None,
            end=end,
        )
        ledger = self._closed_window(build_tenant_ledger(fills), start)
        # Newest close first: the interface lists recent activity, and a page
        # taken from the front of a chronological ledger would be the oldest.
        trips = sorted(
            ledger["round_trips"],
            key=lambda trip: str(trip.get("exit_time") or ""),
            reverse=True,
        )
        page = trips[offset:offset + limit] if limit > 0 else []
        return {
            "status": "ok",
            "count": len(trips),
            "trades": page,
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
        account_id: str | None = None,
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
        ledger = self._ledger(ctx, start=start, end=end, account_id=account_id)
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
        self, ctx: AuthContext, *, year: int | None = None, month: int | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        today = datetime.now(timezone.utc).astimezone()
        resolved_year = year or today.year
        resolved_month = month or today.month
        if not 1 <= resolved_month <= 12:
            raise TraderRequestError("month must be between 1 and 12")
        ledger = self._ledger(ctx, account_id=account_id)
        return {
            "status": "ok",
            "year": resolved_year,
            "month": resolved_month,
            "days": analytics.calendar_days(
                ledger, year=resolved_year, month=resolved_month
            ),
            "safety": SAFETY_DECLARATION,
        }

    # ---- insight --------------------------------------------------------

    def insight_mistakes(
        self,
        ctx: AuthContext,
        *,
        start: str | None = None,
        end: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        trades = self._fills(ctx, end=end, account_id=account_id)
        ledger = self._closed_window(build_tenant_ledger(trades), start)
        from smartmoney_cub_harness.trader.insight import (  # noqa: PLC0415
            CLUSTER_KINDS,
            cluster_mistakes,
        )

        clusters = cluster_mistakes(ledger, trades=trades)
        # The clustering module reports the FILLS behind a cluster, because that
        # is where its trigger is evaluated. A reader clicking an entry needs the
        # round trip, which is what the detail route can address, so the closed
        # trips that carry any of those fills are resolved here and exposed beside
        # the fill ids. Both are sent: the fills are the evidence, the round trips
        # are the way in.
        fills_to_trip: dict[str, str] = {}
        for trip in ledger["round_trips"]:
            trip_id = str(trip.get("round_trip_id") or "")
            if not trip_id:
                continue
            for lot in trip.get("matched_lots") or []:
                fill_id = str(lot.get("lot_fill_id") or "")
                if fill_id:
                    fills_to_trip[fill_id] = trip_id
        matched: dict[str, int] = {kind: 0 for kind in CLUSTER_KINDS}
        for cluster in clusters:
            kind = str(cluster.get("kind") or "")
            if kind in matched:
                matched[kind] = int(cluster.get("count") or 0)
            cluster["label"] = str(cluster.get("label_seed") or kind)
            cluster["round_trip_ids"] = sorted({
                fills_to_trip[fill_id]
                for fill_id in cluster.get("trade_ids") or []
                if fill_id in fills_to_trip
            })
        return {
            "status": "ok",
            "count": len(clusters),
            "rows": clusters,
            # The triggers that were evaluated and found nothing are reported too.
            # A scan that lists only its hits cannot be told from a scan that never
            # ran, and "my journal is clean" is a claim that needs the second.
            "triggers": [
                {
                    "kind": kind,
                    "label": _CLUSTER_LABELS.get(kind, kind),
                    "matched": matched.get(kind, 0),
                }
                for kind in CLUSTER_KINDS
            ],
            "filters": {
                "from": start or "",
                "to": end or "",
                "account_id": account_id or "",
            },
            "safety": SAFETY_DECLARATION,
        }

    def insight_edges(
        self,
        ctx: AuthContext,
        *,
        start: str | None = None,
        end: str | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        trades = self._fills(ctx, end=end, account_id=account_id)
        ledger = self._closed_window(build_tenant_ledger(trades), start)
        from smartmoney_cub_harness.trader.insight import EDGE_DIMENSIONS, extract_edges

        edges = extract_edges(ledger)
        return {
            "status": "ok",
            "count": len(edges),
            "rows": edges,
            "dimensions": list(EDGE_DIMENSIONS),
            "filters": {
                "from": start or "",
                "to": end or "",
                "account_id": account_id or "",
            },
            "safety": SAFETY_DECLARATION,
        }

    # ---- playbooks -----------------------------------------------------

    def insight_patterns(self, ctx: AuthContext, *, account_id: str | None = None,
                         start: str | None = None, end: str | None = None) -> dict[str, Any]:
        from smartmoney_cub_harness.trader.patterns import attribute_patterns
        trades = self._fills(ctx, account_id=account_id, end=end)
        result = attribute_patterns(self._closed_window(build_tenant_ledger(trades), start), trades=trades)
        decisions = {row["document_id"]: row["payload"] for row in
                     self.store.list_documents(ctx.user_id, "pattern_decision", limit=MAX_ANALYTICS_TRADES * 4)}
        for candidate in result["candidates"]:
            decision = decisions.get(candidate["pattern_id"])
            if not decision:
                continue
            candidate["decision"] = decision
            candidate["original_label"] = candidate["label"]
            if decision.get("label"):
                candidate["label"] = decision["label"]
            if decision.get("state") in ("confirmed", "rejected"):
                candidate["status"] = decision["state"]
        return {"status": "ok", **result, "filters": {"account_id": account_id, "from": start, "to": end},
                "truncated": False}

    def decide_pattern(self, ctx: AuthContext, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise TraderRequestError("the request body must be a JSON object")
        pattern_id, action = str(payload.get("pattern_id") or ""), str(payload.get("action") or "")
        if action not in ("confirm", "reject", "rename"):
            raise TraderRequestError("action must be confirm, reject, or rename")
        candidate = next((item for item in self.insight_patterns(ctx)["candidates"] if item["pattern_id"] == pattern_id), None)
        if candidate is None:
            raise TraderRequestError("no current pattern candidate for this tenant", status=404, code="not_found")
        label = str(payload.get("label") or "").strip()
        if action == "rename" and not label:
            raise TraderRequestError("rename requires a nonempty label")
        if len(label) > 120:
            raise TraderRequestError("label must be no longer than 120 characters")
        playbook_id = str(payload.get("playbook_id") or "").strip()
        if playbook_id and playbook_id not in self._playbook_definitions(ctx):
            raise TraderRequestError("playbook must be declared in this tenant's journal")
        previous = candidate.get("decision") or {}
        state = {"confirm": "confirmed", "reject": "rejected"}.get(action, previous.get("state", "unconfirmed"))
        decision = {"pattern_id": pattern_id, "action": action, "state": state,
                    "label": label or previous.get("label") or candidate["label"],
                    "playbook_id": playbook_id or previous.get("playbook_id"),
                    "updated_at": now_iso(), "evidence_version": candidate["version"],
                    "round_trip_id": candidate["round_trip_id"], "safety": SAFETY_DECLARATION}
        self._ensure_tenant(ctx)
        self.store.put_document(ctx.user_id, "pattern_decision", pattern_id, decision)
        self.store.audit(ctx.user_id, "pattern_" + action, record_id=pattern_id, detail=decision)
        return {"status": "ok", "decision": decision, "safety": SAFETY_DECLARATION}

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
        definitions: dict[str, dict[str, Any]] = {
            item["payload"]["playbook_id"]: item["payload"]
            for item in self.store.list_documents(ctx.user_id, "playbook", limit=5000)
        }
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

    def _journal_playbooks(self, ctx: AuthContext, account_id: str | None = None) -> dict[str, dict[str, Any]]:
        """Playbooks observed in this tenant's own journal, scored by analytics."""
        ledger = self._ledger(ctx, account_id=account_id)
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
                    "currency": row.get("currency"),
                    "mixed_currency": row.get("mixed_currency", False),
                    "currency_breakdown": row.get("currency_breakdown", []),
                }
        return found

    def playbooks(self, ctx: AuthContext, *, account_id: str | None = None) -> dict[str, Any]:
        """Declared playbooks, each scored against this tenant's own journal."""
        journal = self._journal_playbooks(ctx, account_id=account_id)
        definitions = self._playbook_definitions(ctx)
        records: list[dict[str, Any]] = []
        for playbook_id, detail in sorted(definitions.items()):
            key = str(detail.get("key") or "")
            stats = journal.get(playbook_id, {})
            records.append(
                {
                    **detail,
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
                    "currency": stats.get("currency"),
                    "mixed_currency": stats.get("mixed_currency", False),
                    "currency_breakdown": stats.get("currency_breakdown", []),
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
                    "currency": stats.get("currency"),
                    "mixed_currency": stats.get("mixed_currency", False),
                    "currency_breakdown": stats.get("currency_breakdown", []),
                }
            )
        return {
            "status": "ok",
            "count": len(records),
            "playbooks": records,
            "stats": {record["playbook_id"]: {key: record.get(key) for key in (
                "trade_count", "win_rate", "net_pnl", "avg_return_pct", "profit_factor", "small_sample"
            )} for record in records},
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
        authored_lists = {}
        for field_name in ("entry_rules", "exit_rules", "risk_rules", "tags"):
            value = payload.get(field_name, [])
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise TraderRequestError(field_name + " must be a list of strings")
            authored_lists[field_name] = value
        detail = {
            "playbook_id": playbook_id,
            "name": name,
            "dimension": dimension,
            "key": key,
            "description": str(payload.get("description") or "").strip(),
            "rules": rules,
            "setup": str(payload.get("setup") or ""),
            **authored_lists,
            "updated_at": now_iso(),
        }
        self._ensure_tenant(ctx)
        self.store.put_document(ctx.user_id, "playbook", playbook_id, detail)
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
        symbol = str(data.get("symbol") or payload.get("symbol") or spec.universe.symbol)
        interval = str(data.get("interval") or payload.get("interval") or spec.universe.interval)
        if symbol != spec.universe.symbol or interval != spec.universe.interval:
            raise TraderRequestError("symbol and interval controls must match the strategy universe")
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
        if any(bar.symbol != symbol or bar.interval != interval for bar in bars):
            raise TraderRequestError("bar symbol and interval must match the strategy universe")

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
            self.store.put_document(ctx.user_id, "backtest_detail", run_id, {
                **result_payload, "run_id": run_id, "provenance": provenance,
                "symbol": symbol, "interval": interval, "spec": spec.to_dict(),
            })
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
        document = self.store.get_document(ctx.user_id, "backtest_detail", run_id)
        detail = document["payload"] if document else {}
        return {"status": "ok", "run": {**run, **detail}, "safety": SAFETY_DECLARATION}

    # ---- replay --------------------------------------------------------

    def create_replay_session(
        self, ctx: AuthContext, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Persist a replay; return only the portion already revealed."""
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
        account_id = str(payload.get("account_id") or "") or None
        record = create_record(
            symbol=symbol, interval=interval, bars=[bar.to_dict() for bar in bars],
            provenance=provenance, mode=str(payload.get("mode") or "review"),
            initial_cash=payload.get("initial_cash", DEFAULT_INITIAL_CASH),
            account_id=account_id, fills=self._fills(ctx, symbol=symbol, account_id=account_id),
        )
        record["index"] = index or 0
        self._ensure_tenant(ctx)
        with self._replay_lock:
            self.store.put_document(ctx.user_id, "replay_session", record["session_id"], record)
        return {
            "status": "ok",
            "session": public_view(record),
            "safety": SAFETY_DECLARATION,
        }

    def replay_session(
        self, ctx: AuthContext, session_id: str, *, index: int | None = None
    ) -> dict[str, Any]:
        """Compatibility read/step; all mutations retain the cursor boundary."""
        if not session_id:
            raise TraderRequestError("a session id is required")
        with self._replay_lock:
            document = self.store.get_document(ctx.user_id, "replay_session", session_id)
            if document is None:
                raise TraderRequestError("no such replay session for this tenant", status=404, code="not_found")
            record = document["payload"]
            if index is not None:
                record = apply_action(record, {"action": "seek", "index": index})
                self.store.put_document(ctx.user_id, "replay_session", record["session_id"], record)
        view = public_view(record)
        return {
            "status": "ok", "session": view,
            "frame": view["bars"][-1], "ephemeral": False,
            "safety": SAFETY_DECLARATION,
        }

    def replay_sessions(self, ctx: AuthContext) -> dict[str, Any]:
        records = self.store.list_documents(ctx.user_id, "replay_session", limit=100)
        # A history list must not disclose the unrevealed series either.
        views = [public_view(record["payload"]) for record in records]
        return {"status": "ok", "sessions": [{k: v for k, v in view.items() if k not in ("bars", "markers", "training")} for view in views],
                "safety": SAFETY_DECLARATION}

    def replay_action(self, ctx: AuthContext, session_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise TraderRequestError("the request body must be a JSON object")
        with self._replay_lock:
            document = self.store.get_document(ctx.user_id, "replay_session", session_id)
            if document is None:
                raise TraderRequestError("no such replay session for this tenant", status=404, code="not_found")
            record = document["payload"]
            updated = apply_action(record, payload)
            self.store.put_document(ctx.user_id, "replay_session", updated["session_id"], updated)
        return {"status": "ok", "session": public_view(updated), "safety": SAFETY_DECLARATION}
