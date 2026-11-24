import json
import pytest
from smartmoney_cub_harness.cli import main
from smartmoney_cub_harness.control_runtime import ControlRuntime


def test_capabilities_are_discoverable_without_state(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(['capabilities', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['protocol_version'] == 1
    assert 'market.bars' in {row['name'] for row in result['operations']}
    assert not list(tmp_path.iterdir())


def test_local_market_catalog_and_preferences_share_workbench(tmp_path, capsys):
    root = str(tmp_path / 'state')
    assert main(['market', 'providers', '--state-dir', root, '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert 'eastmoney' in {row['provider_id'] for row in result['providers']}
    assert main(['preferences', 'update', '--state-dir', root, '--set', 'theme=light', '--json']) == 0
    capsys.readouterr()
    assert main(['preferences', 'show', '--state-dir', root, '--json']) == 0
    assert json.loads(capsys.readouterr().out)['preferences']['theme'] == 'light'


def test_hermes_cannot_implicitly_authorize_network(tmp_path, capsys):
    run = tmp_path / 'runs'; run.mkdir()
    assert main(['operation', 'market.bars', '--principal', 'hermes', '--run-root', str(run),
                 '--state-dir', str(tmp_path / 'state'), '--provider', 'eastmoney', '--symbol', '600000',
                 '--interval', '1d', '--json']) == 3
    assert json.loads(capsys.readouterr().out)['status'] == 'error'


def test_real_grant_revocation_and_exact_human_approval(tmp_path):
    run = tmp_path / 'run'; run.mkdir()
    runtime = ControlRuntime(state_dir=tmp_path/'state', principal='hermes', run_root=run)
    try:
        grant = runtime.permissions.grant('hermes', 'preferences.*', {'root': str(run)})
        runtime.execute('preferences.update', {'theme': 'light'})
        assert runtime.execute('preferences.show')['preferences']['theme'] == 'light'
        runtime.permissions.revoke(grant['grant_id'])
        with pytest.raises(PermissionError):
            runtime.execute('preferences.update', {'theme': 'dark'})
        # Even a grant must not expose human credential administration.
        runtime.permissions.grant('hermes', 'providers.update', {'root': str(run)})
        with pytest.raises(PermissionError):
            runtime.execute('providers.update', {'provider_id': 'toy'})
    finally:
        runtime.close()


def test_replay_persisted_pause_resume_and_isolated_training(tmp_path):
    runtime = ControlRuntime(state_dir=tmp_path/'state', allow_network=True)
    bars = [{'symbol':'TOY','interval':'1d','open_time':f'2026-08-0{i+1}',
             'open':10+i,'high':12+i,'low':9+i,'close':11+i,'volume':100} for i in range(4)]
    try:
        created = runtime.execute('replay.create', {'symbol':'TOY','interval':'1d','bars':bars,'mode':'training'})
        payload = {'session_id':created['session']['session_id']}
        runtime.execute('replay.play', payload)
        runtime.execute('replay.action', {**payload,'action':'tick'})
        runtime.execute('replay.pause', payload)
        runtime.close()
        runtime = ControlRuntime(state_dir=tmp_path/'state')
        paused = runtime.execute('replay.action', {**payload,'action':'tick'})
        assert paused['session']['cursor'] == 1
        assert not paused['session']['playing']
        runtime.execute('replay.play', payload)
        resumed = runtime.execute('replay.action', {**payload,'action':'tick'})
        assert resumed['session']['cursor'] == 2
        journal = runtime.execute('journal.list')
        assert not journal.get('fills') and not journal.get('trades')
    finally:
        runtime.close()


def test_secret_in_argv_and_unprotected_file_is_rejected(tmp_path,capsys):
    assert main(['providers','update','--set','values={"password":"toy-only"}','--json']) == 3
    assert 'toy-only' not in capsys.readouterr().out
    p=tmp_path/'config.json';p.write_text('{"api_key":"toy-only"}');p.chmod(0o644)
    assert main(['providers','update','--input',str(p),'--json']) == 3
    assert 'toy-only' not in capsys.readouterr().out
