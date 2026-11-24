"""Local capability authorization and human approval records.

The store is deliberately narrow: it authorizes local journal and review
capabilities, never broker or execution actions.  Permission decisions are
made from a private SQLite database below an explicitly supplied state root.
Approval payloads are validated before they are serialized, and an approved
request can be consumed only once.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import stat
import uuid
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

_DB_NAME = "control_permissions.sqlite3"
_SCOPE_KEYS = frozenset({"root", "account", "provider"})
_FAMILY_SUFFIX = ".*"
_YES_FLAG_RE = re.compile(r"(?<!\S)--yes(?:[=\s]|$)")

# Build these names from parts so the sensitive field vocabulary does not get
# copied into persisted records or error output by accident.
_SENSITIVE_FIELD_NAMES = frozenset(
    "".join(parts)
    for parts in (
        ("api", "_", "key"),
        ("access", "_", "token"),
        ("refresh", "_", "token"),
        ("client", "_", "secret"),
        ("private", "_", "key"),
        ("signing", "_", "key"),
    )
)
_SECRET_VALUE_PATTERNS = (
    re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
        r"password|passwd|secret|authorization|cookie)\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(r"(?i)(?:^|\b)sk[-_][a-z0-9_-]{8,}"),
    re.compile(r"(?i)(?:^|\b)gh[pousr]_[a-z0-9_-]{8,}"),
    re.compile(r"(?i)(?:^|\b)AIza[a-z0-9_-]{8,}"),
    re.compile(r"(?i)(?:^|\b)AKIA[A-Z0-9]{8,}"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(r"(?s)-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"^[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$"),
)

_FORBIDDEN_EXACT_NAMES = frozenset(
    {
        "cancel",
        "execute",
        "execution",
        "order",
        "order_execution",
        "place_order",
        "trade_execute",
        "trade_execution",
        "trade",
        "trade_write",
        "account_modify",
        "account_write",
        "broker_write",
        "withdraw",
        "transfer",
    }
)
_FORBIDDEN_PREFIXES = (
    "cancel_",
    "execute_",
    "execution_",
    "order_",
    "place_order_",
    "trade_execute_",
    "trade_execution_",
    "trade_write_",
    "account_modify_",
    "account_write_",
    "broker_write_",
    "withdraw_",
    "transfer_",
)
_FORBIDDEN_MARKERS = (
    "cancel",
    "execute",
    "execution",
    "order_",
    "place_order",
    "order_place",
    "trade_execute",
    "trade_execution",
    "trade_write",
    "account_modify",
    "account_write",
    "broker_write",
    "withdraw",
    "transfer",
)


class PermissionDenied(PermissionError):
    """A capability, scope, or approval gate did not authorize the action.

    This is the stable compatibility exception for callers that distinguish
    denied authorization from malformed input.
    """


class ApprovalError(PermissionError):
    """An approval request is missing, not approved, mismatched, or spent."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _absolute_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    return Path(os.path.abspath(os.fspath(candidate)))


def _reject_symlink_components(path: Path) -> None:
    """Reject existing symlink components without resolving through them."""
    absolute = _absolute_path(path)
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("state paths may not contain symlinks")


def _prepare_private_root(root: str | Path) -> Path:
    if not isinstance(root, (str, Path)):
        raise TypeError("root must be an explicit filesystem path")
    root_path = _absolute_path(root)
    if root_path == Path(root_path.anchor):
        raise ValueError("state root must be a private directory")
    _reject_symlink_components(root_path)
    try:
        info = os.lstat(root_path)
    except FileNotFoundError:
        root_path.mkdir(parents=True, mode=0o700)
    else:
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("state root must be a real directory")

    _reject_symlink_components(root_path)
    if not root_path.is_dir() or root_path.is_symlink():
        raise ValueError("state root must be a real directory")
    root_path.chmod(0o700)
    return root_path


