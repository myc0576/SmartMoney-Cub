from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workspace import Workspace

DEFAULT_WORKSPACE_DB = "state/workspace/review.db"

# The JSON rule registry (rule_registry.json, written by registry.register_candidate
# and read by the self-evolve loop) predates the sqlite rule library and still uses
# its own status vocabulary. Mirroring it into the library keeps one place a human
# can look for "every rule we have", while the JSON file stays the loop's artifact.
REGISTRY_STATUS_TO_RULE_STATUS = {
    "challenger": "challenger",
    "promotion_recommended": "promotion_recommended",
    "promoted": "champion",
}

# confirm-promotion speaks in human decisions; the rule library speaks in statuses.
PROMOTION_DECISION_TO_RULE_STATUS = {
    "promote": "champion",
    "reject": "rejected",
    "defer": "deferred",
}

# Only a champion row has been authorized by a human. Every other status is a
# proposal the human has not accepted, which is why the written note is required
# for champion and required nowhere else.
CHAMPION_STATUS = "champion"


def rule_status_for_registry_status(registry_status: str) -> str:
    """Translate a JSON-registry status into a rule-library status."""
    try:
        return REGISTRY_STATUS_TO_RULE_STATUS[registry_status]
    except KeyError:
        raise ValueError(f"unsupported registry status: {registry_status}") from None


