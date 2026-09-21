from pathlib import Path

ROOT = Path(__file__).resolve().parent

def replace(path, old, new, count=1):
    file = ROOT / path
    source = file.read_text(encoding='utf-8')
    assert source.count(old) == count, (path, old[:90], source.count(old))
    file.write_text(source.replace(old, new), encoding='utf-8')

def drop_line(path, needle):
    file = ROOT / path
    lines = file.read_text(encoding='utf-8').splitlines(keepends=True)
    assert sum(needle in line for line in lines) == 1, (path, needle)
    file.write_text(''.join(line for line in lines if needle not in line), encoding='utf-8')

def block(path, start, end, new):
    file = ROOT / path
    source = file.read_text(encoding='utf-8')
    assert source.count(start) == source.count(end) == 1, (path, start, end)
    left, right = source.index(start), source.index(end)
    assert left < right
    file.write_text(source[:left] + new + source[right:], encoding='utf-8')

app = 'gui/src/App.tsx'
replace(app, "import { SettingsView } from './views/SettingsView';", "import { ConnectionSettings as SettingsView } from './views/ConnectionSettings';")
drop_line(app, "import { JevView }")
replace(app, " | 'jev'", '')
drop_line(app, "key: 'jev',")
replace(app, "hint: '模型、隐私与诊断'", "hint: '模型、连接与 Agent 集成'")
drop_line(app, "{tab === 'jev' ? <JevView /> : null}")
(ROOT / 'gui/src/views/JevView.tsx').unlink()
replace('gui/package.json', '"typecheck": "tsc --noEmit"', '"typecheck": "tsc --noEmit",\n    "test": "node --experimental-strip-types --test tests/*.test.mjs"')

server = 'src/smartmoney_cub_harness/workbench/server.py'
replace(server, 'from smartmoney_cub_harness.local_state import LOCAL_STATE_DIR', 'from smartmoney_cub_harness.jev.configuration import JevConnectionSettings\nfrom smartmoney_cub_harness.local_state import LOCAL_STATE_DIR')
replace(server, '        self._lock = threading.Lock()\n', '        self._lock = threading.Lock()\n        self.jev_connection = JevConnectionSettings(self.root)\n')
replace(server, '    def jev_status(self) -> dict[str, Any]:', '''    def jev_settings(self) -> dict[str, Any]:
        try:
            return self.jev_connection.view()
        except (ValueError, OSError) as error:
            raise ApiError("无法读取 JEV 凭据文件，请重新保存密钥。") from error

    def update_jev_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.jev_connection.save(payload)
        except ValueError as error:
            raise ApiError(str(error)) from error
        except OSError as error:
            raise ApiError("无法保存 JEV 密钥，请检查本机文件权限。") from error

    def test_jev_connection(self) -> dict[str, Any]:
        return self.jev_connection.test_connection()

    def jev_status(self) -> dict[str, Any]:''')
replace(server, 'run_jev_doctor()', 'run_jev_doctor(credentials_root=self.root)')
replace(server, '''            if path == "/api/settings":
                self._json(self.service.settings())''', '''            if path == "/api/settings/jev":
                if not is_loopback(self.client_address[0]):
                    raise ApiError("JEV settings are local-only", status=403, code="forbidden")
                self._json(self.service.jev_settings())
                return
            if path == "/api/settings":
                self._json(self.service.settings())''')
replace(server, '''            if path == "/api/settings":
                self._json(self.service.update_settings(self._read_json()))''', '''            if path in {"/api/settings/jev", "/api/settings/jev/test"}:
                if not is_loopback(self.client_address[0]):
                    raise ApiError("JEV settings are local-only", status=403, code="forbidden")
                payload = self._read_json()
                if path.endswith("/test"):
                    if payload:
                        raise ApiError("connection tests accept no journal data")
                    self._json(self.service.test_jev_connection())
                else:
                    self._json(self.service.update_jev_settings(payload))
                return
            if path == "/api/settings":
                self._json(self.service.update_settings(self._read_json()))''')
cli = 'src/smartmoney_cub_harness/jev/cli.py'
replace(cli, 'def run_jev_doctor() -> dict[str, Any]:', 'def run_jev_doctor(*, credentials_root: Any = None) -> dict[str, Any]:')
replace(cli, '    direct_backend = TypeSafeDirectJevBackend()', '''    if credentials_root is None:
        direct_backend = TypeSafeDirectJevBackend()
    else:
        from smartmoney_cub_harness.jev.configuration import JevConnectionSettings

        direct_backend = JevConnectionSettings(credentials_root).backend()''')

