from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from smartmoney_cub_harness import __version__
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "smartmoney_cub_harness.cli", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_documented_control_plane_sequence_is_executable(tmp_path):
    """The advertised toy workflow must run exactly as documented."""
    decision_dir = tmp_path / "run"
    decision_time = "2026-06-01T15:31:00+08:00"

    capture = run_cli(
        "capture-run",
        "--mode",
        "after-close",
        "--preset",
        "toy",
        "--root",
        str(tmp_path),
        "--decision-time",
        decision_time,
    )
    assert capture.returncode == 0, capture.stderr
    captured = json.loads(capture.stdout)
    assert captured["run_dir"]

    # CLI output redacts absolute paths, so locate the run directory on disk.
    run_dirs = sorted(p for p in tmp_path.rglob("run_manifest.json"))
    assert len(run_dirs) == 1, run_dirs
    run_dir = run_dirs[0].parent

    # build-outcome must accept the package resource reference the toy loop records.
    outcome = run_cli(
        "build-outcome",
        str(run_dir),
        "--horizon",
        "d1",
        "--price-source",
        "smartmoney_cub_harness:data/sample_prices.json",
    )
    assert outcome.returncode == 0, outcome.stderr
    assert json.loads(outcome.stdout)["status"] == "ok"

    evaluated = run_cli("evaluate-run", str(run_dir), "--horizon", "d1")
    assert evaluated.returncode == 0, evaluated.stderr
    assert json.loads(evaluated.stdout)["status"] == "evaluated"
def test_readme_quick_start_loop_command_is_real(tmp_path):
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    zh_readme = (REPO_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    command = 'smcub loop --preset toy --agent-trigger "自进化"'

    assert command in readme
    assert command in zh_readme
    assert SAFETY_DECLARATION in readme
    assert SAFETY_DECLARATION in zh_readme

    # The documented invocation is checked verbatim above; here the same loop is
    # run with its artifacts rooted in tmp_path. Running it against the checkout
    # accumulated run directories in the repository until unique_run_dir's
    # 999-sibling cap was hit and this test began failing for a reason that had
    # nothing to do with the README.
    result = run_cli(
        "loop", "--preset", "toy", "--agent-trigger", "自进化",
        "--root", str(tmp_path), cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["loop_report"].endswith("loop_report.md")
    assert payload["trace"].endswith("trace.jsonl")
    assert payload["safety"] == SAFETY_DECLARATION


def test_readme_points_to_integration_contract():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    integrations = (REPO_ROOT / "docs" / "integrations.md").read_text(encoding="utf-8")

    assert "wbh604/UZI-Skill" in readme
    assert "docs/integrations.md" in readme
    assert "recommended-companion" in integrations
    assert "runtime-integrated" in integrations
    assert SAFETY_DECLARATION in integrations


def test_readmes_document_isolated_installation_and_cli_upgrades():
    readmes = [
        (REPO_ROOT / "README.md").read_text(encoding="utf-8"),
        (REPO_ROOT / "README.zh-CN.md").read_text(encoding="utf-8"),
    ]

    for readme in readmes:
        assert "python -m venv .venv" in readme
        assert "py -m venv .venv" in readme
        assert "pipx install smartmoney-cub-harness" in readme
        assert "pipx upgrade smartmoney-cub-harness" in readme
        assert "smcub --version" in readme
        assert "docs/versioning.md" in readme


def test_versioning_policy_covers_all_supported_update_paths():
    policy = (REPO_ROOT / "docs" / "versioning.md").read_text(encoding="utf-8")

    assert "Semantic Versioning" in policy
    assert "git pull" in policy
    assert "python -m pip install --upgrade smartmoney-cub-harness" in policy
    assert "pipx upgrade smartmoney-cub-harness" in policy
    assert "Trusted Publishing" in policy
    assert "vX.Y.Z" in policy
    assert "does not update automatically" in policy.lower()
    assert "Current release channel: GitHub Releases" in policy
    # The repository was renamed; the clone URL in the policy has to name the
    # repository that actually exists, or a user following the upgrade path hits
    # a redirect (or, for a push, the wrong remote).
    assert f"git+https://github.com/myc0576/SmartMoney-Cub.git@v{__version__}" in policy


def test_local_virtual_environment_is_ignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert ".venv/" in gitignore


def test_readmes_document_control_plane_commands_and_boundaries():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    zh_readme = (REPO_ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    for command in ("capture-run", "validate-envelope", "build-evidence-pack", "replay-evidence-pack"):
        assert command in readme
        assert command in zh_readme

    for phrase in (
        "local-first",
        "agent-agnostic",
        "no embedded LLM",
        "no broker connection",
        "no automatic trading",
        "declarative, unverified policy record",
        "not a subprocess sandbox",
        "only selects the disposable `tmp/sandbox` output namespace",
        "evidence_pack.sha256",
    ):
        assert phrase in readme
    for phrase in (
        "本地优先",
        "不绑定任何 Agent",
        "不内置 LLM",
        "不连接券商",
        "不自动交易",
        "声明式、未经验证的策略记录",
        "不是子进程沙箱",
        "只选择一次性的 `tmp/sandbox` 输出目录",
        "evidence_pack.sha256",
    ):
        assert phrase in zh_readme


def test_toy_rule_candidate_is_challenger_only_and_read_only():
    candidate = json.loads(
        (REPO_ROOT / "examples" / "toy_strategy" / "sample_rule_candidate.json").read_text(
            encoding="utf-8"
        )
    )
    assert candidate["candidate_role"] == "challenger"
    assert candidate["champion_mutated"] is False
    assert candidate["core_rules_mutated"] is False
    assert candidate["safety"] == SAFETY_DECLARATION


def test_architecture_distinguishes_declared_policy_from_enforcement():
    architecture = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "`enforcement: declarative`" in architecture
    assert "`verified: false`" in architecture
    assert "does not sandbox arbitrary captured commands" in architecture
    assert "governance commands may write local evidence and registry artifacts" in architecture
    assert "not an authenticated signature" in architecture
    assert "`register-candidate --confirm-promote`" in architecture
