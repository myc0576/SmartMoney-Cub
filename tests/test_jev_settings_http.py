from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workbench.server import WorkbenchHandler, WorkbenchService


@pytest.fixture
def connection_server(tmp_path, monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    service = WorkbenchService(tmp_path)
    handler = type('ConnectionHandler', (WorkbenchHandler,), {
        'service': service, 'asset_dir': None, 'access_token': None,
    })
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', service
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        service.close()


def call(base, path='/api/settings/jev', payload=None):
    request = urllib.request.Request(base + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_jev_settings_http_routes(connection_server):
    base, service = connection_server
    code, before = call(base)
    assert code == 200 and not before['configured']
    code, saved = call(base, payload={'api_key': 'toy-http-credential'})
    assert code == 200 and saved['configured']
    code, after = call(base)
    assert code == 200 and after['key_source'] == 'local'
    assert 'toy-http-credential' not in json.dumps(after)
    assert after['connection'] == 'untested'
    assert after['safety'] == SAFETY_DECLARATION
    _, doctor = call(base, '/api/jev/status')
    assert doctor['backends']['typesafe-direct']['available']
    code, cleared = call(base, payload={'clear_key': True})
    assert code == 200 and not cleared['configured']


def test_invalid_key_and_journal_data_are_refused(connection_server):
    base, _ = connection_server
    code, error = call(base, payload={'api_key': 'bad\nheader'})
    assert code == 400 and error['safety'] == SAFETY_DECLARATION
    code, _ = call(base, '/api/settings/jev/test', {'trades': ['not allowed']})
    assert code == 400
    code, result = call(base, '/api/settings/jev/test', {})
    assert code == 200 and result['status'] == 'error'
    assert result['connection'] == 'unconfigured'


def test_probe_route_uses_settings_connection(connection_server):
    base, service = connection_server
    call(base, payload={'api_key': 'toy-http-credential'})
    class ToyBackend:
        def evaluate(self, state, questions, *, decision_time):
            assert state == {'connection_test': True}
            assert len(questions) == 1
    service.jev_connection._backend_factory = lambda **kwargs: ToyBackend()
    code, result = call(base, '/api/settings/jev/test', {})
    assert code == 200 and result['connection'] == 'connected'
    assert result['safety'] == SAFETY_DECLARATION
