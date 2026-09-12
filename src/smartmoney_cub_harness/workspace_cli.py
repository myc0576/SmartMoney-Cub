from __future__ import annotations

from pathlib import Path
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workspace import Workspace

DEFAULT_WORKSPACE_DB = "state/workspace/review.db"


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
