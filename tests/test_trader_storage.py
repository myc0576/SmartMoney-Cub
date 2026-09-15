"""Storage layer tests: contract behavior, tenant isolation, and engine plumbing.

The isolation claims in the spec are only real if a test demonstrates them, so
every "tenant B cannot see tenant A" assertion below is written twice: once
against the SQLite engine with real rows, and once as a source audit of the
Postgres engine, which cannot run on a machine without the hosted extra or a
database. The Postgres source audit is deliberately strict: it parses the module
and requires a literal user_id predicate in every tenant-scoped SQL statement,
so a future edit that assembles SQL without one fails the suite.

Both tenants in these tests are toy identities in a temporary store. No real
trade, account, or path is committed anywhere.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import os
import re
import sys
from pathlib import Path

import pytest

from smartmoney_cub_harness.trader.storage import (
    MODE_HOSTED,
    MODE_LOCAL,
    StoreError,
    TenantStore,
    open_store,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = REPO_ROOT / "src" / "smartmoney_cub_harness" / "trader" / "storage"
POSTGRES_SOURCE = STORAGE_DIR / "postgres_store.py"
SQLITE_SOURCE = STORAGE_DIR / "sqlite_store.py"
STORAGE_SOURCE = STORAGE_DIR / "base.py"

INSTALL_HINT = 'pip install "smartmoney-cub-harness[hosted]"'

# Every public method that reads or writes tenant rows. migrate(), connect(),
# and close() are excluded on purpose: they operate on the schema or the
# connection, not on a tenant's rows.
TENANT_SCOPED_METHODS = (
    "create_user",
    "get_user",
    "list_trades",
    "insert_trades",
    "list_accounts",
    "upsert_account",
    "save_backtest_run",
    "list_backtest_runs",
    "save_bars",
    "load_bars",
    "audit",
)


def _buy(trade_id: str, **overrides: object) -> dict:
    """One toy execution, shape-identical for both tenants."""
    row = {
        "trade_id": trade_id,
        "account_id": "ACC-TOY",
        "symbol": "TOY-SYM",
        "name": "Toy Instrument",
        "side": "BUY",
        "trade_date": "2026-09-01",
        "trade_time": "09:40:00",
        "price": 10.0,
        "quantity": 100.0,
        "fee": 1.0,
        "thesis": "toy thesis",
        "regime": "toy regime",
        "tags": ["toy"],
    }
    row.update(overrides)
    return row


def _bar(close: float, **overrides: object) -> dict:
    row = {
        "symbol": "TOY-SYM",
        "interval": "1d",
        "open_time": "2026-09-01T00:00:00Z",
        "open": 10.0,
        "high": 11.0,
        "low": 9.5,
        "close": close,
        "volume": 1000.0,
        "provider": "toy",
        "fetched_at": "2026-09-01T00:00:00Z",
    }
    row.update(overrides)
    return row


@pytest.fixture()
def store():
    """An in-memory store, migrated on open, with two toy tenants."""
    opened = open_store(":memory:", mode=MODE_LOCAL)
    opened.create_user("tenant-a", tenant_id="toy-a", display_name="Tenant A")
    opened.create_user("tenant-b", tenant_id="toy-b", display_name="Tenant B")
    try:
        yield opened
    finally:
        opened.close()


# ---------------------------------------------------------------- contract


def test_open_store_returns_a_tenant_store(store) -> None:
    assert isinstance(store, TenantStore)


def test_migrate_is_idempotent(tmp_path) -> None:
    """DoD: calling migrate() twice succeeds and changes no data."""
    first = open_store(tmp_path / "tenant" / "store.db")
    try:
        initial = first.migrate()
        first.create_user("tenant-a")
        first.insert_trades("tenant-a", [_buy("TRD-1")])
        second = first.migrate()
        assert second["status"] == "ok"
        assert second["tables"] == initial["tables"]
        # The rows survived the second migration, so it created rather than reset.
        assert len(first.list_trades("tenant-a")) == 1
    finally:
        first.close()


def test_store_directory_holds_one_database_per_tenant(tmp_path) -> None:
    """A directory location means the tenant owns exactly one database file."""
    directory = tmp_path / "tenant-a"
    opened = open_store(directory, mode=MODE_LOCAL)
    try:
        assert Path(opened.database_path) == directory / "trader_store.db"
        assert Path(opened.database_path).is_file()
    finally:
        opened.close()


def test_shared_ddl_ships_as_package_data() -> None:
    """The DDL is data, so the wheel must declare it or an install breaks."""
    payload = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"\[tool\.setuptools\.package-data\]\n(.*?)(?=\n\[)", payload, re.S)
    assert block is not None
    assert "trader/storage/*.sql" in block.group(1)
    assert (STORAGE_DIR / "schema.sql").is_file()


def test_sqlite_store_uses_wal_mode(tmp_path) -> None:
    """WAL keeps a reader from blocking the local service's writer."""
    opened = open_store(tmp_path / "tenant-a")
    try:
        mode = opened._db.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        opened.close()


