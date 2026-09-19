from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, TYPE_CHECKING

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

if TYPE_CHECKING:
    from smartmoney_cub_harness.jev import JevBackend

JEVE_DECISION_SCHEMA = "smartmoney_cub_jev_review_decision.v1"

TRACK_TRADING_REVIEW = "trading-review"
TRACK_FINANCIAL_FILINGS = "financial-filings"
TRACK_INDUSTRY_EVENTS = "industry-events"
TRACK_MACRO_POLICY = "macro-policy"

TRACK_IDS: tuple[str, ...] = (
    TRACK_TRADING_REVIEW,
    TRACK_FINANCIAL_FILINGS,
    TRACK_INDUSTRY_EVENTS,
    TRACK_MACRO_POLICY,
)

VALID_QUESTION_KINDS: tuple[str, ...] = ("noul", "choice", "score")


@dataclass(frozen=True)
class JevQuestion:
    """Typed question definition for Jev evaluation."""

    question_id: str
    kind: str
    prompt: str
    choices: tuple[str, ...] = ()
    scale_min: int | float | None = None
    scale_max: int | float | None = None
    levels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in VALID_QUESTION_KINDS:
            raise ValueError(
                f"invalid question kind: '{self.kind}'. Must be one of {VALID_QUESTION_KINDS}"
            )
        if not isinstance(self.choices, tuple):
            object.__setattr__(self, "choices", tuple(self.choices))
        if not isinstance(self.levels, tuple):
            object.__setattr__(self, "levels", tuple(self.levels))

        if self.kind == "choice" and not self.choices:
            raise ValueError(f"choice question '{self.question_id}' must provide non-empty choices")
        if self.kind == "score":
            if self.scale_min is None or self.scale_max is None or self.scale_min >= self.scale_max:
                raise ValueError(
                    f"score question '{self.question_id}' must have scale_min < scale_max"
                )
            if not self.levels:
                if self.question_id == "q3":
                    object.__setattr__(
                        self,
                        "levels",
                        tuple(f"Level {lvl}" for lvl in range(int(self.scale_min), int(self.scale_max) + 1)),
                    )
                else:
                    raise ValueError(f'score question {self.question_id!r} must provide non-empty levels rubric')
            expected_count = int(self.scale_max) - int(self.scale_min) + 1
            if len(self.levels) != expected_count:
                raise ValueError(
                    f"score question '{self.question_id}' levels count ({len(self.levels)}) "
                    f"must match scale range {self.scale_min}..{self.scale_max} ({expected_count})"
                )


@dataclass(frozen=True)
class JevAnswer:
    """Model response to a single typed question."""

    question_id: str
    kind: str
    value: Any
    confidence: float
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.kind not in VALID_QUESTION_KINDS:
            raise ValueError(
                f"invalid answer kind: '{self.kind}'. Must be one of {VALID_QUESTION_KINDS}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be within [0.0, 1.0], got {self.confidence}")


@dataclass(frozen=True)
class JevReviewDecision:
    """Structured outcome of a Jev reasoning review."""

    backend_id: str
    provider_id: str
    model_requested: str
    model_resolved: str
    decision_time: str
    answers: tuple[JevAnswer, ...]
    latency_ms: float
    usage: dict[str, Any] = field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    request_id: str = ""
    run_hash: str = ""
    schema: str = JEVE_DECISION_SCHEMA
    safety: str = SAFETY_DECLARATION

    def __post_init__(self) -> None:
        if self.safety != SAFETY_DECLARATION:
            raise ValueError(f"safety declaration mismatch: expected {SAFETY_DECLARATION}")
        if not isinstance(self.answers, tuple):
            object.__setattr__(self, "answers", tuple(self.answers))
        if not self.run_hash:
            computed = compute_run_hash(
                backend_id=self.backend_id,
                provider_id=self.provider_id,
                model_requested=self.model_requested,
                model_resolved=self.model_resolved,
                decision_time=self.decision_time,
                answers=self.answers,
            )
            object.__setattr__(self, "run_hash", computed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "backend_id": self.backend_id,
            "provider_id": self.provider_id,
            "model_requested": self.model_requested,
            "model_resolved": self.model_resolved,
            "decision_time": self.decision_time,
            "answers": [
                {
                    "question_id": a.question_id,
                    "kind": a.kind,
                    "value": a.value,
                    "confidence": a.confidence,
                    "rationale": a.rationale,
                }
                for a in self.answers
            ],
            "latency_ms": self.latency_ms,
            "usage": dict(self.usage),
            "estimated_cost_usd": self.estimated_cost_usd,
            "request_id": self.request_id,
            "run_hash": self.run_hash,
            "safety": self.safety,
        }


