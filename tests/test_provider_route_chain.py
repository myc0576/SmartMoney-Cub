from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from typing import Any
import pytest

from smartmoney_cub_harness.agent.provider_errors import (
    ClassifiedProviderError,
    FailurePhase,
    ProviderErrorCode,
    classify_provider_error,
)
from smartmoney_cub_harness.agent.route_chain import (
    CooldownTracker,
    RouteCandidate,
    RouteChainPolicy,
    stream_chat_with_route_chain,
)
from smartmoney_cub_harness.agent.providers import (
    ALPHATECH_PROVIDER_ID,
    OFFLINE_PROVIDER_ID,
    ProviderError,
    resolve_provider,
    stream_chat,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


# ---------------------------------------------------------------------------
# Test mock HTTP server for simulating network and upstream error responses
# ---------------------------------------------------------------------------

class MockProviderHandler(BaseHTTPRequestHandler):
    scenario: str = "ok"
    request_count: int = 0
    fail_counts: dict[str, int] = {}

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Quiet test output

    def do_POST(self) -> None:
        MockProviderHandler.request_count += 1
        scenario = MockProviderHandler.scenario

        if scenario == "quota_403":
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = json.dumps({
                "error": {
                    "message": "You have insufficient balance / quota. Please recharge.",
                    "type": "insufficient_quota",
                    "code": "insufficient_quota"
                }
            })
            self.wfile.write(body.encode("utf-8"))
            return

        if scenario == "rate_limit_429":
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", "2")
            self.end_headers()
            body = json.dumps({
                "error": {
                    "message": "Rate limit reached: requests per minute exceeded.",
                    "type": "rate_limit_error",
                    "code": "rate_limit_exceeded"
                }
            })
            self.wfile.write(body.encode("utf-8"))
            return

        if scenario == "server_error_502":
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = json.dumps({"error": {"message": "Bad gateway from upstream"}})
            self.wfile.write(body.encode("utf-8"))
            return

        if scenario == "auth_401":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = json.dumps({"error": {"message": "Incorrect API key provided"}})
            self.wfile.write(body.encode("utf-8"))
            return

        if scenario == "invalid_request_400":
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = json.dumps({"error": {"message": "Invalid model parameter or context length exceeded"}})
            self.wfile.write(body.encode("utf-8"))
            return

        if scenario == "mid_stream_disconnect":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk1 = json.dumps({"choices": [{"delta": {"content": "First token before abort"}}]})
            self.wfile.write(f"data: {chunk1}\n\n".encode("utf-8"))
            self.wfile.flush()
            # Force disconnect mid-stream
            self.close_connection = True
            return

        if scenario == "fail_once_then_ok":
            if MockProviderHandler.request_count == 1:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Temporary server unavailable"}')
                return
            # Second try succeeds
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunk = json.dumps({"choices": [{"delta": {"content": "Recovered response"}}]})
            self.wfile.write(f"data: {chunk}\n\ndata: [DONE]\n\n".encode("utf-8"))
            return

        # Default: standard successful response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        chunk = json.dumps({"choices": [{"delta": {"content": "Hello from mock"}}]})
        self.wfile.write(f"data: {chunk}\n\ndata: [DONE]\n\n".encode("utf-8"))


@pytest.fixture
def mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockProviderHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    MockProviderHandler.request_count = 0
    MockProviderHandler.scenario = "ok"
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()
    server.server_close()


# ---------------------------------------------------------------------------
# Tests for Error Classification
# ---------------------------------------------------------------------------

def test_error_classification_quota_403() -> None:
    provider = {
        "provider_id": "alphatech",
        "label": "AlphaTech API",
        "portal_url": "https://alphatech.net.cn",
        "api_key": "sk-secret-key-12345",
    }
    body = '{"error": {"message": "You have insufficient balance / quota", "type": "insufficient_quota", "code": "insufficient_quota"}}'
    raw_error = urllib.error.HTTPError(
        url="https://alphatech.net.cn/v1/chat/completions",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=None,
    )
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="gpt-5.6-sol",
        phase=FailurePhase.PRE_STREAM,
        detail=body,
    )
    assert classified.code == ProviderErrorCode.INSUFFICIENT_QUOTA
    assert classified.http_status == 403
    assert classified.phase == FailurePhase.PRE_STREAM
    assert classified.retryable_same_target is False
    assert classified.fallbackable is True
    assert classified.portal_url == "https://alphatech.net.cn"
    assert "sk-secret-key-12345" not in classified.message
    assert "sk-secret-key-12345" not in str(classified)
    assert "充值" in classified.action_suggestion or "额度" in classified.message