def test_get_user_returns_none_for_an_unknown_tenant(store) -> None:
    assert store.get_user("nobody") is None


def test_create_user_is_an_upsert(store) -> None:
    store.create_user("tenant-a", tenant_id="toy-a", display_name="Renamed")
    record = store.get_user("tenant-a")
    assert record is not None
    assert record["display_name"] == "Renamed"
    assert record["tenant_id"] == "toy-a"


def test_trades_round_trip_with_json_columns(store) -> None:
    store.insert_trades(
        "tenant-a",
        [
            _buy("TRD-1"),
            _buy("TRD-2", side="SELL", trade_date="2026-09-03", price=11.0, tags=["toy", "exit"]),
        ],
    )
    rows = store.list_trades("tenant-a")
    assert [row["trade_id"] for row in rows] == ["TRD-2", "TRD-1"]
    assert rows[0]["tags"] == ["toy", "exit"]
    assert rows[0]["side"] == "SELL"
    assert rows[1]["quantity"] == 100.0
    assert rows[1]["tags"] == ["toy"]


def test_insert_trades_corrects_a_repeated_trade_id(store) -> None:
    """A re-import updates in place instead of doubling the position."""
    first = store.insert_trades("tenant-a", [_buy("TRD-1")])
    second = store.insert_trades("tenant-a", [_buy("TRD-1", price=12.5)])
    assert first["inserted"] == ["TRD-1"] and first["updated"] == []
    assert second["inserted"] == [] and second["updated"] == ["TRD-1"]
    rows = store.list_trades("tenant-a")
    assert len(rows) == 1
    assert rows[0]["price"] == 12.5


def test_list_trades_filters_within_the_tenant(store) -> None:
    store.insert_trades(
        "tenant-a",
        [
            _buy("TRD-1"),
            _buy("TRD-2", symbol="OTHER-SYM", account_id="ACC-2", trade_date="2026-09-05"),
        ],
    )
    assert [r["trade_id"] for r in store.list_trades("tenant-a", symbol="OTHER-SYM")] == ["TRD-2"]
    assert [r["trade_id"] for r in store.list_trades("tenant-a", account_id="ACC-TOY")] == ["TRD-1"]
    assert [r["trade_id"] for r in store.list_trades("tenant-a", start="2026-09-04")] == ["TRD-2"]
    assert [r["trade_id"] for r in store.list_trades("tenant-a", end="2026-09-02")] == ["TRD-1"]
    assert len(store.list_trades("tenant-a", limit=1)) == 1


def test_insert_trades_refuses_an_unknown_tenant(store) -> None:
    """Fail closed: no orphan rows without a tenant to own them."""
    with pytest.raises(StoreError):
        store.insert_trades("nobody", [_buy("TRD-1")])
    assert store.list_trades("nobody") == []


def test_insert_trades_rejects_an_invalid_side(store) -> None:
    with pytest.raises(StoreError):
        store.insert_trades("tenant-a", [_buy("TRD-1", side="TRANSFER")])


