from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.plugins.envelope import validate_evidence_envelope
from smartmoney_cub_harness.safety import redact
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

WORKSPACE_SCHEMA = "smartmoney_cub_workspace.v1"

# The rule lifecycle, in the only vocabulary the rule library accepts. A rule
# moves challenger -> promotion_recommended -> champion only through an explicit
# human confirmation, and rejected/deferred record that the human said no (or
# not yet). Keeping this as one tuple means the storage layer and the CLI
# validate against the same list instead of drifting apart.
RULE_STATUSES = (
    "challenger",
    "promotion_recommended",
    "champion",
    "rejected",
    "deferred",
)

# Review-case decisions. The first six are the review vocabulary; the remaining
# labels come from the existing harness decision contract so both stay usable.
REVIEW_ACTIONS = (
    "BUY",
    "SELL",
    "HOLD",
    "FLAT",
    "AVOID",
    "NO_DECISION",
    "ALERT",
    "WATCH",
    "EMPTY_POSITION",
    "ERROR",
    "SILENT",
    "IMPORTED",
)

# SILENT is the absence of a decision and IMPORTED is a historical fact recovered
# from a broker export. Neither is an observation, so neither carries a risk
# contract. Every other label must supply one.
NON_OBSERVATION_ACTIONS = ("SILENT", "IMPORTED")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


