from __future__ import annotations

import json
from pathlib import Path

import pytest

from smartmoney_cub_harness.plugins import (
    BUILTIN_PROFILES,
    BaseConsumer,
    BaseProvider,
    CapabilityName,
    EffectScope,
    EvidenceEnvelopeError,
    ManifestError,
    PluginState,
    ServiceDefinition,
    ServiceRegistry,
    build_evidence_envelope,
    parse_manifest,
    validate_evidence_envelope,
    validate_manifest,
)
from smartmoney_cub_harness.plugins.lifecycle import should_activate
from smartmoney_cub_harness.plugins.profiles import Patch, get_profile
from smartmoney_cub_harness.plugins.types import ResultKind
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

TOY_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "examples" / "toy_plugin"


def _manifest(**overrides: object) -> dict:
    payload = {
        "schema": "smartmoney_cub_plugin_manifest.v1",
        "plugin_id": "demo.reviewer",
        "name": "Demo Reviewer",
        "version": "0.1.0",
        "source_repo": "https://example.com/demo",
        "source_commit": "abc123",
        "license": "MIT",
        "kind": "local-path",
        "trust_level": "review-only",
        "api_range": ">=1,<2",
        "capabilities": ["reviewer"],
        "data_time_semantics": "historical_export",
        "entrypoint": "demo.plugin:register",
        "safety": SAFETY_DECLARATION,
    }
    payload.update(overrides)
    return payload


class _StaticProvider(BaseProvider):
    capability = CapabilityName.TRADE_IMPORT
    plugin_id = "demo.local"

    def invoke(self, request: dict) -> dict:
        return {"round_trips": [], "echo": request.get("symbol")}


class _DashConsumer(BaseConsumer):
    required_services = (CapabilityName.TRADE_IMPORT,)
    optional_services = (CapabilityName.MARKET_CONTEXT,)


def test_valid_manifest_parses_with_safety_declaration() -> None:
    result = validate_manifest(_manifest())
    assert result["ok"] is True
    assert result["safety"] == SAFETY_DECLARATION
    manifest = parse_manifest(_manifest())
    assert manifest.plugin_id == "demo.reviewer"
    assert manifest.capabilities == ["reviewer"]
    assert manifest.to_dict()["safety"] == SAFETY_DECLARATION


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({"safety": ""}, "missing_or_invalid_safety_declaration"),
        ({"license": ""}, "empty_license"),
        ({"api_range": ">=3,<4"}, "incompatible_api_range:>=3,<4"),
        ({"capabilities": []}, "capabilities_not_non_empty_list"),
        ({"capabilities": ["order_execution"]}, "forbidden_capability:order_execution"),
        ({"kind": "telepathy"}, "invalid_kind"),
        ({"trust_level": "root"}, "invalid_trust_level"),
    ],
)
def test_manifest_rejects_unsafe_or_incomplete_declarations(overrides: dict, expected_error: str) -> None:
    result = validate_manifest(_manifest(**overrides))
    assert result["ok"] is False
    assert expected_error in result["errors"]
    assert result["safety"] == SAFETY_DECLARATION


def test_missing_required_fields_are_all_reported() -> None:
    result = validate_manifest({"plugin_id": "x"})
    assert result["ok"] is False
    assert "missing_schema" in result["errors"]
    assert "missing_licence" not in result["errors"]
    assert "missing_license" in result["errors"]
    parse_raises = False
    try:
        parse_manifest({"plugin_id": "x"})
    except ManifestError:
        parse_raises = True
    assert parse_raises


def test_manifest_rejects_non_object_payload() -> None:
    result = validate_manifest(["not", "an", "object"])
    assert result["ok"] is False
    assert result["errors"] == ["manifest_not_object"]


def test_subprocess_manifest_requires_entrypoint() -> None:
    result = validate_manifest(_manifest(kind="subprocess", entrypoint=None))
    assert "subprocess_plugin_requires_entrypoint" in result["errors"]


def test_service_registry_injects_without_provider_imports() -> None:
    registry = ServiceRegistry()
    registry.register_provider(_StaticProvider())

    consumer = _DashConsumer()
    wiring = registry.inject(consumer)
    assert wiring["bound"] == [CapabilityName.TRADE_IMPORT]
    assert wiring["missing_optional"] == [CapabilityName.MARKET_CONTEXT]
    assert consumer.has(CapabilityName.TRADE_IMPORT)
    assert consumer.call(CapabilityName.TRADE_IMPORT, {"symbol": "600111"})["echo"] == "600111"


