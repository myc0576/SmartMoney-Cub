from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
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

_DEFAULT_CLIENT = object()


class TypeSafeDirectJevBackend:
    """Direct integration backend for TypeSafe Jev API."""

    backend_id: str = "typesafe-direct"
    provider_id: str = "typesafe"

    def __init__(
        self,
        api_key: str | None = None,
        model_requested: str = "jev-latest",
        base_url: str = "https://api.typesafe.ai",
        timeout_seconds: float = 30.0,
        http_client: Any = _DEFAULT_CLIENT,
        *,
        credentials_root: str | Path | None = None,
        max_attempts: int = 3,
    ) -> None:
        from smartmoney_cub_harness.jev.connection import credential

        self.api_key = api_key if api_key is not None else credential(credentials_root)[0]
        self.model_requested = model_requested
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client
        self.max_attempts = max(1, min(int(max_attempts), 3))

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
                "TypeSafe direct backend endpoint is unreachable: no client is wired in this environment"
            )

        start_t = time.perf_counter()

        formatted_questions: dict[str, Any] = {}
        for q in questions:
            if q.kind == "noul":
                formatted_questions[q.question_id] = {
                    "type": "noul",
                    "instructions": q.prompt,
                }
            elif q.kind == "choice":
                crit = dict(getattr(q, "choice_criteria", {}))
                if not crit:
                    crit = {c: c for c in q.choices}
                formatted_questions[q.question_id] = {
                    "type": "choice",
                    "instructions": q.prompt,
                    "criteria": crit,
                }
            elif q.kind == "score":
                s_min = int(q.scale_min) if q.scale_min is not None else 0
                criteria_list = list(q.levels) if q.levels else [f"Level {lvl}" for lvl in range(s_min, s_min + 1)]
                formatted_questions[q.question_id] = {
                    "type": "score",
                    "instructions": q.prompt,
                    "criteria": criteria_list,
                }
            else:
                raise JevProtocolError(f"Unsupported question kind: {q.kind}")

        request_payload = {
            "model": self.model_requested,
            "questions": formatted_questions,
            "state": state,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(
            f"{self.base_url}/v1/systemone",
            data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        resp_data = self._execute_request(req, request_payload)

        model_resolved = resp_data.get("model_resolved") or resp_data.get("model") or self.model_requested
        raw_answers = resp_data.get("answers")
        if isinstance(raw_answers, list):
            answers_by_id = {
                a.get("question_id"): a for a in raw_answers if isinstance(a, dict)
            }
        elif isinstance(raw_answers, dict):
            answers_by_id = raw_answers
        else:
            raise JevProtocolError("TypeSafe response missing answers object or list")

        parsed_answers: list[JevAnswer] = []
        for q in questions:
            raw_ans = answers_by_id.get(q.question_id)
            if raw_ans is None:
                raise JevProtocolError(f"Missing answer for question {q.question_id}")
            if not isinstance(raw_ans, dict):
                raise JevProtocolError(f"Answer for {q.question_id} must be an object")

            ans_type = raw_ans.get("type")
            if ans_type is not None and ans_type != q.kind:
                raise JevProtocolError(
                    f"Type mismatch for {q.question_id}: expected {q.kind}, got {ans_type}"
                )

            val = raw_ans.get("value")
            if q.kind == "noul":
                if isinstance(val, str):
                    val = val.lower() in ("true", "yes", "1")
                else:
                    val = bool(val)
                prob = raw_ans.get("noul")
                if prob is not None:
                    conf = float(prob)
                    val = conf >= 0.5
                else:
                    conf = float(raw_ans.get("confidence", 1.0))
            elif q.kind == "choice":
                if "choice" in raw_ans:
                    val = str(raw_ans["choice"])
                else:
                    val = str(val if val is not None else "")
                if q.choices and val not in q.choices:
                    raise JevProtocolError(
                        f"Answer {val} for {q.question_id} not in allowed choices {q.choices}"
                    )
                conf = float(raw_ans.get("confidence", 1.0))
            elif q.kind == "score":
                raw_score = raw_ans.get("score")
                s_min = int(q.scale_min) if q.scale_min is not None else 0
                if raw_score is not None:
                    float_index = float(raw_score)
                    val = int(round(float_index + s_min))
                    conf = float(raw_ans.get("confidence", float_index))
                else:
                    try:
                        val = float(val) if "." in str(val) else int(val)
                    except (ValueError, TypeError) as exc:
                        raise JevProtocolError(
                            f"Answer for score question {q.question_id} must be numeric"
                        ) from exc
                    conf = float(raw_ans.get("confidence", 1.0))
            else:
                conf = float(raw_ans.get("confidence", 1.0))

            conf = float(raw_ans.get("confidence", conf))
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
        estimated_cost_usd = (
            None if resp_data.get("estimated_cost_usd") is None else float(resp_data["estimated_cost_usd"])
        )
        request_id = str(resp_data.get("request_id", "") or "")

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
            estimated_cost_usd=estimated_cost_usd if estimated_cost_usd is not None else 0.0,
            request_id=request_id,
            run_hash=run_hash,
            safety=SAFETY_DECLARATION,
        )

    def _execute_request(
        self,
        req: urllib.request.Request,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.http_client is not _DEFAULT_CLIENT and self.http_client is not None:
            try:
                try:
                    return self.http_client(req)
                except TypeError:
                    return self.http_client(payload)
            except Exception as exc:
                if isinstance(exc, (JevUnavailable, JevProtocolError)):
                    raise
                raise JevUnavailable(f"TypeSafe direct request failed: {exc}") from exc

        max_attempts = self.max_attempts
        for attempt in range(1, max_attempts + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    raw_bytes = resp.read()
                    return json.loads(raw_bytes.decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
                if attempt < max_attempts:
                    time.sleep(1.0 * attempt)
                    continue
                raise JevUnavailable(f"TypeSafe direct request failed: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise JevProtocolError(f"TypeSafe direct response not valid JSON: {exc}") from exc
