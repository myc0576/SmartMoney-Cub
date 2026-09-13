"""Request authentication for the trader product.

Every tenant-scoped entry point starts by resolving a request to an
AuthContext, so tenancy has exactly one origin. The product never stores
credentials of its own: hosted requests are authenticated by the alphatech
platform, and offline runs use a single fixed local user.
"""

from __future__ import annotations

from smartmoney_cub_harness.trader.auth.identity import (
    AuthContext,
    AuthError,
    resolve_identity,
)

__all__ = ["AuthContext", "AuthError", "resolve_identity"]
