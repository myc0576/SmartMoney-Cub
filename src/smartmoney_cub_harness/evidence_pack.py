from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.evaluator import evaluate_decision
from smartmoney_cub_harness.manifest import validate_run_manifest
from smartmoney_cub_harness.registry import promotion_blockers
from smartmoney_cub_harness.safety import is_relative_artifact_path, safety_envelope
from smartmoney_cub_harness.schemas import EVIDENCE_PACK_SCHEMA, EVIDENCE_REPLAY_SCHEMA, SAFETY_DECLARATION

PACK_MANIFEST_NAME = "evidence_pack.json"
PACK_SEAL_NAME = "evidence_pack.sha256"
METRIC_FIELDS = {
    "sample_count",
    "false_alert_rate",
    "missed_opportunity_rate",
    "future_leakage_count",
    "risk_contract_violation_rate",
}
SAMPLE_FIELDS = {
    "sample_id",
    "paths",
    "manifest_validation",
    "evaluation_grade",
    "failed",
    "safety",
}
EVALUATION_GRADES = {
    "missed_opportunity",
    "true_silent",
    "not_evaluated",
    "invalid",
    "false_alert",
    "useful_alert",
}


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _write_frozen(path: Path, payload: dict[str, Any]) -> str:
    frozen = safety_envelope(payload)
    frozen["safety"] = SAFETY_DECLARATION
    content = _canonical_bytes(frozen)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return value


def _stable_sample_id(manifest: dict[str, Any], index: int) -> str:
    run_id = str(manifest.get("run_id") or f"sample-{index + 1}")
    safe = "".join(character if character.isalnum() or character in "-_" else "-" for character in run_id)
    return safe.strip("-") or f"sample-{index + 1}"


def _review_status(failure_count: int, trailing_failures: int, metrics: dict[str, Any]) -> str:
    if trailing_failures >= 3:
        return "blocked"
    if failure_count:
        return "pending_review"
    return "challenger" if promotion_blockers(metrics) else "ready_for_review"


def _write_replay_report(
    root: Path, report: dict[str, Any], *, persist: bool = True
) -> dict[str, Any]:
    if persist:
        # The dispatcher also writes failures before a format can be trusted.
        # Use the same checked atomic replacement for every version, including
        # malformed packs, so an existing hard link never becomes a write target.
        from smartmoney_cub_harness.onchain_evidence import _write_report

        try:
            _write_report(root, report)
        except (OSError, ValueError):
            report["evidence_status"] = "pending_review"
            report["result_mismatches"].append("report_write_failed")
            report["promotion_gate"]["eligible_for_human_review"] = False
    return report


def _pending_replay(root: Path, reason: str, *, persist: bool = True) -> dict[str, Any]:
    return _write_replay_report(
        root,
        safety_envelope(
            {
                "schema": EVIDENCE_REPLAY_SCHEMA,
                "evidence_status": "pending_review",
                "hash_mismatches": [],
                "result_mismatches": [reason],
                "metrics": {
                    "sample_count": 0,
                    "false_alert_rate": 0.0,
                    "missed_opportunity_rate": 0.0,
                    "future_leakage_count": 0,
                    "risk_contract_violation_rate": 0.0,
                },
                "failure_count": 0,
                "trailing_consecutive_failure_count": 0,
                "samples": [],
                "promotion_gate": {
                    "eligible_for_human_review": False,
                    "human_confirmation_required": True,
                    "champion_mutated": False,
                    "core_rules_mutated": False,
                },
            }
        ),
        persist=persist,
    )


