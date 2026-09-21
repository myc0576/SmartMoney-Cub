import { useEffect, useRef, useState } from 'react';
import { api, streamTurn } from '../api';
import { Markdown } from './common';
import { AssistantActivity, type Activity, type ToolCall } from './AssistantActivity';
import { ModelPicker, effortLabel, findModel } from './ModelPicker';
import type { Meta, SessionEvent, SessionSummary } from '../types';

// The assistant panel mirrors the harness interaction model: a session list, a
// transcript with expandable tool cards, and a live connection indicator. Every
// event shown here is also stored locally, so a reload restores the transcript.

interface TurnState {
  text: string;
  toolCalls: ToolCall[];
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
  const [activity, setActivity] = useState<Activity | null>(null);
  const [lastTools, setLastTools] = useState<ToolCall[]>([]);
  const [panelError, setPanelError] = useState('');
  const [showJump, setShowJump] = useState(false);
  const [navigationPending, setNavigationPending] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(true);
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
  const abortRef = useRef<AbortController | null>(null);
  const aliveRef = useRef(true);
  const requestRef = useRef(0);
  const busyRef = useRef(false);
  const runSessionRef = useRef<string | null>(null);
  const followRef = useRef(true);

  const chooseSession = (id: string) => {
    ++requestRef.current;
    setActiveId(id); setShowSessions(false); setTurn(null); setActivity(null);
    setLiveArtifacts([]); setLastTools([]); setPanelError('');
    followRef.current = true; setShowJump(false);
  };

  const loadSessions = async () => {
    try {
      const result = await api.sessions();
      if (!aliveRef.current) return [];
      setSessions(result.sessions);
      setUnavailable('');
      return result.sessions;
    } catch (failure) {
      if (!aliveRef.current) return [];
      setSessions([]);
      setUnavailable(failure instanceof Error ? failure.message : String(failure));
      return [];
    }
  };