assistant = 'gui/src/components/AssistantPanel.tsx'
replace(assistant, "import { api, streamTurn } from '../api';", "import { api, streamTurn } from '../api';\nimport { AssistantRunStatus } from './AssistantRunStatus';\nimport { shouldSendOnEnter, shouldFollowOutput, type RunPhase } from './assistantRun';")
replace(assistant, "  const [currentAction, setCurrentAction] = useState('');", "  const [phase, setPhase] = useState<RunPhase>('connecting');\n  const [startedAt, setStartedAt] = useState(0);\n  const [endedAt, setEndedAt] = useState<number | null>(null);\n  const [showJump, setShowJump] = useState(false);")
replace(assistant, '  const abortRef = useRef<AbortController | null>(null);', '''  const abortRef = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);
  const followRef = useRef(true);
  const turnSessionRef = useRef<string | null>(null);
  const cancelRef = useRef<Promise<unknown> | null>(null);
  const aliveRef = useRef(true);
  useEffect(() => {
    aliveRef.current = true;
    return () => { aliveRef.current = false; abortRef.current?.abort(); };
  }, []);''')
replace(assistant, '    setSelection(next);\n', '    if (sendingRef.current) return;\n    setSelection(next);\n')
block(assistant, '  useEffect(() => {\n    if (!activeId)', '  const startSession = async () => {', '''  useEffect(() => {
    if (sendingRef.current) return;
    if (!activeId) { setEvents([]); return; }
    let cancelled = false;
    void api.sessionDetail(activeId).then((detail) => {
      if (cancelled || sendingRef.current) return;
      setEvents(detail.events);
      setTurn(null);
      const session = detail.session;
      if (session) setSelection({
        provider_id: session.provider_id || meta?.default_provider || 'alphatech',
        model: session.model || meta?.default_model || '',
        reasoning: session.reasoning || meta?.default_reasoning || 'off',
      });
    }).catch(() => { if (!cancelled) setUnavailable('无法读取会话，请重新打开助手重试。'); });
    return () => { cancelled = true; };
  }, [activeId, meta]);

  useEffect(() => {
    const node = bodyRef.current;
    if (node && followRef.current) node.scrollTop = node.scrollHeight;
    else if (node) setShowJump(true);
  }, [events, turn, busy]);

''')
replace(assistant, '  const startSession = async () => {\n', '  const startSession = async () => {\n    if (sendingRef.current) return;\n')
replace(assistant, "      provider_id: meta?.default_provider || 'alphatech',\n    });", "      provider_id: selection.provider_id,\n      model: selection.model,\n      reasoning: selection.reasoning,\n    });")
block(assistant, '  const send = async () => {', '  const fork = async () => {', '''  const send = async () => {
    const text = input.trim();
    if (!text || sendingRef.current || unavailable || !hasRoutableModel) return;
    sendingRef.current = true; // Lock before the first await, including session creation.
    const controller = new AbortController();
    abortRef.current = controller;
    cancelRef.current = null;
    turnSessionRef.current = null;
    followRef.current = true;
    setShowJump(false);
    setBusy(true);
    setStartedAt(Date.now());
    setEndedAt(null);
    setPhase('connecting');
    setTurn({ text: '', toolCalls: [] });
    setLiveArtifacts([]);
    let sessionId = activeId;
    let failed = false;
    const initialSeq = events.reduce((seq, event) => Math.max(seq, event.seq), 0);
    const fail = (message: string) => {
      failed = true;
      if (!aliveRef.current || controller.signal.aborted) return;
      setPhase('error');
      setTurn(prev => ({ text: prev?.text || '', toolCalls: prev?.toolCalls || [], error: message }));
    };
    try {
      if (!sessionId) {
        const created = await api.createSession({ title: text.slice(0, 18), context, ...selection });
        sessionId = created.session.session_id;
        if (controller.signal.aborted || !aliveRef.current) return;
        setActiveId(sessionId);
      }
      if (controller.signal.aborted || !aliveRef.current) return;
      turnSessionRef.current = sessionId;
      setInput('');
      setEvents(prev => [...prev, {
        event_id: -Date.now(), seq: -1, kind: 'user_message', role: 'user',
        payload: { text }, created_at: new Date().toISOString(),
      }]);
      await streamTurn(sessionId, text, {
        signal: controller.signal,
        onEvent: event => {
          if (!aliveRef.current || controller.signal.aborted) return;
          if (event.kind === 'delta') {
            setPhase('writing');
            setTurn(prev => ({ ...prev, text: (prev?.text || '') + String(event.text || ''), toolCalls: prev?.toolCalls || [] }));
          } else if (event.kind === 'tool_call') {
            setPhase('tools');
            setTurn(prev => ({ ...prev, text: prev?.text || '', toolCalls: [...(prev?.toolCalls || []), {
              callId: String(event.call_id), name: String(event.name || '工具'), arguments: event.arguments,
            }] }));
          } else if (event.kind === 'tool_result') {
            setTurn(prev => ({ ...prev, text: prev?.text || '', toolCalls: (prev?.toolCalls || []).map(call =>
              call.callId === String(event.call_id) ? { ...call, result: event.result } : call) }));
          } else if (event.kind === 'error') {
            fail(String(event.error || event.text || '本轮未完成'));
          } else if (event.kind === 'artifact') {
            const artifact = event.artifact || event.payload?.artifact;
            if (artifact) setLiveArtifacts(prev => [...prev, artifact]);
            window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
          }
        },
        onError: fail,
        onDone: () => {}, // EOF alone is not proof the answer was persisted.
      });
      if (!controller.signal.aborted && aliveRef.current && !failed) {
        try {
          const detail = await api.sessionDetail(sessionId);
          if (controller.signal.aborted || !aliveRef.current) return;
          const persisted = detail.events.some(event => event.seq > initialSeq && event.kind === 'assistant_message');
          if (persisted) {
            setEvents(detail.events); setTurn(null); setLiveArtifacts([]); setPhase('finished');
          } else fail('连接已结束，但回复尚未确认保存。请重新读取会话检查结果。');
        } catch { fail('回复已接收，但会话记录刷新失败；已保留本轮内容。'); }
      }
    } catch (failure) {
      if (!controller.signal.aborted) fail(failure instanceof Error ? failure.message : '连接失败，请重试。');
    } finally {
      if (cancelRef.current) await cancelRef.current;
      sendingRef.current = false;
      abortRef.current = null;
      turnSessionRef.current = null;
      if (aliveRef.current) {
        setBusy(false); setEndedAt(Date.now());
        if (controller.signal.aborted) setPhase('stopped');
        void loadSessions();
        window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
      }
    }
  };

  const stop = () => {
    const sessionId = turnSessionRef.current;
    abortRef.current?.abort();
    setPhase('stopped');
    setEndedAt(Date.now());
    if (sessionId && !cancelRef.current) {
      cancelRef.current = api.cancelTurn(sessionId).catch(() => {
        if (aliveRef.current) setTurn(prev => ({ text: prev?.text || '', toolCalls: prev?.toolCalls || [],
          error: '已停止接收；服务端停止未确认，请稍后重新读取会话。' }));
      });
    }
  };

''')
replace(assistant, '  const fork = async () => {\n    if (!activeId) return;', '  const fork = async () => {\n    if (!activeId || sendingRef.current) return;')
replace(assistant, 'onClick={startSession} title="新建会话"', 'onClick={startSession} disabled={busy} title="新建会话"')
replace(assistant, 'onClick={fork} title="分叉会话"', 'onClick={fork} disabled={busy} title="分叉会话"')
replace(assistant, 'onClick={() => { setActiveId(session.session_id); setShowSessions(false); }}', 'disabled={busy} onClick={() => { setActiveId(session.session_id); setShowSessions(false); }}')
replace(assistant, '<div className="assistant-body" ref={bodyRef}>', '''<div className="assistant-body" ref={bodyRef} onScroll={() => {
        const node = bodyRef.current;
        if (!node) return;
        followRef.current = shouldFollowOutput(node.scrollHeight, node.clientHeight, node.scrollTop);
        setShowJump(!followRef.current);
      }}>''')
