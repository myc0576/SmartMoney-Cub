"""Tenant authentication for the trader product.

No test here calls the alphatech platform. Session-mode tests stub the
/api/user/self answer, and the two transport tests point the adapter at a
loopback HTTP server started inside the test.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.auth import AuthContext, AuthError, resolve_identity
from smartmoney_cub_harness.trader.auth import alphatech

SECRET = "toy-shared-secret"


@pytest.fixture(autouse=True)
def _isolated_platform_env(monkeypatch):
    """Pin every platform knob so a developer's environment cannot steer a test."""
    for name in (
        alphatech.AUTH_MODE_ENV,
        alphatech.BASE_URL_ENV,
        alphatech.SSO_SECRET_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    # A non-routable base URL, so a test that forgets to stub the lookup fails
    # fast instead of reaching the real platform.
    monkeypatch.setenv(alphatech.BASE_URL_ENV, "http://127.0.0.1:1")
    alphatech.clear_identity_cache()
    yield
    alphatech.clear_identity_cache()


def _stub_self(monkeypatch, body, *, status: int = 200, calls: list | None = None):
    """Replace the platform lookup, recording each call so caching is observable."""
    recorded = calls if calls is not None else []

    def fake(cookie_header: str, *, base_url: str, timeout: float = 0.0):
        recorded.append({"cookie": cookie_header, "base_url": base_url})
        return alphatech.SelfResponse(status=status, body=body)

    monkeypatch.setattr(alphatech, "fetch_platform_user", fake)
    return recorded


def _signed_headers(
    user_id: str = "4711",
    *,
    timestamp: object = None,
    secret: str = SECRET,
    signature: str | None = None,
) -> dict[str, str]:
    stamp = str(int(time.time())) if timestamp is None else str(timestamp)
    if signature is None:
        signature = alphatech.hmac.new(
            secret.encode("utf-8"),
            alphatech.hmac_message(user_id, stamp),
            alphatech.sha256,
        ).hexdigest()
    return {
        alphatech.USER_HEADER: user_id,
        alphatech.TIMESTAMP_HEADER: stamp,
        alphatech.SIGNATURE_HEADER: signature,
    }


# --- local mode -------------------------------------------------------------


def test_local_mode_returns_a_fixed_single_user_context():
    first = resolve_identity({}, mode="local")
    second = resolve_identity({alphatech.USER_HEADER: "somebody"}, mode="local")

    assert isinstance(first, AuthContext)
    assert first == second
    assert first.user_id == "local"
    assert first.tenant_id == "local"
    assert first.mode == "local"
    assert first.platform_user_id == ""
    assert first.display_name


def test_local_mode_never_reads_headers(monkeypatch):
    class HostileHeaders:
        def __getitem__(self, key):
            raise AssertionError("local mode must not read request headers")

        def get(self, key, default=None):
            raise AssertionError("local mode must not read request headers")

        def items(self):
            raise AssertionError("local mode must not read request headers")

    # Even with the platform configured for hosted traffic, local mode stays local.
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_SESSION)
    monkeypatch.setenv(alphatech.BASE_URL_ENV, "http://127.0.0.1:1")

    context = resolve_identity(HostileHeaders(), mode="local")

    assert context.mode == "local"
    assert context.user_id == "local"


def test_unknown_mode_fails_closed():
    with pytest.raises(AuthError):
        resolve_identity({}, mode="who-knows")


def test_local_context_carries_the_safety_declaration():
    assert resolve_identity({}, mode="local").safety == SAFETY_DECLARATION


# --- session mode (default) -------------------------------------------------


def test_session_mode_defaults_to_cookie_forwarding(monkeypatch):
    assert alphatech.platform_auth_mode() == alphatech.MODE_SESSION
    calls = _stub_self(monkeypatch, {"id": 4711, "username": "toy-trader"})

    context = resolve_identity({"Cookie": "session=toy-cookie"}, mode="hosted")

    assert context.platform_user_id == "4711"
    assert context.tenant_id == "alphatech:4711"
    assert context.user_id == context.tenant_id
    assert context.mode == "hosted"
    assert context.display_name == "toy-trader"
    assert calls == [{"cookie": "session=toy-cookie", "base_url": "http://127.0.0.1:1"}]


def test_session_mode_forwards_only_the_session_cookie(monkeypatch):
    calls = _stub_self(monkeypatch, {"id": "4711"})

    resolve_identity({"cookie": "theme=dark; session=toy-cookie; lang=zh"}, mode="hosted")

    assert calls[0]["cookie"] == "session=toy-cookie"


def test_session_mode_forwards_the_whole_header_when_the_cookie_name_is_unexpected(
    monkeypatch,
):
    # The cookie name is an assumption. A wrong guess must not reject every
    # request, so the full header is the fallback.
    calls = _stub_self(monkeypatch, {"id": "4711"})

    resolve_identity({"Cookie": "new_api_session=toy-cookie"}, mode="hosted")

    assert calls[0]["cookie"] == "new_api_session=toy-cookie"


