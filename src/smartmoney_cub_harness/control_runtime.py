"""Direct and HTTP adapters for the registered CLI operations."""
from __future__ import annotations

import inspect
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from smartmoney_cub_harness.control_operations import OPERATIONS, HUMAN_ONLY
from smartmoney_cub_harness.control_permissions import PermissionStore, PermissionDenied, _reject_symlink_components
from smartmoney_cub_harness.local_state import local_state_root, journal_dir
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


class ControlError(Exception):
    def __init__(self, code, message, exit_code=2):
        super().__init__(message)
        self.code, self.exit_code = code, exit_code


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ControlError("redirect_refused", "Service redirects are refused; configure the final trusted URL", 5)


def _query(payload):
    return {k: [json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)]
            for k, v in payload.items() if v is not None}


def _path(op, payload):
    def field(match):
        key = match.group(1)
        value = payload.get(key)
        if value is None or not str(value).strip():
            raise ControlError("missing_argument", key + " is required")
        return quote(str(value), safe="")
    return re.sub(r"\{(\w+)\}", field, op.path)


def _safe_input(payload, root):
    """Agent-controlled file paths are confined; secrets never enter tool JSON."""
    from smartmoney_cub_harness.control_permissions import validate_approval_payload
    validate_approval_payload(payload)
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"state_dir", "run_root", "server", "principal", "confirmed", "permissions_confirmed", "approval_id"}:
                    raise PermissionDenied("integration cannot override execution context or confirmation")
                if key in {"path", "output", "input_csv", "file", "rule_candidate", "directory"} or key.endswith(("_path", "_dir")):
                    raw = Path(str(item)).expanduser()
                    _reject_symlink_components(raw)
                    candidate = raw.resolve()
                    if not candidate.is_relative_to(root):
                        raise PermissionDenied("artifact path is outside configured run_root")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(payload)


