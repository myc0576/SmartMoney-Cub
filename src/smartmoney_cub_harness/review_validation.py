from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from smartmoney_cub_harness.redaction import (
    DATE_KEYS,
    EXACT_AMOUNT_KEYS,
    EXACT_QUANTITY_KEYS,
    EXACT_TIME_KEYS,
    IDENTIFIER_KEYS,
    PORTFOLIO_KEYS,
    SYMBOL_CODE_RE,
    SYMBOL_KEYS,
    scan_for_attachments,
)
from smartmoney_cub_harness.review_contracts import (
    ContractDecodeError,
    PluginReviewResult,
    ReviewErrorCode,
    ReviewErrorMetadata,
)
from smartmoney_cub_harness.safety import REDACTED, looks_sensitive_key, redact_string
from smartmoney_cub_harness.schemas import (
    REQUIRED_ALERT_DECISION_FIELDS,
    SAFETY_DECLARATION,
    VALID_ACTION_LABELS,
    VALID_DATA_QUALITY_FLAGS,
)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[ReviewErrorMetadata, ...]
    safety: str = SAFETY_DECLARATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [error.to_dict() for error in self.errors],
            "safety": self.safety,
        }


def _result(errors: list[ReviewErrorMetadata]) -> ValidationResult:
    return ValidationResult(ok=not errors, errors=tuple(errors))


def _error(code: str, message: str, field: str | None = None) -> ReviewErrorMetadata:
    return ReviewErrorMetadata(code=code, message=message, field=field)


def _aware_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _matches_redaction_key(key: str, candidates: tuple[str, ...]) -> bool:
    lowered = key.lower()
    return any(
        lowered == candidate or lowered.endswith(f"_{candidate}") for candidate in candidates
    )


def _is_band(value: object) -> bool:
    return isinstance(value, str) and (
        value in {"0", "unknown"} or re.fullmatch(r"\d+(?:\.\d+)?-\d+(?:\.\d+)?", value) is not None
    )


def _is_time_bucket(value: object) -> bool:
    return isinstance(value, str) and (
        value == "unknown" or re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", value) is not None
    )


def _is_date_bucket(value: object) -> bool:
    return isinstance(value, str) and (
        value == "unknown" or re.fullmatch(r"\d{4}-\d{2}", value) is not None
    )


def validate_redacted_payload(payload: object) -> ValidationResult:
    errors: list[ReviewErrorMetadata] = []
    if not isinstance(payload, Mapping):
        return _result(
            [
                _error(
                    ReviewErrorCode.REDACTION_SENSITIVE_VALUE,
                    "Redacted payload must be an object.",
                    "payload",
                )
            ]
        )

    for path in scan_for_attachments(payload):
        errors.append(
            _error(
                ReviewErrorCode.REDACTION_ATTACHMENT,
                "Attachments and embedded file material must not leave the local boundary.",
                path,
            )
        )

    def walk(node: object, path: str = "") -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                lowered = key_text.lower()
                attachment_markers = ("attachment", "screenshot", "image_data", "file_data")
                if any(marker in lowered for marker in attachment_markers):
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_ATTACHMENT,
                            "Attachment fields must not enter a redacted review envelope.",
                            child_path,
                        )
                    )
                if looks_sensitive_key(key_text) and value != REDACTED:
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_SENSITIVE_VALUE,
                            "Sensitive keyed values must be redacted.",
                            child_path,
                        )
                    )
                if lowered in IDENTIFIER_KEYS and isinstance(value, str):
                    if value != REDACTED and not value.startswith("subject-"):
                        errors.append(
                            _error(
                                ReviewErrorCode.REDACTION_IDENTIFIER_VALUE,
                                "Direct identifiers must be removed or aliased.",
                                child_path,
                            )
                        )
                if lowered in SYMBOL_KEYS and isinstance(value, str):
                    if not value.startswith("symbol-"):
                        errors.append(
                            _error(
                                ReviewErrorCode.REDACTION_IDENTIFIER_VALUE,
                                "Symbols must use a redacted alias.",
                                child_path,
                            )
                        )
                if lowered in PORTFOLIO_KEYS and isinstance(value, str):
                    if not value.startswith("portfolio-"):
                        errors.append(
                            _error(
                                ReviewErrorCode.REDACTION_IDENTIFIER_VALUE,
                                "Portfolio identifiers must use a redacted alias.",
                                child_path,
                            )
                        )
                if (
                    _matches_redaction_key(key_text, EXACT_QUANTITY_KEYS)
                    or _matches_redaction_key(key_text, EXACT_AMOUNT_KEYS)
                ) and not _is_band(value):
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_EXACT_VALUE,
                            "Exact quantities and amounts must be coarsened to bands.",
                            child_path,
                        )
                    )
                if _matches_redaction_key(key_text, EXACT_TIME_KEYS) and not _is_time_bucket(value):
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_EXACT_VALUE,
                            "Exact timestamps must be coarsened to session buckets.",
                            child_path,
                        )
                    )
                if lowered in DATE_KEYS and not _is_date_bucket(value):
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_EXACT_VALUE,
                            "Exact dates must be coarsened to month buckets.",
                            child_path,
                        )
                    )
                walk(value, child_path)
            return
        if isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")
            return
        if isinstance(node, str):
            if redact_string(node) != node:
                errors.append(
                    _error(
                        ReviewErrorCode.REDACTION_SENSITIVE_VALUE,
                        "Free text still contains sensitive material.",
                        path or "payload",
                    )
                )
            if SYMBOL_CODE_RE.search(node):
                errors.append(
                    _error(
                        ReviewErrorCode.REDACTION_IDENTIFIER_VALUE,
                        "Free text still contains an unaliased symbol.",
                        path or "payload",
                    )
                )

    walk(payload)
    return _result(errors)


