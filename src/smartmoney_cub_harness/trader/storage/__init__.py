"""Tenant storage: one interface, two engines, isolation proven by test.

Why the shape is open_store(path_or_url, mode=...) rather than two classes: the
rest of the product must not care where the journal lives. A local install calls
open_store with a directory and gets SQLite; the hosted deployment calls it with
a postgres URL and gets Postgres. The returned object satisfies TenantStore in
either case.

Mode is explicit rather than inferred from the string alone, so a misconfigured
hosted deployment fails loudly instead of silently writing a local file that
looks like it worked.
"""

from __future__ import annotations

from pathlib import Path

from smartmoney_cub_harness.trader.storage.base import (
    MODE_HOSTED,
    MODE_LOCAL,
    STORAGE_SCHEMA,
    AccountRecord,
    AuditRecord,
    BacktestRunRecord,
    BarRecord,
    Row,
    StoreError,
    TenantStore,
    TradeRecord,
    UserRecord,
    schema_sql,
)

__all__ = [
    "MODE_HOSTED",
    "MODE_LOCAL",
    "STORAGE_SCHEMA",
    "AccountRecord",
    "AuditRecord",
    "BacktestRunRecord",
    "BarRecord",
    "PostgresTenantStore",
    "Row",
    "SQLiteTenantStore",
    "StoreError",
    "TenantStore",
    "TradeRecord",
    "UserRecord",
    "open_store",
    "schema_sql",
]


def __getattr__(name: str):
    """Resolve the engine classes lazily.

    Both engines are importable, but the postgres module pulls nothing at import
    time and the sqlite module is stdlib-only, so this hook exists to keep the
    package's import surface honest: importing the package never requires the
    hosted driver, and a caller asking for a class by name still gets it.
    """
    if name == "SQLiteTenantStore":
        from smartmoney_cub_harness.trader.storage.sqlite_store import SQLiteTenantStore

        return SQLiteTenantStore
    if name == "PostgresTenantStore":
        from smartmoney_cub_harness.trader.storage.postgres_store import PostgresTenantStore

        return PostgresTenantStore
    raise AttributeError(name)


def open_store(path_or_url: str | Path, *, mode: str = MODE_LOCAL) -> TenantStore:
    """Open the tenant store for a location and a mode.

    A postgres URL selects the hosted engine; anything else is a local SQLite
    path (a directory means the tenant owns a directory and the database lives
    inside it). In hosted mode the local engine is refused rather than
    substituted, because a hosted tenant must never land in a local file.

    The Postgres class is imported inside this function so a local-only install
    never imports the hosted module, and opening a store never needs the driver
    when the driver is not the one being used.
    """
    selected = str(mode or MODE_LOCAL).strip().lower()
    location = str(path_or_url)
    if selected == MODE_LOCAL:
        from smartmoney_cub_harness.trader.storage.sqlite_store import SQLiteTenantStore

        return SQLiteTenantStore(location)
    if selected == MODE_HOSTED:
        from smartmoney_cub_harness.trader.storage.postgres_store import PostgresTenantStore, is_postgres_url

        if not is_postgres_url(location):
            raise StoreError(
                "hosted mode needs a postgres URL (postgresql:// or postgres://),"
                f" got {location.split('://')[0]!r}; set mode='local' for a local store"
            )
        return PostgresTenantStore(location)
    raise StoreError(f"unknown store mode: {mode!r}")