def test_error_classification_rate_limit_429() -> None:
    provider = {"provider_id": "gw", "api_key": "sk-secret"}
    body = '{"error": {"message": "Rate limit exceeded: 60 rpm"}}'
    raw_error = urllib.error.HTTPError("https://gw/v1", 429, "Too Many Requests", {}, None)
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="m1",
        phase=FailurePhase.PRE_STREAM,
        detail=body,
    )
    assert classified.code == ProviderErrorCode.RATE_LIMITED
    assert classified.http_status == 429
    assert classified.retryable_same_target is True
    assert classified.fallbackable is True


def test_error_classification_server_error_5xx() -> None:
    provider = {"provider_id": "gw"}
    body = '{"error": "Internal server error"}'
    raw_error = urllib.error.HTTPError("https://gw/v1", 503, "Service Unavailable", {}, None)
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="m1",
        phase=FailurePhase.PRE_STREAM,
        detail=body,
    )
    assert classified.code == ProviderErrorCode.SERVER_ERROR
    assert classified.http_status == 503
    assert classified.retryable_same_target is True
    assert classified.fallbackable is True


def test_error_classification_timeout() -> None:
    provider = {"provider_id": "gw"}
    raw_error = socket.timeout("timed out")
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="m1",
        phase=FailurePhase.PRE_STREAM,
    )
    assert classified.code == ProviderErrorCode.TIMEOUT
    assert classified.retryable_same_target is True
    assert classified.fallbackable is True


def test_error_classification_auth_401() -> None:
    provider = {"provider_id": "gw", "api_key": "sk-bad-key"}
    raw_error = urllib.error.HTTPError("https://gw/v1", 401, "Unauthorized", {}, None)
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="m1",
        phase=FailurePhase.PRE_STREAM,
        detail='{"error": "Invalid API key"}',
    )
    assert classified.code == ProviderErrorCode.AUTHENTICATION
    assert classified.retryable_same_target is False
    assert classified.fallbackable is True


def test_error_classification_invalid_request_400() -> None:
    provider = {"provider_id": "gw"}
    raw_error = urllib.error.HTTPError("https://gw/v1", 400, "Bad Request", {}, None)
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="m1",
        phase=FailurePhase.PRE_STREAM,
        detail='{"error": "max_tokens too high"}',
    )
    assert classified.code == ProviderErrorCode.INVALID_REQUEST
    assert classified.retryable_same_target is False
    assert classified.fallbackable is True


# ---------------------------------------------------------------------------
# Tests for Actionable 403 Quota Result
# ---------------------------------------------------------------------------

def test_403_quota_actionable_result(mock_server: str) -> None:
    MockProviderHandler.scenario = "quota_403"
    provider = {
        "provider_id": ALPHATECH_PROVIDER_ID,
        "base_url": mock_server,
        "protocol": "openai-chat",
        "api_key": "sk-user-key-live",
        "portal_url": "https://alphatech.net.cn",
    }
    with pytest.raises(ClassifiedProviderError) as exc_info:
        list(stream_chat(provider, model="gpt-5.6-sol", messages=[{"role": "user", "content": "hi"}]))

    err = exc_info.value
    assert err.code == ProviderErrorCode.INSUFFICIENT_QUOTA
    assert err.http_status == 403
    assert err.portal_url == "https://alphatech.net.cn"
    actionable = err.to_dict()
    assert actionable["error_code"] == "insufficient_quota"
    assert actionable["portal_url"] == "https://alphatech.net.cn"
    assert "sk-user-key-live" not in json.dumps(actionable)
    assert len(actionable["recovery_suggestions"]) > 0


# ---------------------------------------------------------------------------
# Tests for Pre-stream vs Mid-stream Behavior
# ---------------------------------------------------------------------------

