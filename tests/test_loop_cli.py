from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(REPO_ROOT / "src")
REQUIRED_STEPS = [
    "resolve_agent_trigger",
    "doctor",
    "observe",
    "candidate",
    "plan",
    "position_check",
    "outcome",
    "evaluate",
    "review",
    "collect_case",
    "save_memory",
    "append_evolution_ledger",
    "propose_challenger_rule",
    "generate_report",
]
REQUIRED_ARTIFACT_KEYS = [
    "loop_report",
    "trace",
    "case_record",
    "memory_record",
    "ledger",
    "decision_path",
    "outcome_path",
    "evaluation_path",
    "proposed_challenger_rule_path",
    "rule_registry_path",
]
FORBIDDEN_PHRASES = [
    "buy now",
    "sell now",
    "guaranteed",
    "stock recommendation",
    "should buy",
    "sure win",
]
ABSOLUTE_PATH_RE = re.compile(r"(?i)([A-Z]:\\|/Users/|/home/)")


def run_cli(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC_PATH + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "smartmoney_cub_harness.cli", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_loop(*args: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run the loop with its artifacts isolated under tmp_path.

    Why this wrapper exists: every invocation used to write its run directories
    into the checkout, so a long-lived working tree accumulated
    tmp/sandbox/<day>/<stamp>-<n>/ until unique_run_dir's 999-sibling cap was
    reached and these tests began failing with "too many run directories" --
    a breakage the tests caused themselves and one that never reproduced on a
    fresh clone.

    The summary's artifact keys are relative to the run root, so a caller reads
    them as tmp_path/<key>. That keeps the assertions about output shape intact
    while leaving the repository untouched. The process working directory is
    also tmp_path, so a run that writes anything relative still lands there.
    """
    return run_cli("loop", *args, "--root", str(tmp_path), cwd=tmp_path)


def load_isolated(summary: dict, tmp_path: Path) -> tuple[str, str, list[dict]]:
    """Read a loop report and trace out of the isolated root."""
    report_text = (tmp_path / summary["loop_report"]).read_text(encoding="utf-8")
    trace_text = (tmp_path / summary["trace"]).read_text(encoding="utf-8")
    trace = [json.loads(line) for line in trace_text.splitlines() if line.strip()]
    return report_text, trace_text, trace


def load_summary(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def read_loop_outputs(summary: dict) -> tuple[str, str, list[dict]]:
    report_text = (REPO_ROOT / summary["loop_report"]).read_text(encoding="utf-8")
    trace_text = (REPO_ROOT / summary["trace"]).read_text(encoding="utf-8")
    trace = [json.loads(line) for line in trace_text.splitlines() if line.strip()]
    return report_text, trace_text, trace


def assert_no_local_path_leakage(*texts: str) -> None:
    for text in texts:
        assert not ABSOLUTE_PATH_RE.search(text)


def assert_forbidden_phrases_absent(*texts: str) -> None:
    lowered = "\n".join(texts).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in lowered


def test_loop_preset_toy_exits_successfully_and_prints_safe_summary(tmp_path: Path):
    result = run_loop("--preset", "toy", "--json", tmp_path=tmp_path)

    summary = load_summary(result)

    assert summary["status"] == "ok"
    assert summary["loop_name"] == "observe_candidate_plan_position_outcome_review_rule_update"
    assert summary["preset"] == "toy"
    assert summary["safety"] == SAFETY_DECLARATION
    assert summary["champion_mutated"] is False
    assert summary["network_required"] is False
    assert summary["telemetry"] is False
    assert summary["grade"] == "useful_alert"
    assert SAFETY_DECLARATION in result.stdout
    assert '"champion_mutated": false' in result.stdout


def test_loop_preset_toy_works_outside_repository(tmp_path: Path):
    result = run_cli("loop", "--preset", "toy", "--agent-trigger", "loop", "--json", cwd=tmp_path)

    summary = load_summary(result)

    assert summary["status"] == "ok"
    assert (tmp_path / summary["loop_report"]).is_file()
    assert (tmp_path / summary["trace"]).is_file()
    outcome = json.loads((tmp_path / summary["outcome_path"]).read_text(encoding="utf-8"))
    assert outcome["price_source"] == "smartmoney_cub_harness:data/sample_prices.json"
    assert str(tmp_path) not in json.dumps(outcome)


def test_loop_accepts_chinese_and_english_agent_triggers(tmp_path: Path):
    chinese = load_summary(run_loop("--preset", "toy", "--agent-trigger", "自进化", tmp_path=tmp_path))
    english = load_summary(run_loop("--preset", "toy", "--agent-trigger", "loop", tmp_path=tmp_path))

    assert chinese["status"] == "ok"
    assert english["status"] == "ok"
    assert chinese["agent_intent"] == "full_loop"
    assert english["agent_intent"] == "full_loop"


def test_loop_generates_report_trace_and_required_artifacts(tmp_path: Path):
    summary = load_summary(
        run_loop("--preset", "toy", "--agent-trigger", "loop", "--horizon", "d1", tmp_path=tmp_path)
    )

    for key in REQUIRED_ARTIFACT_KEYS:
        assert (tmp_path / summary[key]).exists(), key

    report_text, trace_text, trace = load_isolated(summary, tmp_path)
    doctor_output = next(line["output"] for line in trace if line["step"] == "doctor")
    case_record = json.loads((tmp_path / summary["case_record"]).read_text(encoding="utf-8"))
    memory_text = (tmp_path / summary["memory_record"]).read_text(encoding="utf-8")
    ledger_lines = (tmp_path / summary["ledger"]).read_text(encoding="utf-8").splitlines()

    assert [line["step"] for line in trace] == REQUIRED_STEPS
    assert all(line["safety"] == SAFETY_DECLARATION for line in trace)
    assert all(line["champion_mutated"] is False for line in trace)
    assert all(line["no_future_leakage"] is True for line in trace)
    assert doctor_output["network_required"] is False
    assert doctor_output["telemetry"] is False
    assert doctor_output["upload"] is False
    assert doctor_output["credentials_required"] is False
    assert doctor_output["github_auth_required"] is False
    assert doctor_output["external_api_required"] is False
    assert doctor_output["broker_api_required"] is False
    assert case_record["safety"] == SAFETY_DECLARATION
    assert "Smartmoney Cub Local Memory" in memory_text
    assert ledger_lines and json.loads(ledger_lines[0])["champion_mutated"] is False
    assert "Smartmoney Cub Agent Loop Report" in report_text
    assert "champion_mutated: false" in report_text
    result_text = json.dumps(summary, ensure_ascii=False)
    assert_no_local_path_leakage(result_text, report_text, trace_text, memory_text)
    assert_forbidden_phrases_absent(result_text, report_text, trace_text, memory_text)


def test_challenger_rule_proposal_does_not_mutate_champion_registry(tmp_path: Path):
    summary = load_summary(run_loop("--preset", "toy", "--agent-trigger", "规则进化", tmp_path=tmp_path))
    registry = json.loads((tmp_path / summary["rule_registry_path"]).read_text(encoding="utf-8"))
    proposal = json.loads((tmp_path / summary["proposed_challenger_rule_path"]).read_text(encoding="utf-8"))

    assert registry["champions"] == {}
    assert proposal["candidate_role"] == "challenger"
    assert proposal["champion_mutated"] is False
    assert proposal["requires_human_confirmation"] is True


def test_readme_demo_command_shape_works_with_current_source(tmp_path: Path):
    result = run_loop("--preset", "toy", "--agent-trigger", "loop", tmp_path=tmp_path)

    summary = load_summary(result)

    assert summary["status"] == "ok"
    assert summary["safety"] == SAFETY_DECLARATION
