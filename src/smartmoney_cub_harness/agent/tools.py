from __future__ import annotations

import json
from typing import Any, Callable

from smartmoney_cub_harness import analytics
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.store import DEFAULT_PORTFOLIO_ID, Store

# The assistant gets read-only domain tools plus one narrow write: proposing a
# challenger rule. There is deliberately no shell, no file write, no arbitrary
# network access, and no broker or order surface.

MAX_ROWS = 50


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_trades",
            "description": "List reviewed closed trades with net PnL, return, and holding period.",
            "parameters": _schema(
                {
                    "portfolio_id": {"type": "string"},
                    "symbol": {"type": "string"},
                    "regime": {"type": "string"},
                    "limit": {"type": "integer"},
                }
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trade",
            "description": "Get one closed trade by round-trip id, including matched lots and fees.",
            "parameters": _schema({"round_trip_id": {"type": "string"}}, ["round_trip_id"]),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analytics_summary",
            "description": "Aggregate review metrics with sample sizes, equity curve, and breakdowns.",
            "parameters": _schema({"portfolio_id": {"type": "string"}}),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_month",
            "description": "Daily profit and loss for one month, used for calendar review.",
            "parameters": _schema(
                {
                    "year": {"type": "integer"},
                    "month": {"type": "integer"},
                    "portfolio_id": {"type": "string"},
                },
                ["year", "month"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_positions",
            "description": "List positions that are still open and not yet paired into a round trip.",
            "parameters": _schema({"portfolio_id": {"type": "string"}}),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_rules",
            "description": "List champion and challenger rules from the local rule registry.",
            "parameters": _schema({"status": {"type": "string"}}),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_review_cases",
            "description": "List recorded review cases, optionally filtered by action or symbol.",
            "parameters": _schema({"action": {"type": "string"}, "symbol": {"type": "string"}}),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_challenger_rule",
            "description": "Propose a challenger rule from reviewed evidence. This never mutates a champion rule.",
            "parameters": _schema(
                {
                    "rule_id": {"type": "string"},
                    "title": {"type": "string"},
                    "family": {"type": "string"},
                    "condition": {"type": "string"},
                    "evidence_note": {"type": "string"},
                    "sample_count": {"type": "integer"},
                },
                ["rule_id", "title"],
            ),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "data_quality_report",
            "description": "Report import quality: blocking issues, open positions, and unconfirmed rows.",
            "parameters": _schema({"portfolio_id": {"type": "string"}}),
        },
    },
]


