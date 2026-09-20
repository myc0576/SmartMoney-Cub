from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend
from smartmoney_cub_harness.jev.errors import JevError, JevProtocolError, JevUnavailable
from smartmoney_cub_harness.jev.openrouter import OpenRouterJevBackend
from smartmoney_cub_harness.jev.questions import (
    JEVE_DECISION_SCHEMA,
    TRACK_FINANCIAL_FILINGS,
    TRACK_IDS,
    TRACK_INDUSTRY_EVENTS,
    TRACK_MACRO_POLICY,
    TRACK_TRADING_REVIEW,
    JevAnswer,
    JevQuestion,
    JevReviewDecision,
    available_tracks,
    build_questions,
    compute_run_hash,
    run_jev_review,
    validate_state_temporality,
)


@runtime_checkable
class JevBackend(Protocol):
    """Protocol interface that every Jev review backend must implement."""

    backend_id: str
    provider_id: str
    model_requested: str

    def health(self) -> dict[str, Any]:
        ...

    def evaluate(
        self,
        state: Mapping[str, Any] | Any,
        questions: tuple[JevQuestion, ...],
        *,
        decision_time: str,
    ) -> JevReviewDecision:
        ...


__all__ = (
    "JEVE_DECISION_SCHEMA",
    "TRACK_TRADING_REVIEW",
    "TRACK_FINANCIAL_FILINGS",
    "TRACK_INDUSTRY_EVENTS",
    "TRACK_MACRO_POLICY",
    "TRACK_IDS",
    "JevQuestion",
    "JevAnswer",
    "JevReviewDecision",
    "JevBackend",
    "build_questions",
    "available_tracks",
    "run_jev_review",
    "compute_run_hash",
    "validate_state_temporality",
    "JevUnavailable",
    "JevProtocolError",
    "JevError",
    "TypeSafeDirectJevBackend",
    "OpenRouterJevBackend",
)
