"""Trader product: journal, analytics, market data, backtest, and replay.

This subpackage is the product surface layered on the harness control plane.
The harness contract in docs/harness-contract.md governs it: read-only with
respect to markets and execution, writable with respect to the user's own
tenant-scoped journal.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"

