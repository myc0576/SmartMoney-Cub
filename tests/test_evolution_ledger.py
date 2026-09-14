from __future__ import annotations

import json
from pathlib import Path

import pytest

from smartmoney_cub_harness.evolution_ledger import append_ledger_event, read_ledger
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_append_ledger_event_writes_redacted_jsonl(tmp_path: Path):
    ledger = tmp_path / "evolution_ledger.jsonl"

    result = append_ledger_event(
        ledger,
        "case_memory_saved",
        {"case_id": "toy", "note": "token=abc", "champion_mutated": False},
    )
    entries = read_ledger(ledger)

    assert result["safety"] == SAFETY_DECLARATION
    assert result["champion_mutated"] is False
    assert entries[0]["event"] == "case_memory_saved"
    assert entries[0]["requires_human_confirmation"] is True
    # The secret is asserted on the field that carried it, not on the whole
    # file. Each entry also carries a random uuid4 hex ledger_id, and a bare
    # "abc not in <file>" search therefore failed roughly once in fifty runs
    # whenever those three letters happened to fall inside the id -- a flake
    # that looked like a redaction failure but was the test searching the wrong
    # string. The field-local check is the one that actually proves the secret
    # was removed, and it cannot be fooled by an unrelated identifier.
    entry = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert entry["note"] == "token=[REDACTED]"
    assert "abc" not in entry["note"]
    assert "[REDACTED]" in ledger.read_text(encoding="utf-8")


def test_champion_mutation_requires_explicit_confirmation(tmp_path: Path):
    ledger = tmp_path / "evolution_ledger.jsonl"

    with pytest.raises(ValueError, match="explicit confirmation"):
        append_ledger_event(ledger, "champion_mutated", {"champion_mutated": True})

    result = append_ledger_event(
        ledger,
        "champion_mutated",
        {"champion_mutated": True, "explicit_confirmation": True, "rule_id": "toy-rule-v2"},
    )
    saved = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])

    assert result["champion_mutated"] is True
    assert saved["explicit_confirmation"] is True
