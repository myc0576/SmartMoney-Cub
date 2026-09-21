"""Local JEV settings never return credentials or turn storage into connectivity."""
import json
from pathlib import Path

import pytest

from smartmoney_cub_harness.agent.providers import credentials_path, load_credentials, save_credentials
from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workbench.server import ApiError, WorkbenchService


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)
    svc = WorkbenchService(tmp_path)
    yield svc
    svc.close()


def test_save_clear_and_blank_key_preserve_other_credentials(service):
    save_credentials(service.root, {'providers': {'other': {'api_key': 'toy-other'}}})
    result = service.update_jev_connection({'api_key': 'toy-jev-key'})
    assert result['has_key'] and not result['connection_verified']
    assert 'toy-jev-key' not in json.dumps(result)
    assert result['safety'] == SAFETY_DECLARATION
    assert service.update_jev_connection({'api_key': ''})['has_key']
    backend = TypeSafeDirectJevBackend(credentials_root=service.root)
    assert backend.api_key == 'toy-jev-key'
    assert credentials_path(service.root).stat().st_mode & 0o777 == 0o600
    assert service.update_jev_connection({'clear_key': True})['has_key'] is False
    assert load_credentials(service.root)['providers']['other']['api_key'] == 'toy-other'
    assert not any(p['provider_id'] == 'typesafe-jev' for p in service.settings()['providers'])


@pytest.mark.parametrize('value', ['   ', 'TYPESAFE_API_KEY=toy-key', 'bad key', 'bad\nkey', '中文', 23])
def test_reject_invalid_key_without_echo_or_write(service, value):
    with pytest.raises(ApiError) as caught:
        service.update_jev_connection({'api_key': value})
    assert str(value) not in str(caught.value)
    assert not credentials_path(service.root).exists()


def test_read_and_save_do_not_probe_network(service, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Reading or saving settings must not contact a provider')
    monkeypatch.setattr(TypeSafeDirectJevBackend, 'evaluate', forbidden)
    assert not service.jev_connection()['has_key']
    assert service.update_jev_connection({'api_key': 'toy-jev-key'})['has_key']
    assert service.jev_status()['available']


def test_explicit_connection_probe_uses_saved_key_and_toy_state(service, monkeypatch):
    service.update_jev_connection({'api_key': 'toy-jev-key'})
    from types import SimpleNamespace
    def evaluate(backend, state, questions, *, decision_time):
        assert backend.api_key == 'toy-jev-key'
        assert state == {'connection_test': True}
        assert len(questions) == 1
        return SimpleNamespace(model_resolved='toy-jev-model')
    monkeypatch.setattr(TypeSafeDirectJevBackend, 'evaluate', evaluate)
    result = service.test_jev_connection()
    assert result['connection_verified'] is True
    assert result['model_resolved'] == 'toy-jev-model'
    assert 'toy-jev-key' not in json.dumps(result)


def test_missing_key_and_provider_error_fail_closed(service, monkeypatch):
    assert service.test_jev_connection()['connection_verified'] is False
    service.update_jev_connection({'api_key': 'toy-jev-key'})
    def fail(*args, **kwargs):
        raise RuntimeError('upstream echoed toy-jev-key')
    monkeypatch.setattr(TypeSafeDirectJevBackend, 'evaluate', fail)
    result = service.test_jev_connection()
    assert result['connection_verified'] is False
    assert 'toy-jev-key' not in json.dumps(result)


def test_explicit_key_and_isolated_state_root_take_precedence(service, tmp_path, monkeypatch):
    monkeypatch.setenv('TYPESAFE_API_KEY', 'toy-env-key')
    service.update_jev_connection({'api_key': 'toy-local-key'})
    assert TypeSafeDirectJevBackend(credentials_root=service.root).api_key == 'toy-local-key'
    assert TypeSafeDirectJevBackend(api_key='toy-explicit', credentials_root=service.root).api_key == 'toy-explicit'
    assert TypeSafeDirectJevBackend(credentials_root=tmp_path / 'other').api_key == 'toy-env-key'
    view = service.update_jev_connection({'clear_key': True})
    assert view['key_source'] == 'environment' and view['has_key']


def test_probe_is_one_bounded_request_and_uses_real_direct_serializer(service, monkeypatch):
    import urllib.error
    import urllib.request
    service.update_jev_connection({'api_key': 'toy-jev-key'})
    calls = []
    def reject(request, *, timeout):
        calls.append(request)
        assert request.full_url == 'https://api.typesafe.ai/v1/systemone'
        assert request.get_header('Authorization') == 'Bearer toy-jev-key'
        assert json.loads(request.data)['state'] == {'connection_test': True}
        assert timeout <= 10
        raise urllib.error.URLError('toy-key should never be echoed')
    monkeypatch.setattr(urllib.request, 'urlopen', reject)
    assert not service.test_jev_connection()['connection_verified']
    assert len(calls) == 1


def test_corrupt_credentials_are_not_overwritten(service):
    path = credentials_path(service.root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{broken', encoding='utf-8')
    with pytest.raises(ApiError):
        service.update_jev_connection({'api_key': 'toy-new-key'})
    assert path.read_text(encoding='utf-8') == '{broken'


def test_credential_replace_failure_leaves_old_file_intact(tmp_path, monkeypatch):
    import os
    save_credentials(tmp_path, {'providers': {'other': {'api_key': 'toy-original'}}})
    original = credentials_path(tmp_path).read_bytes()
    def fail(*args):
        raise OSError('toy filesystem failure')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError):
        save_credentials(tmp_path, {'providers': {'other': {'api_key': 'toy-replacement'}}})
    assert credentials_path(tmp_path).read_bytes() == original
    assert len(list(tmp_path.glob('*.tmp'))) == 0
