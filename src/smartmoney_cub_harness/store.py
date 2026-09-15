from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import threading
import uuid
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

# The convergence store owns the local review workbench data: immutable source
# documents, extraction runs, reviewed fills, portfolios, agent sessions, and the
# audit trail of what was sent to an external model.
#
# Two rules are enforced here rather than in the UI:
#   1. A source document is written once and never overwritten.
#   2. A fill correction appends a revision; the previous revision stays readable.

STORE_BASENAME = "review_store.db"
DOCUMENTS_DIRNAME = "documents"
DEFAULT_PORTFOLIO_ID = "PORT-DEFAULT"
DEFAULT_PORTFOLIO_NAME = "默认组合"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _synchronized(method):
    """Serialize writes.

    The local service answers requests on multiple threads, so one connection is
    shared behind a re-entrant lock. Reads stay lock-free because each statement
    uses its own cursor.
    """

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class Store:
    """SQLite-backed local store for the convergence workbench."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)
        self.documents_dir = self.root / DOCUMENTS_DIRNAME
        self.documents_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / STORE_BASENAME
        # The local service is threaded, so the connection is shared explicitly
        # and every write below takes the lock.
        self._db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._ensure_schema()

    # ---- schema --------------------------------------------------------

    def _ensure_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS portfolio (
                portfolio_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS source_document (
                document_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                media_type TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                safety TEXT NOT NULL,
                UNIQUE (sha256)
            );
            CREATE TABLE IF NOT EXISTS extraction_run (
                extraction_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                engine TEXT NOT NULL,
                engine_version TEXT,
                status TEXT NOT NULL,
                row_count INTEGER NOT NULL DEFAULT 0,
                mean_confidence REAL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (document_id) REFERENCES source_document (document_id)
            );
            CREATE TABLE IF NOT EXISTS fill_record (
                fill_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL,
                document_id TEXT,
                extraction_id TEXT,
                trade_date TEXT NOT NULL,
                trade_time TEXT NOT NULL DEFAULT "",
                symbol TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT "",
                side TEXT NOT NULL,
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                fee REAL NOT NULL DEFAULT 0.0,
                thesis TEXT NOT NULL DEFAULT "",
                invalidation_price REAL,
                regime TEXT NOT NULL DEFAULT "",
                tags TEXT NOT NULL DEFAULT '[]',
                revision INTEGER NOT NULL DEFAULT 1,
                superseded INTEGER NOT NULL DEFAULT 0,
                edited_by TEXT NOT NULL DEFAULT "import",
                confidence REAL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS fill_record_portfolio
                ON fill_record (portfolio_id, trade_date, trade_time);
            CREATE TABLE IF NOT EXISTS candidate_fill (
                candidate_id TEXT PRIMARY KEY,
                extraction_id TEXT NOT NULL,
                portfolio_id TEXT NOT NULL,
                row_index INTEGER NOT NULL,
                trade_date TEXT,
                trade_time TEXT,
                symbol TEXT,
                name TEXT,
                side TEXT,
                price REAL,
                quantity INTEGER,
                fee REAL,
                field_confidence TEXT NOT NULL DEFAULT '{}',
                raw_text TEXT NOT NULL DEFAULT '',
                warnings TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY (extraction_id) REFERENCES extraction_run (extraction_id)
            );
            CREATE TABLE IF NOT EXISTS agent_session (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '{}',
                provider_id TEXT NOT NULL DEFAULT 'alphatech',
                model TEXT NOT NULL DEFAULT '',
                reasoning TEXT NOT NULL DEFAULT 'medium',
                status TEXT NOT NULL DEFAULT 'idle',
                forked_from TEXT,
                archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS session_event (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                kind TEXT NOT NULL,
                role TEXT,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES agent_session (session_id)
            );
            CREATE INDEX IF NOT EXISTS session_event_seq
                ON session_event (session_id, seq);
            CREATE TABLE IF NOT EXISTS outbound_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                provider_id TEXT NOT NULL,
                model TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                sent_keys TEXT NOT NULL,
                redaction_summary TEXT NOT NULL,
                blocked INTEGER NOT NULL DEFAULT 0,
                reason TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        try:
            self._db.execute("ALTER TABLE candidate_fill ADD COLUMN fee REAL")
        except sqlite3.OperationalError:
            pass
        self._db.commit()
        self._ensure_default_portfolio()

    @_synchronized
    def _ensure_default_portfolio(self) -> None:
        row = self._db.execute(
            "SELECT portfolio_id FROM portfolio WHERE portfolio_id = ?",
            (DEFAULT_PORTFOLIO_ID,),
        ).fetchone()
        if row is None:
            self._db.execute(
                "INSERT INTO portfolio (portfolio_id, name, description, created_at)"
                " VALUES (?, ?, ?, ?)",
                (
                    DEFAULT_PORTFOLIO_ID,
                    DEFAULT_PORTFOLIO_NAME,
                    "本地默认组合。示例与演示数据全部为虚构数据。",
                    _now_iso(),
                ),
            )
            self._db.commit()

    @_synchronized
    def close(self) -> None:
        self._db.close()

    # ---- portfolios ----------------------------------------------------

    def list_portfolios(self) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM portfolio WHERE archived = 0 ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    @_synchronized
    def create_portfolio(self, name: str, description: str = "") -> dict[str, Any]:
        name = (name or "").strip()
        if not name:
            raise ValueError("portfolio name must not be empty")
        portfolio_id = f"PORT-{_uuid()}"
        self._db.execute(
            "INSERT INTO portfolio (portfolio_id, name, description, created_at)"
            " VALUES (?, ?, ?, ?)",
            (portfolio_id, name, description, _now_iso()),
        )
        self._db.commit()
        return self.get_portfolio(portfolio_id)

    def get_portfolio(self, portfolio_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM portfolio WHERE portfolio_id = ?", (portfolio_id,)
        ).fetchone()
        if row is None:
            raise KeyError(portfolio_id)
        return dict(row)

    # ---- immutable source documents ------------------------------------

    @_synchronized
    def add_document(
        self,
        content: bytes,
        *,
        file_name: str,
        media_type: str,
        source_kind: str,
        portfolio_id: str = DEFAULT_PORTFOLIO_ID,
    ) -> dict[str, Any]:
        """Store raw bytes once, keyed by content hash.

        The same bytes imported twice resolve to the same document instead of
        creating a duplicate the user has to clean up.
        """
        digest = hashlib.sha256(content).hexdigest()
        existing = self._db.execute(
            "SELECT * FROM source_document WHERE sha256 = ?", (digest,)
        ).fetchone()
        if existing is not None:
            if existing["source_kind"] == "unknown" and source_kind != "unknown":
                self._db.execute(
                    "UPDATE source_document SET source_kind = ? WHERE document_id = ?",
                    (source_kind, existing["document_id"]),
                )
                self._db.commit()
                return {**dict(existing), "source_kind": source_kind, "duplicate": True}
            return {**dict(existing), "duplicate": True}

        safe_name = Path(file_name or "upload.bin").name
        stored_name = f"{digest[:16]}-{safe_name}"
        target = self.documents_dir / stored_name
        if not target.exists():
            target.write_bytes(content)

        document_id = f"DOC-{_uuid()}"
        self._db.execute(
            "INSERT INTO source_document (document_id, portfolio_id, file_name, media_type,"
            " byte_size, sha256, stored_name, source_kind, imported_at, safety)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document_id,
                portfolio_id,
                safe_name,
                media_type or "application/octet-stream",
                len(content),
                digest,
                stored_name,
                source_kind,
                _now_iso(),
                SAFETY_DECLARATION,
            ),
        )
        self._db.commit()
        record = self.get_document(document_id)
        return {**record, "duplicate": False}

    def get_document(self, document_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM source_document WHERE document_id = ?", (document_id,)
        ).fetchone()
        if row is None:
            raise KeyError(document_id)
        return dict(row)

    def list_documents(self, *, portfolio_id: str | None = None) -> list[dict[str, Any]]:
        if portfolio_id:
            rows = self._db.execute(
                "SELECT * FROM source_document WHERE portfolio_id = ? ORDER BY imported_at DESC",
                (portfolio_id,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM source_document ORDER BY imported_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def document_bytes(self, document_id: str) -> bytes:
        record = self.get_document(document_id)
        return (self.documents_dir / record["stored_name"]).read_bytes()

    # ---- extraction runs and candidates --------------------------------

    @_synchronized
    def record_extraction(
        self,
        *,
        document_id: str,
        engine: str,
        engine_version: str,
        status: str,
        rows: list[dict[str, Any]],
        mean_confidence: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        extraction_id = f"EXT-{_uuid()}"
        self._db.execute(
            "INSERT INTO extraction_run (extraction_id, document_id, engine, engine_version,"
            " status, row_count, mean_confidence, payload, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                extraction_id,
                document_id,
                engine,
                engine_version,
                status,
                len(rows),
                mean_confidence,
                json.dumps(payload or {}, ensure_ascii=False),
                _now_iso(),
            ),
        )
        for index, row in enumerate(rows):
            self._db.execute(
                "INSERT INTO candidate_fill (candidate_id, extraction_id, portfolio_id, row_index,"
                " trade_date, trade_time, symbol, name, side, price, quantity, fee, field_confidence,"
                " raw_text, warnings)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"CAND-{extraction_id}-{index}",
                    extraction_id,
                    row.get("portfolio_id") or DEFAULT_PORTFOLIO_ID,
                    index,
                    row.get("trade_date"),
                    row.get("trade_time") or "",
                    row.get("symbol"),
                    row.get("name") or "",
                    row.get("side"),
                    row.get("price"),
                    row.get("quantity"),
                    row.get("fee"),
                    json.dumps(row.get("field_confidence") or {}, ensure_ascii=False),
                    row.get("raw_text") or "",
                    json.dumps(row.get("warnings") or [], ensure_ascii=False),
                ),
            )
        self._db.commit()
        return self.get_extraction(extraction_id)

    def get_extraction(self, extraction_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM extraction_run WHERE extraction_id = ?", (extraction_id,)
        ).fetchone()
        if row is None:
            raise KeyError(extraction_id)
        record = dict(row)
        payload = json.loads(record.pop("payload") or "{}")
        record["detail"] = payload
        record["rows"] = self.list_candidates(extraction_id)
        return record

    def list_candidates(self, extraction_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM candidate_fill WHERE extraction_id = ? ORDER BY row_index",
            (extraction_id,),
        ).fetchall()
        return [_candidate_row(row) for row in rows]

    def list_extractions(self, *, document_id: str | None = None) -> list[dict[str, Any]]:
        if document_id:
            rows = self._db.execute(
                "SELECT * FROM extraction_run WHERE document_id = ? ORDER BY created_at DESC",
                (document_id,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM extraction_run ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        return [{k: v for k, v in dict(row).items() if k != "payload"} for row in rows]

    # ---- reviewed fills ------------------------------------------------

    @_synchronized
    def add_fills(
        self,
        fills: list[dict[str, Any]],
        *,
        portfolio_id: str = DEFAULT_PORTFOLIO_ID,
        document_id: str | None = None,
        extraction_id: str | None = None,
        edited_by: str = "import",
    ) -> dict[str, Any]:
        """Append reviewed fills.

        A correction never overwrites a row. The previous revision is marked
        superseded so the history stays readable.
        """
        inserted: list[str] = []
        superseded: list[str] = []
        skipped: list[str] = []
        for fill in fills:
            identity = _fill_identity(fill)
            same_fill = self._db.execute(
                "SELECT fill_id FROM fill_record WHERE fill_id IN ("
                "  SELECT fill_id FROM fill_record WHERE portfolio_id = ? AND trade_date = ?"
                "  AND trade_time = ? AND symbol = ? AND side = ?"
                "  AND ABS(price - ?) < 0.000001 AND quantity = ?)",
                (
                    portfolio_id,
                    fill["trade_date"],
                    fill.get("trade_time") or "",
                    fill["symbol"],
                    fill["side"],
                    float(fill["price"]),
                    int(fill["quantity"]),
                ),
            ).fetchall()
            if same_fill:
                # The same economic fill is already recorded, so a repeated
                # import or OCR pass must not double the position.
                skipped.append(identity)
                continue

            # A correction is a new revision: the earlier row for the same
            # symbol, date, and side becomes superseded but stays readable.
            prior = self._db.execute(
                "SELECT fill_id, revision FROM fill_record WHERE portfolio_id = ?"
                " AND superseded = 0 AND trade_date = ? AND symbol = ? AND side = ?",
                (portfolio_id, fill["trade_date"], fill["symbol"], fill["side"]),
            ).fetchall()
            revision = 1
            if prior:
                revision = max(int(row["revision"]) for row in prior) + 1
                for row in prior:
                    self._db.execute(
                        "UPDATE fill_record SET superseded = 1 WHERE fill_id = ?",
                        (row["fill_id"],),
                    )
                    superseded.append(row["fill_id"])

            fill_id = f"FILL-{_uuid()}"
            self._db.execute(
                "INSERT INTO fill_record (fill_id, portfolio_id, document_id, extraction_id,"
                " trade_date, trade_time, symbol, name, side, price, quantity, fee, thesis,"
                " invalidation_price, regime, tags, revision, superseded, edited_by, confidence,"
                " created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)",
                (
                    fill_id,
                    portfolio_id,
                    document_id,
                    extraction_id,
                    fill["trade_date"],
                    fill.get("trade_time") or "",
                    fill["symbol"],
                    fill.get("name") or "",
                    fill["side"],
                    float(fill["price"]),
                    int(fill["quantity"]),
                    float(fill.get("fee") or 0.0),
                    fill.get("thesis") or "",
                    fill.get("invalidation_price"),
                    fill.get("regime") or "",
                    json.dumps(fill.get("tags") or [], ensure_ascii=False),
                    revision,
                    edited_by,
                    fill.get("confidence"),
                    _now_iso(),
                ),
            )
            inserted.append(fill_id)
        self._db.commit()
        return {
            "status": "ok",
            "inserted": inserted,
            "inserted_count": len(inserted),
            "superseded": superseded,
            "skipped": skipped,
            "safety": SAFETY_DECLARATION,
        }

    def list_fills(
        self,
        *,
        portfolio_id: str | None = None,
        include_superseded: bool = False,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if portfolio_id:
            clauses.append("portfolio_id = ?")
            params.append(portfolio_id)
        if not include_superseded:
            clauses.append("superseded = 0")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            "SELECT * FROM fill_record" + where + " ORDER BY trade_date, trade_time, created_at",
            params,
        ).fetchall()
        return [_fill_row(row) for row in rows]

    def fill_revisions(self, *, portfolio_id: str | None = None, symbol: str | None = None) -> list[dict[str, Any]]:
        """Return every revision, including superseded ones, newest first."""
        clauses: list[str] = []
        params: list[Any] = []
        if portfolio_id:
            clauses.append("portfolio_id = ?")
            params.append(portfolio_id)
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.execute(
            "SELECT * FROM fill_record" + where + " ORDER BY trade_date DESC, trade_time DESC, revision DESC",
            params,
        ).fetchall()
        return [_fill_row(row) for row in rows]

    @_synchronized
    def delete_fill(self, fill_id: str) -> bool:
        cursor = self._db.execute(
            "DELETE FROM fill_record WHERE fill_id = ?", (fill_id,)
        )
        self._db.commit()
        return cursor.rowcount > 0

    @_synchronized
    def clear_fills(self, portfolio_id: str | None = None) -> int:
        if portfolio_id:
            cursor = self._db.execute(
                "DELETE FROM fill_record WHERE portfolio_id = ?", (portfolio_id,)
            )
        else:
            cursor = self._db.execute("DELETE FROM fill_record")
        self._db.commit()
        return cursor.rowcount

    # ---- agent sessions ------------------------------------------------

    @_synchronized
    def create_session(
        self,
        *,
        title: str,
        context: dict[str, Any] | None = None,
        provider_id: str = "alphatech",
        model: str = "",
        reasoning: str = "medium",
        forked_from: str | None = None,
    ) -> dict[str, Any]:
        session_id = f"SES-{_uuid()}"
        now = _now_iso()
        self._db.execute(
            "INSERT INTO agent_session (session_id, title, context, provider_id, model,"
            " reasoning, status, forked_from, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'idle', ?, ?, ?)",
            (
                session_id,
                title or "新会话",
                json.dumps(context or {}, ensure_ascii=False),
                provider_id,
                model,
                reasoning,
                forked_from,
                now,
                now,
            ),
        )
        self._db.commit()
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT * FROM agent_session WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return _session_row(row)

    def list_sessions(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        where = "" if include_archived else " WHERE archived = 0"
        rows = self._db.execute(
            "SELECT * FROM agent_session" + where + " ORDER BY updated_at DESC"
        ).fetchall()
        return [_session_row(row) for row in rows]

    @_synchronized
    def update_session(self, session_id: str, **fields: Any) -> dict[str, Any]:
        allowed = {"title", "provider_id", "model", "reasoning", "status", "archived", "context"}
        updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if "context" in updates:
            updates["context"] = json.dumps(updates["context"], ensure_ascii=False)
        if updates:
            assignments = ", ".join(f"{key} = ?" for key in updates)
            self._db.execute(
                f"UPDATE agent_session SET {assignments}, updated_at = ? WHERE session_id = ?",
                [*updates.values(), _now_iso(), session_id],
            )
            self._db.commit()
        return self.get_session(session_id)

    @_synchronized
    def fork_session(self, session_id: str, *, title: str | None = None) -> dict[str, Any]:
        source = self.get_session(session_id)
        events = self.list_events(session_id)
        fork = self.create_session(
            title=title or f"{source['title']} (分叉)",
            context=source["context"],
            provider_id=source["provider_id"],
            model=source["model"],
            reasoning=source["reasoning"],
            forked_from=session_id,
        )
        for event in events:
            self.append_event(
                fork["session_id"],
                kind=event["kind"],
                role=event.get("role"),
                payload=event["payload"],
            )
        # A fork is a new conversation. Keeping the transcript but dropping the
        # status means the parent can keep streaming while the fork starts idle.
        return {**fork, "copied_events": len(events)}

    @_synchronized
    def append_event(
        self,
        session_id: str,
        *,
        kind: str,
        payload: dict[str, Any],
        role: str | None = None,
    ) -> dict[str, Any]:
        row = self._db.execute(
            "SELECT COALESCE(MAX(seq), 0) AS seq FROM session_event WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        seq = int(row["seq"]) + 1
        cursor = self._db.execute(
            "INSERT INTO session_event (session_id, seq, kind, role, payload, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                seq,
                kind,
                role,
                json.dumps(payload, ensure_ascii=False),
                _now_iso(),
            ),
        )
        self._db.execute(
            "UPDATE agent_session SET updated_at = ? WHERE session_id = ?",
            (_now_iso(), session_id),
        )
        self._db.commit()
        return {
            "event_id": cursor.lastrowid,
            "session_id": session_id,
            "seq": seq,
            "kind": kind,
            "role": role,
            "payload": payload,
        }

    def list_events(self, session_id: str, *, after_seq: int = 0) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM session_event WHERE session_id = ? AND seq > ? ORDER BY seq",
            (session_id, after_seq),
        ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "session_id": row["session_id"],
                "seq": row["seq"],
                "kind": row["kind"],
                "role": row["role"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    # ---- outbound audit ------------------------------------------------

    @_synchronized
    def record_audit(
        self,
        *,
        session_id: str | None,
        provider_id: str,
        model: str,
        payload_sha256: str,
        sent_keys: list[str],
        redaction_summary: dict[str, Any],
        blocked: bool = False,
        reason: str | None = None,
    ) -> dict[str, Any]:
        cursor = self._db.execute(
            "INSERT INTO outbound_audit (session_id, provider_id, model, payload_sha256,"
            " sent_keys, redaction_summary, blocked, reason, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                provider_id,
                model,
                payload_sha256,
                json.dumps(sent_keys, ensure_ascii=False),
                json.dumps(redaction_summary, ensure_ascii=False),
                1 if blocked else 0,
                reason,
                _now_iso(),
            ),
        )
        self._db.commit()
        return {"audit_id": cursor.lastrowid, "blocked": blocked, "reason": reason}

    def list_audits(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM outbound_audit ORDER BY audit_id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {
                **{k: row[k] for k in ("audit_id", "session_id", "provider_id", "model", "payload_sha256", "reason", "created_at")},
                "sent_keys": json.loads(row["sent_keys"] or "[]"),
                "blocked": bool(row["blocked"]),
                "redaction_summary": json.loads(row["redaction_summary"] or "{}"),
            }
            for row in rows
        ]

    # ---- settings ------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._db.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    @_synchronized
    def set_setting(self, key: str, value: Any) -> None:
        self._db.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), _now_iso()),
        )
        self._db.commit()

    # ---- maintenance ---------------------------------------------------

    @_synchronized
    def counts(self) -> dict[str, int]:
        tables = (
            "portfolio",
            "source_document",
            "extraction_run",
            "fill_record",
            "agent_session",
            "session_event",
            "outbound_audit",
        )
        result: dict[str, int] = {}
        for table in tables:
            row = self._db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            result[table] = int(row["n"])
        return result

    @_synchronized
    def backup(self, destination: str | Path) -> dict[str, Any]:
        """Copy the store aside before a migration or a destructive action."""
        target = Path(destination)
        if target.suffix == "":
            target = target.with_suffix(".db")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._db.execute("PRAGMA wal_checkpoint(FULL)")
        shutil.copy2(self.db_path, target)
        return {
            "status": "ok",
            "path": str(target),
            "byte_size": target.stat().st_size,
            "safety": SAFETY_DECLARATION,
        }


def _fill_identity(fill: dict[str, Any]) -> str:
    return "|".join(
        [
            str(fill.get("trade_date") or ""),
            str(fill.get("trade_time") or ""),
            str(fill.get("symbol") or ""),
            str(fill.get("side") or ""),
            f"{float(fill.get('price') or 0):.4f}",
            str(int(fill.get("quantity") or 0)),
        ]
    )


def _fill_identity_row(row: sqlite3.Row, fill: dict[str, Any]) -> str:
    del fill
    return "|".join(
        [
            str(row["trade_date"]),
            str(row["trade_time"]),
            str(row["symbol"]),
            str(row["side"]),
            f"{float(row['price']):.4f}",
            str(int(row["quantity"])),
        ]
    )


def _fill_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["tags"] = json.loads(record.get("tags") or "[]")
    record["superseded"] = bool(record.get("superseded"))
    return record


def _candidate_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["field_confidence"] = json.loads(record.get("field_confidence") or "{}")
    record["warnings"] = json.loads(record.get("warnings") or "[]")
    return record


def _session_row(row: sqlite3.Row) -> dict[str, Any]:
    record = dict(row)
    record["context"] = json.loads(record.get("context") or "{}")
    record["archived"] = bool(record.get("archived"))
    return record
