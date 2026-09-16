from __future__ import annotations

import importlib

import pytest


DECISION_TIME = "2026-09-10T15:00:00+08:00"
AVAILABLE_AT = "2026-09-10T14:00:00+08:00"
SAFETY = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"


def _contracts():
    return importlib.import_module("smartmoney_cub_harness.review_contracts")


def _validation():
    return importlib.import_module("smartmoney_cub_harness.review_validation")


def _scope_payload() -> dict:
    contracts = _contracts()
    return {
        "schema": contracts.REVIEW_SCOPE_SCHEMA,
        "review_id": "toy-review-1",
        "decision_time": DECISION_TIME,
        "horizons": ["d1", "d3"],
        "case_ids": ["toy-case-1"],
        "safety": SAFETY,
    }


def _redacted_envelope_payload() -> dict:
    contracts = _contracts()
    return {
        "schema": contracts.REDACTED_REVIEW_ENVELOPE_SCHEMA,
        "scope": _scope_payload(),
        "payload": {
            "symbol": "symbol-deadbeef",
            "portfolio_id": "portfolio-cafebabe",
            "quantity": "100-500",
            "amount": "10000-50000",
            "entry_time": "14:00-14:15",
            "trade_date": "2026-09",
            "return_pct": -4.25,
        },
        "payload_sha256": "a" * 64,
        "redaction_policy": "redaction.v1",
        "sent_keys": [
            "amount",
            "entry_time",
            "portfolio_id",
            "quantity",
            "return_pct",
            "symbol",
            "trade_date",
        ],
        "safety": SAFETY,
    }


def _evidence_payload() -> dict:
    contracts = _contracts()
    return {
        "schema": contracts.REVIEW_EVIDENCE_SCHEMA,
        "evidence_id": "toy-evidence-1",
        "kind": "review_observation",
        "summary": "Toy offline evidence for process review.",
        "data_source": "toy_offline_fixture",
        "available_at": AVAILABLE_AT,
        "data_quality_flag": "ok",
        "safety": SAFETY,
    }


def _observation() -> dict:
    return {
        "action_label": "WATCH",
        "summary": "Toy observation only; not an instruction.",
        "invalidation_price": 10.0,
        "time_stop": "D3 review",
        "give_up_conditions": ["Toy thesis is no longer supported."],
        "data_source": "toy_offline_fixture",
        "available_at": AVAILABLE_AT,
        "data_quality_flag": "ok",
    }


def _review_package(
    *,
    scope_decision_time: str = DECISION_TIME,
    envelope_decision_time: str = DECISION_TIME,
    observations: tuple[dict, ...] = (),
):
    contracts = _contracts()
    scope_payload = _scope_payload()
    scope_payload["decision_time"] = scope_decision_time
    envelope_payload = _redacted_envelope_payload()
    envelope_payload["scope"]["decision_time"] = envelope_decision_time
    return contracts.StructuredReviewPackage(
        review_id="toy-review-1",
        scope=contracts.ReviewScope.from_dict(scope_payload),
        envelope=contracts.RedactedReviewEnvelope.from_dict(envelope_payload),
        observations=observations,
    )


def test_current_contracts_round_trip_as_typed_objects() -> None:
    contracts = _contracts()
    scope = contracts.ReviewScope.from_dict(_scope_payload())
    envelope = contracts.RedactedReviewEnvelope.from_dict(_redacted_envelope_payload())
    evidence = contracts.ReviewEvidence.from_dict(_evidence_payload())
    package = contracts.StructuredReviewPackage(
        review_id="toy-review-1",
        scope=scope,
        envelope=envelope,
        evidence=(evidence,),
        observations=(_observation(),),
        challenger_proposals=(
            {
                "rule_id": "toy-rule-v2",
                "candidate_role": "challenger",
                "champion_mutated": False,
                "core_rules_mutated": False,
            },
        ),
    )
    result = contracts.PluginReviewResult(
        plugin_id="toy.reviewer",
        status="ok",
        review_package=package,
    )

    restored = contracts.PluginReviewResult.from_dict(result.to_dict())

    assert restored == result
    assert restored.review_package is not None
    assert restored.review_package.evidence[0].data_source == "toy_offline_fixture"
    assert result.to_dict()["safety"] == SAFETY
    assert result.to_dict()["champion_mutated"] is False
    assert result.to_dict()["core_rules_mutated"] is False