class ControlRuntime:
    def __init__(self, *, state_dir=None, server=None, principal="human", run_root=None,
                 confirmed=False, allow_network=False, approval_id=None, timeout=30,
                 budget_spec=None,
                 token_env="SMCUB_ACCESS_TOKEN", cookie_env="SMCUB_SESSION_COOKIE"):
        self.root = local_state_root(state_dir).expanduser().resolve()
        self.server = server.rstrip("/") if server else None
        self.principal = principal
        self.run_root = Path(run_root).expanduser().resolve(strict=True) if run_root else None
        if principal != "human" and run_root:
            _reject_symlink_components(Path(run_root).expanduser())
        self.confirmed, self.allow_network, self.approval_id = confirmed, allow_network, approval_id
        self.timeout, self.token_env, self.cookie_env = timeout, token_env, cookie_env
        self.budget_spec = budget_spec
        self._trader = self._workbench = self._store = None
        self._operation_scopes = {}
        if self.server:
            url = urlsplit(self.server)
            if url.username or url.password or url.query or url.fragment:
                raise ControlError("invalid_server", "Service URL cannot contain credentials, query, or fragment")
            if url.scheme != "https" and not (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}):
                raise ControlError("insecure_server", "Remote service requires HTTPS")

    @property
    def permissions(self):
        return PermissionStore(self.root / "control")

    def close(self):
        if self._workbench:
            self._workbench.close()
        if self._trader:
            self._trader.close()
        if self._store:
            self._store.close()

    def _services(self):
        if self._workbench is not None:
            return self._trader, self._workbench
        if self._trader is None:
            from smartmoney_cub_harness.trader.storage import open_store
            from smartmoney_cub_harness.trader.api.service import TraderService
            from smartmoney_cub_harness.workbench.server import WorkbenchService
            self._store = open_store(journal_dir(self.root), mode="local")
            self._trader = TraderService(self._store, resume_watch=False)
            self._workbench = WorkbenchService(self.root, trader_service=self._trader)
        return self._trader, self._workbench

    def _authorize(self, op, payload):
        session_provider = None
        if op.name in {"assistant.send", "assistant.resume"}:
            _, service = self._services()
            session = service.store.get_session(str(payload.get("session_id") or ""))
            session_provider = session.get("provider_id")
            if self.budget_spec is not None and session.get("agent_id"):
                raise ControlError("unmetered_agent", "External agent costs cannot be bounded by this CLI; use a configured metered provider", 4)
        if self.principal != "human":
            if op.name in HUMAN_ONLY:
                raise PermissionDenied("credential/configuration administration requires the human interface")
            if not self.run_root or not self.run_root.is_dir():
                raise PermissionDenied("run_root must be configured for integration operations")
            _safe_input(payload, self.run_root)
            scope = {"root": str(self.run_root)}
            # Include a narrowed scope only on operations that actually apply it.
            if op.name.startswith(("journal.", "analytics.", "insight.", "playbook.", "calendar.")) and payload.get("account_id"):
                scope["account"] = str(payload["account_id"])
            if op.name in {"market.bars", "connections.accounts", "connections.connect", "connections.sync", "connections.disconnect"}:
                provider = payload.get("provider") or payload.get("provider_id")
                if provider:
                    scope["provider"] = str(provider)
            if session_provider:
                scope["provider"] = str(session_provider)
            self.permissions.require(self.principal, op.name, scope)
            self._operation_scopes[op.name] = scope
            if op.confirmation:
                if not self.approval_id:
                    raise PermissionDenied("human approval required; submit permissions.request")
                self.permissions.consume(self.approval_id, op.name, payload, self.principal)
        else:
            if op.confirmation and not self.confirmed:
                raise PermissionDenied("explicit confirmation required (--confirm or interactive prompt)")
            offline_bars = op.name in {"backtest.run", "replay.create"} and bool(payload.get("bars"))
            if op.network and not offline_bars and not self.allow_network:
                raise PermissionDenied("network access requires --allow-network")

    def execute(self, name, payload=None):
        if name not in OPERATIONS:
            raise ControlError("unknown_operation", "Unknown business operation")
        payload = dict(payload or {})
        op = OPERATIONS[name]
        if self.server and (self.budget_spec is not None or self.principal != "human"):
            return self._http(op, payload)
        if name.startswith("connections.oauth-") and not self.server and not getattr(self, "_oauth_wizard_active", False):
            raise ControlError("oauth_wizard_required", "Use connections authorize so PKCE state remains alive until the callback", 4)
        if name == "permissions.request":
            target = str(payload.get("operation") or "")
            if target not in OPERATIONS or target.startswith("permissions."):
                raise ControlError("invalid_operation", "Approval must name a registered business operation")
            return self.permissions.request(target, dict(payload.get("payload") or {}), self.principal)
        self._authorize(op, payload)
        if name.endswith(".setup"):
            if self.server:
                raise ControlError("local_setup_required", "Configure this provider using its service-local setup wizard", 4)
            from smartmoney_cub_harness.control_setup import setup_info
            identifier = str(payload.get("provider_id") or payload.get("plugin_id") or payload.get("id") or "")
            return setup_info(name.split(".")[0], identifier, self.root)
        if name == "backtest.validate":
            from smartmoney_cub_harness.trader.backtest import validate_strategy
            value = validate_strategy(payload.get("spec", payload))
            return {"status": "ok", "valid": True, "safety": SAFETY_DECLARATION}
        if name in {"replay.step", "replay.seek", "replay.rewind", "replay.pause", "replay.play"}:
            payload["action"] = name.split(".")[1]
            return self._invoke(OPERATIONS["replay.action"], payload)
        if name == "connections.watch":
            raise ControlError("stream_command_required", "Use the connections watch foreground command")
        return self._invoke(op, payload)

    def _invoke(self, op, payload):
        _path(op, payload)  # validate required identifiers consistently before effects
        if op.name == "plugin.install-catalog":
            payload = {**payload, "permissions_confirmed": True}
        if self.server:
            return self._http(op, payload)
        trader, workbench = self._services()
        if op.path.startswith("/api/trader/"):
            if trader is None:
                raise ControlError("service_not_mounted", "This service does not mount the journal API", 4)
            from smartmoney_cub_harness.trader.api.routes import dispatch
            status, value = dispatch(trader, op.method, _path(op, payload),
                query=_query(payload) if op.method == "GET" else {}, headers={},
                body=json.dumps(payload).encode() if op.method != "GET" else b"",
                content_type="application/json")
            if status >= 400:
                code = str(value.get("code") or "service_error")
                message = value.get("error") or "Business operation failed"
                raise ControlError(code, str(message), 3 if status in {401,403} else 6 if status == 409 else 5 if status >= 500 else 2)
            return value
        fn = getattr(workbench, op.handler)
        if op.name == "providers.update":
            return workbench.update_settings({"providers": {payload["provider_id"]: {k:v for k,v in payload.items() if k != "provider_id"}}})
        kwargs = {}
        for key, parameter in inspect.signature(fn).parameters.items():
            if key == "payload":
                kwargs[key] = payload
            elif key == "query":
                kwargs[key] = _query(payload)
            elif key == "enabled":
                kwargs[key] = op.name.endswith("enable")
            elif key in payload:
                kwargs[key] = payload[key]
            elif parameter.default is inspect.Parameter.empty:
                raise ControlError("missing_argument", key + " is required")
        if op.stream:
            def stream():
                with workbench.claim_session_owner() as claimed:
                    if not claimed:
                        raise ControlError("session_owner_active", "An active service owns sessions; connect using --server", 6)
                    events = iter(fn(**kwargs))
                    try:
                        while True:
                            if self.principal != "human":
                                self.permissions.require(self.principal, op.name, self._operation_scopes[op.name])
                            try:
                                event = next(events)
                            except StopIteration:
                                break
                            yield event
                    finally:
                        if hasattr(events, "close"):
                            events.close()
            return stream()
        value = fn(**kwargs)
        return value

    def _http(self, op, payload):
        path = _path(op, payload)
        controlled = self.budget_spec is not None or self.principal != "human"
        if controlled:
            path = "/api/control/execute"
            request_payload = {"operation": op.name, "payload": payload, "principal": self.principal,
                               "confirmed": self.confirmed, "allow_network": self.allow_network,
                               "approval_id": self.approval_id, "budget": self.budget_spec}
        else:
            request_payload = payload
        if not controlled and op.method == "GET" and payload:
            path += "?" + urlencode(payload, doseq=True)
        headers = {"Accept": "text/event-stream" if op.stream else "application/json", "Content-Type": "application/json"}
        token = os.environ.get(self.token_env)
        cookie = os.environ.get(self.cookie_env)
        if token:
            headers["X-SMCUB-Token"] = token
        if cookie:
            headers["Cookie"] = cookie
        request = Request(self.server + path, method="POST" if controlled else op.method, headers=headers,
                          data=json.dumps(request_payload).encode() if controlled or op.method != "GET" else None)
        try:
            response = build_opener(NoRedirect).open(request, timeout=self.timeout)
        except HTTPError as exc:
            # Do not echo arbitrary upstream bodies containing credentials/private records.
            raise ControlError("http_error", "Service returned HTTP " + str(exc.code), 3 if exc.code in {401,403} else 5) from None
        except (URLError, TimeoutError) as exc:
            raise ControlError("unreachable", "Service unreachable; no local fallback was attempted", 5) from None
        if op.stream:
            def events():
                with response:
                    data = []
                    for line in response:
                        text = line.decode("utf-8").rstrip("\r\n")
                        if text.startswith("data:"):
                            data.append(text[5:].lstrip())
                        elif not text and data:
                            yield json.loads("\n".join(data)); data = []
                    if data:
                        yield json.loads("\n".join(data))
            return events()
        with response:
            if op.name == "benchmark.image":
                return response.read()
            return json.load(response)
