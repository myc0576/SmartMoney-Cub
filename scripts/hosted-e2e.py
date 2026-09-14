"""Hosted-mode end-to-end check: the deployment configuration, actually run.

Why this exists as a script rather than a unit test: the unit tests cover the
storage, auth, and API layers separately with a SQLite store, and they skip the
Postgres path entirely when no database is present. That leaves the one
configuration a hosted deployment actually uses — Postgres plus platform
identity plus two tenants at once — never executed end to end. This script runs
it against a real PostgreSQL and asserts the properties that matter.

It is opt-in because it needs a database and a driver:
    pip install "smartmoney-cub-harness[hosted]" pgserver
    SMARTMONEY_HOSTED_E2E=1 python scripts/hosted-e2e.py

Without SMARTMONEY_HOSTED_E2E it prints why it skipped and exits 0, so it can sit
in a pipeline without becoming a false failure on a machine that cannot host one.

It checks both platform auth modes. Session mode is the default a hosted
deployment runs, and it is checked first because it is the one a real browser
reaches: the caller's platform cookie is forwarded to the platform, and the
frontend sends no auth header of its own. Signed-header mode is the fallback.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

SECRET = "hosted-e2e-secret"
PORT = int(os.environ.get("SMCUB_E2E_PORT", "8831"))
REPO = Path(__file__).resolve().parents[1]
SAFETY = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"


def signed(user: str) -> dict[str, str]:
    stamp = str(int(time.time()))
    digest = hmac.new(SECRET.encode(), f"{user}:{stamp}".encode(), hashlib.sha256).hexdigest()
    return {
        "X-AlphaTech-User": user,
        "X-AlphaTech-Timestamp": stamp,
        "X-AlphaTech-Signature": digest,
    }


def call(user: str, method: str, path: str, payload: dict | None = None):
    headers = signed(user)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode() or "{}")


def main() -> int:
    if os.environ.get("SMARTMONEY_HOSTED_E2E") not in {"1", "true", "yes"}:
        print("skipped: set SMARTMONEY_HOSTED_E2E=1 to run the hosted check.")
        print("This check needs a PostgreSQL it may start itself, plus the psycopg driver:")
        print('  pip install "smartmoney-cub-harness[hosted]" pgserver')
        return 0

    try:
        import pgserver
        import psycopg
    except ImportError as exc:
        print(f"skipped: {exc}. Install with:")
        print('  pip install "smartmoney-cub-harness[hosted]" pgserver')
        return 0

    data_dir = tempfile.mkdtemp(prefix="smcub-e2e-")
    # cleanup_mode="delete" stops the server and removes its data directory when
    # the last handle closes. The previous value, None, means "never stop or
    # delete", so every run left a PostgreSQL process behind. Since this script
    # now runs in CI on every push and locally on every release, that leak
    # accumulated until the next initdb failed and the check broke the machine it
    # was verifying.
    server = pgserver.get_server(data_dir, cleanup_mode="delete")
    raw = server.get_uri()
    with psycopg.connect(raw) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE trader")
    # pgserver returns a unix-socket URI; swap the database name in place rather
    # than splitting on '/', which would cut into the socket directory path.
    database_url = raw.replace("/postgres?", "/trader?", 1)
    print("[1] postgres started, database 'trader' created")

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO / "src")
    environment["ALPHATECH_AUTH_MODE"] = "hmac"
    environment["ALPHATECH_SSO_SECRET"] = SECRET
    state_dir = tempfile.mkdtemp(prefix="smcub-e2e-state-")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "smartmoney_cub_harness.cli", "trader", "serve",
            "--mode", "hosted", "--database-url", database_url,
            "--port", str(PORT), "--no-browser", "--state-dir", state_dir,
        ],
        cwd=REPO, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        # Hosted mode authenticates every request, so the readiness probe signs in.
        # An anonymous probe would see 401 forever and look like a failed start.
        health = None
        for _ in range(60):
            status, payload = call("readiness-probe", "GET", "/api/trader/health")
            if status == 200:
                health = payload
                break
            time.sleep(0.5)
        if health is None:
            print("the hosted server did not become ready")
            if process.stdout:
                print(process.stdout.read()[-1500:])
            return 1
        print(f"[2] hosted server ready | auth_mode={health.get('auth_mode')}")

        for tenant, symbol, buy, sell in (
            ("alice", "AAA", 10.0, 12.0),
            ("bob", "BBB", 20.0, 18.0),
        ):
            status, payload = call(tenant, "POST", "/api/trader/trades/import", {"rows": [
                {"trade_id": f"{tenant}-b", "symbol": symbol, "side": "BUY",
                 "price": buy, "quantity": 100, "trade_date": "2026-09-01"},
                {"trade_id": f"{tenant}-s", "symbol": symbol, "side": "SELL",
                 "price": sell, "quantity": 100, "trade_date": "2026-09-03"},
            ]})
            if status != 200 or payload.get("inserted_count") != 2:
                print(f"[3] {tenant} import failed: {status} {payload}")
                return 1
            print(f"[3] {tenant} imported 2 fills of {symbol}")

        status_a, body_a = call("alice", "GET", "/api/trader/trades")
        status_b, body_b = call("bob", "GET", "/api/trader/trades")
        if (status_a, status_b) != (200, 200):
            print(f"[4] read failed: {status_a} {status_b}")
            return 1
        text_a, text_b = json.dumps(body_a), json.dumps(body_b)
        symbols_a = {row["symbol"] for row in body_a["trades"]}
        symbols_b = {row["symbol"] for row in body_b["trades"]}
        print(f"[4] alice sees {sorted(symbols_a)} | bob sees {sorted(symbols_b)}")
        if symbols_a != {"AAA"} or symbols_b != {"BBB"}:
            print("[4] FAIL: a tenant read rows that are not theirs")
            return 1
        if "BBB" in text_a or "AAA" in text_b:
            print("[4] FAIL: one tenant's payload contains the other's symbol")
            return 1
        print("    PASS: tenant isolation holds over HTTP")

        request = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/trader/trades")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                print(f"[5] FAIL: unauthenticated request accepted with {response.status}")
                return 1
        except urllib.error.HTTPError as error:
            payload = json.loads(error.read().decode() or "{}")
            if error.code != 401:
                print(f"[5] FAIL: expected 401, got {error.code}")
                return 1
            if payload.get("safety") != SAFETY:
                print("[5] FAIL: the refusal body dropped the safety declaration")
                return 1
            print(f"[5] unauthenticated refused with 401, declaration intact")

        tampered = signed("alice")
        tampered["X-AlphaTech-Signature"] = "deadbeef"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(f"http://127.0.0.1:{PORT}/api/trader/trades", headers=tampered),
                timeout=10,
            ) as response:
                print(f"[6] FAIL: tampered signature accepted with {response.status}")
                return 1
        except urllib.error.HTTPError as error:
            if error.code != 401:
                print(f"[6] FAIL: expected 401, got {error.code}")
                return 1
            print("[6] tampered signature refused with 401")

        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT user_id, count(*) FROM trades GROUP BY user_id ORDER BY user_id")
                per_tenant = cursor.fetchall()
        print(f"[7] rows in postgres per tenant: {per_tenant}")
        if len(per_tenant) != 2:
            print("[7] FAIL: expected both tenants to have their own rows in postgres")
            return 1

        print()
        print("ALL HOSTED-MODE CHECKS PASSED")
        print()
        if session_mode_check(database_url) != 0:
            return 1
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except Exception:
            process.kill()


class _PlatformStub(BaseHTTPRequestHandler):
    """Answers /api/user/self the way the platform does.

    new-api returns 401 when the session is absent or invalid, and the user
    object when it is valid. Standing this up locally is what lets the default
    session mode be checked without the real platform.
    """

    valid_cookie = "session=hosted-e2e-session"

    def log_message(self, *args) -> None:  # noqa: D102 - silence the test server
        return

    def do_GET(self) -> None:  # noqa: N802 - the handler interface dictates the name
        if self.path.split("?")[0] != "/api/user/self":
            self.send_response(404)
            self.end_headers()
            return
        if self.valid_cookie not in (self.headers.get("Cookie") or ""):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"success":false}')
            return
        body = json.dumps({"id": 42, "username": "e2e-user", "display_name": "E2E User"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def session_mode_check(database_url: str) -> int:
    """Check the default hosted auth mode: the platform session cookie.

    Why this is separate from the signed-header check above: session mode is what
    a hosted deployment runs by default, and it is the only mode a browser can
    reach, because the frontend sets no auth header and relies on the cookie jar.
    A deployment could pass every signed-header test and still refuse every real
    user; that is exactly the gap this closes.
    """
    platform_port = PORT + 10
    app_port = PORT + 11
    stub = ThreadingHTTPServer(("127.0.0.1", platform_port), _PlatformStub)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    print(f"[8] stub platform on {platform_port} (answers /api/user/self)")

    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO / "src")
    environment["ALPHATECH_AUTH_MODE"] = "session"
    environment["ALPHATECH_BASE_URL"] = f"http://127.0.0.1:{platform_port}"
    environment.pop("ALPHATECH_SSO_SECRET", None)
    state_dir = tempfile.mkdtemp(prefix="smcub-e2e-session-")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "smartmoney_cub_harness.cli", "trader", "serve",
            "--mode", "hosted", "--database-url", database_url,
            "--port", str(app_port), "--no-browser", "--state-dir", state_dir,
        ],
        cwd=REPO, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    def call(cookie: str | None, path: str = "/api/trader/health"):
        headers = {"Cookie": cookie} if cookie else {}
        request = urllib.request.Request(f"http://127.0.0.1:{app_port}{path}", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode() or "{}")
        except Exception as error:  # the server may still be starting
            return 0, {"error": str(error)}

    try:
        status = 0
        for _ in range(60):
            status, _ = call(_PlatformStub.valid_cookie)
            if status == 200:
                break
            time.sleep(0.5)
        if status != 200:
            print("[9] FAIL: the session-mode server never became ready")
            if process.stdout:
                print(process.stdout.read()[-1200:])
            return 1

        status, body = call(_PlatformStub.valid_cookie)
        identity = body.get("user_id", "")
        print(f"[9] valid platform session -> {status} | identity {identity}")
        if status != 200 or not identity.endswith("42"):
            print("[9] FAIL: a valid platform session was not resolved to the platform user")
            return 1

        status, _ = call("session=wrong")
        print(f"[10] invalid session -> {status}")
        if status != 401:
            print("[10] FAIL: an invalid session was accepted")
            return 1

        status, body = call(None)
        print(f"[11] no session -> {status}")
        if status != 401 or body.get("safety") != SAFETY:
            print("[11] FAIL: an anonymous request was accepted, or the refusal lost the declaration")
            return 1

        status, body = call(_PlatformStub.valid_cookie, "/api/trader/trades")
        print(f"[12] journal readable through the cookie -> {status} | trades {body.get('count')}")
        if status != 200:
            print("[12] FAIL: the session could not read its own journal")
            return 1

        print()
        print("ALL SESSION-MODE CHECKS PASSED")
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except Exception:
            process.kill()
        stub.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
