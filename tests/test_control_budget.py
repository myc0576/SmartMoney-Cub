from __future__ import annotations

from decimal import Decimal

import pytest

from smartmoney_cub_harness.control_budget import BudgetError, BudgetExceeded, BudgetGuard, UnknownModelCost, default_deny_budget, paid_budget, require_paid_budget
from smartmoney_cub_harness.agent import providers
from smartmoney_cub_harness.agent.route_chain import RouteCandidate, RouteChainPolicy, stream_chat_with_route_chain
from smartmoney_cub_harness.agent.provider_errors import ClassifiedProviderError, FailurePhase, ProviderErrorCode


def test_budget_reserves_before_injected_provider_and_bounds_calls() -> None:
    calls: list[dict[str, object]] = []
    guard = BudgetGuard(
        Decimal("0.01"),
        {"toy-model": {"input_usd_per_million": "1", "output_usd_per_million": "2"}},
        max_calls=1,
    )

    def provider_call(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"ok": True}

    assert guard.call_provider(provider_call, model="toy-model", input_tokens=1000, output_tokens=1000) == {"ok": True}
    assert guard.calls == 1
    assert calls == [{"model": "toy-model"}]
    with pytest.raises(BudgetExceeded):
        guard.call_provider(provider_call, model="toy-model", input_tokens=1, output_tokens=1)
    assert len(calls) == 1


def test_budget_rejects_unknown_cost_before_provider() -> None:
    calls: list[object] = []
    guard = BudgetGuard(Decimal("1"), {"known": {"input_usd_per_million": 1, "output_usd_per_million": 1}})
    with pytest.raises(UnknownModelCost):
        guard.call_provider(lambda **kwargs: calls.append(kwargs), model="unknown", input_tokens=1, output_tokens=1)
    assert calls == []


def test_paid_budget_hooks_real_provider_transport_and_is_context_local(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[object] = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n'
            yield b'data: [DONE]\n'

    monkeypatch.setattr(providers.urllib.request, "urlopen", lambda request, timeout: sent.append(request) or Response())
    guard = BudgetGuard(Decimal("0.01"), {"toy-model": {"input_usd_per_million": "1", "output_usd_per_million": "1"}}, max_calls=1)
    provider = {"base_url": "http://127.0.0.1:9/v1", "protocol": "openai-chat", "api_key": ""}
    with paid_budget(guard):
        assert list(providers.stream_chat(provider, model="toy-model", messages=[{"role": "user", "content": "hi"}]))[-1]["kind"] == "done"
    assert len(sent) == 1
    assert guard.calls == 1
    list(providers.stream_chat(provider, model="toy-model", messages=[{"role": "user", "content": "legacy"}]))
    assert len(sent) == 2


def test_paid_budget_counts_each_transport_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    def fail(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise OSError("toy transport")
    monkeypatch.setattr(providers.urllib.request, "urlopen", fail)
    guard = BudgetGuard(Decimal("0.01"), {"toy-model": {"input_usd_per_million": "1", "output_usd_per_million": "1"}}, max_calls=1)
    provider = {"base_url": "http://127.0.0.1:9/v1", "protocol": "openai-chat", "api_key": ""}
    with paid_budget(guard):
        with pytest.raises(Exception):
            list(providers.stream_chat(provider, model="toy-model", messages=[{"role": "user", "content": "retry"}]))
    assert attempts == 1
    assert guard.calls == 1


def test_paid_budget_stops_route_retry_before_second_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fail(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise OSError("toy transport")

    monkeypatch.setattr(providers.urllib.request, "urlopen", fail)
    guard = BudgetGuard(Decimal("0.01"), {"toy-model": {"input_usd_per_million": "1", "output_usd_per_million": "1"}}, max_calls=1)
    candidate = RouteCandidate("toy", "toy-model", base_url="http://127.0.0.1:9/v1", api_key="")
    with paid_budget(guard):
        with pytest.raises(Exception):
            list(stream_chat_with_route_chain(
                [candidate],
                [{"role": "user", "content": "retry"}],
                policy=RouteChainPolicy(max_same_target_retries=1, initial_backoff_seconds=0),
            ))
    assert attempts == 1
    assert guard.calls == 1


def test_external_bridge_without_accountable_budget_denies_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fail(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise AssertionError("transport must not be reached")

    monkeypatch.setattr(providers.urllib.request, "urlopen", fail)
    provider = {"base_url": "http://127.0.0.1:9/v1", "protocol": "openai-chat", "api_key": ""}
    with require_paid_budget():
        with pytest.raises(ClassifiedProviderError, match="accountable paid budget"):
            list(providers.stream_chat(provider, model="toy-model", messages=[{"role": "user", "content": "bridge"}]))
    assert attempts == 0


def test_default_deny_budget_rejects_unpriced_model_before_transport() -> None:
    guard = default_deny_budget()
    with pytest.raises(UnknownModelCost):
        guard.reserve("toy-model", 1, 1)


def test_paid_budget_context_is_nested_and_restores() -> None:
    outer = BudgetGuard(Decimal("1"), {"toy-model": {"input_usd_per_million": 1, "output_usd_per_million": 1}})
    inner = BudgetGuard(Decimal("1"), {"toy-model": {"input_usd_per_million": 1, "output_usd_per_million": 1}})
    with paid_budget(outer):
        with paid_budget(inner):
            inner.reserve("toy-model", 1, 1)
        outer.reserve("toy-model", 1, 1)
    assert inner.calls == 1
    assert outer.calls == 1
