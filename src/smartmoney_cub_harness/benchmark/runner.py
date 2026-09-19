from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from smartmoney_cub_harness.benchmark.baseline import baseline_predictions
from smartmoney_cub_harness.benchmark.cases import (
    BENCHMARK_ID,
    TRACK_IDS,
    BenchmarkCase,
    load_track,
)
from smartmoney_cub_harness.benchmark.metrics import calculate_system_metrics
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

BENCHMARK_RUN_SCHEMA = "smartmoney_cub_benchmark_run.v1"


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


def compute_benchmark_run_hash(payload: dict[str, Any]) -> str:
    """Compute deterministic run hash from run inputs and evaluated predictions."""
    # Hash inputs: benchmark_id, tracks, sample_count, systems config, predictions
    canonical_systems = []
    for s in sorted(payload.get("systems", []), key=lambda x: x.get("system_id", "")):
        m = s.get("metrics")
        filtered_m = None
        if isinstance(m, dict):
            # Exclude wall-clock volatile latency jitter to guarantee reproducible hash
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


def run_benchmark(
    *,
    tracks: Sequence[str] | None = None,
    systems: Sequence[str] | None = None,
    out_dir: str | Path | None = None,
    mode: str = "all",  # "all", "dev", or "holdout"
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Execute benchmark evaluation across selected tracks and systems."""
    selected_tracks = list(tracks) if tracks is not None else list(TRACK_IDS)
    for t in selected_tracks:
        if t not in TRACK_IDS:
            raise ValueError(f"unknown track '{t}'. Must be one of {TRACK_IDS}")

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

    # Per track breakdown
    baseline_track_details: dict[str, dict[str, Any]] = {}
    for track in selected_tracks:
        t_cases = track_cases_map[track]
        t_preds: list[Any] = []
        t_targets: list[Any] = []
        t_confs: list[float] = []
        t_lats: list[float] = []
        t_costs: list[float] = []

        for case in t_cases:
            t0 = time.perf_counter()
            preds_dict = baseline_predictions(case)
            lat_ms = (time.perf_counter() - t0) * 1000.0

            for q_id, target_val in case.labels.items():
                pred_val = preds_dict.get(q_id)
                t_preds.append(pred_val)
                t_targets.append(target_val)
                t_confs.append(1.0)
                t_lats.append(lat_ms)
                t_costs.append(0.0)

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
            }
        )

    # 3. Check Jev systems (fail-closed, never fabricate)
    # Try lazy import of jev
    jev_available = False
    try:
        import smartmoney_cub_harness.jev as jev_mod
        jev_available = True
    except Exception:
        jev_available = False

    for sys_id in selected_systems:
        if sys_id == "deterministic_baseline":
            continue

        if sys_id in ("typesafe_direct", "typesafe-direct"):
            # Check credential
            api_key = os.getenv("TYPESAFE_API_KEY")
            if not jev_available:
                reason = "jev_module_unavailable"
            elif not api_key:
                reason = "missing_credential"
            else:
                reason = "live_evaluation_not_wired"
            evaluated_systems.append(
                {
                    "system_id": "typesafe_direct",
                    "status": "not_run",
                    "reason": reason,
                    "model_requested": "typesafe-direct-latest",
                    "model_resolved": None,
                    "cost_usd": 0.0,
                    "latency_p50_ms": 0.0,
                    "metrics": None,
                }
            )

        elif sys_id in ("openrouter_jev", "openrouter-jev"):
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not jev_available:
                reason = "jev_module_unavailable"
            elif not api_key:
                reason = "missing_credential"
            else:
                reason = "live_evaluation_not_wired"
            evaluated_systems.append(
                {
                    "system_id": "openrouter_jev",
                    "status": "not_run",
                    "reason": reason,
                    "model_requested": "~typesafe/jev-latest",
                    "model_resolved": None,
                    "cost_usd": 0.0,
                    "latency_p50_ms": 0.0,
                    "metrics": None,
                }
            )

    run_payload: dict[str, Any] = {
        "schema": BENCHMARK_RUN_SCHEMA,
        "run_id": run_id,
        "benchmark_id": BENCHMARK_ID,
        "run_date": now_str,
        "mode": mode,
        "tracks": selected_tracks,
        "sample_count": sample_count,
        "git_sha": _get_git_sha(),
        "systems": evaluated_systems,
        "safety": SAFETY_DECLARATION,
    }

    # Deterministic run hash
    run_hash = compute_benchmark_run_hash(run_payload)
    run_payload["run_hash"] = run_hash

    # Write to out_dir if requested
    if out_dir is not None:
        target_dir = Path(out_dir) / run_id
        target_dir.mkdir(parents=True, exist_ok=True)
        run_json_path = target_dir / "run.json"
        with run_json_path.open("w", encoding="utf-8") as f:
            json.dump(run_payload, f, indent=2, ensure_ascii=False)

    return run_payload


def verify_run(run_dir: str | Path) -> dict[str, Any]:
    """Verify integrity of a benchmark run JSON and ensure required fields and safety declaration exist."""
    p = Path(run_dir)
    run_json = p / "run.json" if p.is_dir() else p
    if not run_json.exists():
        raise FileNotFoundError(f"run file not found at {run_json}")

    with run_json.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Verify safety declaration
    if data.get("safety") != SAFETY_DECLARATION:
        raise ValueError(f"invalid or missing safety declaration: {data.get('safety')}")

    # Verify required top-level fields
    for fld in ("run_id", "benchmark_id", "sample_count", "systems", "run_hash"):
        if fld not in data or data[fld] is None:
            raise ValueError(f"missing required field '{fld}' in benchmark run")

    # Verify hash integrity
    saved_hash = data["run_hash"]
    recomputed = compute_benchmark_run_hash(data)
    if saved_hash != recomputed:
        raise ValueError(
            f"run_hash mismatch: saved '{saved_hash}', recomputed '{recomputed}'"
        )

    # Verify systems
    systems = data.get("systems", [])
    if not systems:
        raise ValueError("run contains no systems")

    for s in systems:
        if "system_id" not in s or "status" not in s:
            raise ValueError(f"malformed system entry: {s}")
        if s["status"] == "completed":
            metrics = s.get("metrics")
            if not metrics:
                raise ValueError(f"completed system {s['system_id']} missing metrics")
            required_metrics = (
                "schema_valid_rate",
                "accuracy",
                "macro_f1",
                "recall",
                "fpr",
                "brier",
                "ece",
                "coverage",
                "abstention_rate",
                "selective_risk",
                "stability",
                "p50_latency_ms",
                "p95_latency_ms",
                "p99_latency_ms",
                "cost_per_case",
                "retry_rate",
                "confidence_interval_95",
                "mcnemar_against_baseline",
            )
            for m in required_metrics:
                if m not in metrics:
                    raise ValueError(f"system {s['system_id']} missing required metric '{m}'")

    return {
        "status": "ok",
        "run_id": data["run_id"],
        "run_hash": data["run_hash"],
        "sample_count": data["sample_count"],
        "systems_count": len(systems),
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

    # Find primary completed systems in baseline and candidate
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