def test_missing_hard_dependency_is_reported_as_pending_cause() -> None:
    registry = ServiceRegistry()
    consumer = _DashConsumer()
    with pytest.raises(Exception) as excinfo:
        registry.inject(consumer)
    assert CapabilityName.TRADE_IMPORT in getattr(excinfo.value, "missing", [])


def test_provider_replacement_keeps_consumer_unchanged() -> None:
    class _OtherProvider(_StaticProvider):
        plugin_id = "demo.replacement"

        def invoke(self, request: dict) -> dict:
            return {"round_trips": ["replaced"]}

    registry = ServiceRegistry()
    first = _StaticProvider()
    registry.register_provider(first)
    consumer = _DashConsumer()
    registry.inject(consumer)
    assert consumer.call(CapabilityName.TRADE_IMPORT, {})["round_trips"] == []

    registry.unregister_provider(first)
    registry.register_provider(_OtherProvider())
    registry.inject(consumer)
    assert consumer.call(CapabilityName.TRADE_IMPORT, {})["round_trips"] == ["replaced"]


def test_capability_catalog_reports_conflicts_and_declared_permissions() -> None:
    registry = ServiceRegistry()

    class _ProviderA(_StaticProvider):
        plugin_id = "demo.a"
        precedence = 5

    class _ProviderB(_StaticProvider):
        plugin_id = "demo.b"
        precedence = 5

    registry.register_provider(_ProviderA())
    registry.register_provider(_ProviderB())
    catalog = registry.catalog()
    assert catalog["conflicts"]
    identity = registry.provider_identity(CapabilityName.TRADE_IMPORT)
    assert identity is not None
    # Declared permissions are never presented as a verified sandbox.
    assert identity["enforcement"] == "declarative"
    assert identity["verified"] is False


def test_custom_service_definition_keeps_definition_provider_separate() -> None:
    registry = ServiceRegistry()
    registry.define(ServiceDefinition(name="custom_seam", description="test seam"))

    class _Custom(BaseProvider):
        capability = "custom_seam"
        plugin_id = "demo.custom"

        def invoke(self, request: dict) -> dict:
            return {"ok": True}

    registry.register_provider(_Custom())
    catalog = registry.catalog()
    entry = next(item for item in catalog["capabilities"] if item["capability"] == "custom_seam")
    assert entry["status"] == "available"


def test_effect_scope_rolls_back_in_reverse_and_survives_failures() -> None:
    order: list[str] = []
    scope = EffectScope()
    scope.add("first", lambda: order.append("first"))
    scope.add("second", lambda: order.append("second"))

    def boom() -> None:
        raise RuntimeError("disposer failed")

    scope.add("third", boom)
    errors = scope.dispose()
    assert [entry["effect"] for entry in errors] == ["third"]
    assert order == ["second", "first"]
    assert scope.disposed is True


def test_effect_scope_clears_stale_references() -> None:
    class Holder:
        ref: object | None = "stale"

    holder = Holder()
    scope = EffectScope()
    scope.wrap("dash", holder, "ref")
    scope.dispose()
    assert holder.ref is None


@pytest.mark.parametrize(
    ("enabled", "missing", "blockers", "expected"),
    [
        (True, [], [], PluginState.ACTIVE),
        (False, [], [], PluginState.DISABLED),
        (True, ["evaluator"], [], PluginState.PENDING),
        (True, [], ["network_required_but_profile_disallows_network"], PluginState.BLOCKED),
        (True, ["evaluator"], ["blocked"], PluginState.BLOCKED),
    ],
)
def test_activation_policy(enabled: bool, missing: list, blockers: list, expected: str) -> None:
    should, state = should_activate(enabled=enabled, missing_services=missing, blockers=blockers)
    assert state == expected
    assert should is (expected == PluginState.ACTIVE)