def validate_source_time(
    *,
    decision_time: object,
    data_source: object,
    available_at: object,
    data_quality_flag: object,
) -> ValidationResult:
    errors: list[ReviewErrorMetadata] = []
    if not isinstance(data_source, str) or not data_source.strip():
        errors.append(
            _error(
                ReviewErrorCode.MISSING_DATA_SOURCE,
                "A non-empty data source is required.",
                "data_source",
            )
        )
    decision_dt = _aware_timestamp(decision_time)
    if decision_dt is None:
        errors.append(
            _error(
                ReviewErrorCode.INVALID_DECISION_TIME,
                "decision_time must be a timezone-aware ISO timestamp.",
                "decision_time",
            )
        )
    available_dt = _aware_timestamp(available_at)
    if available_dt is None:
        errors.append(
            _error(
                ReviewErrorCode.INVALID_AVAILABLE_AT,
                "available_at must be a timezone-aware ISO timestamp.",
                "available_at",
            )
        )
    if data_quality_flag not in VALID_DATA_QUALITY_FLAGS:
        errors.append(
            _error(
                ReviewErrorCode.INVALID_DATA_QUALITY,
                "data_quality_flag is not supported.",
                "data_quality_flag",
            )
        )
    if decision_dt is not None and available_dt is not None and available_dt > decision_dt:
        errors.append(
            _error(
                ReviewErrorCode.FUTURE_LEAKAGE,
                "available_at must not be later than decision_time.",
                "available_at",
            )
        )
    return _result(errors)


def validate_observation(
    observation: object,
    *,
    decision_time: object,
) -> ValidationResult:
    if not isinstance(observation, Mapping):
        return _result(
            [
                _error(
                    ReviewErrorCode.OBSERVATION_MISSING_FIELD,
                    "Observation must be an object.",
                    "observation",
                )
            ]
        )
    action_label = observation.get("action_label")
    if action_label not in VALID_ACTION_LABELS:
        return _result(
            [
                _error(
                    ReviewErrorCode.INVALID_ACTION_LABEL,
                    "action_label is not supported.",
                    "action_label",
                )
            ]
        )
    if action_label == "SILENT":
        return _result([])

    missing: list[ReviewErrorMetadata] = []
    for field_name in REQUIRED_ALERT_DECISION_FIELDS:
        value = observation.get(field_name)
        absent = field_name not in observation or value is None
        if field_name in ("time_stop", "data_source", "available_at", "data_quality_flag"):
            absent = absent or not isinstance(value, str) or not value.strip()
        if field_name == "give_up_conditions":
            absent = not isinstance(value, (list, tuple)) or not value
        if absent:
            missing.append(
                _error(
                    ReviewErrorCode.OBSERVATION_MISSING_FIELD,
                    f"Non-silent observation requires {field_name}.",
                    field_name,
                )
            )
    if missing:
        return _result(missing)
    return validate_source_time(
        decision_time=decision_time,
        data_source=observation.get("data_source"),
        available_at=observation.get("available_at"),
        data_quality_flag=observation.get("data_quality_flag"),
    )


def validate_challenger_only_mutation(payload: object) -> ValidationResult:
    if not isinstance(payload, Mapping):
        return _result(
            [
                _error(
                    ReviewErrorCode.CHALLENGER_ONLY_MUTATION,
                    "Rule proposal must be an object.",
                    "candidate_role",
                )
            ]
        )
    if (
        payload.get("candidate_role") != "challenger"
        or payload.get("champion_mutated", False) is not False
        or payload.get("core_rules_mutated", False) is not False
    ):
        return _result(
            [
                _error(
                    ReviewErrorCode.CHALLENGER_ONLY_MUTATION,
                    "Review output may propose a challenger and must not mutate "
                    "champion or core rules.",
                    "candidate_role",
                )
            ]
        )
    return _result([])


def validate_plugin_result(
    result: PluginReviewResult | Mapping[str, Any],
    *,
    decision_time: object,
) -> ValidationResult:
    if isinstance(result, Mapping):
        try:
            result = PluginReviewResult.from_dict(result)
        except ContractDecodeError as exc:
            return _result(
                [
                    _error(
                        ReviewErrorCode.CONTRACT_DECODE,
                        str(exc),
                        "plugin_result",
                    )
                ]
            )

    errors: list[ReviewErrorMetadata] = []
    if result.safety != SAFETY_DECLARATION:
        errors.append(
            _error(
                ReviewErrorCode.INVALID_SAFETY,
                "Plugin result safety declaration is missing or invalid.",
                "safety",
            )
        )
    if result.champion_mutated or result.core_rules_mutated:
        errors.extend(
            validate_challenger_only_mutation(
                {
                    "candidate_role": "challenger",
                    "champion_mutated": result.champion_mutated,
                    "core_rules_mutated": result.core_rules_mutated,
                }
            ).errors
        )

    observations = list(result.observations)
    evidence = list(result.evidence)
    challengers = list(result.challenger_proposals)
    if result.review_package is not None:
        package = result.review_package
        errors.extend(validate_redacted_payload(package.envelope.payload).errors)
        observations.extend(package.observations)
        evidence.extend(package.evidence)
        challengers.extend(package.challenger_proposals)

    for observation in observations:
        errors.extend(validate_observation(observation, decision_time=decision_time).errors)
    for item in evidence:
        errors.extend(
            validate_source_time(
                decision_time=decision_time,
                data_source=item.data_source,
                available_at=item.available_at,
                data_quality_flag=item.data_quality_flag,
            ).errors
        )
    for proposal in challengers:
        errors.extend(validate_challenger_only_mutation(proposal).errors)
    return _result(errors)
