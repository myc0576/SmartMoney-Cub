from __future__ import annotations

import json
from pathlib import Path

import pytest

from smartmoney_cub_harness.cli import main
from smartmoney_cub_harness.registry import register_candidate
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workspace import Workspace
from smartmoney_cub_harness.workspace_cli import (
    sync_registry_candidate_to_workspace,
    sync_registry_file_to_workspace,
)


def _run(capsys, *argv: str) -> dict:
    """Drive the CLI the same way tests/test_workspace_cli.py does."""
    code = main(list(argv))
    payload = json.loads(capsys.readouterr().out)
    payload["_exit_code"] = code
    return payload


def _challenger(
    workspace: Workspace,
    rule_id: str = "T-V1",
    *,
    sample_count: int = 3,
) -> None:
    """Write a challenger the way the review assistant's tool does."""
    workspace.set_rule_state(
        rule_id=rule_id,
        status="challenger",
        family="toy-family",
        title="toy challenger",
        metrics={"sample_count": sample_count, "proposed_by": "review_assistant"},
    )


def test_assistant_challenger_is_listed_with_its_sample_size_blocker(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace.db")
    _challenger(workspace)

    rules = workspace.list_rules_with_blockers()

    assert [rule["rule_id"] for rule in rules] == ["T-V1"]
    assert rules[0]["status"] == "challenger"
    assert rules[0]["promotion_blockers"] == ["sample_count_below_20"]
    assert rules[0]["promotion_recommendable"] is False
    assert rules[0]["safety"] == SAFETY_DECLARATION
    workspace.close()


def test_promote_rule_refuses_a_blank_note_and_leaves_the_status_unchanged(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace.db")
    _challenger(workspace)

    for blank in ("", "   ", "\t\n"):
        with pytest.raises(ValueError) as excinfo:
            workspace.promote_rule(rule_id="T-V1", note=blank)
        assert "explicit human confirmation note" in str(excinfo.value)
        # The refusal must not half-write row state.
        assert workspace.get_rule("T-V1")["status"] == "challenger"
        assert workspace.get_rule("T-V1")["promotion_note"] is None

    assert workspace.summary()["champion_rule_count"] == 0
    workspace.close()


def test_promote_rule_with_a_real_note_records_the_champion_and_the_note(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace.db")
    _challenger(workspace)

    result = workspace.promote_rule(rule_id="T-V1", note="reviewed 3 samples by hand")

    assert result["rule_status"] == "champion"
    assert result["promotion_note"] == "reviewed 3 samples by hand"
    # Blockers are reported, not enforced: the contract lets a human promote a
    # rule whose evidence is thin, and the payload is how they are told so.
    assert result["promotion_blockers"] == ["sample_count_below_20"]
    assert result["promotion_recommendable"] is False
    assert result["blockers_are_advisory"] is True

    rule = workspace.get_rule("T-V1")
    assert rule["status"] == "champion"
    assert rule["promotion_note"] == "reviewed 3 samples by hand"
    assert rule["promoted_at"] is not None
    # The description written with the challenger survives the promotion.
    assert rule["family"] == "toy-family"
    assert rule["title"] == "toy challenger"
    workspace.close()


def test_cli_promote_rule_without_a_note_fails_without_writing_a_champion(
    capsys, tmp_path: Path
) -> None:
    db = str(tmp_path / "workspace.db")
    workspace = Workspace(db)
    _challenger(workspace)
    workspace.close()

    result = _run(capsys, "workspace", "promote-rule", "T-V1", "--db", db)

    assert result["_exit_code"] == 2
    assert result["status"] == "error"
    assert result["error"]["code"] == "ValueError"
    assert "explicit human confirmation note" in result["error"]["message"]
    assert result["safety"] == SAFETY_DECLARATION

    assert Workspace(db).get_rule("T-V1")["status"] == "challenger"


def test_cli_promote_rule_with_a_note_then_lists_it_as_a_champion(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "workspace.db")
    workspace = Workspace(db)
    _challenger(workspace)
    workspace.close()

    promoted = _run(
        capsys,
        "workspace",
        "promote-rule",
        "T-V1",
        "--note",
        "manual review of the toy sample",
        "--db",
        db,
    )
    assert promoted["_exit_code"] == 0
    assert promoted["rule"]["rule_status"] == "champion"

    champions = _run(capsys, "workspace", "rules", "--status", "champion", "--db", db)
    assert champions["_exit_code"] == 0
    assert champions["count"] == 1
    assert champions["rules"][0]["rule_id"] == "T-V1"
    assert champions["rules"][0]["promotion_note"] == "manual review of the toy sample"
    assert champions["safety"] == SAFETY_DECLARATION

    challengers = _run(capsys, "workspace", "rules", "--status", "challenger", "--db", db)
    assert challengers["rules"] == []


def test_cli_rules_on_an_empty_library_is_ok_not_an_error(capsys, tmp_path: Path) -> None:
    result = _run(capsys, "workspace", "rules", "--db", str(tmp_path / "workspace.db"))

    assert result["_exit_code"] == 0
    assert result["status"] == "ok"
    assert result["rules"] == []
    assert result["count"] == 0
    assert result["safety"] == SAFETY_DECLARATION


def test_summary_champion_count_rises_only_after_the_human_promotion(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "workspace.db")
    workspace = Workspace(db)
    _challenger(workspace)
    workspace.close()

    before = _run(capsys, "workspace", "summary", "--db", db)
    assert before["summary"]["champion_rule_count"] == 0

    _run(capsys, "workspace", "promote-rule", "T-V1", "--note", "approved by hand", "--db", db)

    after = _run(capsys, "workspace", "summary", "--db", db)
    assert after["summary"]["champion_rule_count"] == 1


def test_cli_reject_rule_needs_no_note(capsys, tmp_path: Path) -> None:
    db = str(tmp_path / "workspace.db")
    workspace = Workspace(db)
    _challenger(workspace)
    workspace.close()

    rejected = _run(capsys, "workspace", "reject-rule", "T-V1", "--db", db)

    assert rejected["_exit_code"] == 0
    assert rejected["rule"]["rule_status"] == "rejected"
    assert Workspace(db).get_rule("T-V1")["status"] == "rejected"


def test_self_evolve_challenger_becomes_visible_in_the_rule_library(tmp_path: Path) -> None:
    """A challenger proposed through the JSON registry lands in the same library."""
    registry_path = tmp_path / "rule_registry.json"
    db = str(tmp_path / "workspace.db")
    register_candidate(
        registry_path,
        {
            "rule_id": "toy-loop-challenger",
            "family": "toy-family",
            "metrics": {"sample_count": 4},
        },
    )

    synced = sync_registry_file_to_workspace(registry_path, db_path=db)

    assert synced["count"] == 1
    rules = Workspace(db).list_rules_with_blockers()
    assert [rule["rule_id"] for rule in rules] == ["toy-loop-challenger"]
    assert rules[0]["status"] == "challenger"
    assert rules[0]["promotion_blockers"] == ["sample_count_below_20"]


def test_registry_promoted_status_still_needs_the_human_note(tmp_path: Path) -> None:
    """The champion gate holds on the registry bridge too, and writes nothing on refusal."""
    db = str(tmp_path / "workspace.db")

    with pytest.raises(ValueError) as excinfo:
        sync_registry_candidate_to_workspace(
            rule_id="toy-loop-challenger",
            registry_status="promoted",
            metrics={"sample_count": 4},
            db_path=db,
        )
    assert "explicit human confirmation note" in str(excinfo.value)
    assert Workspace(db).list_rules() == []

    record = sync_registry_candidate_to_workspace(
        rule_id="toy-loop-challenger",
        registry_status="promoted",
        metrics={"sample_count": 4},
        note="approved by hand",
        db_path=db,
    )
    assert record["rule_status"] == "champion"
    assert Workspace(db).get_rule("toy-loop-challenger")["promotion_note"] == "approved by hand"


def _promotion_packet(tmp_path: Path) -> Path:
    """Write the packet shape confirm_promotion reads, with a strong candidate.

    Built by hand rather than by running the loop so this test isolates the
    registry -> rule-library bridge. The loop's own end-to-end behavior is
    covered by tests/test_self_evolve.py.
    """
    loop_dir = tmp_path / "loop"
    loop_dir.mkdir(parents=True, exist_ok=True)
    (loop_dir / "rule_registry.json").write_text(
        json.dumps({"schema": "smartmoney_cub_rule_registry.v1", "champions": {}, "candidates": []}),
        encoding="utf-8",
    )
    packet = {
        "schema": "smartmoney_cub_promotion_packet.v1",
        "status": "promotion_recommended",
        "candidate": {
            "rule_id": "toy-loop-challenger",
            "family": "toy-family",
            "metrics": {
                "sample_count": 25,
                "false_alert_rate": 0.1,
                "missed_opportunity_rate": 0.1,
                "future_leakage_count": 0,
                "risk_contract_violation_rate": 0.0,
            },
        },
        "rule_registry_path": "rule_registry.json",
        "ledger_path": "evolution_ledger.jsonl",
    }
    packet_path = loop_dir / "promotion_packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    return packet_path


def test_cli_confirm_promotion_without_a_note_writes_no_champion_anywhere(
    capsys, tmp_path: Path
) -> None:
    packet_path = _promotion_packet(tmp_path)
    db = str(tmp_path / "workspace.db")

    result = _run(
        capsys,
        "confirm-promotion",
        str(packet_path),
        "--decision",
        "promote",
        "--workspace-db",
        db,
    )

    assert result["_exit_code"] == 2
    assert result["error"]["code"] == "ValueError"
    assert "explicit human confirmation note" in result["error"]["message"]
    # The refusal happens before confirm_promotion, so the JSON registry stays
    # empty too: neither store may read as promoted.
    registry = json.loads((packet_path.parent / "rule_registry.json").read_text(encoding="utf-8"))
    assert registry["champions"] == {}
    assert Workspace(db).list_rules() == []


def test_cli_confirm_promotion_with_a_note_promotes_in_both_stores(capsys, tmp_path: Path) -> None:
    packet_path = _promotion_packet(tmp_path)
    db = str(tmp_path / "workspace.db")

    result = _run(
        capsys,
        "confirm-promotion",
        str(packet_path),
        "--decision",
        "promote",
        "--note",
        "manual approval",
        "--workspace-db",
        db,
    )

    assert result["_exit_code"] == 0
    assert result["champion_mutated"] is True
    registry = json.loads((packet_path.parent / "rule_registry.json").read_text(encoding="utf-8"))
    assert registry["champions"]["toy-family"] == "toy-loop-challenger"

    rules = Workspace(db).list_rules_with_blockers(status="champion")
    assert [rule["rule_id"] for rule in rules] == ["toy-loop-challenger"]
    assert rules[0]["promotion_note"] == "manual approval"
    assert rules[0]["promotion_blockers"] == []


def test_cli_confirm_promotion_defer_and_reject_map_to_their_rule_statuses(
    capsys, tmp_path: Path
) -> None:
    for decision, expected in (("reject", "rejected"), ("defer", "deferred")):
        packet_path = _promotion_packet(tmp_path / decision)
        db = str(tmp_path / f"{decision}.db")

        result = _run(
            capsys,
            "confirm-promotion",
            str(packet_path),
            "--decision",
            decision,
            "--workspace-db",
            db,
        )

        assert result["_exit_code"] == 0
        assert result["champion_mutated"] is False
        rules = Workspace(db).list_rules()
        assert [rule["status"] for rule in rules] == [expected]
        # A defer or reject never claims champion status, so no champion row and
        # no borrowed promotion note.
        assert Workspace(db).summary()["champion_rule_count"] == 0
