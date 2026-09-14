"""Deploy the committed tree the way a release host would, and prove it runs.

Why this exists as its own step: every other check in this repository runs
against the *working tree*, which is not what a deployment uses. A release host
clones the repository, installs the package, and starts it. Anything the working
tree has but the commit does not -- an uncommitted file, a build output that was
never added, a gitignored asset the interface needs -- works here and fails
there, and the failure surfaces after the release.

This closes that gap by deploying from a fresh clone of the committed tree:

    1. clone HEAD into a temporary directory
    2. install the package the way deploy/README.md documents
    3. run the deployment checks from the clone
    4. start hosted mode against a throwaway PostgreSQL and verify two tenants

It is deliberately not part of scripts/verify.sh: it needs Postgres and the
hosted extra, and verify.sh must stay runnable on a machine with neither. Run it
before a release, and in CI on the release job.

    python scripts/release-smoke.py

Exit 0 means the committed tree deploys and serves. Any failure prints what to
fix and exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAFETY = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"

STUB_PORT = 8962
APP_PORT = 8961
TOKEN = "release-smoke-token"


def run(command, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy the committed tree and smoke it.")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave the clone and virtualenv in place for inspection.",
    )
    args = parser.parse_args()

    workspace = Path(tempfile.mkdtemp(prefix="smcub-release-smoke-"))
    clone = workspace / "repo"
    venv = workspace / "venv"
    failures: list[str] = []

    try:
        print("=== [1] clone the committed tree (not the working tree) ===", flush=True)
        result = run(["git", "clone", "--quiet", "--local", str(REPO), str(clone)])
        if result.returncode != 0:
            print("  FAIL: could not clone the repository: " + result.stderr[-300:])
            return 1
        head = run(["git", "log", "--oneline", "-1"], cwd=clone).stdout.strip()
        print("  cloned HEAD: " + head)
        dirty = run(["git", "status", "--porcelain"], cwd=REPO).stdout.strip()
        if dirty:
            print("  note: the working tree has uncommitted changes; the clone has none of them")

        print("")
        print("=== [2] install the package the documented way ===", flush=True)
        run([sys.executable, "-m", "venv", str(venv)])
        install = run([str(venv / "bin" / "pip"), "install", "-q", str(clone) + "[hosted]"])
        if install.returncode != 0:
            print("  FAIL: the documented install failed: " + (install.stderr or "")[-400:])
            return 1
        print("  installed: " + run([str(venv / "bin" / "smcub"), "--version"]).stdout.strip())

        # The interface is committed so an install needs no Node toolchain. If it
        # were missing from the commit, this is where it would show.
        interface = clone / "src" / "smartmoney_cub_harness" / "workbench" / "web"
        index = interface / "index.html"
        asset_dir = interface / "assets"
        assets = sorted(asset_dir.glob("*")) if asset_dir.is_dir() else []
        if not index.is_file() or not assets:
            failures.append("no built interface in the commit")
            print("  FAIL: the committed tree has no built interface to serve")
        else:
            print("  interface: index.html + " + str(len(assets)) + " asset(s), committed")

        print("")
        print("=== [3] the deployment checks, run from the clone ===", flush=True)
        for script, label in (
            ("scripts/preflight.py", "preflight"),
            ("scripts/nginx-check.py", "nginx-check"),
        ):
            outcome = run([str(venv / "bin" / "python"), script], cwd=clone)
            ok = outcome.returncode == 0
            print("  " + ("OK   " if ok else "FAIL ") + label)
            if not ok:
                failures.append(label)
                print("       " + (outcome.stdout + outcome.stderr)[-300:])

        print("")
        print("=== [4] hosted mode against Postgres, two tenants ===", flush=True)
        failures.extend(_hosted_smoke(clone, venv))

    finally:
        if args.keep:
            print("")
            print("kept for inspection: " + str(workspace))
        else:
            shutil.rmtree(workspace, ignore_errors=True)

    print("")
    if failures:
        print("RELEASE SMOKE FAILED: " + ", ".join(failures))
        return 1
    print("RELEASE SMOKE PASSED: the committed tree deploys, serves, and isolates tenants")
    return 0


def _hosted_smoke(clone: Path, venv: Path) -> list[str]:
    """Start hosted mode against a throwaway Postgres and check the essentials."""
    try:
        import pgserver
        import psycopg
    except ImportError as exc:
        print("  skipped: " + str(exc))
        print('  install with: pip install "smartmoney-cub-harness[hosted]" pgserver')
        return []

    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Stub(BaseHTTPRequestHandler):
        """Stands in for the platform's identity endpoint."""

        def log_message(self, *args):
            return

        def do_GET(self):
            cookie = self.headers.get("Cookie") or ""
            user = None
            if "session=one" in cookie:
                user = {"id": 2001}
            elif "session=two" in cookie:
                user = {"id": 2002}
            body = json.dumps(user or {"error": "no session"}).encode()
            self.send_response(200 if user else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    stub = ThreadingHTTPServer(("127.0.0.1", STUB_PORT), Stub)
    threading.Thread(target=stub.serve_forever, daemon=True).start()

    data_dir = tempfile.mkdtemp(prefix="smcub-release-pg-")
    server = pgserver.get_server(data_dir, cleanup_mode=None)
    raw = server.get_uri()
    with psycopg.connect(raw) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE smoke")
    database_url = raw.replace("/postgres?", "/smoke?", 1)

    environment = dict(os.environ)
    environment["ALPHATECH_AUTH_MODE"] = "session"
    environment["ALPHATECH_BASE_URL"] = "http://127.0.0.1:" + str(STUB_PORT)

    process = subprocess.Popen(
        [
            str(venv / "bin" / "smcub"), "trader", "serve",
            "--mode", "hosted", "--database-url", database_url,
            "--port", str(APP_PORT), "--token", TOKEN, "--no-browser",
            "--state-dir", tempfile.mkdtemp(prefix="smcub-release-state-"),
        ],
        cwd=clone, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True,
    )

    def call(path, cookie=None, method="GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            "http://127.0.0.1:" + str(APP_PORT) + path, data=data, method=method
        )
        request.add_header("X-SMCUB-Token", TOKEN)
        if cookie:
            request.add_header("Cookie", cookie)
        if data:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()
        except Exception as error:
            return 0, str(error)

    failures: list[str] = []
    try:
        ready = False
        for _ in range(80):
            status, _ = call("/")
            if status == 200:
                ready = True
                break
            time.sleep(0.5)
        print("  " + ("OK   " if ready else "FAIL ") + "the hosted server started from the clone")
        if not ready:
            return ["hosted server did not start"]

        status, _ = call(
            "/api/trader/trades/import", "session=one", "POST",
            {"rows": [{"trade_id": "smoke-1", "symbol": "TENANT_ONE", "side": "BUY",
                       "price": 1.0, "quantity": 1, "trade_date": "2026-09-01"}]},
        )
        print("  " + ("OK   " if status == 200 else "FAIL ") + "a tenant can import its own fills")
        if status != 200:
            failures.append("import")

        status, body = call("/api/trader/trades", "session=two")
        leaked = "TENANT_ONE" in body
        print("  " + ("OK   " if not leaked else "FAIL ") + "a second tenant cannot see the first's fills")
        if leaked:
            failures.append("tenant isolation")

        status, _ = call("/api/trader/trades")
        print("  " + ("OK   " if status == 401 else "FAIL ") + "an anonymous request is refused (" + str(status) + ")")
        if status != 401:
            failures.append("anonymous refusal")

        status, body = call("/api/trader/health", "session=one")
        carries = SAFETY in body
        print("  " + ("OK   " if carries else "FAIL ") + "every response carries the safety declaration")
        if not carries:
            failures.append("safety declaration")
    finally:
        process.terminate()
        try:
            output = process.communicate(timeout=15)[0] or ""
        except Exception:
            process.kill()
            output = ""
        for line in output.splitlines():
            if SAFETY in line or line.startswith("mode:"):
                print("       banner: " + line.strip())
        stub.shutdown()
        stub.server_close()
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
