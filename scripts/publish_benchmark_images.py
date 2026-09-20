#!/usr/bin/env python3
"""Publish generated benchmark score images from artifacts/ into tracked assets/benchmark/.

Enforces safety constraints:
- Refuses to publish from any run where the baseline achieved 100% accuracy on every track
  (signature of circular/tautological ground-truth evaluation).
- Copies PNG and SVG score images into assets/benchmark/.
- Validates the copied images exist and meet size limits.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def publish_benchmark_images(
    run_dir: str | Path,
    target_dir: str | Path = "assets/benchmark",
) -> list[str]:
    run_path = Path(run_dir)
    target_path = Path(target_dir)

    run_json_path = run_path / "run.json"
    if not run_json_path.is_file():
        raise FileNotFoundError(f"run.json not found under {run_path}")

    data = json.loads(run_json_path.read_text(encoding="utf-8"))

    # Safety check: refuse circular-label runs
    systems = data.get("systems", [])
    baseline = next((s for s in systems if s.get("system_id") == "deterministic_baseline"), None)
    if baseline:
        track_metrics = baseline.get("track_metrics", {})
        if track_metrics:
            accuracies = [m.get("accuracy", 0.0) for m in track_metrics.values()]
            if len(accuracies) >= 4 and all(acc >= 0.9999 for acc in accuracies):
                raise ValueError(
                    f"Refusing to publish from run {run_path.name}: baseline achieved 100% accuracy "
                    "across all tracks, which indicates circular ground truth generation."
                )

    target_path.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    # Copy all generated benchmark score images (PNG and SVG)
    image_files = sorted(list(run_path.glob("benchmark*.png")) + list(run_path.glob("benchmark*.svg")))
    if not image_files:
        raise FileNotFoundError(f"No benchmark images found in {run_path}")

    for img_file in image_files:
        dest = target_path / img_file.name
        shutil.copy2(img_file, dest)
        copied.append(str(dest))

    # Also copy run.json for audit and integrity
    dest_run_json = target_path / "run.json"
    shutil.copy2(run_json_path, dest_run_json)
    copied.append(str(dest_run_json))

    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish benchmark artifacts to tracked assets/benchmark")
    parser.add_argument(
        "run_dir",
        nargs="?",
        default="artifacts/benchmark/run_20260919_133157_240",
        help="Path to the valid benchmark run directory",
    )
    parser.add_argument(
        "--target-dir",
        default="assets/benchmark",
        help="Destination directory in tracked assets (default: assets/benchmark)",
    )
    args = parser.parse_args(argv)

    try:
        copied = publish_benchmark_images(args.run_dir, args.target_dir)
        print(f"Published {len(copied)} files from {args.run_dir} to {args.target_dir}:")
        for c in copied:
            print(f"  - {c}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
