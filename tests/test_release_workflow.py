from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_release_workflow_uses_tagged_github_releases_without_pypi():
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert 'tags: ["v*"]' in workflow
    assert 'environment: pypi' not in workflow
    assert 'id-token: write' not in workflow
    assert 'pypa/gh-action-pypi-publish@release/v1' not in workflow
    assert 'PYPI_TOKEN' not in workflow
    assert 'password:' not in workflow


def test_release_workflow_validates_version_and_publishes_release_assets():
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert 'Verify tag matches package version' in workflow
    assert 'python -m build' in workflow
    assert 'Verify installed toy loop outside checkout' in workflow
    assert 'smcub loop --preset toy' in workflow
    assert 'smcub inspect-artifacts' in workflow
    assert 'mktemp -d' in workflow
    assert 'actions/upload-artifact@v4' in workflow
    assert 'actions/download-artifact@v4' in workflow
    # The release now waits for both the Python distributions and the npm
    # launcher package, so neither can be published from a stale build.
    assert 'needs: [build, npm-package]' in workflow
    assert 'node --check npm/bin/smartmoney-cub.js' in workflow
    assert 'npm pack' in workflow
    assert 'gh release create' in workflow
    assert '--repo "${GITHUB_REPOSITORY}"' in workflow
    assert 'dist/*' in workflow