def test_explicit_v1_package_is_normalized_without_losing_review_data() -> None:
    contracts = _contracts()
    legacy = {
        "schema": contracts.LEGACY_STRUCTURED_REVIEW_PACKAGE_SCHEMA,
        "id": "toy-review-legacy",
        "scope": {
            "schema": contracts.LEGACY_REVIEW_SCOPE_SCHEMA,
            "id": "toy-review-legacy",
            "decision_at": DECISION_TIME,
            "horizon": "d1",
            "cases": ["toy-case-old"],
            "safety": SAFETY,
        },
        "redacted_envelope": {
            "schema": contracts.LEGACY_REDACTED_REVIEW_ENVELOPE_SCHEMA,
            "review_scope": {
                "schema": contracts.LEGACY_REVIEW_SCOPE_SCHEMA,
                "id": "toy-review-legacy",
                "decision_at": DECISION_TIME,
                "horizon": "d1",
                "cases": ["toy-case-old"],
                "safety": SAFETY,
            },
            "body": {"symbol": "symbol-deadbeef", "return_pct": 1.25},
            "sha256": "b" * 64,
            "policy": "redaction.v1",
            "keys": ["return_pct", "symbol"],
            "safety": SAFETY,
        },
        "items": [
            {
                "schema": contracts.LEGACY_REVIEW_EVIDENCE_SCHEMA,
                "id": "toy-evidence-old",
                "type": "review_observation",
                "text": "Legacy toy evidence.",
                "source": "toy_offline_fixture",
                "available_time": AVAILABLE_AT,
                "quality": "ok",
                "safety": SAFETY,
            }
        ],
        "review_observations": [_observation()],
        "challengers": [{"rule_id": "toy-rule-old", "candidate_role": "challenger"}],
        "safety": SAFETY,
    }

    package = contracts.StructuredReviewPackage.from_dict(legacy)

    assert package.source_schema == contracts.LEGACY_STRUCTURED_REVIEW_PACKAGE_SCHEMA
    assert package.schema == contracts.STRUCTURED_REVIEW_PACKAGE_SCHEMA
    assert package.scope.source_schema == contracts.LEGACY_REVIEW_SCOPE_SCHEMA
    assert package.scope.horizons == ("d1",)
    assert package.envelope.payload["symbol"] == "symbol-deadbeef"
    assert package.evidence[0].summary == "Legacy toy evidence."
    assert package.to_dict()["schema"] == contracts.STRUCTURED_REVIEW_PACKAGE_SCHEMA


def test_unknown_schema_version_is_rejected_explicitly() -> None:
    contracts = _contracts()
    payload = _scope_payload()
    payload["schema"] = "smartmoney_cub_review_scope.v99"

    with pytest.raises(contracts.ContractDecodeError, match="unsupported_schema"):
        contracts.ReviewScope.from_dict(payload)


def test_error_and_safety_metadata_have_stable_wire_shapes() -> None:
    contracts = _contracts()
    error = contracts.ReviewErrorMetadata(
        code=contracts.ReviewErrorCode.FUTURE_LEAKAGE,
        message="Evidence was unavailable at decision time.",
        field="available_at",
    )

    assert error.to_dict() == {
        "code": "future_leakage",
        "message": "Evidence was unavailable at decision time.",
        "field": "available_at",
        "retryable": False,
    }
    assert contracts.SafetyMetadata().to_dict() == {
        "declaration": SAFETY,
        "read_only": True,
        "order": False,
        "cancel": False,
        "trade": False,
        "account_mutation": False,
        "champion_mutation": False,
    }


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"account": "toy-account-raw"}, "redaction_sensitive_value"),
        ({"note": "token=toy-secret-value"}, "redaction_sensitive_value"),
        ({"symbol": "123456"}, "redaction_identifier_value"),
        ({"attachment": "data:image/png;base64," + "A" * 80}, "redaction_attachment"),
        (
            {"note": "/".join(("", "Users", "example", "ToyJournal.csv"))},
            "redaction_sensitive_value",
        ),
    ],
)
def test_redaction_validator_rejects_material_that_could_identify_or_escape(
    payload: dict, expected_code: str
) -> None:
    validation = _validation()

    result = validation.validate_redacted_payload(payload)

    assert result.ok is False
    assert expected_code in [error.code for error in result.errors]
    assert result.to_dict()["safety"] == SAFETY


