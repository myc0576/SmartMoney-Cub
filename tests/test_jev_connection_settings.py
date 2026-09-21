"""JEV settings must configure a usable backend without exposing credentials."""
import json
import os
import stat
import urllib.error
from io import BytesIO

import pytest

from smartmoney_cub_harness.jev import connection
from smartmoney_cub_harness.workbench.server import WorkbenchService, ApiError


@pytest.fixture(autouse=True)
def no_ambient_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


def test_save_preserve_clear_and_state_root_isolation(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    assert not connection.connection_settings(a)["has_key"]
    saved = connection.save_connection(a, {"api_key": "fixture-key-not-a-real-secret"})
    assert saved["has_key"] and saved["key_source"] == "local"
    assert "fixture-key" not in json.dumps(saved)
    assert not connection.connection_settings(b)["has_key"]
    assert connection.configured_backend(a).api_key == "fixture-key-not-a-real-secret"
    assert connection.save_connection(a, {"api_key": ""})["has_key"]
    if os.name != "nt":
        assert stat.S_IMODE((a / connection.CREDENTIALS_NAME).stat().st_mode) == 0o600
    assert not connection.save_connection(a, {"clear_key": True})["has_key"]


def test_environment_fallback_without_modifying_process_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "fixture-env-key")
    assert connection.connection_settings(tmp_path)["key_source"] == "environment"
    connection.save_connection(tmp_path, {"api_key": "fixture-local-key"})
    assert connection.configured_backend(tmp_path).api_key == "fixture-local-key"
    assert os.environ["TYPESAFE_API_KEY"] == "fixture-env-key"
    assert connection.save_connection(tmp_path, {"clear_key": True})["key_source"] == "environment"


@pytest.mark.parametrize("payload", [
    {"api_key": "   "}, {"api_key": "bad key"}, {"api_key": "bad\r\nHeader"},
    {"api_key": "密钥"}, {"api_key": 42}, {"clear_key": "false"},
    {"api_key": "fixture", "clear_key": True}, {"api_key": "KEY=value"},
])
def test_reject_invalid_keys_without_echo_or_write(tmp_path, payload):
    with pytest.raises(ValueError):
        connection.save_connection(tmp_path, payload)
    assert not (tmp_path / connection.CREDENTIALS_NAME).exists()


def test_loading_or_saving_never_calls_network(tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("settings must not make network requests")
    monkeypatch.setattr(connection, "_probe_request", forbidden)
    connection.save_connection(tmp_path, {"api_key": "fixture-key"})
    connection.connection_settings(tmp_path)
    assert not connection.probe_connection(tmp_path / "missing")["connected"]


def test_explicit_probe_uses_saved_key_and_synthetic_state(tmp_path, monkeypatch):
    connection.save_connection(tmp_path, {"api_key": "fixture-key"})
    def respond(req):
        assert req.full_url == "https://api.typesafe.ai/v1/systemone"
        assert req.get_header("Authorization") == "Bearer fixture-key"
        payload = json.loads(req.data)
        assert payload["state"] == {"connection_test": True}
        assert list(payload["questions"]) == ["connection_test"]
        return {"model": "jev-test", "answers": {"connection_test": {"type": "noul", "noul": 0.9}}}
    monkeypatch.setattr(connection, "_probe_request", respond)
    result = connection.probe_connection(tmp_path)
    assert result["connected"] and result["model_resolved"] == "jev-test"
    assert "fixture-key" not in json.dumps(result)
    assert "connected" not in connection.connection_settings(tmp_path)  # no stale green badge


def test_upstream_error_is_sanitized(tmp_path, monkeypatch):
    connection.save_connection(tmp_path, {"api_key": "fixture-secret"})
    def fail(req):
        raise urllib.error.HTTPError(req.full_url, 401, "fixture-secret", {}, BytesIO(b"fixture-secret"))
    monkeypatch.setattr(connection, "_probe_request", fail)
    result = connection.probe_connection(tmp_path)
    assert not result["connected"]
    assert "fixture-secret" not in json.dumps(result)


def test_workbench_key_is_not_added_to_chat_providers(tmp_path):
    svc = WorkbenchService(tmp_path)
    try:
        before = svc.settings()["defaults"]
        result = svc.update_jev_connection({"api_key": "fixture-key"})
        assert result["has_key"]
        assert svc.jev_status()["backends"]["typesafe-direct"]["available"]
        assert "fixture-key" not in json.dumps(svc.settings())
        assert before == svc.settings()["defaults"]
        with pytest.raises(ApiError):
            svc.update_jev_connection({"api_key": "bad key"})
    finally:
        svc.close()


def test_probe_refuses_redirect_instead_of_forwarding_key():
    req = connection.urllib.request.Request("https://api.typesafe.ai/v1/systemone")
    with pytest.raises(urllib.error.HTTPError):
        connection._NoRedirect().redirect_request(req, None, 302, "move", {}, "https://untrusted.invalid")


@pytest.mark.parametrize("answer", [{}, {"type": "noul", "noul": float("nan")},
    {"type": "noul", "noul": 1.5}, {"type": "noul", "noul": True}, {"type": "choice", "noul": 0.8}])
def test_probe_rejects_invalid_typed_answers(monkeypatch, answer):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return json.dumps({"model": "jev-test", "answers": {"connection_test": answer}}).encode()
    class Opener:
        def open(self, request, timeout):
            assert timeout == 12
            return Response()
    monkeypatch.setattr(connection.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(connection.JevProtocolError):
        connection._probe_request(connection.urllib.request.Request("https://api.typesafe.ai/v1/systemone"))
