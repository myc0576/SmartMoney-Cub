from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

# The agent skill lets a coding agent drive the local review harness without
# touching the database, the credentials, or the attachments directly. The skill
# only calls the stable JSON CLI.

SKILL_NAME = "smartmoney-cub"
SKILL_DIR_NAME = "smartmoney-cub"

TARGET_DIRS: dict[str, tuple[str, ...]] = {
    "codex": (".codex", "skills"),
    "claude": (".claude", "skills"),
    "deepseek-harness": (".deepseek", "skills"),
}

SKILL_BODY = '''---
name: smartmoney-cub
description: >
  Review local trading decisions with the SmartMoney-Cub harness. Use when the
  user asks to review trades, import a broker export, check discipline against
  their own rules, compute review metrics, or propose a challenger rule.
---

# SmartMoney-Cub review harness

Read-only decision logging and review. It is not a stock picker, broker
connector, or financial advice system.

Every response and artifact must carry:

    READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE

## Rules

1. Never place, modify, or cancel an order. Never connect to a broker.
2. Never invent performance numbers. Report the sample size behind any average.
3. Never promote a rule to champion. Propose a challenger and stop.
4. Never send a screenshot, PDF, or CSV original to any external service. The
   harness parses those locally and sends only redacted structured fields.
5. Report a blocking ledger issue before giving any review conclusion.

## Commands

All commands print JSON.

    smcub store status --json
    smcub import file <path> --json
    smcub import commit <extraction_id> --json
    smcub workspace summary
    smcub workspace list-cases --action AVOID
    smcub workspace show-case <case_id>
    smcub workbench --no-browser

## Review workflow

1. Run `smcub store status --json` and confirm the store is healthy.
2. For a new file, run `smcub import file <path> --json` and show the parsed
   rows with their confidence. Nothing is written until the user confirms.
3. Run `smcub import commit <extraction_id> --json` only after confirmation.
4. Read the ledger status. If it is `needs_review`, list the blocking issues and
   stop before drawing conclusions.
5. Summarize with `smcub workspace summary` and report the sample size.
6. When a pattern is supported, propose a challenger rule. The champion registry
   only changes after explicit human confirmation.

## Boundaries

The skill may read review data and propose challenger rules. It may not read the
credentials file, the raw attachment directory, or the SQLite database directly,
and it may not bypass the redactor that runs before any external model request.
'''


def target_directory(target: str, *, home: Path | None = None) -> Path:
    """Resolve the install directory for a host, or accept an explicit path."""
    if target in TARGET_DIRS:
        base = (home or Path.home()).joinpath(*TARGET_DIRS[target])
        return base / SKILL_DIR_NAME
    return Path(target).expanduser()


def install_skill(
    *,
    target: str = "codex",
    force: bool = False,
    home: Path | None = None,
) -> dict[str, Any]:
    destination = target_directory(target, home=home)
    skill_file = destination / "SKILL.md"
    if skill_file.exists() and not force:
        return {
            "status": "exists",
            "destination": str(destination),
            "error": "skill already installed; pass --force to overwrite",
            "safety": SAFETY_DECLARATION,
        }
    destination.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(SKILL_BODY, encoding="utf-8")
    return {
        "status": "ok",
        "target": target,
        "destination": str(destination),
        "files": ["SKILL.md"],
        "safety": SAFETY_DECLARATION,
    }


def uninstall_skill(*, target: str = "codex", home: Path | None = None) -> dict[str, Any]:
    destination = target_directory(target, home=home)
    if not destination.is_dir():
        return {"status": "absent", "destination": str(destination), "safety": SAFETY_DECLARATION}
    shutil.rmtree(destination)
    return {"status": "ok", "destination": str(destination), "safety": SAFETY_DECLARATION}


def skill_text() -> str:
    return SKILL_BODY

