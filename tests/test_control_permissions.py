from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import os
from pathlib import Path

import pytest

from smartmoney_cub_harness.control_permissions import (
    ApprovalError,
    PermissionDenied,
    PermissionDeniedError,
    PermissionStore,
    validate_approval_payload,
    validate_payload,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_private_root_and_database_reject_symlinks(tmp_path: Path) -> None:
    real_root = tmp_path / "private-state"
    store = PermissionStore(real_root)

    assert real_root.stat().st_mode & 0o777 == 0o700
    assert store.db_path.stat().st_mode & 0o777 == 0o600
    assert store.root == real_root

    link = tmp_path / "state-link"
    link.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        PermissionStore(link)

    db_link_root = tmp_path / "database-link"
    db_link_root.mkdir()
    target = tmp_path / "outside.sqlite3"
    target.touch()
    (db_link_root / "control_permissions.sqlite3").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        PermissionStore(db_link_root)


def test_exact_and_family_grants_require_explicit_matching_scope(tmp_path: Path) -> None:
    store = PermissionStore(tmp_path / "state")
    journal_root = tmp_path / "journal"
    journal_root.mkdir()

    exact = store.grant("hermes", "journal.append", {"root": journal_root, "account": "toy"})
    family = store.grant("hermes", "review.*", {"root": journal_root, "provider": "local"})
    assert exact["safety"] == SAFETY_DECLARATION
    assert store.list("hermes")["grants"]

    store.require("hermes", "journal.append", {"root": journal_root, "account": "toy"})
    store.require(
        "hermes",
        "journal.append",
        {"root": journal_root / "nested", "account": "toy"},
    )
    store.require("hermes", "review.read", {"root": journal_root, "provider": "local"})

    with pytest.raises(PermissionDenied):
        store.require("hermes", "journal.delete", {"root": journal_root, "account": "toy"})
    with pytest.raises(PermissionDenied):
        store.require("hermes", "review.read", {"root": tmp_path / "elsewhere", "provider": "local"})
    with pytest.raises(PermissionDenied):
        store.require("hermes", "journal.append", {"root": journal_root})
    with pytest.raises(PermissionDenied):
        store.require("hermes", "journal.append", {"root": journal_root, "account": "toy", "provider": "local"})
    with pytest.raises(PermissionDenied):
        store.require("hermes", "journal.append", {"root": journal_root, "account": "*"})
    with pytest.raises(ValueError):
        store.grant("hermes", "journal.append", {"root": journal_root, "region": "toy"})

    revoked = store.revoke(exact["grant_id"])
    assert revoked["revoked"] is True
    with pytest.raises(PermissionDenied):
        store.require("hermes", "journal.append", {"root": journal_root, "account": "toy"})
    assert store.revoke(exact["grant_id"])["revoked"] is True

    reopened = PermissionStore(tmp_path / "state")
    reopened.require("hermes", "review.read", {"root": journal_root, "provider": "local"})
    with pytest.raises(ValueError):
        store.grant("hermes", "order.place", {"root": journal_root})


def test_approval_starts_pending_and_rejects_secrets_and_yes_bypass(tmp_path: Path) -> None:
    store = PermissionStore(tmp_path / "state")
    payload = {"root": str(tmp_path / "journal"), "record": "toy-1", "labels": ["review"]}
    request = store.request("journal.append", payload)

    assert request["status"] == "pending"
    assert request["confirmed"] is False
    assert request["consumed"] is False
    assert request["payload"] == payload

    with pytest.raises(ApprovalError):
        store.consume(request["request_id"], "journal.append", payload, "hermes")
    with pytest.raises(ValueError):
        store.request("journal.append", {"api" + "_key": "toy-secret-value"})
    with pytest.raises(PermissionDenied):
        store.request("journal.append", {"argv": ["journal", "--yes"]})
    with pytest.raises(PermissionDenied):
        store.request("journal.append --yes", {})
    with pytest.raises(ValueError):
        validate_approval_payload({"nested": {"api" + "_key": "toy-secret-value"}})

    prose = {"note": "review password reset behavior for the toy account"}
    copy = validate_payload(prose)
    assert copy == prose
    assert copy is not prose
    assert PermissionDeniedError is PermissionDenied
    assert validate_payload({"session_id": "s1", "max_tokens": 128, "token_usage": 3}) == {
        "session_id": "s1", "max_tokens": 128, "token_usage": 3
    }
    assert validate_payload({"auth": "local metadata", "operation": "journal.import"})["operation"] == "journal.import"

    database_text = store.db_path.read_bytes()
    assert b"toy-secret-value" not in database_text


def test_approval_requires_human_confirmation_exact_match_and_one_use(tmp_path: Path) -> None:
    store = PermissionStore(tmp_path / "state")
    payload = {"root": str(tmp_path / "journal"), "record": "toy-2"}
    request = store.request("journal.append", payload, principal="hermes")

    with pytest.raises(ValueError, match="human note"):
        store.approve(request["request_id"], True)
    with pytest.raises(ValueError, match="unsafe"):
        store.approve(request["request_id"], True, "human api_key=toy-secret-value")
    denied_request = store.request("journal.append", payload, principal="reviewer")
    denied = store.approve(denied_request["request_id"], False)
    assert denied["status"] == "denied"
    with pytest.raises(ApprovalError):
        store.consume(denied_request["request_id"], "journal.append", payload, "reviewer")

    approved = store.approve(request["request_id"], True, "human reviewed toy journal append")
    assert approved["status"] == "approved"
    assert approved["confirmed"] is True
    assert approved["safety"] == SAFETY_DECLARATION

    with pytest.raises(ApprovalError):
        store.consume(request["request_id"], "journal.append", {"root": payload["root"], "record": "other"}, "hermes")
    with pytest.raises(ApprovalError):
        store.consume(request["request_id"], "journal.append", payload, "other-principal")
    assert store.consume(request["request_id"], "journal.append", payload, "hermes") is None
    with pytest.raises(ApprovalError):
        store.consume(request["request_id"], "journal.append", payload, "hermes")

    with pytest.raises(ApprovalError):
        store.approve(request["request_id"], True, "second human decision")


def test_approval_consumption_is_atomic_one_use_under_concurrency(tmp_path: Path) -> None:
    store = PermissionStore(tmp_path / "state")
    payload = {"root": str(tmp_path / "journal"), "record": "toy-concurrent"}
    request = store.request("journal.append", payload)
    store.approve(request["request_id"], True, "human reviewed concurrent toy append")

    def consume_once() -> str:
        try:
            store.consume(request["request_id"], "journal.append", payload, "hermes")
        except ApprovalError:
            return "rejected"
        return "consumed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: consume_once(), range(2)))

    assert sorted(results) == ["consumed", "rejected"]


def test_cross_process_store_persists_grant_revoke_and_one_use(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    journal_root = tmp_path / "journal"
    journal_root.mkdir()
    script = """
import json
import sys
from pathlib import Path
from smartmoney_cub_harness.control_permissions import PermissionStore

store = PermissionStore(Path(sys.argv[1]))
if sys.argv[2] == "grant":
    print(json.dumps(store.grant("hermes", "journal.append", {"root": str(Path(sys.argv[3])), "account": "toy"})))
elif sys.argv[2] == "require":
    store.require("hermes", "journal.append", {"root": Path(sys.argv[3]), "account": "toy"})
elif sys.argv[2] == "revoke":
    print(json.dumps(store.revoke(sys.argv[3])))
elif sys.argv[2] == "request":
    print(json.dumps(store.request("journal.append", {"root": sys.argv[3], "record": "cross-process"})))
elif sys.argv[2] == "approve":
    print(json.dumps(store.approve(sys.argv[3], True, "human cross-process approval")))
elif sys.argv[2] == "consume":
    store.consume(sys.argv[3], "journal.append", {"root": sys.argv[4], "record": "cross-process"}, "hermes")
"""

    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", script, str(state_root), *args],
            text=True,
            capture_output=True,
            check=check,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        )

    grant = json.loads(run("grant", str(journal_root)).stdout)
    assert run("require", str(journal_root)).returncode == 0
    revoked = json.loads(run("revoke", grant["grant_id"]).stdout)
    assert revoked["revoked"] is True
    assert run("require", str(journal_root), check=False).returncode != 0

    request = json.loads(run("request", str(journal_root)).stdout)
    json.loads(run("approve", request["request_id"]).stdout)
    assert run("consume", request["request_id"], str(journal_root)).returncode == 0
    assert run("consume", request["request_id"], str(journal_root), check=False).returncode != 0
