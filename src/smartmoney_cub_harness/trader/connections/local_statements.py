"""User-selected CSV/JSON directory reader with content checkpoints.

No login, broker export or PDF extraction is attempted. rotki generic trades
are understood structurally; unknown assets/ambiguous swaps require mapping.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from .manifests import get_manifest
from .models import ConnectionAccount, ConnectionCursor, EventPage, ScopeValidation
from .providers import _event
from .protocol import PermissionConnectionError
from .vezgo import VezgoConnection


class LocalStatementConnection:
    def __init__(self, directory, credentials=None, *, account_id=None):
        if not str(directory).strip():
            raise ValueError("statement_directory_required")
        self.directory = Path(directory).resolve()
        self.account_id, self._disconnected = account_id, False
        if not self.directory.is_dir():
            raise ValueError("statement_directory_must_exist")

    def metadata(self):
        return get_manifest("local-statement-directory")

    def bind_credentials(self, credentials):
        pass  # Access is the explicitly selected local directory, not a key.

    def validate_read_access(self, credentials=None):
        try:
            valid = not self._disconnected and self.directory.is_dir()
            if valid:
                next(self.directory.iterdir(), None)
        except OSError:
            valid = False
        return ScopeValidation(valid, "verified" if valid else "denied", required=("read",),
                               granted=("read",) if valid else (), issues=() if valid else ("statement_directory_unreadable",))

    def _files(self):
        if not self.validate_read_access().allowed:
            raise PermissionConnectionError("statement_directory_unreadable")
        return [p for p in sorted(self.directory.iterdir()) if p.suffix.lower() in (".csv", ".json") and p.is_file() and not p.is_symlink()]

    def read_events(self, cursor=None, credentials=None):
        if cursor and cursor.provider_id != self.metadata().provider_id:
            raise ValueError("cursor_provider_mismatch")
        files = self._files()
        snapshot, digest = [], hashlib.sha256()
        total = 0
        for path in files:
            size = path.stat().st_size
            total += size
            if size > 20 * 1024 * 1024 or total > 100 * 1024 * 1024:
                raise ValueError("statement_directory_size_limit")
            content = path.read_bytes()
            digest.update(path.name.encode())
            digest.update(content)
            snapshot.append((path, content))
        fingerprint = digest.hexdigest()
        checkpoint = ConnectionCursor(self.metadata().provider_id, fingerprint)
        if cursor and cursor.token == fingerprint:
            return EventPage(checkpoint_cursor=checkpoint)
        events, counts, errors = [], Counter(), []
        for path, content in snapshot:
            try:
                text = content.decode("utf-8-sig")
                if path.suffix.lower() == ".csv":
                    rows = list(csv.DictReader(io.StringIO(text)))
                else:
                    payload = json.loads(text)
                    rows = payload if isinstance(payload, list) else payload.get("rows", payload.get("data", []))
                if not isinstance(rows, list):
                    raise ValueError("statement_rows_required")
                for row in rows:
                    event = self._normalize(row, counts)
                    events.append(event)
            except (ValueError, TypeError, KeyError, UnicodeError):
                errors.append("statement_requires_mapping:" + hashlib.sha256(path.name.encode()).hexdigest()[:12])
        return EventPage(tuple(events), checkpoint_cursor=None if errors else checkpoint, partial=bool(errors), errors=tuple(errors))

    def _normalize(self, row, counts):
        if not isinstance(row, dict):
            raise ValueError("statement_row_must_be_object")
        identity = str(row.get("external_id") or row.get("id") or row.get("trade_id") or row.get("execution_id") or "")
        if not identity:
            economic = {key: value for key, value in row.items() if key not in ("description", "notes", "revision")}
            base = hashlib.sha256(json.dumps(economic, sort_keys=True).encode()).hexdigest()[:24]
            counts[base] += 1
            identity = base + "-" + str(counts[base])
        revision = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:24]
        if "Spend Currency" in row and "Receive Currency" in row:
            account = str(row.get("account_id") or self.account_id or row.get("Location") or "unknown-account")
            payload = {"id": identity, "transaction_type": "trade", "confirmed_at": int(row["Timestamp"]),
                "parts": [{"ticker": row["Spend Currency"], "direction": "sent", "amount": row["Spend Amount"]},
                          {"ticker": row["Receive Currency"], "direction": "received", "amount": row["Receive Amount"]}],
                "fees": [{"ticker": row.get("Fee Currency"), "amount": row["Fee"]}] if row.get("Fee") else []}
            event = VezgoConnection.normalize(payload, account)
            return replace(event, source=self.metadata().provider_id, revision=revision,
                           metadata={**event.metadata, "format": "rotki_generic_trades"})
        combined = dict(row)
        combined["external_id"], combined["revision"] = identity, revision
        if self.account_id and not combined.get("account_id"):
            combined["account_id"] = self.account_id
        if row.get("trade_date") and row.get("trade_time") and not row.get("occurred_at"):
            combined["occurred_at"] = str(row["trade_date"]) + "T" + str(row["trade_time"])
        # The generic helper does not infer read-time availability from a date.
        event = _event(self.metadata().provider_id, combined, 0)
        return replace(event, available_at=row.get("available_at"))

    def list_accounts(self, credentials=None):
        accounts = {e.account_id: e for e in self.read_events().events if e.account_id != "unknown-account"}
        return tuple(ConnectionAccount(key, "Statement account " + key, self.metadata().provider_id, "source_declared", e.currency, ("read",)) for key, e in sorted(accounts.items()))

    def read_positions(self, credentials=None):
        return ()

    def disconnect(self):
        self._disconnected = True
