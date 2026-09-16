from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Iterator

from smartmoney_cub_harness.agent.provider_errors import (
    ClassifiedProviderError,
    FailurePhase,
    ProviderErrorCode,
    classify_provider_error,
)
from smartmoney_cub_harness.agent.providers import (
    OFFLINE_PROVIDER_ID,
    stream_chat,
)
from smartmoney_cub_harness.safety import redact


@dataclass
class RouteCandidate:
    provider_id: str
    model: str
    effort: str = "off"
    label: str = ""
    base_url: str = ""
    protocol: str = "openai-chat"
    api_key: str = ""
    portal_url: str = ""

    def to_provider_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "label": self.label or self.provider_id,
            "base_url": self.base_url,
            "protocol": self.protocol or ("offline" if self.provider_id == OFFLINE_PROVIDER_ID else "openai-chat"),
            "api_key": self.api_key,
            "portal_url": self.portal_url,
        }


class CooldownTracker:
    """Tracks per-target temporary cooldowns to prevent repeating known-failing routes."""

    def __init__(self) -> None:
        self._cooldowns: dict[str, float] = {}

    def _target_key(self, provider_id: str, model: str | None = None) -> str:
        return f"{provider_id}:{model}" if model else provider_id

    def mark_failure(
        self,
        provider_id: str,
        model: str,
        error: ClassifiedProviderError,
        now: float | None = None,
        duration_seconds: float | None = None,
    ) -> float:
        current_time = now if now is not None else time.time()
        if duration_seconds is None:
            if error.code == ProviderErrorCode.INSUFFICIENT_QUOTA:
                duration_seconds = 300.0
            elif error.code == ProviderErrorCode.RATE_LIMITED:
                duration_seconds = 30.0
            elif error.code in (ProviderErrorCode.SERVER_ERROR, ProviderErrorCode.TIMEOUT):
                duration_seconds = 15.0
            elif error.code == ProviderErrorCode.AUTHENTICATION:
                duration_seconds = 300.0
            else:
                duration_seconds = 10.0

        expiry = current_time + duration_seconds
        key = self._target_key(provider_id, model)
        self._cooldowns[key] = max(self._cooldowns.get(key, 0.0), expiry)
        self._cooldowns[provider_id] = max(self._cooldowns.get(provider_id, 0.0), expiry)
        return duration_seconds

    def is_cooling_down(
        self, provider_id: str, model: str | None = None, now: float | None = None
    ) -> bool:
        return self.remaining_cooldown(provider_id, model=model, now=now) > 0.0

    def remaining_cooldown(
        self, provider_id: str, model: str | None = None, now: float | None = None
    ) -> float:
        current_time = now if now is not None else time.time()
        key = self._target_key(provider_id, model)
        target_expiry = self._cooldowns.get(key, 0.0)
        provider_expiry = self._cooldowns.get(provider_id, 0.0)
        expiry = max(target_expiry, provider_expiry)
        return max(0.0, expiry - current_time)

    def clear(self, provider_id: str | None = None, model: str | None = None) -> None:
        if provider_id is None:
            self._cooldowns.clear()
            return
        self._cooldowns.pop(provider_id, None)
        if model is not None:
            self._cooldowns.pop(self._target_key(provider_id, model), None)
        else:
            # Clear all model-specific keys for this provider
            keys_to_delete = [k for k in self._cooldowns if k.startswith(f"{provider_id}:")]
            for k in keys_to_delete:
                self._cooldowns.pop(k, None)


@dataclass
class RouteChainPolicy:
    max_same_target_retries: int = 1
    initial_backoff_seconds: float = 0.5
    default_cooldown_seconds: float = 30.0
    cooldown_tracker: CooldownTracker = field(default_factory=CooldownTracker)


def _order_candidates_by_cooldown(
    candidates: list[RouteCandidate],
    tracker: CooldownTracker,
) -> list[RouteCandidate]:
    now = time.time()
    active: list[RouteCandidate] = []
    cooling: list[tuple[float, RouteCandidate]] = []

    for c in candidates:
        rem = tracker.remaining_cooldown(c.provider_id, c.model, now=now)
        if rem <= 0.0:
            active.append(c)
        else:
            cooling.append((rem, c))

    cooling.sort(key=lambda item: item[0])
    return active + [c for _, c in cooling]


def stream_chat_with_route_chain(
    candidates: list[RouteCandidate],
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    policy: RouteChainPolicy | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream chat through a candidate route chain with retries, cooldowns, and fallback.

    - Pre-stream errors can retry bounded times on the same target, or fall back to
      subsequent candidates (including offline).
    - Mid-stream errors fail immediately and do not restart from scratch to prevent
      duplicate transcript chunks.
    """
    if not candidates:
        raise ClassifiedProviderError(
            code=ProviderErrorCode.INVALID_REQUEST,
            message="No route candidates provided for route chain.",
            phase=FailurePhase.PRE_STREAM,
        )

    policy = policy or RouteChainPolicy()
    ordered_candidates = _order_candidates_by_cooldown(candidates, policy.cooldown_tracker)
    last_error: ClassifiedProviderError | None = None

    for idx, candidate in enumerate(ordered_candidates):
        is_last_candidate = idx == len(ordered_candidates) - 1
        provider_dict = candidate.to_provider_dict()

        # Handle offline candidate directly
        if (
            candidate.protocol == "offline"
            or candidate.provider_id == OFFLINE_PROVIDER_ID
            or provider_dict.get("protocol") == "offline"
        ):
            yield {
                "kind": "delta",
                "text": "【本地离线复盘】使用本地确定性启发式规则评估交易执行偏差与风控表现。",
            }
            yield {"kind": "done", "finish_reason": "stop"}
            return

        # Attempt with bounded same-target retries
        for attempt in range(1 + policy.max_same_target_retries):
            if attempt > 0:
                backoff = policy.initial_backoff_seconds * (2 ** (attempt - 1))
                time.sleep(min(backoff, 5.0))

            emitted_any = False
            try:
                stream_iter = stream_chat(
                    provider_dict,
                    model=candidate.model,
                    messages=messages,
                    tools=tools,
                    effort=candidate.effort,
                )
                for event in stream_iter:
                    emitted_any = True
                    yield event
                # Successfully finished
                policy.cooldown_tracker.clear(candidate.provider_id, candidate.model)
                return
            except ClassifiedProviderError as exc:
                classified = exc
            except Exception as raw_exc:
                phase = FailurePhase.MID_STREAM if emitted_any else FailurePhase.PRE_STREAM
                classified = classify_provider_error(
                    raw_exc,
                    provider=provider_dict,
                    model=candidate.model,
                    phase=phase,
                )

            last_error = classified

            # If failure happened mid-stream, never silently replay from scratch
            if classified.phase == FailurePhase.MID_STREAM:
                policy.cooldown_tracker.mark_failure(
                    candidate.provider_id, candidate.model, classified
                )
                raise classified

            # Pre-stream failure
            if classified.retryable_same_target and attempt < policy.max_same_target_retries:
                continue

            # Target exhausted or non-retryable
            policy.cooldown_tracker.mark_failure(
                candidate.provider_id, candidate.model, classified
            )
            if classified.fallbackable and not is_last_candidate:
                break  # Fall back to next candidate in chain
            else:
                raise classified

    if last_error:
        raise last_error

