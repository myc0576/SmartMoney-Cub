"""Where one local user's state lives, for both of the product's front doors.

`smcub workbench` is the documented local front door -- it is also what
`npx smartmoney-cub` runs -- and `smcub trader serve --mode local` is the same
product on the same socket. They used to answer "where is my journal?"
differently, and in two ways at once: the state root was `state/convergence`
against `state/trader`, and the tenant store sat one level apart inside it, at
`<root>/journal/` for the workbench and directly at `<root>/` for the trader
entry point. A user who imported fills through one of them then opened the other
and found an empty account, while both were behaving exactly as written.

Two literals that must agree is a drift bug waiting for a quiet afternoon, so
both entry points now resolve through this module and there is one answer to
give. The interface, the journal, the rule library, and the plugin state all
hang off the same root, which is what makes an imported fill immediately
reviewable.

Resolving a root keeps the older layout readable rather than stranding it. A
journal that already exists is never abandoned in place: an existing flat store
wins, the nested store is used when only it exists, and a root with neither gets
the flat layout, which is the one the trader entry point has always used.
"""

from __future__ import annotations

from pathlib import Path

# The local single-user state root. One value, because two entry points read it.
LOCAL_STATE_DIR = "state/trader"

# The nested layout the workbench originally shipped, and the store's file name.
LEGACY_JOURNAL_DIRNAME = "journal"
TENANT_DB_BASENAME = "trader_store.db"


def local_state_root(state_dir: str | Path | None = None) -> Path:
    """The state root for one local user, with an explicit path taking priority.

    An explicit path is used as given, including a relative one, so a caller can
    point a throwaway run at a temporary directory without this module deciding
    it knows better.
    """
    return Path(state_dir) if state_dir else Path(LOCAL_STATE_DIR)


def journal_dir(root: str | Path) -> Path:
    """The directory that holds the tenant store for a state root.

    The order of these checks is the compatibility guarantee. A flat store is
    returned whenever it exists, so unifying the two entry points cannot shadow a
    journal someone is already using. The nested directory is returned only when
    no flat store exists, which is what keeps a workbench-era `<root>/journal/`
    readable after this change. A root with neither gets the flat layout, so a
    fresh user starts on the new shape instead of inheriting the old one.
    """
    root_path = Path(root)
    if (root_path / TENANT_DB_BASENAME).is_file():
        return root_path
    nested = root_path / LEGACY_JOURNAL_DIRNAME
    if (nested / TENANT_DB_BASENAME).is_file():
        return nested
    return root_path

