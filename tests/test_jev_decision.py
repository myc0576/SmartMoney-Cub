from __future__ import annotations

import dataclasses
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

from smartmoney_cub_harness import cli
from smartmoney_cub_harness.jev import (
    JEVE_DECISION_SCHEMA,
    TRACK_TRADING_REVIEW,
    JevAnswer,
    JevQuestion,
    JevReviewDecision,
    compute_run_hash,
    run_jev_review,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_jev_review_decision_fields_and_types():
    ans = JevAnswer(
        question_id="evidence_sufficiency",
        kind="choice",
        value="sufficient",
        confidence=0.95,
        rationale="Clear verifiable disclosures",
    )
    decision = JevReviewDecision(
        backend_id="openrouter-jev",
        provider_id="openrouter",
        model_requested="~typesafe/jev-latest",
        model_resolved="typesafe/jev-v1.0-preview",
        decision_time="2026-06-01T15:00:00Z",
        answers=(ans,),
        latency_ms=123.4,
        usage={"prompt_tokens": 120, "completion_tokens": 40},
        estimated_cost_usd=0.00096,
        request_id="req-test-abc",
    )

    assert decision.schema == JEVE_DECISION_SCHEMA
    assert decision.backend_id == "openrouter-jev"
    assert decision.provider_id == "openrouter"
    assert decision.model_requested == "~typesafe/jev-latest"
    assert decision.model_resolved == "typesafe/jev-v1.0-preview"
    assert decision.decision_time == "2026-06-01T15:00:00Z"
    assert len(decision.answers) == 1
    assert decision.latency_ms == 123.4
    assert decision.usage == {"prompt_tokens": 120, "completion_tokens": 40}
    assert decision.estimated_cost_usd == 0.00096
    assert decision.request_id == "req-test-abc"
    assert decision.run_hash != ""
    assert decision.safety == SAFETY_DECLARATION


def test_jev_review_decision_is_frozen():
    ans = JevAnswer(question_id="q1", kind="noul", value=True, confidence=1.0)
    decision = JevReviewDecision(
        backend_id="b1",
        provider_id="p1",
        model_requested="m1",
        model_resolved="m1-resolved",
        decision_time="2026-06-01T15:00:00Z",
        answers=(ans,),
        latency_ms=10.0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.backend_id = "other"  # type: ignore


def test_jev_review_decision_safety_mismatch_raises():
    ans = JevAnswer(question_id="q1", kind="noul", value=True, confidence=1.0)
    with pytest.raises(ValueError, match="safety declaration mismatch"):
        JevReviewDecision(
            backend_id="b1",
            provider_id="p1",
            model_requested="m1",
            model_resolved="m1-resolved",
            decision_time="2026-06-01T15:00:00Z",
            answers=(ans,),
            latency_ms=10.0,
            safety="INVALID_SAFETY_DECLARATION",
        )


def test_jev_review_decision_to_dict_serialization():
    ans = JevAnswer(
        question_id="q1",
        kind="choice",
        value="opt_a",
        confidence=0.85,
        rationale="rational reasoning",
    )
    decision = JevReviewDecision(
        backend_id="test-backend",
        provider_id="test-provider",
        model_requested="test-model",
        model_resolved="test-model-v1",
        decision_time="2026-06-01T15:00:00Z",
        answers=(ans,),
        latency_ms=45.6,
    )
    data = decision.to_dict()
    assert data["schema"] == JEVE_DECISION_SCHEMA
    assert data["backend_id"] == "test-backend"
    assert data["provider_id"] == "test-provider"
    assert data["model_requested"] == "test-model"
    assert data["model_resolved"] == "test-model-v1"
    assert data["safety"] == SAFETY_DECLARATION
    assert data["run_hash"] == decision.run_hash
    assert len(data["answers"]) == 1
    assert data["answers"][0]["question_id"] == "q1"
    assert data["answers"][0]["value"] == "opt_a"

    # Must be JSON serializable
    serialized = json.dumps(data)
    assert isinstance(serialized, str)
    loaded = json.loads(serialized)
    assert loaded["safety"] == SAFETY_DECLARATION


def test_compute_run_hash_determinism_and_sensitivity():
    ans1 = JevAnswer("q1", "choice", "yes", 0.9)
    ans2 = JevAnswer("q2", "score", 4, 0.8)

    hash1 = compute_run_hash(
        backend_id="b1",
        provider_id="p1",
        model_requested="mr",
        model_resolved="mres",
        decision_time="2026-06-01T15:00:00Z",
        answers=[ans1, ans2],
    )
    hash2 = compute_run_hash(
        backend_id="b1",
        provider_id="p1",
        model_requested="mr",
        model_resolved="mres",
        decision_time="2026-06-01T15:00:00Z",
        answers=[ans2, ans1],  # reversed order should still produce same hash
    )
    assert hash1 == hash2
    assert len(hash1) == 64

    # Sensitivity check
    hash_diff = compute_run_hash(
        backend_id="b1",
        provider_id="p1",
        model_requested="mr",
        model_resolved="mres-different",
        decision_time="2026-06-01T15:00:00Z",
        answers=[ans1, ans2],
    )
    assert hash1 != hash_diff


def test_run_jev_review_flow_with_mock_backend():
    class MockBackend:
        backend_id = "mock-backend"
        provider_id = "mock-provider"
        model_requested = "mock-model"

        def health(self):
            return {"status": "ok", "available": True, "safety": SAFETY_DECLARATION}

        def evaluate(self, state, questions, *, decision_time):
            answers = tuple(
                JevAnswer(q.question_id, q.kind, "mock_val", 1.0) for q in questions
            )
            return JevReviewDecision(
                backend_id=self.backend_id,
                provider_id=self.provider_id,
                model_requested=self.model_requested,
                model_resolved="mock-model-resolved",
                decision_time=decision_time,
                answers=answers,
                latency_ms=10.0,
            )

    valid_state = {
        "decision_time": "2026-06-01T15:00:00Z",
        "available_at": "2026-06-01T14:55:00Z",
    }
    decision = run_jev_review(
        state=valid_state,
        track=TRACK_TRADING_REVIEW,
        decision_time="2026-06-01T15:00:00Z",
        backend=MockBackend(),
    )
    assert isinstance(decision, JevReviewDecision)
    assert decision.safety == SAFETY_DECLARATION
    assert len(decision.answers) == 4

    # Rejection of future leakage
    leaked_state = {
        "decision_time": "2026-06-01T15:00:00Z",
        "available_at": "2026-06-01T15:01:00Z",
    }
    with pytest.raises(ValueError, match="future_leakage"):
        run_jev_review(
            state=leaked_state,
            track=TRACK_TRADING_REVIEW,
            decision_time="2026-06-01T15:00:00Z",
            backend=MockBackend(),
        )


def test_cli_jev_doctor_command(capsys):
    exit_code = cli.main(["jev", "doctor"])
    assert exit_code == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["status"] == "ok"
    assert payload["engine"] == "jev"
    assert payload["safety"] == SAFETY_DECLARATION
    assert payload["tracks"] == [
        "trading-review",
        "financial-filings",
        "industry-events",
        "macro-policy",
    ]
    assert "typesafe-direct" in payload["backends"]
    assert "openrouter-jev" in payload["backends"]
    assert payload["network_required"] is False
    assert payload["execution_integrations"] == "disabled"
