from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_connections_live_in_settings_not_a_standalone_engine():
    app = (ROOT / 'gui/src/App.tsx').read_text(encoding='utf-8')
    assert "key: 'jev'" not in app
    assert 'JevView' not in app
    assert not (ROOT / 'gui/src/views/JevView.tsx').exists()
    assert 'ConnectionSettings as SettingsView' in app
    connections = (ROOT / 'gui/src/views/ConnectionSettings.tsx').read_text(encoding='utf-8')
    assert 'Agent 集成中心' in connections
    assert 'JEV 连接' in connections
    assert 'api/settings/jev' in connections
    assert 'localStorage' not in connections


def test_assistant_keeps_control_and_partial_output():
    source = (ROOT / 'gui/src/components/AssistantPanel.tsx').read_text(encoding='utf-8')
    send = source.split('  const send = async () => {')[1].split('  const stop =')[0]
    assert send.index('sendingRef.current = true') < send.index('await api.createSession')
    stop = source.split('  const stop =')[1].split('  const fork =')[0]
    assert 'setTurn(null)' not in stop
    assert 'api.cancelTurn' in stop
    assert 'shouldSendOnEnter' in source
    assert 'shouldFollowOutput' in source
    assert '<AssistantRunStatus' in source
    assert 'className="tool-card" open' not in source


def test_local_jev_secret_file_is_ignored():
    ignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    assert 'jev-credentials.json' in ignore
