"""Authenticated server-side capability and budget enforcement for CLI clients."""
from __future__ import annotations

import os

from smartmoney_cub_harness.control_budget import BudgetGuard, paid_budget
from smartmoney_cub_harness.control_operations import OPERATIONS, capabilities
from smartmoney_cub_harness.control_runtime import ControlRuntime
from smartmoney_cub_harness.safety import redact
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def describe():
    return {**capabilities(), "server_enforced_permissions": True, "server_enforced_budget": True}


def execute(handler):
    """Called only after WorkbenchHandler authentication has succeeded."""
    try:
        request = handler._read_json()
        name = request.get("operation")
        if name not in OPERATIONS:
            raise ValueError("unknown operation")
        principal = str(request.get("principal") or "human")
        run_root = os.environ.get("SMCUB_CONTROL_RUN_ROOT")
        if principal != "human" and not run_root:
            raise PermissionError("service operator must configure SMCUB_CONTROL_RUN_ROOT")
        budget = request.get("budget") or {"cap_usd": "0", "pricing": {"__unpriced__": {
            "input_usd_per_million": 0, "output_usd_per_million": 0}}, "max_calls": 1}
        guard = BudgetGuard(**budget)
        runtime = ControlRuntime(state_dir=handler.service.root, principal=principal, run_root=run_root,
                                 confirmed=request.get("confirmed") is True and principal == "human",
                                 allow_network=request.get("allow_network") is True,
                                 approval_id=request.get("approval_id"), budget_spec=budget)
        # Reuse the authenticated service and its session owner. Never recover
        # sessions or create a separate store as a side effect of an HTTP call.
        runtime._workbench = handler.service
        runtime._trader = handler.trader_service or handler.service.trader_service
        with paid_budget(guard):
            result = runtime.execute(name, request.get("payload") or {})
            if OPERATIONS[name].stream:
                handler._stream_events(str((request.get("payload") or {}).get("session_id") or ""), result)
            elif name == "benchmark.image" and isinstance(result, tuple):
                body, mime = result
                handler.send_response(200)
                handler.send_header("Content-Type", mime)
                handler.send_header("Content-Length", str(len(body)))
                handler.end_headers()
                handler.wfile.write(body)
            else:
                handler._json(redact(result))
    except Exception as error:
        handler._json({"status": "error", "code": getattr(error, "code", "permission_denied" if isinstance(error, PermissionError) else "invalid_request"),
                       "error": str(redact(str(error))), "safety": SAFETY_DECLARATION},
                      status=403 if isinstance(error, PermissionError) else 400)
