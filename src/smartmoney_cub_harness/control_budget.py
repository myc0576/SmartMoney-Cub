"""Explicit paid-provider budget guard with dependency injection."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from contextlib import contextmanager
from contextvars import ContextVar
import json
from typing import Any, Callable, Mapping


class BudgetError(RuntimeError):
    """A provider call cannot proceed under the configured budget."""


class UnknownModelCost(BudgetError):
    """The requested model has no validated user-provided price."""


class BudgetExceeded(BudgetError):
    """A call would exceed the USD or call-count cap."""


_ACTIVE_BUDGET: ContextVar["BudgetGuard | None"] = ContextVar("smc_paid_budget", default=None)
_BRIDGE_BUDGET_REQUIRED: ContextVar[bool] = ContextVar("smc_bridge_budget_required", default=False)


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite non-negative decimal") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{label} must be a finite non-negative decimal")
    return result.quantize(Decimal("0.00000001"))


@dataclass(frozen=True)
class ModelPricing:
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal

    @classmethod
    def from_values(cls, input_usd_per_million: Any, output_usd_per_million: Any) -> "ModelPricing":
        return cls(_decimal(input_usd_per_million, "input pricing"), _decimal(output_usd_per_million, "output pricing"))


def validate_pricing(pricing: Mapping[str, Any]) -> dict[str, ModelPricing]:
    if not isinstance(pricing, Mapping) or not pricing:
        raise ValueError("pricing must be a non-empty model mapping")
    result: dict[str, ModelPricing] = {}
    for model, value in pricing.items():
        if not isinstance(model, str) or not model.strip():
            raise ValueError("pricing model names must be non-empty strings")
        if isinstance(value, ModelPricing):
            result[model] = value
        elif isinstance(value, Mapping):
            result[model] = ModelPricing.from_values(value.get("input_usd_per_million"), value.get("output_usd_per_million"))
        else:
            raise ValueError(f"pricing for {model!r} is invalid")
    return result


@dataclass
class BudgetGuard:
    cap_usd: Decimal
    pricing: dict[str, ModelPricing]
    max_calls: int = 1
    calls: int = 0
    reserved_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        self.cap_usd = _decimal(self.cap_usd, "USD cap")
        if type(self.max_calls) is not int or self.max_calls < 1:
            raise ValueError("max_calls must be a positive integer")
        self.pricing = validate_pricing(self.pricing)
        self.reserved_usd = _decimal(self.reserved_usd, "reserved USD")
        if self.reserved_usd > self.cap_usd:
            raise ValueError("reserved USD exceeds cap")

    def reserve(self, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        if model not in self.pricing:
            raise UnknownModelCost(f"no validated cost for model {model!r}")
        if type(input_tokens) is not int or input_tokens < 0:
            raise ValueError("input_tokens must be a non-negative integer")
        if type(output_tokens) is not int or output_tokens < 0:
            raise ValueError("output_tokens must be a non-negative integer")
        if self.calls >= self.max_calls:
            raise BudgetExceeded("maximum provider calls reached")
        price = self.pricing[model]
        cost = ((Decimal(input_tokens) * price.input_usd_per_million) + (Decimal(output_tokens) * price.output_usd_per_million)) / Decimal(1_000_000)
        cost = cost.quantize(Decimal("0.00000001"))
        if self.reserved_usd + cost > self.cap_usd:
            raise BudgetExceeded("provider call would exceed the USD cap")
        self.reserved_usd += cost
        self.calls += 1
        return cost

    def call_provider(self, provider_call: Callable[..., Any], *, model: str, input_tokens: int, output_tokens: int, **kwargs: Any) -> Any:
        """Reserve, then invoke the injected provider exactly once."""
        self.reserve(model, input_tokens, output_tokens)
        return provider_call(model=model, **kwargs)

    def reserve_request(self, model: str, request_body: bytes, *, max_tokens: int) -> Decimal:
        """Reserve a conservative request estimate before transport.

        Input is charged by UTF-8 bytes and output by the declared request
        limit. This intentionally overestimates input tokens and fails closed
        when the request body cannot be decoded as JSON.
        """
        if type(max_tokens) is not int or max_tokens < 0:
            raise ValueError("max_tokens must be a non-negative integer")
        try:
            json.loads(request_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BudgetError("cannot conservatively inspect provider request") from exc
        return self.reserve(model, len(request_body), max_tokens)


@contextmanager
def paid_budget(guard: BudgetGuard):
    """Activate an opt-in budget for provider transports in this context."""
    if not isinstance(guard, BudgetGuard):
        raise TypeError("paid_budget requires a BudgetGuard")
    token = _ACTIVE_BUDGET.set(guard)
    try:
        yield guard
    finally:
        _ACTIVE_BUDGET.reset(token)


@contextmanager
def require_paid_budget():
    """Deny outbound provider transport unless an accountable budget is active."""
    token = _BRIDGE_BUDGET_REQUIRED.set(True)
    try:
        yield
    finally:
        _BRIDGE_BUDGET_REQUIRED.reset(token)


def reserve_provider_request(model: str, request_body: bytes, *, max_tokens: int) -> Decimal | None:
    """Reserve an active paid request; deny unsupported bridge calls."""
    guard = _ACTIVE_BUDGET.get()
    if guard is None:
        if _BRIDGE_BUDGET_REQUIRED.get():
            raise BudgetError("provider transport requires an accountable paid budget")
        return None
    return guard.reserve_request(model, request_body, max_tokens=max_tokens)


def default_deny_budget() -> BudgetGuard:
    """Zero-cap guard used by callers that must fail closed without pricing."""
    return BudgetGuard(Decimal("0"), {"__unpriced__": {"input_usd_per_million": 1, "output_usd_per_million": 1}}, max_calls=1)


__all__ = ["BudgetError", "BudgetExceeded", "BudgetGuard", "ModelPricing", "UnknownModelCost", "default_deny_budget", "paid_budget", "require_paid_budget", "reserve_provider_request", "validate_pricing"]