def test_pre_stream_vs_mid_stream(mock_server: str) -> None:
    # Pre-stream error
    MockProviderHandler.scenario = "server_error_502"
    provider = {
        "provider_id": "test-gw",
        "base_url": mock_server,
        "protocol": "openai-chat",
        "api_key": "sk-123",
    }
    with pytest.raises(ClassifiedProviderError) as pre_exc:
        list(stream_chat(provider, model="m1", messages=[{"role": "user", "content": "hi"}]))
    assert pre_exc.value.phase == FailurePhase.PRE_STREAM

    # Mid-stream error
    MockProviderHandler.scenario = "mid_stream_disconnect"
    # When mid-stream disconnects, stream_chat raises mid-stream ClassifiedProviderError
    with pytest.raises(ClassifiedProviderError) as mid_exc:
        list(stream_chat(provider, model="m1", messages=[{"role": "user", "content": "hi"}]))
    assert mid_exc.value.phase == FailurePhase.MID_STREAM
    assert mid_exc.value.code == ProviderErrorCode.STREAM_INTERRUPTION


# ---------------------------------------------------------------------------
# Tests for Route Chain Retries, Cooldowns, and Fallbacks
# ---------------------------------------------------------------------------

def test_route_chain_retries_cooldown_and_fallback(mock_server: str) -> None:
    # 1. Bounded retry on same target when transient error occurs
    MockProviderHandler.scenario = "fail_once_then_ok"
    primary = RouteCandidate(provider_id="test-p1", model="m1", base_url=mock_server, api_key="k1")
    policy = RouteChainPolicy(max_same_target_retries=2, initial_backoff_seconds=0.01)

    events = list(stream_chat_with_route_chain(
        candidates=[primary],
        messages=[{"role": "user", "content": "hi"}],
        policy=policy,
    ))
    # Succeeded on retry
    deltas = [e["text"] for e in events if e.get("kind") == "delta"]
    assert "Recovered response" in "".join(deltas)

    # 2. Fallback to secondary when primary fails permanently or exhausts retries
    MockProviderHandler.scenario = "quota_403"
    candidate_primary = RouteCandidate(
        provider_id="test-quota",
        model="m1",
        base_url=mock_server,
        api_key="k1",
        portal_url="https://recharge.example",
    )
    candidate_offline = RouteCandidate(
        provider_id=OFFLINE_PROVIDER_ID,
        model="heuristic-v1",
        protocol="offline",
    )

    fallback_events = list(stream_chat_with_route_chain(
        candidates=[candidate_primary, candidate_offline],
        messages=[{"role": "user", "content": "复盘"}],
        policy=policy,
    ))
    # Offline candidate produced output
    assert any(e.get("kind") == "delta" for e in fallback_events)
    # Primary should now be in cooldown
    assert policy.cooldown_tracker.is_cooling_down("test-quota", "m1")


# ---------------------------------------------------------------------------
# Tests for Safe Diagnostics and Credential Redaction
# ---------------------------------------------------------------------------

def test_safe_diagnostics_redacts_credentials() -> None:
    provider = {
        "provider_id": "test-sec",
        "api_key": "sk-live-super-secret-password-12345",
        "auth_token": "bearer-token-secret-9999",
    }
    raw_error = urllib.error.HTTPError("https://api.example/v1", 403, "Forbidden", {}, None)
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="sec-model",
        phase=FailurePhase.PRE_STREAM,
        detail="sk-live-super-secret-password-12345 was rejected by endpoint",
    )
    diagnostics = classified.safe_diagnostics
    diag_str = json.dumps(diagnostics)
    assert "sk-live-super-secret-password-12345" not in diag_str
    assert "bearer-token-secret-9999" not in diag_str
    assert "[REDACTED]" in diag_str or "secret" not in diag_str
    assert classified.safety == SAFETY_DECLARATION



# ---------------------------------------------------------------------------
# Additional Focused Tests for Review Findings
# ---------------------------------------------------------------------------

