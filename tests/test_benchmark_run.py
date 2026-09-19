from __future__ import annotations

import json
from pathlib import Path
import pytest

from smartmoney_cub_harness.benchmark.baseline import baseline_predictions
from smartmoney_cub_harness.benchmark.cases import (
    TRACK_IDS,
    load_track,
)
from smartmoney_cub_harness.benchmark.metrics import (
    calculate_system_metrics,
    compute_accuracy,
    compute_brier_score,
    compute_confidence_interval_95,
    compute_ece,
    compute_macro_f1,
    compute_mcnemar_test,
)
from smartmoney_cub_harness.benchmark.runner import (
    BENCHMARK_RUN_SCHEMA,
    compare_runs,
    compute_benchmark_run_hash,
    run_benchmark,
    verify_run,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_baseline_predictions_deterministic():
    cases = load_track("trading-review")
    c = cases[0]
    p1 = baseline_predictions(c)
    p2 = baseline_predictions(c)
    assert p1 == p2
    assert "evidence_sufficiency" in p1
    assert "review_priority" in p1


def test_run_hash_identical_inputs_identical_hash(tmp_path: Path):
    # Run twice on dev mode with baseline
    res1 = run_benchmark(tracks=["trading-review"], systems=["deterministic_baseline"], mode="dev", out_dir=tmp_path / "out1")
    res2 = run_benchmark(tracks=["trading-review"], systems=["deterministic_baseline"], mode="dev", out_dir=tmp_path / "out2")

    assert res1["run_hash"] == res2["run_hash"]
    assert res1["sample_count"] == 30
    assert res1["schema"] == BENCHMARK_RUN_SCHEMA
    assert res1["safety"] == SAFETY_DECLARATION


def test_metrics_completeness(tmp_path: Path):
    res = run_benchmark(
        tracks=["macro-policy"],
        systems=["deterministic_baseline"],
        mode="dev",
        out_dir=tmp_path,
    )
    sys_entry = res["systems"][0]
    metrics = sys_entry["metrics"]

    required_keys = (
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
    for k in required_keys:
        assert k in metrics, f"Missing metric {k}"

    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert 0.0 <= metrics["coverage"] <= 1.0
    assert len(metrics["confidence_interval_95"]) == 2
    ci_low, ci_high = metrics["confidence_interval_95"]
    assert 0.0 <= ci_low <= ci_high <= 1.0


def test_jev_systems_marked_not_run_without_credentials(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    res = run_benchmark(
        tracks=["trading-review"],
        systems=["deterministic_baseline", "typesafe_direct", "openrouter_jev"],
        mode="dev",
        out_dir=tmp_path,
    )

    systems_map = {s["system_id"]: s for s in res["systems"]}
    assert systems_map["deterministic_baseline"]["status"] == "completed"
    assert systems_map["typesafe_direct"]["status"] == "not_run"
    assert systems_map["typesafe_direct"]["metrics"] is None
    assert systems_map["openrouter_jev"]["status"] == "not_run"
    assert systems_map["openrouter_jev"]["metrics"] is None


def test_verify_run_detects_tampered_hash(tmp_path: Path):
    out_dir = tmp_path / "run_tamper"
    res = run_benchmark(tracks=["macro-policy"], systems=["deterministic_baseline"], out_dir=out_dir)
    run_dir = out_dir / res["run_id"]
    run_json = run_dir / "run.json"

    # Verify passes initially
    v_res = verify_run(run_dir)
    assert v_res["status"] == "ok"
    assert v_res["safety"] == SAFETY_DECLARATION

    # Tamper with accuracy in run.json
    with run_json.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data["systems"][0]["metrics"]["accuracy"] = 0.9999
    with run_json.open("w", encoding="utf-8") as f:
        json.dump(data, f)

    with pytest.raises(ValueError, match="run_hash mismatch"):
        verify_run(run_dir)


def test_compare_runs(tmp_path: Path):
    out_b = tmp_path / "base"
    out_c = tmp_path / "cand"
    res_b = run_benchmark(tracks=["macro-policy"], mode="dev", out_dir=out_b)
    res_c = run_benchmark(tracks=["macro-policy"], mode="dev", out_dir=out_c)

    comp = compare_runs(out_b / res_b["run_id"], out_c / res_c["run_id"])
    assert comp["safety"] == SAFETY_DECLARATION
    assert "deterministic_baseline" in comp["systems_deltas"]
    assert comp["systems_deltas"]["deterministic_baseline"]["accuracy"]["diff"] == 0.0
