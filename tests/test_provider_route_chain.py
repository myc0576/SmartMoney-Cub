from __future__ import annotations

import json
import socket
import urllib.error
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
    assert classified.fallbackable is False


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
    assert classified.fallbackable is False


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