def test_opaque_token_redacted_from_diagnostics_and_candidate_repr() -> None:
    opaque_secret = "opaque_cust_token_XYZ9988776655"
    provider = {
        "provider_id": "custom-opaque",
        "api_key": opaque_secret,
    }
    raw_error = urllib.error.HTTPError("https://api.example/v1", 403, "Forbidden", {}, None)
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="m1",
        phase=FailurePhase.PRE_STREAM,
        detail=f"rejected request with token {opaque_secret} inside message",
    )
    serialized = json.dumps(classified.to_dict())
    assert opaque_secret not in serialized
    assert opaque_secret not in str(classified)
    assert opaque_secret not in classified.raw_message
    assert "[REDACTED]" in serialized

    candidate = RouteCandidate(
        provider_id="custom-opaque",
        model="m1",
        api_key=opaque_secret,
    )
    candidate_repr = repr(candidate)
    assert opaque_secret not in candidate_repr


def test_resolve_provider_preserves_portal_url(tmp_path) -> None:
    resolved = resolve_provider(ALPHATECH_PROVIDER_ID)
    assert resolved.get("portal_url") == "https://alphatech.net.cn"


def test_runtime_emits_structured_classified_error(tmp_path, monkeypatch) -> None:
    from smartmoney_cub_harness.agent.runtime import ReviewAgentRuntime
    from smartmoney_cub_harness.store import Store
    from smartmoney_cub_harness.agent.providers import save_credentials

    store = Store(tmp_path)
    save_credentials(tmp_path, {"providers": {ALPHATECH_PROVIDER_ID: {"api_key": "sk-test"}}})
    runtime = ReviewAgentRuntime(store)
    session = store.create_session(title="复盘", provider_id=ALPHATECH_PROVIDER_ID, model="gpt-5.6-sol")
    session_id = session["session_id"]

    # Mock the route chain after its candidates are exhausted. The runtime now
    # delegates provider attempts to the route-chain boundary rather than
    # calling one provider stream directly.
    def mock_route_chain_fail(*args, **kwargs):
        raise classify_provider_error(
            urllib.error.HTTPError("https://api.example/v1", 403, "Forbidden", {}, None),
            provider={"provider_id": ALPHATECH_PROVIDER_ID, "portal_url": "https://alphatech.net.cn"},
            model="gpt-5.6-sol",
            phase=FailurePhase.PRE_STREAM,
            detail='{"error": {"message": "insufficient_quota"}}',
        )

    import smartmoney_cub_harness.agent.runtime as runtime_mod
    monkeypatch.setattr(runtime_mod, "stream_chat_with_route_chain", mock_route_chain_fail)
    events = list(runtime.run_turn(session_id, "复盘此交易"))
    error_events = [e for e in events if e.get("kind") == "error"]
    assert len(error_events) == 1
    err_evt = error_events[0]
    assert "classified" in err_evt
    assert err_evt["classified"]["error_code"] == "insufficient_quota"
    assert err_evt["classified"]["portal_url"] == "https://alphatech.net.cn"


def test_open_socket_timeout_classified_through_stream_chat(monkeypatch) -> None:
    def fake_open(*args, **kwargs):
        raise socket.timeout("connection timed out during open")

    import smartmoney_cub_harness.agent.providers as prov_mod
    monkeypatch.setattr(prov_mod, "_open", fake_open)

    provider = {"provider_id": "test-p", "base_url": "http://127.0.0.1:9/v1"}
    with pytest.raises(ClassifiedProviderError) as exc_info:
        list(stream_chat(provider, model="m", messages=[]))
    assert exc_info.value.code == ProviderErrorCode.TIMEOUT
    assert exc_info.value.phase == FailurePhase.PRE_STREAM


def test_http_504_and_408_classified_as_timeout() -> None:
    provider = {"provider_id": "test-p"}
    err_504 = urllib.error.HTTPError("https://api.example/v1", 504, "Gateway Timeout", {}, None)
    classified_504 = classify_provider_error(err_504, provider=provider, model="m")
    assert classified_504.code == ProviderErrorCode.TIMEOUT
    assert classified_504.http_status == 504

    err_408 = urllib.error.HTTPError("https://api.example/v1", 408, "Request Timeout", {}, None)
    classified_408 = classify_provider_error(err_408, provider=provider, model="m")
    assert classified_408.code == ProviderErrorCode.TIMEOUT
    assert classified_408.http_status == 408


