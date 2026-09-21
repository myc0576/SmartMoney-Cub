from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# ---- one local account, two front doors ------------------------------------
#
# 'smcub workbench' is the documented local front door and 'smcub trader serve
# --mode local' is the same product on the same socket. They disagreed about
# where the journal lived in two ways at once -- a different state root, and a
# different depth inside it -- so an imported fill was invisible from the other
# entry point, and the second one to start looked like it had lost the data.
# These tests hold the two answers together, because nothing else will: the
# failure is silent and looks like an empty account rather than an error.


def test_both_front_doors_default_to_the_same_state_root() -> None:
    from smartmoney_cub_harness import convergence_cli, trader_cli

    assert convergence_cli.DEFAULT_STATE_DIR == trader_cli.DEFAULT_STATE_DIR


def test_the_server_signature_defaults_to_the_same_root() -> None:
    """A third literal in start_workbench() is how these drifted before."""
    import inspect

    from smartmoney_cub_harness.local_state import LOCAL_STATE_DIR
    from smartmoney_cub_harness.workbench import server

    default = inspect.signature(server.start_workbench).parameters["root"].default
    assert default == LOCAL_STATE_DIR


def test_both_front_doors_resolve_the_same_journal_file(tmp_path: Path) -> None:
    """The end-to-end claim: one root, one store, whichever door opened it."""
    from smartmoney_cub_harness.local_state import journal_dir, local_state_root
    from smartmoney_cub_harness.trader.api import TraderService
    from smartmoney_cub_harness.trader.auth import MODE_LOCAL
    from smartmoney_cub_harness.trader.auth.identity import LOCAL_CONTEXT
    from smartmoney_cub_harness.trader.storage import open_store

    root = tmp_path / "state"
    # The workbench resolves the root it will hand the server; the trader entry
    # point resolves its store location. Both must name the same store file.
    workbench_journal = journal_dir(local_state_root(str(root)))
    trader_journal = journal_dir(root)

    assert workbench_journal == trader_journal

    store = open_store(workbench_journal, mode=MODE_LOCAL)
    try:
        service = TraderService(store, auth_mode=MODE_LOCAL)
        service.import_trades(
            LOCAL_CONTEXT,
            rows=[
                {
                    "trade_id": "T-BUY",
                    "symbol": "600519",
                    "side": "BUY",
                    "trade_date": "2026-09-01",
                    "price": 100.0,
                    "quantity": 10,
                },
            ],
        )
        # A fill written through the resolved path is visible from the same path,
        # which is the property that was false while the roots disagreed.
        reopened = open_store(workbench_journal, mode=MODE_LOCAL)
        try:
            assert len(reopened.list_trades(LOCAL_CONTEXT.user_id)) == 1
        finally:
            reopened.close()
    finally:
        store.close()


def test_a_workbench_era_journal_directory_still_opens(tmp_path: Path) -> None:
    """The older nested layout is read, not abandoned.

    Unifying the roots must not orphan a journal someone already has on disk, so
    a root that only carries 'journal/trader_store.db' still resolves to that
    store rather than to a new, empty file beside it.
    """
    from smartmoney_cub_harness.local_state import journal_dir

    root = tmp_path / "convergence"
    nested = root / "journal"
    nested.mkdir(parents=True)
    (nested / "trader_store.db").write_bytes(b"")

    assert journal_dir(root) == nested


def test_an_existing_flat_store_wins_over_a_nested_one(tmp_path: Path) -> None:
    """The flat store is the current layout, so it must not be shadowed.

    A root can hold both during a migration. The one the trader entry point has
    always written is the one that must open, or a migration would silently
    switch a user onto a stale copy.
    """
    from smartmoney_cub_harness.local_state import journal_dir

    root = tmp_path / "state"
    (root / "journal").mkdir(parents=True)
    (root / "journal" / "trader_store.db").write_bytes(b"")
    (root / "trader_store.db").write_bytes(b"")

    assert journal_dir(root) == root


def test_a_fresh_root_starts_on_the_flat_layout(tmp_path: Path) -> None:
    """Neither layout exists yet, so a new user gets the current one."""
    from smartmoney_cub_harness.local_state import journal_dir

    assert journal_dir(tmp_path / "brand-new") == tmp_path / "brand-new"


def test_run_workbench_opens_the_journal_the_trader_door_uses(tmp_path: Path) -> None:
    """Drive the shipped command and read back the store it actually opened."""
    from smartmoney_cub_harness.convergence_cli import run_workbench
    from smartmoney_cub_harness.local_state import journal_dir

    captured: dict[str, object] = {}

    def fake_start_workbench(**kwargs) -> None:
        captured.update(kwargs)

    server_module = importlib.import_module("smartmoney_cub_harness.workbench.server")
    original = server_module.start_workbench
    server_module.start_workbench = fake_start_workbench
    try:
        code = run_workbench(host="127.0.0.1", port=8787, state_dir=str(tmp_path), open_browser=False)
    finally:
        server_module.start_workbench = original

    assert code == 0
    service = captured.get("trader_service")
    assert service is not None, "run_workbench did not mount the trader surface"

    # The store behind the mounted service is the file the shared rule resolves.
    store = getattr(service, "store", None)
    assert store is not None
    opened = Path(getattr(store, "database_path", ""))
    assert opened == journal_dir(tmp_path) / "trader_store.db"


@pytest.mark.parametrize("command", ["workbench", "trader"])
def test_the_cli_exposes_both_front_doors(command: str) -> None:
    """Guard the two spellings the README documents, so a rename is noticed."""
    from smartmoney_cub_harness import cli

    parser = cli.build_parser()
    actions = [a for a in parser._actions if getattr(a, "choices", None)]
    assert any(command in (a.choices or {}) for a in actions), command
