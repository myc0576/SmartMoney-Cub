from __future__ import annotations

import json

import pytest

from smartmoney_cub_harness.plugins.curated_catalog import (
    CURATED_FINANCE_PLUGINS,
    CuratedFinancePluginCatalog,
    CuratedManifestError,
    parse_curated_manifest,
    validate_curated_manifest,
)
from smartmoney_cub_harness.plugins.cordis_adapters import (
    CordisBoundaryError,
    CordisReviewRequest,
    EvaluatorMemoryChallengerToyAdapter,
    TradingAgentsMultiRoleToyAdapter,
    build_toy_review_request,
    request_challenger_promotion,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_curated_manifest_has_strict_descriptor_metadata() -> None:
    descriptor = CURATED_FINANCE_PLUGINS[0]
    payload = descriptor.to_manifest()

    assert validate_curated_manifest(payload)["ok"] is True
    assert {
        "id",
        "name",
        "version",
        "source",
        "commit",
        "license",
        "declared_network",
        "permissions",
        "installed",
        "enabled",
        "update",
        "health",
        "profile_reload",
        "safety",
    } <= payload.keys()
    assert payload["safety"] == SAFETY_DECLARATION
    assert parse_curated_manifest(payload).id == descriptor.id


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("declared_network", "false", "invalid_declared_network"),
        ("permissions", ["shell"], "forbidden_permission:shell"),
        ("permissions", ["filesystem_read"], "forbidden_permission:filesystem_read"),
        ("permissions", ["web_fetch"], "forbidden_permission:web_fetch"),
        ("permissions", ["agent_team"], "forbidden_permission:agent_team"),
        ("commit", "", "empty_commit"),
        ("safety", "", "invalid_safety"),
    ],
)
def test_curated_manifest_rejects_unsafe_or_malformed_metadata(
    field: str, value: object, error: str
) -> None:
    payload = CURATED_FINANCE_PLUGINS[0].to_manifest()
    payload[field] = value
    result = validate_curated_manifest(payload)
    assert result["ok"] is False
    assert error in result["errors"]
    assert result["safety"] == SAFETY_DECLARATION
    with pytest.raises(CuratedManifestError):
        parse_curated_manifest(payload)


def test_curated_manifest_is_strict_about_unknown_fields() -> None:
    payload = CURATED_FINANCE_PLUGINS[0].to_manifest()
    payload["unexpected"] = True
    result = validate_curated_manifest(payload)
    assert result["ok"] is False
    assert "unknown_field:unexpected" in result["errors"]


def test_catalog_state_transitions_are_local_and_do_not_fetch_upstream() -> None:
    catalog = CuratedFinancePluginCatalog(CURATED_FINANCE_PLUGINS)
    plugin_id = CURATED_FINANCE_PLUGINS[0].id

    installed = catalog.install(plugin_id)
    assert installed["status"] == "installed"
    assert installed["plugin"]["installed"] is True
    assert installed["plugin"]["enabled"] is False

    enabled = catalog.enable(plugin_id)
    assert enabled["status"] == "enabled"
    assert enabled["plugin"]["enabled"] is True

    update = catalog.record_update(plugin_id, version="0.2.0", commit="toy-update-1")
    assert update["status"] == "update_available"
    applied = catalog.update(plugin_id)
    assert applied["status"] == "updated"
    assert applied["plugin"]["version"] == "0.2.0"
    assert applied["plugin"]["enabled"] is False

    disabled = catalog.disable(plugin_id)
    assert disabled["status"] == "disabled"
    assert disabled["plugin"]["enabled"] is False

    health = catalog.health(plugin_id)
    assert health["status"] == "ok"
    assert health["health"]["executed_upstream"] is False
    assert health["safety"] == SAFETY_DECLARATION

    reload_result = catalog.profile_reload("default-offline")
    assert reload_result["status"] == "profile_reload_requested"
    assert reload_result["event"]["explicit"] is True
    assert reload_result["event"]["executed_upstream"] is False


def test_cordis_request_requires_task_one_redacted_typed_envelope() -> None:
    request = build_toy_review_request()
    assert isinstance(request, CordisReviewRequest)
    assert request.envelope.safety == SAFETY_DECLARATION

    with pytest.raises(CordisBoundaryError):
        CordisReviewRequest.from_payload({"raw_journal": "private", "csv": "original"})

    encoded = json.dumps(request.to_dict(), ensure_ascii=False)
    assert "raw_journal" not in encoded
    assert "absolute" not in encoded
    assert "/Users/" not in encoded


@pytest.mark.parametrize(
    "adapter",
    [TradingAgentsMultiRoleToyAdapter(), EvaluatorMemoryChallengerToyAdapter()],
)
def test_toy_cordis_adapters_return_validated_structured_review_results(adapter) -> None:
    request = build_toy_review_request()
    result = adapter.run(request)

    assert result.validation["ok"] is True
    assert result.plugin_result.safety == SAFETY_DECLARATION
    assert result.to_dict()["safety"] == SAFETY_DECLARATION
    assert result.plugin_result.champion_mutated is False
    assert result.plugin_result.core_rules_mutated is False
    assert result.plugin_result.evidence
    assert result.plugin_result.challenger_proposals


def test_champion_promotion_requires_challenger_and_explicit_confirmation() -> None:
    result = TradingAgentsMultiRoleToyAdapter().run(build_toy_review_request())
    proposal = result.plugin_result.challenger_proposals[0]

    blocked = request_challenger_promotion(proposal, explicit_confirmation=False)
    assert blocked["promotion_authorized"] is False
    assert blocked["champion_mutated"] is False

    authorized = request_challenger_promotion(proposal, explicit_confirmation=True)
    assert authorized["promotion_authorized"] is True
    assert authorized["champion_mutated"] is False
    assert authorized["next_step"] == "core_governance_human_mutation"

    with pytest.raises(CordisBoundaryError):
        request_challenger_promotion(
            {"candidate_role": "champion", "champion_mutated": False, "core_rules_mutated": False},
            explicit_confirmation=True,
        )


def test_legacy_plugin_catalog_exposes_curated_finance_catalog_without_loading_upstream() -> None:
    from smartmoney_cub_harness.plugin_cli import plugin_catalog

    payload = plugin_catalog()
    curated = payload["curated_finance"]
    assert curated["schema"] == "smartmoney_cub_curated_finance_catalog.v1"
    assert {item["id"] for item in curated["plugins"]} == {
        "smartmoney.tradingagents-toy",
        "smartmoney.evaluator-memory-challenger-toy",
    }
    assert all(item["health"]["executed_upstream"] is False for item in curated["plugins"])
    assert payload["safety"] == SAFETY_DECLARATION