def test_redaction_validator_accepts_redacted_toy_review_shape() -> None:
    validation = _validation()

    result = validation.validate_redacted_payload(_redacted_envelope_payload()["payload"])

    assert result.ok is True
    assert result.errors == ()


def test_redaction_validator_accepts_numeric_characters_inside_valid_aliases() -> None:
    validation = _validation()

    result = validation.validate_redacted_payload(
        {
            "symbol": "symbol-123456ab",
            "portfolio_id": "portfolio-a123456b",
            "watchlist": ["symbol-123456ab"],
            "review_note": "subject-123456ab",
        }
    )

    assert result.ok is True
    assert result.errors == ()


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"screenshot": "toy-image-reference"}, "redaction_attachment"),
        ({"quantity": 125}, "redaction_exact_value"),
        ({"amount": 25000.0}, "redaction_exact_value"),
        ({"entry_time": "2026-09-10T14:07:00+08:00"}, "redaction_exact_value"),
        ({"trade_date": "2026-09-10"}, "redaction_exact_value"),
    ],
)
def test_redaction_validator_rejects_attachment_fields_and_uncoarsened_values(
    payload: dict, expected_code: str
) -> None:
    validation = _validation()

    result = validation.validate_redacted_payload(payload)

    assert result.ok is False
    assert expected_code in [error.code for error in result.errors]


@pytest.mark.parametrize(
    "missing_field",
    [
        "invalidation_price",
        "time_stop",
        "give_up_conditions",
        "data_source",
        "available_at",
        "data_quality_flag",
    ],
)
def test_non_silent_observation_requires_complete_risk_and_provenance(
    missing_field: str,
) -> None:
    validation = _validation()
    observation = _observation()
    observation.pop(missing_field)

    result = validation.validate_observation(observation, decision_time=DECISION_TIME)

    assert result.ok is False
    assert result.errors[0].code == "observation_missing_field"
    assert result.errors[0].field == missing_field


def test_silent_observation_does_not_require_non_silent_risk_fields() -> None:
    validation = _validation()

    result = validation.validate_observation(
        {"action_label": "SILENT", "summary": "No usable toy output."},
        decision_time=DECISION_TIME,
    )

    assert result.ok is True


@pytest.mark.parametrize(
    ("available_at", "quality", "expected_code"),
    [
        ("2026-09-10T15:00:01+08:00", "ok", "future_leakage"),
        ("2026-09-10T14:00:00", "ok", "invalid_available_at"),
        (AVAILABLE_AT, "unknown", "invalid_data_quality"),
    ],
)
def test_source_time_validator_rejects_future_naive_or_unknown_quality(
    available_at: str, quality: str, expected_code: str
) -> None:
    validation = _validation()

    result = validation.validate_source_time(
        decision_time=DECISION_TIME,
        data_source="toy_offline_fixture",
        available_at=available_at,
        data_quality_flag=quality,
    )

    assert result.ok is False
    assert expected_code in [error.code for error in result.errors]


@pytest.mark.parametrize(
    "mutation",
    [
        {"candidate_role": "champion"},
        {"candidate_role": "challenger", "champion_mutated": True},
        {"candidate_role": "challenger", "core_rules_mutated": True},
    ],
)
def test_mutation_validator_refuses_every_non_challenger_or_direct_mutation(
    mutation: dict,
) -> None:
    validation = _validation()

    result = validation.validate_challenger_only_mutation(mutation)

    assert result.ok is False
    assert result.errors[0].code == "challenger_only_mutation"


def test_plugin_result_validation_aggregates_contract_errors_with_stable_codes() -> None:
    contracts = _contracts()
    validation = _validation()
    result = contracts.PluginReviewResult(
        plugin_id="toy.reviewer",
        status="ok",
        observations=({**_observation(), "available_at": "2026-09-10T16:00:00+08:00"},),
        challenger_proposals=({"candidate_role": "champion"},),
    )

    checked = validation.validate_plugin_result(result, decision_time=DECISION_TIME)

    assert checked.ok is False
    assert [error.code for error in checked.errors] == [
        "future_leakage",
        "challenger_only_mutation",
    ]
    assert checked.to_dict()["safety"] == SAFETY