def test_cooldown_excludes_candidate_and_returns_retry_after(mock_server: str) -> None:
    MockProviderHandler.scenario = "quota_403"
    candidate = RouteCandidate(provider_id="c1", model="m1", base_url=mock_server, api_key="k")
    policy = RouteChainPolicy(max_same_target_retries=0)

    # First attempt fails and puts candidate in cooldown
    with pytest.raises(ClassifiedProviderError):
        list(stream_chat_with_route_chain([candidate], messages=[{"role": "user", "content": "hi"}], policy=policy))

    assert policy.cooldown_tracker.is_cooling_down("c1", "m1")

    # Second invocation immediately during cooldown must not hit the server, and must raise 429 with retry-after
    MockProviderHandler.request_count = 0
    with pytest.raises(ClassifiedProviderError) as exc_info:
        list(stream_chat_with_route_chain([candidate], messages=[{"role": "user", "content": "hi"}], policy=policy))

    assert MockProviderHandler.request_count == 0  # Excluded! Never hit network
    assert exc_info.value.http_status == 429
    assert exc_info.value.code == ProviderErrorCode.RATE_LIMITED
    assert "retry_after" in exc_info.value.safe_diagnostics


def test_auth_and_invalid_request_fallback_to_next_candidate(mock_server: str) -> None:
    MockProviderHandler.scenario = "auth_401"
    primary_bad_auth = RouteCandidate(provider_id="p-bad", model="m", base_url=mock_server, api_key="bad")
    fallback_offline = RouteCandidate(provider_id=OFFLINE_PROVIDER_ID, model="offline-m", protocol="offline")
    policy = RouteChainPolicy(max_same_target_retries=0)

    events = list(stream_chat_with_route_chain([primary_bad_auth, fallback_offline], messages=[], policy=policy))
    assert any(e.get("kind") == "delta" for e in events)


def test_http_status_parsed_from_provider_error_message() -> None:
    base_err = ProviderError("provider returned HTTP 502: Bad gateway")
    classified = classify_provider_error(base_err)
    assert classified.http_status == 502
    assert classified.code == ProviderErrorCode.SERVER_ERROR


def test_opaque_token_scrubbed_from_all_serialized_fields_including_portal_and_recovery() -> None:
    opaque_secret = "opaque_secret_in_portal_and_recovery_887766"
    provider = {
        "provider_id": "custom-opaque-portal",
        "api_key": opaque_secret,
        "portal_url": f"https://portal.example.com/login?token={opaque_secret}",
    }
    raw_error = urllib.error.HTTPError("https://api.example/v1", 403, "Forbidden", {}, None)
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="m1",
        phase=FailurePhase.PRE_STREAM,
        detail=f"insufficient_quota: access denied for token {opaque_secret}",
    )
    # Check object fields directly
    assert opaque_secret not in classified.portal_url
    assert opaque_secret not in classified.action_suggestion
    assert opaque_secret not in json.dumps(classified.recovery_suggestions)

    # Check serialization boundary
    data = classified.to_dict()
    serialized = json.dumps(data)
    assert opaque_secret not in serialized
    assert opaque_secret not in data["portal_url"]
    assert opaque_secret not in data["action_suggestion"]
    assert opaque_secret not in json.dumps(data["recovery_suggestions"])
    assert opaque_secret not in json.dumps(data["safe_diagnostics"])

    # Test direct ClassifiedProviderError initialization with embedded secrets in all fields
    direct_err = ClassifiedProviderError(
        code=ProviderErrorCode.INSUFFICIENT_QUOTA,
        message=f"msg with {opaque_secret}",
        raw_message=f"raw with {opaque_secret}",
        portal_url=f"https://topup.example?key={opaque_secret}",
        action_suggestion=f"Use token {opaque_secret}",
        recovery_suggestions=[{"action": "recharge", "url": f"https://pay.example?k={opaque_secret}"}],
        safe_diagnostics={"token_detail": f"info {opaque_secret}"},
        extra_secrets={opaque_secret},
    )
    direct_dict = direct_err.to_dict()
    direct_serialized = json.dumps(direct_dict)
    assert opaque_secret not in direct_serialized
    assert opaque_secret not in direct_dict["portal_url"]
    assert opaque_secret not in direct_dict["action_suggestion"]
    assert opaque_secret not in json.dumps(direct_dict["recovery_suggestions"])
    assert opaque_secret not in json.dumps(direct_dict["safe_diagnostics"])



