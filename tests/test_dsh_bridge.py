from __future__ import annotations

import io
import hashlib
import json

import pytest

from smartmoney_cub_harness.agent.dsh_bridge import (
    ALLOWED_CAPABILITIES,
    DSH_PROFILE,
    DSH_PROTOCOL,
    DshBridgeError,
    DshProfile,
    DshSidecarBridge,
    InMemoryDshTransport,
    dsh_source_bootstrap,
)
from smartmoney_cub_harness.review_contracts import (
    REDACTED_REVIEW_ENVELOPE_SCHEMA,
    RedactedReviewEnvelope,
    ReviewScope,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _envelope() -> RedactedReviewEnvelope:
    scope = ReviewScope(
        review_id="REV-toy-1",
        decision_time="2026-09-10T15:00:00+08:00",
        horizons=("next_session",),
        case_ids=("case-toy-1",),
    )
    payload = {
        "portfolio_id": "portfolio-12345678",
        "symbol": "symbol-12345678",
        "quantity": "0-100",
        "price": "10-20",
        "trade_time": "09:00-10:00",
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return RedactedReviewEnvelope(
        scope=scope,
        payload=payload,
        payload_sha256=digest,
        redaction_policy="redaction.v1",
        sent_keys=("portfolio_id", "symbol"),
    )


def test_profile_is_fail_closed_and_bootstrap_is_metadata_only() -> None:
    profile = DshProfile()
    payload = profile.to_dict()
    assert profile.name == DSH_PROFILE
    assert profile.protocol == DSH_PROTOCOL
    assert set(payload["capabilities"]) == set(ALLOWED_CAPABILITIES)
    assert payload["allow_network"] is False
    assert payload["allow_shell"] is False
    assert payload["allow_filesystem"] is False
    assert payload["allow_credentials"] is False
    assert payload["safety"] == SAFETY_DECLARATION
    assert dsh_source_bootstrap()["executed"] is False

    with pytest.raises(ValueError):
        DshProfile(capabilities=frozenset({"shell"}))


def test_handshake_and_lifecycle_use_versioned_safe_json_rpc() -> None:
    transport = InMemoryDshTransport()
    bridge = DshSidecarBridge(transport, transport)
    handshake = bridge.handshake(_envelope())
    assert handshake["result"]["profile"] == DSH_PROFILE
    assert bridge.subscribe()["result"]["accepted"] is True
    assert bridge.heartbeat()["result"]["alive"] is True
    assert bridge.cancel("REV-toy-1")["result"]["method"] == "cancel"
    assert bridge.resume("REV-toy-1", after_seq=3)["result"]["method"] == "resume"
    assert bridge.fork("REV-toy-1", title="toy fork")["result"]["method"] == "fork"
    assert bridge.close("REV-toy-1")["result"]["method"] == "close"
    assert bridge.connected is False

    requests = [json.loads(line) for line in transport.inbox]
    assert requests[0]["method"] == "handshake"
    assert requests[0]["params"]["profile"]["name"] == DSH_PROFILE
    assert requests[0]["params"]["envelope"]["schema"] == REDACTED_REVIEW_ENVELOPE_SCHEMA
    assert all(request["safety"] == SAFETY_DECLARATION for request in requests)
    assert all(request["method"] in {"handshake", "subscribe", "heartbeat", "cancel", "resume", "fork", "close"} for request in requests)


def test_bridge_rejects_unredacted_envelope_and_crash_is_classified() -> None:
    transport = InMemoryDshTransport()
    bridge = DshSidecarBridge(transport, transport)
    bad = _envelope().to_dict()
    bad["payload"]["api_key"] = "toy-secret"
    with pytest.raises(DshBridgeError) as error:
        bridge.handshake(bad)
    assert error.value.code == "invalid_review_envelope"
    assert "toy-secret" not in repr(error.value)

    reader = io.StringIO("")
    writer = io.StringIO()
    disconnected = DshSidecarBridge(reader, writer)
    with pytest.raises(DshBridgeError) as crashed:
        disconnected.handshake(_envelope())
    assert crashed.value.code == "sidecar_crashed"
    assert crashed.value.retryable is True


def test_bridge_does_not_accept_model_facing_methods() -> None:
    transport = InMemoryDshTransport()
    bridge = DshSidecarBridge(transport, transport)
    with pytest.raises(DshBridgeError) as error:
        bridge._call("shell", {})
    assert error.value.code == "method_not_allowed"