def test_evidence_envelope_hashes_and_marks_review_only() -> None:
    envelope = build_evidence_envelope(
        plugin_id="demo.reviewer",
        plugin_version="0.1.0",
        source_ref="demo@abc123",
        capability=CapabilityName.REVIEWER,
        result_kind=ResultKind.MODEL_OPINION,
        request={"symbol": "600111"},
        output={"observations": []},
        decision_time="2026-09-10T15:00:00+08:00",
        available_at="2026-09-10T14:00:00+08:00",
        data_source="toy_fixture",
        data_quality="ok",
        model_used=True,
    )
    assert validate_evidence_envelope(envelope)["ok"] is True
    assert envelope["review_only"] is True
    assert len(envelope["input_sha256"]) == 64
    assert len(envelope["output_sha256"]) == 64
    # Plugin output must never claim to have mutated champion rules.
    assert envelope["champion_mutated"] is False
    assert envelope["safety"] == SAFETY_DECLARATION


def test_evidence_envelope_blocks_future_leakage() -> None:
    with pytest.raises(EvidenceEnvelopeError) as excinfo:
        build_evidence_envelope(
            plugin_id="demo.reviewer",
            plugin_version="0.1.0",
            source_ref="demo@abc123",
            capability=CapabilityName.REVIEWER,
            result_kind=ResultKind.FACT_DATA,
            request={},
            output={},
            decision_time="2026-09-10T15:00:00+08:00",
            available_at="2026-09-11T15:00:00+08:00",
            data_source="toy_fixture",
            data_quality="ok",
        )
    assert "future leakage" in str(excinfo.value)


def test_evidence_envelope_requires_quality_and_aware_timestamps() -> None:
    with pytest.raises(EvidenceEnvelopeError):
        build_evidence_envelope(
            plugin_id="demo.reviewer",
            plugin_version="0.1.0",
            source_ref="demo",
            capability="reviewer",
            result_kind=ResultKind.FACT_DATA,
            request={},
            output={},
            decision_time=None,
            available_at="2026-09-10T15:00:00",
            data_source="toy",
            data_quality="ok",
        )
    with pytest.raises(EvidenceEnvelopeError):
        build_evidence_envelope(
            plugin_id="demo.reviewer",
            plugin_version="0.1.0",
            source_ref="demo",
            capability="reviewer",
            result_kind=ResultKind.FACT_DATA,
            request={},
            output={},
            decision_time=None,
            available_at="2026-09-10T15:00:00+08:00",
            data_source="toy",
            data_quality="",
        )


def test_envelope_validation_rejects_forbidden_permissions_and_champion_mutation() -> None:
    envelope = build_evidence_envelope(
        plugin_id="demo.reviewer",
        plugin_version="0.1.0",
        source_ref="demo",
        capability="reviewer",
        result_kind=ResultKind.REVIEW_OBSERVATION,
        request={},
        output={},
        decision_time=None,
        available_at="2026-09-10T15:00:00+08:00",
        data_source="toy",
        data_quality="ok",
    )
    envelope["permission"]["order"] = True
    envelope["champion_mutated"] = True
    result = validate_evidence_envelope(envelope)
    assert result["ok"] is False
    assert "forbidden_permission:order" in result["errors"]
    assert "plugin_output_must_not_mutate_champion" in result["errors"]


def test_builtin_profiles_default_to_offline_and_gate_ai() -> None:
    offline = get_profile("default-offline")
    assert offline.allow_network is False
    assert offline.allow_external_llm is False

    ai = get_profile("ai-optional")
    entries = {entry.id: entry for entry in ai.resolve_entries()}
    assert entries["ai.llm-provider-slot"].enabled is False
    assert entries["ai.llm-provider-slot"].disabled_reason is not None

    a_share = get_profile("a-share-review")
    ids = [entry.id for entry in a_share.resolve_entries()]
    assert "a-share.fill-ledger" in ids
    assert "core.local-csv-import" in ids


def test_profile_patches_enable_and_reconfigure_entries() -> None:
    profile = get_profile("research")
    patched = Patch(entry_id="research.evaluator-slot", enabled=True, config={"model": "toy"})
    profile.patches = [patched]
    entries = {entry.id: entry for entry in profile.resolve_entries()}
    assert entries["research.evaluator-slot"].enabled is True
    assert entries["research.evaluator-slot"].config == {"model": "toy"}
    # Patching one entry must not disturb the others.
    assert entries["research.replay-slot"].enabled is False
    profile.patches = []


def test_profile_dump_is_json_serialisable_and_carries_safety() -> None:
    payload = {name: profile.to_dict() for name, profile in BUILTIN_PROFILES.items()}
    encoded = json.dumps(payload, ensure_ascii=False)
    assert SAFETY_DECLARATION in encoded
    assert set(payload) == {"default-offline", "a-share-review", "research", "ai-optional"}