def test_exception_instance_does_not_store_plaintext_secrets_in_vars_or_repr() -> None:
    opaque_secret = "opaque_token_never_in_vars_77665544"
    provider = {
        "provider_id": "custom-opaque-vars",
        "api_key": opaque_secret,
        "portal_url": f"https://portal.example.com/login?token={opaque_secret}",
    }
    raw_error = urllib.error.HTTPError("https://api.example/v1", 403, "Forbidden", {}, None)
    classified = classify_provider_error(
        raw_error,
        provider=provider,
        model="m1",
        phase=FailurePhase.PRE_STREAM,
        detail=f"insufficient_quota: rejected {opaque_secret}",
    )

    # 1. Assert vars(classified) does not contain the secret in any key or value
    error_vars = vars(classified)
    vars_str = json.dumps(error_vars, default=str)
    assert opaque_secret not in vars_str
    assert "extra_secrets" not in error_vars

    # 2. Assert repr and str do not contain the secret
    assert opaque_secret not in repr(classified)
    assert opaque_secret not in str(classified)

    # 3. Assert all fields and to_dict remain scrubbed
    data = classified.to_dict()
    assert opaque_secret not in json.dumps(data)
    assert opaque_secret not in data["portal_url"]
    assert urllib.parse.urlsplit(data["portal_url"]).query == ""
    assert urllib.parse.urlsplit(data["portal_url"]).fragment == ""


def _assert_no_credential_on_error(error: ClassifiedProviderError, secret: str) -> None:
    surfaces = {
        name: getattr(error, name)
        for name in dir(error)
        if not name.startswith("_") and not callable(getattr(error, name))
    }
    surfaces.update({
        "vars": vars(error),
        "repr": repr(error),
        "str": str(error),
        "serialized": error.to_dict(),
        "cause": error.__cause__,
        "context": error.__context__,
    })
    leaked_surfaces = [
        name for name, value in surfaces.items()
        if secret in repr(value) or secret in str(value)
    ]
    assert leaked_surfaces == []
    assert secret not in json.dumps(error.to_dict())


@pytest.mark.parametrize("construction", ["classifier", "constructor", "stream"])
@pytest.mark.parametrize("parameter", [
    "access_token", "token", "api_key", "key", "access_key", "secret",
    "password", "authorization", "signature", "X-Vendor-Credential",
    "ACCESS%5FTOKEN", "opaqueVendorProof",
])
def test_independent_url_query_credentials_are_private(
    monkeypatch, construction: str, parameter: str,
) -> None:
    secret = "toyOpaqueQueryCredential/987+654"
    encoded = urllib.parse.quote(secret, safe="")
    portal = f"https://portal.example/recover?{parameter}={encoded}&plan=pro"
    detail = f"insufficient_quota: recover at {portal}; rejected {secret}"
    provider = {
        "provider_id": "gateway", "base_url": "https://provider.example/v1",
        "portal_url": portal, "api_key": "unrelatedToyCredential",
    }
    if construction == "constructor":
        error = ClassifiedProviderError(
            code=ProviderErrorCode.INSUFFICIENT_QUOTA, message=detail,
            raw_message=detail, portal_url=portal,
            recovery_suggestions=[{"action": "recharge", "label": "前往服务商充值", "url": portal}],
            safe_diagnostics={f"echo-{secret}": {"detail": detail}},
        )
    elif construction == "classifier":
        error = classify_provider_error(
            ProviderError(f"provider returned HTTP 403: {detail}"), provider=provider,
        )
    else:
        def fail_open(*args, **kwargs):
            raise urllib.error.HTTPError(portal, 403, detail, {}, None)

        monkeypatch.setattr("urllib.request.urlopen", fail_open)
        with pytest.raises(ClassifiedProviderError) as caught:
            list(stream_chat(provider, model="model", messages=[]))
        error = caught.value

    _assert_no_credential_on_error(error, secret)
    _assert_no_credential_on_error(error, encoded)
    assert error.__cause__ is None
    assert error.__context__ is None
    target = urllib.parse.urlsplit(error.portal_url)
    assert (target.scheme, target.netloc, target.path) == (
        "https", "portal.example", "/recover",
    )
    assert error.recovery_suggestions[0]["url"] == error.portal_url
    assert error.recovery_suggestions[0]["action"] == "recharge"