def test_plugin_result_uses_package_scope_time_and_rejects_caller_disagreement() -> None:
    contracts = _contracts()
    validation = _validation()
    observation = {
        **_observation(),
        "available_at": "2026-09-10T15:30:00+08:00",
    }
    result = contracts.PluginReviewResult(
        plugin_id="toy.reviewer",
        status="ok",
        review_package=_review_package(observations=(observation,)),
    )

    checked = validation.validate_plugin_result(
        result,
        decision_time="2026-09-10T16:00:00+08:00",
    )

    assert [error.code for error in checked.errors] == [
        "decision_time_mismatch",
        "future_leakage",
    ]
    assert checked.errors[0].field == "decision_time"


def test_plugin_result_rejects_envelope_scope_time_disagreement() -> None:
    contracts = _contracts()
    validation = _validation()
    result = contracts.PluginReviewResult(
        plugin_id="toy.reviewer",
        status="ok",
        review_package=_review_package(
            envelope_decision_time="2026-09-10T16:00:00+08:00"
        ),
    )

    checked = validation.validate_plugin_result(result, decision_time=DECISION_TIME)

    assert checked.ok is False
    assert checked.errors[0].code == "decision_time_mismatch"
    assert checked.errors[0].field == "review_package.envelope.scope.decision_time"


@pytest.mark.parametrize(
    "payload",
    [
        {"symbol": 123456},
        {"portfolio_id": 42},
        {"symbol": "symbol-not-hex"},
        {"portfolio_id": "portfolio-too-short"},
    ],
)
def test_redaction_validator_requires_valid_aliases_regardless_of_value_type(
    payload: dict,
) -> None:
    validation = _validation()

    checked = validation.validate_redacted_payload(payload)

    assert checked.ok is False
    assert checked.errors[0].code == "redaction_identifier_value"


@pytest.mark.parametrize(
    "field_name",
    ["csv_original", "original_csv", "original_file", "source-original-file"],
)
def test_redaction_validator_rejects_original_file_fields(field_name: str) -> None:
    validation = _validation()

    checked = validation.validate_redacted_payload({field_name: "toy-offline-reference"})

    assert checked.ok is False
    assert checked.errors[0].code == "redaction_attachment"
    assert checked.errors[0].field == field_name


@pytest.mark.parametrize(
    "contract_name",
    ["scope", "envelope", "evidence", "package", "plugin_result"],
)
def test_typed_contract_construction_rejects_tampered_safety(contract_name: str) -> None:
    contracts = _contracts()
    scope = contracts.ReviewScope.from_dict(_scope_payload())
    envelope = contracts.RedactedReviewEnvelope.from_dict(_redacted_envelope_payload())
    evidence = contracts.ReviewEvidence.from_dict(_evidence_payload())
    factories = {
        "scope": lambda: contracts.ReviewScope(
            review_id="toy-review-unsafe",
            decision_time=DECISION_TIME,
            horizons=("d1",),
            safety="tampered",
        ),
        "envelope": lambda: contracts.RedactedReviewEnvelope(
            scope=scope,
            payload={},
            payload_sha256="a" * 64,
            redaction_policy="redaction.v1",
            sent_keys=(),
            safety="tampered",
        ),
        "evidence": lambda: contracts.ReviewEvidence(
            evidence_id="toy-evidence-unsafe",
            kind="review_observation",
            summary="Toy unsafe metadata fixture.",
            data_source="toy_offline_fixture",
            available_at=AVAILABLE_AT,
            data_quality_flag="ok",
            safety="tampered",
        ),
        "package": lambda: contracts.StructuredReviewPackage(
            review_id="toy-review-unsafe",
            scope=scope,
            envelope=envelope,
            evidence=(evidence,),
            safety="tampered",
        ),
        "plugin_result": lambda: contracts.PluginReviewResult(
            plugin_id="toy.reviewer",
            status="ok",
            safety="tampered",
        ),
    }

    with pytest.raises(contracts.ContractDecodeError, match="invalid_safety"):
        factories[contract_name]()


def test_challenger_validation_rejects_hidden_promotion_field() -> None:
    validation = _validation()

    checked = validation.validate_challenger_only_mutation(
        {
            "rule_id": "toy-rule-v3",
            "candidate_role": "challenger",
            "promote_to": "champion",
            "champion_mutated": False,
            "core_rules_mutated": False,
        }
    )

    assert checked.ok is False
    assert checked.errors[0].code == "challenger_only_mutation"
    assert checked.errors[0].field == "promote_to"


