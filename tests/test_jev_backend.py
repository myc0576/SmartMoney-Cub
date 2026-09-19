from __future__ import annotations

import json
import os
import pytest
import urllib.request

from smartmoney_cub_harness.jev import (
    JevBackend,
    JevProtocolError,
    JevQuestion,
    JevReviewDecision,
    JevUnavailable,
    OpenRouterJevBackend,
    TypeSafeDirectJevBackend,
    build_questions,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_backends_satisfy_jev_backend_protocol():
    direct = TypeSafeDirectJevBackend(api_key=None)
    openrouter = OpenRouterJevBackend(api_key=None)

    assert isinstance(direct, JevBackend)
    assert isinstance(openrouter, JevBackend)


def test_typesafe_direct_backend_fails_closed_without_credential(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    backend = TypeSafeDirectJevBackend(api_key=None)

    assert backend.backend_id == "typesafe-direct"
    assert backend.provider_id == "typesafe"

    health = backend.health()
    assert health["available"] is False
    assert health["reason"] == "missing_credential"
    assert health["safety"] == SAFETY_DECLARATION

    questions = (
        JevQuestion("q1", "choice", "Pick", choices=("yes", "no")),
    )
    with pytest.raises(JevUnavailable, match="missing credential"):
        backend.evaluate({"case": "toy"}, questions, decision_time="2026-06-01T15:00:00Z")


def test_typesafe_direct_backend_fails_closed_offline_with_key():
    backend = TypeSafeDirectJevBackend(api_key="test-key-mock")
    health = backend.health()
    assert health["available"] is True
    assert health["safety"] == SAFETY_DECLARATION

    questions = (
        JevQuestion("q1", "choice", "Pick", choices=("yes", "no")),
    )
    # In offline environment without mock client, must fail closed with JevUnavailable
    with pytest.raises(JevUnavailable, match="unreachable or offline"):
        backend.evaluate({"case": "toy"}, questions, decision_time="2026-06-01T15:00:00Z")


def test_typesafe_direct_backend_with_mock_client_succeeds():
    def mock_client(payload):
        return {
            "model_resolved": "typesafe/jev-direct-2026",
            "request_id": "req-12345",
            "answers": [
                {
                    "question_id": "q1",
                    "value": "yes",
                    "confidence": 0.95,
                    "rationale": "Clear evidence in disclosures",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 30},
            "estimated_cost_usd": 0.0005,
        }

    backend = TypeSafeDirectJevBackend(api_key="test-key", http_client=mock_client)
    questions = (
        JevQuestion("q1", "choice", "Pick", choices=("yes", "no")),
    )
    decision = backend.evaluate({"case": "toy"}, questions, decision_time="2026-06-01T15:00:00Z")

    assert isinstance(decision, JevReviewDecision)
    assert decision.backend_id == "typesafe-direct"
    assert decision.provider_id == "typesafe"
    assert decision.model_resolved == "typesafe/jev-direct-2026"
    assert decision.safety == SAFETY_DECLARATION
    assert len(decision.answers) == 1
    assert decision.answers[0].value == "yes"
    assert decision.run_hash != ""


def test_openrouter_backend_fails_closed_without_credential(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    backend = OpenRouterJevBackend(api_key=None)

    assert backend.backend_id == "openrouter-jev"
    assert backend.provider_id == "openrouter"
    # Exact wire value verification
    assert backend.model_requested == "~typesafe/jev-latest"

    health = backend.health()
    assert health["available"] is False
    assert health["reason"] == "missing_credential"
    assert health["safety"] == SAFETY_DECLARATION

    questions = (
        JevQuestion("q1", "choice", "Pick", choices=("yes", "no")),
    )
    with pytest.raises(JevUnavailable, match="missing OPENROUTER_API_KEY"):
        backend.evaluate({"case": "toy"}, questions, decision_time="2026-06-01T15:00:00Z")


def test_openrouter_backend_sends_required_headers_and_records_model_resolved():
    recorded_headers = {}

    def mock_http_client(req: urllib.request.Request) -> dict:
        for k, v in req.headers.items():
            recorded_headers[k.lower()] = v
        return {
            "id": "gen-openrouter-987",
            "model": "typesafe/jev-v1.0-preview",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "answers": [
                                    {
                                        "question_id": "evidence_sufficiency",
                                        "value": "sufficient",
                                        "confidence": 0.92,
                                        "rationale": "High data quality and matching thesis",
                                    },
                                    {
                                        "question_id": "major_counter_evidence",
                                        "value": False,
                                        "confidence": 0.88,
                                        "rationale": "No adverse signals found",
                                    },
                                ]
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 150, "completion_tokens": 45},
        }

    backend = OpenRouterJevBackend(api_key="sk-or-test-secret", http_client=mock_http_client)
    questions = (
        JevQuestion(
            "evidence_sufficiency",
            "choice",
            "Check evidence",
            choices=("sufficient", "partial", "insufficient", "contradictory"),
        ),
        JevQuestion("major_counter_evidence", "noul", "Check counter evidence"),
    )

    decision = backend.evaluate(
        {"ticker": "DEMO"},
        questions,
        decision_time="2026-06-01T15:00:00Z",
    )

    # Verify required headers
    assert recorded_headers["http-referer"] == "https://github.com/myc0576/Smartmoney-Cub"
    assert recorded_headers["x-openrouter-title"] == "SmartMoney-Cub"
    assert recorded_headers["authorization"] == "Bearer sk-or-test-secret"

    # Verify model_resolved is recorded from response
    assert decision.model_requested == "~typesafe/jev-latest"
    assert decision.model_resolved == "typesafe/jev-v1.0-preview"
    assert decision.request_id == "gen-openrouter-987"
    assert decision.safety == SAFETY_DECLARATION
    assert len(decision.answers) == 2
    assert decision.answers[0].value == "sufficient"
    assert decision.answers[1].value is False


def test_openrouter_backend_fails_on_protocol_errors():
    # Malformed answers payload
    def bad_content_client(req):
        return {
            "id": "gen-bad",
            "model": "typesafe/jev-v1.0",
            "choices": [{"message": {"content": "not-valid-json"}}],
        }

    backend = OpenRouterJevBackend(api_key="sk-test", http_client=bad_content_client)
    questions = (
        JevQuestion("q1", "choice", "Pick", choices=("a", "b")),
    )
    with pytest.raises(JevProtocolError):
        backend.evaluate({}, questions, decision_time="2026-06-01T15:00:00Z")


def test_openrouter_backend_fails_closed_on_network_error():
    def network_fail_client(req):
        raise ConnectionResetError("network peer dropped connection")

    backend = OpenRouterJevBackend(api_key="sk-test", http_client=network_fail_client)
    questions = (
        JevQuestion("q1", "choice", "Pick", choices=("a", "b")),
    )
    with pytest.raises(JevUnavailable, match="request failed"):
        backend.evaluate({}, questions, decision_time="2026-06-01T15:00:00Z")