def test_accounts_round_trip(store) -> None:
    created = store.upsert_account(
        "tenant-a",
        {
            "account_id": "ACC-Toy",
            "name": "Toy Account",
            "broker": "Toy Broker",
            "initial_balance": 50000.0,
        },
    )
    assert created["account_id"] == "ACC-Toy"
    assert created["currency"] == "CNY"
    updated = store.upsert_account("tenant-a", {"account_id": "ACC-Toy", "name": "Renamed"})
    assert updated["name"] == "Renamed"
    assert updated["broker"] == ""
    assert [a["account_id"] for a in store.list_accounts("tenant-a")] == ["ACC-Toy"]


def test_generated_account_id_is_stable_across_the_upsert(store) -> None:
    first = store.upsert_account("tenant-a", {"name": "No Id Given"})
    rows = store.list_accounts("tenant-a")
    assert len(rows) == 1
    assert rows[0]["account_id"] == first["account_id"]


def test_backtest_runs_round_trip_with_json_payloads(store) -> None:
    store.save_backtest_run(
        "tenant-a",
        {
            "run_id": "BT-1",
            "strategy_name": "sma-cross-toy",
            "symbol": "TOY-SYM",
            "interval": "1d",
            "metrics": {"total_net_pnl": 12.5, "trade_count": 2},
            "equity_curve": [{"exit_time": "2026-09-03", "cumulative_pnl": 12.5}],
            "spec": {"version": 1, "name": "sma-cross-toy"},
        },
    )
    runs = store.list_backtest_runs("tenant-a")
    assert len(runs) == 1
    assert runs[0]["metrics"]["total_net_pnl"] == 12.5
    assert runs[0]["equity_curve"][0]["cumulative_pnl"] == 12.5
    assert runs[0]["spec"]["version"] == 1
    assert runs[0]["interval"] == "1d"


def test_save_backtest_run_is_an_upsert(store) -> None:
    store.save_backtest_run("tenant-a", {"run_id": "BT-1", "metrics": {"total_net_pnl": 1.0}})
    store.save_backtest_run("tenant-a", {"run_id": "BT-1", "metrics": {"total_net_pnl": 2.0}})
    runs = store.list_backtest_runs("tenant-a")
    assert len(runs) == 1
    assert runs[0]["metrics"]["total_net_pnl"] == 2.0


def test_save_bars_is_idempotent_and_load_bars_returns_them_in_order(store) -> None:
    store.save_bars("tenant-a", [_bar(10.5), _bar(11.5, open_time="2026-09-02T00:00:00Z")])
    # Re-fetching the first bar corrects it rather than duplicating the row.
    store.save_bars("tenant-a", [_bar(10.9, volume=2000.0)])
    bars = store.load_bars("tenant-a", symbol="TOY-SYM", interval="1d")
    assert [b["open_time"] for b in bars] == ["2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"]
    assert bars[0]["close"] == 10.9
    assert bars[0]["volume"] == 2000.0
    # The row is exposed as interval, matching the market-data Bar shape.
    assert bars[0]["interval"] == "1d"
    assert store.load_bars(
        "tenant-a", symbol="TOY-SYM", interval="1d", start="2026-09-02T00:00:00Z"
    ) == [bars[1]]


def test_audit_records_and_lists_within_a_tenant(store) -> None:
    entry = store.audit("tenant-a", "manual_note", record_id="TRD-1", detail={"note": "toy"})
    assert entry["action"] == "manual_note"
    assert entry["detail"] == {"note": "toy"}
    actions = [row["action"] for row in store.list_audit("tenant-a")]
    assert "manual_note" in actions


def test_every_response_carries_the_safety_declaration(store) -> None:
    """The product never returns a payload without the execution-ban declaration."""
    from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

    payloads = [
        store.insert_trades("tenant-a", [_buy("TRD-1")]),
        store.save_bars("tenant-a", [_bar(10.5)]),
    ]
    for payload in payloads:
        assert payload["safety"] == SAFETY_DECLARATION


# --------------------------------------------------------------- isolation


