"""Pre-flight a deployment before it faces users.

Why this exists: every defect found late in this build lived in the operator's
path, not the code path. The nginx prefix, the token gate, the bare /api
spelling, the multi-user advisory, and the release workflow were all *reviewed*
and all wrong, because nothing had ever executed the shape they describe.

This script executes that shape. It starts the product the way the service units
start it, puts the shipped proxy rules in front of it, and asserts the properties
a launch depends on. Run it against a staging deployment before pointing users at
it, and against production after any config change.

    python scripts/preflight.py                 # local mode, fastest check
    python scripts/preflight.py --mode hosted   # needs DATABASE_URL

Exit 0 means the deployment answers correctly. Any failure prints what to fix.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAFETY = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
TOKEN = "preflight-token"


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def request(url: str, *, token: str | None = None, cookie: str | None = None):
    headers = {}
    if token:
        headers["X-SMCUB-Token"] = token
    if cookie:
        headers["Cookie"] = cookie
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()


class Proxy:
    """The shipped nginx rules, applied by a stand-in that follows them exactly.

    Reproducing the config's own precedence is the point: the prefix, the token
    injection, and the longest-prefix choice are what the deployment relies on,
    and reading them has proven insufficient.
    """

    def __init__(self, app: str, port: int, token: str, prefix: str = "/trader"):
        self.app, self.port, self.token, self.prefix = app, port, token, prefix
        self.proc = None

    def start(self):
        script = REPO / "scripts" / "_preflight_proxy.cjs"
        self.proc = subprocess.Popen(
            ["node", str(script), self.app, str(self.port), self.token, self.prefix],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(40):
            status, _ = request(f"http://127.0.0.1:{self.port}{self.prefix}/")
            if status:
                return True
            time.sleep(0.25)
        return False

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except Exception:
                self.proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-flight a trader deployment.")
    parser.add_argument("--mode", default="local", choices=["local", "hosted"])
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args()

    failures: list[str] = []
    notes: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(f"  {'OK  ' if condition else 'FAIL'} {label}" + (f"  [{detail}]" if detail and not condition else ""))
        if not condition:
            failures.append(label)

    app_port, proxy_port = _free_port(), _free_port()
    state = tempfile.mkdtemp(prefix="preflight-state-")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(REPO / "src")
    environment["TRADER_ACCESS_TOKEN"] = TOKEN
    if args.mode == "hosted" and not args.database_url:
        print("--mode hosted needs --database-url or DATABASE_URL")
        return 2

    # Start the product the way deploy/trader.service does: hosted or local, a
    # loopback bind, and a required access token.
    command = [
        sys.executable, "-m", "smartmoney_cub_harness.cli", "trader", "serve",
        "--mode", args.mode, "--host", "127.0.0.1", "--port", str(app_port),
        "--token", TOKEN, "--no-browser", "--state-dir", state,
    ]
    if args.mode == "hosted":
        command += ["--database-url", args.database_url]
    process = subprocess.Popen(
        command, cwd=REPO, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    proxy = Proxy(f"http://127.0.0.1:{app_port}", proxy_port, TOKEN)
    try:
        print(f"[1] start the product as the service units do  (mode={args.mode})")
        ready = False
        for _ in range(60):
            status, _ = request(f"http://127.0.0.1:{app_port}/")
            if status:
                ready = True
                break
            time.sleep(0.5)
        if not ready:
            print("    the server never answered")
            if process.stdout:
                print(process.stdout.read()[-1200:])
            return 1
        print(f"    up on 127.0.0.1:{app_port}")

        print()
        print("[2] the access token gates the data, not the interface")
        for path in ("/api", "/api/", "/api/trader/health", "/api/overview", "/api/settings", "/api/audit"):
            status, body = request(f"http://127.0.0.1:{app_port}{path}")
            is_json = body[:1] == b"{"
            check(f"{path} needs the token", status == 401 and not (status == 200 and is_json),
                  f"got {status}")
        for path in ("/", "/any/client/route"):
            status, _ = request(f"http://127.0.0.1:{app_port}{path}")
            check(f"{path} serves the interface without a token", status == 200, f"got {status}")

        print()
        print("[3] the shipped proxy rules carry the token for browsers")
        if not proxy.start():
            check("the proxy came up", False)
        else:
            status, _ = request(f"http://127.0.0.1:{proxy_port}/trader/")
            check("/trader/ serves the interface", status == 200, f"got {status}")
            status, body = request(f"http://127.0.0.1:{proxy_port}/trader/api/trader/health")
            # What this route returns depends on the mode, and asserting 200 in
            # both would be wrong. In local mode the process is the single local
            # user and the token is the only gate, so it answers 200. In hosted
            # mode the token gets the request past the proxy, and then the request
            # still needs a platform identity -- without one 401 is the correct
            # answer, and it proves the token reached the app (otherwise the
            # refusal would have come from the proxy and never reached the app's
            # own error shape).
            try:
                payload = json.loads(body)
                has_declaration = payload.get("safety") == SAFETY
            except Exception:
                payload, has_declaration = {}, False

            if args.mode == "local":
                check("/trader/api/trader/health answers through the proxy", status == 200, f"got {status}")
                check("the response carries the safety declaration", has_declaration)
            else:
                # Hosted: the app must have seen the request (its own refusal shape),
                # which is what shows the proxy's token header reached it.
                saw_the_app = status in (200, 401) and bool(payload)
                check("the request reached the app through the proxy", saw_the_app, f"got {status}")
                if status == 401:
                    check("the refusal is the app's own shape, not the proxy's",
                          has_declaration, str(payload)[:60])
                    notes.append(
                        "hosted mode answered 401 through the proxy, which is correct without "
                        "a platform identity; the token header reached the app."
                    )
                else:
                    check("the response carries the safety declaration", has_declaration)

            # The trust boundary, checked because getting it wrong is invisible
            # from the outside: the proxy injects the access token for every
            # visitor, so the token cannot tell one person from another, and a
            # published workbench surface would show each of them the same
            # container-local state. Confirm the shipped rules close it, and that
            # the tenant-scoped surface stays open.
            boundary_paths = (
                "/trader/api/settings",
                "/trader/api/assistant/sessions",
                "/trader/api/overview",
            )
            leaked = []
            for path in boundary_paths:
                status, _ = request(f"http://127.0.0.1:{proxy_port}{path}")
                if status == 403:
                    continue
                # A refusal from the app (401) still means the proxy forwarded it,
                # which is exactly the exposure: the app has no tenant identity to
                # refuse on for these routes in local mode.
                leaked.append(f"{path}={status}")
            check(
                "the workbench API is closed at the trust boundary",
                not leaked,
                ", ".join(leaked),
            )

            status, _ = request(f"http://127.0.0.1:{proxy_port}/trader/api/trader/health")
            check(
                "the tenant-scoped API stays reachable through the proxy",
                status in (200, 401),
                f"got {status}",
            )

        print()
        print("[4] the product refuses a misconfigured deployment")
        for name, value in (("ALPHATECH_AUTH_MODE", "typo"),):
            probe_env = dict(environment)
            probe_env[name] = value
            probe = subprocess.run(
                [sys.executable, "-c",
                 "import sys; sys.path.insert(0, 'src');"
                 "from smartmoney_cub_harness.trader.auth import resolve_identity, AuthError;"
                 "resolve_identity({}, mode='hosted')"],
                cwd=REPO, env=probe_env, capture_output=True, text=True, timeout=40,
            )
            refused = probe.returncode != 0 and "AuthError" in probe.stderr
            check(f"{name}={value} is refused rather than falling open", refused,
                  (probe.stderr.strip().splitlines() or ["no output"])[-1][:60])

        print()
        print("[5] the safety contract is intact")
        doctor = subprocess.run([sys.executable, "-m", "smartmoney_cub_harness.cli", "doctor"],
                                cwd=REPO, env=environment, capture_output=True, text=True, timeout=60)
        try:
            payload = json.loads(doctor.stdout)
            check("doctor carries the safety declaration", payload.get("safety") == SAFETY)
            check("execution integrations stay disabled",
                  payload.get("execution_integrations") == "disabled")
            check("no broker API is required", payload.get("broker_api_required") is False)
        except Exception as exc:
            check("doctor produced readable output", False, str(exc))
    finally:
        proxy.stop()
        process.terminate()
        try:
            process.wait(timeout=10)
        except Exception:
            process.kill()

    print()
    if failures:
        print(f"PRE-FLIGHT FAILED: {len(failures)} check(s) need attention")
        for item in failures:
            print("  -", item)
        return 1
    print("PRE-FLIGHT PASSED: this deployment answers the way it is supposed to.")
    for note in notes:
        print("  note:", note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
