from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.plugins.envelope import build_evidence_envelope
from smartmoney_cub_harness.plugins.lifecycle import (
    EffectScope,
    PluginInstance,
    PluginState,
    should_activate,
)
from smartmoney_cub_harness.plugins.manifest import (
    PluginManifest,
    parse_manifest,
    validate_manifest,
)
from smartmoney_cub_harness.plugins.profiles import Profile, get_profile
from smartmoney_cub_harness.plugins.registry import PluginRegistry, PluginStateStore
from smartmoney_cub_harness.plugins.services import (
    BaseConsumer,
    ServiceRegistry,
    ServiceProvider,
)
from smartmoney_cub_harness.plugins.types import (
    CapabilityName,
    PluginKind,
    ResultKind,
    TrustLevel,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

PLUGIN_ENTRY_POINT_GROUP = "smartmoney_cub.plugins"
MANIFEST_FILENAMES = ("plugin.json", "smartmoney-plugin.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class PluginPermissionError(RuntimeError):
    """Raised when a plugin needs a capability the active profile does not grant."""


class PluginExecutionError(RuntimeError):
    """Raised when a plugin fails and the failure must stay visible."""


@dataclass
class PluginHost:
    """Shared context handed to plugins, mirroring the DSH service context.

    Plugins receive a host rather than importing harness internals, so the core
    keeps ownership of persistence, validation, and safety enforcement.
    """

    profile_name: str
    allow_network: bool = False
    allow_external_llm: bool = False
    allow_credentials: bool = False
    workspace: Path | None = None
    services: ServiceRegistry = field(default_factory=ServiceRegistry)

    def gate(self, manifest: PluginManifest) -> list[str]:
        """Return blocking reasons for running this plugin under this profile."""
        blockers: list[str] = []
        if manifest.network_required and not self.allow_network:
            blockers.append("network_required_but_profile_disallows_network")
        if manifest.requires_credentials and not self.allow_credentials:
            blockers.append("credentials_required_but_profile_disallows_credentials")
        if (
            CapabilityName.LLM_PROVIDER in manifest.capabilities
            and not self.allow_external_llm
        ):
            blockers.append("llm_provider_requires_explicit_external_llm_opt_in")
        # Only the core trust level may run in-process; everything else is isolated.
        if manifest.trust_level != TrustLevel.CORE and manifest.kind != PluginKind.SUBPROCESS:
            if manifest.trust_level == TrustLevel.UNTRUSTED_EXTERNAL:
                blockers.append("untrusted_external_requires_subprocess_isolation")
        return blockers


@dataclass
class SubprocessProvider:
    """Report-only bridge that runs a third-party command in its own process."""

    capability: str
    plugin_id: str
    command: list[str]
    network_required: bool = False
    requires_credentials: bool = False
    isolated_process: bool = True
    precedence: int = 0
    timeout_seconds: int = 120

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(request, ensure_ascii=False)
        completed = subprocess.run(
            self.command,
            input=payload,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise PluginExecutionError(
                f"subprocess plugin {self.plugin_id} exited {completed.returncode}: "
                f"{(completed.stderr or '').strip()[:400]}"
            )
        try:
            parsed = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise PluginExecutionError(
                f"subprocess plugin {self.plugin_id} returned invalid JSON: {exc}"
            ) from exc
        if not isinstance(parsed, dict):
            raise PluginExecutionError(f"subprocess plugin {self.plugin_id} must return a JSON object")
        parsed.setdefault("safety", SAFETY_DECLARATION)
        parsed.setdefault("isolated_process", True)
        return parsed

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "capability": self.capability,
            "plugin_id": self.plugin_id,
            "isolation": "subprocess",
            "network_required": self.network_required,
            "enforcement": "declarative",
            "verified": False,
            "safety": SAFETY_DECLARATION,
        }


def discover_manifest_paths(plugin_dirs: list[str | Path]) -> list[Path]:
    """Find manifest files under explicit local plugin directories.

    A directory may itself be a plugin root (manifest at its top level) or a
    parent containing several plugin subdirectories.
    """
    found: list[Path] = []
    for directory in plugin_dirs:
        root = Path(directory).expanduser()
        if not root.exists():
            continue
        if root.is_file() and root.name in MANIFEST_FILENAMES:
            found.append(root)
            continue
        if root.is_dir():
            for filename in MANIFEST_FILENAMES:
                direct = root / filename
                if direct.is_file():
                    found.append(direct)
        for filename in MANIFEST_FILENAMES:
            found.extend(sorted(root.glob(f"*/{filename}")))
    # Preserve order while removing duplicates from overlapping inputs.
    unique: list[Path] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


def discover_installed_entry_points() -> list[dict[str, Any]]:
    """List installed plugins advertising the harness entry point group.

    Discovery only reports what exists; nothing is imported or executed here.
    """
    discovered: list[dict[str, Any]] = []
    try:
        entry_points = importlib_metadata.entry_points()
    except Exception:
        return discovered

    selected = (
        entry_points.select(group=PLUGIN_ENTRY_POINT_GROUP)
        if hasattr(entry_points, "select")
        else entry_points.get(PLUGIN_ENTRY_POINT_GROUP, [])
    )
    for entry_point in selected:
        discovered.append(
            {
                "name": entry_point.name,
                "value": entry_point.value,
                "group": PLUGIN_ENTRY_POINT_GROUP,
                "safety": SAFETY_DECLARATION,
            }
        )
    return discovered


@dataclass
class PluginRuntime:
    """Discovers, validates, gates, activates, and executes plugins."""

    profile: Profile = field(default_factory=lambda: get_profile("default-offline"))
    registry: PluginRegistry = field(default_factory=PluginRegistry)
    services: ServiceRegistry = field(default_factory=ServiceRegistry)
    state_store: PluginStateStore | None = None
    host: PluginHost | None = None
    effects: dict[str, EffectScope] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.host is None:
            self.host = PluginHost(
                profile_name=self.profile.name,
                allow_network=self.profile.allow_network,
                allow_external_llm=self.profile.allow_external_llm,
                allow_credentials=self.profile.allow_credentials,
                services=self.services,
            )

    # ---- composition -----------------------------------------------------

    def entry_tree(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.profile.resolve_entries()]

    def enabled_entry_ids(self) -> set[str]:
        return {entry.id for entry in self.profile.resolve_entries() if entry.enabled}

    # ---- discovery and validation ---------------------------------------

    def load_manifest(self, payload: Any) -> PluginManifest:
        result = validate_manifest(payload)
        if not result["ok"]:
            plugin_id = str(payload.get("plugin_id")) if isinstance(payload, dict) else "unknown"
            self.registry.reject(plugin_id=plugin_id, reason="manifest_invalid", errors=result["errors"])
            raise ValueError("; ".join(result["errors"]))
        return parse_manifest(payload)

    def discover(self, plugin_dirs: list[str | Path] | None = None) -> dict[str, Any]:
        """Inspect local manifests and record their lifecycle state."""
        # First rebuild what a previous invocation already installed, so state,
        # provenance, and audit history survive across separate CLI runs.
        self.hydrate()
        discovered: list[dict[str, Any]] = []
        for manifest_path in discover_manifest_paths(plugin_dirs or []):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self.registry.reject(
                    plugin_id=str(manifest_path.parent.name),
                    reason="manifest_unreadable",
                    errors=[str(exc)],
                )
                continue

            validation = validate_manifest(payload)
            if not validation["ok"]:
                self.registry.reject(
                    plugin_id=str(payload.get("plugin_id") or manifest_path.parent.name),
                    reason="manifest_invalid",
                    errors=validation["errors"],
                )
                continue

            manifest = parse_manifest(payload)
            instance = self.registry.get(manifest.plugin_id) or PluginInstance(
                plugin_id=manifest.plugin_id,
                version=manifest.version,
            )
            existing_source = str((instance.manifest or {}).get("installed_from") or "")
            if existing_source and existing_source != str(manifest_path):
                # A duplicate id would let one plugin shadow another's evidence.
                self.registry.reject(
                    plugin_id=manifest.plugin_id,
                    reason="duplicate_plugin_id",
                    errors=[f"already discovered at another location: {manifest_path}"],
                )
                continue

            instance.manifest = {**manifest.to_dict(), "installed_from": str(manifest_path)}
            instance.capabilities = list(manifest.capabilities)
            instance.required_services = list(manifest.required_services)
            instance.optional_services = list(manifest.optional_services)
            instance.isolation = (
                "subprocess" if manifest.kind == PluginKind.SUBPROCESS else "in-process"
            )
            # Hydrate the prior lifecycle state so the audit trail reads correctly
            # across separate CLI invocations.
            prior = self.state_store.get(manifest.plugin_id) if self.state_store else None
            if prior and prior.get("state") in PluginState.ALL:
                instance.state = str(prior["state"])
            else:
                instance.transition(PluginState.DISCOVERED)
            self._persist(instance)
            self.registry.add(instance)
            discovered.append(instance.status())

        return {
            "discovered": discovered,
            "rejected": list(self.registry.rejected),
            "entry_points": discover_installed_entry_points(),
            "safety": SAFETY_DECLARATION,
        }

    def hydrate(self) -> list[PluginInstance]:
        """Rebuild plugin instances from persisted state, keeping provenance."""
        if self.state_store is None:
            return []
        hydrated: list[PluginInstance] = []
        for record in self.state_store.list_all():
            manifest = record.get("manifest") or {}
            instance = PluginInstance(
                plugin_id=str(record["plugin_id"]),
                version=str(record.get("version") or "unknown"),
                manifest=manifest,
                capabilities=list(record.get("capabilities") or []),
                required_services=list(manifest.get("required_services") or []),
                optional_services=list(manifest.get("optional_services") or []),
                isolation="subprocess" if manifest.get("kind") == PluginKind.SUBPROCESS else "in-process",
                state=str(record.get("state") or PluginState.DISCOVERED),
                last_error=record.get("last_error"),
            )
            self.registry.add(instance)
            hydrated.append(instance)
        return hydrated

    # ---- activation ------------------------------------------------------

    def register_provider(self, plugin_id: str, provider: ServiceProvider) -> None:
        self.services.register_provider(provider, plugin_id=plugin_id)

    def activate(self, plugin_id: str, *, enabled: bool = True) -> PluginInstance:
        """Resolve dependencies and gate a plugin into ACTIVE, PENDING, or BLOCKED."""
        instance = self.registry.get(plugin_id)
        if instance is None:
            raise KeyError(f"unknown plugin: {plugin_id}")
        if instance.manifest is None:
            raise ValueError(f"plugin {plugin_id} has no manifest")

        manifest = parse_manifest(instance.manifest)
        instance.transition(PluginState.INSPECTED)

        blockers = list(self.host.gate(manifest)) if self.host else []
        missing = [
            capability
            for capability in manifest.required_services
            if self.services.resolve(capability) is None
        ]
        instance.missing_services = missing
        instance.blockers = blockers

        should, state = should_activate(
            enabled=enabled, missing_services=missing, blockers=blockers
        )
        previous = instance.state
        instance.transition(state)
        instance.generation += 1
        if should:
            self._register_declared_providers(instance, manifest)
            instance.health = self._health(instance)
            if instance.health.get("status") != "ok":
                instance.transition(PluginState.FAILED)
                instance.last_error = str(instance.health.get("error") or "health_check_failed")

        self._persist(instance, from_state=previous, detail=f"activate:{state}")
        return instance

    def _register_declared_providers(self, instance: PluginInstance, manifest: PluginManifest) -> None:
        """Register providers for the capabilities a manifest declares.

        Registration is recorded as a reversible effect so deactivation removes the
        provider and no consumer keeps a stale reference.
        """
        scope = self.effects.setdefault(instance.plugin_id, EffectScope())

        if manifest.kind == PluginKind.ENTRY_POINT:
            self._register_entry_point_providers(instance, manifest, scope)
            return

        if manifest.kind != PluginKind.SUBPROCESS:
            return

        entrypoint = manifest.entrypoint
        if isinstance(entrypoint, str):
            command = entrypoint.split()
        elif isinstance(entrypoint, list):
            command = [str(part) for part in entrypoint]
        else:
            return

        for capability in manifest.capabilities:
            # Capabilities the plugin consumes rather than provides are not registered.
            if capability in manifest.required_services:
                continue
            existing = self.services.resolve(capability)
            if existing is not None and getattr(existing, "plugin_id", None) == instance.plugin_id:
                continue
            provider = SubprocessProvider(
                capability=capability,
                plugin_id=instance.plugin_id,
                command=command,
                network_required=manifest.network_required,
                requires_credentials=manifest.requires_credentials,
            )
            self.services.register_provider(provider, plugin_id=instance.plugin_id)
            scope.add(f"provider:{capability}", lambda p=provider: self.services.unregister_provider(p))

    def _register_entry_point_providers(
        self, instance: PluginInstance, manifest: PluginManifest, scope: EffectScope
    ) -> None:
        """Load an installed entry point and register the providers it returns.

        In-process loading is restricted to the core and review-only trust levels.
        Untrusted code is blocked earlier by the profile gate, so it never reaches
        this path in process.
        """
        spec = manifest.entrypoint
        if not isinstance(spec, str) or ":" not in spec:
            instance.last_error = "entry-point plugin requires an entrypoint like 'module:attribute'"
            return

        try:
            from importlib.metadata import EntryPoint

            target = EntryPoint(name=manifest.plugin_id, value=spec, group=PLUGIN_ENTRY_POINT_GROUP).load()
            produced = target() if callable(target) else target
        except Exception as exc:
            instance.last_error = f"{type(exc).__name__}: {exc}"
            return

        providers = produced if isinstance(produced, (list, tuple)) else [produced]
        for provider in providers:
            capability = str(getattr(provider, "capability", "") or "")
            if not capability:
                continue
            if capability not in manifest.capabilities:
                # A provider must not smuggle in a capability the manifest never declared.
                instance.last_error = f"provider declared undeclared capability: {capability}"
                continue
            if not getattr(provider, "plugin_id", ""):
                try:
                    provider.plugin_id = instance.plugin_id
                except Exception:
                    continue
            self.services.register_provider(provider, plugin_id=instance.plugin_id)
            scope.add(
                f"provider:{capability}",
                lambda p=provider: self.services.unregister_provider(p),
            )

    def _health(self, instance: PluginInstance) -> dict[str, Any]:
        provider = None
        for capability in instance.capabilities:
            candidate = self.services.resolve(capability)
            if candidate is not None:
                provider = candidate
                break
        if provider is None:
            return {
                "status": "ok",
                "plugin_id": instance.plugin_id,
                "note": "no provider registered; entry is a slot",
                "enforcement": "declarative",
                "verified": False,
                "safety": SAFETY_DECLARATION,
            }
        try:
            result = dict(provider.health_check())
        except Exception as exc:
            return {
                "status": "error",
                "plugin_id": instance.plugin_id,
                "error": str(exc),
                "safety": SAFETY_DECLARATION,
            }
        result.setdefault("safety", SAFETY_DECLARATION)
        return result

    def deactivate(self, plugin_id: str, *, state: str = PluginState.DISABLED) -> PluginInstance:
        """Unload a plugin and roll back every effect it registered."""
        instance = self.registry.get(plugin_id)
        if instance is None:
            raise KeyError(f"unknown plugin: {plugin_id}")
        previous = instance.state
        instance.transition(PluginState.UNLOADING)
        scope = self.effects.pop(plugin_id, None)
        if scope is not None:
            errors = scope.dispose()
            if errors:
                instance.last_error = json.dumps(errors, ensure_ascii=False)

        provider = None
        for capability in instance.capabilities:
            candidate = self.services.resolve(capability)
            if candidate is not None and getattr(candidate, "plugin_id", None) == plugin_id:
                provider = candidate
                break
        if provider is not None:
            self.services.unregister_provider(provider)

        instance.health = None
        instance.missing_services = []
        instance.transition(state)
        self._persist(instance, from_state=previous, detail=f"deactivate:{state}")
        return instance

    def inject(self, consumer: BaseConsumer) -> dict[str, Any]:
        return self.services.inject(consumer)

    # ---- execution -------------------------------------------------------

    def execute(
        self,
        *,
        plugin_id: str,
        capability: str,
        request: dict[str, Any],
        decision_time: str | None,
        available_at: str,
        data_source: str = "",
        data_quality: str = "ok",
        result_kind: str = ResultKind.REVIEW_OBSERVATION,
    ) -> dict[str, Any]:
        """Run one capability and always return a wrapped evidence envelope."""
        instance = self.registry.get(plugin_id)
        if instance is None:
            raise KeyError(f"unknown plugin: {plugin_id}")
        if not instance.is_serving:
            raise PluginPermissionError(
                f"plugin {plugin_id} is {instance.state} and cannot serve {capability}"
            )

        manifest = parse_manifest(instance.manifest or {})
        blockers = list(self.host.gate(manifest)) if self.host else []
        if blockers:
            raise PluginPermissionError("; ".join(blockers))

        provider = self.services.resolve(capability)
        if provider is None:
            raise PermissionError(f"no provider registered for capability {capability}")
        if str(getattr(provider, "plugin_id", "")) != plugin_id:
            raise PluginExecutionError(
                f"capability {capability} is served by {getattr(provider, 'plugin_id', 'unknown')}, "
                f"not {plugin_id}"
            )

        started = _now_iso()
        error: str | None = None
        output: Any = None
        try:
            output = provider.invoke(dict(request))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finished = _now_iso()

        envelope = build_evidence_envelope(
            plugin_id=plugin_id,
            plugin_version=instance.version,
            source_ref=str(
                (instance.manifest or {}).get("source_commit")
                or (instance.manifest or {}).get("source_tag")
                or (instance.manifest or {}).get("source_repo")
                or "unknown"
            ),
            capability=capability,
            result_kind=result_kind,
            request=request,
            output=output,
            decision_time=decision_time,
            available_at=available_at,
            data_source=data_source or manifest.name,
            data_quality=data_quality,
            network_used=bool(getattr(provider, "network_required", False)),
            model_used=bool(CapabilityName.LLM_PROVIDER in manifest.capabilities),
            permission={
                "order": False,
                "cancel": False,
                "trade": False,
                "account_mutation": False,
                "broker_access": False,
                "network": bool(getattr(provider, "network_required", False)),
                "enforcement": "declarative",
                "verified": False,
            },
            error=error,
            replay={"command": "smcub plugin run", "capability": capability},
            started_at=started,
            finished_at=finished,
            extra={"isolation": instance.isolation},
        )

        previous = instance.state
        instance.transition(PluginState.EXECUTED if error is None else PluginState.FAILED)
        instance.last_error = error
        self._persist(instance, from_state=previous, detail=f"execute:{capability}")
        return envelope

    # ---- introspection ---------------------------------------------------

    def doctor(self) -> dict[str, Any]:
        catalog = self.services.catalog()
        return {
            "status": "ok",
            "profile": self.profile.name,
            "allow_network": self.profile.allow_network,
            "allow_external_llm": self.profile.allow_external_llm,
            "allow_credentials": self.profile.allow_credentials,
            "entry_tree": self.entry_tree(),
            "plugins": self.registry.list_all(),
            "rejected": list(self.registry.rejected),
            "capabilities": catalog["capabilities"],
            "conflicts": catalog["conflicts"],
            "permission_enforcement": "declarative",
            "sandbox_verified": False,
            "safety": SAFETY_DECLARATION,
        }

    def _persist(self, instance: PluginInstance, *, from_state: str | None = None, detail: str = "") -> None:
        if self.state_store is None:
            return
        self.state_store.record(instance, from_state=from_state, detail=detail)
