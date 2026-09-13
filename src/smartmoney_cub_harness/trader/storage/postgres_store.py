"""Postgres tenant store: the hosted engine, behind an opt-in extra.

Why this file is separate from the SQLite one: the hosted product runs many
tenants against one server, and the local product runs one user against one
file. The contract is identical (see base.TenantStore); only the driver and the
placeholder style differ, so a caller never branches on which engine it holds.

Two properties are load-bearing here and are checked by tests rather than
trusted:

1. psycopg is imported lazily, inside connect(). The core package must install
   and import with no third-party runtime dependency, so importing this module
   or the storage package must never require the driver. A missing driver is a
   StoreError carrying the install hint, not an ImportError at import time.

2. Every tenant-scoped statement carries a literal user_id predicate, including
   its writes. Nothing is assembled by string concatenation that would hide the
   predicate from a reader or from a source-scanning test. Writes are written as
   an UPDATE ... WHERE user_id = %s followed by an INSERT, rather than an
   ON CONFLICT upsert, so the predicate is present in both statements and no
   version-specific conflict syntax is needed.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
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

DATABASE_URL_PREFIXES = ("postgres://", "postgresql://", "postgresql+psycopg://")

INSTALL_HINT = 'pip install "smartmoney-cub-harness[hosted]"'

DRIVER_IMPORT_ERROR = (
    "the hosted Postgres store needs the psycopg driver; "
    f"install it with: {INSTALL_HINT}"
)

SIDE_ALIASES = {
    "BUY": "BUY",
    "B": "BUY",
    "买入": "BUY",
    "SELL": "SELL",
    "S": "SELL",
    "卖出": "SELL",
}


def is_postgres_url(location: str) -> bool:
    """True when open_store should route to the hosted engine."""
    return str(location).strip().lower().startswith(DATABASE_URL_PREFIXES)


class PostgresTenantStore:
    """Tenant store on Postgres. Hosted mode, many tenants, one server."""

    engine = "postgres"

    def __init__(self, database_url: str) -> None:
        url = require_text(database_url, "database_url")
        if not is_postgres_url(url):
            raise StoreError(f"not a postgres url: {url.split('://')[0]}://...")
        self.database_url = url
        self._lock = threading.RLock()
        self._conn: Any = None

    # ---- connection ----------------------------------------------------

    def connect(self) -> Any:
        """Open the driver connection, importing psycopg only here.

        The import is deliberately inside this function. Reading it at module
        level would make the storage package unimportable on a machine without
        the extra, which is exactly what the core dependency rule forbids.
        """
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise StoreError(DRIVER_IMPORT_ERROR) from exc
        try:
            return psycopg.connect(self.database_url, row_factory=dict_row)
        except Exception as exc:  # driver-specific error types live off-module
            raise StoreError(f"could not connect to the hosted database: {exc}") from exc

    def _connection(self) -> Any:
        with self._lock:
            if self._conn is None or getattr(self._conn, "closed", False):
                self._conn = self.connect()
            return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> PostgresTenantStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        """Run one write atomically, rolling back on any failure."""
        with self._lock:
            conn = self._connection()
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise
            conn.commit()

    def _require_user(self, conn: Any, user_id: str) -> str:
        """Fail closed on an unknown tenant instead of writing orphan rows."""
        resolved = require_text(user_id, "user_id")
        row = conn.execute(
            "SELECT user_id, tenant_id FROM users WHERE user_id = %s",
            (resolved,),
        ).fetchone()
        if row is None:
            raise StoreError(f"unknown tenant: {resolved!r}")
        return resolved

    def _fetchall(self, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection().execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def _fetchone(self, sql: str, params: Sequence[Any]) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection().execute(sql, tuple(params)).fetchone()
        return None if row is None else dict(row)

    def _write_audit(
        self,
        conn: Any,
        user_id: str,
        action: str,
        record_id: str = "",
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        conn.execute(
            "INSERT INTO audit_log (user_id, audit_id, action, record_id, detail, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
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

        Idempotent: the shared DDL is written with IF NOT EXISTS throughout, so a
        second call neither fails nor drops data. This method is the one place in
        this module without a user_id predicate, because it creates the tables
        that carry user_id rather than reading or writing tenant rows.
        """
        statements = iter_statements(schema_sql())
        with self._transaction() as conn:
            for statement in statements:
                conn.execute(statement)
            tables = [
                str(row["table_name"])
                for row in conn.execute(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = current_schema() ORDER BY table_name"
                ).fetchall()
            ]
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
        """Create the tenant row, or refresh its display fields."""
        resolved = require_text(user_id, "user_id")
        tenant = optional_text(tenant_id) or resolved
        stamp = now_iso()
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE users SET tenant_id = %s, display_name = %s, updated_at = %s"
                " WHERE user_id = %s",
                (tenant, optional_text(display_name), stamp, resolved),
            )
            if cursor.rowcount == 0:
                conn.execute(
                    "INSERT INTO users (user_id, tenant_id, display_name, created_at,"
                    " updated_at) VALUES (%s, %s, %s, %s, %s)",
                    (resolved, tenant, optional_text(display_name), stamp, stamp),
                )
        return self.get_user(resolved) or {}

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        row = self._fetchone(
            "SELECT * FROM users WHERE user_id = %s",
            (require_text(user_id, "user_id"),),
        )
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

        Optional filters narrow the tenant's own rows; the user_id predicate is
        always present, so a filter can never widen the scope.
        """
        resolved = require_text(user_id, "user_id")
        account = optional_text(account_id)
        ticker = optional_text(symbol)
        since = optional_text(start)
        until = optional_text(end)
        # One statement, not a concatenation: the tenant predicate is the first
        # and only unconditional clause, and an empty filter is passed as an
        # empty string so the same statement serves the filtered and unfiltered
        # case. Reading the source therefore always shows the user_id scope.
        sql = (
            "SELECT * FROM trades WHERE user_id = %s"
            " AND (%s = '' OR account_id = %s)"
            " AND (%s = '' OR symbol = %s)"
            " AND (%s = '' OR trade_date >= %s)"
            " AND (%s = '' OR trade_date <= %s)"
            " ORDER BY trade_date DESC, trade_time DESC, created_at DESC LIMIT %s OFFSET %s"
        )
        params: list[Any] = [
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
        ]
        return [TradeRecord.from_row(row).to_dict() for row in self._fetchall(sql, params)]

    def insert_trades(self, user_id: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Append or correct executions for this tenant.

        Each row is written as an UPDATE scoped by user_id followed by an INSERT,
        so a repeated import corrects the row and a cross-tenant write has no
        statement that could perform it.
        """
        resolved = require_text(user_id, "user_id")
        inserted: list[str] = []
        updated: list[str] = []
        with self._transaction() as conn:
            self._require_user(conn, resolved)
            for raw in rows:
                record = self._normalize_trade(resolved, raw)
                cursor = conn.execute(
                    "UPDATE trades SET account_id = %s, symbol = %s, name = %s, side = %s,"
                    " trade_date = %s, trade_time = %s, price = %s, quantity = %s, fee = %s,"
                    " thesis = %s, invalidation_price = %s, regime = %s, tags = %s"
                    " WHERE user_id = %s AND trade_id = %s",
                    (
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
                        resolved,
                        record["trade_id"],
                    ),
                )
                if cursor.rowcount == 0:
                    conn.execute(
                        "INSERT INTO trades (user_id, trade_id, account_id, symbol, name,"
                        " side, trade_date, trade_time, price, quantity, fee, thesis,"
                        " invalidation_price, regime, tags, created_at)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
                    inserted.append(record["trade_id"])
                else:
                    updated.append(record["trade_id"])
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

        This mirrors the SQLite engine deliberately: both must accept the same
        import row. Keep the two in step when a field is added.
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
        rows = self._fetchall(
            "SELECT * FROM accounts WHERE user_id = %s ORDER BY name, account_id",
            (require_text(user_id, "user_id"),),
        )
        return [AccountRecord.from_row(row).to_dict() for row in rows]

    def upsert_account(self, user_id: str, account: Mapping[str, Any]) -> dict[str, Any]:
        """Create or update one account inside this tenant."""
        resolved = require_text(user_id, "user_id")
        account_id = optional_text(account.get("account_id")) or new_id("ACC")
        name = optional_text(account.get("name")) or account_id
        stamp = now_iso()
        with self._transaction() as conn:
            self._require_user(conn, resolved)
            cursor = conn.execute(
                "UPDATE accounts SET name = %s, broker = %s, currency = %s,"
                " initial_balance = %s, updated_at = %s"
                " WHERE user_id = %s AND account_id = %s",
                (
                    name,
                    optional_text(account.get("broker")),
                    optional_text(account.get("currency")) or "CNY",
                    require_float(account.get("initial_balance") or 0.0, "initial_balance"),
                    stamp,
                    resolved,
                    account_id,
                ),
            )
            if cursor.rowcount == 0:
                conn.execute(
                    "INSERT INTO accounts (user_id, account_id, name, broker, currency,"
                    " initial_balance, created_at, updated_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        resolved,
                        account_id,
                        name,
                        optional_text(account.get("broker")),
                        optional_text(account.get("currency")) or "CNY",
                        require_float(
                            account.get("initial_balance") or 0.0, "initial_balance"
                        ),
                        stamp,
                        stamp,
                    ),
                )
            self._write_audit(conn, resolved, "upsert_account", account_id)
        return self._get_account(resolved, account_id)

    def _get_account(self, user_id: str, account_id: str) -> dict[str, Any]:
        row = self._fetchone(
            "SELECT * FROM accounts WHERE user_id = %s AND account_id = %s",
            (user_id, account_id),
        )
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
            cursor = conn.execute(
                "UPDATE backtest_runs SET strategy_name = %s, symbol = %s, bar_interval = %s,"
                " started_at = %s, metrics = %s, equity_curve = %s, spec = %s"
                " WHERE user_id = %s AND run_id = %s",
                (
                    optional_text(run.get("strategy_name") or run.get("name")),
                    optional_text(run.get("symbol")),
                    optional_text(run.get("interval") or run.get("bar_interval")),
                    optional_text(run.get("started_at")) or stamp,
                    encode_json(run.get("metrics"), {}),
                    encode_json(run.get("equity_curve"), []),
                    encode_json(run.get("spec"), {}),
                    resolved,
                    run_id,
                ),
            )
            if cursor.rowcount == 0:
                conn.execute(
                    "INSERT INTO backtest_runs (user_id, run_id, strategy_name, symbol,"
                    " bar_interval, started_at, metrics, equity_curve, spec, created_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
        row = self._fetchone(
            "SELECT * FROM backtest_runs WHERE user_id = %s AND run_id = %s",
            (user_id, run_id),
        )
        if row is None:
            raise StoreError(f"unknown backtest run: {run_id!r}")
        return BacktestRunRecord.from_row(row).to_dict()

    def list_backtest_runs(self, user_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT * FROM backtest_runs WHERE user_id = %s"
            " ORDER BY created_at DESC, run_id DESC LIMIT %s",
            (require_text(user_id, "user_id"), max(1, int(limit))),
        )
        return [BacktestRunRecord.from_row(row).to_dict() for row in rows]

    # ---- market bars ---------------------------------------------------

    def save_bars(self, user_id: str, bars: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Upsert cached bars for this tenant, keyed per tenant."""
        resolved = require_text(user_id, "user_id")
        stored = 0
        with self._transaction() as conn:
            self._require_user(conn, resolved)
            for raw in bars:
                record = self._normalize_bar(resolved, raw)
                cursor = conn.execute(
                    "UPDATE market_bars SET open = %s, high = %s, low = %s, close = %s,"
                    " volume = %s, provider = %s, fetched_at = %s"
                    " WHERE user_id = %s AND symbol = %s AND bar_interval = %s"
                    " AND open_time = %s",
                    (
                        record["open"],
                        record["high"],
                        record["low"],
                        record["close"],
                        record["volume"],
                        record["provider"],
                        record["fetched_at"],
                        resolved,
                        record["symbol"],
                        record["interval"],
                        record["open_time"],
                    ),
                )
                if cursor.rowcount == 0:
                    conn.execute(
                        "INSERT INTO market_bars (user_id, symbol, bar_interval, open_time,"
                        " open, high, low, close, volume, provider, fetched_at)"
                        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
        sql = (
            "SELECT * FROM market_bars WHERE user_id = %s"
            " AND symbol = %s AND bar_interval = %s"
            " AND (%s = '' OR open_time >= %s)"
            " AND (%s = '' OR open_time <= %s)"
            " ORDER BY open_time LIMIT %s"
        )
        params: list[Any] = [
            resolved,
            ticker,
            step,
            since,
            since,
            until,
            until,
            max(1, int(limit)),
        ]
        return [BarRecord.from_row(row).to_dict() for row in self._fetchall(sql, params)]

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
                "INSERT INTO audit_log (user_id, audit_id, action, record_id, detail,"
                " created_at) VALUES (%s, %s, %s, %s, %s, %s)",
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
        rows = self._fetchall(
            "SELECT * FROM audit_log WHERE user_id = %s"
            " ORDER BY created_at DESC, audit_id DESC LIMIT %s",
            (require_text(user_id, "user_id"), max(1, int(limit))),
        )
        return [AuditRecord.from_row(row).to_dict() for row in rows]