class Workspace:
    """SQLite review workspace for decisions, outcomes, evidence, and rule state.

    SQLite owns querying and statistics. Immutable evidence stays in the Evidence
    Pack and plugin envelopes, so auditability does not depend on a mutable row.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.db_path))
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS review_case (
                case_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                decision_time TEXT NOT NULL,
                thesis TEXT,
                invalidation_price REAL,
                time_stop TEXT,
                give_up_conditions TEXT,
                data_source TEXT,
                available_at TEXT,
                data_quality_flag TEXT,
                regime TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS review_outcome (
                case_id TEXT NOT NULL,
                horizon TEXT NOT NULL,
                return_pct REAL,
                max_adverse_excursion_pct REAL,
                outcome_time TEXT,
                detail TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (case_id, horizon)
            );
            CREATE TABLE IF NOT EXISTS plugin_evidence (
                evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT,
                plugin_id TEXT NOT NULL,
                plugin_version TEXT NOT NULL,
                capability TEXT NOT NULL,
                result_kind TEXT NOT NULL,
                input_sha256 TEXT,
                output_sha256 TEXT,
                decision_time TEXT,
                available_at TEXT,
                review_only INTEGER NOT NULL DEFAULT 1,
                envelope TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rule_state (
                rule_id TEXT PRIMARY KEY,
                family TEXT,
                title TEXT,
                status TEXT NOT NULL,
                metrics TEXT NOT NULL DEFAULT '{}',
                promotion_note TEXT,
                promoted_at TEXT,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    # ---- the non-silent observation contract ---------------------------

    def add_case(
        self,
        *,
        case_id: str,
        symbol: str,
        action: str,
        decision_time: str,
        thesis: str = "",
        invalidation_price: float | None = None,
        time_stop: str | None = None,
        give_up_conditions: list[str] | None = None,
        data_source: str | None = None,
        available_at: str | None = None,
        data_quality_flag: str | None = None,
        regime: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Record a review case.

        A non-SILENT observation without invalidation, time stop, give-up
        conditions, source, availability, and quality is refused rather than
        stored as if it were complete.
        """
        action_label = str(action).upper()
        if action_label not in REVIEW_ACTIONS:
            raise ValueError(f"action must be one of: {', '.join(REVIEW_ACTIONS)}")

        decision_dt = _parse_timestamp(decision_time)
        if decision_dt is None:
            raise ValueError("decision_time must be a timezone-aware ISO timestamp")

        if action_label not in NON_OBSERVATION_ACTIONS:
            missing: list[str] = []
            if invalidation_price is None:
                missing.append("invalidation_price")
            if not time_stop:
                missing.append("time_stop")
            if not give_up_conditions:
                missing.append("give_up_conditions")
            if not data_source:
                missing.append("data_source")
            if not available_at:
                missing.append("available_at")
            if not data_quality_flag:
                missing.append("data_quality_flag")
            if missing:
                raise ValueError(
                    "non-silent observation is missing required fields: " + ", ".join(missing)
                )

            source_dt = _parse_timestamp(available_at)
            if source_dt is None:
                raise ValueError("available_at must be a timezone-aware ISO timestamp")
            if source_dt > decision_dt:
                raise ValueError(
                    f"available_at {available_at} is after decision_time {decision_time}: future leakage"
                )

        self._connection.execute(
            """
            INSERT INTO review_case (
                case_id, symbol, action, decision_time, thesis, invalidation_price,
                time_stop, give_up_conditions, data_source, available_at,
                data_quality_flag, regime, tags, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                symbol = excluded.symbol,
                action = excluded.action,
                decision_time = excluded.decision_time,
                thesis = excluded.thesis,
                invalidation_price = excluded.invalidation_price,
                time_stop = excluded.time_stop,
                give_up_conditions = excluded.give_up_conditions,
                data_source = excluded.data_source,
                available_at = excluded.available_at,
                data_quality_flag = excluded.data_quality_flag,
                regime = excluded.regime,
                tags = excluded.tags
            """,
            (
                case_id,
                symbol,
                action_label,
                decision_time,
                thesis,
                invalidation_price,
                time_stop,
                json.dumps(give_up_conditions or [], ensure_ascii=False),
                data_source,
                available_at,
                data_quality_flag,
                regime,
                json.dumps(tags or [], ensure_ascii=False),
                _now_iso(),
            ),
        )
        self._connection.commit()
        record = self.get_case(case_id)
        assert record is not None
        return record

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM review_case WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["give_up_conditions"] = json.loads(payload.get("give_up_conditions") or "[]")
        payload["tags"] = json.loads(payload.get("tags") or "[]")
        payload["safety"] = SAFETY_DECLARATION
        return payload

    def list_cases(
        self,
        *,
        action: str | None = None,
        symbol: str | None = None,
        regime: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if action:
            clauses.append("action = ?")
            parameters.append(str(action).upper())
        if symbol:
            clauses.append("symbol = ?")
            parameters.append(symbol)
        if regime:
            clauses.append("regime = ?")
            parameters.append(regime)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._connection.execute(
            f"SELECT case_id FROM review_case{where} ORDER BY decision_time DESC, case_id LIMIT ?",
            (*parameters, limit),
        ).fetchall()
        return [record for record in (self.get_case(row["case_id"]) for row in rows) if record]

    def record_outcome(
        self,
        *,
        case_id: str,
        horizon: str,
        return_pct: float,
        max_adverse_excursion_pct: float | None = None,
        outcome_time: str | None = None,
        detail: str = "",
    ) -> dict[str, Any]:
        """Record a D1/D3 style outcome. Post-decision data never rewrites the case."""
        if self.get_case(case_id) is None:
            raise KeyError(f"unknown case: {case_id}")
        self._connection.execute(
            """
            INSERT INTO review_outcome (
                case_id, horizon, return_pct, max_adverse_excursion_pct,
                outcome_time, detail, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id, horizon) DO UPDATE SET
                return_pct = excluded.return_pct,
                max_adverse_excursion_pct = excluded.max_adverse_excursion_pct,
                outcome_time = excluded.outcome_time,
                detail = excluded.detail
            """,
            (
                case_id,
                horizon,
                return_pct,
                max_adverse_excursion_pct,
                outcome_time,
                detail,
                _now_iso(),
            ),
        )
        self._connection.commit()
        return {
            "status": "ok",
            "case_id": case_id,
            "horizon": horizon,
            "safety": SAFETY_DECLARATION,
        }

    def list_outcomes(self, case_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM review_outcome WHERE case_id = ? ORDER BY horizon", (case_id,)
        ).fetchall()
        return [{**dict(row), "safety": SAFETY_DECLARATION} for row in rows]

    # ---- plugin evidence -------------------------------------------------

    def record_evidence(self, envelope: dict[str, Any], *, case_id: str | None = None) -> dict[str, Any]:
        """Persist a validated plugin envelope. Invalid evidence is refused."""
        validation = validate_evidence_envelope(envelope)
        if not validation["ok"]:
            raise ValueError("invalid evidence envelope: " + "; ".join(validation["errors"]))

        self._connection.execute(
            """
            INSERT INTO plugin_evidence (
                case_id, plugin_id, plugin_version, capability, result_kind,
                input_sha256, output_sha256, decision_time, available_at,
                review_only, envelope, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                envelope["plugin_id"],
                envelope["plugin_version"],
                envelope["capability"],
                envelope["result_kind"],
                envelope.get("input_sha256"),
                envelope.get("output_sha256"),
                envelope.get("decision_time"),
                envelope.get("available_at"),
                int(bool(envelope.get("review_only", True))),
                json.dumps(redact(envelope), ensure_ascii=False),
                _now_iso(),
            ),
        )
        self._connection.commit()
        return {
            "status": "ok",
            "plugin_id": envelope["plugin_id"],
            "capability": envelope["capability"],
            "review_only": bool(envelope.get("review_only", True)),
            "safety": SAFETY_DECLARATION,
        }

    def list_evidence(self, *, case_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        if case_id:
            rows = self._connection.execute(
                "SELECT * FROM plugin_evidence WHERE case_id = ? ORDER BY evidence_id DESC LIMIT ?",
                (case_id, limit),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM plugin_evidence ORDER BY evidence_id DESC LIMIT ?", (limit,)
            ).fetchall()
        records: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["review_only"] = bool(payload.get("review_only"))
            payload["envelope"] = json.loads(payload["envelope"])
            payload["safety"] = SAFETY_DECLARATION
            records.append(payload)
        return records

    # ---- rule state ------------------------------------------------------

    def set_rule_state(
        self,
        *,
        rule_id: str,
        status: str,
        family: str = "",
        title: str = "",
        metrics: dict[str, Any] | None = None,
        promotion_note: str | None = None,
    ) -> dict[str, Any]:
        if status not in RULE_STATUSES:
            raise ValueError("unsupported rule status")
        # A champion row may only be written with an explicit human note.
        if status == "champion" and not (promotion_note or "").strip():
            raise ValueError("champion rule requires an explicit human confirmation note")
        self._connection.execute(
            """
            INSERT INTO rule_state (
                rule_id, family, title, status, metrics, promotion_note, promoted_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(rule_id) DO UPDATE SET
                family = excluded.family,
                title = excluded.title,
                status = excluded.status,
                metrics = excluded.metrics,
                promotion_note = excluded.promotion_note,
                promoted_at = excluded.promoted_at,
                updated_at = excluded.updated_at
            """,
            (
                rule_id,
                family,
                title,
                status,
                json.dumps(metrics or {}, ensure_ascii=False),
                promotion_note,
                _now_iso() if status == "champion" else None,
                _now_iso(),
            ),
        )
        self._connection.commit()
        return {"status": "ok", "rule_id": rule_id, "rule_status": status, "safety": SAFETY_DECLARATION}

    def get_rule(self, rule_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM rule_state WHERE rule_id = ?", (rule_id,)
        ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["metrics"] = json.loads(payload.get("metrics") or "{}")
        payload["safety"] = SAFETY_DECLARATION
        return payload

    def list_rules(self, *, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self._connection.execute(
                "SELECT rule_id FROM rule_state WHERE status = ? ORDER BY rule_id", (status,)
            ).fetchall()
        else:
            rows = self._connection.execute("SELECT rule_id FROM rule_state ORDER BY rule_id").fetchall()
        return [record for record in (self.get_rule(row["rule_id"]) for row in rows) if record]

    def list_rules_with_blockers(self, *, status: str | None = None) -> list[dict[str, Any]]:
        """List rules with the promotion blockers computed from each row's metrics.

        Attaching the blockers at read time keeps the stored row an honest record
        of what was proposed: the thresholds live in one frozen place
        (registry.promotion_blockers) and a row can never carry a stale, hand
        edited copy of them.
        """
        # Imported lazily because registry imports only schemas, but a future
        # registry-side import of Workspace would otherwise make this a cycle.
        from smartmoney_cub_harness.registry import promotion_blockers  # noqa: PLC0415

        rules: list[dict[str, Any]] = []
        for rule in self.list_rules(status=status):
            payload = dict(rule)
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            blockers = promotion_blockers(metrics)
            payload["promotion_blockers"] = blockers
            # Named "recommendable", not "recommended", so it cannot be mistaken
            # for the promotion_recommended status stored on the row.
            payload["promotion_recommendable"] = not blockers
            rules.append(payload)
        return rules

    def promote_rule(
        self,
        *,
        rule_id: str,
        note: str,
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Promote a rule to champion behind the human confirmation gate.

        Two separate gates apply, and they are deliberately not the same gate:

        * The threshold gate (sample_count, false-alert, missed-opportunity,
          future-leakage, risk-contract) decides whether the evidence may produce
          a promotion RECOMMENDATION. It does not by itself authorize champion
          mutation -- see docs/harness-contract.md, "Promotion Thresholds":
          passing thresholds may create a promotion recommendation, while
          champion mutation still requires explicit confirmation.
        * The human gate is the non-blank note. An assistant can only propose a
          challenger; a human writes the note, and that note is the only thing
          that can write a champion row.

        So blockers do NOT hard-refuse here. Refusing on any blocker would make
        the recommendation and the mutation the same decision, which is exactly
        the distinction the contract draws, and it would silently turn a
        threshold check into policy authority. Instead this returns the blockers
        in the payload so the caller (CLI, HTTP, reviewer) can explain why a
        promotion is or is not advised, and the human decides with that in hand.

        The blank-note refusal is re-checked in this layer on purpose. The CLI
        also rejects an empty note, but the HTTP and direct-call paths reach this
        method without passing through argparse, so the gate has to live where
        the row is actually written.
        """
        # set_rule_state also refuses a blank champion note; this earlier check
        # makes the intent explicit and keeps the failure message stable.
        if not (note or "").strip():
            raise ValueError("champion rule requires an explicit human confirmation note")

        from smartmoney_cub_harness.registry import promotion_blockers  # noqa: PLC0415

        # Prefer the caller's metrics when supplied; otherwise keep whatever the
        # rule already carried so a promotion does not erase the evidence that
        # was reviewed. Family and title are carried forward for the same reason:
        # set_rule_state's upsert replaces those columns, and a promotion must not
        # blank the description of the rule the human just approved.
        existing = self.get_rule(rule_id) or {}
        resolved_metrics = metrics if metrics is not None else existing.get("metrics") or {}
        blockers = promotion_blockers(resolved_metrics)

        record = self.set_rule_state(
            rule_id=rule_id,
            status="champion",
            family=existing.get("family") or "",
            title=existing.get("title") or "",
            metrics=resolved_metrics,
            promotion_note=note,
        )
        return {
            **record,
            "promotion_note": note,
            "promotion_blockers": blockers,
            "promotion_recommendable": not blockers,
            "blockers_are_advisory": True,
            "safety": SAFETY_DECLARATION,
        }

    def reject_rule(self, *, rule_id: str, note: str = "") -> dict[str, Any]:
        """Mark a rule rejected. No note is required: refusing a promotion asks
        nothing of the evidence, whereas granting one is the action that needs a
        human to own it.
        """
        # Carry the existing description and any earlier human note forward. A
        # rejection is not a reason to silently erase why the rule was approved
        # before, and the upsert would otherwise blank both columns.
        existing = self.get_rule(rule_id) or {}
        record = self.set_rule_state(
            rule_id=rule_id,
            status="rejected",
            family=existing.get("family") or "",
            title=existing.get("title") or "",
            metrics=existing.get("metrics") or {},
            promotion_note=note or existing.get("promotion_note"),
        )
        return {**record, "note": note, "safety": SAFETY_DECLARATION}

    # ---- reporting -------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        case_count = self._connection.execute("SELECT COUNT(*) AS n FROM review_case").fetchone()["n"]
        outcome_count = self._connection.execute("SELECT COUNT(*) AS n FROM review_outcome").fetchone()["n"]
        evidence_count = self._connection.execute("SELECT COUNT(*) AS n FROM plugin_evidence").fetchone()["n"]
        champion_count = self._connection.execute(
            "SELECT COUNT(*) AS n FROM rule_state WHERE status = 'champion'"
        ).fetchone()["n"]
        outcomes = self._connection.execute(
            "SELECT return_pct FROM review_outcome WHERE return_pct IS NOT NULL"
        ).fetchall()
        returns = [float(row["return_pct"]) for row in outcomes]
        return {
            "schema": WORKSPACE_SCHEMA,
            "db_path": str(redact(str(self.db_path))),
            "case_count": case_count,
            "outcome_count": outcome_count,
            "evidence_count": evidence_count,
            "champion_rule_count": champion_count,
            "sample_count": len(returns),
            "mean_return_pct": round(sum(returns) / len(returns), 2) if returns else None,
            "statistical_limits": (
                "Sample is self-selected review history, not a controlled study. "
                "Small samples cannot support confident conclusions."
            ),
            "safety": SAFETY_DECLARATION,
        }
