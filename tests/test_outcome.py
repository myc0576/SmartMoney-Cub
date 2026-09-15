from __future__ import annotations

import json
from pathlib import Path

import pytest

from smartmoney_cub_harness.outcome import build_outcome, resolve_price_source


def test_packaged_price_source_reference_is_resolved() -> None:
    """README and loop output use a package resource reference; it must resolve."""
    resolved = resolve_price_source("smartmoney_cub_harness:data/sample_prices.json")
    assert resolved.is_file()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    assert isinstance(payload, dict) and payload


def test_plain_price_source_path_is_returned_unchanged() -> None:
    assert resolve_price_source("examples/toy/prices.json") == Path("examples/toy/prices.json")


def test_build_outcome_accepts_packaged_reference(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "decision.json").write_text(
        json.dumps(
            {
                "action_label": "ALERT",
                "decision_time": "2026-06-01T15:30:00+08:00",
                "symbol": "TOY.CUB",
            }
        ),
        encoding="utf-8",
    )
    prices = {
        "TOY.CUB": {
            "20260601": {"close": 10.0, "low": 9.5},
            "20260602": {"close": 11.0, "low": 10.2},
        }
    }
    price_path = tmp_path / "prices.json"
    price_path.write_text(json.dumps(prices), encoding="utf-8")

    outcome_path = build_outcome(run_dir, horizon="d1", price_source=resolve_price_source(price_path))
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["symbol"] == "TOY.CUB"


def _prices(path: Path) -> Path:
    price_path = path / "prices.json"
    price_path.write_text(
        json.dumps(
            {
                "TOY.CUB": {
                    "20260601": {"close": 10.0, "low": 9.9},
                    "20260602": {"close": 10.5, "low": 9.8, "met_user_pattern": True},
                    "20260604": {"close": 10.8, "low": 9.7, "met_user_pattern": True},
                },
                "TOY.BETA": {
                    "20260601": {"close": 8.0, "low": 7.9},
                    "20260602": {"close": 7.8, "low": 7.5},
                },
            }
        ),
        encoding="utf-8",
    )
    return price_path


def test_build_outcome_writes_d1_price_fields_with_provenance(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "decision.json").write_text(
        json.dumps({"symbol": "TOY.CUB", "decision_time": "2026-06-01T15:30:00+08:00"}),
        encoding="utf-8",
    )

    outcome_path = build_outcome(run_dir, horizon="d1", price_source=_prices(tmp_path))

    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["d1_return_pct"] == 5.0
    assert outcome["max_adverse_excursion_pct"] == -2.0
    assert outcome["met_user_pattern"] is True


def test_build_outcome_can_publish_logical_provenance_instead_of_physical_path(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "decision.json").write_text(
        json.dumps({"symbol": "TOY.CUB", "decision_time": "2026-06-01T15:30:00+08:00"}),
        encoding="utf-8",
    )

    outcome_path = build_outcome(
        run_dir,
        horizon="d1",
        price_source=_prices(tmp_path),
        price_source_label="smartmoney_cub_harness:data/sample_prices.json",
    )

    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["price_source"] == "smartmoney_cub_harness:data/sample_prices.json"
    assert str(tmp_path) not in outcome_path.read_text(encoding="utf-8")


def test_build_outcome_derives_symbol_from_artifact_candidate(tmp_path: Path):
    run_dir = tmp_path / "run"
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (run_dir / "decision.json").write_text(
        json.dumps({"action_label": "ALERT", "decision_time": "2026-06-01T15:30:00+08:00"}),
        encoding="utf-8",
    )
    (artifact_dir / "toy.stdout.txt").write_text(
        json.dumps({"observation_candidates": [{"symbol": "TOY.CUB"}]}),
        encoding="utf-8",
    )

    outcome_path = build_outcome(run_dir, horizon="d1", price_source=_prices(tmp_path))

    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["symbol"] == "TOY.CUB"


def test_build_outcome_rejects_ambiguous_artifact_codes(tmp_path: Path):
    run_dir = tmp_path / "run"
    artifact_dir = run_dir / "artifacts"
    artifact_dir.mkdir(parents=True)
    (run_dir / "decision.json").write_text(
        json.dumps({"action_label": "ALERT", "decision_time": "2026-06-01T15:30:00+08:00"}),
        encoding="utf-8",
    )
    (artifact_dir / "toy.stdout.txt").write_text(
        json.dumps({"context": [{"symbol": "TOY.CUB"}, {"symbol": "TOY.BETA"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ambiguous"):
        build_outcome(run_dir, horizon="d1", price_source=_prices(tmp_path))
