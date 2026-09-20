from __future__ import annotations

import json
from pathlib import Path
import pytest

pytest.importorskip("PIL", reason="Pillow is required for benchmark render tests")
from PIL import Image

from smartmoney_cub_harness.benchmark.render import render_images
from smartmoney_cub_harness.benchmark.runner import run_benchmark
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_render_refuses_when_run_hash_missing(tmp_path: Path):
    run_file = tmp_path / "run.json"
    run_file.write_text(
        json.dumps({
            "run_id": "test_run_1",
            "sample_count": 60,
            "systems": [{"system_id": "s1", "model_resolved": "m1"}],
            "safety": SAFETY_DECLARATION,
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="run_hash is missing"):
        render_images(tmp_path)


def test_render_refuses_when_sample_count_missing(tmp_path: Path):
    run_file = tmp_path / "run.json"
    run_file.write_text(
        json.dumps({
            "run_id": "test_run_2",
            "run_hash": "abcdef123456",
            "systems": [{"system_id": "s1", "model_resolved": "m1"}],
            "safety": SAFETY_DECLARATION,
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sample_count is missing"):
        render_images(tmp_path)


def test_render_refuses_when_model_version_missing(tmp_path: Path):
    run_file = tmp_path / "run.json"
    run_file.write_text(
        json.dumps({
            "run_id": "test_run_3",
            "run_hash": "abcdef123456",
            "sample_count": 60,
            "systems": [{"system_id": "s1"}],
            "safety": SAFETY_DECLARATION,
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="model/version is missing"):
        render_images(tmp_path)


def test_render_images_full_suite_and_exact_match(tmp_path: Path):
    out_bench = tmp_path / "bench_out"
    res = run_benchmark(
        tracks=["trading-review", "financial-filings", "industry-events", "macro-policy"],
        systems=["deterministic_baseline"],
        mode="all",
        out_dir=out_bench,
    )
    run_dir = out_bench / res["run_id"]
    images_dir = tmp_path / "rendered_artifacts"

    created = render_images(run_dir, out_dir=images_dir)
    assert len(created) == 18  # 9 PNGs + 9 SVGs

    expected_files = [
        "benchmark-hero-1200x630.png",
        "benchmark-hero-1200x630.svg",
        "benchmark-leaderboard.png",
        "benchmark-leaderboard.svg",
        "benchmark-domain-trading-review.png",
        "benchmark-domain-trading-review.svg",
        "benchmark-domain-financial-filings.png",
        "benchmark-domain-financial-filings.svg",
        "benchmark-domain-industry-events.png",
        "benchmark-domain-industry-events.svg",
        "benchmark-domain-macro-policy.png",
        "benchmark-domain-macro-policy.svg",
        "benchmark-calibration.png",
        "benchmark-calibration.svg",
        "benchmark-quality-cost-latency.png",
        "benchmark-quality-cost-latency.svg",
        "benchmark-card-compact.png",
        "benchmark-card-compact.svg",
    ]
    for fname in expected_files:
        fpath = images_dir / fname
        assert fpath.exists(), f"Expected file {fname} not found"

    # Verify hero PNG dimensions
    hero_png = images_dir / "benchmark-hero-1200x630.png"
    with Image.open(hero_png) as im:
        assert im.size == (1200, 630)

    # Verify compact card PNG dimensions
    card_png = images_dir / "benchmark-card-compact.png"
    with Image.open(card_png) as im:
        assert im.size == (600, 360)

    # Verify numbers in SVG match run.json exactly
    base_metrics = res["systems"][0]["metrics"]
    acc_pct = f"{base_metrics["accuracy"]:.2%}"
    f1_val = f"{base_metrics["macro_f1"]:.4f}"
    ece_val = f"{base_metrics["ece"]:.4f}"
    safety_decl = SAFETY_DECLARATION

    hero_svg_text = (images_dir / "benchmark-hero-1200x630.svg").read_text(encoding="utf-8")
    assert acc_pct in hero_svg_text
    assert f1_val in hero_svg_text
    assert ece_val in hero_svg_text
    assert safety_decl in hero_svg_text
    assert res["run_hash"][:16] in hero_svg_text


def test_svg_renders_unmeasured_systems_matching_png(tmp_path: Path):
    out_bench = tmp_path / "bench_out"
    res = run_benchmark(
        tracks=["macro-policy"],
        systems=["deterministic_baseline", "typesafe_direct", "openrouter_jev"],
        mode="dev",
        out_dir=out_bench,
    )
    run_dir = out_bench / res["run_id"]
    images_dir = tmp_path / "rendered_artifacts"

    render_images(run_dir, out_dir=images_dir)

    hero_svg_text = (images_dir / "benchmark-hero-1200x630.svg").read_text(encoding="utf-8")
    lead_svg_text = (images_dir / "benchmark-leaderboard.svg").read_text(encoding="utf-8")

    for sys_id in ("deterministic_baseline", "typesafe_direct", "openrouter_jev"):
        assert sys_id in hero_svg_text, f"{sys_id} missing from hero SVG"
        assert sys_id in lead_svg_text, f"{sys_id} missing from leaderboard SVG"

    assert "not_run" in hero_svg_text
    assert "not_run" in lead_svg_text


def test_render_images_raises_actionable_error_when_pillow_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import smartmoney_cub_harness.benchmark.render as render_mod

    run_file = tmp_path / "run.json"
    run_file.write_text(
        json.dumps({
            "run_id": "test_run_no_pillow",
            "run_hash": "abcdef123456",
            "sample_count": 60,
            "systems": [{"system_id": "s1", "model_resolved": "m1"}],
            "safety": SAFETY_DECLARATION,
        }),
        encoding="utf-8",
    )

    def mock_require_pillow():
        raise RuntimeError(
            "Pillow is required for benchmark image rendering. "
            'Install it with: pip install -e ".[benchmark]"'
        )

    monkeypatch.setattr(render_mod, "_require_pillow", mock_require_pillow)
    with pytest.raises(RuntimeError, match=r'pip install -e "\.\[benchmark\]"'):
        render_mod.render_images(tmp_path)