@pytest.mark.parametrize(
    "metadata,expected_field",
    [
        ({"rationale": "Keep as challenger; no promotion is requested."}, None),
        ({"rationale": "No champion or core rules were mutated."}, None),
        ({"items": [{"promote_to": "challenger"}]}, "metadata.items[0].promote_to"),
        ({"items": [{"PROMOTE-TO": "challenger"}]}, "metadata.items[0].PROMOTE-TO"),
        ({"items": [{"champion_mutated": False}]}, "metadata.items[0].champion_mutated"),
        ({"items": [{"Champion-Mutated": False}]}, "metadata.items[0].Champion-Mutated"),
        ({"items": [{"role": "champion"}]}, "metadata.items[0].role"),
        ({"items": [" ChAmPiOn "]}, "metadata.items[0]"),
    ],
)
def test_challenger_metadata_distinguishes_prose_from_mutation_indicators(
    metadata: dict, expected_field: str | None,
) -> None:
    checked = _validation().validate_challenger_only_mutation(
        {"candidate_role": "challenger", "metadata": metadata}
    )

    assert checked.ok is (expected_field is None)
    assert checked.safety == SAFETY
    if expected_field is None:
        assert checked.errors == ()
    else:
        assert len(checked.errors) == 1
        assert checked.errors[0].code == "challenger_only_mutation"
        assert checked.errors[0].field == expected_field


def test_plugin_result_rejects_nested_challenger_promotion_metadata() -> None:
    contracts = _contracts()
    validation = _validation()
    result = contracts.PluginReviewResult(
        plugin_id="toy.reviewer",
        status="ok",
        challenger_proposals=(
            {
                "rule_id": "toy-rule-nested",
                "candidate_role": "challenger",
                "champion_mutated": False,
                "core_rules_mutated": False,
                "metadata": {"promote_to": "champion"},
            },
        ),
    )

    checked = validation.validate_plugin_result(result, decision_time=DECISION_TIME)

    assert checked.ok is False
    assert checked.errors[0].code == "challenger_only_mutation"
    assert checked.errors[0].field == "metadata.promote_to"


def test_plugin_result_rejects_hyphenated_champion_mutation_key() -> None:
    contracts = _contracts()
    validation = _validation()
    result = contracts.PluginReviewResult(
        plugin_id="toy.reviewer",
        status="ok",
        challenger_proposals=(
            {
                "rule_id": "toy-rule-hyphenated",
                "candidate_role": "challenger",
                "champion_mutated": False,
                "core_rules_mutated": False,
                "champion-mutated": True,
            },
        ),
    )

    checked = validation.validate_plugin_result(result, decision_time=DECISION_TIME)

    assert checked.ok is False
    assert checked.errors[0].code == "challenger_only_mutation"
    assert checked.errors[0].field == "champion-mutated"


def test_v1_plugin_result_normalizes_aliases_to_current_contract() -> None:
    contracts = _contracts()
    legacy = {
        "schema": contracts.LEGACY_PLUGIN_REVIEW_RESULT_SCHEMA,
        "plugin_id": "toy.legacy-reviewer",
        "status": "ok",
        "package": None,
        "review_observations": [_observation()],
        "items": [
            {
                "schema": contracts.LEGACY_REVIEW_EVIDENCE_SCHEMA,
                "id": "toy-evidence-v1",
                "type": "review_observation",
                "text": "Legacy toy plugin evidence.",
                "source": "toy_offline_fixture",
                "available_time": AVAILABLE_AT,
                "quality": "ok",
                "safety": SAFETY,
            }
        ],
        "challengers": [
            {
                "rule_id": "toy-rule-v1",
                "candidate_role": "challenger",
                "champion_mutated": False,
                "core_rules_mutated": False,
            }
        ],
        "error": None,
        "champion_mutated": False,
        "core_rules_mutated": False,
        "safety": SAFETY,
    }

    result = contracts.PluginReviewResult.from_dict(legacy)

    assert result.source_schema == contracts.LEGACY_PLUGIN_REVIEW_RESULT_SCHEMA
    assert result.schema == contracts.PLUGIN_REVIEW_RESULT_SCHEMA
    assert result.observations[0]["action_label"] == "WATCH"
    assert result.evidence[0].summary == "Legacy toy plugin evidence."
    assert result.challenger_proposals[0]["candidate_role"] == "challenger"
    assert result.to_dict()["schema"] == contracts.PLUGIN_REVIEW_RESULT_SCHEMA
