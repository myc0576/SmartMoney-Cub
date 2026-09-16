"""Cordis-facing, toy-backed review adapters.

The adapter seam is intentionally typed around Task 1's redacted review
envelope.  It has no upstream import, subprocess, network, filesystem, or
credential access.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from smartmoney_cub_harness.review_contracts import (
    PluginReviewResult,
    RedactedReviewEnvelope,
    ReviewEvidence,
    ReviewScope,
)
from smartmoney_cub_harness.review_validation import (
    ValidationResult,
    validate_challenger_only_mutation,
    validate_plugin_result,
    validate_redacted_payload,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


class CordisBoundaryError(ValueError):
    """Raised when data crosses the adapter boundary in an unsafe shape."""


def _sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CordisReviewRequest:
    """The only input shape accepted by a Cordis review adapter."""

    envelope: RedactedReviewEnvelope
    safety: str = SAFETY_DECLARATION

    def __post_init__(self) -> None:
        if self.safety != SAFETY_DECLARATION:
            raise CordisBoundaryError("invalid_safety")
        validation = validate_redacted_payload(self.envelope.payload)
        if not validation.ok:
            raise CordisBoundaryError("redaction_failed:" + ",".join(error.code for error in validation.errors))

    @classmethod
    def from_payload(cls, payload: Any) -> CordisReviewRequest:
        if not isinstance(payload, dict) or "envelope" not in payload:
            raise CordisBoundaryError("only a Task 1 redacted envelope is accepted")
        try:
            envelope = RedactedReviewEnvelope.from_dict(payload["envelope"])
            request = cls(envelope=envelope, safety=payload.get("safety", ""))
        except Exception as exc:
            if isinstance(exc, CordisBoundaryError):
                raise
            raise CordisBoundaryError(f"invalid_redacted_envelope:{type(exc).__name__}") from exc
        return request

    def to_dict(self) -> dict[str, Any]:
        return {"envelope": self.envelope.to_dict(), "safety": self.safety}


@dataclass(frozen=True)
class CordisAdapterResult:
    plugin_result: PluginReviewResult
    validation: dict[str, Any]
    safety: str = SAFETY_DECLARATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_result": self.plugin_result.to_dict(),
            "validation": self.validation,
            "safety": self.safety,
        }


class CordisReviewAdapter(Protocol):
    plugin_id: str

    def run(self, request: CordisReviewRequest) -> CordisAdapterResult: ...


def _observation(*, source: str, available_at: str, thesis: str) -> dict[str, Any]:
    return {
        "action_label": "WATCH",
        "invalidation_price": "unknown",
        "time_stop": "next review session close",
        "give_up_conditions": ["toy evidence is incomplete", "provenance becomes stale"],
        "data_source": source,
        "available_at": available_at,
        "data_quality_flag": "ok",
        "thesis": thesis,
    }


def _challenger(*, rule_id: str, rationale: str) -> dict[str, Any]:
    return {
        "candidate_role": "challenger",
        "rule_id": rule_id,
        "rationale": rationale,
        "champion_mutated": False,
        "core_rules_mutated": False,
    }


class _ToyAdapter:
    plugin_id = ""

    def _build_result(self, request: CordisReviewRequest) -> PluginReviewResult:
        raise NotImplementedError

    def run(self, request: CordisReviewRequest) -> CordisAdapterResult:
        if not isinstance(request, CordisReviewRequest):
            raise CordisBoundaryError("adapter_requires_CordisReviewRequest")
        result = self._build_result(request)
        validation: ValidationResult = validate_plugin_result(
            result,
            decision_time=request.envelope.scope.decision_time,
        )
        payload = validation.to_dict()
        if not validation.ok:
            raise CordisBoundaryError("plugin_result_validation_failed:" + ",".join(error["code"] for error in payload["errors"]))
        return CordisAdapterResult(plugin_result=result, validation=payload)


class TradingAgentsMultiRoleToyAdapter(_ToyAdapter):
    """Deterministic multi-role evidence resembling a debate, without an LLM."""

    plugin_id = "smartmoney.tradingagents-toy"

    def _build_result(self, request: CordisReviewRequest) -> PluginReviewResult:
        available_at = request.envelope.scope.decision_time
        evidence = tuple(
            ReviewEvidence(
                evidence_id=f"ta-{index}",
                kind=role,
                summary=summary,
                data_source="toy_tradingagents_fixture",
                available_at=available_at,
                data_quality_flag="ok",
            )
            for index, (role, summary) in enumerate(
                (
                    ("fundamental_analyst", "Toy fundamentals are illustrative only."),
                    ("technical_analyst", "Toy trend context is a review observation."),
                    ("risk_manager", "Toy risk review requires an explicit invalidation."),
                ),
                start=1,
            )
        )
        return PluginReviewResult(
            plugin_id=self.plugin_id,
            status="ok",
            observations=(
                _observation(
                    source="toy_tradingagents_fixture",
                    available_at=available_at,
                    thesis="Three toy roles disagree safely enough to warrant human review.",
                ),
            ),
            evidence=evidence,
            challenger_proposals=(
                _challenger(
                    rule_id="toy-ta-challenger-001",
                    rationale="Require agreement between toy roles before a review candidate is considered.",
                ),
            ),
            champion_mutated=False,
            core_rules_mutated=False,
        )


class EvaluatorMemoryChallengerToyAdapter(_ToyAdapter):
    """Deterministic evaluator/memory/challenger evidence over toy input."""

    plugin_id = "smartmoney.evaluator-memory-challenger-toy"

    def _build_result(self, request: CordisReviewRequest) -> PluginReviewResult:
        available_at = request.envelope.scope.decision_time
        evidence = tuple(
            ReviewEvidence(
                evidence_id=f"emc-{index}",
                kind=role,
                summary=summary,
                data_source="toy_evaluator_memory_fixture",
                available_at=available_at,
                data_quality_flag="ok",
            )
            for index, (role, summary) in enumerate(
                (
                    ("evaluator", "Toy sample count is intentionally small and non-promotional."),
                    ("memory", "Toy memory records portable review context only."),
                    ("challenger", "Toy challenger remains a proposal for later measurement."),
                ),
                start=1,
            )
        )
        return PluginReviewResult(
            plugin_id=self.plugin_id,
            status="ok",
            observations=(
                _observation(
                    source="toy_evaluator_memory_fixture",
                    available_at=available_at,
                    thesis="Evaluation and memory preserve uncertainty for human review.",
                ),
            ),
            evidence=evidence,
            challenger_proposals=(
                _challenger(
                    rule_id="toy-emc-challenger-001",
                    rationale="Keep the candidate in shadow evaluation until evidence thresholds are met.",
                ),
            ),
            champion_mutated=False,
            core_rules_mutated=False,
        )


def build_toy_review_request() -> CordisReviewRequest:
    """Build a redacted, deterministic fixture without reading a local file."""

    scope = ReviewScope(
        review_id="toy-review-0001",
        decision_time="2026-09-10T15:00:00+08:00",
        horizons=("d1", "d3"),
        case_ids=("toy-case-0001",),
    )
    payload = {
        "symbol": "symbol-12345678",
        "portfolio_id": "portfolio-12345678",
        "decision_date": "2026-09",
        "entry_time": "09:30-10:00",
        "amount": "0-10",
        "thesis": "toy offline evidence review",
    }
    envelope = RedactedReviewEnvelope(
        scope=scope,
        payload=payload,
        payload_sha256=_sha256(payload),
        redaction_policy="task1-redacted-typed-envelope",
        sent_keys=tuple(sorted(payload)),
    )
    return CordisReviewRequest(envelope=envelope)


def request_challenger_promotion(
    proposal: dict[str, Any], *, explicit_confirmation: bool
) -> dict[str, Any]:
    """Authorize a human handoff; never mutate champion state in the adapter layer."""

    validation = validate_challenger_only_mutation(proposal)
    if not validation.ok:
        raise CordisBoundaryError("challenger_gate_failed:" + ",".join(error.code for error in validation.errors))
    return {
        "status": "promotion_authorized" if explicit_confirmation else "awaiting_explicit_confirmation",
        "promotion_authorized": bool(explicit_confirmation),
        "explicit_confirmation": bool(explicit_confirmation),
        "champion_mutated": False,
        "core_rules_mutated": False,
        "next_step": "core_governance_human_mutation" if explicit_confirmation else "human_confirmation_required",
        "safety": SAFETY_DECLARATION,
    }

