from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


REVIEW_SCOPE_SCHEMA = "smartmoney_cub_review_scope.v2"
LEGACY_REVIEW_SCOPE_SCHEMA = "smartmoney_cub_review_scope.v1"
REDACTED_REVIEW_ENVELOPE_SCHEMA = "smartmoney_cub_redacted_review_envelope.v2"
LEGACY_REDACTED_REVIEW_ENVELOPE_SCHEMA = "smartmoney_cub_redacted_review_envelope.v1"
REVIEW_EVIDENCE_SCHEMA = "smartmoney_cub_review_evidence.v2"
LEGACY_REVIEW_EVIDENCE_SCHEMA = "smartmoney_cub_review_evidence.v1"
STRUCTURED_REVIEW_PACKAGE_SCHEMA = "smartmoney_cub_structured_review_package.v2"
LEGACY_STRUCTURED_REVIEW_PACKAGE_SCHEMA = "smartmoney_cub_structured_review_package.v1"
PLUGIN_REVIEW_RESULT_SCHEMA = "smartmoney_cub_plugin_review_result.v2"
LEGACY_PLUGIN_REVIEW_RESULT_SCHEMA = "smartmoney_cub_plugin_review_result.v1"


class ContractDecodeError(ValueError):
    """Raised when a versioned review contract cannot be normalized safely."""


class ReviewErrorCode:
    CONTRACT_DECODE = "contract_decode"
    INVALID_SAFETY = "invalid_safety"
    REDACTION_ATTACHMENT = "redaction_attachment"
    REDACTION_EXACT_VALUE = "redaction_exact_value"
    REDACTION_IDENTIFIER_VALUE = "redaction_identifier_value"
    REDACTION_SENSITIVE_VALUE = "redaction_sensitive_value"
    OBSERVATION_MISSING_FIELD = "observation_missing_field"
    INVALID_ACTION_LABEL = "invalid_action_label"
    INVALID_DECISION_TIME = "invalid_decision_time"
    INVALID_AVAILABLE_AT = "invalid_available_at"
    INVALID_DATA_QUALITY = "invalid_data_quality"
    MISSING_DATA_SOURCE = "missing_data_source"
    FUTURE_LEAKAGE = "future_leakage"
    CHALLENGER_ONLY_MUTATION = "challenger_only_mutation"