def _pack_validation_errors(pack: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_fields = {
        "schema",
        "horizon",
        "rule_candidate_path",
        "samples",
        "hashes",
        "metrics",
        "failure_count",
        "trailing_consecutive_failure_count",
        "review_status",
        "promotion_gate",
        "safety",
    }
    if set(pack) != required_fields:
        errors.append("fields")
    if pack.get("schema") != EVIDENCE_PACK_SCHEMA:
        errors.append("schema")
    if pack.get("safety") != SAFETY_DECLARATION:
        errors.append("safety")
    if pack.get("horizon") not in {"d1", "d3"}:
        errors.append("horizon")

    rule_path = pack.get("rule_candidate_path")
    if not is_relative_artifact_path(rule_path):
        errors.append("rule_candidate_path")

    samples = pack.get("samples")
    hashes = pack.get("hashes")
    expected_hash_paths: set[str] = {rule_path} if isinstance(rule_path, str) else set()
    sample_ids: set[str] = set()
    if not isinstance(samples, list) or not samples:
        errors.append("samples")
        samples = []
    for sample in samples:
        if not isinstance(sample, dict):
            errors.append("sample")
            continue
        if set(sample) != SAMPLE_FIELDS:
            errors.append("sample_fields")
        sample_id = sample.get("sample_id")
        if (
            not isinstance(sample_id, str)
            or not sample_id
            or sample_id in sample_ids
            or any(not (character.isalnum() or character in "-_") for character in sample_id)
        ):
            errors.append("sample_id")
            continue
        sample_ids.add(sample_id)
        if sample.get("safety") != SAFETY_DECLARATION or not isinstance(sample.get("failed"), bool):
            errors.append("sample_contract")
        if sample.get("evaluation_grade") not in EVALUATION_GRADES:
            errors.append("evaluation_grade")
        manifest_validation = sample.get("manifest_validation")
        if not (
            isinstance(manifest_validation, dict)
            and set(manifest_validation) == {"ok", "errors", "warnings", "source_count", "safety"}
            and isinstance(manifest_validation.get("ok"), bool)
            and isinstance(manifest_validation.get("errors"), list)
            and all(isinstance(item, str) for item in manifest_validation.get("errors", []))
            and isinstance(manifest_validation.get("warnings"), list)
            and all(isinstance(item, str) for item in manifest_validation.get("warnings", []))
            and isinstance(manifest_validation.get("source_count"), int)
            and not isinstance(manifest_validation.get("source_count"), bool)
            and manifest_validation.get("source_count", -1) >= 0
            and manifest_validation.get("safety") == SAFETY_DECLARATION
        ):
            errors.append("manifest_validation")
        paths = sample.get("paths")
        if not isinstance(paths, dict) or set(paths) != {"manifest", "decision", "outcome", "evaluation"}:
            errors.append("sample_paths")
            continue
        prefix = f"samples/{sample_id}/"
        for path in paths.values():
            if not is_relative_artifact_path(path) or not str(path).startswith(prefix):
                errors.append("sample_path")
            elif isinstance(path, str):
                expected_hash_paths.add(path)

    if not isinstance(hashes, dict):
        errors.append("hashes")
        hashes = {}
    for path, digest in hashes.items():
        if not is_relative_artifact_path(path):
            errors.append("hash_path")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            errors.append("hash_digest")
    if set(hashes) != expected_hash_paths:
        errors.append("hash_inventory_mismatch")

    metrics = pack.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != METRIC_FIELDS:
        errors.append("metrics")
    else:
        sample_count = metrics.get("sample_count")
        if (
            not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count != len(samples)
        ):
            errors.append("sample_count")
        future_leakage_count = metrics.get("future_leakage_count")
        if (
            not isinstance(future_leakage_count, int)
            or isinstance(future_leakage_count, bool)
            or future_leakage_count < 0
        ):
            errors.append("metrics")
        for field in ("false_alert_rate", "missed_opportunity_rate", "risk_contract_violation_rate"):
            value = metrics.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
                errors.append("metrics")
    for field in ("failure_count", "trailing_consecutive_failure_count"):
        value = pack.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(field)
    if pack.get("review_status") not in {"challenger", "ready_for_review", "pending_review", "blocked"}:
        errors.append("review_status")
    gate = pack.get("promotion_gate")
    if not (
        isinstance(gate, dict)
        and set(gate)
        == {
            "eligible_for_human_review",
            "human_confirmation_required",
            "champion_mutated",
            "core_rules_mutated",
        }
        and isinstance(gate.get("eligible_for_human_review"), bool)
        and gate.get("human_confirmation_required") is True
        and gate.get("champion_mutated") is False
        and gate.get("core_rules_mutated") is False
    ):
        errors.append("promotion_gate")
    return list(dict.fromkeys(errors))


def build_evidence_pack(
    output_dir: str | Path,
    sample_dirs: list[str | Path],
    rule_candidate: dict[str, Any],
    horizon: str = "d1",
) -> dict[str, Any]:
    if not sample_dirs:
        raise ValueError("evidence pack requires at least one sample")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    sample_records: list[dict[str, Any]] = []
    score_totals = {"false_alert": 0, "missed_opportunity": 0, "risk_contract_violation": 0}
    future_leakage_count = 0
    failures: list[bool] = []

    rule_path = "rule_candidate.json"
    hashes[rule_path] = _write_frozen(output_path / rule_path, rule_candidate)

    used_ids: set[str] = set()
    for index, source_dir in enumerate(sample_dirs):
        source = Path(source_dir)
        manifest = _read_json(source / "run_manifest.json")
        decision = _read_json(source / "decision.json")
        outcome = _read_json(source / f"outcome_{horizon}.json")
        manifest_validation = validate_run_manifest(manifest)
        evaluation = evaluate_decision(decision, outcome)
        base_sample_id = _stable_sample_id(manifest, index)
        sample_id = base_sample_id
        suffix = index + 1
        while sample_id in used_ids:
            sample_id = f"{base_sample_id}-{suffix}"
            suffix += 1
        used_ids.add(sample_id)

        prefix = f"samples/{sample_id}"
        paths = {
            "manifest": f"{prefix}/run_manifest.json",
            "decision": f"{prefix}/decision.json",
            "outcome": f"{prefix}/outcome_{horizon}.json",
            "evaluation": f"{prefix}/evaluation.json",
        }
        frozen_payloads = {
            "manifest": manifest,
            "decision": decision,
            "outcome": outcome,
            "evaluation": evaluation,
        }
        for name, relative_path in paths.items():
            hashes[relative_path] = _write_frozen(output_path / relative_path, frozen_payloads[name])

        scores = evaluation.get("scores") or {}
        for score_name in score_totals:
            score_totals[score_name] += int(scores.get(score_name) or 0)
        future_leakage_count += sum(
            1 for error in manifest_validation.get("errors", []) if str(error).startswith("future_leakage:")
        )
        failed = not manifest_validation.get("ok") or evaluation.get("grade") in {"invalid", "not_evaluated"}
        failures.append(bool(failed))
        sample_records.append(
            safety_envelope(
                {
                    "sample_id": sample_id,
                    "paths": paths,
                    "manifest_validation": manifest_validation,
                    "evaluation_grade": evaluation.get("grade"),
                    "failed": bool(failed),
                }
            )
        )

    sample_count = len(sample_records)
    metrics = {
        "sample_count": sample_count,
        "false_alert_rate": score_totals["false_alert"] / sample_count,
        "missed_opportunity_rate": score_totals["missed_opportunity"] / sample_count,
        "future_leakage_count": future_leakage_count,
        "risk_contract_violation_rate": score_totals["risk_contract_violation"] / sample_count,
    }
    trailing_failures = 0
    for failed in reversed(failures):
        if not failed:
            break
        trailing_failures += 1
    failure_count = sum(failures)
    review_status = _review_status(failure_count, trailing_failures, metrics)
    pack = safety_envelope(
        {
            "schema": EVIDENCE_PACK_SCHEMA,
            "horizon": horizon,
            "rule_candidate_path": rule_path,
            "samples": sample_records,
            "hashes": hashes,
            "metrics": metrics,
            "failure_count": failure_count,
            "trailing_consecutive_failure_count": trailing_failures,
            "review_status": review_status,
            "promotion_gate": {
                "eligible_for_human_review": review_status == "ready_for_review",
                "human_confirmation_required": True,
                "champion_mutated": False,
                "core_rules_mutated": False,
            },
        }
    )
    manifest_bytes = _canonical_bytes(pack)
    (output_path / PACK_MANIFEST_NAME).write_bytes(manifest_bytes)
    (output_path / PACK_SEAL_NAME).write_text(
        hashlib.sha256(manifest_bytes).hexdigest() + "\n", encoding="ascii"
    )
    return pack


def replay_evidence_pack(pack_dir: str | Path) -> dict[str, Any]:
    # Dispatch only a sealed, strictly parsed version. The original price-based
    # v1 evaluator remains below; on-chain inputs never enter that evaluator.
    from smartmoney_cub_harness.onchain_evidence import (
        replay_onchain_evidence_pack,
        safe_pack_path,
        strict_json_loads,
    )

    root = Path(pack_dir)
    try:
        manifest_path = safe_pack_path(root, PACK_MANIFEST_NAME)
        seal_path = safe_pack_path(root, PACK_SEAL_NAME)
        safe_pack_path(root, "replay_report.json")
    except (OSError, ValueError):
        return _pending_replay(root, "invalid_pack:unsafe_path", persist=False)
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError:
        return _pending_replay(root, "manifest_seal_missing")
    try:
        seal = seal_path.read_text(encoding="ascii").strip()
    except OSError:
        return _pending_replay(root, "manifest_seal_missing")
    except UnicodeDecodeError:
        return _pending_replay(root, "manifest_seal_malformed")
    if re.fullmatch(r"[0-9a-fA-F]{64}", seal) is None:
        return _pending_replay(root, "manifest_seal_malformed")
    if hashlib.sha256(manifest_bytes).hexdigest() != seal:
        return _pending_replay(root, "manifest_seal_mismatch")
    try:
        pack = strict_json_loads(manifest_bytes)
    except (UnicodeDecodeError, ValueError):
        return _pending_replay(root, "invalid_pack:malformed_json")
    if not isinstance(pack, dict):
        return _pending_replay(root, "invalid_pack:not_an_object")
    if pack.get("schema") == "smartmoney_cub_onchain_evidence_pack.v1":
        return replay_onchain_evidence_pack(root)
    if pack.get("schema") != EVIDENCE_PACK_SCHEMA:
        return _pending_replay(root, "invalid_pack:schema")
    pack_errors = _pack_validation_errors(pack)
    if pack_errors:
        primary = "hash_inventory_mismatch" if "hash_inventory_mismatch" in pack_errors else pack_errors[0]
        return _pending_replay(root, f"invalid_pack:{primary}")
    hash_mismatches: list[str] = []
    result_mismatches: list[str] = []

    for relative_path, expected_hash in (pack.get("hashes") or {}).items():
        artifact = _relative_artifact(root, str(relative_path))
        try:
            actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact.is_file() else None
        except OSError:
            actual_hash = None
        if actual_hash != expected_hash:
            hash_mismatches.append(str(relative_path))

    try:
        rule_candidate = _read_json(_relative_artifact(root, pack["rule_candidate_path"]))
        if rule_candidate.get("safety") != SAFETY_DECLARATION:
            result_mismatches.append("safety:rule_candidate")
    except (OSError, ValueError, json.JSONDecodeError):
        result_mismatches.append("unreadable_rule_candidate")

    score_totals = {"false_alert": 0, "missed_opportunity": 0, "risk_contract_violation": 0}
    future_leakage_count = 0
    failures: list[bool] = []
    base_failures: list[bool] = []
    replayed_samples: list[dict[str, Any]] = []
    for sample in pack.get("samples") or []:
        sample_id = str(sample.get("sample_id") or "unknown")
        paths = sample.get("paths") or {}
        try:
            manifest = _read_json(_relative_artifact(root, str(paths["manifest"])))
            decision = _read_json(_relative_artifact(root, str(paths["decision"])))
            outcome = _read_json(_relative_artifact(root, str(paths["outcome"])))
            frozen_evaluation = _read_json(_relative_artifact(root, str(paths["evaluation"])))
            manifest_validation = validate_run_manifest(manifest)
            evaluation = evaluate_decision(decision, outcome)
            mismatched = False
            for artifact_name, artifact_payload in (
                ("manifest", manifest),
                ("decision", decision),
                ("outcome", outcome),
                ("evaluation", frozen_evaluation),
            ):
                if artifact_payload.get("safety") != SAFETY_DECLARATION:
                    result_mismatches.append(f"safety:{sample_id}:{artifact_name}")
                    mismatched = True
            if safety_envelope(evaluation) != frozen_evaluation:
                result_mismatches.append(f"evaluation:{sample_id}")
                mismatched = True
            if manifest_validation != sample.get("manifest_validation"):
                result_mismatches.append(f"manifest_validation:{sample_id}")
                mismatched = True
            if evaluation.get("grade") != sample.get("evaluation_grade"):
                result_mismatches.append(f"evaluation_grade:{sample_id}")
                mismatched = True
            scores = evaluation.get("scores") or {}
            for score_name in score_totals:
                score_totals[score_name] += int(scores.get(score_name) or 0)
            future_leakage_count += sum(
                1 for error in manifest_validation.get("errors", []) if str(error).startswith("future_leakage:")
            )
            base_failed = (
                not manifest_validation.get("ok")
                or evaluation.get("grade") in {"invalid", "not_evaluated"}
            )
            if sample.get("failed") is not base_failed:
                result_mismatches.append(f"failed:{sample_id}")
                mismatched = True
            failed = base_failed or mismatched or any(
                str(path).startswith(f"samples/{sample_id}/") for path in hash_mismatches
            )
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            result_mismatches.append(f"unreadable_sample:{sample_id}")
            base_failed = True
            failed = True
        base_failures.append(bool(base_failed))
        failures.append(bool(failed))
        replayed_samples.append(safety_envelope({"sample_id": sample_id, "failed": bool(failed)}))

    sample_count = len(replayed_samples)
    if sample_count == 0:
        raise ValueError("evidence pack requires at least one sample")
    metrics = {
        "sample_count": sample_count,
        "false_alert_rate": score_totals["false_alert"] / sample_count,
        "missed_opportunity_rate": score_totals["missed_opportunity"] / sample_count,
        "future_leakage_count": future_leakage_count,
        "risk_contract_violation_rate": score_totals["risk_contract_violation"] / sample_count,
    }
    if metrics != pack.get("metrics"):
        result_mismatches.append("metrics")
    trailing_failures = 0
    for failed in reversed(failures):
        if not failed:
            break
        trailing_failures += 1
    failure_count = sum(failures)
    base_trailing_failures = 0
    for failed in reversed(base_failures):
        if not failed:
            break
        base_trailing_failures += 1
    base_failure_count = sum(base_failures)
    if base_failure_count != pack.get("failure_count"):
        result_mismatches.append("failure_count")
    if base_trailing_failures != pack.get("trailing_consecutive_failure_count"):
        result_mismatches.append("trailing_consecutive_failure_count")
    expected_review_status = _review_status(base_failure_count, base_trailing_failures, metrics)
    if pack.get("review_status") != expected_review_status:
        result_mismatches.append("review_status")
    expected_eligibility = expected_review_status == "ready_for_review"
    if pack.get("promotion_gate", {}).get("eligible_for_human_review") is not expected_eligibility:
        result_mismatches.append("promotion_gate.eligible_for_human_review")

    mismatched = bool(hash_mismatches or result_mismatches)
    if trailing_failures >= 3:
        evidence_status = "blocked"
    elif failure_count or mismatched:
        evidence_status = "pending_review"
    else:
        evidence_status = "verified"
    report = safety_envelope(
        {
            "schema": EVIDENCE_REPLAY_SCHEMA,
            "evidence_status": evidence_status,
            "hash_mismatches": hash_mismatches,
            "result_mismatches": result_mismatches,
            "metrics": metrics,
            "failure_count": failure_count,
            "trailing_consecutive_failure_count": trailing_failures,
            "samples": replayed_samples,
            "promotion_gate": {
                "eligible_for_human_review": (
                    evidence_status == "verified"
                    and failure_count == 0
                    and not promotion_blockers(metrics)
                ),
                "human_confirmation_required": True,
                "champion_mutated": False,
                "core_rules_mutated": False,
            },
        }
    )
    return _write_replay_report(root, report)


def _relative_artifact(root: Path, relative_path: str) -> Path:
    if not is_relative_artifact_path(relative_path):
        raise ValueError("evidence artifacts must use relative paths")
    return root / Path(relative_path)
