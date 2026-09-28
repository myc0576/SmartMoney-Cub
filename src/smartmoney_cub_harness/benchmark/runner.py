from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from smartmoney_cub_harness.benchmark.baseline import baseline_predictions
from smartmoney_cub_harness.benchmark.cases import (
    BENCHMARK_ID,
    TRACK_IDS,
    BenchmarkCase,
    load_track,
)
from smartmoney_cub_harness.benchmark.metrics import (
    CASE_BOOTSTRAP_METHOD,
    CASE_BOOTSTRAP_REPLICATES,
    CASE_BOOTSTRAP_SEED,
    CASE_BOOTSTRAP_UNIT,
    calculate_system_metrics,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

LEGACY_BENCHMARK_RUN_SCHEMA = "smartmoney_cub_benchmark_run.v1"
BENCHMARK_RUN_SCHEMA = "smartmoney_cub_benchmark_run.v2"
BENCHMARK_STATISTICS = {
    "confidence_interval_method": CASE_BOOTSTRAP_METHOD,
    "confidence_interval_unit": CASE_BOOTSTRAP_UNIT,
    "bootstrap": {
        "seed": CASE_BOOTSTRAP_SEED,
        "replicates": CASE_BOOTSTRAP_REPLICATES,
        "stratified_by": "track",
    },
}
TYPESAFE_CHECKPOINT_SCHEMA = "smartmoney_cub_typesafe_checkpoint.v1"
TYPESAFE_MAX_COST_USD = 4.00
TYPESAFE_PUBLIC_CASE_COUNT = 240
TYPESAFE_PUBLIC_ITEM_COUNT = 1020


def _get_git_sha() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown_git_sha"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a diagnostic artifact atomically and without private request data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _checkpoint_payload(
    *,
    selected_tracks: Sequence[str],
    selected_cases: Sequence[BenchmarkCase],
    model_requested: str,
    model_resolved: str | None,
    total_cost: float,
    case_evaluations: Sequence[Mapping[str, Any]],
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Build a checkpoint containing only toy, structured evaluation data."""
    payload: dict[str, Any] = {
        "schema": TYPESAFE_CHECKPOINT_SCHEMA,
        "benchmark_id": BENCHMARK_ID,
        "system_id": "typesafe_direct",
        "tracks": list(selected_tracks),
        "case_ids": [case.case_id for case in selected_cases],
        "model_requested": model_requested,
        "model_resolved": model_resolved,
        "cost_usd": round(float(total_cost), 6),
        "case_evaluations": [dict(record) for record in case_evaluations],
        "status": status,
        "safety": SAFETY_DECLARATION,
    }
    if reason:
        payload["reason"] = reason
    return payload


def _write_checkpoint(
    checkpoint_path: Path | None,
    *,
    selected_tracks: Sequence[str],
    selected_cases: Sequence[BenchmarkCase],
    model_requested: str,
    model_resolved: str | None,
    total_cost: float,
    case_evaluations: Sequence[Mapping[str, Any]],
    status: str,
    reason: str | None = None,
) -> None:
    if checkpoint_path is None:
        return
    _atomic_write_json(
        checkpoint_path,
        _checkpoint_payload(
            selected_tracks=selected_tracks,
            selected_cases=selected_cases,
            model_requested=model_requested,
            model_resolved=model_resolved,
            total_cost=total_cost,
            case_evaluations=case_evaluations,
            status=status,
            reason=reason,
        ),
    )


def _load_checkpoint(
    checkpoint_path: Path,
    *,
    selected_tracks: Sequence[str],
    selected_cases: Sequence[BenchmarkCase],
    model_requested: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], float]:
    """Load and fail closed on a checkpoint for a different benchmark selection."""
    with checkpoint_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("schema") != TYPESAFE_CHECKPOINT_SCHEMA:
        raise ValueError("unsupported TypeSafe checkpoint schema")
    if payload.get("safety") != SAFETY_DECLARATION:
        raise ValueError("TypeSafe checkpoint has an invalid safety declaration")
    expected_case_ids = [case.case_id for case in selected_cases]
    if payload.get("benchmark_id") != BENCHMARK_ID or payload.get("system_id") != "typesafe_direct":
        raise ValueError("TypeSafe checkpoint belongs to a different benchmark system")
    if payload.get("tracks") != list(selected_tracks) or payload.get("case_ids") != expected_case_ids:
        raise ValueError("TypeSafe checkpoint selection does not match this run")
    if payload.get("model_requested") != model_requested:
        raise ValueError("TypeSafe checkpoint model_requested does not match this run")
    if payload.get("status") not in {"incomplete", "completed"}:
        raise ValueError("TypeSafe checkpoint has an invalid status")
    model_resolved = payload.get("model_resolved")
    if model_resolved is not None and (not isinstance(model_resolved, str) or not model_resolved.strip()):
        raise ValueError("TypeSafe checkpoint has an invalid model_resolved")
    if payload.get("status") == "completed" and model_resolved is None:
        raise ValueError("completed TypeSafe checkpoint is missing model_resolved")
    records = payload.get("case_evaluations")
    if not isinstance(records, list):
        raise ValueError("TypeSafe checkpoint case_evaluations must be a list")
    record_map: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("case_id"), str):
            raise ValueError("TypeSafe checkpoint contains a malformed case evaluation")
        case_id = record["case_id"]
        if case_id in record_map:
            raise ValueError("TypeSafe checkpoint contains a duplicate case_id")
        if "request_id" in record or "headers" in record or "api_key" in record:
            raise ValueError("TypeSafe checkpoint contains private request data")
        if case_id not in set(expected_case_ids):
            raise ValueError("TypeSafe checkpoint contains a case outside this run")
        record_map[case_id] = record
    try:
        checkpoint_cost = float(payload.get("cost_usd"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("TypeSafe checkpoint has invalid cost_usd") from exc
    if not math.isfinite(checkpoint_cost) or checkpoint_cost < 0:
        raise ValueError("TypeSafe checkpoint has invalid cost_usd")
    recorded_cost = 0.0
    case_by_id = {case.case_id: case for case in selected_cases}
    for case_id, record in record_map.items():
        validated_preds: list[Any] = []
        validated_targets: list[Any] = []
        validated_confidences: list[float] = []
        validated_latencies: list[float] = []
        validated_costs: list[float] = []
        _append_case_record(
            record,
            case_by_id[case_id],
            validated_preds,
            validated_targets,
            validated_confidences,
            validated_latencies,
            validated_costs,
        )
        recorded_cost += float(record["cost_usd"])
    if not math.isclose(checkpoint_cost, recorded_cost, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("TypeSafe checkpoint cost_usd does not match case records")
    if payload.get("status") == "completed" and len(record_map) != len(selected_cases):
        raise ValueError("completed TypeSafe checkpoint does not contain every selected case")
    return payload, record_map, checkpoint_cost


def _append_case_record(
    record: Mapping[str, Any],
    case: BenchmarkCase,
    preds: list[Any],
    targets: list[Any],
    confidences: list[float],
    latencies: list[float],
    costs: list[float],
) -> None:
    """Validate a saved case record and append its outcomes to metric inputs."""
    if record.get("case_id") != case.case_id or record.get("track") != case.track or record.get("split") != case.split:
        raise ValueError("case checkpoint identity does not match the frozen case")
    if "request_id" in record:
        raise ValueError("benchmark case evaluation must not expose request_id")
    items = record.get("items")
    if not isinstance(items, list) or len(items) != len(case.labels):
        raise ValueError("case checkpoint has incomplete items")
    by_question: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping) or {"question_id", "prediction", "target", "confidence"} - set(item):
            raise ValueError("case checkpoint contains a malformed item")
        question_id = item["question_id"]
        if question_id in by_question or question_id not in case.labels:
            raise ValueError("case checkpoint questions do not match the frozen case")
        if item.get("target") != case.labels[question_id]:
            raise ValueError("case checkpoint target does not match the frozen case")
        confidence = item.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(float(confidence)) or not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("case checkpoint has invalid confidence")
        by_question[question_id] = item
    if set(by_question) != set(case.labels):
        raise ValueError("case checkpoint questions do not match the frozen case")
    latency = record.get("latency_ms")
    cost = record.get("cost_usd")
    if isinstance(latency, bool) or not isinstance(latency, (int, float)) or not math.isfinite(float(latency)) or float(latency) < 0:
        raise ValueError("case checkpoint has invalid latency_ms")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(float(cost)) or float(cost) < 0:
        raise ValueError("case checkpoint has invalid cost_usd")
    usage = record.get("usage")
    if not isinstance(usage, Mapping) or set(usage) != {"input_tokens", "output_tokens"} or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in usage.values()):
        raise ValueError("case checkpoint has invalid token usage")
    for question_id in case.labels:
        item = by_question[question_id]
        preds.append(item.get("prediction"))
        targets.append(item.get("target"))
        confidences.append(float(item["confidence"]))
        latencies.append(float(latency))
        costs.append(float(cost))


def _legacy_benchmark_run_hash(payload: Mapping[str, Any]) -> str:
    """Reproduce the v1 hash algorithm for old published artifacts."""
    canonical_systems = []
    for s in sorted(payload.get("systems", []), key=lambda x: x.get("system_id", "")):
        m = s.get("metrics")
        filtered_m = None
        if isinstance(m, dict):
            filtered_m = {
                k: v
                for k, v in m.items()
                if not k.endswith("_latency_ms")
            }
        canonical_systems.append({
            "system_id": s.get("system_id"),
            "status": s.get("status"),
            "metrics": filtered_m,
        })

    canonical_payload = {
        "benchmark_id": payload.get("benchmark_id"),
        "tracks": sorted(payload.get("tracks", [])),
        "sample_count": payload.get("sample_count"),
        "systems": canonical_systems,
    }
    raw = json.dumps(canonical_payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _hashable_case_evaluations(value: Any) -> Any:
    """Remove wall-clock latency from v2 integrity inputs.

    Latency is retained in the public record, but is inherently noisy between
    identical local runs. Predictions, targets, confidence, cost, usage,
    case identity, track, and split remain covered by the run hash.
    """
    if not isinstance(value, list):
        return value
    result: list[Any] = []
    for case in value:
        if not isinstance(case, Mapping):
            result.append(case)
            continue
        result.append({
            key: _hashable_case_evaluations(item)
            for key, item in case.items()
            if key != "latency_ms"
        })
    return result


def _hashable_statistics(value: Any) -> Any:
    """Remove wall-clock latency fields from nested metric objects."""
    if isinstance(value, Mapping):
        return {
            key: _hashable_statistics(item)
            for key, item in value.items()
            if "latency" not in str(key).lower()
        }
    if isinstance(value, list):
        return [_hashable_statistics(item) for item in value]
    return value


def compute_benchmark_run_hash(payload: dict[str, Any]) -> str:
    """Compute a deterministic v1 or v2 benchmark integrity hash."""
    if payload.get("schema") == LEGACY_BENCHMARK_RUN_SCHEMA:
        return _legacy_benchmark_run_hash(payload)

    canonical_systems = []
    for system in sorted(payload.get("systems", []), key=lambda item: item.get("system_id", "")):
        metrics = system.get("metrics")
        if isinstance(metrics, dict):
            metrics = {
                key: value
                for key, value in metrics.items()
                if not key.endswith("_latency_ms")
            }
        canonical_systems.append({
            "system_id": system.get("system_id"),
            "status": system.get("status"),
            "model_requested": system.get("model_requested"),
            "model_resolved": system.get("model_resolved"),
            "cost_usd": system.get("cost_usd"),
            "metrics": metrics,
            "track_metrics": _hashable_statistics(system.get("track_metrics")),
            "case_evaluations": _hashable_case_evaluations(system.get("case_evaluations")),
        })

    canonical_payload = {
        "schema": payload.get("schema"),
        "benchmark_id": payload.get("benchmark_id"),
        "tracks": sorted(payload.get("tracks", [])),
        "sample_count": payload.get("sample_count"),
        "mode": payload.get("mode"),
        "limit_per_track": payload.get("limit_per_track"),
        "statistics": payload.get("statistics"),
        "systems": canonical_systems,
    }
    raw = json.dumps(canonical_payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_benchmark(
    *,
    tracks: Sequence[str] | None = None,
    systems: Sequence[str] | None = None,
    out_dir: str | Path | None = None,
    mode: str = "all",  # "all", "dev", or "holdout"
    base_dir: str | Path | None = None,
    live: bool = False,
    typesafe_backend: Any = None,
    openrouter_backend: Any = None,
    limit_per_track: int | None = None,
    typesafe_checkpoint_path: str | Path | None = None,
    resume_typesafe: bool = False,
    typesafe_budget_usd: float = TYPESAFE_MAX_COST_USD,
) -> dict[str, Any]:
    """Execute benchmark evaluation across selected tracks and systems."""
    selected_tracks = list(tracks) if tracks is not None else list(TRACK_IDS)
    for t in selected_tracks:
        if t not in TRACK_IDS:
            raise ValueError(f"unknown track '{t}'. Must be one of {TRACK_IDS}")
    if limit_per_track is not None and (
        isinstance(limit_per_track, bool)
        or not isinstance(limit_per_track, int)
        or limit_per_track <= 0
    ):
        raise ValueError("limit_per_track must be a positive integer")
    if isinstance(typesafe_budget_usd, bool) or not isinstance(typesafe_budget_usd, (int, float)):
        raise ValueError("typesafe_budget_usd must be a finite non-negative number")
    if not math.isfinite(float(typesafe_budget_usd)) or float(typesafe_budget_usd) < 0:
        raise ValueError("typesafe_budget_usd must be a finite non-negative number")
    if float(typesafe_budget_usd) > TYPESAFE_MAX_COST_USD:
        raise ValueError(f"typesafe_budget_usd cannot exceed {TYPESAFE_MAX_COST_USD:.2f}")

    selected_systems = list(systems) if systems is not None else [
        "deterministic_baseline",
        "typesafe_direct",
        "openrouter_jev",
    ]

    # 1. Load cases
    all_cases: list[BenchmarkCase] = []
    track_cases_map: dict[str, list[BenchmarkCase]] = {}
    for track in selected_tracks:
        c_list = load_track(track, base_dir=base_dir)
        if mode in ("dev", "holdout"):
            c_list = [c for c in c_list if c.split == mode]
        if limit_per_track is not None and limit_per_track > 0:
            c_list = c_list[:limit_per_track]
        track_cases_map[track] = c_list
        all_cases.extend(c_list)

    sample_count = len(all_cases)
    now_str = _now_iso()
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{sample_count}"

    # 2. Evaluate deterministic baseline first
    baseline_raw_preds: list[Any] = []
    baseline_targets: list[Any] = []
    baseline_confs: list[float] = []
    baseline_lats: list[float] = []
    baseline_costs: list[float] = []
    baseline_case_evaluations: list[dict[str, Any]] = []

    baseline_track_details: dict[str, dict[str, Any]] = {}
    for track in selected_tracks:
        t_cases = track_cases_map[track]
        t_preds: list[Any] = []
        t_targets: list[Any] = []
        t_confs: list[float] = []
        t_lats: list[float] = []
        t_costs: list[float] = []
        t_case_evaluations: list[dict[str, Any]] = []

        for case in t_cases:
            t0 = time.perf_counter()
            preds_dict = baseline_predictions(case)
            lat_ms = (time.perf_counter() - t0) * 1000.0
            case_items = []

            for q_id, target_val in case.labels.items():
                pred_val = preds_dict.get(q_id)
                t_preds.append(pred_val)
                t_targets.append(target_val)
                t_confs.append(1.0)
                t_lats.append(lat_ms)
                t_costs.append(0.0)
                case_items.append({
                    "question_id": q_id,
                    "prediction": pred_val,
                    "target": target_val,
                    "confidence": 1.0,
                })
            case_record = {
                "case_id": case.case_id,
                "track": case.track,
                "split": case.split,
                "items": case_items,
                "latency_ms": lat_ms,
                "cost_usd": 0.0,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
            t_case_evaluations.append(case_record)
            baseline_case_evaluations.append(case_record)

        baseline_raw_preds.extend(t_preds)
        baseline_targets.extend(t_targets)
        baseline_confs.extend(t_confs)
        baseline_lats.extend(t_lats)
        baseline_costs.extend(t_costs)

        baseline_track_details[track] = calculate_system_metrics(
            total_cases=len(t_cases),
            valid_schema_cases=len(t_cases),
            preds=t_preds,
            targets=t_targets,
            confidences=t_confs,
            latencies_ms=t_lats,
            costs_usd=t_costs,
            baseline_preds=t_preds,
            case_evaluations=t_case_evaluations,
            case_latencies_ms=[case["latency_ms"] for case in t_case_evaluations],
            case_costs_usd=[case["cost_usd"] for case in t_case_evaluations],
        )

    baseline_overall_metrics = calculate_system_metrics(
        total_cases=sample_count,
        valid_schema_cases=sample_count,
        preds=baseline_raw_preds,
        targets=baseline_targets,
        confidences=baseline_confs,
        latencies_ms=baseline_lats,
        costs_usd=baseline_costs,
        baseline_preds=baseline_raw_preds,
        case_evaluations=baseline_case_evaluations,
        case_latencies_ms=[case["latency_ms"] for case in baseline_case_evaluations],
        case_costs_usd=[case["cost_usd"] for case in baseline_case_evaluations],
    )

    evaluated_systems: list[dict[str, Any]] = []

    # Add deterministic baseline
    if "deterministic_baseline" in selected_systems:
        evaluated_systems.append(
            {
                "system_id": "deterministic_baseline",
                "status": "completed",
                "model_requested": "rule_based",
                "model_resolved": "deterministic_rules_v1",
                "cost_usd": 0.0,
                "latency_p50_ms": baseline_overall_metrics["p50_latency_ms"],
                "latency_p95_ms": baseline_overall_metrics["p95_latency_ms"],
                "latency_p99_ms": baseline_overall_metrics["p99_latency_ms"],
                "metrics": baseline_overall_metrics,
                "track_metrics": baseline_track_details,
                "case_evaluations": baseline_case_evaluations,
            }
        )

    # 3. Check Jev systems (fail-closed, never fabricate)
    jev_mod = None
    try:
        import smartmoney_cub_harness.jev as jev_mod
    except Exception:
        jev_mod = None

    for sys_id in selected_systems:
        if sys_id == "deterministic_baseline":
            continue

        if sys_id in ("typesafe_direct", "typesafe-direct"):
            api_key = os.getenv("TYPESAFE_API_KEY")

            if jev_mod is None:
                evaluated_systems.append(
                    {
                        "system_id": "typesafe_direct",
                        "status": "not_run",
                        "reason": "jev_module_unavailable",
                        "model_requested": "jev-latest",
                        "model_resolved": None,
                        "cost_usd": 0.0,
                        "latency_p50_ms": 0.0,
                        "metrics": None,
                    }
                )
                continue

            if not api_key and typesafe_backend is None:
                evaluated_systems.append(
                    {
                        "system_id": "typesafe_direct",
                        "status": "not_run",
                        "reason": "missing_credential",
                        "model_requested": "jev-latest",
                        "model_resolved": None,
                        "cost_usd": 0.0,
                        "latency_p50_ms": 0.0,
                        "metrics": None,
                    }
                )
                continue

            if not live and typesafe_backend is None:
                evaluated_systems.append(
                    {
                        "system_id": "typesafe_direct",
                        "status": "not_run",
                        "reason": "live_evaluation_not_wired",
                        "model_requested": "jev-latest",
                        "model_resolved": None,
                        "cost_usd": 0.0,
                        "latency_p50_ms": 0.0,
                        "metrics": None,
                    }
                )
                continue

            # Execute live evaluation through typesafe backend
            backend = typesafe_backend
            if backend is None:
                backend = jev_mod.TypeSafeDirectJevBackend(
                    api_key=api_key,
                    model_requested="jev-latest",
                )

            evaluated_systems.append(
                _evaluate_jev_system(
                    system_id="typesafe_direct",
                    backend=backend,
                    selected_tracks=selected_tracks,
                    track_cases_map=track_cases_map,
                    sample_count=sample_count,
                    baseline_raw_preds=baseline_raw_preds,
                    default_model_requested="jev-latest",
                    checkpoint_path=Path(typesafe_checkpoint_path) if typesafe_checkpoint_path is not None else None,
                    resume=resume_typesafe,
                    budget_usd=float(typesafe_budget_usd),
                )
            )

        elif sys_id in ("openrouter_jev", "openrouter-jev"):
            api_key = os.getenv("OPENROUTER_API_KEY")
            if jev_mod is None:
                evaluated_systems.append(
                    {
                        "system_id": "openrouter_jev",
                        "status": "not_run",
                        "reason": "jev_module_unavailable",
                        "model_requested": "~typesafe/jev-latest",
                        "model_resolved": None,
                        "cost_usd": 0.0,
                        "latency_p50_ms": 0.0,
                        "metrics": None,
                    }
                )
                continue

            if not api_key and openrouter_backend is None:
                evaluated_systems.append(
                    {
                        "system_id": "openrouter_jev",
                        "status": "not_run",
                        "reason": "missing_credential",
                        "model_requested": "~typesafe/jev-latest",
                        "model_resolved": None,
                        "cost_usd": 0.0,
                        "latency_p50_ms": 0.0,
                        "metrics": None,
                    }
                )
                continue

            if not live and openrouter_backend is None:
                evaluated_systems.append(
                    {
                        "system_id": "openrouter_jev",
                        "status": "not_run",
                        "reason": "live_evaluation_not_wired",
                        "model_requested": "~typesafe/jev-latest",
                        "model_resolved": None,
                        "cost_usd": 0.0,
                        "latency_p50_ms": 0.0,
                        "metrics": None,
                    }
                )
                continue

            backend = openrouter_backend
            if backend is None:
                backend = jev_mod.OpenRouterJevBackend(
                    api_key=api_key,
                    model_requested="~typesafe/jev-latest",
                )

            evaluated_systems.append(
                _evaluate_jev_system(
                    system_id="openrouter_jev",
                    backend=backend,
                    selected_tracks=selected_tracks,
                    track_cases_map=track_cases_map,
                    sample_count=sample_count,
                    baseline_raw_preds=baseline_raw_preds,
                    default_model_requested="~typesafe/jev-latest",
                )
            )

    run_payload: dict[str, Any] = {
        "schema": BENCHMARK_RUN_SCHEMA,
        "run_id": run_id,
        "benchmark_id": BENCHMARK_ID,
        "run_date": now_str,
        "mode": mode,
        "tracks": selected_tracks,
        "sample_count": sample_count,
        "limit_per_track": limit_per_track,
        "statistics": BENCHMARK_STATISTICS,
        "git_sha": _get_git_sha(),
        "systems": evaluated_systems,
        "safety": SAFETY_DECLARATION,
    }

    run_hash = compute_benchmark_run_hash(run_payload)
    run_payload["run_hash"] = run_hash

    if out_dir is not None:
        target_dir = Path(out_dir) / run_id
        target_dir.mkdir(parents=True, exist_ok=True)
        run_json_path = target_dir / "run.json"
        with run_json_path.open("w", encoding="utf-8") as f:
            json.dump(run_payload, f, indent=2, ensure_ascii=False)

    return run_payload


def _evaluate_jev_system(
    *,
    system_id: str,
    backend: Any,
    selected_tracks: list[str],
    track_cases_map: dict[str, list[BenchmarkCase]],
    sample_count: int,
    baseline_raw_preds: list[Any],
    default_model_requested: str,
    checkpoint_path: Path | None = None,
    resume: bool = False,
    budget_usd: float = TYPESAFE_MAX_COST_USD,
) -> dict[str, Any]:
    """Execute Jev evaluation with resumable TypeSafe checkpoints.

    Checkpoints contain only structured toy benchmark outcomes. Provider
    request identifiers and authentication material never enter them.
    """
    from smartmoney_cub_harness.jev.errors import JevProtocolError, JevUnavailable
    from smartmoney_cub_harness.jev.questions import build_questions

    selected_cases = [case for track in selected_tracks for case in track_cases_map[track]]
    model_requested = str(getattr(backend, "model_requested", default_model_requested)).strip()
    if not model_requested:
        model_requested = default_model_requested
    model_resolved: str | None = None
    total_cost = 0.0
    case_evaluations: list[dict[str, Any]] = []
    resumed_records: dict[str, dict[str, Any]] = {}

    if resume:
        if checkpoint_path is None:
            raise ValueError("resume requires a TypeSafe checkpoint path")
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"TypeSafe checkpoint not found: {checkpoint_path}")
        checkpoint, resumed_records, checkpoint_cost = _load_checkpoint(
            checkpoint_path,
            selected_tracks=selected_tracks,
            selected_cases=selected_cases,
            model_requested=model_requested,
        )
        model_resolved = checkpoint.get("model_resolved")
        total_cost = checkpoint_cost

    def incomplete_result(reason: str) -> dict[str, Any]:
        if checkpoint_path is not None:
            _write_checkpoint(
                checkpoint_path,
                selected_tracks=selected_tracks,
                selected_cases=selected_cases,
                model_requested=model_requested,
                model_resolved=model_resolved,
                total_cost=total_cost,
                case_evaluations=case_evaluations,
                status="incomplete",
                reason=reason,
            )
        status = "incomplete" if checkpoint_path is not None else "not_run"
        return {
            "system_id": system_id,
            "status": status,
            "reason": reason,
            "model_requested": model_requested,
            "model_resolved": model_resolved,
            "cost_usd": round(total_cost, 6),
            "latency_p50_ms": 0.0,
            "metrics": None,
            "completed_case_count": len(case_evaluations),
        }

    def estimated_next_cost(questions: Sequence[Any], case: BenchmarkCase) -> float | None:
        estimator = getattr(backend, "estimate_cost_usd", None)
        if callable(estimator):
            try:
                estimate = estimator(case.state, questions)
            except TypeError:
                estimate = estimator(questions)
            try:
                estimate_float = float(estimate)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("invalid estimated request cost") from exc
            if not math.isfinite(estimate_float) or estimate_float < 0:
                raise ValueError("invalid estimated request cost")
            return estimate_float
        declared = getattr(backend, "estimated_cost_usd", None)
        if declared is None:
            return None
        try:
            estimate_float = float(declared)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid estimated request cost") from exc
        if not math.isfinite(estimate_float) or estimate_float < 0:
            raise ValueError("invalid estimated request cost")
        return estimate_float

    all_preds: list[Any] = []
    all_targets: list[Any] = []
    all_confs: list[float] = []
    all_lats: list[float] = []
    all_costs: list[float] = []
    track_details: dict[str, dict[str, Any]] = {}

    for track in selected_tracks:
        t_cases = track_cases_map[track]
        t_preds: list[Any] = []
        t_targets: list[Any] = []
        t_confs: list[float] = []
        t_lats: list[float] = []
        t_costs: list[float] = []
        t_case_evaluations: list[dict[str, Any]] = []

        for case in t_cases:
            case_record = resumed_records.get(case.case_id)
            if case_record is not None:
                try:
                    _append_case_record(
                        case_record,
                        case,
                        t_preds,
                        t_targets,
                        t_confs,
                        t_lats,
                        t_costs,
                    )
                except ValueError as exc:
                    return incomplete_result(f"invalid_checkpoint:{exc}")
                t_case_evaluations.append(case_record)
                case_evaluations.append(case_record)
                continue

            decision_time = case.state.get("decision_time", _now_iso())
            try:
                questions = build_questions(track, state=case.state, decision_time=decision_time)
                remaining_budget = float(budget_usd) - total_cost
                if remaining_budget <= 1e-9:
                    return incomplete_result("budget_exceeded")
                estimate = estimated_next_cost(questions, case)
                if system_id == "typesafe_direct" and estimate is None:
                    return incomplete_result("unverifiable_request_cost")
                if estimate is not None and estimate > remaining_budget + 1e-9:
                    return incomplete_result("budget_exceeded")
                decision = backend.evaluate(
                    case.state,
                    questions,
                    decision_time=decision_time,
                )
            except JevProtocolError:
                return incomplete_result("protocol_error")
            except JevUnavailable as exc:
                exc_str = str(exc).lower()
                if "no client" in exc_str:
                    reason = "no_client"
                elif "missing credential" in exc_str:
                    reason = "missing_credential"
                elif "timeout" in exc_str or "timed out" in exc_str:
                    reason = "timeout"
                else:
                    reason = "provider_unreachable"
                return incomplete_result(reason)
            except ValueError as exc:
                if "estimated request cost" in str(exc):
                    return incomplete_result("protocol_error")
                return incomplete_result("protocol_error")
            except Exception as exc:
                exc_str = str(exc).lower()
                if "timeout" in exc_str or "timed out" in exc_str:
                    reason = "timeout"
                elif "connection" in exc_str or "unreachable" in exc_str:
                    reason = "provider_unreachable"
                else:
                    reason = "protocol_error"
                return incomplete_result(reason)

            try:
                resolved_value = getattr(decision, "model_resolved", None)
                requested_value = getattr(decision, "model_requested", None)
                if not isinstance(resolved_value, str) or not isinstance(requested_value, str):
                    raise ValueError("missing model metadata")
                resolved = resolved_value.strip()
                requested = requested_value.strip()
                cost = float(decision.estimated_cost_usd)
                case_lat = float(decision.latency_ms)
                usage = decision.usage
                if not requested or not resolved or not math.isfinite(cost) or cost < 0:
                    raise ValueError("invalid model or cost metadata")
                if not math.isfinite(case_lat) or case_lat < 0:
                    raise ValueError("invalid latency")
                if not isinstance(usage, Mapping):
                    raise ValueError("invalid token usage")
                normalized_usage: dict[str, int] = {}
                for key in ("input_tokens", "output_tokens"):
                    value = usage.get(key)
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        raise ValueError("invalid token usage")
                    normalized_usage[key] = value
                if cost > float(budget_usd) - total_cost + 1e-9:
                    return incomplete_result("budget_exceeded")
                answer_ids = [answer.question_id for answer in decision.answers]
                expected_ids = list(case.labels)
                if len(answer_ids) != len(set(answer_ids)) or set(answer_ids) != set(expected_ids):
                    raise ValueError("answers do not match case questions")
                ans_map = {answer.question_id: answer for answer in decision.answers}
                case_items = []
                for q_id, target_val in case.labels.items():
                    ans = ans_map[q_id]
                    confidence = float(ans.confidence)
                    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                        raise ValueError("invalid answer confidence")
                    case_items.append({
                        "question_id": q_id,
                        "prediction": ans.value,
                        "target": target_val,
                        "confidence": confidence,
                    })
                if model_resolved is not None and model_resolved != resolved:
                    raise ValueError("resolved model changed during run")
                if model_requested != requested:
                    raise ValueError("requested model mismatch")
                model_resolved = resolved
                case_record = {
                    "case_id": case.case_id,
                    "track": case.track,
                    "split": case.split,
                    "items": case_items,
                    "latency_ms": case_lat,
                    "cost_usd": cost,
                    "usage": normalized_usage,
                }
                _append_case_record(
                    case_record,
                    case,
                    t_preds,
                    t_targets,
                    t_confs,
                    t_lats,
                    t_costs,
                )
                total_cost += cost
                t_case_evaluations.append(case_record)
                case_evaluations.append(case_record)
                _write_checkpoint(
                    checkpoint_path,
                    selected_tracks=selected_tracks,
                    selected_cases=selected_cases,
                    model_requested=model_requested,
                    model_resolved=model_resolved,
                    total_cost=total_cost,
                    case_evaluations=case_evaluations,
                    status="incomplete",
                )
            except (AttributeError, TypeError, ValueError, OverflowError):
                return incomplete_result("protocol_error")

        all_preds.extend(t_preds)
        all_targets.extend(t_targets)
        all_confs.extend(t_confs)
        all_lats.extend(t_lats)
        all_costs.extend(t_costs)

        t_base_preds = []
        for case in t_cases:
            b_preds = baseline_predictions(case)
            for q_id in case.labels.keys():
                t_base_preds.append(b_preds.get(q_id))

        track_details[track] = calculate_system_metrics(
            total_cases=len(t_cases),
            valid_schema_cases=len(t_cases),
            preds=t_preds,
            targets=t_targets,
            confidences=t_confs,
            latencies_ms=t_lats,
            costs_usd=t_costs,
            baseline_preds=t_base_preds,
            case_evaluations=t_case_evaluations,
            case_latencies_ms=[case["latency_ms"] for case in t_case_evaluations],
            case_costs_usd=[case["cost_usd"] for case in t_case_evaluations],
        )

    overall_metrics = calculate_system_metrics(
        total_cases=sample_count,
        valid_schema_cases=sample_count,
        preds=all_preds,
        targets=all_targets,
        confidences=all_confs,
        latencies_ms=all_lats,
        costs_usd=all_costs,
        baseline_preds=baseline_raw_preds,
        case_evaluations=case_evaluations,
        case_latencies_ms=[case["latency_ms"] for case in case_evaluations],
        case_costs_usd=[case["cost_usd"] for case in case_evaluations],
    )
    _write_checkpoint(
        checkpoint_path,
        selected_tracks=selected_tracks,
        selected_cases=selected_cases,
        model_requested=model_requested,
        model_resolved=model_resolved,
        total_cost=total_cost,
        case_evaluations=case_evaluations,
        status="completed",
    )

    return {
        "system_id": system_id,
        "status": "completed",
        "model_requested": model_requested,
        "model_resolved": model_resolved,
        "cost_usd": round(total_cost, 6),
        "latency_p50_ms": overall_metrics["p50_latency_ms"],
        "latency_p95_ms": overall_metrics["p95_latency_ms"],
        "latency_p99_ms": overall_metrics["p99_latency_ms"],
        "metrics": overall_metrics,
        "track_metrics": track_details,
        "case_evaluations": case_evaluations,
    }


def verify_run(run_dir: str | Path) -> dict[str, Any]:
    """Verify a legacy v1 or case-record v2 benchmark run."""
    p = Path(run_dir)
    run_json = p / "run.json" if p.is_dir() else p
    if not run_json.exists():
        raise FileNotFoundError(f"run file not found at {run_json}")
    with run_json.open("r", encoding="utf-8") as f:
        data = json.load(f)

    schema = data.get("schema")
    if schema not in (None, LEGACY_BENCHMARK_RUN_SCHEMA, BENCHMARK_RUN_SCHEMA):
        raise ValueError(f"unsupported benchmark run schema: {schema}")
    is_v2 = schema == BENCHMARK_RUN_SCHEMA
    if data.get("safety") != SAFETY_DECLARATION:
        raise ValueError(f"invalid or missing safety declaration: {data.get('safety')}")
    for field in ("run_id", "benchmark_id", "sample_count", "systems", "run_hash"):
        if field not in data or data[field] is None:
            raise ValueError(f"missing required field '{field}' in benchmark run")
    systems = data.get("systems")
    if not isinstance(systems, list) or not systems:
        raise ValueError("run contains no systems")

    case_questions: dict[str, dict[str, set[str]]] = {}
    case_labels: dict[str, dict[str, dict[str, Any]]] = {}
    case_splits: dict[str, dict[str, str]] = {}
    allowed_case_ids: dict[str, set[str]] = {}
    expected_case_ids: set[str] = set()
    if is_v2:
        tracks = data.get("tracks")
        sample_count = data.get("sample_count")
        if not isinstance(tracks, list) or not tracks or len(set(tracks)) != len(tracks):
            raise ValueError("v2 tracks must be a non-empty list of unique tracks")
        if any(track not in TRACK_IDS for track in tracks):
            raise ValueError("v2 run contains an unknown track")
        if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0:
            raise ValueError("v2 sample_count must be a positive integer")
        mode = data.get("mode")
        if mode not in ("all", "dev", "holdout"):
            raise ValueError("v2 run has an invalid mode")
        limit = data.get("limit_per_track")
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ValueError("v2 limit_per_track must be a positive integer")
        if data.get("statistics") != BENCHMARK_STATISTICS:
            raise ValueError("v2 run has unsupported or missing statistics configuration")
        for track in tracks:
            frozen_cases = load_track(track)
            eligible_cases = [
                case for case in frozen_cases
                if mode == "all" or case.split == mode
            ]
            case_questions[track] = {
                case.case_id: set(case.labels) for case in frozen_cases
            }
            case_labels[track] = {
                case.case_id: dict(case.labels) for case in frozen_cases
            }
            case_splits[track] = {
                case.case_id: case.split for case in frozen_cases
            }
            allowed_case_ids[track] = {case.case_id for case in eligible_cases}
            if limit is None:
                expected_case_ids.update(allowed_case_ids[track])
        selected_case_count = len(expected_case_ids)
        if limit is None and sample_count != selected_case_count:
            raise ValueError("v2 sample_count does not match the frozen case selection")
        if limit is not None:
            maximum = sum(min(limit, len(case_ids)) for case_ids in allowed_case_ids.values())
            if sample_count > maximum:
                raise ValueError("v2 sample_count exceeds limit_per_track")

    saved_hash = data["run_hash"]
    recomputed = compute_benchmark_run_hash(data)
    if saved_hash != recomputed:
        raise ValueError(f"run_hash mismatch: saved '{saved_hash}', recomputed '{recomputed}'")

    required_metrics = (
        "schema_valid_rate", "accuracy", "macro_f1", "recall", "fpr", "brier",
        "ece", "coverage", "abstention_rate", "selective_risk", "stability",
        "p50_latency_ms", "p95_latency_ms", "p99_latency_ms", "cost_per_case",
        "retry_rate", "confidence_interval_95", "mcnemar_against_baseline",
    )
    seen_system_ids: set[str] = set()
    for system in systems:
        if not isinstance(system, dict) or "system_id" not in system or "status" not in system:
            raise ValueError(f"malformed system entry: {system}")
        if not isinstance(system["system_id"], str) or not system["system_id"] or system["system_id"] in seen_system_ids:
            raise ValueError("system_id values must be non-empty and unique")
        seen_system_ids.add(system["system_id"])
        status = system["status"]
        if status == "not_run":
            continue
        if status != "completed":
            raise ValueError(f"system {system['system_id']} has invalid status {status}")
        metrics = system.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError(f"completed system {system['system_id']} missing metrics")
        for metric in required_metrics:
            if metric not in metrics:
                raise ValueError(f"system {system['system_id']} missing required metric '{metric}'")
        if not is_v2:
            legacy_method = metrics.get("confidence_interval_method")
            legacy_unit = metrics.get("confidence_interval_unit")
            # Published v1 artifacts predate explicit CI metadata. Preserve
            # their original item-level Wilson interpretation while rejecting
            # partial or contradictory metadata added later.
            if legacy_method is None and legacy_unit is None:
                continue
            if legacy_method != "item_wilson_legacy" or legacy_unit != "item":
                raise ValueError(f"legacy system {system['system_id']} has invalid confidence interval metadata")
            continue

        system_id = system["system_id"]
        if not isinstance(system.get("model_requested"), str) or not system["model_requested"].strip():
            raise ValueError(f"completed system {system_id} missing model_requested")
        if not isinstance(system.get("model_resolved"), str) or not system["model_resolved"].strip():
            raise ValueError(f"completed system {system_id} missing model_resolved")
        total_cost = system.get("cost_usd")
        if isinstance(total_cost, bool) or not isinstance(total_cost, (int, float)) or not math.isfinite(total_cost) or total_cost < 0:
            raise ValueError(f"completed system {system_id} has invalid cost_usd")
        if metrics.get("confidence_interval_method") != CASE_BOOTSTRAP_METHOD or metrics.get("confidence_interval_unit") != CASE_BOOTSTRAP_UNIT or metrics.get("bootstrap") != BENCHMARK_STATISTICS["bootstrap"]:
            raise ValueError(f"completed system {system_id} has invalid confidence interval metadata")
        track_metrics = system.get("track_metrics")
        if not isinstance(track_metrics, dict) or set(track_metrics) != set(data["tracks"]):
            raise ValueError(f"completed system {system_id} has incomplete track_metrics")
        for track, track_metric in track_metrics.items():
            if not isinstance(track_metric, dict) or track_metric.get("confidence_interval_method") != CASE_BOOTSTRAP_METHOD or track_metric.get("confidence_interval_unit") != CASE_BOOTSTRAP_UNIT or track_metric.get("bootstrap") != BENCHMARK_STATISTICS["bootstrap"]:
                raise ValueError(f"completed system {system_id} has invalid track confidence interval metadata for {track}")

        records = system.get("case_evaluations")
        if not isinstance(records, list) or len(records) != data["sample_count"]:
            raise ValueError(f"completed system {system_id} has incomplete case_evaluations")
        seen_case_ids: set[str] = set()
        observed_by_track = {track: 0 for track in data["tracks"]}
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("case evaluation must be an object")
            required_record = {"case_id", "track", "split", "items", "latency_ms", "cost_usd", "usage"}
            if required_record - set(record):
                raise ValueError("case evaluation is missing required fields")
            if "request_id" in record:
                raise ValueError("benchmark case evaluation must not expose request_id")
            case_id = record["case_id"]
            track = record["track"]
            if not isinstance(case_id, str) or not case_id or case_id in seen_case_ids:
                raise ValueError("case_id values must be non-empty and unique")
            if not isinstance(track, str) or track not in data["tracks"] or case_id not in case_questions.get(track, {}):
                raise ValueError("case evaluation is not present in the frozen benchmark dataset")
            if case_id not in allowed_case_ids[track]:
                raise ValueError("case evaluation is outside the selected benchmark split")
            if record["split"] != case_splits[track][case_id]:
                raise ValueError("case split does not match the frozen benchmark dataset")
            seen_case_ids.add(case_id)
            observed_by_track[track] += 1
            for key in ("latency_ms", "cost_usd"):
                value = record[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError(f"case evaluation has invalid {key}")
            usage = record["usage"]
            if not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens"} or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in usage.values()):
                raise ValueError("case evaluation has invalid token usage")
            items = record["items"]
            if not isinstance(items, list) or not items:
                raise ValueError("case evaluation must contain items")
            question_ids: set[str] = set()
            for item in items:
                if not isinstance(item, dict) or {"question_id", "prediction", "target", "confidence"} - set(item):
                    raise ValueError("case item is missing required fields")
                question_id = item["question_id"]
                if not isinstance(question_id, str) or not question_id or question_id in question_ids:
                    raise ValueError("question_id values must be non-empty and unique within a case")
                question_ids.add(question_id)
                confidence = item["confidence"]
                if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                    raise ValueError("case item has invalid confidence")
                expected_labels = case_labels[track][case_id]
                if question_id not in expected_labels:
                    raise ValueError("case item question_id is not present in the frozen benchmark case")
                if item["target"] != expected_labels[question_id]:
                    raise ValueError("case item target does not match the frozen benchmark label")
            if question_ids != case_questions[track][case_id]:
                raise ValueError("case items do not match frozen benchmark questions")
        if limit is None and seen_case_ids != expected_case_ids:
            raise ValueError("case evaluations do not match the selected frozen benchmark cases")
        if limit is not None and any(count > limit for count in observed_by_track.values()):
            raise ValueError("case evaluations exceed limit_per_track")
        if len(seen_case_ids) != sample_count:
            raise ValueError("case evaluations do not match sample_count")
        recorded_cost = sum(float(record["cost_usd"]) for record in records)
        if not math.isclose(float(total_cost), recorded_cost, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(f"completed system {system_id} cost_usd does not match case records")

    return {
        "status": "ok",
        "run_id": data["run_id"],
        "run_hash": data["run_hash"],
        "sample_count": data["sample_count"],
        "systems_count": len(systems),
        "safety": SAFETY_DECLARATION,
    }


def verify_typesafe_public_run(run_dir: str | Path) -> dict[str, Any]:
    """Apply the strict gate required before publishing TypeSafe figures."""
    verification = verify_run(run_dir)
    path = Path(run_dir)
    run_json = path / "run.json" if path.is_dir() else path
    with run_json.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if data.get("schema") != BENCHMARK_RUN_SCHEMA:
        raise ValueError("TypeSafe public gate requires a v2 benchmark run")
    if data.get("tracks") != list(TRACK_IDS):
        raise ValueError("TypeSafe public gate requires all four tracks in canonical order")
    if data.get("mode") != "all" or data.get("limit_per_track") is not None:
        raise ValueError("TypeSafe public gate requires the complete unfiltered benchmark")
    if data.get("sample_count") != TYPESAFE_PUBLIC_CASE_COUNT:
        raise ValueError("TypeSafe public gate requires exactly 240 cases")

    systems = {
        system.get("system_id"): system
        for system in data.get("systems", [])
        if isinstance(system, dict)
    }
    system = systems.get("typesafe_direct")
    if not isinstance(system, dict) or system.get("status") != "completed":
        raise ValueError("TypeSafe public gate requires a completed typesafe_direct system")
    model_resolved = system.get("model_resolved")
    if not isinstance(model_resolved, str) or not model_resolved.strip():
        raise ValueError("TypeSafe public gate requires a resolved model version")

    records = system.get("case_evaluations")
    if not isinstance(records, list) or len(records) != TYPESAFE_PUBLIC_CASE_COUNT:
        raise ValueError("TypeSafe public gate requires 240 case evaluations")
    case_ids = [record.get("case_id") for record in records if isinstance(record, dict)]
    if len(case_ids) != TYPESAFE_PUBLIC_CASE_COUNT or len(set(case_ids)) != TYPESAFE_PUBLIC_CASE_COUNT:
        raise ValueError("TypeSafe public gate requires unique case IDs for all 240 cases")
    item_count = sum(
        len(record.get("items", []))
        for record in records
        if isinstance(record, dict)
    )
    if item_count != TYPESAFE_PUBLIC_ITEM_COUNT:
        raise ValueError("TypeSafe public gate requires exactly 1,020 evaluated items")

    total_cost = system.get("cost_usd")
    if (
        isinstance(total_cost, bool)
        or not isinstance(total_cost, (int, float))
        or not math.isfinite(float(total_cost))
        or float(total_cost) < 0
        or float(total_cost) > TYPESAFE_MAX_COST_USD + 1e-9
    ):
        raise ValueError("TypeSafe public gate requires total TypeSafe cost at or below $4.00")
    metrics = system.get("metrics")
    expected_cost_per_case = round(float(total_cost) / TYPESAFE_PUBLIC_CASE_COUNT, 6)
    if not isinstance(metrics, dict) or metrics.get("cost_per_case") != expected_cost_per_case:
        raise ValueError("TypeSafe public gate has inconsistent cost_per_case")

    return {
        "status": "ok",
        "gate": "typesafe_public",
        "run_id": verification["run_id"],
        "run_hash": verification["run_hash"],
        "model_resolved": model_resolved,
        "case_count": TYPESAFE_PUBLIC_CASE_COUNT,
        "item_count": TYPESAFE_PUBLIC_ITEM_COUNT,
        "cost_usd": round(float(total_cost), 6),
        "safety": SAFETY_DECLARATION,
    }


def compare_runs(baseline_path: str | Path, candidate_path: str | Path) -> dict[str, Any]:
    """Compare two benchmark runs and output comparative delta."""
    b_path = Path(baseline_path)
    b_file = b_path / "run.json" if b_path.is_dir() else b_path
    c_path = Path(candidate_path)
    c_file = c_path / "run.json" if c_path.is_dir() else c_path

    with b_file.open("r", encoding="utf-8") as f:
        b_data = json.load(f)
    with c_file.open("r", encoding="utf-8") as f:
        c_data = json.load(f)

    def get_sys_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {s["system_id"]: s for s in data.get("systems", []) if s.get("status") == "completed"}

    b_sys = get_sys_map(b_data)
    c_sys = get_sys_map(c_data)

    comparison: dict[str, Any] = {
        "baseline_run_id": b_data.get("run_id"),
        "candidate_run_id": c_data.get("run_id"),
        "benchmark_id": b_data.get("benchmark_id"),
        "safety": SAFETY_DECLARATION,
        "systems_deltas": {},
    }

    common_systems = set(b_sys.keys()) & set(c_sys.keys())
    for sys_id in sorted(common_systems):
        b_metrics = b_sys[sys_id]["metrics"]
        c_metrics = c_sys[sys_id]["metrics"]
        delta = {}
        for k in ("accuracy", "macro_f1", "recall", "fpr", "brier", "ece", "cost_per_case"):
            b_val = float(b_metrics.get(k, 0.0))
            c_val = float(c_metrics.get(k, 0.0))
            delta[k] = {
                "baseline": b_val,
                "candidate": c_val,
                "diff": round(c_val - b_val, 4),
            }
        comparison["systems_deltas"][sys_id] = delta

    return comparison