def _mapping(payload: object, *, name: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ContractDecodeError(f"invalid_field:{name}")
    return payload


def _schema(payload: Mapping[str, Any], supported: tuple[str, ...]) -> str:
    value = payload.get("schema")
    if value not in supported:
        raise ContractDecodeError(f"unsupported_schema:{value}")
    return str(value)


def _string(value: object, *, name: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ContractDecodeError(f"invalid_field:{name}")
    return value


def _strings(value: object, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ContractDecodeError(f"invalid_field:{name}")
    return tuple(value)


def _dicts(value: object, *, name: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, Mapping) for item in value):
        raise ContractDecodeError(f"invalid_field:{name}")
    return tuple(dict(item) for item in value)


def _safety(value: object) -> str:
    if value != SAFETY_DECLARATION:
        raise ContractDecodeError("invalid_safety")
    return SAFETY_DECLARATION


@dataclass(frozen=True)
class SafetyMetadata:
    declaration: str = SAFETY_DECLARATION
    read_only: bool = True
    order: bool = False
    cancel: bool = False
    trade: bool = False
    account_mutation: bool = False
    champion_mutation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "declaration": self.declaration,
            "read_only": self.read_only,
            "order": self.order,
            "cancel": self.cancel,
            "trade": self.trade,
            "account_mutation": self.account_mutation,
            "champion_mutation": self.champion_mutation,
        }


@dataclass(frozen=True)
class ReviewErrorMetadata:
    code: str
    message: str
    field: str | None = None
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "retryable": self.retryable,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ReviewErrorMetadata:
        raw = _mapping(payload, name="error")
        field_value = raw.get("field")
        if field_value is not None and not isinstance(field_value, str):
            raise ContractDecodeError("invalid_field:error.field")
        return cls(
            code=_string(raw.get("code"), name="error.code"),
            message=_string(raw.get("message"), name="error.message"),
            field=field_value,
            retryable=bool(raw.get("retryable", False)),
        )


@dataclass(frozen=True)
class ReviewScope:
    review_id: str
    decision_time: str
    horizons: tuple[str, ...]
    case_ids: tuple[str, ...] = ()
    safety: str = SAFETY_DECLARATION
    schema: str = REVIEW_SCOPE_SCHEMA
    source_schema: str = REVIEW_SCOPE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REVIEW_SCOPE_SCHEMA,
            "review_id": self.review_id,
            "decision_time": self.decision_time,
            "horizons": list(self.horizons),
            "case_ids": list(self.case_ids),
            "safety": self.safety,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ReviewScope:
        raw = _mapping(payload, name="scope")
        source_schema = _schema(raw, (REVIEW_SCOPE_SCHEMA, LEGACY_REVIEW_SCOPE_SCHEMA))
        if source_schema == LEGACY_REVIEW_SCOPE_SCHEMA:
            horizon = raw.get("horizon")
            horizons = raw.get("horizons", [horizon] if horizon is not None else [])
            review_id = raw.get("id")
            decision_time = raw.get("decision_at")
            case_ids = raw.get("cases", [])
        else:
            horizons = raw.get("horizons")
            review_id = raw.get("review_id")
            decision_time = raw.get("decision_time")
            case_ids = raw.get("case_ids", [])
        return cls(
            review_id=_string(review_id, name="scope.review_id"),
            decision_time=_string(decision_time, name="scope.decision_time"),
            horizons=_strings(horizons, name="scope.horizons"),
            case_ids=_strings(case_ids, name="scope.case_ids"),
            safety=_safety(raw.get("safety")),
            source_schema=source_schema,
        )


@dataclass(frozen=True)
class RedactedReviewEnvelope:
    scope: ReviewScope
    payload: dict[str, Any]
    payload_sha256: str
    redaction_policy: str
    sent_keys: tuple[str, ...]
    safety: str = SAFETY_DECLARATION
    schema: str = REDACTED_REVIEW_ENVELOPE_SCHEMA
    source_schema: str = REDACTED_REVIEW_ENVELOPE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REDACTED_REVIEW_ENVELOPE_SCHEMA,
            "scope": self.scope.to_dict(),
            "payload": dict(self.payload),
            "payload_sha256": self.payload_sha256,
            "redaction_policy": self.redaction_policy,
            "sent_keys": list(self.sent_keys),
            "safety": self.safety,
        }

    @classmethod
    def from_dict(cls, payload: object) -> RedactedReviewEnvelope:
        raw = _mapping(payload, name="envelope")
        source_schema = _schema(
            raw,
            (REDACTED_REVIEW_ENVELOPE_SCHEMA, LEGACY_REDACTED_REVIEW_ENVELOPE_SCHEMA),
        )
        if source_schema == LEGACY_REDACTED_REVIEW_ENVELOPE_SCHEMA:
            scope = raw.get("review_scope")
            body = raw.get("body")
            sha256 = raw.get("sha256")
            policy = raw.get("policy")
            sent_keys = raw.get("keys", [])
        else:
            scope = raw.get("scope")
            body = raw.get("payload")
            sha256 = raw.get("payload_sha256")
            policy = raw.get("redaction_policy")
            sent_keys = raw.get("sent_keys", [])
        return cls(
            scope=ReviewScope.from_dict(scope),
            payload=dict(_mapping(body, name="envelope.payload")),
            payload_sha256=_string(sha256, name="envelope.payload_sha256"),
            redaction_policy=_string(policy, name="envelope.redaction_policy"),
            sent_keys=_strings(sent_keys, name="envelope.sent_keys"),
            safety=_safety(raw.get("safety")),
            source_schema=source_schema,
        )


@dataclass(frozen=True)
class ReviewEvidence:
    evidence_id: str
    kind: str
    summary: str
    data_source: str
    available_at: str
    data_quality_flag: str
    safety: str = SAFETY_DECLARATION
    schema: str = REVIEW_EVIDENCE_SCHEMA
    source_schema: str = REVIEW_EVIDENCE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REVIEW_EVIDENCE_SCHEMA,
            "evidence_id": self.evidence_id,
            "kind": self.kind,
            "summary": self.summary,
            "data_source": self.data_source,
            "available_at": self.available_at,
            "data_quality_flag": self.data_quality_flag,
            "safety": self.safety,
        }

    @classmethod
    def from_dict(cls, payload: object) -> ReviewEvidence:
        raw = _mapping(payload, name="evidence")
        source_schema = _schema(raw, (REVIEW_EVIDENCE_SCHEMA, LEGACY_REVIEW_EVIDENCE_SCHEMA))
        if source_schema == LEGACY_REVIEW_EVIDENCE_SCHEMA:
            values = {
                "evidence_id": raw.get("id"),
                "kind": raw.get("type"),
                "summary": raw.get("text"),
                "data_source": raw.get("source"),
                "available_at": raw.get("available_time"),
                "data_quality_flag": raw.get("quality"),
            }
        else:
            values = raw
        return cls(
            evidence_id=_string(values.get("evidence_id"), name="evidence.evidence_id"),
            kind=_string(values.get("kind"), name="evidence.kind"),
            summary=_string(values.get("summary"), name="evidence.summary"),
            data_source=_string(values.get("data_source"), name="evidence.data_source"),
            available_at=_string(values.get("available_at"), name="evidence.available_at"),
            data_quality_flag=_string(
                values.get("data_quality_flag"), name="evidence.data_quality_flag"
            ),
            safety=_safety(raw.get("safety")),
            source_schema=source_schema,
        )


