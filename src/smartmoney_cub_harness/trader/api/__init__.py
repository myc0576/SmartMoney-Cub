"""The trader product's HTTP surface.

Exactly one name is exported on purpose: the workbench server mounts this
product by handing an AuthContext-resolving store service to routes.dispatch,
and nothing else in the process needs to know how the product is put together.

    from smartmoney_cub_harness.trader.api import TraderService

The route table and the dispatch function live in routes.py so the server's
mount is three lines and cannot drift from what docs/trader-api.md documents.
"""

from __future__ import annotations

from smartmoney_cub_harness.trader.api.service import (
    TraderRequestError,
    TraderService,
    build_tenant_ledger,
    parse_delimited_rows,
    parse_import_payload,
)

__all__ = [
    "TraderRequestError",
    "TraderService",
    "build_tenant_ledger",
    "parse_delimited_rows",
    "parse_import_payload",
]

