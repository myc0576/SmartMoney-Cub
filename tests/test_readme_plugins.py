"""Guard: the curated catalog, the READMEs, and the docs must not drift apart.

The catalog is the single source of truth for which open-source projects ship in
the marketplace. The bilingual READMEs and docs/integrations.md restate that list
for readers who never open the interface, so a project added to the catalog but
missing from the prose -- or removed from the catalog but left in the prose --
is a documentation defect. These tests fail on that drift rather than trusting
whoever edited last.
"""

from __future__ import annotations

from pathlib import Path

from smartmoney_cub_harness.plugins.catalog import catalog_entries
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
README_ZH = REPO_ROOT / "README.zh-CN.md"
INTEGRATIONS = REPO_ROOT / "docs" / "integrations.md"

CURATED_HEADING_EN = "## Curated Open-Source Projects"
CURATED_HEADING_ZH = "## 收录的开源项目"


def _entry_is_named(text: str, entry: dict) -> bool:
    """A row may name a project by id, display name, or upstream URL."""
    identifiers = (
        entry["plugin_id"],
        entry["name"],
        entry["repo"],
        # A built-in has no URL to link, so the row names it by its repo scheme.
        entry["repo"].removeprefix("builtin://"),
    )
    return any(identifier and identifier in text for identifier in identifiers)


def test_readmes_carry_the_curated_section() -> None:
    assert CURATED_HEADING_EN in README.read_text(encoding="utf-8")
    assert CURATED_HEADING_ZH in README_ZH.read_text(encoding="utf-8")


def test_english_readme_covers_every_catalog_entry() -> None:
    text = README.read_text(encoding="utf-8")
    missing = [e["plugin_id"] for e in catalog_entries() if not _entry_is_named(text, e)]
    assert not missing, f"README.md is missing curated projects: {missing}"


def test_chinese_readme_covers_every_catalog_entry() -> None:
    text = README_ZH.read_text(encoding="utf-8")
    missing = [e["plugin_id"] for e in catalog_entries() if not _entry_is_named(text, e)]
    assert not missing, f"README.zh-CN.md is missing curated projects: {missing}"


def test_integrations_doc_covers_every_catalog_entry() -> None:
    text = INTEGRATIONS.read_text(encoding="utf-8")
    missing = [e["plugin_id"] for e in catalog_entries() if not _entry_is_named(text, e)]
    assert not missing, f"docs/integrations.md is missing curated projects: {missing}"


def test_readmes_state_the_safety_declaration_near_the_table() -> None:
    for path in (README, README_ZH):
        text = path.read_text(encoding="utf-8")
        assert SAFETY_DECLARATION in text, path.name


def test_every_readme_row_declares_an_install_way() -> None:
    """A row without an install method would not tell a reader what to do."""
    for path in (README, README_ZH):
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = [line for line in lines if line.startswith("| ") and line.count("|") >= 5]
        curated_rows = [row for row in rows if "pip install" in row or "git clone" in row or "Built-in" in row or "内置" in row]
        assert len(curated_rows) >= len(catalog_entries()), (
            f"{path.name} has {len(curated_rows)} curated rows for "
            f"{len(catalog_entries())} catalog entries"
        )