@dataclass(frozen=True)
class StructuredReviewPackage:
    review_id: str
    scope: ReviewScope
    envelope: RedactedReviewEnvelope
    evidence: tuple[ReviewEvidence, ...] = ()
    observations: tuple[dict[str, Any], ...] = ()
    challenger_proposals: tuple[dict[str, Any], ...] = ()
    safety: str = SAFETY_DECLARATION
    schema: str = STRUCTURED_REVIEW_PACKAGE_SCHEMA
    source_schema: str = STRUCTURED_REVIEW_PACKAGE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": STRUCTURED_REVIEW_PACKAGE_SCHEMA,
            "review_id": self.review_id,
            "scope": self.scope.to_dict(),
            "envelope": self.envelope.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "observations": [dict(item) for item in self.observations],
            "challenger_proposals": [dict(item) for item in self.challenger_proposals],
            "safety": self.safety,
        }

    @classmethod
    def from_dict(cls, payload: object) -> StructuredReviewPackage:
        raw = _mapping(payload, name="review_package")
        source_schema = _schema(
            raw,
            (STRUCTURED_REVIEW_PACKAGE_SCHEMA, LEGACY_STRUCTURED_REVIEW_PACKAGE_SCHEMA),
        )
        if source_schema == LEGACY_STRUCTURED_REVIEW_PACKAGE_SCHEMA:
            review_id = raw.get("id")
            envelope = raw.get("redacted_envelope")
            evidence = raw.get("items", [])
            observations = raw.get("review_observations", [])
            challengers = raw.get("challengers", [])
        else:
            review_id = raw.get("review_id")
            envelope = raw.get("envelope")
            evidence = raw.get("evidence", [])
            observations = raw.get("observations", [])
            challengers = raw.get("challenger_proposals", [])
        if not isinstance(evidence, (list, tuple)):
            raise ContractDecodeError("invalid_field:review_package.evidence")
        return cls(
            review_id=_string(review_id, name="review_package.review_id"),
            scope=ReviewScope.from_dict(raw.get("scope")),
            envelope=RedactedReviewEnvelope.from_dict(envelope),
            evidence=tuple(ReviewEvidence.from_dict(item) for item in evidence),
            observations=_dicts(observations, name="review_package.observations"),
            challenger_proposals=_dicts(
                challengers, name="review_package.challenger_proposals"
            ),
            safety=_safety(raw.get("safety")),
            source_schema=source_schema,
        )


@dataclass(frozen=True)
class PluginReviewResult:
    plugin_id: str
    status: str
    review_package: StructuredReviewPackage | None = None
    observations: tuple[dict[str, Any], ...] = ()
    evidence: tuple[ReviewEvidence, ...] = ()
    challenger_proposals: tuple[dict[str, Any], ...] = ()
    error: ReviewErrorMetadata | None = None
    champion_mutated: bool = False
    core_rules_mutated: bool = False
    safety: str = SAFETY_DECLARATION
    schema: str = PLUGIN_REVIEW_RESULT_SCHEMA
    source_schema: str = PLUGIN_REVIEW_RESULT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PLUGIN_REVIEW_RESULT_SCHEMA,
            "plugin_id": self.plugin_id,
            "status": self.status,
            "review_package": self.review_package.to_dict() if self.review_package else None,
            "observations": [dict(item) for item in self.observations],
            "evidence": [item.to_dict() for item in self.evidence],
            "challenger_proposals": [dict(item) for item in self.challenger_proposals],
            "error": self.error.to_dict() if self.error else None,
            "champion_mutated": self.champion_mutated,
            "core_rules_mutated": self.core_rules_mutated,
            "safety": self.safety,
        }

    @classmethod
    def from_dict(cls, payload: object) -> PluginReviewResult:
        raw = _mapping(payload, name="plugin_result")
        source_schema = _schema(
            raw,
            (PLUGIN_REVIEW_RESULT_SCHEMA, LEGACY_PLUGIN_REVIEW_RESULT_SCHEMA),
        )
        if source_schema == LEGACY_PLUGIN_REVIEW_RESULT_SCHEMA:
            review_package = raw.get("package")
            observations = raw.get("review_observations", [])
            evidence = raw.get("items", [])
            challengers = raw.get("challengers", [])
        else:
            review_package = raw.get("review_package")
            observations = raw.get("observations", [])
            evidence = raw.get("evidence", [])
            challengers = raw.get("challenger_proposals", [])
        if not isinstance(evidence, (list, tuple)):
            raise ContractDecodeError("invalid_field:plugin_result.evidence")
        error = raw.get("error")
        return cls(
            plugin_id=_string(raw.get("plugin_id"), name="plugin_result.plugin_id"),
            status=_string(raw.get("status"), name="plugin_result.status"),
            review_package=(
                StructuredReviewPackage.from_dict(review_package)
                if review_package is not None
                else None
            ),
            observations=_dicts(observations, name="plugin_result.observations"),
            evidence=tuple(ReviewEvidence.from_dict(item) for item in evidence),
            challenger_proposals=_dicts(
                challengers, name="plugin_result.challenger_proposals"
            ),
            error=ReviewErrorMetadata.from_dict(error) if error is not None else None,
            champion_mutated=bool(raw.get("champion_mutated", False)),
            core_rules_mutated=bool(raw.get("core_rules_mutated", False)),
            safety=_safety(raw.get("safety")),
            source_schema=source_schema,
        )
