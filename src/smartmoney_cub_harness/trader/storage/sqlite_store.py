"""SQLite tenant store: the default engine, local and dependency-free.

Why SQLite is the default: the product has to install and run offline on a
trader's own machine and in CI, where the core package has no third-party
runtime dependency. The hosted engine is an opt-in extra; this one is the floor.

The idioms match the existing review store (smartmoney_cub_harness.store): WAL
journal mode, an explicit sqlite3.Row factory, one connection behind a lock
because the local service answers on several threads, and writes wrapped in a
transaction. The one thing this store adds is the tenant rule: every
tenant-scoped statement carries its user_id predicate in the SQL itself, so the
predicate is visible in the statement that relies on it rather than assembled by
a helper.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from smartmoney_cub_harness.trader.storage.base import (
    AccountRecord,
    AuditRecord,
    BacktestRunRecord,
    BarRecord,
    StoreError,
    TradeRecord,
    UserRecord,
    encode_json,
    iter_statements,
    new_id,
    now_iso,
    optional_float,
    optional_text,
    require_float,
    require_text,
    safety_envelope,
    schema_sql,
)

DATABASE_FILENAME = "trader_store.db"
FILE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
MEMORY_PATH = ":memory:"

SIDE_ALIASES = {
    "BUY": "BUY",
    "B": "BUY",
    "买入": "BUY",
    "SELL": "SELL",
    "S": "SELL",
    "卖出": "SELL",
}

TRADE_UPSERT = (
    "INSERT INTO trades (user_id, trade_id, account_id, symbol, name, side,"
    " trade_date, trade_time, price, quantity, fee, thesis,"
    " invalidation_price, regime, tags, created_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    " ON CONFLICT (user_id, trade_id) DO UPDATE SET"
    " account_id = excluded.account_id, symbol = excluded.symbol,"
    " name = excluded.name, side = excluded.side,"
    " trade_date = excluded.trade_date, trade_time = excluded.trade_time,"
    " price = excluded.price, quantity = excluded.quantity,"
    " fee = excluded.fee, thesis = excluded.thesis,"
    " invalidation_price = excluded.invalidation_price,"
    " regime = excluded.regime, tags = excluded.tags"
    " WHERE trades.user_id = excluded.user_id"
)

BAR_UPSERT = (
    "INSERT INTO market_bars (user_id, symbol, bar_interval, open_time,"
    " open, high, low, close, volume, provider, fetched_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    " ON CONFLICT (user_id, symbol, bar_interval, open_time) DO UPDATE SET"
    " open = excluded.open, high = excluded.high, low = excluded.low,"
    " close = excluded.close, volume = excluded.volume,"
    " provider = excluded.provider, fetched_at = excluded.fetched_at"
    " WHERE market_bars.user_id = excluded.user_id"
)


def resolve_database_path(path: str | Path) -> Path | str:
    """Turn an open_store location into a SQLite database path.

    A directory means the tenant owns a directory and one database per tenant
    lives inside it; a file path or ":memory:" means the caller named the
    database itself. Two tenants therefore cannot share a file by accident,
    because the directory form always appends the same fixed filename.
    """
    text = str(path)
    if text == MEMORY_PATH or text.startswith("file:"):
        return text
    candidate = Path(text)
    if candidate.suffix.lower() in FILE_SUFFIXES:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate / DATABASE_FILENAME


class SQLiteTenantStore:
    """Tenant store on sqlite3. Local mode, single user, no server."""

    engine = "sqlite"

    def __init__(self, path: str | Path) -> None:
        self.database_path = resolve_database_path(path)
        self._lock = threading.RLock()
        try:
            self._db = sqlite3.connect(str(self.database_path), check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA journal_mode = WAL")
            self._db.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error as exc:  # pragma: no cover - filesystem failure
            raise StoreError(
                f"could not open sqlite store at {self.database_path}: {exc}"
            ) from exc
        # The schema is created on open so a caller never has to remember to
        # migrate, and calling migrate() again stays a no-op.
        self.migrate()

    # ---- plumbing ------------------------------------------------------

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Run one write atomically: commit on success, roll back on failure.

        The lock is held for the whole block, so a threaded caller cannot
        interleave two writes between their statements.
        """
        with self._lock:
            try:
                yield self._db
            except Exception:
                self._db.rollback()
                raise
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> SQLiteTenantStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _require_user(self, conn: sqlite3.Connection, user_id: str) -> str:
        """Fail closed on an unknown tenant instead of writing orphan rows."""
        resolved = require_text(user_id, "user_id")
        row = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?", (resolved,)
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown tenant: {resolved!r}")
        return resolved

    def _write_audit(
        self,
        conn: sqlite3.Connection,
        user_id: str,
        action: str,
        record_id: str = "",
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        conn.execute(
            "INSERT INTO audit_log (user_id, audit_id, action, record_id, detail, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                user_id,
                new_id("AUD"),
                require_text(action, "action"),
                record_id or "",
                encode_json(detail, {}),
                now_iso(),
            ),
        )

    # ---- schema --------------------------------------------------------

    def migrate(self) -> dict[str, Any]:
        """Create the tenant schema if it is absent.

        Idempotent by construction: every statement is CREATE ... IF NOT EXISTS,
        so a second call neither fails nor drops data.
        """
        statements = iter_statements(schema_sql())
        try:
            with self._transaction() as conn:
                for statement in statements:
                    conn.execute(statement)
                tables = [
                    str(row["name"])
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                        " AND name NOT LIKE 'sqlite_%' ORDER BY name"
                    ).fetchall()
                ]
        except sqlite3.Error as exc:
            raise StoreError(f"migration failed: {exc}") from exc
        return safety_envelope({
            "status": "ok",
            "engine": self.engine,
            "statements": len(statements),
            "tables": tables,
        })

    # ---- tenants -------------------------------------------------------

    def create_user(
        self, user_id: str, *, tenant_id: str | None = None, display_name: str = ""
    ) -> dict[str, Any]:
        """Create the tenant row, or refresh its display fields.

        The conflict clause repeats the user_id equality so an update can only
        ever touch the row it is upserting.
        """
        resolved = require_text(user_id, "user_id")
        tenant = optional_text(tenant_id) or resolved
        stamp = now_iso()
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO users (user_id, tenant_id, display_name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (user_id) DO UPDATE SET"
                " tenant_id = excluded.tenant_id,"
                " display_name = excluded.display_name,"
                " updated_at = excluded.updated_at"
                " WHERE users.user_id = excluded.user_id",
                (resolved, tenant, optional_text(display_name), stamp, stamp),
            )
        return self.get_user(resolved) or {}

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT * FROM users WHERE user_id = ?", (require_text(user_id, "user_id"),)
        ).fetchone()
        if row is None:
            return None
        return UserRecord.from_row(row).to_dict()

    # ---- trades --------------------------------------------------------

    def list_trades(
        self,
        user_id: str,
        *,
        account_id: str | None = None,
        symbol: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Return this tenant's trades.

        The optional arguments narrow the tenant's own rows; they never widen the
        scope, because user_id is always the first predicate.
        """
        resolved = require_text(user_id, "user_id")
        account = optional_text(account_id)
        ticker = optional_text(symbol)
        since = optional_text(start)
        until = optional_text(end)
        # One statement, not a concatenation: the tenant predicate is the
        # unconditional first clause, and an empty filter arrives as an empty
        # string so the same statement serves the filtered and unfiltered case.
        # Reading the source therefore always shows the user_id scope.
        rows = self._db.execute(
            "SELECT * FROM trades WHERE user_id = ?"
            " AND (? = '' OR account_id = ?)"
            " AND (? = '' OR symbol = ?)"
            " AND (? = '' OR trade_date >= ?)"
            " AND (? = '' OR trade_date <= ?)"
            " ORDER BY trade_date DESC, trade_time DESC, created_at DESC LIMIT ? OFFSET ?",
            [
                resolved,
                account,
                account,
                ticker,
                ticker,
                since,
                since,
                until,
                until,
                max(1, int(limit)),
                max(0, int(offset)),
            ],
        ).fetchall()
        return [TradeRecord.from_row(row).to_dict() for row in rows]

    def insert_trades(self, user_id: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Append executions for this tenant.

        Re-importing a row with the same trade_id updates it instead of
        duplicating the position, and the update is confined to this tenant by
        the conflict clause.
        """
        resolved = require_text(user_id, "user_id")
        inserted: list[str] = []
        updated: list[str] = []
        with self._transaction() as conn:
            self._require_user(conn, resolved)
            for raw in rows:
                record = self._normalize_trade(resolved, raw)
                existing = conn.execute(
                    "SELECT trade_id FROM trades WHERE user_id = ? AND trade_id = ?",
                    (resolved, record["trade_id"]),
                ).fetchone()
                conn.execute(
                    TRADE_UPSERT,
                    (
                        resolved,
                        record["trade_id"],
                        record["account_id"],
                        record["symbol"],
                        record["name"],
                        record["side"],
                        record["trade_date"],
                        record["trade_time"],
                        record["price"],
                        record["quantity"],
                        record["fee"],
                        record["thesis"],
                        record["invalidation_price"],
                        record["regime"],
                        encode_json(record["tags"], []),
                        record["created_at"],
                    ),
                )
                (updated if existing is not None else inserted).append(record["trade_id"])
            self._write_audit(
                conn,
                resolved,
                "insert_trades",
                record_id=",".join(inserted + updated),
                detail={"inserted": len(inserted), "updated": len(updated)},
            )
        return safety_envelope({
            "status": "ok",
            "user_id": resolved,
            "inserted": inserted,
            "updated": updated,
            "inserted_count": len(inserted),
            "updated_count": len(updated),
        })

    @staticmethod
    def _normalize_trade(user_id: str, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize one journal row into the stored shape.

        Field aliases are accepted because the same row arrives from a CSV
        import, a broker export, and the API, and all of them have to land as
        one meaning.
        """
        side = optional_text(raw.get("side")).upper()
        side = SIDE_ALIASES.get(side, side)
        if side not in ("BUY", "SELL"):
            raise StoreError(f"side must be BUY or SELL, got {raw.get('side')!r}")
        fee = raw.get("fee")
        if fee is None:
            fee = raw.get("commission") or 0.0
        quantity = raw.get("quantity")
        if quantity is None:
            quantity = raw.get("qty")
        return {
            "user_id": user_id,
            "trade_id": optional_text(raw.get("trade_id") or raw.get("fill_id"))
            or new_id("TRD"),
            "account_id": optional_text(raw.get("account_id")),
            "symbol": require_text(raw.get("symbol"), "symbol"),
            "name": optional_text(raw.get("name")),
            "side": side,
            "trade_date": require_text(
                raw.get("trade_date") or raw.get("date"), "trade_date"
            ),
            "trade_time": optional_text(raw.get("trade_time") or raw.get("time")),
            "price": require_float(raw.get("price"), "price"),
            "quantity": require_float(quantity, "quantity"),
            "fee": require_float(fee, "fee"),
            "thesis": optional_text(raw.get("thesis")),
            "invalidation_price": optional_float(
                raw.get("invalidation_price"), "invalidation_price"
            ),
            "regime": optional_text(raw.get("regime")),
            "tags": list(raw.get("tags") or []),
            "created_at": optional_text(raw.get("created_at")) or now_iso(),
        }

    # ---- accounts ------------------------------------------------------

    def list_accounts(self, user_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM accounts WHERE user_id = ? ORDER BY name, account_id",
            (require_text(user_id, "user_id"),),
        ).fetchall()
        return [AccountRecord.from_row(row).to_dict() for row in rows]

    def upsert_account(self, user_id: str, account: Mapping[str, Any]) -> dict[str, Any]:
        """Create or update one account inside this tenant."""
        resolved = require_text(user_id, "user_id")
        account_id = optional_text(account.get("account_id")) or new_id("ACC")
        name = optional_text(account.get("name")) or account_id
        stamp = now_iso()
        with self._transaction() as conn:
            self._require_user(conn, resolved)
            conn.execute(
                "INSERT INTO accounts (user_id, account_id, name, broker, currency,"
                " initial_balance, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (user_id, account_id) DO UPDATE SET"
                " name = excluded.name, broker = excluded.broker,"
                " currency = excluded.currency, initial_balance = excluded.initial_balance,"
                " updated_at = excluded.updated_at"
                " WHERE accounts.user_id = excluded.user_id",
                (
                    resolved,
                    account_id,
                    name,
                    optional_text(account.get("broker")),
                    optional_text(account.get("currency")) or "CNY",
                    require_float(account.get("initial_balance") or 0.0, "initial_balance"),
                    stamp,
                    stamp,
                ),
            )
            self._write_audit(conn, resolved, "upsert_account", account_id)
        return self._get_account(resolved, account_id)

    def _get_account(self, user_id: str, account_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM accounts WHERE user_id = ? AND account_id = ?",
            (user_id, account_id),
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown account: {account_id!r}")
        return AccountRecord.from_row(row).to_dict()

    # ---- backtest runs -------------------------------------------------

    def save_backtest_run(self, user_id: str, run: Mapping[str, Any]) -> dict[str, Any]:
        """Persist one backtest run and its results for this tenant."""
        resolved = require_text(user_id, "user_id")
        run_id = optional_text(run.get("run_id")) or new_id("BT")
        stamp = now_iso()
        with self._transaction() as conn:
            self._require_user(conn, resolved)
            conn.execute(
                "INSERT INTO backtest_runs (user_id, run_id, strategy_name, symbol,"
                " bar_interval, started_at, metrics, equity_curve, spec, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (user_id, run_id) DO UPDATE SET"
                " strategy_name = excluded.strategy_name, symbol = excluded.symbol,"
                " bar_interval = excluded.bar_interval, started_at = excluded.started_at,"
                " metrics = excluded.metrics, equity_curve = excluded.equity_curve,"
                " spec = excluded.spec"
                " WHERE backtest_runs.user_id = excluded.user_id",
                (
                    resolved,
                    run_id,
                    optional_text(run.get("strategy_name") or run.get("name")),
                    optional_text(run.get("symbol")),
                    optional_text(run.get("interval") or run.get("bar_interval")),
                    optional_text(run.get("started_at")) or stamp,
                    encode_json(run.get("metrics"), {}),
                    encode_json(run.get("equity_curve"), []),
                    encode_json(run.get("spec"), {}),
                    stamp,
                ),
            )
            self._write_audit(conn, resolved, "save_backtest_run", run_id)
        return self._get_backtest_run(resolved, run_id)

    def _get_backtest_run(self, user_id: str, run_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM backtest_runs WHERE user_id = ? AND run_id = ?",
            (user_id, run_id),
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown backtest run: {run_id!r}")
        return BacktestRunRecord.from_row(row).to_dict()

    def list_backtest_runs(self, user_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM backtest_runs WHERE user_id = ?"
            " ORDER BY created_at DESC, run_id DESC LIMIT ?",
            (require_text(user_id, "user_id"), max(1, int(limit))),
        ).fetchall()
        return [BacktestRunRecord.from_row(row).to_dict() for row in rows]

    # ---- market bars ---------------------------------------------------

    def save_bars(self, user_id: str, bars: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Upsert cached bars for this tenant.

        The cache is keyed per tenant, so two tenants fetching the same symbol
        keep separate rows, and re-fetching corrects a bar in place.
        """
        resolved = require_text(user_id, "user_id")
        stored = 0
        with self._transaction() as conn:
            self._require_user(conn, resolved)
            for raw in bars:
                record = self._normalize_bar(resolved, raw)
                conn.execute(
                    BAR_UPSERT,
                    (
                        resolved,
                        record["symbol"],
                        record["interval"],
                        record["open_time"],
                        record["open"],
                        record["high"],
                        record["low"],
                        record["close"],
                        record["volume"],
                        record["provider"],
                        record["fetched_at"],
                    ),
                )
                stored += 1
            self._write_audit(
                conn, resolved, "save_bars", str(stored), detail={"stored": stored}
            )
        return safety_envelope({
            "status": "ok",
            "user_id": resolved,
            "stored_count": stored,
        })

    @staticmethod
    def _normalize_bar(user_id: str, raw: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "symbol": require_text(raw.get("symbol"), "symbol"),
            "interval": require_text(
                raw.get("interval") or raw.get("bar_interval"), "interval"
            ),
            "open_time": require_text(
                raw.get("open_time") or raw.get("time") or raw.get("t"), "open_time"
            ),
            "open": require_float(raw.get("open"), "open"),
            "high": require_float(raw.get("high"), "high"),
            "low": require_float(raw.get("low"), "low"),
            "close": require_float(raw.get("close"), "close"),
            "volume": require_float(raw.get("volume") or 0.0, "volume"),
            "provider": optional_text(raw.get("provider")),
            "fetched_at": optional_text(raw.get("fetched_at")),
        }

    def load_bars(
        self,
        user_id: str,
        *,
        symbol: str,
        interval: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        resolved = require_text(user_id, "user_id")
        ticker = require_text(symbol, "symbol")
        step = require_text(interval, "interval")
        since = optional_text(start)
        until = optional_text(end)
        # Same shape as list_trades: one statement whose first clause is the
        # tenant scope, with the optional range passed as empty-able parameters.
        rows = self._db.execute(
            "SELECT * FROM market_bars WHERE user_id = ?"
            " AND symbol = ? AND bar_interval = ?"
            " AND (? = '' OR open_time >= ?)"
            " AND (? = '' OR open_time <= ?)"
            " ORDER BY open_time LIMIT ?",
            [
                resolved,
                ticker,
                step,
                since,
                since,
                until,
                until,
                max(1, int(limit)),
            ],
        ).fetchall()
        return [BarRecord.from_row(row).to_dict() for row in rows]

    # ---- audit ---------------------------------------------------------

    def audit(
        self,
        user_id: str,
        action: str,
        *,
        record_id: str | None = None,
        detail: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one audit entry inside this tenant."""
        resolved = require_text(user_id, "user_id")
        audit_id = new_id("AUD")
        stamp = now_iso()
        with self._transaction() as conn:
            self._require_user(conn, resolved)
            conn.execute(
                "INSERT INTO audit_log (user_id, audit_id, action, record_id, detail, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    resolved,
                    audit_id,
                    require_text(action, "action"),
                    optional_text(record_id),
                    encode_json(detail, {}),
                    stamp,
                ),
            )
        return AuditRecord.from_row(
            {
                "user_id": resolved,
                "audit_id": audit_id,
                "action": action,
                "record_id": record_id or "",
                "detail": encode_json(detail, {}),
                "created_at": stamp,
            }
        ).to_dict()

    def list_audit(self, user_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return this tenant's audit trail, newest first."""
        rows = self._db.execute(
            "SELECT * FROM audit_log WHERE user_id = ?"
            " ORDER BY created_at DESC, audit_id DESC LIMIT ?",
            (require_text(user_id, "user_id"), max(1, int(limit))),
        ).fetchall()
        return [AuditRecord.from_row(row).to_dict() for row in rows]
