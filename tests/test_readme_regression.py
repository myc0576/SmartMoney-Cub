"""Regression tests protecting the README presentation layer.

Guards cover images, safety declarations, documentation matrix links,
synchronization of open-source integration matrices, status vocabulary,
and ensures no runtime integration is claimed without backing code and tests.

These tests are offline, dependency-free, and read repository files only.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

README_EN = REPO_ROOT / "README.md"
README_ZH = REPO_ROOT / "README.zh-CN.md"
INTEGRATIONS_DOC = REPO_ROOT / "docs" / "integrations.md"

COVER_PATH = "assets/smartmoney-cub-harness-cover.png"
SAFETY_DECLARATION = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"

CONFLICT_MARKER_RE = re.compile(r"^(<{7}( |$)|={7}$|>{7}( |$))", re.MULTILINE)

# Projects allowed to claim `runtime-integrated` must have runtime code
# and tests inside this repository. Keep this map in sync with reality.
RUNTIME_EVIDENCE = {
    "tradingagents": (
        REPO_ROOT / "src" / "smartmoney_cub_harness" / "tradingagents_adapter.py",
        REPO_ROOT / "tests" / "test_tradingagents_adapter.py",
    ),
}

SIX_OPEN_SOURCE_PROJECTS = (
    ("akfamily/akshare", "AKShare"),
    ("microsoft/qlib", "Qlib"),
    ("amazon-science/chronos-forecasting", "Chronos"),
    ("google-research/timesfm", "TimesFM"),
    ("Nixtla/neuralforecast", "NeuralForecast"),
    ("AI4Finance-Foundation/FinRobot", "FinRobot"),
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_both_readmes_reference_cover_and_carry_safety_declaration():
    en = read(README_EN)
    zh = read(README_ZH)
    assert COVER_PATH in en, "README.md must show the cover image"
    assert "README.zh-CN.md" in en, "README.md must link to the Chinese README"
    assert SAFETY_DECLARATION in en, "README.md must carry safety declaration"

    assert COVER_PATH in zh, "README.zh-CN.md must show the cover image"
    assert "README.md" in zh, "README.zh-CN.md must link to the English README"
    assert SAFETY_DECLARATION in zh, "README.zh-CN.md must carry safety declaration"


def test_both_readmes_link_to_integrations_doc_and_have_matrix_section():
    en = read(README_EN)
    zh = read(README_ZH)

    assert "## Open-Source Integration Matrix" in en, (
        "README.md must contain the Open-Source Integration Matrix section"
    )
    assert "docs/integrations.md" in en, "README.md must link to docs/integrations.md"

    assert "## 优秀开源项目集成矩阵" in zh, (
        "README.zh-CN.md must contain 优秀开源项目集成矩阵 section"
    )
    assert "docs/integrations.md" in zh, "README.zh-CN.md must link to docs/integrations.md"


def test_no_merge_conflict_markers_in_presentation_files():
    files = [README_EN, README_ZH, *sorted((REPO_ROOT / "docs").glob("*.md"))]
    for path in files:
        assert not CONFLICT_MARKER_RE.search(read(path)), f"conflict marker in {path.name}"


def test_cover_asset_exists_and_is_not_empty():
    cover = REPO_ROOT / COVER_PATH
    assert cover.is_file(), "cover image referenced by both READMEs must exist"
    assert cover.stat().st_size > 0


def test_runtime_integrated_claims_are_backed_by_code_and_tests():
    """Any matrix row claiming `runtime-integrated` must map to real runtime
    code and tests in this repository. Plans and manifests do not count."""
    for path in (README_EN, README_ZH, INTEGRATIONS_DOC):
        for line in read(path).splitlines():
            if "runtime-integrated" not in line:
                continue
            stripped = line.lstrip()
            if not stripped.startswith("|"):
                # prose may mention the status
                continue
            # The status-vocabulary DEFINITION row in docs/integrations.md declares the
            # status itself (| `runtime-integrated` | Code, tests, ... |) and is not a
            # project claim, so it is exempt. Escape the pipes and use \s: an unescaped
            # leading '|' is regex alternation matching the empty string on every line,
            # which silently turned every assertion below into dead code.
            if re.match(r"^\|\s*`runtime-integrated`\s*\|", stripped):
                # status-vocabulary definition row, not a project claim
                continue
            # A table row making the claim must name a known project with evidence.
            lowered = line.lower()
            evidence = [v for k, v in RUNTIME_EVIDENCE.items() if k in lowered]
            assert evidence, (
                f"{path.name} claims runtime-integrated without registered evidence: {line}"
            )
            for code_path, test_path in evidence:
                assert code_path.is_file(), f"missing runtime code {code_path}"
                assert test_path.is_file(), f"missing runtime test {test_path}"


def test_integration_statuses_in_readmes_use_shared_vocabulary():
    """READMEs may only use statuses defined in docs/integrations.md so the
    condensed matrix cannot drift into invented labels."""
    vocabulary = {
        "recommended-companion",
        "reserved-slot",
        "documented-adapter",
        "optional-bridge",
        "runtime-integrated",
    }
    doc = read(INTEGRATIONS_DOC)
    for status in vocabulary:
        assert f"`{status}`" in doc, f"docs/integrations.md must define `{status}`"

    status_re = re.compile(r"`([a-z]+(?:-[a-z]+)+)`")
    known_non_status = {"read-only", "local-first", "human-in-the-loop", "toy-only", "after-close"}
    for path in (README_EN, README_ZH):
        in_matrix = False
        for line in read(path).splitlines():
            if line.startswith("## "):
                in_matrix = "Integration Matrix" in line or "集成矩阵" in line
                continue
            if not in_matrix or not line.lstrip().startswith("|"):
                continue
            for token in status_re.findall(line):
                if token in known_non_status:
                    continue
                if token.count("-") >= 1 and any(
                    token.startswith(prefix)
                    for prefix in ("recommended", "reserved", "documented", "optional", "runtime", "catalog", "adapter")
                ):
                    assert token in vocabulary, (
                        f"{path.name} uses undefined integration status `{token}`"
                    )


def test_six_open_source_projects_appear_in_integrations_doc():
    """Verify all six target open-source projects are recorded in docs/integrations.md."""
    doc = read(INTEGRATIONS_DOC)
    for repo, name in SIX_OPEN_SOURCE_PROJECTS:
        assert repo in doc or name in doc, (
            f"Missing {name} ({repo}) in docs/integrations.md"
        )
