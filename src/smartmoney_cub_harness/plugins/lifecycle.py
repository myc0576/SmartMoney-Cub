from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

Disposer = Callable[[], None]


class PluginState:
    """Plugin lifecycle states mirroring the DSH model."""

    DISCOVERED = "DISCOVERED"
    INSPECTED = "INSPECTED"
    INSTALLED = "INSTALLED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    PENDING = "PENDING"
    LOADING = "LOADING"
    ACTIVE = "ACTIVE"
    UNLOADING = "UNLOADING"
    DISPOSED = "DISPOSED"
    EXECUTED = "EXECUTED"
    EVIDENCE_WRAPPED = "EVIDENCE_WRAPPED"
    REVIEWED = "REVIEWED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    DEPRECATED = "DEPRECATED"
    REVOKED = "REVOKED"

    ALL = (
        DISCOVERED,
        INSPECTED,
        INSTALLED,
        ENABLED,
        DISABLED,
        PENDING,
        LOADING,
        ACTIVE,
        UNLOADING,
        DISPOSED,
        EXECUTED,
        EVIDENCE_WRAPPED,
        REVIEWED,
        FAILED,
        BLOCKED,
        DEPRECATED,
        REVOKED,
    )

    # States in which a plugin may serve capabilities.
    SERVING = (ACTIVE, EXECUTED, EVIDENCE_WRAPPED, REVIEWED)


class EffectScope:
    """Records registrations and resources so they can be rolled back.

    Every mutation a plugin performs during activation must go through here.
    Unloading runs disposers in reverse order so partial failures stay contained.
    """

    def __init__(self) -> None:
        self._disposers: list[tuple[str, Disposer]] = []
        self._disposed = False

    def add(self, label: str, disposer: Disposer) -> None:
        self._disposers.append((label, disposer))

    def wrap(self, label: str, target: Any, attribute: str) -> None:
        """Register a disposer that clears a previously bound reference."""
        self.add(label, lambda: setattr(target, attribute, None))

    @property
    def labels(self) -> list[str]:
        return [label for label, _ in self._disposers]

    @property
    def disposed(self) -> bool:
        return self._disposed

    def dispose(self) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        for label, disposer in reversed(self._disposers):
            try:
                disposer()
            except Exception as exc:  # a failing disposer must not mask others
                errors.append({"effect": label, "error": str(exc)})
        self._disposers.clear()
        self._disposed = True
        return errors


@dataclass
class PluginInstance:
    """A loaded plugin plus the reversible effects it created."""

    plugin_id: str
    version: str
    state: str = PluginState.DISCOVERED
    manifest: dict[str, Any] | None = None
    capabilities: list[str] = field(default_factory=list)
    required_services: list[str] = field(default_factory=list)
    optional_services: list[str] = field(default_factory=list)
    missing_services: list[str] = field(default_factory=list)
    isolation: str = "in-process"
    blockers: list[str] = field(default_factory=list)
    health: dict[str, Any] | None = None
    last_error: str | None = None
    generation: int = 0

    def transition(self, state: str) -> None:
        if state not in PluginState.ALL:
            raise ValueError(f"unknown plugin state: {state}")
        self.state = state

    @property
    def is_serving(self) -> bool:
        return self.state in PluginState.SERVING

    def status(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "version": self.version,
            "state": self.state,
            "capabilities": list(self.capabilities),
            "required_services": list(self.required_services),
            "optional_services": list(self.optional_services),
            "missing_services": list(self.missing_services),
            "isolation": self.isolation,
            "blockers": list(self.blockers),
            "health": self.health,
            "last_error": self.last_error,
            "generation": self.generation,
            "safety": SAFETY_DECLARATION,
        }


def should_activate(
    *,
    enabled: bool,
    missing_services: list[str],
    blockers: list[str],
) -> tuple[bool, str]:
    """Decide the next state for a plugin after dependency resolution.

    Separated from loading so the policy is directly testable.
    """
    if blockers:
        return False, PluginState.BLOCKED
    if missing_services:
        return False, PluginState.PENDING
    if not enabled:
        return False, PluginState.DISABLED
    return True, PluginState.ACTIVE
