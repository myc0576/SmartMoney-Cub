from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.benchmark.cases import (
    BENCHMARK_ID,
    TRACK_IDS,
    load_cases,
    load_track,
)
from smartmoney_cub_harness.benchmark.render import render_images
from smartmoney_cub_harness.benchmark.runner import (
    compare_runs,
    run_benchmark,
    verify_run,
)
from smartmoney_cub_harness.safety import redact


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(redact(payload), ensure_ascii=False, indent=2))


def register_benchmark_commands(sub: Any) -> None:
    """Register benchmark CLI commands: run, verify, render, compare."""
    bench_cmd = sub.add_parser("benchmark", help="Financial reasoning benchmark harness (finance-jev-v1)")
    bench_sub = bench_cmd.add_subparsers(dest="benchmark_command", required=True)

    run_cmd = bench_sub.add_parser("run", help="Run benchmark across tracks and systems")
    run_cmd.add_argument("--tracks", nargs="+", choices=list(TRACK_IDS), help="Tracks to evaluate (default: all)")
    run_cmd.add_argument("--systems", nargs="+", help="Systems to evaluate (default: deterministic_baseline)")
    run_cmd.add_argument("--out-dir", default="artifacts/benchmark", help="Directory to save run JSON artifact")
    run_cmd.add_argument("--mode", choices=["all", "dev", "holdout"], default="all", help="Split filter (default: all)")
    run_cmd.add_argument("--live", action="store_true", default=False, help="Enable live evaluation for external model backends")
    run_cmd.add_argument("--limit-per-track", type=int, default=None, help="Limit number of cases evaluated per track")

    verify_cmd = bench_sub.add_parser("verify", help="Verify integrity of a benchmark run artifact")
    verify_cmd.add_argument("run_dir", help="Path to run directory or run.json")

    render_cmd = bench_sub.add_parser("render", help="Render scoring images (PNG and SVG) for a benchmark run")
    render_cmd.add_argument("run_dir", help="Path to run directory or run.json")
    render_cmd.add_argument("--out-dir", help="Output directory for images (default: artifacts/benchmark/<run_id>)")

    compare_cmd = bench_sub.add_parser("compare", help="Compare candidate run against baseline run")
    compare_cmd.add_argument("baseline", help="Path to baseline run directory or run.json")
    compare_cmd.add_argument("candidate", help="Path to candidate run directory or run.json")


def handle_benchmark_cli(args: argparse.Namespace) -> int:
    """Handle dispatch for benchmark subcommands."""
    if args.benchmark_command == "run":
        res = run_benchmark(
            tracks=args.tracks,
            systems=args.systems,
            out_dir=args.out_dir,
            mode=args.mode,
            live=getattr(args, "live", False),
            limit_per_track=getattr(args, "limit_per_track", None),
        )
        _print_json(res)
        return 0

    if args.benchmark_command == "verify":
        res = verify_run(args.run_dir)
        _print_json(res)
        return 0 if res.get("status") == "ok" else 2

    if args.benchmark_command == "render":
        files = render_images(args.run_dir, out_dir=args.out_dir)
        _print_json({"status": "ok", "rendered_files": files})
        return 0

    if args.benchmark_command == "compare":
        res = compare_runs(args.baseline, args.candidate)
        _print_json(res)
        return 0

    return 2