class ToolBox:
    """Executes the assistant's domain tools against the local store."""

    def __init__(self, store: Store, workspace_db: str | None = None) -> None:
        self.store = store
        self.workspace_db = workspace_db or "state/workspace/review.db"
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "list_trades": self.list_trades,
            "get_trade": self.get_trade,
            "analytics_summary": self.analytics_summary,
            "calendar_month": self.calendar_month,
            "open_positions": self.open_positions,
            "list_rules": self.list_rules,
            "list_review_cases": self.list_review_cases,
            "propose_challenger_rule": self.propose_challenger_rule,
            "data_quality_report": self.data_quality_report,
        }

    # ---- dispatch ------------------------------------------------------

    def call(self, name: str, arguments: Any) -> dict[str, Any]:
        handler = self._handlers.get(name)
        if handler is None:
            return _error("unknown_tool", f"tool {name!r} is not available")
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as error:
                return _error("invalid_arguments", str(error))
        else:
            parsed = dict(arguments or {})
        try:
            return handler(**parsed)
        except TypeError as error:
            return _error("invalid_arguments", str(error))
        except KeyError as error:
            return _error("not_found", str(error))

    # ---- reads ---------------------------------------------------------

    def _analysis(self, portfolio_id: str | None) -> dict[str, Any]:
        fills = self.store.list_fills(portfolio_id=portfolio_id or DEFAULT_PORTFOLIO_ID)
        return analytics.analyze(fills)

    def list_trades(
        self,
        portfolio_id: str | None = None,
        symbol: str | None = None,
        regime: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        trips = self._analysis(portfolio_id)["round_trips"]
        if symbol:
            trips = [trip for trip in trips if trip["symbol"] == symbol]
        if regime:
            trips = [trip for trip in trips if (trip.get("regime") or "") == regime]
        capped = trips[: max(1, min(int(limit or MAX_ROWS), MAX_ROWS))]
        return {
            "status": "ok",
            "count": len(trips),
            "returned": len(capped),
            "trades": [
                {
                    "round_trip_id": trip["round_trip_id"],
                    "symbol": trip["symbol"],
                    "name": trip.get("name") or "",
                    "entry_time": trip["entry_time"],
                    "exit_time": trip["exit_time"],
                    "return_pct": trip["return_pct"],
                    "net_pnl": trip["net_pnl"],
                    "holding_days": trip.get("holding_days", 0),
                    "regime": trip.get("regime") or "",
                    "thesis": trip.get("thesis") or "",
                    "tags": trip.get("tags") or [],
                }
                for trip in capped
            ],
            "safety": SAFETY_DECLARATION,
        }

    def get_trade(self, round_trip_id: str) -> dict[str, Any]:
        for trip in self._analysis(None)["round_trips"]:
            if trip["round_trip_id"] == round_trip_id:
                return {"status": "ok", "trade": trip, "safety": SAFETY_DECLARATION}
        return _error("not_found", f"no round trip {round_trip_id!r}")

    def analytics_summary(self, portfolio_id: str | None = None) -> dict[str, Any]:
        analysis = self._analysis(portfolio_id)
        return {
            "status": "ok",
            "summary": analysis["summary"],
            "breakdown": analysis["breakdown"],
            "ledger_status": analysis["ledger_status"],
            "safety": SAFETY_DECLARATION,
        }

    def calendar_month(
        self, year: int, month: int, portfolio_id: str | None = None
    ) -> dict[str, Any]:
        analysis = analytics.analyze(
            self.store.list_fills(portfolio_id=portfolio_id or DEFAULT_PORTFOLIO_ID),
            year=int(year),
            month=int(month),
        )
        return {
            "status": "ok",
            "year": int(year),
            "month": int(month),
            "days": analysis["calendar"],
            "safety": SAFETY_DECLARATION,
        }

    def open_positions(self, portfolio_id: str | None = None) -> dict[str, Any]:
        analysis = self._analysis(portfolio_id)
        return {
            "status": "ok",
            "count": len(analysis["open_positions"]),
            "positions": analysis["open_positions"],
            "safety": SAFETY_DECLARATION,
        }

    def list_rules(self, status: str | None = None) -> dict[str, Any]:
        from smartmoney_cub_harness.workspace import Workspace  # noqa: PLC0415

        workspace = Workspace(self.workspace_db)
        try:
            rules = workspace.list_rules(status=status)
        finally:
            workspace.close()
        return {"status": "ok", "count": len(rules), "rules": rules, "safety": SAFETY_DECLARATION}

    def list_review_cases(
        self, action: str | None = None, symbol: str | None = None
    ) -> dict[str, Any]:
        from smartmoney_cub_harness.workspace import Workspace  # noqa: PLC0415

        workspace = Workspace(self.workspace_db)
        try:
            cases = workspace.list_cases(action=action, symbol=symbol)[:MAX_ROWS]
        finally:
            workspace.close()
        return {
            "status": "ok",
            "count": len(cases),
            "cases": cases,
            "safety": SAFETY_DECLARATION,
        }

    def data_quality_report(self, portfolio_id: str | None = None) -> dict[str, Any]:
        analysis = self._analysis(portfolio_id)
        return {
            "status": "ok",
            "ledger_status": analysis["ledger_status"],
            "blocking_issue_count": len(analysis["blocking_issues"]),
            "issues": analysis["issues"][:MAX_ROWS],
            "open_position_count": len(analysis["open_positions"]),
            "safety": SAFETY_DECLARATION,
        }

    # ---- the one narrow write -----------------------------------------

    def propose_challenger_rule(
        self,
        rule_id: str,
        title: str,
        family: str | None = None,
        condition: str | None = None,
        evidence_note: str | None = None,
        sample_count: int | None = None,
    ) -> dict[str, Any]:
        from smartmoney_cub_harness.workspace import Workspace  # noqa: PLC0415

        workspace = Workspace(self.workspace_db)
        try:
            record = workspace.set_rule_state(
                rule_id=rule_id,
                status="challenger",
                family=family,
                title=title,
                metrics={
                    "sample_count": int(sample_count or 0),
                    "condition": condition or "",
                    "evidence_note": evidence_note or "",
                    "proposed_by": "review_assistant",
                },
            )
        finally:
            workspace.close()
        return {
            "status": "ok",
            "rule": record,
            "champion_mutated": False,
            "note": "Challenger proposed. Promotion still requires the human confirmation gate.",
            "safety": SAFETY_DECLARATION,
        }


def _error(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": code, "message": message},
        "safety": SAFETY_DECLARATION,
    }