  useEffect(() => {
    aliveRef.current = true;
    const version = requestRef.current;
    void loadSessions().then(list => {
      if (!aliveRef.current || requestRef.current !== version) return;
      if (list.length) setActiveId(list[0].session_id);
      setLoadingSessions(false);
    });
    return () => {
      aliveRef.current = false; ++requestRef.current;
      abortRef.current?.abort();
      if (busyRef.current && runSessionRef.current) {
        void api.cancelTurn(runSessionRef.current, AbortSignal.timeout(5000)).catch(() => {});
      }
    };
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
    if (busyRef.current) return;
    busyRef.current = true; setNavigationPending(true); setPanelError('');
    try {
      if (activeId) await api.updateSession(activeId, next);
      await api.updateSettings({ default_provider_id: next.provider_id, default_model: next.model, default_reasoning: next.reasoning });
      if (aliveRef.current) { setSelection(next); await loadSessions(); onMetaReload?.(); }
    } catch (error) { if (aliveRef.current) setPanelError(error instanceof Error ? error.message : '模型切换失败'); }
    finally { busyRef.current = false; if (aliveRef.current) setNavigationPending(false); }
  };

  useEffect(() => {
    let cancelled = false;
    const version = requestRef.current;
    if (busyRef.current) return;
    if (!activeId) {
      setEvents([]);
      return;
    }
    void api.sessionDetail(activeId).then((detail) => {
      if (cancelled || !aliveRef.current || busyRef.current || requestRef.current !== version) return;
      setEvents(detail.events);
      const session = detail.session;
      if (session) {
        // A session recorded before the model was part of the seat carries an
        // empty model. Adopting that empty value would blank the picker, so each
        // field only overwrites the current choice when the session actually
        // recorded one - a legacy log must not hide a working default.
        setSelection({
          provider_id: session.provider_id || meta?.default_provider || 'alphatech',
          model: session.model || meta?.default_model || '',
          reasoning: session.reasoning || meta?.default_reasoning || 'off',
        });
      }
    }).catch(error => {
      if (!cancelled && aliveRef.current && requestRef.current === version) setPanelError(error instanceof Error ? error.message : '读取会话失败');
    });
    return () => { cancelled = true; };
  }, [activeId, meta, navigationPending]);

  useEffect(() => {
    const node = bodyRef.current;
    if (node && followRef.current) node.scrollTop = node.scrollHeight;
    else if (node) setShowJump(true);
  }, [events, turn, activity?.phase]);

  const startSession = async () => {
    if (busyRef.current || unavailable) return;
    busyRef.current = true; setNavigationPending(true); setPanelError('');
    try {
      const created = await api.createSession({ title: '新的复盘', context, ...selection });
      if (aliveRef.current) { chooseSession(created.session.session_id); await loadSessions(); }
    } catch (error) { if (aliveRef.current) setPanelError(error instanceof Error ? error.message : '创建会话失败'); }
    finally { busyRef.current = false; if (aliveRef.current) setNavigationPending(false); }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busyRef.current || unavailable || !hasRoutableModel || loadingSessions) return;
    // Lock synchronously, before the first await (React state alone can race).
    busyRef.current = true;
    const version = ++requestRef.current;
    const current = () => aliveRef.current && requestRef.current === version;
    const controller = new AbortController();
    abortRef.current = controller;
    runSessionRef.current = activeId;
    let sessionId = activeId;
    let failed = false;
    let completed = false;
    let cancelled = false;
    let calls: ToolCall[] = [];
    setBusy(true); setInput(''); setPanelError(''); setLastTools([]);
    setActivity({ phase: 'connecting', startedAt: Date.now() });
    followRef.current = true; setShowJump(false);
    setEvents(previous => {
      // Keep an interrupted reply visible when the next turn starts, even if
      // the server did not persist the last delta before the connection broke.
      const extra: SessionEvent[] = [];
      const now = new Date().toISOString();
      if (turn?.text) extra.push({ event_id: -Date.now() - 1, seq: -1, kind: 'assistant_message', role: 'assistant', payload: { text: turn.text }, created_at: now });
      if (turn?.error) extra.push({ event_id: -Date.now() - 2, seq: -1, kind: 'error', role: 'assistant', payload: { error: turn.error }, created_at: now });
      return [...previous, ...extra, { event_id: -Date.now(), seq: -1, kind: 'user_message', role: 'user', payload: { text }, created_at: now }];
    });
    setTurn({ text: '', toolCalls: [] }); setLiveArtifacts([]);
    const fail = (message: string) => {
      if (!current() || failed) return;
      failed = true;
      setTurn(previous => ({ text: previous?.text || '', toolCalls: previous?.toolCalls || [], error: message }));
      setActivity(previous => previous && { ...previous, phase: 'error', finishedAt: Date.now() });
    };
    const phase = (value: Activity['phase']) => {
      if (!failed) setActivity(previous => previous && { ...previous, phase: value });
    };
    try {
      if (!sessionId) {
        const created = await api.createSession({ title: text.slice(0, 18), context, ...selection });
        if (!current()) return; // Stopped while session creation was in flight.
        sessionId = created.session.session_id;
        runSessionRef.current = sessionId;
        setActiveId(sessionId);
        setSessions(previous => [created.session, ...previous]);
      }
      await streamTurn(sessionId, text, {
        signal: controller.signal,
        onEvent: event => {
          if (!current()) return;
          if (event.kind === 'delta') {
            phase('responding');
            setTurn(previous => ({ ...previous, text: (previous?.text || '') + String(event.text || ''), toolCalls: previous?.toolCalls || [] }));
          } else if (event.kind === 'tool_call') {
            phase('tools');
            calls = [...calls, { callId: String(event.call_id), name: String(event.name || '工具'), arguments: event.arguments }];
            setTurn(previous => ({ ...previous, text: previous?.text || '', toolCalls: calls }));
          } else if (event.kind === 'tool_result') {
            calls = calls.map(call => call.callId === String(event.call_id) ? { ...call, result: event.result ?? null } : call);
            phase(calls.some(call => call.result === undefined) ? 'tools' : 'thinking');
            setTurn(previous => ({ ...previous, text: previous?.text || '', toolCalls: calls }));
          } else if (event.kind === 'error') {
            fail(String(event.error || '本轮未完成'));
          } else if (event.kind === 'cancelled' || (event.kind === 'done' && event.cancelled)) {
            cancelled = true;
          } else if (event.kind === 'artifact') {
            const artifact = event.artifact || event.payload?.artifact;
            if (artifact) setLiveArtifacts(previous => [...previous, artifact]);
            window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
          }
        },
        onError: fail,
        onDone: () => { completed = true; },
      });
      if (current() && !completed && !failed && !controller.signal.aborted) fail('响应未完成，请重试。');
    } catch (error) {
      if (!controller.signal.aborted) fail(error instanceof Error ? error.message : '无法启动本轮复盘，请重试。');
    } finally {
      if (current()) {
        busyRef.current = false; setBusy(false); abortRef.current = null; runSessionRef.current = null;
        setLastTools(calls);
        setActivity(previous => previous && { ...previous, phase: failed ? 'error' : cancelled ? 'stopped' : 'complete', finishedAt: Date.now() });
        if (completed && !failed && !cancelled && sessionId) {
          try {
            const detail = await api.sessionDetail(sessionId);
            if (current() && !busyRef.current) {
              setEvents(detail.events); setTurn(null); setLiveArtifacts([]);
            }
          } catch {
            if (current()) setPanelError('回复已完成，但历史记录刷新失败；当前内容已保留。');
          }
        }
        if (current()) { void loadSessions(); window.dispatchEvent(new CustomEvent('smcub:rules-updated')); }
      }
    }
  };