def workspace_add_case(
    payload: dict[str, Any],
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Add a review case from a JSON payload, enforcing the risk contract."""
    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    try:
        record = workspace.add_case(
            case_id=str(payload.get("case_id") or ""),
            symbol=str(payload.get("symbol") or ""),
            action=str(payload.get("action") or ""),
            decision_time=str(payload.get("decision_time") or ""),
            thesis=str(payload.get("thesis") or ""),
            invalidation_price=payload.get("invalidation_price"),
            time_stop=payload.get("time_stop"),
            give_up_conditions=payload.get("give_up_conditions"),
            data_source=payload.get("data_source"),
            available_at=payload.get("available_at"),
            data_quality_flag=payload.get("data_quality_flag"),
            regime=str(payload.get("regime") or ""),
            tags=payload.get("tags"),
        )
    except (ValueError, TypeError) as exc:
        return {
            "status": "error",
            "error": {"code": type(exc).__name__, "message": str(exc)},
            "safety": SAFETY_DECLARATION,
        }
    finally:
        workspace.close()
    return {"status": "ok", "case": record, "safety": SAFETY_DECLARATION}


def workspace_list_cases(
    *,
    db_path: str | None = None,
    action: str | None = None,
    symbol: str | None = None,
    regime: str | None = None,
) -> dict[str, Any]:
    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    try:
        cases = workspace.list_cases(action=action, symbol=symbol, regime=regime)
    finally:
        workspace.close()
    return {"status": "ok", "cases": cases, "count": len(cases), "safety": SAFETY_DECLARATION}


def workspace_show_case(case_id: str, *, db_path: str | None = None) -> dict[str, Any]:
    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    try:
        case = workspace.get_case(case_id)
        if case is None:
            return {"status": "not_found", "case_id": case_id, "safety": SAFETY_DECLARATION}
        outcomes = workspace.list_outcomes(case_id)
        evidence = workspace.list_evidence(case_id=case_id)
    finally:
        workspace.close()
    return {
        "status": "ok",
        "case": case,
        "outcomes": outcomes,
        "evidence_count": len(evidence),
        "safety": SAFETY_DECLARATION,
    }


def workspace_record_outcome(
    *,
    case_id: str,
    horizon: str,
    return_pct: float,
    max_adverse_excursion_pct: float | None = None,
    outcome_time: str | None = None,
    detail: str = "",
    db_path: str | None = None,
) -> dict[str, Any]:
    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    try:
        result = workspace.record_outcome(
            case_id=case_id,
            horizon=horizon,
            return_pct=return_pct,
            max_adverse_excursion_pct=max_adverse_excursion_pct,
            outcome_time=outcome_time,
            detail=detail,
        )
    except KeyError as exc:
        return {
            "status": "not_found",
            "error": {"code": "unknown_case", "message": str(exc)},
            "safety": SAFETY_DECLARATION,
        }
    finally:
        workspace.close()
    return result


def workspace_summary(*, db_path: str | None = None) -> dict[str, Any]:
    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    try:
        summary = workspace.summary()
    finally:
        workspace.close()
    return {"status": "ok", "summary": summary, "safety": SAFETY_DECLARATION}


def workspace_import_csv(
    csv_path: str, *, db_path: str | None = None, regime: str = ""
) -> dict[str, Any]:
    """Import closed round trips from a CSV into the review workspace."""
    from smartmoney_cub_harness.fills import build_fill_ledger, ledger_to_analysis_trades
    from smartmoney_cub_harness.trade_parser import parse_csv_content

    content = Path(csv_path).read_text(encoding="utf-8")
    records = parse_csv_content(content)
    ledger = build_fill_ledger(records)
    trades = ledger_to_analysis_trades(ledger)

    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    imported = 0
    try:
        for trip in ledger["round_trips"]:
            payload = {
                "case_id": trip["round_trip_id"],
                "symbol": trip["symbol"],
                # A closed CSV round trip is a recovered historical fact, not a
                # forward-looking observation, so no risk contract is invented for it.
                "action": "IMPORTED",
                "decision_time": _to_iso(trip["entry_time"]),
                "thesis": trip.get("thesis") or "CSV import: no entry thesis recorded",
                "invalidation_price": trip.get("invalidation_price"),
                "data_source": "broker_csv_import",
                "available_at": _to_iso(trip["entry_time"]),
                "data_quality_flag": (
                    "ok" if ledger["status"] == "ok" else "partial"
                ),
                "regime": trip.get("regime") or regime,
                "tags": list(trip.get("tags") or []) + ["csv_import"],
            }
            workspace.add_case(**payload)
            imported += 1
    except (ValueError, TypeError) as exc:
        return {
            "status": "error",
            "error": {"code": type(exc).__name__, "message": str(exc)},
            "ledger": ledger,
            "imported": imported,
            "safety": SAFETY_DECLARATION,
        }
    finally:
        workspace.close()

    return {
        "status": "ok",
        "imported": imported,
        "ledger_status": ledger["status"],
        "issues": ledger["issues"],
        "open_positions": ledger["open_positions"],
        "trades": trades,
        "safety": SAFETY_DECLARATION,
    }

def _to_iso(value: str) -> str:
    """Convert a fill datetime into a timezone-aware ISO timestamp."""
    text = str(value).strip()
    if "T" in text:
        return text
    date_part, _, time_part = text.partition(" ")
    time_part = time_part or "09:30:00"
    return f"{date_part}T{time_part}+08:00"


# ---- rule library: listing, promotion gate, registry bridge --------------


def workspace_rules(*, db_path: str | None = None, status: str | None = None) -> dict[str, Any]:
    """List the rule library with promotion blockers attached to each rule.

    An empty library is a normal answer, not a failure: a reviewer checking a
    fresh workspace should see "no rules yet" rather than an error.
    """
    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    try:
        rules = workspace.list_rules_with_blockers(status=status)
    finally:
        workspace.close()
    return {
        "status": "ok",
        "rules": rules,
        "count": len(rules),
        "safety": SAFETY_DECLARATION,
    }


def workspace_promote_rule(
    rule_id: str,
    *,
    note: str,
    metrics: dict[str, Any] | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Promote one rule to champion behind the human confirmation gate.

    The blank-note refusal lives in Workspace.promote_rule, not here, because the
    HTTP and direct-call paths never pass through argparse. This wrapper only
    translates the raised ValueError into the error payload every workspace
    command already returns.
    """
    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    try:
        rule = workspace.promote_rule(rule_id=rule_id, note=note, metrics=metrics)
    except (ValueError, TypeError) as exc:
        return {
            "status": "error",
            "error": {"code": type(exc).__name__, "message": str(exc)},
            "safety": SAFETY_DECLARATION,
        }
    finally:
        workspace.close()
    return {"status": "ok", "rule": rule, "safety": SAFETY_DECLARATION}


def workspace_reject_rule(
    rule_id: str,
    *,
    note: str = "",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Reject one rule.

    A note is optional: refusing a promotion asks nothing of the evidence, while
    granting one is the action that needs a human to own it.
    """
    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    try:
        rule = workspace.reject_rule(rule_id=rule_id, note=note)
    except (ValueError, TypeError) as exc:
        return {
            "status": "error",
            "error": {"code": type(exc).__name__, "message": str(exc)},
            "safety": SAFETY_DECLARATION,
        }
    finally:
        workspace.close()
    return {"status": "ok", "rule": rule, "safety": SAFETY_DECLARATION}


def sync_registry_candidate_to_workspace(
    *,
    rule_id: str,
    registry_status: str,
    family: str = "",
    title: str = "",
    metrics: dict[str, Any] | None = None,
    note: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Mirror one JSON-registry rule into the sqlite rule library.

    The JSON registry (rule_registry.json) is the self-evolve loop's own artifact
    and keeps its own status vocabulary; the sqlite rule library is the single
    place a human lists every rule regardless of which path proposed it. Writing
    both keeps a challenger proposed by the loop visible next to one proposed by
    the review assistant, without changing the JSON file's shape.

    A promoted registry status maps to champion here, so it hits the same gate as
    a direct promotion: Workspace.set_rule_state refuses a champion row without a
    non-blank note. That is deliberate. The note is the only thing that may
    produce a champion row, whichever entry point is used.
    """
    return _write_workspace_rule_state(
        rule_id=rule_id,
        rule_status=rule_status_for_registry_status(registry_status),
        family=family,
        title=title,
        metrics=metrics,
        note=note,
        db_path=db_path,
    )


def _write_workspace_rule_state(
    *,
    rule_id: str,
    rule_status: str,
    family: str = "",
    title: str = "",
    metrics: dict[str, Any] | None = None,
    note: str | None = None,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Write one already-resolved rule status into the sqlite rule library.

    The two callers above and below arrive with a status from different
    vocabularies (a JSON-registry status vs. a human decision), so translation
    happens at each call site and this helper only owns the write. That keeps a
    value that is already a rule status -- "champion" from a promote decision --
    from being run through the registry translation a second time.

    A champion write still passes through Workspace.set_rule_state, so the
    blank-note refusal applies here exactly as it does everywhere else.
    """
    workspace = Workspace(db_path or DEFAULT_WORKSPACE_DB)
    try:
        return workspace.set_rule_state(
            rule_id=rule_id,
            status=rule_status,
            family=family,
            title=title,
            metrics=metrics,
            # promotion_note records the human note that authorized champion
            # status. A rejected or deferred rule keeps its note in the JSON
            # registry and ledger instead of borrowing champion-shaped wording.
            promotion_note=(note or None) if rule_status == CHAMPION_STATUS else None,
        )
    finally:
        workspace.close()


def sync_registry_file_to_workspace(
    registry_path: str | Path,
    *,
    db_path: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Mirror every candidate in a rule_registry.json file into the rule library.

    Returns a small sync report rather than the full rule rows: the caller wants
    to know that the bridge ran and which rule ids landed, and the rows themselves
    are one workspace-rules call away.
    """
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    synced: list[dict[str, Any]] = []
    for candidate in registry.get("candidates") or []:
        record = sync_registry_candidate_to_workspace(
            rule_id=str(candidate.get("rule_id") or ""),
            registry_status=str(candidate.get("promotion_status") or "challenger"),
            family=str(candidate.get("family") or ""),
            title=str(candidate.get("title") or ""),
            metrics=candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {},
            note=note,
            db_path=db_path,
        )
        synced.append({"rule_id": record["rule_id"], "rule_status": record["rule_status"]})
    return {"status": "ok", "synced": synced, "count": len(synced), "safety": SAFETY_DECLARATION}


def confirm_promotion_with_workspace(
    promotion_packet: str | Path,
    *,
    decision: str,
    note: str = "",
    db_path: str | None = None,
) -> dict[str, Any]:
    """Record one human promotion decision in both the JSON registry and the library.

    confirm_promotion in self_evolve.py owns the JSON registry, the packet, and the
    ledger. This wrapper adds the sqlite rule-state row so the decision is visible
    in the same rule listing as everything else.

    The blank-note check runs BEFORE confirm_promotion on purpose. confirm_promotion
    writes the JSON champion registry first, so validating afterwards would leave a
    promoted JSON champion that the rule library then refused -- a divergence that
    reads as "promoted" in one place and "not a champion" in the other. Failing
    first means a promote with no written confirmation mutates nothing at all.
    """
    normalized = decision.strip().lower()
    if normalized == "promote" and not (note or "").strip():
        raise ValueError("champion rule requires an explicit human confirmation note")

    from smartmoney_cub_harness.self_evolve import confirm_promotion  # noqa: PLC0415

    packet_path = Path(promotion_packet)
    candidate = json.loads(packet_path.read_text(encoding="utf-8")).get("candidate") or {}
    result = confirm_promotion(packet_path, decision=normalized, note=note)
    result["workspace_rule"] = _write_workspace_rule_state(
        rule_id=str(candidate.get("rule_id") or ""),
        # Already a rule-library status: the decision names it directly, so it
        # must not be re-translated as if it came from the JSON registry.
        rule_status=PROMOTION_DECISION_TO_RULE_STATUS[normalized],
        family=str(candidate.get("family") or ""),
        title=str(candidate.get("title") or ""),
        metrics=candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {},
        note=note,
        db_path=db_path,
    )
    return result
