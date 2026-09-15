from __future__ import annotations

import json
from pathlib import Path

from smartmoney_cub_harness.plugins import PluginRuntime, PluginState, PluginStateStore
from smartmoney_cub_harness.plugins.lifecycle import EffectScope
from smartmoney_cub_harness.plugins.profiles import get_profile
from smartmoney_cub_harness.plugins.services import BaseProvider
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


class _StubProvider(BaseProvider):
    capability = "reviewer"
    plugin_id = "demo.entrypoint"

    def invoke(self, request: dict) -> dict:
        return {"observations": [], "source": "entry-point"}


def _manifest(entrypoint: str) -> dict:
    return {
        "schema": "smartmoney_cub_plugin_manifest.v1",
        "plugin_id": "demo.entrypoint",
        "name": "Entry Point Reviewer",
        "version": "0.1.0",
        "source_repo": "https://example.com/demo",
        "source_commit": "abc123",
        "license": "MIT",
        "kind": "entry-point",
        "trust_level": "review-only",
        "api_range": ">=1,<2",
        "capabilities": ["reviewer"],
        "data_time_semantics": "historical_export",
        "entrypoint": entrypoint,
        "safety": SAFETY_DECLARATION,
    }


def _runtime(tmp_path: Path) -> PluginRuntime:
    return PluginRuntime(
        profile=get_profile("default-offline"),
        state_store=PluginStateStore(tmp_path / "plugins.db"),
    )


def test_entry_point_manifest_requires_colon_spec(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "ep"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        json.dumps(_manifest("not-a-valid-spec")), encoding="utf-8"
    )

    runtime = _runtime(tmp_path)
    runtime.discover([str(plugin_dir)])
    instance = runtime.activate("demo.entrypoint", enabled=True)
    assert instance.state == PluginState.ACTIVE
    assert instance.last_error is not None
    # A malformed entry point must not register any capability.
    assert runtime.services.resolve("reviewer") is None


def test_entry_point_provider_registration_and_rollback(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "ep2"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        json.dumps(_manifest("demo.module:factory")), encoding="utf-8"
    )

    runtime = _runtime(tmp_path)
    runtime.discover([str(plugin_dir)])

    # Register explicitly to model what a loaded entry point returns.
    provider = _StubProvider()
    scope = EffectScope()
    runtime.services.register_provider(provider, plugin_id="demo.entrypoint")
    scope.add("provider:reviewer", lambda: runtime.services.unregister_provider(provider))
    runtime.effects["demo.entrypoint"] = scope

    identity = runtime.services.provider_identity("reviewer")
    assert identity is not None
    assert identity["plugin_id"] == "demo.entrypoint"

    runtime.deactivate("demo.entrypoint")
    # Rollback must remove the provider so no consumer holds a stale reference.
    assert runtime.services.resolve("reviewer") is None
    assert runtime.registry.get("demo.entrypoint").state == PluginState.DISABLED


def test_undeclared_capability_from_entry_point_is_not_registered(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "ep3"
    plugin_dir.mkdir()
    payload = _manifest("demo.module:factory")
    payload["capabilities"] = ["memory"]
    (plugin_dir / "plugin.json").write_text(json.dumps(payload), encoding="utf-8")

    runtime = _runtime(tmp_path)
    runtime.discover([str(plugin_dir)])
    instance = runtime.registry.get("demo.entrypoint")
    assert instance is not None
    assert instance.capabilities == ["memory"]
    # The reviewer capability was never declared, so it must stay unregistered.
    assert runtime.services.resolve("reviewer") is None
