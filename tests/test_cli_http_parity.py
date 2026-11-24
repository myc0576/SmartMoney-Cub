from __future__ import annotations

import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from smartmoney_cub_harness.control_operations import OPERATIONS
from smartmoney_cub_harness.control_runtime import ControlError, ControlRuntime
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.api.service import TraderService
from smartmoney_cub_harness.trader.storage import open_store
from smartmoney_cub_harness.workbench.server import WorkbenchHandler, WorkbenchService

TOKEN = "toy-local-token"


def _manual_fill(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "trade_date": "2026-09-01", "trade_time": "09:40:00",
        "symbol": "TOY-CLI", "name": "Toy CLI Instrument", "side": "BUY",
        "price": 10.0, "quantity": 100.0, "fee": 1.0,
    }
    value.update(overrides)
    return value


@contextmanager
def _server(root: Path):
    workbench = WorkbenchService(root)
    trader_store = open_store(root, mode="local")
    trader = TraderService(trader_store, auth_mode="local")
    handler = type("ParityHandler", (WorkbenchHandler,), {
        "service": workbench, "asset_dir": None, "access_token": TOKEN,
        "trader_service": trader,
    })
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        trader_store.close()
        workbench.close()


def _runtime(root: Path, *, server: str | None = None) -> ControlRuntime:
    return ControlRuntime(state_dir=root, server=server, timeout=10)


def test_registered_workbench_reads_and_mutations_match_local_and_http(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "toy-state"
    root.mkdir()
    monkeypatch.setenv("SMCUB_ACCESS_TOKEN", TOKEN)
    local = _runtime(root)
    try:
        preferences = local.execute("preferences.show")
        assert preferences["status"] == "ok"
        assert preferences["safety"] == SAFETY_DECLARATION
        changed = local.execute("preferences.update", {"locale": "en-US", "theme": "light"})
        assert changed["preferences"]["locale"] == "en-US"
        assert local.execute("import.manual", _manual_fill())["inserted_count"] == 1
        session = local.execute("assistant.create", {"title": "CLI parity", "provider_id": "offline"})
        session_id = session["session"]["session_id"]
        assert local.execute("assistant.show", {"session_id": session_id})["session"]["title"] == "CLI parity"
        account = local.execute("accounts.save", {"account_id": "ACC-TOY", "name": "Toy account"})
        assert account["account"]["account_id"] == "ACC-TOY"
    finally:
        local.close()
    with _server(root) as base:
        remote = _runtime(root, server=base)
        try:
            assert remote.execute("preferences.show")["preferences"]["locale"] == "en-US"
            assert remote.execute("preferences.update", {"timezone": "Asia/Shanghai"})["preferences"]["timezone"] == "Asia/Shanghai"
            assert remote.execute("import.manual", _manual_fill(trade_id="HTTP-1", symbol="TOY-HTTP"))["inserted_count"] == 1
            sessions = remote.execute("assistant.list")
            assert any(item["session_id"] == session_id for item in sessions["sessions"])
            assert any(item["account_id"] == "ACC-TOY" for item in remote.execute("accounts.list")["accounts"])
            updated = remote.execute("accounts.save", {"account_id": "ACC-TOY", "name": "Toy account HTTP"})
            assert updated["account"]["name"] == "Toy account HTTP"
        finally:
            remote.close()


def test_http_auth_denial_does_not_fall_back_to_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "toy-state"
    root.mkdir()
    local = _runtime(root)
    try:
        local.execute("preferences.update", {"locale": "en-US"})
    finally:
        local.close()
    with _server(root) as base:
        monkeypatch.setenv("SMCUB_ACCESS_TOKEN", "wrong-token")
        denied = _runtime(root, server=base)
        try:
            with pytest.raises(ControlError, match="HTTP 401") as error:
                denied.execute("preferences.show")
            assert error.value.code == "http_error"
        finally:
            denied.close()


def test_browser_operations_are_registered_or_explicitly_reported() -> None:
    browser_operations = {
        "GET /api/preferences": "preferences.show", "POST /api/preferences": "preferences.update",
        "POST /api/import/manual": "import.manual", "GET /api/assistant/sessions": "assistant.list",
        "POST /api/assistant/sessions": "assistant.create", "GET /api/trader/accounts": "accounts.list",
        "POST /api/trader/accounts": "accounts.save",
    }
    for route, name in browser_operations.items():
        assert name in OPERATIONS, route
        assert OPERATIONS[name].path
    browser_only = {
        "POST /api/assistant/sessions/{id}/messages": "streaming turn transport",
        "POST /api/assistant/sessions/{id}/resume": "streaming resume transport",
        "POST /api/settings/open-file": "local file opener",
        "GET /api/benchmark/images/{run_id}/{filename}": "binary image asset",
    }
    assert browser_only
    assert all(isinstance(reason, str) and reason for reason in browser_only.values())