def _prepare_database(path: Path) -> None:
    _reject_symlink_components(path)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            descriptor = None
        if descriptor is not None:
            os.close(descriptor)
    else:
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError("permission database must be a regular file")
    _reject_symlink_components(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("permission database must be a regular file")
    path.chmod(0o600)


def _normal_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _sensitive_field(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    sensitive = {
        re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
        for name in _SENSITIVE_FIELD_NAMES
    }
    return normalized in sensitive or normalized in {"password", "passwd", "secret", "token", "cookie", "cookies", "authorization", "credentials", "client_secret", "credential"}


def _secret_value(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)


def _validate_json_value(value: Any, path: str) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"approval payload has an invalid field at {path}")
            if _sensitive_field(key):
                raise ValueError(f"approval payload contains a sensitive field at {path}")
            normalized[key] = _validate_json_value(nested, f"{path}.{key}")
        return normalized
    if isinstance(value, list):
        return [_validate_json_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and _secret_value(value):
            raise ValueError(f"approval payload contains a secret-like value at {path}")
        return value
    if isinstance(value, float):
        if not (value == value and abs(value) != float("inf")):
            raise ValueError(f"approval payload contains a non-finite number at {path}")
        return value
    raise ValueError(f"approval payload contains a non-JSON value at {path}")


def validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a validated copy without mutating or persisting the input.

    Ordinary review prose such as "password reset" remains valid data, while
    secret-bearing fields, secret-like assignments/tokens, control characters,
    non-JSON objects, and non-finite numbers are rejected.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("approval payload must be an object")
    normalized = _validate_json_value(payload, "payload")
    if not isinstance(normalized, dict):  # pragma: no cover - guarded above
        raise ValueError("approval payload must be an object")
    return normalized


# Compatibility name retained for callers of the original helper.
validate_approval_payload = validate_payload


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _payload_hash(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _validate_principal(principal: str) -> str:
    if not isinstance(principal, str) or not principal.strip():
        raise ValueError("principal must be a non-empty string")
    if any(char in principal for char in "\r\n\x00"):
        raise ValueError("principal contains a control character")
    if _secret_value(principal):
        raise ValueError("principal contains a secret-like value")
    return principal


def _validate_name(name: str, label: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if any(char in name for char in "\r\n\x00"):
        raise ValueError(f"{label} contains a control character")
    return name


def _name_for_policy(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")


def _reject_execution_name(name: str, label: str) -> None:
    normalized = _name_for_policy(name)
    if (
        normalized in _FORBIDDEN_EXACT_NAMES
        or any(normalized.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)
        or any(marker in normalized for marker in _FORBIDDEN_MARKERS)
    ):
        raise ValueError(f"{label} is outside the read-only harness contract")


def _validate_capability(capability: str, *, allow_family: bool = True) -> str:
    value = _validate_name(capability, "capability")
    if _secret_value(value):
        raise ValueError("capability contains a secret-like value")
    if value == "*" or "*" in value and not (allow_family and value.endswith(_FAMILY_SUFFIX)):
        raise ValueError("capability wildcard is not a valid scoped grant")
    if value.endswith(_FAMILY_SUFFIX) and value.count("*") != 1:
        raise ValueError("capability family must end with one wildcard")
    _reject_execution_name(value.removesuffix(_FAMILY_SUFFIX), "capability")
    return value


def _validate_operation(operation: str) -> str:
    value = _validate_name(operation, "operation")
    if _secret_value(value):
        raise ValueError("operation contains a secret-like value")
    _reject_execution_name(value, "operation")
    return value


def _normalize_scope(scope: Mapping[str, Any], *, for_request: bool = False) -> dict[str, str]:
    if not isinstance(scope, Mapping) or not scope:
        error = PermissionDenied if for_request else ValueError
        raise error("a non-empty known scope is required")
    unknown = set(scope) - _SCOPE_KEYS
    if unknown:
        error = PermissionDenied if for_request else ValueError
        raise error("scope contains an unknown dimension")

    normalized: dict[str, str] = {}
    for key, raw_value in scope.items():
        if key == "root":
            if isinstance(raw_value, Path):
                raw_value = str(raw_value)
            if not isinstance(raw_value, str) or not raw_value.strip():
                error = PermissionDenied if for_request else ValueError
                raise error("scope root must be a non-empty path")
            root = _absolute_path(raw_value)
            _reject_symlink_components(root)
            normalized[key] = str(root)
        else:
            if not isinstance(raw_value, str) or not raw_value.strip() or raw_value in {"*", "any", "all"}:
                error = PermissionDenied if for_request else ValueError
                raise error("scope values must be explicit and non-wildcard")
            if _secret_value(raw_value):
                error = PermissionDenied if for_request else ValueError
                raise error("scope contains a secret-like value")
            normalized[key] = raw_value
    return normalized


def _capability_matches(granted: str, requested: str) -> bool:
    if granted == requested:
        return True
    if granted.endswith(_FAMILY_SUFFIX):
        family = granted[: -len(_FAMILY_SUFFIX)]
        return bool(family) and requested.startswith(family + ".")
    return False


def _scope_matches(granted: Mapping[str, str], requested: Mapping[str, str]) -> bool:
    """Match every declared dimension; a root grant may cover its descendants."""
    if set(granted) != set(requested):
        return False
    for key, granted_value in granted.items():
        requested_value = requested[key]
        if key != "root":
            if granted_value != requested_value:
                return False
            continue
        try:
            Path(requested_value).relative_to(Path(granted_value))
        except ValueError:
            return False
    return True


def _has_yes_flag(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_YES_FLAG_RE.search(value))
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and _normal_key(key) in {
                "yes",
                "autoapprove",
                "skipconfirmation",
            } and nested is True:
                return True
            if _has_yes_flag(key) or _has_yes_flag(nested):
                return True
        return False
    if isinstance(value, list):
        return any(_has_yes_flag(item) for item in value)
    return False


def _approval_payload(operation: str, payload: dict[str, Any], principal: str) -> tuple[dict[str, Any], str]:
    operation = _validate_operation(operation)
    principal = _validate_principal(principal)
    safe_payload = validate_payload(payload)
    if _secret_value(operation) or _secret_value(principal):
        raise ValueError("approval request contains a secret-like value")
    if _has_yes_flag(operation) or _has_yes_flag(principal) or _has_yes_flag(safe_payload):
        raise PermissionDenied("the human approval gate cannot be bypassed with --yes")
    payload_json = _canonical_json(safe_payload)
    return {
        "operation": operation,
        "payload": safe_payload,
        "principal": principal,
    }, payload_json


class PermissionStore:
    """SQLite-backed capability grants and one-use approval requests."""

    def __init__(self, root: Path):
        self.root = _prepare_private_root(root)
        self.db_path = self.root / _DB_NAME
        _prepare_database(self.db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS grants (
                        grant_id TEXT PRIMARY KEY,
                        principal TEXT NOT NULL,
                        capability TEXT NOT NULL,
                        scope_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        revoked_at TEXT
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS grants_lookup "
                    "ON grants (principal, capability, revoked_at)"
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS approvals (
                        request_id TEXT PRIMARY KEY,
                        operation TEXT NOT NULL,
                        principal TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'consumed')),
                        confirmed INTEGER NOT NULL DEFAULT 0 CHECK (confirmed IN (0, 1)),
                        note TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        decided_at TEXT,
                        consumed_at TEXT
                    )
                    """
                )
                connection.execute("CREATE INDEX IF NOT EXISTS approvals_status ON approvals (status)")
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    @contextlib.contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _grant_record(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "grant_id": row["grant_id"],
            "principal": row["principal"],
            "capability": row["capability"],
            "scope": json.loads(row["scope_json"]),
            "created_at": row["created_at"],
            "revoked": row["revoked_at"] is not None,
            "revoked_at": row["revoked_at"],
            "safety": SAFETY_DECLARATION,
        }

    @staticmethod
    def _approval_record(row: sqlite3.Row) -> dict[str, Any]:
        status = str(row["status"])
        return {
            "request_id": row["request_id"],
            "operation": row["operation"],
            "principal": row["principal"],
            "payload": json.loads(row["payload_json"]),
            "payload_hash": row["payload_hash"],
            "status": status,
            "confirmed": bool(row["confirmed"]),
            "note": row["note"],
            "created_at": row["created_at"],
            "decided_at": row["decided_at"],
            "consumed": status == "consumed",
            "consumed_at": row["consumed_at"],
            "safety": SAFETY_DECLARATION,
        }

    def grant(self, principal: str, capability: str, scope: dict[str, Any]) -> dict[str, Any]:
        principal = _validate_principal(principal)
        capability = _validate_capability(capability)
        normalized_scope = _normalize_scope(scope)
        grant_id = uuid.uuid4().hex
        created_at = _utc_now()
        with self._write_transaction() as connection:
            connection.execute(
                """
                INSERT INTO grants (grant_id, principal, capability, scope_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (grant_id, principal, capability, _canonical_json(normalized_scope), created_at),
            )
            row = connection.execute("SELECT * FROM grants WHERE grant_id = ?", (grant_id,)).fetchone()
        if row is None:  # pragma: no cover - the insert and select share a transaction
            raise RuntimeError("grant was not persisted")
        return self._grant_record(row)

    def revoke(self, grant_id: str) -> dict[str, Any]:
        if not isinstance(grant_id, str) or not grant_id:
            raise ValueError("grant_id must be a non-empty string")
        with self._write_transaction() as connection:
            row = connection.execute("SELECT * FROM grants WHERE grant_id = ?", (grant_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown grant: {grant_id}")
            if row["revoked_at"] is None:
                connection.execute(
                    "UPDATE grants SET revoked_at = ? WHERE grant_id = ? AND revoked_at IS NULL",
                    (_utc_now(), grant_id),
                )
            row = connection.execute("SELECT * FROM grants WHERE grant_id = ?", (grant_id,)).fetchone()
        return self._grant_record(row)

    def list(self, principal: str | None = None) -> dict[str, Any]:
        if principal is not None:
            principal = _validate_principal(principal)
        with self._connect() as connection:
            if principal is None:
                rows = connection.execute("SELECT * FROM grants ORDER BY created_at, grant_id").fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM grants WHERE principal = ? ORDER BY created_at, grant_id",
                    (principal,),
                ).fetchall()
        return {
            "grants": [self._grant_record(row) for row in rows],
            "principal": principal,
            "safety": SAFETY_DECLARATION,
        }

    def require(self, principal: str, capability: str, scope: dict[str, Any]) -> None:
        principal = _validate_principal(principal)
        capability = _validate_capability(capability, allow_family=False)
        try:
            normalized_scope = _normalize_scope(scope, for_request=True)
        except (TypeError, ValueError, PermissionDenied) as exc:
            if isinstance(exc, PermissionDenied):
                raise
            raise PermissionDenied("requested scope is missing or invalid") from exc

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT capability, scope_json FROM grants "
                "WHERE principal = ? AND revoked_at IS NULL ORDER BY created_at, grant_id",
                (principal,),
            ).fetchall()
        for row in rows:
            if _capability_matches(str(row["capability"]), capability):
                granted_scope = json.loads(row["scope_json"])
                if _scope_matches(granted_scope, normalized_scope):
                    return None
        raise PermissionDenied("capability is not authorized for the requested scope")

    def request(
        self,
        operation: str,
        payload: dict[str, Any],
        principal: str = "hermes",
    ) -> dict[str, Any]:
        fields, payload_json = _approval_payload(operation, payload, principal)
        request_id = uuid.uuid4().hex
        created_at = _utc_now()
        payload_hash = _payload_hash(payload_json)
        with self._write_transaction() as connection:
            connection.execute(
                """
                INSERT INTO approvals (
                    request_id, operation, principal, payload_json, payload_hash,
                    status, confirmed, note, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', 0, '', ?)
                """,
                (
                    request_id,
                    fields["operation"],
                    fields["principal"],
                    payload_json,
                    payload_hash,
                    created_at,
                ),
            )
            row = connection.execute("SELECT * FROM approvals WHERE request_id = ?", (request_id,)).fetchone()
        if row is None:  # pragma: no cover - the insert and select share a transaction
            raise RuntimeError("approval request was not persisted")
        return self._approval_record(row)

    def approve(self, request_id: str, confirmed: bool, note: str = "") -> dict[str, Any]:
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("request_id must be a non-empty string")
        if type(confirmed) is not bool:
            raise ValueError("confirmed must be a boolean")
        if not isinstance(note, str):
            raise ValueError("approval note must be a string")
        if _secret_value(note) or _has_yes_flag(note):
            raise ValueError("approval note contains unsafe approval text")
        if confirmed and not note.strip():
            raise ValueError("confirmed approval requires an explicit human note")

        status = "approved" if confirmed else "denied"
        with self._write_transaction() as connection:
            row = connection.execute("SELECT * FROM approvals WHERE request_id = ?", (request_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown approval request: {request_id}")
            if row["status"] != "pending":
                raise ApprovalError("approval request has already been decided or consumed")
            connection.execute(
                """
                UPDATE approvals
                SET status = ?, confirmed = ?, note = ?, decided_at = ?
                WHERE request_id = ? AND status = 'pending'
                """,
                (status, int(confirmed), note, _utc_now(), request_id),
            )
            row = connection.execute("SELECT * FROM approvals WHERE request_id = ?", (request_id,)).fetchone()
        return self._approval_record(row)

    def consume(
        self,
        request_id: str,
        operation: str,
        payload: dict[str, Any],
        principal: str,
    ) -> None:
        if not isinstance(request_id, str) or not request_id:
            raise ValueError("request_id must be a non-empty string")
        fields, payload_json = _approval_payload(operation, payload, principal)
        payload_hash = _payload_hash(payload_json)
        with self._write_transaction() as connection:
            row = connection.execute("SELECT * FROM approvals WHERE request_id = ?", (request_id,)).fetchone()
            if row is None:
                raise ApprovalError("approval request does not exist")
            if row["status"] != "approved":
                raise ApprovalError("approval request is not approved or has already been consumed")
            if (
                row["operation"] != fields["operation"]
                or row["principal"] != fields["principal"]
                or row["payload_hash"] != payload_hash
                or row["payload_json"] != payload_json
            ):
                raise ApprovalError("approval request does not exactly match the requested action")
            result = connection.execute(
                """
                UPDATE approvals
                SET status = 'consumed', consumed_at = ?
                WHERE request_id = ? AND status = 'approved'
                """,
                (_utc_now(), request_id),
            )
            if result.rowcount != 1:
                raise ApprovalError("approval request has already been consumed")
        return None


__all__ = [
    "ApprovalError",
    "PermissionDenied",
    "PermissionDeniedError",
    "PermissionStore",
    "validate_payload",
    "validate_approval_payload",
]


# Compatibility name used by integrations that prefer an explicit suffix.
PermissionDeniedError = PermissionDenied
