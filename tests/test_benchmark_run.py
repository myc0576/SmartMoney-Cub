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
    assert systems_map["typesafe_direct"]["reason"] == "missing_credential"
    assert systems_map["typesafe_direct"]["metrics"] is None
    assert systems_map["openrouter_jev"]["status"] == "not_run"
    assert systems_map["openrouter_jev"]["reason"] == "missing_credential"
    assert systems_map["openrouter_jev"]["metrics"] is None


def test_jev_systems_truthful_reason_when_credential_present(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-typesafe-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")

    res = run_benchmark(
        tracks=["macro-policy"],
        systems=["deterministic_baseline", "typesafe_direct", "openrouter_jev"],
        mode="dev",
        out_dir=tmp_path,
    )

    systems_map = {s["system_id"]: s for s in res["systems"]}
    assert systems_map["typesafe_direct"]["status"] == "not_run"
    assert systems_map["typesafe_direct"]["reason"] != "missing_credential"
    assert systems_map["typesafe_direct"]["reason"] == "live_evaluation_not_wired"

    assert systems_map["openrouter_jev"]["status"] == "not_run"
    assert systems_map["openrouter_jev"]["reason"] != "missing_credential"
    assert systems_map["openrouter_jev"]["reason"] == "live_evaluation_not_wired"


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


def test_baseline_is_not_a_100_percent_tautology():
    # Defend against tautological 1.0 accuracy sweep across all tracks
    res = run_benchmark(tracks=list(TRACK_IDS), systems=["deterministic_baseline"])
    overall_acc = res["systems"][0]["metrics"]["accuracy"]
    assert 0.50 <= overall_acc < 0.98, (
        f"Baseline accuracy {overall_acc:.2%} must be realistic and non-circular (expected 50%-98%)"
    )

    track_metrics = res["systems"][0]["track_metrics"]
    perfect_tracks = [t for t, m in track_metrics.items() if m["accuracy"] >= 1.0]
    assert len(perfect_tracks) < len(TRACK_IDS), (
        "Baseline cannot have 100% accuracy on every track; this indicates circular evaluation."
    )

def test_typesafe_direct_live_evaluation_wired_with_mock():
    def mock_backend_client(req):
        body = json.loads(req.data.decode("utf-8"))
        q_keys = list(body["questions"].keys())
        answers = {}
        for qk in q_keys:
            q_info = body["questions"][qk]
            if q_info["type"] == "noul":
                answers[qk] = {"type": "noul", "noul": 0.05}
            elif q_info["type"] == "choice":
                choices = list(q_info["criteria"].keys())
                answers[qk] = {"type": "choice", "choice": choices[0], "confidence": 0.95}
            elif q_info["type"] == "score":
                answers[qk] = {"type": "score", "score": 2.0, "confidence": 0.8}
        return {
            "model": "jev-1.13.0",
            "answers": answers,
            "usage": {"input_tokens": 120, "output_tokens": 12},
        }

    from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend

    fake_backend = TypeSafeDirectJevBackend(
        api_key="mock-key",
        http_client=mock_backend_client,
    )

    res = run_benchmark(
        tracks=["trading-review"],
        systems=["typesafe_direct"],
        mode="dev",
        live=True,
        typesafe_backend=fake_backend,
        limit_per_track=2,
    )

    sys_res = res["systems"][0]
    assert sys_res["system_id"] == "typesafe_direct"
    assert sys_res["status"] == "completed"
    assert sys_res["model_requested"] == "jev-latest"
    assert sys_res["model_resolved"] == "jev-1.13.0"
    assert sys_res["metrics"] is not None
    assert "accuracy" in sys_res["metrics"]
    assert "macro_f1" in sys_res["metrics"]
    assert "brier" in sys_res["metrics"]
    assert "ece" in sys_res["metrics"]
    assert "mcnemar_against_baseline" in sys_res["metrics"]


def test_typesafe_direct_reports_truthful_reason_on_failure():
    from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend
    from smartmoney_cub_harness.jev.errors import JevUnavailable, JevProtocolError

    def timeout_client(req):
        raise TimeoutError("timed out connecting to server")

    bad_backend = TypeSafeDirectJevBackend(
        api_key="mock-key",
        http_client=timeout_client,
    )

    res = run_benchmark(
        tracks=["trading-review"],
        systems=["typesafe_direct"],
        mode="dev",
        live=True,
        typesafe_backend=bad_backend,
        limit_per_track=2,
    )
    sys_res = res["systems"][0]
    assert sys_res["status"] == "not_run"
    assert sys_res["reason"] == "timeout"
    assert sys_res["metrics"] is None


def test_typesafe_direct_distinguishes_no_client_from_provider_unreachable():
    from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend

    # Local configuration: client explicitly None
    local_backend = TypeSafeDirectJevBackend(
        api_key="mock-key",
        http_client=None,
    )

    res = run_benchmark(
        tracks=["trading-review"],
        systems=["typesafe_direct"],
        mode="dev",
        live=True,
        typesafe_backend=local_backend,
        limit_per_track=2,
    )
    sys_res = res["systems"][0]
    assert sys_res["status"] == "not_run"
    assert sys_res["reason"] == "no_client"
    assert sys_res["reason"] != "provider_unreachable"

    # Outside network failure
    def unreachable_client(req):
        raise ConnectionResetError("network peer dropped connection")

    net_backend = TypeSafeDirectJevBackend(
        api_key="mock-key",
        http_client=unreachable_client,
    )
    res_net = run_benchmark(
        tracks=["trading-review"],
        systems=["typesafe_direct"],
        mode="dev",
        live=True,
        typesafe_backend=net_backend,
        limit_per_track=2,
    )
    sys_net = res_net["systems"][0]
    assert sys_net["status"] == "not_run"
    assert sys_net["reason"] == "provider_unreachable"
    assert sys_net["reason"] != "no_client"

def test_readme_benchmark_figures_match_published_run():
    """Ensure headline benchmark figures in README.md stay strictly in sync with assets/benchmark/run.json."""
    from pathlib import Path
    import json
    import re

    root = Path(__file__).resolve().parent.parent
    run_json_path = root / "assets" / "benchmark" / "run.json"
    readme_path = root / "README.md"
    readme_zh_path = root / "README.zh-CN.md"

    assert run_json_path.exists(), "assets/benchmark/run.json missing"
    assert readme_path.exists(), "README.md missing"
    assert readme_zh_path.exists(), "README.zh-CN.md missing"

    with run_json_path.open("r", encoding="utf-8") as f:
        run_data = json.load(f)

    baseline = next(s for s in run_data["systems"] if s["system_id"] == "deterministic_baseline")
    typesafe = next(s for s in run_data["systems"] if s["system_id"] == "typesafe_direct")

    expected_figures = {
        "baseline_accuracy": f"{baseline['metrics']['accuracy']:.2%}",
        "baseline_f1": f"{baseline['metrics']['macro_f1']:.4f}",
        "jev_accuracy": f"{typesafe['metrics']['accuracy']:.2%}",
        "jev_f1": f"{typesafe['metrics']['macro_f1']:.4f}",
        "jev_ece": f"{typesafe['metrics']['ece']:.4f}",
    }

    en_text = readme_path.read_text(encoding="utf-8")
    zh_text = readme_zh_path.read_text(encoding="utf-8")

    for name, fig in expected_figures.items():
        assert fig in en_text, f"Figure {fig} ({name}) not found in README.md"
        assert fig in zh_text, f"Figure {fig} ({name}) not found in README.zh-CN.md"
