"""Prove a hosted journal can be backed up and recovered.

Why this exists: deploy/docker-compose.yml tells the operator "Back this up: it is
the user's own data", and no procedure existed anywhere in the repository. A
backup instruction that has never been restored is a belief, not a capability.
The journal is the one thing in this product a user cannot recreate, so the
recovery path is worth executing rather than describing -- and this project's
record is that every late defect lived in a path that was reviewed but never run.

The check performs the whole cycle the way a disaster would:

    1. start the product in hosted mode against a throwaway PostgreSQL
    2. write a tenant's fills through the API, the real way
    3. pg_dump the database
    4. stop that server, as a disaster would
    5. restore the dump into a fresh, empty database
    6. serve the product from the RESTORED database and verify the tenant's data
       is present and that tenant isolation survived the round trip

Step 6 is the one that matters. A dump that restores into a database the product
cannot serve from is not a backup.

    python scripts/backup-restore-check.py

Exit 0 means the journal is recoverable. Needs PostgreSQL and the hosted extra.
"""
from __future__ import annotations

import hashlib
import hmac as hmaclib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAFETY = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
TOKEN = "backup-check-token"
SECRET = "backup-check-secret"


def pg_bin() -> pathlib.Path:
    """The bundled PostgreSQL binaries (pg_dump, pg_restore)."""
    import pgserver

    binaries = pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin"
    for name in ("pg_dump", "pg_restore"):
        if not (binaries / name).exists():
            raise SystemExit("missing " + name + " under " + str(binaries))
    return binaries


def signed(user: str) -> dict[str, str]:
    stamp = str(int(time.time()))
    digest = hmaclib.new(SECRET.encode(), f"{user}:{stamp}".encode(), hashlib.sha256).hexdigest()
    return {
        "X-AlphaTech-User": user,
        "X-AlphaTech-Timestamp": stamp,
        "X-AlphaTech-Signature": digest,
        "X-SMCUB-Token": TOKEN,
    }


def call(port: int, user: str, method: str, path: str, payload: dict | None = None):
    headers = signed(user)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=body, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except Exception as error:
        return 0, str(error)


def serve(database_url: str, port: int):
    """Start the product on a port, refusing to reuse one already in use.

    A leftover listener on the port made this check pass its readiness probe
    against a *different* instance, so it dumped and asserted on the wrong
    database and reported "data did not survive" for a backup that was never
    taken. Failing loudly on a busy port is the difference between a check and a
    coincidence.
    """
    if _port_in_use(port):
        raise SystemExit(
            f"port {port} is already in use; stop that process first "
            "(a leftover server would be probed instead of this one)"
        )
    environment = dict(os.environ)
    environment["ALPHATECH_AUTH_MODE"] = "hmac"
    environment["ALPHATECH_SSO_SECRET"] = SECRET
    return subprocess.Popen(
        [
            sys.executable, "-m", "smartmoney_cub_harness.cli", "trader", "serve",
            "--mode", "hosted", "--database-url", database_url,
            "--port", str(port), "--token", TOKEN, "--no-browser",
            "--state-dir", tempfile.mkdtemp(prefix="smcub-backup-state-"),
        ],
        cwd=REPO, env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )


def _port_in_use(port: int) -> bool:
    import socket

    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def wait_ready(port: int, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if call(port, "probe", "GET", "/")[0] == 200:
            return True
        time.sleep(0.5)
    return False


def main() -> int:
    try:
        import pgserver
        import psycopg
    except ImportError as error:
        print("skipped: " + str(error))
        print('  install with: pip install "smartmoney-cub-harness[hosted]" pgserver')
        return 0

    binaries = pg_bin()
    failures: list[str] = []
    source_port, recovered_port = 8991, 8992

    print("=== [1] a source database and a serving product ===", flush=True)
    source_pg = pgserver.get_server(tempfile.mkdtemp(prefix="smcub-bk1-"), cleanup_mode="delete")
    source_raw = source_pg.get_uri()
    with psycopg.connect(source_raw) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE journal")
    source_url = source_raw.replace("/postgres?", "/journal?", 1)

    source = serve(source_url, source_port)
    if not wait_ready(source_port):
        print("  FAIL: the source product never started")
        return 1
    print("  source product ready")

    print("=== [2] write a tenant's fills through the API ===", flush=True)
    status, _ = call(
        source_port, "alice", "POST", "/api/trader/trades/import",
        {"rows": [{"trade_id": "bk-1", "symbol": "AUDIT_BACKUP_SYM", "side": "BUY",
                   "price": 3.0, "quantity": 7, "trade_date": "2026-09-01"}]},
    )
    if status != 200:
        failures.append("import")
        print("  FAIL: import returned " + str(status))
    _status, before = call(source_port, "alice", "GET", "/api/trader/trades")
    print("  alice's fill is served:", "AUDIT_BACKUP_SYM" in before)

    print("=== [3] pg_dump ===", flush=True)
    dump = pathlib.Path(tempfile.mkdtemp(prefix="smcub-dump-")) / "journal.dump"
    result = subprocess.run(
        [str(binaries / "pg_dump"), "-Fc", "-f", str(dump), source_url],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not dump.exists():
        failures.append("pg_dump")
        print("  FAIL:", result.stderr[-300:])
        return 1
    print("  dumped", dump.stat().st_size, "bytes")

    print("=== [4] stop the source, as a disaster would ===", flush=True)
    source.terminate()
    try:
        source.wait(timeout=15)
    except Exception:
        source.kill()
    print("  source stopped")

    print("=== [5] restore into a fresh, empty database ===", flush=True)
    recovered_pg = pgserver.get_server(tempfile.mkdtemp(prefix="smcub-bk2-"), cleanup_mode="delete")
    recovered_raw = recovered_pg.get_uri()
    with psycopg.connect(recovered_raw) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE recovered")
    recovered_url = recovered_raw.replace("/postgres?", "/recovered?", 1)
    result = subprocess.run(
        [str(binaries / "pg_restore"), "-d", recovered_url, str(dump)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        failures.append("pg_restore")
        print("  FAIL:", result.stderr[-300:])
    else:
        print("  restored")

    print("=== [6] serve the product FROM the restored database ===", flush=True)
    recovered = serve(recovered_url, recovered_port)
    if not wait_ready(recovered_port):
        failures.append("restored product would not start")
        print("  FAIL: the product cannot serve the restored database")
    else:
        print("  the product serves the restored database")
        _status, own = call(recovered_port, "alice", "GET", "/api/trader/trades")
        survived = "AUDIT_BACKUP_SYM" in own
        print("  the tenant's data survived:", survived)
        if not survived:
            failures.append("data did not survive the restore")

        _status, other = call(recovered_port, "bob", "GET", "/api/trader/trades")
        isolated = "AUDIT_BACKUP_SYM" not in other
        print("  tenant isolation survived:", isolated)
        if not isolated:
            failures.append("isolation lost in the restore")

        _status, health = call(recovered_port, "alice", "GET", "/api/trader/health")
        carries = SAFETY in health
        print("  the safety declaration is intact:", carries)
        if not carries:
            failures.append("safety declaration")

    recovered.terminate()

    print("")
    if failures:
        print("BACKUP/RESTORE CHECK FAILED: " + ", ".join(failures))
        return 1
    print("BACKUP/RESTORE CHECK PASSED: the journal is recoverable and still isolated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
