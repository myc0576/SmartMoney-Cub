"""alphatech platform identity adapter: the only file that knows the protocol.

The product runs behind the alphatech platform's login. The platform is a
new-api deployment, so the caller's login is a session cookie and
GET /api/user/self answers with the current user, or 401 when the session is
not valid. A second mode accepts an explicitly signed identity header, which is
the fallback if the platform team prefers a signed header over cookie
forwarding; the ALPHATECH_AUTH_MODE environment variable selects between them.

Every guess this file makes about the platform lives in the table below, so a
wrong guess is a one-file change and never a hunt through the product.

Platform protocol assumptions

| Assumption | What this file uses | Where to change it |
| --- | --- | --- |
| Identity endpoint | GET {ALPHATECH_BASE_URL}/api/user/self | SELF_ENDPOINT |
| Base URL | ALPHATECH_BASE_URL, default https://alphatech.net.cn (the site root, not the /v1 model-gateway base the agent providers use) | DEFAULT_BASE_URL, base_url() |
| Unauthenticated answer | HTTP 401; a 200 body carrying success: false is also treated as unauthenticated | _context_from_self_response |
| Auth mechanism, session mode (default) | the caller's platform session cookie, forwarded in the Cookie request header; no header of ours is trusted | forwarded_cookie_header, fetch_platform_user |
| Session cookie name | "session". Used only to narrow what is forwarded; when that name is absent the whole Cookie header is forwarded, so a wrong guess degrades to sending more than needed instead of failing every request | SESSION_COOKIE_NAME, forwarded_cookie_header |
| Identity field | top-level "id" in the JSON body of /api/user/self | _context_from_self_response |
| Display name | "display_name", else "username", else the platform id | DISPLAY_NAME_FIELDS |
| Tenant mapping | tenant_id = "alphatech:" + platform_user_id; one tenant per platform user, identical in both modes | TENANT_PREFIX, tenant_id_for |
| Signed-header mode (fallback) | X-AlphaTech-User, X-AlphaTech-Timestamp (unix seconds), X-AlphaTech-Signature = HMAC-SHA256 hex over "user_id:timestamp" keyed by ALPHATECH_SSO_SECRET | USER_HEADER, TIMESTAMP_HEADER, SIGNATURE_HEADER, hmac_message |
| Replay window | a signature is accepted within +/-300 seconds of the platform clock, so a stale one cannot be replayed | SIGNATURE_MAX_AGE_SECONDS |
| Mode switch | ALPHATECH_AUTH_MODE = session (default) or hmac; any other value fails closed | platform_auth_mode, resolve_platform_identity |
| Lookup caching | a successful session lookup is cached for 60 seconds, keyed by the forwarded cookie, so it is not a platform round trip per request | SESSION_CACHE_TTL_SECONDS, clear_identity_cache |
| Transport failure | a timeout, DNS failure, or unreadable body means "cannot verify", which fails closed | fetch_platform_user |

If the platform team instead supplies a signed header, the switch is
ALPHATECH_AUTH_MODE=hmac plus ALPHATECH_SSO_SECRET. If their header names, the
timestamp unit, or the signed message differ, align the three header constants
and hmac_message with what they send; nothing outside this file changes.

Importing this module performs no network access and reads no environment
variable; configuration is read at request time so tests and operators control
it without import-order surprises.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping

from smartmoney_cub_harness.trader.auth.identity import AuthContext, AuthError

DEFAULT_BASE_URL = "https://alphatech.net.cn"
SELF_ENDPOINT = "/api/user/self"

AUTH_MODE_ENV = "ALPHATECH_AUTH_MODE"
BASE_URL_ENV = "ALPHATECH_BASE_URL"
SSO_SECRET_ENV = "ALPHATECH_SSO_SECRET"

MODE_SESSION = "session"
MODE_HMAC = "hmac"
DEFAULT_PLATFORM_AUTH_MODE = MODE_SESSION

COOKIE_HEADER = "Cookie"
SESSION_COOKIE_NAME = "session"
USER_HEADER = "X-AlphaTech-User"
TIMESTAMP_HEADER = "X-AlphaTech-Timestamp"
SIGNATURE_HEADER = "X-AlphaTech-Signature"

SIGNATURE_MAX_AGE_SECONDS = 300
SESSION_CACHE_TTL_SECONDS = 60.0
REQUEST_TIMEOUT_SECONDS = 5.0

TENANT_PREFIX = "alphatech"
DISPLAY_NAME_FIELDS = ("display_name", "username")


@dataclass(frozen=True)
class SelfResponse:
    """The shape of a /api/user/self answer, decoupled from the transport."""

    status: int
    body: Any


def platform_auth_mode() -> str:
    configured = (os.environ.get(AUTH_MODE_ENV) or "").strip().lower()
    return configured or DEFAULT_PLATFORM_AUTH_MODE


def base_url() -> str:
    configured = (os.environ.get(BASE_URL_ENV) or "").strip()
    return (configured or DEFAULT_BASE_URL).rstrip("/")


def sso_secret() -> str:
    return (os.environ.get(SSO_SECRET_ENV) or "").strip()


def tenant_id_for(platform_user_id: str) -> str:
    """Map a platform user id to its stable tenant id.

    Prefixing keeps a platform identifier from being mistaken for a local user
    or for a future identity provider's id inside the same store.
    """
    return f"{TENANT_PREFIX}:{platform_user_id}"


def build_context(platform_user_id: Any, display_name: str = "") -> AuthContext:
    normalized = _normalize_platform_user_id(platform_user_id)
    tenant_id = tenant_id_for(normalized)
    return AuthContext(
        user_id=tenant_id,
        tenant_id=tenant_id,
        display_name=display_name or normalized,
        mode="hosted",
        platform_user_id=normalized,
    )


def resolve_platform_identity(headers: Mapping[str, str]) -> AuthContext:
    """Resolve a hosted request to an identity, or raise AuthError.

    Both modes fail closed: an unverifiable request raises rather than
    degrading to an anonymous tenant, and an unrecognized mode is an error
    rather than a silent fallback.
    """
    mode = platform_auth_mode()
    if mode == MODE_SESSION:
        return _resolve_session_identity(headers)
    if mode == MODE_HMAC:
        return _resolve_signed_identity(headers)
    raise AuthError(f"unknown {AUTH_MODE_ENV}: {mode!r}")


def forwarded_cookie_header(headers: Mapping[str, str]) -> str:
    """Return the Cookie value to forward to the platform, or "" when there is none.

    The platform's cookie name is an assumption, so the whole header is the
    fallback: forwarding a little extra is survivable, while depending on a
    wrong name would reject every request.
    """
    raw = _header(headers, COOKIE_HEADER).strip()
    if not raw:
        return ""
    for part in raw.split(";"):
        name, _, value = part.partition("=")
        if name.strip() == SESSION_COOKIE_NAME and value.strip():
            return f"{SESSION_COOKIE_NAME}={value.strip()}"
    return raw


def hmac_message(user_id: str, timestamp: str) -> bytes:
    """The exact bytes the platform signs. Changing this changes the contract."""
    return f"{user_id}:{timestamp}".encode("utf-8")


def fetch_platform_user(
    cookie_header: str,
    *,
    base_url: str,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
) -> SelfResponse:
    """Ask the platform who this cookie belongs to.

    Kept separate from the resolution logic so tests can stub the answer and
    assert that the suite makes no live call.
    """
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{SELF_ENDPOINT}",
        headers={COOKIE_HEADER: cookie_header},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return SelfResponse(
                status=int(getattr(response, "status", 200) or 0),
                body=_decode_body(response.read()),
            )
    except urllib.error.HTTPError as error:
        # 401 is the documented unauthenticated answer. Every other status lands
        # here too, because an answer we do not recognize cannot verify anyone.
        return SelfResponse(status=int(getattr(error, "code", 0) or 0), body=_safe_read(error))
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise AuthError(f"alphatech identity lookup failed: {type(error).__name__}") from error


def clear_identity_cache() -> None:
    """Drop cached session lookups; used by tests and when configuration changes."""
    with _CACHE_LOCK:
        _CACHE.clear()


_CACHE: dict[str, tuple[float, AuthContext]] = {}
_CACHE_LOCK = threading.Lock()


def _resolve_session_identity(headers: Mapping[str, str]) -> AuthContext:
    cookie_header = forwarded_cookie_header(headers)
    if not cookie_header:
        raise AuthError("no alphatech session cookie on the request")

    key = _cache_key(cookie_header)
    now = _now_seconds()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

    # The lookup happens outside the lock on purpose: a slow platform answer
    # must not block other tenants' requests.
    response = fetch_platform_user(cookie_header, base_url=base_url())
    context = _context_from_self_response(response)
    with _CACHE_LOCK:
        fetched_at = _now_seconds()
        _prune_expired(fetched_at)
        _CACHE[key] = (fetched_at + SESSION_CACHE_TTL_SECONDS, context)
    return context


def _resolve_signed_identity(headers: Mapping[str, str]) -> AuthContext:
    secret = sso_secret()
    if not secret:
        # Fail closed: with no shared secret nothing can be verified, so there
        # is no identity that would be safe to act as.
        raise AuthError(f"{SSO_SECRET_ENV} is not set; refusing to authenticate")

    user_id = _header(headers, USER_HEADER).strip()
    signature = _header(headers, SIGNATURE_HEADER).strip()
    timestamp = _header(headers, TIMESTAMP_HEADER).strip()
    if not (user_id and signature and timestamp):
        raise AuthError("signed identity headers are incomplete")

    signed_at = _parse_timestamp(timestamp)
    age = int(time.time()) - signed_at
    if not -SIGNATURE_MAX_AGE_SECONDS <= age <= SIGNATURE_MAX_AGE_SECONDS:
        raise AuthError(
            f"signed identity timestamp is outside the {SIGNATURE_MAX_AGE_SECONDS}s window"
        )

    expected = hmac.new(
        secret.encode("utf-8"), hmac_message(user_id, timestamp), sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise AuthError("signed identity signature does not match")

    # The header carries no display name, so the platform id stands in for it.
    return build_context(user_id)


def _context_from_self_response(response: SelfResponse) -> AuthContext:
    if response.status != 200:
        raise AuthError(f"alphatech rejected the platform session (status {response.status})")
    body = response.body
    if not isinstance(body, Mapping):
        raise AuthError("alphatech /api/user/self did not return a JSON object")
    if body.get("success") is False:
        raise AuthError("alphatech /api/user/self reported success=false")
    return build_context(body.get("id"), _display_name(body))


def _display_name(body: Mapping[str, Any]) -> str:
    for field in DISPLAY_NAME_FIELDS:
        value = body.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_platform_user_id(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        raise AuthError("alphatech did not return a usable platform user id")
    if isinstance(value, int):
        normalized = str(value)
    elif isinstance(value, str):
        normalized = value.strip()
    else:
        raise AuthError("alphatech returned a platform user id of an unsupported type")
    if not normalized:
        raise AuthError("alphatech returned an empty platform user id")
    return normalized


def _parse_timestamp(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise AuthError("signed identity timestamp is not an integer number of seconds") from None


def _header(headers: Mapping[str, str], name: str) -> str:
    """Look up a header case-insensitively, tolerating anything mapping-shaped.

    HTTP header names are case-insensitive, and callers hand us either a plain
    dict or the server's own header object, so the comparison happens here.
    """
    wanted = name.strip().lower()
    try:
        items = headers.items()
    except AttributeError:
        return ""
    for key, value in items:
        if str(key).strip().lower() == wanted:
            return "" if value is None else str(value)
    return ""


def _decode_body(raw: Any) -> Any:
    if not raw:
        return None
    try:
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    except UnicodeDecodeError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _safe_read(response: Any) -> Any:
    try:
        return _decode_body(response.read())
    except Exception:  # noqa: BLE001 - the HTTP status already decided the outcome
        return None


def _cache_key(cookie_header: str) -> str:
    return sha256(cookie_header.encode("utf-8")).hexdigest()


def _prune_expired(now: float) -> None:
    for key in [key for key, (expires_at, _) in _CACHE.items() if expires_at <= now]:
        _CACHE.pop(key, None)


def _now_seconds() -> float:
    """Monotonic clock, indirected so tests can advance it without sleeping."""
    return time.monotonic()
