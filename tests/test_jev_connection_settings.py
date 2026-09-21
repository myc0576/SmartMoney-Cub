"""Toy-only coverage for settings: credentials are never returned to the UI."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from smartmoney_cub_harness.jev.configuration import JevConnectionSettings
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY', raising=False)


def test_saved_key_is_private_and_does_not_probe(tmp_path):
    def forbidden(**kwargs):
        raise AssertionError('saving must not create a network client')
    config = JevConnectionSettings(tmp_path, backend_factory=forbidden)
    assert not config.view()['configured']
    result = config.save({'api_key': ' toy-credential '})
    assert result['configured'] and result['key_source'] == 'local'
    assert result['connection'] == 'untested'
    assert 'toy-credential' not in json.dumps(result)
    assert result['safety'] == SAFETY_DECLARATION
    assert JevConnectionSettings(tmp_path).view()['configured']
    if os.name != 'nt':
        assert config.path.stat().st_mode & 0o777 == 0o600
    assert config.save({'api_key': ''})['configured']
    assert not config.save({'clear_key': True})['configured']


@pytest.mark.parametrize('value', [' ', 'x\ny', '含中文', 'TYPESAFE_API_KEY=toy', ['bad'], 'x' * 4097])
def test_invalid_input_is_rejected_without_echoing_it(tmp_path, value):
    with pytest.raises(ValueError) as exc:
        JevConnectionSettings(tmp_path).save({'api_key': value})
    assert 'toy' not in str(exc.value)
    assert not (tmp_path / 'jev-credentials.json').exists()


def test_environment_fallback_and_local_override(tmp_path, monkeypatch):
    monkeypatch.setenv('TYPESAFE_API_KEY', 'environment-toy')
    seen = []
    config = JevConnectionSettings(tmp_path, backend_factory=lambda **kw: seen.append(kw))
    assert config.view()['key_source'] == 'environment'
    config.save({'api_key': 'local-toy'})
    config.backend()
    assert seen[-1]['api_key'] == 'local-toy'
    assert config.save({'clear_key': True})['key_source'] == 'environment'
    config.backend()
    assert seen[-1]['api_key'] == 'environment-toy'


def test_explicit_probe_uses_only_synthetic_state(tmp_path):
    calls = []
    class Backend:
        def __init__(self, **kwargs):
            assert kwargs['api_key'] == 'toy-credential'
        def evaluate(self, state, questions, *, decision_time):
            calls.append((state, questions, decision_time))
            return SimpleNamespace(model_resolved='toy-model')
    config = JevConnectionSettings(tmp_path, backend_factory=Backend)
    config.save({'api_key': 'toy-credential'})
    assert calls == []
    result = config.test_connection()
    assert result['connection'] == 'connected'
    assert calls[0][0] == {'connection_test': True}
    assert len(calls[0][1]) == 1
    assert 'toy-credential' not in json.dumps(result)
    assert config.view()['connection'] == 'untested'


def test_probe_failures_never_echo_upstream_credentials(tmp_path):
    class Backend:
        def __init__(self, **kwargs):
            pass
        def evaluate(self, *args, **kwargs):
            raise RuntimeError('upstream leaked toy-credential')
    config = JevConnectionSettings(tmp_path, backend_factory=Backend)
    config.save({'api_key': 'toy-credential'})
    result = config.test_connection()
    assert result['status'] == 'error'
    assert result['connection'] == 'failed'
    assert 'toy-credential' not in json.dumps(result)


def test_missing_key_does_not_contact_provider(tmp_path):
    config = JevConnectionSettings(tmp_path, backend_factory=lambda **kw: pytest.fail('no request'))
    assert config.test_connection()['connection'] == 'unconfigured'


def test_malformed_file_fails_closed(tmp_path):
    config = JevConnectionSettings(tmp_path)
    config.path.write_text('{broken private contents', encoding='utf-8')
    with pytest.raises(ValueError, match='凭据文件'):
        config.view()


def test_conflicting_or_unknown_updates_are_rejected(tmp_path):
    config = JevConnectionSettings(tmp_path)
    for payload in ({'clear_key': 'true'}, {'api_key': 'toy', 'clear_key': True}, {'base_url': 'http://example.test'}):
        with pytest.raises(ValueError):
            config.save(payload)
