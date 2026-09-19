from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
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


class OpenRouterJevBackend:
    """OpenRouter proxy backend for Jev reasoning model."""

    backend_id: str = "openrouter-jev"
    provider_id: str = "openrouter"

    def __init__(
        self,
        api_key: str | None = None,
        model_requested: str = "~typesafe/jev-latest",
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 30.0,
        http_client: Callable[[urllib.request.Request], dict[str, Any]] | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
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
        return {
            "status": "ok",
            "available": True,
            "backend_id": self.backend_id,
            "provider_id": self.provider_id,
            "model_requested": self.model_requested,
            "model_resolved": None,
            "safety": SAFETY_DECLARATION,
        }

    def evaluate(
        self,
        state: Mapping[str, Any] | Any,
        questions: tuple[JevQuestion, ...],
        *,
        decision_time: str,
    ) -> JevReviewDecision:
        """Evaluate state against questions via OpenRouter API, recording model_resolved."""
        if not self.api_key:
            raise JevUnavailable("OpenRouter Jev backend unavailable: missing OPENROUTER_API_KEY")

        start_t = time.perf_counter()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/myc0576/Smartmoney-Cub",
            "X-OpenRouter-Title": "SmartMoney-Cub",
            "Content-Type": "application/json",
        }

        system_prompt = (
            "You are Jev, a specialized financial reasoning engine. "
            "Evaluate the provided state against each typed question. "
            "You must output ONLY valid JSON in the following format: "
            '{"answers": [{"question_id": str, "kind": "noul"|"choice"|"score", '
            '"value": bool|str|number, "confidence": float, "rationale": str}]}'
        )

        user_payload = {
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

        body = {
            "model": self.model_requested,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
        }

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        if self.http_client is not None:
            try:
                data = self.http_client(req)
            except Exception as exc:
                if isinstance(exc, (JevUnavailable, JevProtocolError)):
                    raise
                raise JevUnavailable(f"OpenRouter client request failed: {exc}") from exc
        else:
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
                raise JevUnavailable(f"OpenRouter network request failed: {exc}") from exc
            except json.JSONDecodeError as exc:
                raise JevProtocolError(f"OpenRouter response is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise JevProtocolError("OpenRouter response payload must be a JSON object")

        model_resolved = data.get("model") or self.model_requested
        request_id = str(data.get("id", ""))
        usage = dict(data.get("usage", {}))

        # Calculate estimated cost if pricing info or token counts available
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        # Conservative standard baseline estimation
        estimated_cost_usd = round(
            (prompt_tokens * 0.000003) + (completion_tokens * 0.000015), 6
        )

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise JevProtocolError("OpenRouter response missing valid 'choices' array")

        message = choices[0].get("message", {})
        content_raw = message.get("content", "")
        if isinstance(content_raw, str):
            try:
                parsed_content = json.loads(content_raw)
            except json.JSONDecodeError as exc:
                raise JevProtocolError(
                    f"Model output content is not valid JSON: {exc}"
                ) from exc
        elif isinstance(content_raw, dict):
            parsed_content = content_raw
        else:
            raise JevProtocolError(f"Unexpected content type: {type(content_raw)}")

        raw_answers = parsed_content.get("answers")
        if not isinstance(raw_answers, list):
            raise JevProtocolError("Parsed content missing 'answers' list")

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