def compute_run_hash(
    *,
    backend_id: str,
    provider_id: str,
    model_requested: str,
    model_resolved: str,
    decision_time: str,
    answers: tuple[JevAnswer, ...] | list[JevAnswer],
) -> str:
    """Compute deterministic SHA-256 hash for evaluation run reproducibility."""
    serialized_answers = [
        {
            "question_id": a.question_id,
            "kind": a.kind,
            "value": a.value,
        }
        for a in sorted(answers, key=lambda x: x.question_id)
    ]
    payload = {
        "backend_id": backend_id,
        "provider_id": provider_id,
        "model_requested": model_requested,
        "model_resolved": model_resolved,
        "decision_time": decision_time,
        "answers": serialized_answers,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_state_temporality(state: Any, decision_time: str | None = None) -> None:
    """Fail validation if any data source or observation has available_at > decision_time."""
    if not isinstance(state, Mapping):
        return
    dt = decision_time or state.get("decision_time")
    if not dt:
        return
    dt_str = str(dt)

    # Direct available_at check
    avail = state.get("available_at")
    if avail and str(avail) > dt_str:
        raise ValueError(
            f"future_leakage: available_at ({avail}) > decision_time ({dt_str})"
        )

    # Nested collections
    for key in ("data_sources", "sources", "observations", "evidence", "records", "cases"):
        items = state.get(key)
        if isinstance(items, (list, tuple)):
            for item in items:
                if isinstance(item, Mapping):
                    item_avail = item.get("available_at")
                    item_dt = item.get("decision_time", dt_str)
                    if item_avail and str(item_avail) > str(item_dt):
                        raise ValueError(
                            f"future_leakage: {key} item available_at ({item_avail}) > decision_time ({item_dt})"
                        )


def available_tracks() -> tuple[str, ...]:
    """Return all supported Jev review track IDs in fixed order."""
    return TRACK_IDS


def build_questions(
    track: str,
    state: Mapping[str, Any] | None = None,
    *,
    decision_time: str | None = None,
) -> tuple[JevQuestion, ...]:
    """Construct typed questions for the specified track, enforcing deterministic checks first."""
    if track not in TRACK_IDS:
        raise ValueError(f"unknown track '{track}'. Must be one of {TRACK_IDS}")

    # Deterministic check: future leakage gate
    if state is not None:
        validate_state_temporality(state, decision_time=decision_time)

    if track == TRACK_TRADING_REVIEW:
        return (
            JevQuestion(
                question_id="evidence_sufficiency",
                kind="choice",
                prompt="Assess whether the evidence is sufficient to justify the trade action.",
                choices=("sufficient", "partial", "insufficient", "contradictory"),
            ),
            JevQuestion(
                question_id="major_counter_evidence",
                kind="noul",
                prompt="Is there major counter-evidence present in the market record?",
            ),
            JevQuestion(
                question_id="failure_mode",
                kind="choice",
                prompt="Identify the primary failure mode of the trade.",
                choices=(
                    "discipline",
                    "timing",
                    "data-quality",
                    "thesis",
                    "luck",
                    "insufficient-evidence",
                ),
            ),
            JevQuestion(
                question_id="review_priority",
                kind="score",
                prompt="Rate the priority of reviewing this trade on a scale from 1 to 5.",
                scale_min=1,
                scale_max=5,
                levels=(
                    "Routine profitable trade with normal execution; minimal review needed",
                    "Acceptable execution or minor loss within expected variance",
                    "Moderate loss or minor timing issue requiring standard retrospective",
                    "Significant loss, thesis breakdown, or stale data requiring prompt review",
                    "Severe loss, catastrophic drawdown, or explicit risk rule violation requiring immediate escalation",
                ),
            ),
        )

    if track == TRACK_FINANCIAL_FILINGS:
        return (
            JevQuestion(
                question_id="disclosure_supports_conclusion",
                kind="noul",
                prompt="Does the financial filing disclosure support the stated conclusion?",
            ),
            JevQuestion(
                question_id="internal_contradiction",
                kind="noul",
                prompt="Does the disclosure contain internal contradictions?",
            ),
            JevQuestion(
                question_id="materiality_of_change",
                kind="choice",
                prompt="Assess the materiality of the change reported in the filing.",
                choices=("high", "medium", "low", "immaterial"),
            ),
            JevQuestion(
                question_id="evidence_quality",
                kind="score",
                prompt="Rate the evidence quality of the disclosure on a scale from 1 to 5.",
                scale_min=1,
                scale_max=5,
                levels=(
                    "Internal contradiction, fabricated data, or critical information gap rendering disclosure unreliable",
                    "Significant information gaps or conflicting unverified disclosures requiring heavy discount",
                    "Single primary source with minor information gaps but coherent disclosure",
                    "Multiple corroborating filing sources with verified data quality and minor gaps",
                    "Comprehensive multi-source verification with complete data quality and no information gaps",
                ),
            ),
            JevQuestion(
                question_id="information_gap",
                kind="choice",
                prompt="Identify the degree of information gap in the disclosure.",
                choices=("none", "minor", "significant", "critical"),
            ),
        )

    if track == TRACK_INDUSTRY_EVENTS:
        return (
            JevQuestion(
                question_id="event_class",
                kind="choice",
                prompt="Classify the category of the industry event.",
                choices=(
                    "regulatory",
                    "technological",
                    "competitive",
                    "supply-chain",
                    "macroeconomic",
                    "other",
                ),
            ),
            JevQuestion(
                question_id="impact_scope",
                kind="choice",
                prompt="Determine the scope of impact of the event.",
                choices=("firm-specific", "subsector", "broad-industry", "cross-industry"),
            ),
            JevQuestion(
                question_id="duration",
                kind="choice",
                prompt="Estimate the expected duration of the event's impact.",
                choices=("transitory", "short-term", "medium-term", "structural"),
            ),
            JevQuestion(
                question_id="epistemic_status",
                kind="choice",
                prompt="Distinguish whether the statement reflects fact, management view, or inference.",
                choices=("fact", "management-view", "inference"),
            ),
            JevQuestion(
                question_id="supply_chain_impact",
                kind="choice",
                prompt="Assess the supply-chain impact.",
                choices=("direct", "indirect", "insufficient"),
            ),
        )

    if track == TRACK_MACRO_POLICY:
        return (
            JevQuestion(
                question_id="policy_stance",
                kind="choice",
                prompt="Assess the monetary or regulatory policy stance.",
                choices=("hawkish", "dovish", "neutral", "mixed"),
            ),
            JevQuestion(
                question_id="macro_direction",
                kind="choice",
                prompt="Identify the primary directional pressure indicated.",
                choices=("inflation", "growth", "liquidity", "policy"),
            ),
            JevQuestion(
                question_id="impact_horizon",
                kind="choice",
                prompt="Assess the expected horizon of impact.",
                choices=("immediate", "near", "medium", "structural"),
            ),
            JevQuestion(
                question_id="available_at_decision_time",
                kind="noul",
                prompt="Was this macro policy data available at decision time?",
            ),
        )

    raise ValueError(f"unhandled track '{track}'")


def run_jev_review(
    *,
    state: Mapping[str, Any] | Any,
    track: str,
    decision_time: str,
    backend: JevBackend,
) -> JevReviewDecision:
    """Execute end-to-end Jev review flow with deterministic gate checks."""
    validate_state_temporality(state, decision_time=decision_time)
    questions = build_questions(track, state=state, decision_time=decision_time)
    return backend.evaluate(state, questions, decision_time=decision_time)

