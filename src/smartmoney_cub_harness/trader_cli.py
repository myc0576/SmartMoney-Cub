"""The trader serve command: one process, both products, one port.

Why this file exists rather than living inside cli.py: cli.py is the argument
surface, and this file is the deployment behavior, so a reviewer can read what a
hosted deployment does in one screen. cli.py keeps a lazy import of the entry
point and calls it.

The two modes are deliberately asymmetric, and the asymmetry is the point. A
local run is a single offline user with no authentication, and its journal is a
directory on this machine. A hosted run is one alphatech tenant per platform
identity and its journal is Postgres; it refuses to start rather than quietly
writing a local file, because a hosted tenant that lands in a local database
looks like it worked and is the worst kind of failure.

The review workbench is mounted on the same socket, so one deployment serves
both products from one process and one port.
"""

from __future__ import annotations

import sys
from pathlib import Path

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.auth import MODE_HOSTED, MODE_LOCAL
from smartmoney_cub_harness.trader.storage import StoreError, open_store

DEFAULT_STATE_DIR = "state/trader"
DEFAULT_PORT = 8787


def resolve_mode(value: str | None) -> str:
    """Normalize the mode argument, refusing anything the product does not have."""
    selected = str(value or MODE_LOCAL).strip().lower()
    if selected not in (MODE_LOCAL, MODE_HOSTED):
        raise ValueError("mode must be local or hosted, got " + repr(value))
    return selected


def resolve_store_location(
    mode: str, *, database_url: str | None, state_dir: str | None
) -> tuple[str, str]:
    """Resolve where the journal lives, and refuse an incoherent pair.

    Passing a postgres URL in local mode is refused rather than ignored: the
    caller clearly meant hosted, and silently writing to a local file would
    discard their data from where they expect it.
    """
    url = str(database_url or "").strip()
    directory = str(state_dir or "").strip()
    if mode == MODE_HOSTED:
        if not url:
            raise ValueError(
                "hosted mode needs --database-url with a postgres URL;"
                " no local fallback is offered on purpose"
            )
        return url, MODE_HOSTED
    if url:
        raise ValueError(
            "local mode does not use --database-url; drop it or pass --mode hosted"
        )
    return directory or DEFAULT_STATE_DIR, MODE_LOCAL


def run_trader_serve(
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    mode: str = MODE_LOCAL,
    database_url: str | None = None,
    state_dir: str | None = None,
    open_browser: bool = True,
    token: str | None = None,
) -> int:
    from smartmoney_cub_harness.trader.api import TraderService
    from smartmoney_cub_harness.workbench.server import (
        bundled_asset_dir,
        is_loopback,
        start_workbench,
    )

    try:
        selected = resolve_mode(mode)
        location, store_mode = resolve_store_location(
            selected, database_url=database_url, state_dir=state_dir
        )
    except ValueError as error:
        sys.stderr.write(str(error) + "\n")
        return 2

    if not is_loopback(host) and not token:
        sys.stderr.write(
            "refusing to bind " + host + " without --token: "
            "a trading journal must not be exposed on a network by default\n"
        )
        return 2

    try:
        store = open_store(location, mode=store_mode)
    except StoreError as error:
        sys.stderr.write("could not open the tenant store: " + str(error) + "\n")
        return 2

    service = TraderService(store, auth_mode=selected)

    def announce(url: str) -> None:
        sys.stderr.write("smartmoney-cub trader: " + url + "\n")
        sys.stderr.write("mode: " + selected + "\n")
        if selected == MODE_LOCAL:
            sys.stderr.write("store: " + str(location) + "\n")
        else:
            # A database URL can carry a password, so only its scheme is reported.
            sys.stderr.write("store: " + str(location).split("://")[0] + "://(configured)\n")
        sys.stderr.write(SAFETY_DECLARATION + "\n")

    workbench_root = Path(DEFAULT_STATE_DIR)
    if selected == MODE_LOCAL and state_dir:
        workbench_root = Path(state_dir)

    try:
        start_workbench(
            root=workbench_root,
            host=host,
            port=port,
            asset_dir=bundled_asset_dir(),
            open_browser=open_browser,
            access_token=token,
            trader_service=service,
            ready=announce,
        )
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()
    return 0

