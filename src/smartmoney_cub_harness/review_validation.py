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


def _is_attachment_field(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
    if any(
        marker in normalized
        for marker in ("attachment", "screenshot", "image_data", "file_data")
    ):
        return True
    tokens = set(normalized.split("_"))
    original_file_tokens = {"csv", "file", "document", "image", "pdf"}
    return "original" in tokens and bool(tokens & original_file_tokens)


def _is_alias(value: object, *, kind: str) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"{kind}-[0-9a-f]{{8}}", value) is not None


def _is_known_alias(value: object) -> bool:
    """Recognize typed aliases wherever they appear, including nested lists."""
    return isinstance(value, str) and re.fullmatch(
        r"(?:symbol|portfolio|subject)-[0-9a-f]{8}", value
    ) is not None


def _contains_unaliased_symbol_code(value: str) -> bool:
    """Scan free text without mistaking a typed alias suffix for a code."""
    without_aliases = re.sub(r"(?:symbol|portfolio|subject)-[0-9a-f]{8}", "", value)
    return SYMBOL_CODE_RE.search(without_aliases) is not None


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
                if _is_attachment_field(key_text):
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
                if lowered in SYMBOL_KEYS and not _is_alias(value, kind="symbol"):
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_IDENTIFIER_VALUE,
                            "Symbols must use a redacted alias.",
                            child_path,
                        )
                    )
                if lowered in PORTFOLIO_KEYS and not _is_alias(value, kind="portfolio"):
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_IDENTIFIER_VALUE,
                            "Portfolio identifiers must use a redacted alias.",
                            child_path,
                        )
                    )
                # A valid pseudonymous identifier is already fully validated
                # by its typed field rule. Do not re-scan its hash suffix as
                # free text: an HMAC alias may legitimately contain six
                # consecutive decimal characters.
                if (
                    lowered in SYMBOL_KEYS and _is_alias(value, kind="symbol")
                ) or (
                    lowered in PORTFOLIO_KEYS and _is_alias(value, kind="portfolio")
                ):
                    continue
                is_exact_band = _matches_redaction_key(
                    key_text, EXACT_QUANTITY_KEYS
                ) or _matches_redaction_key(key_text, EXACT_AMOUNT_KEYS)
                if is_exact_band and not _is_band(value):
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_EXACT_VALUE,
                            "Exact quantities and amounts must be coarsened to bands.",
                            child_path,
                        )
                    )
                if is_exact_band:
                    continue
                is_exact_time = _matches_redaction_key(key_text, EXACT_TIME_KEYS)
                if is_exact_time and not _is_time_bucket(value):
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_EXACT_VALUE,
                            "Exact timestamps must be coarsened to session buckets.",
                            child_path,
                        )
                    )
                if is_exact_time:
                    continue
                is_exact_date = lowered in DATE_KEYS
                if is_exact_date and not _is_date_bucket(value):
                    errors.append(
                        _error(
                            ReviewErrorCode.REDACTION_EXACT_VALUE,
                            "Exact dates must be coarsened to month buckets.",
                            child_path,
                        )
                    )
                if is_exact_date:
                    continue
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
            if not _is_known_alias(node) and _contains_unaliased_symbol_code(node):
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
    guard_fields = {"candidate_role", "champion_mutated", "core_rules_mutated"}
    mutation_fragments = (
        "promot",
        "champion",
        "mutat",
        "core_rule",
        "target_role",
        "target_status",
        "rule_status",
    )

    def has_mutation_key(key: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
        return any(fragment in normalized for fragment in mutation_fragments)

    def is_validated_guard(key: object, value: object) -> bool:
        return isinstance(key, str) and (
            (key == "candidate_role" and value == "challenger")
            or (key in guard_fields - {"candidate_role"} and value is False)
        )

    def find_indicator(node: object, path: str, *, top_level: bool = False) -> str | None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                field_name = str(key)
                child_path = f"{path}.{field_name}" if path else field_name
                if top_level and is_validated_guard(key, value):
                    continue
                if has_mutation_key(field_name):
                    return child_path
                indicator_path = find_indicator(value, child_path)
                if indicator_path is not None:
                    return indicator_path
            return None
        if isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                indicator_path = find_indicator(item, f"{path}[{index}]")
                if indicator_path is not None:
                    return indicator_path
            return None
        # Values use exact role matching; explanatory prose is not a mutation key.
        if isinstance(node, str) and node.strip().lower() == "champion":
            return path
        return None

    indicator_path = find_indicator(payload, "", top_level=True)
    if indicator_path is not None:
        return _result(
            [
                _error(
                    ReviewErrorCode.CHALLENGER_ONLY_MUTATION,
                    "Unsupported promotion or mutation field in challenger proposal.",
                    indicator_path,
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
    effective_decision_time = decision_time
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
        effective_decision_time = package.scope.decision_time
        scope_dt = _aware_timestamp(package.scope.decision_time)
        caller_dt = _aware_timestamp(decision_time)
        envelope_dt = _aware_timestamp(package.envelope.scope.decision_time)
        if scope_dt is None:
            errors.append(
                _error(
                    ReviewErrorCode.INVALID_DECISION_TIME,
                    "Review package scope decision_time must be a timezone-aware ISO timestamp.",
                    "review_package.scope.decision_time",
                )
            )
        else:
            if caller_dt != scope_dt:
                errors.append(
                    _error(
                        ReviewErrorCode.DECISION_TIME_MISMATCH,
                        "Caller decision_time must match the review package scope.",
                        "decision_time",
                    )
                )
            if envelope_dt != scope_dt:
                errors.append(
                    _error(
                        ReviewErrorCode.DECISION_TIME_MISMATCH,
                        "Envelope scope decision_time must match the review package scope.",
                        "review_package.envelope.scope.decision_time",
                    )
                )
        errors.extend(validate_redacted_payload(package.envelope.payload).errors)
        observations.extend(package.observations)
        evidence.extend(package.evidence)
        challengers.extend(package.challenger_proposals)

    for observation in observations:
        errors.extend(
            validate_observation(
                observation,
                decision_time=effective_decision_time,
            ).errors
        )
    for item in evidence:
        errors.extend(
            validate_source_time(
                decision_time=effective_decision_time,
                data_source=item.data_source,
                available_at=item.available_at,
                data_quality_flag=item.data_quality_flag,
            ).errors
        )
    for proposal in challengers:
        errors.extend(validate_challenger_only_mutation(proposal).errors)
    return _result(errors)