@pytest.mark.parametrize("secret", ["quota", "pre_stream", "a", "action", "READ", "前往"])
def test_short_credentials_preserve_protocol_and_quota_cooldown(monkeypatch, secret: str) -> None:
    provider = {"provider_id": "gateway", "api_key": secret, "portal_url": "https://portal.example/recover"}
    error = classify_provider_error(
        ProviderError("provider returned HTTP 403: insufficient_quota"), provider=provider,
    )
    payload = error.to_dict()
    assert payload["error_code"] == "insufficient_quota"
    assert payload["phase"] == "pre_stream"
    assert payload["safety"] == SAFETY_DECLARATION
    assert payload["http_status"] == 403
    assert payload["retryable_same_target"] is False
    assert payload["fallbackable"] is True
    assert payload["safe_diagnostics"]["phase"] == "pre_stream"
    assert payload["recovery_suggestions"] == [
        {"action": "recharge", "label": "前往服务商充值", "url": "https://portal.example/recover"},
        {"action": "switch_model", "label": "切换备用模型"},
        {"action": "offline_mode", "label": "使用离线规则"},
    ]
    tracker = CooldownTracker()
    assert tracker.mark_failure("gateway", "model", error, now=100) == 300
    assert tracker.remaining_cooldown("gateway", "model", now=399) == 1
    assert not tracker.is_cooling_down("gateway", "model", now=400)

    calls = []
    def fail_open(*args, **kwargs):
        calls.append(True)
        raise urllib.error.HTTPError("https://provider.example/v1", 403, "insufficient_quota", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fail_open)
    monkeypatch.setattr("smartmoney_cub_harness.agent.route_chain.time.time", lambda: 100)
    policy = RouteChainPolicy(max_same_target_retries=2, initial_backoff_seconds=0)
    events = list(stream_chat_with_route_chain([
        RouteCandidate(provider_id="gateway", model="model", api_key=secret, base_url="https://provider.example/v1"),
        RouteCandidate(provider_id=OFFLINE_PROVIDER_ID, model="offline", protocol="offline"),
    ], messages=[], policy=policy))
    assert len(calls) == 1  # Quota must not retry the failed target.
    assert events[-1] == {"kind": "done", "finish_reason": "stop"}
    assert "本地离线复盘" in events[0]["text"]
    assert policy.cooldown_tracker.remaining_cooldown("gateway", "model", now=100) == 300


@pytest.mark.parametrize("construction", ["classifier", "constructor"])
def test_opaque_credential_absent_from_all_exception_surfaces(construction: str) -> None:
    secret = "J7vQ9mR2xN6pL4wZ8cT5"
    provider = {
        "provider_id": f"gateway-{secret}",
        "api_key": secret,
        "portal_url": f"https://portal.example/renew/{secret}?ref={secret}",
    }
    model = f"model-{secret}"
    detail = f"insufficient_quota: rejected {secret}"
    if construction == "classifier":
        error = classify_provider_error(
            ProviderError(f"provider returned HTTP 403: {detail}"),
            provider=provider,
            model=model,
            detail=detail,
        )
    else:
        error = ClassifiedProviderError(
            code=ProviderErrorCode.INSUFFICIENT_QUOTA,
            message=detail,
            raw_message=detail,
            http_status=403,
            provider_id=provider["provider_id"],
            model=model,
            fallbackable=True,
            portal_url=provider["portal_url"],
            action_suggestion=f"Recharge {secret}",
            recovery_suggestions=[{"action": "recharge", "url": provider["portal_url"]}],
            safe_diagnostics={"detail": detail},
            extra_secrets={secret},
        )

    _assert_no_credential_on_error(error, secret)
    data = error.to_dict()
    assert error.provider_id == data["provider_id"] == "gateway-[REDACTED]"
    assert error.model == data["model"] == "model-[REDACTED]"
    assert error.code == data["error_code"] == ProviderErrorCode.INSUFFICIENT_QUOTA
    assert error.http_status == data["http_status"] == 403
    assert error.phase == data["phase"] == FailurePhase.PRE_STREAM
    assert error.retryable_same_target is False
    assert error.fallbackable is True
    assert error.portal_url == "https://portal.example/renew/[REDACTED]"
    assert error.recovery_suggestions[0]["url"] == error.portal_url
    assert error.safe_diagnostics["detail"] == "insufficient_quota: rejected [REDACTED]"
    assert error.args == (error.message,)
    assert error.safety == data["safety"] == SAFETY_DECLARATION


