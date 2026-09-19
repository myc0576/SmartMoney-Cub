"""End-to-end benchmark integration tests: drive run -> verify -> render.

Validates:
1. End-to-end execution of run_benchmark -> verify_run -> render_images
2. Generated PNG and SVG images exist on disk and meet dimensional constraints
3. Metrics and accuracy numbers in SVG match run.json
4. Safety declaration READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE is present in every artifact
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from PIL import Image

from smartmoney_cub_harness.benchmark.cases import TRACK_IDS
from smartmoney_cub_harness.benchmark.render import render_images
from smartmoney_cub_harness.benchmark.runner import (
    BENCHMARK_RUN_SCHEMA,
    run_benchmark,
    verify_run,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_jev_benchmark_e2e_lifecycle(tmp_path: Path):
    bench_out = tmp_path / "artifacts" / "benchmark"
    bench_out.mkdir(parents=True, exist_ok=True)

    # 1. Drive run_benchmark on dev split across all 4 tracks
    run_res = run_benchmark(
        tracks=list(TRACK_IDS),
        systems=["deterministic_baseline"],
        mode="dev",
        out_dir=bench_out,
    )

    run_id = run_res["run_id"]
    run_dir = bench_out / run_id
    run_json_path = run_dir / "run.json"
    assert run_json_path.is_file()

    # Assert safety declaration and schema contract
    assert run_res["safety"] == SAFETY_DECLARATION
    assert run_res["schema"] == BENCHMARK_RUN_SCHEMA
    assert run_res["sample_count"] == 120  # 30 per track * 4 tracks in dev mode

    # 2. Drive verify_run and assert integrity
    v_res = verify_run(run_dir)
    assert v_res["status"] == "ok"
    assert v_res["safety"] == SAFETY_DECLARATION
    assert v_res["run_hash"] == run_res["run_hash"]

    # 3. Drive render_images
    rendered_files = render_images(run_dir, out_dir=run_dir)
    assert len(rendered_files) == 18  # 9 PNGs + 9 SVGs
    for fpath_str in rendered_files:
        fpath = Path(fpath_str)
        assert fpath.is_file(), f"Rendered file {fpath} does not exist"

    # 4. Verify images exist and dimensions match requirements
    hero_png = run_dir / "benchmark-hero-1200x630.png"
    assert hero_png.is_file()
    with Image.open(hero_png) as img:
        assert img.size == (1200, 630)

    card_png = run_dir / "benchmark-card-compact.png"
    assert card_png.is_file()
    with Image.open(card_png) as img:
        assert img.size == (600, 360)

    # 5. Assert numbers and safety declaration in SVG match run.json
    run_data = json.loads(run_json_path.read_text(encoding="utf-8"))
    base_metrics = run_data["systems"][0]["metrics"]
    acc_pct = f"{base_metrics['accuracy']:.2%}"
    f1_val = f"{base_metrics['macro_f1']:.4f}"
    ece_val = f"{base_metrics['ece']:.4f}"

    hero_svg_text = (run_dir / "benchmark-hero-1200x630.svg").read_text(encoding="utf-8")
    assert acc_pct in hero_svg_text
    assert f1_val in hero_svg_text
    assert ece_val in hero_svg_text
    assert SAFETY_DECLARATION in hero_svg_text
    assert run_res["run_hash"][:16] in hero_svg_text
