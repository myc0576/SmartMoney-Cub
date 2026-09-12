from __future__ import annotations

import json
from pathlib import Path

from smartmoney_cub_harness.plugins.envelope import (
    EVIDENCE_ENVELOPE_SCHEMA,
    REQUIRED_ENVELOPE_FIELDS,
    build_evidence_envelope,
    validate_evidence_envelope,
)
from smartmoney_cub_harness.plugins.manifest import (
    PLUGIN_MANIFEST_SCHEMA,
    REQUIRED_MANIFEST_FIELDS,
    parse_manifest,
    validate_manifest,
)
from smartmoney_cub_harness.plugins.types import ResultKind
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = REPO_ROOT / "schemas"
TOY_MANIFEST = REPO_ROOT / "examples" / "toy_plugin" / "plugin.json"


def _schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_manifest_schema_matches_validator_expectations() -> None:
    schema = _schema("plugin-manifest.schema.json")
    assert schema["properties"]["schema"]["const"] == PLUGIN_MANIFEST_SCHEMA
    assert schema["properties"]["safety"]["const"] == SAFETY_DECLARATION
    # Every field the validator requires must also be required by the schema.
    assert set(REQUIRED_MANIFEST_FIELDS) <= set(schema["required"])


def test_manifest_schema_forbids_execution_capabilities() -> None:
    schema = _schema("plugin-manifest.schema.json")
    capability_items = schema["properties"]["capabilities"]["items"]
    assert "not" in capability_items
    pattern = capability_items["not"]["pattern"].lower()
    for forbidden in ("order", "cancel", "trade_execution", "account_mutation", "broker"):
        assert forbidden in pattern


def test_evidence_schema_matches_envelope_validator() -> None:
    schema = _schema("plugin-evidence-envelope.schema.json")
    assert schema["properties"]["schema"]["const"] == EVIDENCE_ENVELOPE_SCHEMA
    assert schema["properties"]["safety"]["const"] == SAFETY_DECLARATION
    assert set(REQUIRED_ENVELOPE_FIELDS) <= set(schema["required"])
    assert schema["properties"]["result_kind"]["enum"] == list(ResultKind.ALL)
    # Permission honesty and the champion prohibition are part of the wire contract.
    permission = schema["properties"]["permission"]["properties"]
    for forbidden in ("order", "cancel", "trade", "account_mutation", "broker_access"):
        assert permission[forbidden]["const"] is False
    assert permission["enforcement"]["const"] == "declarative"
    assert permission["verified"]["const"] is False
    assert schema["properties"]["champion_mutated"]["const"] is False
    assert schema["properties"]["core_rules_mutated"]["const"] is False


def test_reference_manifest_validates_against_schema_and_code() -> None:
    payload = json.loads(TOY_MANIFEST.read_text(encoding="utf-8"))
    assert validate_manifest(payload)["ok"] is True
    manifest = parse_manifest(payload)
    schema = _schema("plugin-manifest.schema.json")
    for field in schema["required"]:
        assert field in payload, field
    assert manifest.kind == "subprocess"
    assert manifest.network_required is False


def test_produced_envelope_matches_documented_fields() -> None:
    envelope = build_evidence_envelope(
        plugin_id="toy.review-tagger",
        plugin_version="0.1.0",
        source_ref="toy@abc",
        capability="reviewer",
        result_kind=ResultKind.REVIEW_OBSERVATION,
        request={},
        output={"observations": []},
        decision_time=None,
        available_at="2026-09-10T15:00:00+08:00",
        data_source="toy",
        data_quality="ok",
    )
    assert validate_evidence_envelope(envelope)["ok"] is True
    for field in REQUIRED_ENVELOPE_FIELDS:
        assert field in envelope, field
    assert envelope["permission"]["order"] is False
    assert envelope["champion_mutated"] is False


def test_schema_files_are_valid_json_and_declare_ids() -> None:
    for name in (
        "plugin-manifest.schema.json",
        "plugin-evidence-envelope.schema.json",
    ):
        schema = _schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "$id" in schema
        assert schema["type"] == "object"
