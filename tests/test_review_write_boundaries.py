from __future__ import annotations

import json
from pathlib import Path

import pytest

from smartmoney_cub_harness.cli import evaluate_run
from smartmoney_cub_harness.evidence_pack import build_evidence_pack, replay_evidence_pack
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _sample(root: Path) -> Path:
    run = root / "toy-run"
    run.mkdir()
    for name, data in {
        "run_manifest.json": {"run_id": "toy-run", "decision_time": "2026-07-10T09:30:00+08:00", "data_sources": []},
        "decision.json": {"action_label": "SILENT"},
        "outcome_d1.json": {"d1_return_pct": 0.0},
    }.items():
        (run / name).write_text(json.dumps({**data, "safety": SAFETY_DECLARATION}))
    return run


def test_evaluate_refuses_symlinked_output_file(tmp_path: Path):
    run = _sample(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("keep me")
    (run / "eval.json").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        evaluate_run(run)
    assert outside.read_text() == "keep me"


@pytest.mark.parametrize("relative", ["rule_candidate.json", "evidence_pack.json", "evidence_pack.sha256", "samples"])
def test_evidence_pack_refuses_symlinked_output_descendants(tmp_path: Path, relative: str):
    run = _sample(tmp_path)
    pack = tmp_path / "pack"
    pack.mkdir()
    outside = tmp_path / "outside"
    if relative == "samples":
        outside.mkdir()
    else:
        outside.write_text("keep me")
    (pack / relative).symlink_to(outside, target_is_directory=relative == "samples")
    with pytest.raises(ValueError, match="outside"):
        build_evidence_pack(pack, [run], {"rule_id": "toy-rule"})
    if outside.is_dir():
        assert list(outside.iterdir()) == []
    else:
        assert outside.read_text() == "keep me"


def test_replay_refuses_symlinked_report(tmp_path: Path):
    run = _sample(tmp_path)
    pack = tmp_path / "pack"
    build_evidence_pack(pack, [run], {"rule_id": "toy-rule"})
    outside = tmp_path / "outside.json"
    outside.write_text("keep me")
    (pack / "replay_report.json").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        replay_evidence_pack(pack)
    assert outside.read_text() == "keep me"
