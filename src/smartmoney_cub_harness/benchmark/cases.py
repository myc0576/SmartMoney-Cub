from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

BENCHMARK_ID = "finance-jev-v1"
BENCHMARK_CASE_SCHEMA = "smartmoney_cub_benchmark_case.v1"

CASES_PER_TRACK = 60
DEV_PER_TRACK = 30
HOLDOUT_PER_TRACK = 30

TRACK_TRADING_REVIEW = "trading-review"
TRACK_FINANCIAL_FILINGS = "financial-filings"
TRACK_INDUSTRY_EVENTS = "industry-events"
TRACK_MACRO_POLICY = "macro-policy"

TRACK_IDS: tuple[str, ...] = (
    TRACK_TRADING_REVIEW,
    TRACK_FINANCIAL_FILINGS,
    TRACK_INDUSTRY_EVENTS,
    TRACK_MACRO_POLICY,
)


@dataclass(frozen=True)
class BenchmarkCase:
    """A frozen benchmark test case for financial reasoning evaluation."""

    case_id: str
    track: str
    split: str
    state: dict[str, Any]
    labels: dict[str, Any]
    source: str = "toy_offline_generator"
    network_required: bool = False
    benchmark_id: str = BENCHMARK_ID
    schema: str = BENCHMARK_CASE_SCHEMA
    safety: str = SAFETY_DECLARATION

    def __post_init__(self) -> None:
        if self.safety != SAFETY_DECLARATION:
            raise ValueError(f"safety declaration mismatch: expected {SAFETY_DECLARATION}")
        if self.track not in TRACK_IDS:
            raise ValueError(f"unknown track '{self.track}'. Must be one of {TRACK_IDS}")
        if self.split not in ("dev", "holdout"):
            raise ValueError(f"split must be 'dev' or 'holdout', got '{self.split}'")
        if self.network_required is not False:
            raise ValueError("network_required must be False for offline benchmark cases")

        # Invariant: temporal validity
        dt = self.state.get("decision_time")
        if dt:
            dt_str = str(dt)
            avail = self.state.get("available_at")
            if avail and str(avail) > dt_str:
                raise ValueError(
                    f"future leakage: available_at ({avail}) > decision_time ({dt_str})"
                )
            for src in self.state.get("data_sources", []):
                if isinstance(src, Mapping):
                    s_avail = src.get("available_at")
                    if s_avail and str(s_avail) > dt_str:
                        raise ValueError(
                            f"future leakage in data_source: {s_avail} > {dt_str}"
                        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BenchmarkCase:
        return cls(
            case_id=str(data["case_id"]),
            track=str(data["track"]),
            split=str(data["split"]),
            state=dict(data.get("state", {})),
            labels=dict(data.get("labels", {})),
            source=str(data.get("source", "toy_offline_generator")),
            network_required=bool(data.get("network_required", False)),
            benchmark_id=str(data.get("benchmark_id", BENCHMARK_ID)),
            schema=str(data.get("schema", BENCHMARK_CASE_SCHEMA)),
            safety=str(data.get("safety", SAFETY_DECLARATION)),
        )


def load_cases(path: str | Path) -> list[BenchmarkCase]:
    """Load benchmark cases from a JSONL file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"cases file not found: {path}")

    cases: list[BenchmarkCase] = []
    with p.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            data = json.loads(line_str)
            cases.append(BenchmarkCase.from_dict(data))
    return cases


def load_track(track: str, base_dir: str | Path | None = None) -> list[BenchmarkCase]:
    """Load all 60 cases for a given track from benchmarks/finance-jev-v1/<track>.jsonl."""
    if track not in TRACK_IDS:
        raise ValueError(f"unknown track '{track}'. Must be one of {TRACK_IDS}")

    if base_dir is None:
        current = Path.cwd()
        candidate = current / "benchmarks" / BENCHMARK_ID / f"{track}.jsonl"
        if candidate.exists():
            return load_cases(candidate)

        pkg_root = Path(__file__).resolve().parent.parent.parent.parent
        candidate = pkg_root / "benchmarks" / BENCHMARK_ID / f"{track}.jsonl"
        if candidate.exists():
            return load_cases(candidate)
        raise FileNotFoundError(f"cannot find benchmark file for track '{track}'")

    track_path = Path(base_dir) / f"{track}.jsonl"
    return load_cases(track_path)