def test_tenant_b_cannot_read_tenant_a_trades(store) -> None:
    """DoD: two users in one store cannot read each other's trades."""
    store.insert_trades("tenant-a", [_buy("TRD-A1"), _buy("TRD-A2")])
    store.insert_trades("tenant-b", [_buy("TRD-B1")])

    a_ids = {row["trade_id"] for row in store.list_trades("tenant-a")}
    b_rows = store.list_trades("tenant-b")
    b_ids = {row["trade_id"] for row in b_rows}

    assert a_ids == {"TRD-A1", "TRD-A2"}
    assert b_ids == {"TRD-B1"}
    # The explicit DoD assertion: B sees none of A's rows.
    assert a_ids & b_ids == set()
    assert "TRD-A1" not in b_ids and "TRD-A2" not in b_ids
    # And a filter cannot be used to reach across the boundary.
    assert store.list_trades("tenant-b", symbol="TOY-SYM") == b_rows
    assert store.list_trades("tenant-b", account_id="ACC-TOY") == b_rows


def test_tenant_isolation_covers_every_tenant_scoped_table(store) -> None:
    """Isolation is not just the trades table: every scope is checked."""
    store.insert_trades("tenant-a", [_buy("TRD-A1")])
    store.upsert_account("tenant-a", {"account_id": "ACC-A", "name": "A Account"})
    store.save_backtest_run("tenant-a", {"run_id": "BT-A", "metrics": {"n": 1}})
    store.save_bars("tenant-a", [_bar(10.5)])
    store.audit("tenant-a", "manual_note", record_id="TRD-A1")

    assert store.list_trades("tenant-b") == []
    assert store.list_accounts("tenant-b") == []
    assert store.list_backtest_runs("tenant-b") == []
    assert store.load_bars("tenant-b", symbol="TOY-SYM", interval="1d") == []
    assert store.list_audit("tenant-b") == []


def test_a_trade_id_owned_by_a_is_still_creatable_by_b(store) -> None:
    """The trade_id is unique per tenant, so two tenants can share an id value."""
    store.insert_trades("tenant-a", [_buy("SHARED-ID", price=10.0)])
    store.insert_trades("tenant-b", [_buy("SHARED-ID", price=20.0)])
    a_row = store.list_trades("tenant-a")[0]
    b_row = store.list_trades("tenant-b")[0]
    assert (a_row["user_id"], a_row["price"]) == ("tenant-a", 10.0)
    assert (b_row["user_id"], b_row["price"]) == ("tenant-b", 20.0)


def test_two_tenant_directories_are_two_databases(tmp_path) -> None:
    """The local layout gives each tenant its own file, not a shared one."""
    first = open_store(tmp_path / "tenant-a")
    second = open_store(tmp_path / "tenant-b")
    try:
        first.create_user("tenant-a")
        second.create_user("tenant-b")
        first.insert_trades("tenant-a", [_buy("TRD-A1")])
        assert len(first.list_trades("tenant-a")) == 1
        assert second.list_trades("tenant-b") == []
        assert first.database_path != second.database_path
    finally:
        first.close()
        second.close()


# ------------------------------------------------------- open_store routing


def test_open_store_rejects_hosted_mode_without_a_postgres_url(tmp_path) -> None:
    with pytest.raises(StoreError) as excinfo:
        open_store(tmp_path / "local-file.db", mode=MODE_HOSTED)
    assert "postgres" in str(excinfo.value).lower()


def test_open_store_rejects_an_unknown_mode(tmp_path) -> None:
    with pytest.raises(StoreError):
        open_store(tmp_path / "store.db", mode="cloud")


@pytest.mark.parametrize(
    "url", ["postgresql://toy:toy@localhost:5432/toy", "postgres://toy:toy@localhost/toy"]
)
def test_postgres_urls_route_to_the_hosted_engine(url) -> None:
    """No connection is attempted until connect() is called."""
    opened = open_store(url, mode=MODE_HOSTED)
    assert opened.engine == "postgres"


# ----------------------------------------- psycopg is never required to import