replace(assistant, '<details key={call.callId} className="tool-card" open>', '<details key={call.callId} className="tool-card">')
replace(assistant, '''{busy ? <div className="assistant-progress"><span className="breathing-dot" /><span>{currentAction || '正在分析本地证据'}</span><span className="muted">可随时停止</span></div> : null}''', '''<AssistantRunStatus phase={turn.error && phase !== 'stopped' ? 'error' : phase}
              startedAt={startedAt} endedAt={endedAt} calls={turn.toolCalls.length}
              returned={turn.toolCalls.filter(call => call.result !== undefined).length} />''')
replace(assistant, "        {liveArtifacts.map((artifact, index) => renderArtifact(artifact, 'live-' + index))}", """        {liveArtifacts.map((artifact, index) => renderArtifact(artifact, 'live-' + index))}
        {showJump ? <button className="ghost assistant-jump" onClick={() => {
          followRef.current = true; setShowJump(false);
          const node = bodyRef.current; if (node) node.scrollTop = node.scrollHeight;
        }}>回到最新 ↓</button> : null}""")
replace(assistant, "            if (event.key === 'Enter' && !event.shiftKey) {", "            if (shouldSendOnEnter(event.key, event.shiftKey, event.nativeEvent.isComposing, event.keyCode)) {")
replace(assistant, '          <ModelPicker\n', '          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>\n          <ModelPicker\n')
replace(assistant, '            onSelect={(next) => void applySelection(next)}\n          />', '            onSelect={(next) => void applySelection(next)}\n          />\n          </fieldset>')
ignore = ROOT / '.gitignore'
ignore.write_text(ignore.read_text(encoding='utf-8') + '\n# Optional local JEV credentials, including atomic-write temporary files.\njev-credentials.json\n.jev-*\n', encoding='utf-8')
print('Applied exact-context changes for Issue 27.')
