from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from smartmoney_cub_harness.plugins.types import ResultKind
from smartmoney_cub_harness.safety import redact
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

EVIDENCE_ENVELOPE_SCHEMA = "smartmoney_cub_plugin_evidence_envelope.v1"

REQUIRED_ENVELOPE_FIELDS = (
    "schema",
    "plugin_id",
    "plugin_version",
    "source_ref",
    "capability",
    "result_kind",
    "input_sha256",
    "output_sha256",
    "decision_time",
    "available_at",
    "data_source",
    "data_quality",
    "network_used",
    "model_used",
    "permission",
    "safety",
)


class EvidenceEnvelopeError(ValueError):
    """Raised when a plugin output cannot be wrapped into trustworthy evidence."""


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_evidence_envelope(
    *,
    plugin_id: str,
    plugin_version: str,
    source_ref: str,
    capability: str,
    result_kind: str,
    request: dict[str, Any],
    output: Any,
    decision_time: str | None,
    available_at: str,
    data_source: str,
    data_quality: str,
    network_used: bool = False,
    model_used: bool = False,
    permission: dict[str, Any] | None = None,
    error: str | None = None,
    replay: dict[str, Any] | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap any plugin output into a uniform, auditable evidence record.

    Time consistency is enforced here: an output whose data became available only
    after the decision time is blocked instead of being treated as known-then.
    """
    if result_kind not in ResultKind.ALL:
        raise EvidenceEnvelopeError(f"unknown result_kind: {result_kind}")
    if not data_quality:
        raise EvidenceEnvelopeError("data_quality is required")

    available_dt = _parse_timestamp(available_at)
    if available_dt is None:
        raise EvidenceEnvelopeError("available_at must be a timezone-aware ISO timestamp")

    decision_dt = _parse_timestamp(decision_time) if decision_time else None
    if decision_time and decision_dt is None:
        raise EvidenceEnvelopeError("decision_time must be a timezone-aware ISO timestamp")
    if decision_dt is not None and available_dt > decision_dt:
        raise EvidenceEnvelopeError(
            f"available_at {available_at} is after decision_time {decision_time}: future leakage"
        )

    envelope: dict[str, Any] = {
        "schema": EVIDENCE_ENVELOPE_SCHEMA,
        "plugin_id": plugin_id,
        "plugin_version": plugin_version,
        "source_ref": source_ref,
        "capability": capability,
        "result_kind": result_kind,
        "review_only": result_kind in (ResultKind.MODEL_OPINION, ResultKind.REVIEW_OBSERVATION),
        "input_sha256": _canonical_sha256(redact(request)),
        "output_sha256": _canonical_sha256(redact(output)) if error is None else None,
        "started_at": started_at or _now_iso(),
        "finished_at": finished_at or _now_iso(),
        "decision_time": decision_time,
        "available_at": available_at,
        "data_source": data_source,
        "data_quality": data_quality,
        "network_used": bool(network_used),
        "model_used": bool(model_used),
        "error": error,
        "permission": permission
        or {
            "order": False,
            "cancel": False,
            "trade": False,
            "account_mutation": False,
            "broker_access": False,
            "enforcement": "declarative",
            "verified": False,
        },
        "replay": replay or {},
        "champion_mutated": False,
        "core_rules_mutated": False,
        "output": redact(output) if error is None else None,
        "safety": SAFETY_DECLARATION,
    }
    if extra:
        for key, value in extra.items():
            envelope.setdefault(key, redact(value))
    return envelope


def validate_evidence_envelope(payload: Any) -> dict[str, Any]:
    """Validate a stored envelope without raising."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["envelope_not_object"], "safety": SAFETY_DECLARATION}

    for field_name in REQUIRED_ENVELOPE_FIELDS:
        if field_name not in payload:
            errors.append(f"missing_{field_name}")

    if payload.get("schema") not in (None, EVIDENCE_ENVELOPE_SCHEMA):
        errors.append("invalid_envelope_schema")
    if payload.get("safety") != SAFETY_DECLARATION:
        errors.append("missing_or_invalid_safety_declaration")
    if payload.get("result_kind") not in (None, *ResultKind.ALL):
        errors.append("invalid_result_kind")

    for field_name in ("input_sha256", "output_sha256"):
        value = payload.get(field_name)
        if value is not None and (not isinstance(value, str) or len(value) != 64):
            errors.append(f"invalid_{field_name}")

    available_dt = _parse_timestamp(payload.get("available_at"))
    if available_dt is None:
        errors.append("invalid_available_at")
    decision_dt = _parse_timestamp(payload.get("decision_time"))
    if payload.get("decision_time") and decision_dt is None:
        errors.append("invalid_decision_time")
    if available_dt is not None and decision_dt is not None and available_dt > decision_dt:
        errors.append("future_leakage")

    permission = payload.get("permission")
    if isinstance(permission, dict):
        for forbidden in ("order", "cancel", "trade", "account_mutation", "broker_access"):
            if permission.get(forbidden):
                errors.append(f"forbidden_permission:{forbidden}")

    if payload.get("champion_mutated"):
        errors.append("plugin_output_must_not_mutate_champion")

    return {"ok": not errors, "errors": errors, "safety": SAFETY_DECLARATION}