def _blocked_psycopg(monkeypatch) -> None:
    """Make any psycopg import fail, as if the extra were not installed."""
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ImportError("No module named 'psycopg'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)


def test_importing_the_storage_package_needs_no_psycopg(monkeypatch) -> None:
    """DoD: importing the storage package succeeds with psycopg absent."""
    _blocked_psycopg(monkeypatch)
    for name in [
        name
        for name in list(sys.modules)
        if name.startswith("smartmoney_cub_harness.trader.storage")
    ]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    module = importlib.import_module("smartmoney_cub_harness.trader.storage")

    assert module.open_store is not None
    assert module.StoreError is not None
    assert module.TenantStore is not None
    # Importing the package did not pull in a module the driver owns.
    assert "psycopg" not in sys.modules


def test_hosted_store_without_the_driver_reports_the_install_hint(monkeypatch) -> None:
    """DoD: a missing driver is a StoreError with the install hint, not ImportError."""
    _blocked_psycopg(monkeypatch)
    opened = open_store("postgresql://toy:toy@localhost:5432/toy", mode=MODE_HOSTED)

    with pytest.raises(StoreError) as excinfo:
        opened.connect()

    message = str(excinfo.value)
    assert INSTALL_HINT in message
    assert "psycopg" in message


def test_sqlite_engine_still_opens_when_the_driver_import_fails(monkeypatch) -> None:
    """The default local path never touches the hosted driver."""
    _blocked_psycopg(monkeypatch)
    opened = open_store(":memory:", mode=MODE_LOCAL)
    try:
        assert opened.engine == "sqlite"
    finally:
        opened.close()


# ------------------------------------- postgres source audit (grep-style DoD)

SQL_START = re.compile(r"\s*(SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)
PREDICATE_START = re.compile(r"\s*(SELECT|UPDATE|DELETE)\b", re.IGNORECASE)


def _sql_literals(node: ast.AST) -> list[str]:
    """SQL statements inside one function body."""
    found: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if SQL_START.match(child.value):
                found.append(child.value)
    return found


def _function_defs(path: Path) -> dict[str, ast.AST]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_every_tenant_scoped_postgres_method_greps_for_user_id() -> None:
    """DoD: every tenant-scoped query in postgres_store.py has a user_id predicate.

    The module source is audited rather than trusted, because this engine cannot
    execute on a machine without a database. Each tenant-scoped method must carry
    at least one SQL statement, every predicate-bearing statement (SELECT,
    UPDATE, DELETE) must contain the literal user_id = %s, and every INSERT must
    name the user_id column. A later edit that assembles SQL without the
    predicate therefore fails this test.
    """
    functions = _function_defs(POSTGRES_SOURCE)
    for method in TENANT_SCOPED_METHODS:
        assert method in functions, f"{method} is missing from postgres_store.py"
        statements = _sql_literals(functions[method])
        assert statements, f"{method} contains no SQL statement"
        for statement in statements:
            assert "user_id" in statement, f"{method} has SQL without user_id: {statement!r}"
            if PREDICATE_START.match(statement):
                assert "user_id = %s" in statement, (
                    f"{method} has a predicate-bearing statement without"
                    f" 'user_id = %s': {statement!r}"
                )


def test_postgres_module_source_never_imports_psycopg_at_module_level() -> None:
    """A top-level import would make the package unimportable without the extra."""
    tree = ast.parse(POSTGRES_SOURCE.read_text(encoding="utf-8"))
    top_level_imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level_imports.append(node.module)

    assert not any(name.startswith("psycopg") for name in top_level_imports)
    # And the lazy import really is inside connect().
    assert "import psycopg" in POSTGRES_SOURCE.read_text(encoding="utf-8")


def test_sqlite_engine_scopes_every_predicate_to_a_user() -> None:
    """The local engine repeats the rule, so both engines are auditable alike.

    Every SQL statement in the local engine that touches a tenant table must
    scope on user_id. This is the SQLite half of the isolation proof: the
    Postgres half is the source audit above, and both are held to the same
    requirement.
    """
    tenant_tables = ("trades", "accounts", "backtest_runs", "market_bars", "audit_log")
    source = SQLITE_SOURCE.read_text(encoding="utf-8")
    statements = re.findall(r'"(?:SELECT|INSERT|UPDATE|DELETE)[^"]+"', source)
    assert statements, "no SQL statements found in sqlite_store.py"
    for statement in statements:
        if any(table in statement for table in tenant_tables):
            assert "user_id" in statement, statement


def test_storage_modules_import_no_third_party_runtime() -> None:
    """The core package must stay installable offline, storage included."""
    for path in (STORAGE_SOURCE, SQLITE_SOURCE, POSTGRES_SOURCE):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                imported.append(node.module.split(".")[0])
        assert imported, path.name
        # Every import is stdlib, the package itself, or the lazily-loaded driver.
        allowed_local = {"smartmoney_cub_harness", "psycopg"}
        third_party = [
            name
            for name in imported
            if name not in allowed_local and name not in sys.stdlib_module_names
        ]
        assert third_party == [], (path.name, third_party)


# ------------------------------------------------------------ pyproject


def test_hosted_extra_is_declared_and_core_dependencies_stay_empty() -> None:
    payload = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    optional = re.search(
        r"\[project\.optional-dependencies\]\n(.*?)(?=\n\[)", payload, re.S
    )
    assert optional is not None
    assert 'hosted = ["psycopg[binary]>=3.2"]' in optional.group(1)
    # The brief is explicit: adding the extra must not add a core dependency.
    core = re.search(r"(?ms)^dependencies\s*=\s*(\[.*?\])", payload)
    assert core is not None
    assert core.group(1).strip() == "[]"


# ------------------------------------------------- real Postgres, opt-in

POSTGRES_TEST_URL = os.environ.get("SMARTMONEY_TEST_DATABASE_URL") or None

requires_postgres = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="set SMARTMONEY_TEST_DATABASE_URL to run the hosted store tests",
)


@pytest.fixture()
def hosted_store():
    """A real Postgres store, only when a database URL is provided."""
    opened = open_store(POSTGRES_TEST_URL, mode=MODE_HOSTED)
    opened.migrate()
    opened.create_user("tenant-a", tenant_id="toy-a")
    opened.create_user("tenant-b", tenant_id="toy-b")
    yield opened
    # Leave the shared database as it was found.
    conn = opened._connection()
    for table in ("trades", "accounts", "backtest_runs", "market_bars", "audit_log"):
        conn.execute(
            f"DELETE FROM {table} WHERE user_id IN (%s, %s)", ("tenant-a", "tenant-b")
        )
    conn.commit()
    opened.close()


@requires_postgres
def test_hosted_isolation_matches_the_sqlite_contract(hosted_store) -> None:
    """The same isolation assertions, against the real hosted engine."""
    hosted_store.insert_trades("tenant-a", [_buy("TRD-A1")])
    hosted_store.insert_trades("tenant-b", [_buy("TRD-B1")])
    assert {r["trade_id"] for r in hosted_store.list_trades("tenant-a")} == {"TRD-A1"}
    assert {r["trade_id"] for r in hosted_store.list_trades("tenant-b")} == {"TRD-B1"}


@requires_postgres
def test_hosted_upserts_do_not_cross_tenants(hosted_store) -> None:
    hosted_store.insert_trades("tenant-a", [_buy("SHARED-ID", price=10.0)])
    hosted_store.insert_trades("tenant-b", [_buy("SHARED-ID", price=20.0)])
    assert hosted_store.list_trades("tenant-a")[0]["price"] == 10.0
    assert hosted_store.list_trades("tenant-b")[0]["price"] == 20.0
    hosted_store.upsert_account("tenant-a", {"account_id": "ACC-1", "name": "A"})
    assert hosted_store.list_accounts("tenant-b") == []
    hosted_store.save_bars("tenant-a", [_bar(1.0)])
    assert hosted_store.load_bars("tenant-b", symbol="TOY-SYM", interval="1d") == []