def test_opaque_credential_scrubbed_from_complete_constructor_payload() -> None:
    secret = "J7vQ9mR2xN6pL4wZ8cT5"
    diagnostics = {
        f"upstream-{secret}": {"echo": secret},
        "attempts": [(secret, {"detail": f"rejected {secret}"})],
        "reason": RuntimeError(f"upstream rejected {secret}"),
        "retry_after": 7,
    }
    error = ClassifiedProviderError(
        code=f"upstream-{secret}",
        phase=f"phase-{secret}",
        message=f"rejected {secret}",
        recovery_suggestions=[{f"link-{secret}": f"https://portal.example/{secret}"}],
        safe_diagnostics=diagnostics,
        extra_secrets={secret},
    )

    _assert_no_credential_on_error(error, secret)
    assert error.code == "upstream-[REDACTED]"
    assert error.phase == "phase-[REDACTED]"
    assert error.safe_diagnostics["upstream-[REDACTED]"] == {"echo": "[REDACTED]"}
    assert error.safe_diagnostics["attempts"][0] == (
        "[REDACTED]", {"detail": "rejected [REDACTED]"},
    )
    assert error.safe_diagnostics["reason"] == "upstream rejected [REDACTED]"
    assert error.safe_diagnostics["retry_after"] == 7
    assert diagnostics["attempts"][0][0] == secret
    diagnostics["attempts"].append(secret)
    _assert_no_credential_on_error(error, secret)


@pytest.mark.parametrize(
    ("failure_site", "expected_code"),
    [
        ("http_open", ProviderErrorCode.INSUFFICIENT_QUOTA),
        ("url_open", ProviderErrorCode.NETWORK_UNREACHABLE),
        ("timeout_open", ProviderErrorCode.TIMEOUT),
        ("unexpected_open", ProviderErrorCode.UNKNOWN),
        ("stream_read", ProviderErrorCode.STREAM_INTERRUPTION),
    ],
)
def test_opaque_credential_not_retained_in_upstream_exception_chain(
    monkeypatch, failure_site: str, expected_code: str,
) -> None:
    secret = "J7vQ9mR2xN6pL4wZ8cT5"
    failures = {
        "http_open": urllib.error.HTTPError(
            "https://provider.example/v1", 403, f"insufficient_quota {secret}", {}, None,
        ),
        "url_open": urllib.error.URLError(f"unreachable {secret}"),
        "timeout_open": TimeoutError(f"timed out {secret}"),
        "unexpected_open": RuntimeError(f"upstream rejected {secret}"),
    }

    class BrokenStream:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            yield b'data: {"choices": [{"delta": {"content": "partial response"}}]}\n\n'
            raise RuntimeError(f"stream disconnected {secret}")

    def fail_upstream(*args, **kwargs):
        if failure_site == "stream_read":
            return BrokenStream()
        raise failures[failure_site]

    monkeypatch.setattr("urllib.request.urlopen", fail_upstream)
    provider = {
        "provider_id": "gateway",
        "base_url": "https://provider.example/v1",
        "api_key": secret,
    }
    events = []
    with pytest.raises(ClassifiedProviderError) as caught:
        events.extend(stream_chat(provider, model="model", messages=[]))

    error = caught.value
    _assert_no_credential_on_error(error, secret)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert error.code == expected_code
    assert "[REDACTED]" in error.raw_message
    if failure_site == "stream_read":
        assert events == [{"kind": "delta", "text": "partial response"}]
        assert error.phase == FailurePhase.MID_STREAM
        assert error.retryable_same_target is False
        assert error.fallbackable is False
    else:
        assert events == []
        assert error.phase == FailurePhase.PRE_STREAM
