from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from smartmoney_cub_harness.benchmark.runner import compute_benchmark_run_hash, run_benchmark


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("benchmark_publication", ROOT / "scripts/publish_benchmark_images.py")
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


def _run(tmp_path: Path, *, typesafe: bool = False) -> Path:
    data = run_benchmark(systems=["deterministic_baseline"], limit_per_track=1, out_dir=tmp_path)
    if typesafe:
        data["systems"][0]["system_id"] = "typesafe_direct"
        data["systems"][0]["model_requested"] = "jev-latest"
        data["systems"][0]["model_resolved"] = "jev-test"
        data["run_hash"] = compute_benchmark_run_hash(data)
    run = tmp_path / data["run_id"]
    (run / "run.json").write_text(json.dumps(data))
    (run / "benchmark-test.svg").write_text("<svg/>")
    return run


def test_publication_rejects_partial_typesafe_before_writing(tmp_path: Path):
    run = _run(tmp_path, typesafe=True)
    target = tmp_path / "public"
    target.mkdir()
    existing = target / "run.json"
    existing.write_text("existing public data")
    with pytest.raises(ValueError, match="complete unfiltered"):
        publication.publish_benchmark_images(run, target)
    assert existing.read_text() == "existing public data"
    assert not (target / "benchmark-test.svg").exists()


def test_publication_rejects_tampered_run_before_writing(tmp_path: Path):
    run = _run(tmp_path)
    data = json.loads((run / "run.json").read_text())
    data["systems"][0]["metrics"]["accuracy"] = 0.01
    (run / "run.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="run_hash mismatch"):
        publication.publish_benchmark_images(run, tmp_path / "public")
    assert not (tmp_path / "public").exists()


def test_dev_env_forwards_typesafe_public_gate(tmp_path: Path):
    run = _run(tmp_path, typesafe=True)
    result = subprocess.run(
        ["bash", "scripts/dev-env.sh", "benchmark", "verify", str(run), "--require-typesafe-public"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "complete unfiltered" in result.stderr


def test_baseline_only_publication_still_supported(tmp_path: Path):
    run = _run(tmp_path)
    files = publication.publish_benchmark_images(run, tmp_path / "public")
    assert len(files) == 2
    assert (tmp_path / "public/run.json").read_bytes() == (run / "run.json").read_bytes()
