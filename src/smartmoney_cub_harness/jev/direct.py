from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Mapping

from smartmoney_cub_harness.jev.errors import JevProtocolError, JevUnavailable
from smartmoney_cub_harness.jev.questions import (
    JEVE_DECISION_SCHEMA,
    JevAnswer,
    JevQuestion,
    JevReviewDecision,
    compute_run_hash,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


class TypeSafeDirectJevBackend:
    """Direct integration backend for TypeSafe Jev API."""

    backend_id: str = "typesafe-direct"
    provider_id: str = "typesafe"

    def __init__(
        self,
        api_key: str | None = None,
        model_requested: str = "typesafe/jev-direct",
        base_url: str = "https://api.typesafe.ai/v1",
        timeout_seconds: float = 30.0,
        http_client: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY")
        self.model_requested = model_requested
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    def health(self) -> dict[str, Any]:
        """Report backend health and credential status without network side effects."""
        if not self.api_key:
            return {
                "status": "unavailable",
                "available": False,
                "backend_id": self.backend_id,
                "provider_id": self.provider_id,
                "model_requested": self.model_requested,
                "model_resolved": None,
                "reason": "missing_credential",
                "safety": SAFETY_DECLARATION,
            }
        if self.http_client is None:
            return {
                "status": "unavailable",
                "available": False,
                "backend_id": self.backend_id,
                "provider_id": self.provider_id,
                "model_requested": self.model_requested,
                "model_resolved": None,
                "reason": "no_client",
                "safety": SAFETY_DECLARATION,
            }
        return {
            "status": "ok",
            "available": True,
            "backend_id": self.backend_id,
            "provider_id": self.provider_id,
            "model_requested": self.model_requested,
            "model_resolved": self.model_requested,
            "safety": SAFETY_DECLARATION,
        }

    def evaluate(
        self,
        state: Mapping[str, Any] | Any,
        questions: tuple[JevQuestion, ...],
        *,
        decision_time: str,
    ) -> JevReviewDecision:
        """Evaluate state against questions using TypeSafe direct API, failing closed."""
        if not self.api_key:
            raise JevUnavailable("TypeSafe direct backend unavailable: missing credential")

        if self.http_client is None:
            raise JevUnavailable(
                "TypeSafe direct backend endpoint is unreachable or no client is wired in this environment"
            )

        start_t = time.perf_counter()

        request_payload = {
            "model": self.model_requested,
            "state": state,
            "questions": [
                {
                    "question_id": q.question_id,
                    "kind": q.kind,
                    "prompt": q.prompt,
                    "choices": list(q.choices),
                    "scale_min": q.scale_min,
                    "scale_max": q.scale_max,
                }
                for q in questions
            ],
            "decision_time": decision_time,
        }

        try:
            resp_data = self.http_client(request_payload)
        except Exception as exc:
            raise JevUnavailable(f"TypeSafe direct request failed: {exc}") from exc

        model_resolved = resp_data.get("model_resolved") or resp_data.get("model") or self.model_requested
        raw_answers = resp_data.get("answers")
        if not isinstance(raw_answers, list):
            raise JevProtocolError("TypeSafe response missing 'answers' list")

        answers_by_id = {
            a.get("question_id"): a for a in raw_answers if isinstance(a, dict)
        }

        parsed_answers: list[JevAnswer] = []
        for q in questions:
            raw_ans = answers_by_id.get(q.question_id)
            if raw_ans is None:
                raise JevProtocolError(f"Missing answer for question '{q.question_id}'")

            val = raw_ans.get("value")
            if q.kind == "noul":
                if isinstance(val, str):
                    val = val.lower() in ("true", "yes", "1")
                else:
                    val = bool(val)
            elif q.kind == "choice":
                val = str(val)
                if q.choices and val not in q.choices:
                    raise JevProtocolError(
                        f"Answer '{val}' for '{q.question_id}' not in allowed choices {q.choices}"
                    )
            elif q.kind == "score":
                try:
                    val = float(val) if "." in str(val) else int(val)
                except (ValueError, TypeError) as exc:
                    raise JevProtocolError(
                        f"Answer for score question '{q.question_id}' must be numeric"
                    ) from exc

            conf = float(raw_ans.get("confidence", 1.0))
            rationale = str(raw_ans.get("rationale", ""))
            parsed_answers.append(
                JevAnswer(
                    question_id=q.question_id,
                    kind=q.kind,
                    value=val,
                    confidence=conf,
                    rationale=rationale,
                )
            )

        latency_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
        usage = dict(resp_data.get("usage", {}))
        estimated_cost_usd = float(resp_data.get("estimated_cost_usd", 0.0))
        request_id = str(resp_data.get("request_id", ""))

        run_hash = compute_run_hash(
            backend_id=self.backend_id,
            provider_id=self.provider_id,
            model_requested=self.model_requested,
            model_resolved=model_resolved,
            decision_time=decision_time,
            answers=parsed_answers,
        )

        return JevReviewDecision(
            schema=JEVE_DECISION_SCHEMA,
            backend_id=self.backend_id,
            provider_id=self.provider_id,
            model_requested=self.model_requested,
            model_resolved=model_resolved,
            decision_time=decision_time,
            answers=tuple(parsed_answers),
            latency_ms=latency_ms,
            usage=usage,
            estimated_cost_usd=estimated_cost_usd,
            request_id=request_id,
            run_hash=run_hash,
            safety=SAFETY_DECLARATION,
        )
