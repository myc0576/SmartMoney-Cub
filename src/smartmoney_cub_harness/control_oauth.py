"""Human-operated loopback OAuth without losing the in-memory PKCE state."""
from __future__ import annotations

import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from smartmoney_cub_harness.control_runtime import ControlError
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def authorize(runtime, payload, emit):
    if runtime.principal != "human" or not runtime.confirmed or not runtime.allow_network:
        raise PermissionError("OAuth requires a human confirmation and network permission")
    if runtime.server:
        raise ControlError("local_callback_required", "Run the authorization wizard on the account-service host", 4)
    seconds = float(payload.get("wait_seconds", 600))
    if not 1 <= seconds <= 600:
        raise ValueError("OAuth wait_seconds must be between 1 and 600")
    callback = "/api/trader/connections/snaptrade-personal-mcp/oauth/callback"
    outcome = {}
    runtime._oauth_wizard_active = True

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Callback query contains a single-use authorization code.

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            if parsed.path != callback or query.get("state", [None])[0] != outcome.get("state"):
                self.send_error(400, "Invalid callback")
                return
            try:
                outcome["result"] = runtime.execute("connections.oauth-complete", {
                    "state": query["state"][0], "code": query.get("code", [""])[0]})
                status, message = 200, b"Authorization processed. Return to your terminal."
            except Exception:
                outcome["error"] = True
                status, message = 400, b"Authorization failed. See the terminal."
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(message)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = 1
        started = runtime.execute("connections.oauth-start", {
            "redirect_uri": f"http://127.0.0.1:{server.server_port}{callback}"})
        outcome["state"] = started["state"]
        emit({"status": "awaiting_user", "authorization_url": started["authorization_url"],
              "expires_in": seconds, "safety": SAFETY_DECLARATION})
        until = time.monotonic() + seconds
        while time.monotonic() < until and "result" not in outcome and "error" not in outcome:
            server.handle_request()
    if "result" in outcome:
        return outcome["result"]
    raise ControlError("oauth_failed" if outcome.get("error") else "oauth_timeout",
                       "Authorization did not complete; no journal sync was started", 5)
