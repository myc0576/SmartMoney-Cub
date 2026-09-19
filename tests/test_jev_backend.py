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
    # Backend constructed with credential but no client must NOT report available
    backend = TypeSafeDirectJevBackend(api_key="test-key-mock", http_client=None)
    health = backend.health()
    assert health["available"] is False
    assert health["reason"] == "no_client"
    assert health["safety"] == SAFETY_DECLARATION

    questions = (
        JevQuestion("q1", "choice", "Pick", choices=("yes", "no")),
    )
    with pytest.raises(JevUnavailable, match="no client is wired"):
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
    health = backend.health()
    assert health["available"] is True
    assert health["safety"] == SAFETY_DECLARATION

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


def test_openrouter_backend_fails_closed_when_missing_base_url():
    backend = OpenRouterJevBackend(api_key="sk-test", base_url="")
    health = backend.health()
    assert health["available"] is False
    assert health["reason"] == "missing_base_url"
    assert health["safety"] == SAFETY_DECLARATION
    questions = (JevQuestion("q1", "choice", "Pick", choices=("a", "b")),)
    with pytest.raises(JevUnavailable, match="missing base_url"):
        backend.evaluate({}, questions, decision_time="2026-06-01T15:00:00Z")

def test_typesafe_direct_backend_contract_mapping_choice_noul_score():
    def mock_wire_client(req):
        # Verify request payload
        body = json.loads(req.data.decode("utf-8"))
        assert body["model"] == "jev-latest"
        assert body["questions"]["q_choice"]["type"] == "choice"
        assert body["questions"]["q_choice"]["criteria"] == {"sufficient": "sufficient", "partial": "partial"}
        assert body["questions"]["q_noul"]["type"] == "noul"
        assert body["questions"]["q_score"]["type"] == "score"
        assert body["questions"]["q_score"]["criteria"] == ["Level 1", "Level 2", "Level 3", "Level 4", "Level 5"]

        return {
            "model": "jev-1.13.0",
            "answers": {
                "q_choice": {
                    "type": "choice",
                    "choice": "sufficient",
                    "confidence": 0.98,
                    "probabilities": {"sufficient": 0.98, "partial": 0.02},
                },
                "q_noul": {
                    "type": "noul",
                    "noul": 0.06,
                },
                "q_score": {
                    "type": "score",
                    "score": 1.96,
                    "confidence": 0.06,
                    "legend": {"0": "Level 1", "1": "Level 2", "2": "Level 3", "3": "Level 4", "4": "Level 5"},
                    "probabilities": {"0": 0.12, "1": 0.21, "2": 0.31, "3": 0.31, "4": 0.05},
                },
            },
            "usage": {"input_tokens": 499, "output_tokens": 20},
        }

    backend = TypeSafeDirectJevBackend(api_key="test-key", http_client=mock_wire_client)
    questions = (
        JevQuestion("q_choice", "choice", "Assess sufficiency", choices=("sufficient", "partial")),
        JevQuestion("q_noul", "noul", "Is counter evidence present?"),
        JevQuestion("q_score", "score", "Rate priority", scale_min=1, scale_max=5),
    )

    decision = backend.evaluate({"notes": "data"}, questions, decision_time="2026-06-01T15:00:00Z")

    assert decision.model_requested == "jev-latest"
    assert decision.model_resolved == "jev-1.13.0"
    assert decision.request_id == ""
    assert decision.estimated_cost_usd == 0.0
    assert decision.usage == {"input_tokens": 499, "output_tokens": 20}

    ans_map = {a.question_id: a for a in decision.answers}

    # Choice mapping
    assert ans_map["q_choice"].value == "sufficient"
    assert ans_map["q_choice"].confidence == 0.98

    # Noul mapping: 0.06 < 0.5 -> False, confidence = 0.06
    assert ans_map["q_noul"].value is False
    assert ans_map["q_noul"].confidence == 0.06

    # Score mapping: 1.96 index + scale_min(1) = 2.96 -> rounded to 3
    assert ans_map["q_score"].value == 3
    assert ans_map["q_score"].confidence == 0.06


def test_typesafe_direct_backend_disallowed_choice_raises_protocol_error():
    def mock_bad_choice(req):
        return {
            "model": "jev-1.13.0",
            "answers": {
                "q_choice": {
                    "type": "choice",
                    "choice": "hallucinated_choice",
                    "confidence": 0.9,
                }
            },
            "usage": {"input_tokens": 100, "output_tokens": 10},
        }

    backend = TypeSafeDirectJevBackend(api_key="test-key", http_client=mock_bad_choice)
    questions = (
        JevQuestion("q_choice", "choice", "Pick", choices=("valid_a", "valid_b")),
    )
    with pytest.raises(JevProtocolError, match="not in allowed choices"):
        backend.evaluate({"case": "toy"}, questions, decision_time="2026-06-01T15:00:00Z")


def test_typesafe_direct_backend_live_smoke_skipped_without_key():
    if not os.environ.get("TYPESAFE_LIVE_TEST"):
        pytest.skip("TYPESAFE_LIVE_TEST not set; skipping live test")

    key_path = "/tmp/.ts_probe_key"
    if not os.path.exists(key_path):
        pytest.skip("no live key file at /tmp/.ts_probe_key")

    with open(key_path) as f:
        key = f.read().strip()
    if not key:
        pytest.skip("empty key file")

    os.environ["TYPESAFE_LIVE_ENABLED"] = "1"
    try:
        backend = TypeSafeDirectJevBackend(api_key=key)
        questions = (
            JevQuestion("major_counter_evidence", "noul", "Does major counter-evidence appear in the record?"),
        )
        decision = backend.evaluate({"notes": "smoke test"}, questions, decision_time="2026-06-01T15:00:00Z")
        assert decision.model_resolved.startswith("jev-")
        assert len(decision.answers) == 1
        assert isinstance(decision.answers[0].value, bool)
        assert 0.0 <= decision.answers[0].confidence <= 1.0
    finally:
        os.environ.pop("TYPESAFE_LIVE_ENABLED", None)

