from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from smartmoney_cub_harness.preferences import PreferencesError, PreferencesStore
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.store import Store
from smartmoney_cub_harness.workbench.server import WorkbenchHandler, WorkbenchService, _SessionOwnerLock


def test_preferences_are_root_bound_atomic_and_report_missing_fields(tmp_path: Path) -> None:
    root = tmp_path / "workbench"
    store = PreferencesStore(root)

    initial = store.read()
    assert initial["preferences"]["theme"] == "dark"
    assert set(initial["missing_fields"]) == {
        "locale", "timezone", "currency", "number_format", "color_scheme", "theme"
    }

    updated = store.update({"theme": "light", "timezone": "Asia/Shanghai", "color_scheme": "intl"})
    assert updated["preferences"]["theme"] == "light"
    assert updated["preferences"]["timezone"] == "Asia/Shanghai"
    assert "theme" not in updated["missing_fields"]
    assert "locale" in updated["missing_fields"]
    assert json.loads((root / "preferences.json").read_text(encoding="utf-8"))["color_scheme"] == "intl"
    assert (root / "preferences.json").stat().st_mode & 0o077 == 0

    with pytest.raises(PreferencesError):
        store.update({"theme": "solarized"})
    with pytest.raises(PreferencesError):
        store.update({"timezone": "../../outside"})


def test_preferences_reject_a_symlinked_file(tmp_path: Path) -> None:
    root = tmp_path / "workbench"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (root / "preferences.json").symlink_to(outside)
    with pytest.raises(PreferencesError, match="symlink"):
        PreferencesStore(root).read()


def test_session_owner_lock_rejects_a_symlinked_lock_file(tmp_path: Path) -> None:
    root = tmp_path / "workbench"
    root.mkdir()
    outside = tmp_path / "outside.lock"
    outside.write_text("keep", encoding="utf-8")
    (root / ".workbench-session.lock").symlink_to(outside)
    lock = _SessionOwnerLock(root)
    assert lock.acquire() is False
    assert outside.read_text(encoding="utf-8") == "keep"


def _http_server(service: WorkbenchService) -> tuple[ThreadingHTTPServer, str]:
    handler = type(
        "PreferencesHandler",
        (WorkbenchHandler,),
        {"service": service, "asset_dir": None, "access_token": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _json_request(url: str, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def test_preferences_service_and_http_contract(tmp_path: Path) -> None:
    service = WorkbenchService(tmp_path)
    server, base = _http_server(service)
    try:
        status, body = _json_request(base + "/api/preferences")
        assert status == 200
        assert body["preferences"]["locale"] == "zh-CN"
        assert body["safety"] == SAFETY_DECLARATION

        status, body = _json_request(
            base + "/api/preferences", "POST", {"locale": "en-US", "theme": "light"}
        )
        assert status == 200
        assert body["preferences"]["locale"] == "en-US"
        assert body["preferences"]["theme"] == "light"
        assert body["safety"] == SAFETY_DECLARATION

        status, body = _json_request(base + "/api/preferences", "POST", {"theme": "invalid"})
        assert status == 400
        assert body["code"] == "invalid_preferences"
        assert body["safety"] == SAFETY_DECLARATION
    finally:
        server.shutdown()
        server.server_close()
        service.close()


def test_direct_services_do_not_recover_and_server_recovery_is_owner_locked(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    raw = Store(root)
    orphan = raw.create_session(title="live toy session")
    raw.update_session(orphan["session_id"], status="running")
    raw.close()

    direct = WorkbenchService(root)
    assert direct.recovered_sessions == []
    assert direct.store.get_session(orphan["session_id"])["status"] == "running"

    contender = WorkbenchService(root, recover_interrupted_sessions=True)
    try:
        assert contender.recovery_lock_acquired is False
        assert contender.recovered_sessions == []
        assert contender.store.get_session(orphan["session_id"])["status"] == "running"
    finally:
        contender.close()
        direct.close()

    owner = WorkbenchService(root, recover_interrupted_sessions=True)
    try:
        assert owner.recovery_lock_acquired is True
        assert owner.recovered_sessions[0]["status"] == "interrupted"
    finally:
        owner.close()
