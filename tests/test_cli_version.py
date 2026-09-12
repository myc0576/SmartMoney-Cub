from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from smartmoney_cub_harness import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_cli_version_matches_package_version():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "smartmoney_cub_harness.cli", "--version"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"smcub {__version__}"
    assert __version__ == "0.2.0"


def test_build_metadata_uses_package_version_attribute():
    payload = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'dynamic = ["version"]' in payload
    assert re.search(r"(?m)^version\s*=\s*['\"]", payload) is None
    assert '[tool.setuptools.dynamic]' in payload
    assert 'version = { attr = "smartmoney_cub_harness.__version__" }' in payload
