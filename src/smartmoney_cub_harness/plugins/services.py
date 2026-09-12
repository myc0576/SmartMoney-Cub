from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from smartmoney_cub_harness.plugins.types import CapabilityName, SUPPORTED_API_RANGE
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


class MissingDependencyError(RuntimeError):
    """Raised when a consumer cannot be wired because services are unavailable."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        super().__init__("missing required services: " + ", ".join(self.missing))


class CapabilityConflictError(RuntimeError):
    """Raised when two providers claim the same capability with equal precedence."""


@dataclass(frozen=True)
class ServiceDefinition:
    """Stable request/result contract for one capability.

    Definitions carry no reference to any concrete provider or external project,
    so providers and consumers can be replaced independently.
    """

    name: str
    api_version: str = SUPPORTED_API_RANGE
    description: str = ""
    request_schema: dict[str, Any] | None = None
    result_schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "api_version": self.api_version,
            "description": self.description,
            "request_schema": self.request_schema,
            "result_schema": self.result_schema,
            "safety": SAFETY_DECLARATION,
        }


def _definition(name: str, description: str) -> ServiceDefinition:
    return ServiceDefinition(name=name, description=description)


SERVICE_DEFINITIONS: dict[str, ServiceDefinition] = {
    CapabilityName.TRADE_IMPORT: _definition(
        CapabilityName.TRADE_IMPORT,
        "Normalize broker or 同花顺 fills into a reviewable position ledger.",
    ),
    CapabilityName.MARKET_CONTEXT: _definition(
        CapabilityName.MARKET_CONTEXT,
        "Provide read-only market context such as regime or sentiment observations.",
    ),
    CapabilityName.REVIEWER: _definition(
        CapabilityName.REVIEWER,
        "Produce review observations for a decision or round trip.",
    ),
    CapabilityName.CHALLENGER: _definition(
        CapabilityName.CHALLENGER,
        "Produce counter-arguments and rule candidates; never mutates champion rules.",
    ),
    CapabilityName.EVALUATOR: _definition(
        CapabilityName.EVALUATOR,
        "Evaluate a rule candidate against point-in-time samples.",
    ),
    CapabilityName.REPLAY: _definition(
        CapabilityName.REPLAY,
        "Reconstruct a frozen decision context deterministically.",
    ),
    CapabilityName.REPORT_RENDERER: _definition(
        CapabilityName.REPORT_RENDERER,
        "Render local review artifacts; must not upload anything.",
    ),
    CapabilityName.MEMORY: _definition(
        CapabilityName.MEMORY,
        "Store and retrieve portable text memory.",
    ),
    CapabilityName.LLM_PROVIDER: _definition(
        CapabilityName.LLM_PROVIDER,
        "Optional external model access; disabled unless the user explicitly enables it.",
    ),
    CapabilityName.AGENT_BRIDGE: _definition(
        CapabilityName.AGENT_BRIDGE,
        "Bridge a local external agent whose output becomes review evidence only.",
    ),
}


@runtime_checkable
class ServiceProvider(Protocol):
    """A concrete implementation of exactly one capability."""

    capability: str
    plugin_id: str

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]: ...

    def health_check(self) -> dict[str, Any]: ...


class BaseProvider:
    """Convenience base class for first-party and third-party providers."""

    capability: str = ""
    plugin_id: str = ""
    # Higher precedence wins when two providers declare the same capability.
    precedence: int = 0
    # Declared, unverified capabilities. This is not a sandbox attestation.
    network_required: bool = False
    requires_credentials: bool = False
    isolated_process: bool = False

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "capability": self.capability,
            "plugin_id": self.plugin_id,
            "network_required": self.network_required,
            "enforcement": "declarative",
            "verified": False,
            "safety": SAFETY_DECLARATION,
        }


class ServiceConsumer:
    """A component that consumes capabilities instead of importing providers."""

    # Hard dependencies: absence moves the consumer into PENDING.
    required_services: tuple[str, ...] = ()
    # Soft dependencies: absence is recorded but does not block activation.
    optional_services: tuple[str, ...] = ()

    def __init__(self) -> None:
        self._services: dict[str, Callable[..., dict[str, Any]]] = {}
        self.missing_optional: list[str] = []

    @property
    def consumer_id(self) -> str:
        return type(self).__name__

    def bind(self, services: dict[str, Callable[..., dict[str, Any]]]) -> None:
        self._services = dict(services)

    def call(self, capability: str, request: dict[str, Any]) -> dict[str, Any]:
        handler = self._services.get(capability)
        if handler is None:
            raise MissingDependencyError([capability])
        return handler(request)

    def has(self, capability: str) -> bool:
        return capability in self._services


# Backwards-friendly alias so call sites can read either name.
BaseConsumer = ServiceConsumer


@dataclass
class _Registration:
    provider: ServiceProvider
    precedence: int
    plugin_id: str


@dataclass
class ServiceRegistry:
    """Resolves capability names to providers and wires consumers via inject."""

    definitions: dict[str, ServiceDefinition] = field(default_factory=dict)
    _providers: dict[str, list[_Registration]] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.definitions:
            self.definitions = dict(SERVICE_DEFINITIONS)

    def define(self, definition: ServiceDefinition) -> None:
        self.definitions[definition.name] = definition

    def register_provider(self, provider: ServiceProvider, *, plugin_id: str | None = None) -> None:
        capability = str(getattr(provider, "capability", "") or "")
        if not capability:
            raise ValueError("provider must declare a capability")
        owner = str(plugin_id or getattr(provider, "plugin_id", "") or "unknown")
        precedence = int(getattr(provider, "precedence", 0) or 0)
        self._providers.setdefault(capability, []).append(
            _Registration(provider=provider, precedence=precedence, plugin_id=owner)
        )
        self._providers[capability].sort(key=lambda item: item.precedence, reverse=True)
        if len(self._providers[capability]) > 1:
            top = self._providers[capability][0].precedence
            tied = [item for item in self._providers[capability] if item.precedence == top]
            if len(tied) > 1:
                self.conflicts.append(
                    {
                        "capability": capability,
                        "precedence": top,
                        "plugin_ids": sorted(item.plugin_id for item in tied),
                    }
                )

    def unregister_provider(self, provider: ServiceProvider) -> None:
        capability = str(getattr(provider, "capability", ""))
        remaining = [
            item for item in self._providers.get(capability, []) if item.provider is not provider
        ]
        if remaining:
            self._providers[capability] = remaining
        else:
            self._providers.pop(capability, None)

    def available_capabilities(self) -> list[str]:
        return sorted(self._providers)

    def resolve(self, capability: str) -> ServiceProvider | None:
        registrations = self._providers.get(capability) or []
        return registrations[0].provider if registrations else None

    def provider_identity(self, capability: str) -> dict[str, Any] | None:
        registrations = self._providers.get(capability) or []
        if not registrations:
            return None
        top = registrations[0]
        return {
            "capability": capability,
            "plugin_id": top.plugin_id,
            "precedence": top.precedence,
            "network_required": bool(getattr(top.provider, "network_required", False)),
            "requires_credentials": bool(getattr(top.provider, "requires_credentials", False)),
            "isolated_process": bool(getattr(top.provider, "isolated_process", False)),
            "enforcement": "declarative",
            "verified": False,
        }

    def inject(self, consumer: BaseConsumer) -> dict[str, Any]:
        """Wire a consumer; raise when a hard dependency is unavailable."""
        bound: dict[str, Callable[..., dict[str, Any]]] = {}
        missing: list[str] = []
        for capability in consumer.required_services:
            provider = self.resolve(capability)
            if provider is None:
                missing.append(capability)
                continue
            bound[capability] = provider.invoke
        if missing:
            raise MissingDependencyError(missing)

        optional_missing: list[str] = []
        for capability in consumer.optional_services:
            provider = self.resolve(capability)
            if provider is None:
                optional_missing.append(capability)
                continue
            bound[capability] = provider.invoke

        consumer.bind(bound)
        consumer.missing_optional = optional_missing
        return {
            "consumer": consumer.consumer_id,
            "bound": sorted(bound),
            "missing_optional": sorted(optional_missing),
            "safety": SAFETY_DECLARATION,
        }

    def catalog(self) -> dict[str, Any]:
        """Generate the capability catalog used by CLI, dashboard, and docs."""
        entries: list[dict[str, Any]] = []
        for name in sorted(self.definitions):
            definition = self.definitions[name]
            identity = self.provider_identity(name)
            entries.append(
                {
                    "capability": name,
                    "description": definition.description,
                    "api_version": definition.api_version,
                    "status": "available" if identity else "unavailable",
                    "provider": identity,
                }
            )
        return {
            "capabilities": entries,
            "available_count": sum(1 for entry in entries if entry["status"] == "available"),
            "conflicts": list(self.conflicts),
            "safety": SAFETY_DECLARATION,
        }
