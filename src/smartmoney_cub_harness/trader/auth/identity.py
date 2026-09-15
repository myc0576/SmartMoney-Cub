"""Identity resolution: which user and tenant a request acts as.

Why this module exists: the product is hosted behind the alphatech platform's
login, but it also has to run offline as one local user for CI and for a
trader's own machine. Both paths funnel through resolve_identity so every
caller has the same context to filter on, and so the platform mechanics stay in
one adapter file (smartmoney_cub_harness.trader.auth.alphatech).

The two modes are deliberately not interchangeable in failure: local is fixed
and reads nothing from the request, while hosted either produces a verified
identity or raises. There is no anonymous tenant to fall into.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

MODE_HOSTED = "hosted"
MODE_LOCAL = "local"

# The offline user is a single fixed identity so local runs and CI are
# reproducible, and so a developer's real platform identity cannot leak into a
# local store by accident.
LOCAL_USER_ID = "local"
LOCAL_TENANT_ID = "local"
LOCAL_DISPLAY_NAME = "Local User"


class AuthError(Exception):
    """A request could not be resolved to a verified identity."""


@dataclass(frozen=True)
class AuthContext:
    """The identity a request acts as.

    user_id is the tenant-scoped key every store call filters on, and tenant_id
    is the tenant namespace it belongs to; in hosted mode the tenant is one
    platform user, so the two are equal. platform_user_id is the raw alphatech
    identifier and is empty in local mode, which keeps platform identifiers out
    of the offline path entirely.
    """

    user_id: str
    tenant_id: str
    display_name: str
    mode: str
    platform_user_id: str = ""

    @property
    def safety(self) -> str:
        """The execution-ban declaration every product response carries."""
        return SAFETY_DECLARATION


LOCAL_CONTEXT = AuthContext(
    user_id=LOCAL_USER_ID,
    tenant_id=LOCAL_TENANT_ID,
    display_name=LOCAL_DISPLAY_NAME,
    mode=MODE_LOCAL,
    platform_user_id="",
)


def local_context() -> AuthContext:
    """Return the fixed offline identity. No request data is consulted."""
    return LOCAL_CONTEXT


def resolve_identity(headers: Mapping[str, str], *, mode: str = MODE_HOSTED) -> AuthContext:
    """Resolve an incoming request to an identity, or raise AuthError.

    The mode selects the path rather than the request contents, so a malformed
    or hostile request cannot move itself from hosted to local.
    """
    selected = str(mode or "").strip().lower()
    if selected == MODE_LOCAL:
        return local_context()
    if selected == MODE_HOSTED:
        # Imported here on purpose: the adapter imports AuthContext and
        # AuthError from this module, so a module-level import would be a cycle.
        from smartmoney_cub_harness.trader.auth.alphatech import resolve_platform_identity

        return resolve_platform_identity(headers)
    raise AuthError(f"unknown auth mode: {mode!r}")
