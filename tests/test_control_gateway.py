"""Real-socket coverage for the authenticated control gateway."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from smartmoney_cub_harness.control_budget import BudgetError
from smartmoney_cub_harness.control_runtime import ControlError, ControlRuntime
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.api.service import TraderService
from smartmoney_cub_harness.trader.storage import open_store
from smartmoney_cub_harness.workbench.server import WorkbenchHandler, WorkbenchService

TOKEN = "toy-control-token"


@contextmanager
def _server(root: Path, run_root: Path | None = None):
    workbench = WorkbenchService(root)
    trader_store = open_store(root, mode="local")
    trader = TraderService(trader_store, auth_mode="local")
    handler = type("ControlGatewayHandler", (WorkbenchHandler,), {
        "service": workbench, "asset_dir": None, "access_token": TOKEN,
        "trader_service": trader,
    })
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if run_root is not None:
            import os
            os.environ["SMCUB_CONTROL_RUN_ROOT"] = str(run_root)
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        if run_root is not None:
            import os
            os.environ.pop("SMCUB_CONTROL_RUN_ROOT", None)
        server.shutdown()
        server.server_close()
        trader_store.close()
        workbench.close()


def _request(base: str, path: str, *, token: str | None = TOKEN, payload: dict | None = None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-SMCUB-Token"] = token
    request = urllib.request.Request(base + path, headers=headers, method="GET" if payload is None else "POST",
                                     data=None if payload is None else json.dumps(payload).encode())
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, error.headers, json.loads(error.read().decode())


def _remote(root: Path, base: str, *, principal="human", budget=None, allow_network=False) -> ControlRuntime:
    return ControlRuntime(state_dir=root, server=base, principal=principal, run_root=root.parent / "run-root",
                          budget_spec=budget, allow_network=allow_network, timeout=10)


def _control_payload(operation: str, payload: dict | None = None, **extra) -> dict:
    return {"operation": operation, "payload": payload or {}, **extra}


def test_authenticated_post_and_capabilities_have_no_client_fallback(tmp_path, monkeypatch):
    root = tmp_path / "state"; root.mkdir()
    run_root = tmp_path / "run-root"; run_root.mkdir()
    with _server(root, run_root) as base:
        status, _, capabilities = _request(base, "/api/control/capabilities")
        assert status == 200
        assert capabilities["server_enforced_permissions"] is True
        assert capabilities["server_enforced_budget"] is True
        monkeypatch.setenv("SMCUB_ACCESS_TOKEN", TOKEN)
        runtime = _remote(root, base)
        try:
            assert runtime.execute("preferences.update", {"locale": "en-US"})["preferences"]["locale"] == "en-US"
        finally:
            runtime.close()
        status, _, denied = _request(base, "/api/control/execute", token="wrong",
                                     payload=_control_payload("preferences.show"))
        assert status == 401
        assert denied["safety"] == SAFETY_DECLARATION
        remote = _remote(root, base, principal="hermes")
        try:
            monkeypatch.setenv("SMCUB_ACCESS_TOKEN", "wrong")
            monkeypatch.setattr("smartmoney_cub_harness.control_runtime.ControlRuntime._services",
                                lambda *args, **kwargs: pytest.fail("client fallback was attempted"))
            with pytest.raises(ControlError, match="HTTP 401"):
                remote.execute("preferences.show")
        finally:
            remote.close()


def test_server_grant_and_revoke_are_effective_for_nonhuman_remote_calls(tmp_path, monkeypatch):
    root = tmp_path / "state"; root.mkdir()
    run_root = tmp_path / "run-root"; run_root.mkdir()
    with _server(root, run_root) as base:
        monkeypatch.setenv("SMCUB_ACCESS_TOKEN", TOKEN)
        admin = ControlRuntime(state_dir=root)
        grant = admin.permissions.grant("hermes", "preferences.show", {"root": str(run_root)})
        admin.close()
        remote = _remote(root, base, principal="hermes")
        try:
            assert remote.execute("preferences.show")["status"] == "ok"
            remote.permissions.revoke(grant["grant_id"])
            with pytest.raises(ControlError, match="HTTP 403"):
                remote.execute("preferences.show")
        finally:
            remote.close()


@pytest.mark.xfail(reason="import.manual and journal.list use separate workbench/trader stores", strict=True)
def test_remote_human_preferences_and_journal_match_shared_server_state(tmp_path, monkeypatch):
    root = tmp_path / "state"; root.mkdir()
    run_root = tmp_path / "run-root"; run_root.mkdir()
    with _server(root, run_root) as base:
        monkeypatch.setenv("SMCUB_ACCESS_TOKEN", TOKEN)
        local = ControlRuntime(state_dir=root)
        assert local.execute("preferences.update", {"theme": "light"})["preferences"]["theme"] == "light"
        local.close()
        remote = _remote(root, base)
        try:
            assert remote.execute("preferences.show")["preferences"]["theme"] == "light"
            imported = remote.execute("import.manual", {"trade_id": "TOY-GATEWAY-1", "trade_date": "2026-09-01",
                "trade_time": "09:30:00", "symbol": "TOY-GATEWAY", "side": "BUY",
                "price": 10.0, "quantity": 5.0, "fee": 0.1})
            assert imported["inserted_count"] == 1
            assert remote.execute("journal.list")["fills"]
        finally:
            remote.close()


def test_budget_cannot_bypass_transport_and_malformed_budget_fails_before_call(tmp_path, monkeypatch):
    root = tmp_path / "state"; root.mkdir()
    run_root = tmp_path / "run-root"; run_root.mkdir()
    calls = []
    import urllib.request
    original_urlopen = urllib.request.urlopen
    def reject_provider_url(*args, **kwargs):
        url = str(getattr(args[0], "full_url", args[0])) if args else ""
        if "127.0.0.1" not in url and "localhost" not in url:
            calls.append((args, kwargs))
            pytest.fail("toy gateway attempted provider transport")
        return original_urlopen(*args, **kwargs)
    monkeypatch.setattr("smartmoney_cub_harness.agent.providers.urllib.request.urlopen", reject_provider_url)
    with _server(root, run_root) as base:
        monkeypatch.setenv("SMCUB_ACCESS_TOKEN", TOKEN)
        malformed = _control_payload("assistant.send", {"session_id": "missing", "text": "toy"},
            principal="human", budget={"cap_usd": "not-a-budget", "pricing": {}, "max_calls": 1})
        status, _, body = _request(base, "/api/control/execute", payload=malformed)
        assert status == 400
        assert body["safety"] == SAFETY_DECLARATION
        assert calls == []
        budget = {"cap_usd": "0", "pricing": {"toy-model": {"input_usd_per_million": 1, "output_usd_per_million": 1}}, "max_calls": 1}
        remote = _remote(root, base, budget=budget)
        try:
            setup = ControlRuntime(state_dir=root, server=base)
            session = setup.execute("assistant.create", {"provider_id": "offline", "model": "toy-model"})
            setup.close()
            with pytest.raises(ControlError, match="HTTP 403"):
                list(remote.execute("assistant.send", {"session_id": session["session"]["session_id"], "text": "toy"}))
            assert calls == []
        finally:
            remote.close()


@pytest.mark.xfail(reason="control_http recursively re-enters controlled runtime for assistant streaming", strict=True)
def test_remote_assistant_stream_supports_toy_offline_provider(tmp_path, monkeypatch):
    root = tmp_path / "state"; root.mkdir()
    run_root = tmp_path / "run-root"; run_root.mkdir()
    with _server(root, run_root) as base:
        monkeypatch.setenv("SMCUB_ACCESS_TOKEN", TOKEN)
        setup = ControlRuntime(state_dir=root, server=base)
        session = setup.execute("assistant.create", {"provider_id": "offline", "title": "toy stream"})
        setup.close()
        remote = _remote(root, base, budget={"cap_usd": "0", "pricing": {"__unpriced__": {"input_usd_per_million": 0, "output_usd_per_million": 0}}, "max_calls": 1})
        try:
            events = list(remote.execute("assistant.send", {"session_id": session["session"]["session_id"], "text": "review toy evidence"}))
            assert events
            assert any(event["kind"] == "delta" for event in events)
            assert events[-1]["kind"] == "done"
            assert all(event["safety"] == SAFETY_DECLARATION for event in events)
        finally:
            remote.close()