def test_session_mode_maps_the_platform_id_to_a_stable_tenant(monkeypatch):
    _stub_self(monkeypatch, {"id": 4711})

    first = resolve_identity({"Cookie": "session=a"}, mode="hosted")
    alphatech.clear_identity_cache()
    second = resolve_identity({"Cookie": "session=b"}, mode="hosted")

    assert first.tenant_id == second.tenant_id == "alphatech:4711"


def test_session_mode_display_name_falls_back_to_the_platform_id(monkeypatch):
    _stub_self(monkeypatch, {"id": 4711})

    assert resolve_identity({"Cookie": "session=a"}, mode="hosted").display_name == "4711"


def test_session_mode_rejects_an_unauthenticated_platform_answer(monkeypatch):
    _stub_self(monkeypatch, {"success": False, "message": "unauthorized"}, status=401)

    with pytest.raises(AuthError):
        resolve_identity({"Cookie": "session=stale"}, mode="hosted")


def test_session_mode_rejects_a_success_false_body(monkeypatch):
    _stub_self(monkeypatch, {"success": False, "message": "未登录"}, status=200)

    with pytest.raises(AuthError):
        resolve_identity({"Cookie": "session=stale"}, mode="hosted")


def test_session_mode_rejects_a_body_without_a_user_id(monkeypatch):
    _stub_self(monkeypatch, {"username": "toy-trader"})

    with pytest.raises(AuthError):
        resolve_identity({"Cookie": "session=toy-cookie"}, mode="hosted")


def test_session_mode_rejects_a_request_without_a_cookie(monkeypatch):
    calls = _stub_self(monkeypatch, {"id": 4711})

    with pytest.raises(AuthError):
        resolve_identity({"Accept": "application/json"}, mode="hosted")
    assert calls == []


def test_session_mode_caches_the_lookup_for_a_minute(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(alphatech, "_now_seconds", lambda: clock["now"])
    calls = _stub_self(monkeypatch, {"id": 4711})

    first = resolve_identity({"Cookie": "session=toy-cookie"}, mode="hosted")
    clock["now"] += 59.0
    second = resolve_identity({"Cookie": "session=toy-cookie"}, mode="hosted")
    clock["now"] += 2.0
    third = resolve_identity({"Cookie": "session=toy-cookie"}, mode="hosted")

    assert len(calls) == 2
    assert first == second
    assert third == first


def test_session_mode_cache_is_per_session_cookie(monkeypatch):
    calls = _stub_self(monkeypatch, {"id": 4711})

    resolve_identity({"Cookie": "session=one"}, mode="hosted")
    resolve_identity({"Cookie": "session=two"}, mode="hosted")

    assert len(calls) == 2


# --- signed header mode (fallback) ------------------------------------------


def test_signed_identity_resolves_to_the_matching_tenant(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)

    context = resolve_identity(_signed_headers("4711"), mode="hosted")

    assert context.platform_user_id == "4711"
    assert context.tenant_id == "alphatech:4711"
    assert context.mode == "hosted"


def test_both_modes_map_a_platform_user_to_the_same_tenant(monkeypatch):
    _stub_self(monkeypatch, {"id": "4711"})
    session_context = resolve_identity({"Cookie": "session=toy-cookie"}, mode="hosted")
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)

    signed_context = resolve_identity(_signed_headers("4711"), mode="hosted")

    assert signed_context.tenant_id == session_context.tenant_id


def test_uppercase_signature_is_accepted(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)
    headers = _signed_headers("4711")
    headers[alphatech.SIGNATURE_HEADER] = headers[alphatech.SIGNATURE_HEADER].upper()

    assert resolve_identity(headers, mode="hosted").tenant_id == "alphatech:4711"


def test_tampered_signature_raises(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)
    headers = _signed_headers("4711")
    signature = headers[alphatech.SIGNATURE_HEADER]
    headers[alphatech.SIGNATURE_HEADER] = ("0" if signature[0] != "0" else "1") + signature[1:]

    with pytest.raises(AuthError):
        resolve_identity(headers, mode="hosted")


def test_signature_for_another_user_raises(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)
    headers = _signed_headers("4711")
    headers[alphatech.USER_HEADER] = "9999"

    with pytest.raises(AuthError):
        resolve_identity(headers, mode="hosted")


def test_wrong_secret_raises(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, "a-different-secret")

    with pytest.raises(AuthError):
        resolve_identity(_signed_headers("4711"), mode="hosted")


@pytest.mark.parametrize("age", [301, 3600, 86400])
def test_stale_timestamp_raises(monkeypatch, age: int):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)
    headers = _signed_headers("4711", timestamp=int(time.time()) - age)

    with pytest.raises(AuthError):
        resolve_identity(headers, mode="hosted")


def test_timestamp_just_inside_the_replay_window_is_accepted(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)
    fresh = int(time.time()) - (alphatech.SIGNATURE_MAX_AGE_SECONDS - 5)
    headers = _signed_headers("4711", timestamp=fresh)

    assert resolve_identity(headers, mode="hosted").tenant_id == "alphatech:4711"


