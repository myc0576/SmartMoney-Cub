import { useEffect, useRef, useState } from 'react';
import { api, streamTurn } from '../api';
import { Markdown } from './common';
import { AssistantProgress } from './AssistantProgress';
import type { RunPhase } from './AssistantProgress';
import { ModelPicker, effortLabel, findModel } from './ModelPicker';
import type { Meta, SessionEvent, SessionSummary } from '../types';

// The assistant panel mirrors the harness interaction model: a session list, a
// transcript with expandable tool cards, and a live connection indicator. Every
// event shown here is also stored locally, so a reload restores the transcript.

function toolFailed(result: unknown): boolean {
  return Boolean(result && typeof result === 'object' && 'status' in result && result.status === 'error');
}

interface TurnState {
  text: string;
  toolCalls: { callId: string; name: string; arguments: string; result?: unknown }[];
  error?: string;
}

export function AssistantPanel({ meta, context, onClose, onMetaReload }: {
  meta: Meta | null;
  context: Record<string, unknown>;
  onClose?: () => void;
  onMetaReload?: () => void;
}) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [turn, setTurn] = useState<TurnState | null>(null);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [showSessions, setShowSessions] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [currentAction, setCurrentAction] = useState('');
  const [liveArtifacts, setLiveArtifacts] = useState<Record<string, any>[]>([]);
  const [promotionDraft, setPromotionDraft] = useState<Record<string, { promotionId?: string; note: string; status: string }>>({});
  // Set when the assistant surface cannot be reached at all. On a shared host the
  // review workbench API is closed at the trust boundary, so every call here
  // 403s. Without this the panel looked entirely functional -- example prompts,
  // an input, a Send button -- and failed only after the user had typed a
  // question and pressed it, which is worse than saying so up front.
  const [unavailable, setUnavailable] = useState('');
  // The selection applies to the next request, and it is what a new session
  // starts from, so it lives here rather than inside the picker.
  const [selection, setSelection] = useState({
    provider_id: meta?.default_provider || 'alphatech',
    model: meta?.default_model || '',
    reasoning: meta?.default_reasoning || 'off',
  });
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const runRef = useRef<{ controller: AbortController; sessionId: string | null; stopped: boolean; cancellation?: Promise<void> } | null>(null);
  const mounted = useRef(true);
  const viewEpoch = useRef(0);
  const navigationPending = useRef(false);
  const followOutput = useRef(true);
  const [showLatest, setShowLatest] = useState(false);
  const [notice, setNotice] = useState('');
  const [progress, setProgress] = useState<{ phase: RunPhase; startedAt: number; finishedAt: number | null; toolCount: number } | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      const run = runRef.current;
      if (run) {
        run.stopped = true;
        run.controller.abort();
        if (run.sessionId && !run.cancellation) {
          void api.cancelTurn(run.sessionId, AbortSignal.timeout(5000)).catch(() => undefined);
        }
      }
    };
  }, []);

  const loadSessions = async (initial = false) => {
    try {
      const result = await api.sessions();
      if (!mounted.current) return [];
      setSessions(result.sessions);
      setUnavailable('');
      return result.sessions;
    } catch (failure) {
      if (!mounted.current) return [];
      if (initial) setUnavailable(failure instanceof Error ? failure.message : String(failure));
      else setNotice('会话列表刷新失败；当前回复仍然保留。');
      return [];
    }
  };

  useEffect(() => {
    let alive = true;
    const epoch = viewEpoch.current;
    void loadSessions(true).then((list) => {
      if (alive && viewEpoch.current === epoch && !runRef.current && list.length) setActiveId(list[0].session_id);
    });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!meta) return;
    setSelection((prev) =>
      prev.model
        ? prev
        : {
            provider_id: meta.default_provider || 'alphatech',
            model: meta.default_model || '',
            reasoning: meta.default_reasoning || 'off',
          },
    );
  }, [meta]);

  const applySelection = async (next: { provider_id: string; model: string; reasoning: string }) => {
    if (runRef.current || navigationPending.current) return;
    setSelection(next);
    if (activeId) {
      // An existing session keeps its own log, so the choice is recorded on it.
      await api.updateSession(activeId, {
        provider_id: next.provider_id,
        model: next.model,
        reasoning: next.reasoning,
      });
      await loadSessions();
    }
    await api.updateSettings({
      default_provider_id: next.provider_id,
      default_model: next.model,
      default_reasoning: next.reasoning,
    });
    onMetaReload?.();
  };

  useEffect(() => {
    if (runRef.current) return;
    if (!activeId) { setEvents([]); return; }
    let alive = true;
    const epoch = ++viewEpoch.current;
    void api.sessionDetail(activeId).then((detail) => {
      if (!alive || epoch !== viewEpoch.current || runRef.current) return;
      setEvents(detail.events);
      const session = detail.session;
      if (session) setSelection(previous => ({
        provider_id: session.provider_id || previous.provider_id,
        model: session.model || previous.model,
        reasoning: session.reasoning || previous.reasoning,
      }));
    }).catch(() => { if (alive && epoch === viewEpoch.current) setNotice('会话读取失败，请重新选择会话重试。'); });
    return () => { alive = false; };
  }, [activeId]);

  useEffect(() => {
    const node = bodyRef.current;
    if (node && followOutput.current) node.scrollTop = node.scrollHeight;
  }, [events, turn, liveArtifacts, currentAction]);

  const switchSession = (id: string | null) => {
    if (runRef.current || navigationPending.current) return;
    ++viewEpoch.current;
    setActiveId(id); setTurn(null); setProgress(null); setLiveArtifacts([]);
    setNotice(''); setShowSessions(false); followOutput.current = true; setShowLatest(false);
    if (!id) setEvents([]);
  };
  // Create the backend session only when the first message is sent. A new blank
  // conversation keeps the user's current model selection instead of stale meta.
  const startSession = () => switchSession(null);

  const send = async () => {
    const text = input.trim();
    if (!text || busy || runRef.current || navigationPending.current || unavailable || !hasRoutableModel) return;
    const run = { controller: new AbortController(), sessionId: activeId, stopped: false, cancellation: undefined as Promise<void> | undefined };
    // A ref locks synchronously, before any await or React re-render.
    runRef.current = run;
    const epoch = ++viewEpoch.current;
    const baselineSeq = Math.max(0, ...events.map(event => event.seq));
    const active = () => mounted.current && viewEpoch.current === epoch;
    let failed = false;
    let completed = false;
    let submitted = false;
    setBusy(true); setInput(''); setNotice('');
    setCurrentAction(activeId ? '正在连接模型' : '正在建立会话');
    setProgress({ phase: 'connecting', startedAt: Date.now(), finishedAt: null, toolCount: 0 });
    followOutput.current = true; setShowLatest(false);
    // An interrupted draft is not a completed server message. Keep its visible
    // text locally when the user starts another turn rather than erasing it.
    if (turn?.text || turn?.error) {
      const previous = turn;
      setEvents(items => [...items,
        ...(previous.text ? [{ event_id: -Date.now(), seq: -1, kind: 'assistant_message', role: 'assistant', payload: { text: previous.text }, created_at: new Date().toISOString() }] : []),
        ...(previous.error ? [{ event_id: -Date.now() - 1, seq: -1, kind: 'error', role: 'system', payload: { text: previous.error }, created_at: new Date().toISOString() }] : []),
      ]);
    }
    setTurn({ text: '', toolCalls: [] }); setLiveArtifacts([]);
    const fail = (message: string) => {
      failed = true;
      if (!active() || run.stopped) return;
      setCurrentAction('本轮未完成');
      setTurn(previous => ({ text: previous?.text || '', toolCalls: previous?.toolCalls || [], error: message }));
    };
    try {
      if (!run.sessionId) {
        const created = await api.createSession({ title: text.slice(0, 18), context, ...selection }, run.controller.signal);
        run.sessionId = created.session.session_id;
        if (run.stopped || !active()) return;
        setActiveId(run.sessionId);
      }
      if (run.stopped || !active()) return;
      setCurrentAction('正在等待模型响应');
      setEvents(previous => [...previous, {
        event_id: -Date.now() - 2, seq: -1, kind: 'user_message', role: 'user',
        payload: { text }, created_at: new Date().toISOString(),
      }]);
      submitted = true;
      await streamTurn(run.sessionId, text, {
        signal: run.controller.signal,
        onEvent: event => {
          if (!active() || run.stopped) return;
          if (event.kind === 'delta') {
            setCurrentAction('正在生成回复');
            setProgress(previous => previous && ({ ...previous, phase: 'writing' }));
            setTurn(previous => ({ ...previous, text: (previous?.text || '') + String(event.text || ''), toolCalls: previous?.toolCalls || [] }));
          } else if (event.kind === 'tool_call') {
            setCurrentAction('正在调用工具');
            setProgress(previous => previous && ({ ...previous, phase: 'tools', toolCount: previous.toolCount + 1 }));
            setTurn(previous => ({ ...previous, text: previous?.text || '', toolCalls: [...(previous?.toolCalls || []), { callId: event.call_id, name: event.name, arguments: event.arguments }] }));
          } else if (event.kind === 'tool_result') {
            setCurrentAction('工具已返回，等待模型继续');
            setTurn(previous => ({ ...previous, text: previous?.text || '', toolCalls: (previous?.toolCalls || []).map(call => call.callId === event.call_id ? { ...call, result: event.result } : call) }));
          } else if (event.kind === 'error') {
            fail(String(event.error || '本轮请求失败'));
          } else if (event.kind === 'cancelled' || (event.kind === 'done' && event.cancelled)) {
            run.stopped = true;
          } else if (event.kind === 'done') {
            completed = true;
          } else if (event.kind === 'artifact') {
            const artifact = event.artifact || event.payload?.artifact;
            if (artifact) setLiveArtifacts(previous => [...previous, artifact]);
            window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
          }
        },
        onError: fail,
        onDone: () => undefined,
      });
    } catch (error) {
      if (!run.stopped) fail(error instanceof Error ? error.message : '请求失败，请重试。');
    } finally {
      await run.cancellation;
      if (runRef.current === run) runRef.current = null;
      if (active()) {
        setBusy(false);
        if (!submitted) setInput(previous => previous || text);
        const phase: RunPhase = run.stopped ? 'stopped' : failed || !completed ? 'failed' : 'completed';
        setCurrentAction(phase === 'stopped' ? '已停止' : phase === 'completed' ? '回复完成' : '本轮未完成');
        setProgress(previous => previous && ({ ...previous, phase, finishedAt: Date.now() }));
      }
    }
    if (!active()) return;
    if (completed && !failed && !run.stopped && run.sessionId) {
      try {
        const detail = await api.sessionDetail(run.sessionId);
        if (active() && detail.events.some(event => event.kind === 'assistant_message' && event.seq > baselineSeq)) {
          setEvents(detail.events); setTurn(null); setLiveArtifacts([]);
        }
      } catch {
        if (active()) setNotice('回复已收到，但会话同步失败；当前内容仍然保留。');
      }
    }
    if (active()) {
      void loadSessions();
      window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
    }
  };

  const stop = () => {
    const run = runRef.current;
    if (!run || run.stopped) return;
    run.stopped = true;
    setCurrentAction('正在停止');
    if (run.sessionId) {
      run.cancellation = api.cancelTurn(run.sessionId, AbortSignal.timeout(5000)).then(() => undefined).catch(() => {
        if (mounted.current && runRef.current === run) setNotice('已停止接收；后端取消未确认，远端请求可能仍在运行。');
      });
    }
    run.controller.abort();
  };

  const fork = async () => {
    if (!activeId || runRef.current || navigationPending.current) return;
    navigationPending.current = true;
    try {
      const result = await api.forkSession(activeId, {});
      navigationPending.current = false;
      if (mounted.current) { switchSession(result.session.session_id); await loadSessions(); }
    } catch { if (mounted.current) setNotice('分叉会话失败，请重试。'); }
    finally { navigationPending.current = false; }
  };

  const toolResults = new Map(events.filter(event => event.kind === 'tool_result')
    .map(event => [event.payload.call_id, event.payload.result]));
  const activeSession = sessions.find((session) => session.session_id === activeId) || null;
  // The offline template is a retired migration record. Keep it in backend
  // state for old sessions, but never offer it as a selectable model route.
  const providers = (meta?.providers || []).filter((provider) => provider.protocol !== 'offline');
  const seatModel = findModel(providers, selection.provider_id, selection.model);
  const seatProvider = providers.find((item) => item.provider_id === selection.provider_id);

  const hasRoutableModel = Boolean(
    seatModel && seatProvider && seatProvider.protocol !== 'offline' && seatProvider.routable === true,
  );

  const requestPromotion = (strategyId: string) => {
    setPromotionDraft((prev) => ({ ...prev, [strategyId]: { note: '', status: '待确认' } }));
  };

  const confirmPromotion = async (strategyId: string) => {
    const draft = promotionDraft[strategyId];
    if (!draft || !draft.note.trim()) return;
    try {
      await api.promoteRule(strategyId, draft.note.trim());
      setPromotionDraft((prev) => ({ ...prev, [strategyId]: { ...draft, status: '已成为 Champion' } }));
      window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
      const detail = activeId ? await api.sessionDetail(activeId) : null;
      if (detail) setEvents(detail.events);
    } catch (failure) {
      try {
        const req = await api.requestStrategyPromotion(strategyId);
        if (req.promotion?.promotion_id) {
          await api.confirmStrategyPromotion(req.promotion.promotion_id, draft.note.trim());
          setPromotionDraft((prev) => ({ ...prev, [strategyId]: { ...draft, status: '已成为 Champion' } }));
          window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
          const detail = activeId ? await api.sessionDetail(activeId) : null;
          if (detail) setEvents(detail.events);
          return;
        }
      } catch {
        // ignore fallback
      }
      setPromotionDraft((prev) => ({ ...prev, [strategyId]: { ...draft, status: '确认失败：' + (failure instanceof Error ? failure.message : String(failure)) } }));
    }
  };

  const renderArtifact = (artifact: Record<string, any>, key: string | number) => {
    const strategy = artifact.strategy || {};
    const evaluation = artifact.evaluation || {};
    const strategyId = String(strategy.strategy_id || key);
    const draft = promotionDraft[strategyId];
    return <div key={key} className="assistant-artifact">
      <div className="artifact-kicker">治理产出 · challenger</div>
      <strong>{strategy.title || strategy.name || '新规则候选'}</strong>
      <div className="muted">{evaluation.status === 'passed' ? '评估已通过，可以发起人工确认。' : '评估未通过，先补齐门禁条件再考虑晋级。'}</div>
      <div className="row" style={{ marginTop: 8 }}><span className="tag accent">{strategy.status || 'challenger'}</span><span className="tag">{strategyId}</span></div>
      {evaluation.status === 'passed' && !draft ? <button className="ghost" style={{ marginTop: 8 }} onClick={() => requestPromotion(strategyId)}>申请晋级 Champion</button> : null}
      {draft && draft.status !== '已成为 Champion' ? <div className="promotion-inline">
        <input aria-label="晋级确认说明" placeholder="写下你的确认依据" value={draft.note} onChange={(event) => setPromotionDraft((prev) => ({ ...prev, [strategyId]: { ...draft, note: event.target.value } }))} />
        <button className="primary" disabled={!draft.note.trim()} onClick={() => void confirmPromotion(strategyId)}>确认晋级</button>
        <span className="muted">{draft.status}</span>
      </div> : null}
      {draft?.status === '已成为 Champion' ? <div className="status-line ok">✓ 已成为 Champion</div> : null}
    </div>;
  };

  return (
    <aside className={'assistant' + (expanded ? ' expanded' : '')}>
      <div className="assistant-head">
        <strong style={{ fontSize: 12 }}>复盘助手</strong>
        <span className="muted" style={{ fontSize: 11 }}>
          {activeSession ? activeSession.title : '未选择会话'}
        </span>
        <div style={{ flex: 1 }} />
        <span className={'assistant-live-dot' + (busy ? ' busy' : '')} title={busy ? '正在处理' : '已就绪'} />
        <button className="ghost" onClick={() => setShowSessions((prev) => !prev)} title="会话列表">
          会话
        </button>
        <button className="ghost" disabled={busy} onClick={startSession} title="新建会话">新建</button>
        {activeId ? <button className="ghost" disabled={busy} onClick={fork} title="分叉会话">分叉</button> : null}
        <button className="ghost" onClick={() => setExpanded((prev) => !prev)} title={expanded ? '恢复停靠' : '展开助手'}>{expanded ? '恢复' : '展开'}</button>
        {onClose ? <button className="ghost" onClick={onClose}>收起</button> : null}
      </div>

      {showSessions ? (
        <div style={{ maxHeight: 200, overflow: 'auto', borderBottom: '1px solid var(--border)' }}>
          {sessions.length === 0 ? <div className="muted" style={{ padding: 10 }}>还没有会话</div> : null}
          {sessions.map((session) => (
            <button
              key={session.session_id}
              className={'nav-item' + (session.session_id === activeId ? ' active' : '')}
              disabled={busy}
              onClick={() => switchSession(session.session_id)}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{session.title}</span>
              <span className="muted" style={{ fontSize: 10 }}>{session.status}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="assistant-body" ref={bodyRef} onScroll={() => {
        const node = bodyRef.current;
        if (!node) return;
        followOutput.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
        setShowLatest(!followOutput.current);
      }}>
        {expanded ? (
          <div className="assistant-context-rail">
            <span className="eyebrow">LIVE CONTEXT</span>
            <span>{context.round_trip_id ? '已锁定一笔交易' : '当前未锁定交易'}</span>
            <span className="muted">台账 · 规则 · 数据质量会随本轮请求一起校验</span>
          </div>
        ) : null}
        {notice ? <div className="notice" role="status">{notice}</div> : null}
        {unavailable ? (
          <div className="notice" style={{ fontSize: 12, lineHeight: 1.7 }}>
            复盘助手在这个部署里不可用：{unavailable}
            <div className="muted" style={{ marginTop: 6, fontSize: 11 }}>
              助手与设置面板读取的是本机的单用户状态，托管部署会在信任边界处关闭它们。
              交易台账、归因分析与回测都不受影响。
            </div>
          </div>
        ) : null}
        {!unavailable && !hasRoutableModel && !turn ? (
          <div className="notice assistant-model-cta">
            当前还没有可路由的模型。请到“设置 → 模型”配置 Provider 后再开始复盘。
            <button className="ghost" onClick={onMetaReload}>重新读取模型</button>
          </div>
        ) : null}
        {!unavailable && hasRoutableModel && events.length === 0 && !turn ? (
          <div className="muted" style={{ fontSize: 12, lineHeight: 1.7 }}>
            问点什么，例如：<br />
            · 我这个月哪些交易违反了止损纪律？<br />
            · 按持有周期拆一下收益，样本量够吗？<br />
            · 最近三笔亏损交易的共同点是什么？
          </div>
        ) : null}
        {events.map((event) => {
          if (event.kind === 'user_message') {
            return <div key={event.event_id} className="bubble user">{String(event.payload.text || '')}</div>;
          }
          if (event.kind === 'assistant_message') {
            return (
              <div key={event.event_id} className="bubble assistant">
                <Markdown text={String(event.payload.text || '')} />
              </div>
            );
          }
          if (event.kind === 'tool_call') {
            const result = toolResults.get(event.payload.call_id);
            return (
              <details key={event.event_id} className="tool-card">
                <summary>工具调用 · {String(event.payload.name || '')}</summary>
                <pre>{JSON.stringify({ arguments: event.payload.arguments, result }, null, 2)}</pre>
              </details>
            );
          }
          if (event.kind === 'error') {
            return <div key={event.event_id} className="bubble error">{String(event.payload.text || event.payload.error || '本轮失败')}</div>;
          }
          if (event.kind === 'artifact') {
            const artifact = event.payload?.artifact || (event as any).artifact || {};
            return renderArtifact(artifact, event.event_id);
          }
          return null;
        })}

        {turn ? (
          <>
            {turn.toolCalls.map((call) => (
              <details key={call.callId} className="tool-card">
                <summary>
                  <span className={'tool-state ' + (toolFailed(call.result) ? 'failed' : call.result === undefined && busy ? 'running' : '')} aria-hidden="true">{toolFailed(call.result) ? '!' : call.result === undefined ? (busy ? '◌' : '○') : '✓'}</span>
                  {call.name} <span className="muted">{toolFailed(call.result) ? '工具失败' : call.result === undefined ? (busy ? '进行中' : '未完成') : '已返回'}</span>
                </summary>
                <pre>{JSON.stringify({ arguments: call.arguments, result: call.result }, null, 2)}</pre>
              </details>
            ))}
            {turn.text ? <div className="bubble assistant"><Markdown text={turn.text} /></div> : null}
            {turn.error ? <div className="bubble error" role="alert">{turn.error}</div> : null}

          </>
        ) : null}
        {liveArtifacts.map((artifact, index) => renderArtifact(artifact, 'live-' + index))}
        {progress ? <AssistantProgress {...progress} label={currentAction} /> : null}
      </div>

      {showLatest ? <button className="assistant-latest ghost" onClick={() => {
        followOutput.current = true; setShowLatest(false);
        if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
      }}>↓ 回到最新</button> : null}
      <div className="assistant-foot">
        <textarea
          value={input}
          disabled={Boolean(unavailable)}
          placeholder="描述你想复盘的问题（回车发送，Shift+回车换行）"
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
          <fieldset className="assistant-model-fieldset" disabled={busy}>
          <ModelPicker
            providers={providers}
            selection={selection}
            onSelect={(next) => { void applySelection(next).catch(() => setNotice('模型选择保存失败，请重试。')); }}
          />
          </fieldset>
          <div className="row" style={{ gap: 8, marginLeft: 'auto' }}>
            {busy ? (
              <button className="ghost" onClick={stop}>停止</button>
            ) : (
              <button className="primary" onClick={send} disabled={!input.trim() || Boolean(unavailable) || !hasRoutableModel}>发送</button>
            )}
          </div>
        </div>
        <div className="muted" style={{ fontSize: 10.5, lineHeight: 1.6 }}>
          {seatProvider ? seatProvider.label : '未选择 Provider'}
          {seatModel ? ' · ' + (seatModel.label || seatModel.id) : ''}
          {seatModel && seatModel.reasoning_efforts.length > 1
            ? ' · 推理强度 ' + effortLabel(selection.reasoning)
            : ''}
          <br />
          原文只在本机解析 · 外发字段已脱敏
        </div>
      </div>
    </aside>
  );
}
