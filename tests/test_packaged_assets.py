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