def test_far_future_timestamp_raises(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)
    headers = _signed_headers("4711", timestamp=int(time.time()) + 3600)

    with pytest.raises(AuthError):
        resolve_identity(headers, mode="hosted")


def test_non_numeric_timestamp_raises(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)

    with pytest.raises(AuthError):
        resolve_identity(_signed_headers("4711", timestamp="not-a-time"), mode="hosted")


def test_missing_signed_headers_raise(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    monkeypatch.setenv(alphatech.SSO_SECRET_ENV, SECRET)

    with pytest.raises(AuthError):
        resolve_identity({alphatech.USER_HEADER: "4711"}, mode="hosted")


# --- fail-closed configuration ----------------------------------------------


def test_hmac_mode_without_a_secret_fails_closed(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    assert not alphatech.sso_secret()

    with pytest.raises(AuthError) as excinfo:
        resolve_identity(_signed_headers("4711", secret=""), mode="hosted")

    # A configuration error must never yield an anonymous identity.
    assert alphatech.SSO_SECRET_ENV in str(excinfo.value)


def test_hmac_mode_without_a_secret_does_not_read_the_platform(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, alphatech.MODE_HMAC)
    calls = _stub_self(monkeypatch, {"id": 4711})

    with pytest.raises(AuthError):
        resolve_identity(_signed_headers("4711"), mode="hosted")
    assert calls == []


def test_unknown_platform_auth_mode_fails_closed(monkeypatch):
    monkeypatch.setenv(alphatech.AUTH_MODE_ENV, "anonymous")

    with pytest.raises(AuthError):
        resolve_identity({}, mode="hosted")


def test_a_failed_lookup_is_not_cached(monkeypatch):
    calls = _stub_self(monkeypatch, {"success": False}, status=401)

    for _ in range(2):
        with pytest.raises(AuthError):
            resolve_identity({"Cookie": "session=stale"}, mode="hosted")

    assert len(calls) == 2


def test_platform_transport_failure_fails_closed(monkeypatch):
    def explode(cookie_header: str, *, base_url: str, timeout: float = 0.0):
        raise AuthError("alphatech identity lookup failed: URLError")

    monkeypatch.setattr(alphatech, "fetch_platform_user", explode)

    with pytest.raises(AuthError):
        resolve_identity({"Cookie": "session=toy-cookie"}, mode="hosted")


# --- transport, against a loopback server only -------------------------------


def _serve(handler_cls) -> tuple[HTTPServer, str]:
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def _handler_for(status: int, body: str, requests: list):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server calls this name
            requests.append({"path": self.path, "cookie": self.headers.get("Cookie")})
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):  # noqa: A002 - http.server signature
            return

    return Handler


def test_real_transport_reads_the_platform_user_from_a_session_cookie(monkeypatch):
    requests: list = []
    server, url = _serve(
        _handler_for(200, json.dumps({"id": 4711, "username": "toy-trader"}), requests)
    )
    monkeypatch.setenv(alphatech.BASE_URL_ENV, url)
    try:
        context = resolve_identity({"Cookie": "session=toy-cookie"}, mode="hosted")
    finally:
        server.shutdown()
        server.server_close()

    assert context.tenant_id == "alphatech:4711"
    assert context.display_name == "toy-trader"
    assert requests == [{"path": alphatech.SELF_ENDPOINT, "cookie": "session=toy-cookie"}]


def test_real_transport_treats_a_401_as_an_auth_error(monkeypatch):
    requests: list = []
    server, url = _serve(
        _handler_for(401, json.dumps({"success": False, "message": "未登录"}), requests)
    )
    monkeypatch.setenv(alphatech.BASE_URL_ENV, url)
    try:
        with pytest.raises(AuthError) as excinfo:
            resolve_identity({"Cookie": "session=stale"}, mode="hosted")
    finally:
        server.shutdown()
        server.server_close()

    assert "401" in str(excinfo.value)
    assert requests and requests[0]["path"] == alphatech.SELF_ENDPOINT


def test_default_base_url_does_not_carry_the_model_gateway_path():
    # The agent providers use {site}/v1 as a model gateway; identity lives on the
    # site root, so the two must not be conflated.
    assert alphatech.DEFAULT_BASE_URL == "https://alphatech.net.cn"
    assert alphatech.SELF_ENDPOINT == "/api/user/self"


# --- the assumptions stay in one place --------------------------------------


def test_the_protocol_assumptions_are_documented_in_the_adapter_docstring():
    doc = alphatech.__doc__ or ""

    for expected in (
        alphatech.SELF_ENDPOINT,
        alphatech.SESSION_COOKIE_NAME,
        alphatech.USER_HEADER,
        alphatech.AUTH_MODE_ENV,
        alphatech.SSO_SECRET_ENV,
        "Platform protocol assumptions",
    ):
        assert expected in doc