  const stop = async () => {
    if (!busyRef.current || activity?.phase === 'stopping') return;
    const version = ++requestRef.current;
    const sessionId = runSessionRef.current;
    abortRef.current?.abort(); abortRef.current = null;
    setActivity(previous => previous && { ...previous, phase: 'stopping' });
    try {
      if (sessionId) await api.cancelTurn(sessionId, AbortSignal.timeout(5000));
    } catch {
      if (aliveRef.current && requestRef.current === version) setPanelError('已停止接收回复，但后端取消未确认；请稍后检查会话状态。');
    } finally {
      if (aliveRef.current && requestRef.current === version) {
        busyRef.current = false; runSessionRef.current = null; setBusy(false);
        setActivity(previous => previous && { ...previous, phase: 'stopped', finishedAt: Date.now() });
      }
    }
  };

  const fork = async () => {
    if (!activeId || busyRef.current) return;
    busyRef.current = true; setNavigationPending(true); setPanelError('');
    try {
      const result = await api.forkSession(activeId, {});
      if (aliveRef.current) { chooseSession(result.session.session_id); await loadSessions(); }
    } catch (error) { if (aliveRef.current) setPanelError(error instanceof Error ? error.message : '分叉失败'); }
    finally { busyRef.current = false; if (aliveRef.current) setNavigationPending(false); }
  };

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
      {evaluation.status === 'passed' && !draft ? <button className="ghost" style={{ marginTop: 8 }} disabled={busy} onClick={() => requestPromotion(strategyId)}>申请晋级 Champion</button> : null}
      {draft && draft.status !== '已成为 Champion' ? <div className="promotion-inline">
        <input aria-label="晋级确认说明" placeholder="写下你的确认依据" value={draft.note} onChange={(event) => setPromotionDraft((prev) => ({ ...prev, [strategyId]: { ...draft, note: event.target.value } }))} />
        <button className="primary" disabled={busy || !draft.note.trim()} onClick={() => void confirmPromotion(strategyId)}>确认晋级</button>
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
        <button className="ghost" onClick={() => setShowSessions((prev) => !prev)} disabled={busy || navigationPending} title="会话列表">
          会话
        </button>
        <button className="ghost" onClick={() => void startSession()} disabled={busy || navigationPending || loadingSessions || Boolean(unavailable)} title="新建会话">新建</button>
        {activeId ? <button className="ghost" onClick={() => void fork()} disabled={busy || navigationPending} title="分叉会话">分叉</button> : null}
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
              disabled={busy || navigationPending}
              onClick={() => chooseSession(session.session_id)}
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
        followRef.current = node.scrollHeight - node.scrollTop - node.clientHeight < 60;
        setShowJump(!followRef.current);
      }}>
        {panelError ? <div className="notice" role="alert">{panelError}</div> : null}
        {expanded ? (
          <div className="assistant-context-rail">
            <span className="eyebrow">LIVE CONTEXT</span>
            <span>{context.round_trip_id ? '已锁定一笔交易' : '当前未锁定交易'}</span>
            <span className="muted">台账 · 规则 · 数据质量会随本轮请求一起校验</span>
          </div>
        ) : null}
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
            const result = events.find(
              (other) => other.kind === 'tool_result' && other.payload.call_id === event.payload.call_id,
            );
            return (
              <details key={event.event_id} className="tool-card">
                <summary>工具调用 · {String(event.payload.name || '')}</summary>
                <pre>{JSON.stringify({ arguments: event.payload.arguments, result: result?.payload.result }, null, 2)}</pre>
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
            {turn.text ? <div className="bubble assistant"><Markdown text={turn.text} /></div> : null}
            {turn.error ? <div className="bubble error" role="alert">{turn.error}</div> : null}
          </>
        ) : null}
        {activity ? <AssistantActivity activity={activity} calls={turn?.toolCalls || lastTools} /> : null}
        {liveArtifacts.map((artifact, index) => renderArtifact(artifact, 'live-' + index))}
      </div>

      {showJump ? <button className="ghost assistant-jump" onClick={() => {
        followRef.current = true; setShowJump(false);
        if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
      }}>回到最新回复 ↓</button> : null}
      <div className="assistant-foot">
        <textarea
          aria-label="复盘问题"
          value={input}
          disabled={Boolean(unavailable)}
          placeholder="描述你想复盘的问题（回车发送，Shift+回车换行）"
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
          {busy || navigationPending ? <span className="muted">本轮模型已锁定</span> : <ModelPicker
            providers={providers}
            selection={selection}
            onSelect={(next) => void applySelection(next)}
          />}
          <div className="row" style={{ gap: 8, marginLeft: 'auto' }}>
            {busy ? (
              <button className="ghost" disabled={activity?.phase === 'stopping'} onClick={() => void stop()}>停止</button>
            ) : (
              <button className="primary" onClick={() => void send()} disabled={!input.trim() || Boolean(unavailable) || !hasRoutableModel || navigationPending || loadingSessions}>发送</button>
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
