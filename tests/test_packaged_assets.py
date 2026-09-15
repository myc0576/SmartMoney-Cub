from __future__ import annotations

import re
from pathlib import Path

from smartmoney_cub_harness.dashboard.server import TEMPLATES_DIR

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_template_is_packaged() -> None:
    """The dashboard must ship its template, or an installed copy breaks."""
    assert (TEMPLATES_DIR / "index.html").is_file()


def test_package_data_declares_dashboard_templates_and_data() -> None:
    payload = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"\[tool\.setuptools\.package-data\]\n(.*?)(?=\n\[)", payload, re.S)
    assert match is not None
    block = match.group(1)
    assert "dashboard/templates/*.html" in block
    assert "data/*.json" in block


def test_core_distribution_has_no_runtime_dependencies() -> None:
    """Plugins bring their own dependencies; the core must stay installable offline."""
    payload = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^dependencies\s*=\s*(\[.*?\])", payload)
    assert match is not None
    assert match.group(1).strip() == "[]"


def test_reference_plugin_example_is_present() -> None:
    plugin_dir = REPO_ROOT / "examples" / "toy_plugin"
    assert (plugin_dir / "plugin.json").is_file()
    assert (plugin_dir / "provider.py").is_file()


# ---- repository hygiene --------------------------------------------------
#
# A hardcoded absolute path ties a script to one machine and publishes that
# machine's account name and layout. One reached the tree this way: the visual
# harness required playwright by absolute path, so it could only run on its
# author's checkout -- including in CI, which checks the repository out
# somewhere else -- and the file recorded a local user's home directory.
#
# The rule is scoped to what actually ships: the installed package, the scripts
# a deployment runs, and the shipping configuration. Test fixtures are exempt
# because several exist precisely to prove the redactor catches a home path,
# and the redactor's own pattern list must name the shapes it removes.

_PATH_EXEMPT_FILES = (
    "tests/test_share_pack.py",
    "tests/test_redaction.py",
    "tests/test_memory_redaction.py",
    "tests/test_loop_cli.py",
    "tests/test_case_bank.py",
    "tests/test_packaged_assets.py",
    "src/smartmoney_cub_harness/privacy_audit.py",
    "src/smartmoney_cub_harness/safety.py",
    "src/smartmoney_cub_harness/redaction.py",
)

_SHIPPING_GLOBS = ("src/**/*.py", "scripts/**/*.cjs", "scripts/**/*.js", "scripts/**/*.py",
                   "scripts/**/*.sh", "deploy/**/*")

_LOCAL_PATH_RE = re.compile(r"/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/|C:\\\\Users\\\\")


def test_shipping_files_do_not_hardcode_a_local_absolute_path() -> None:
    """What ships must run wherever it is checked out."""
    offenders: list[str] = []
    seen: set[str] = set()
    for pattern in _SHIPPING_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if not path.is_file():
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            if relative in seen or relative in _PATH_EXEMPT_FILES:
                continue
            seen.add(relative)
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if _LOCAL_PATH_RE.search(line):
                    offenders.append(f"{relative}:{line_number}: {line.strip()[:80]}")
    assert not offenders, "shipping files hardcode a local path: " + "; ".join(offenders)
