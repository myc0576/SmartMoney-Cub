import { useEffect, useRef, useState } from 'react';
import { api, streamTurn } from '../api';
import { Markdown } from './common';
import { ModelPicker, effortLabel, findModel } from './ModelPicker';
import type { Meta, SessionEvent, SessionSummary } from '../types';

// The assistant panel mirrors the harness interaction model: a session list, a
// transcript with expandable tool cards, and a live connection indicator. Every
// event shown here is also stored locally, so a reload restores the transcript.

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
  const [reviewScope, setReviewScope] = useState<import('../types').ReviewScopeResponse | null>(null);
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

  const loadSessions = async () => {
    try {
      const result = await api.sessions();
      setSessions(result.sessions);
      setUnavailable('');
      return result.sessions;
    } catch (failure) {
      setSessions([]);
      setUnavailable(failure instanceof Error ? failure.message : String(failure));
      return [];
    }
  };

  useEffect(() => {
    void loadSessions().then((list) => {
      if (list.length) setActiveId(list[0].session_id);
    });
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
    if (!activeId) {
      setEvents([]);
      return;
    }
    void api.sessionDetail(activeId).then((detail) => {
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
    });
    void api.reviewScope(activeId).then(setReviewScope).catch(() => setReviewScope(null));
  }, [activeId, meta]);

  useEffect(() => {
    const node = bodyRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [events, turn]);

  const startSession = async () => {
    const created = await api.createSession({
      title: '复盘 ' + new Date().toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }),
      context,
      provider_id: meta?.default_provider || 'alphatech',
    });
    await loadSessions();
    setActiveId(created.session.session_id);
    setShowSessions(false);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    let sessionId = activeId;
    if (!sessionId) {
      const created = await api.createSession({
        title: text.slice(0, 18),
        context,
        provider_id: selection.provider_id,
        model: selection.model,
        reasoning: selection.reasoning,
      });
      sessionId = created.session.session_id;
      setActiveId(sessionId);
      await loadSessions();
    }
    if (!reviewScope?.confirmed || reviewScope.envelope.scope.review_id !== sessionId) {
      const preview = await api.reviewScope(sessionId);
      setReviewScope(preview);
      return;
    }
    setInput('');
    setBusy(true);
    setTurn({ text: '', toolCalls: [] });
    const controller = new AbortController();
    abortRef.current = controller;
    setEvents((prev) => [
      ...prev,
      {
        event_id: -1, seq: -1, kind: 'user_message', role: 'user',
        payload: { text }, created_at: new Date().toISOString(),
      },
    ]);

    await streamTurn(sessionId, text, {
      signal: controller.signal,
      onEvent: (event) => {
        if (event.kind === 'delta') {
          setTurn((prev) => ({ text: (prev?.text || '') + event.text, toolCalls: prev?.toolCalls || [] }));
        } else if (event.kind === 'tool_call') {
          setTurn((prev) => ({
            text: prev?.text || '',
            toolCalls: [...(prev?.toolCalls || []), { callId: event.call_id, name: event.name, arguments: event.arguments }],
          }));
        } else if (event.kind === 'tool_result') {
          setTurn((prev) => ({
            text: prev?.text || '',
            toolCalls: (prev?.toolCalls || []).map((call) =>
              call.callId === event.call_id ? { ...call, result: event.result } : call,
            ),
          }));
        } else if (event.kind === 'error') {
          setTurn((prev) => ({ text: prev?.text || '', toolCalls: prev?.toolCalls || [], error: event.error }));
        }
      },
      onError: (message) => {
        setTurn((prev) => ({ text: prev?.text || '', toolCalls: prev?.toolCalls || [], error: message }));
      },
      onDone: () => {
        setBusy(false);
        setTurn(null);
        void api.sessionDetail(sessionId!).then((detail) => setEvents(detail.events));
        void loadSessions();
      },
    });
  };

  const stop = async () => {
    if (activeId && busy) {
      await api.cancelTurn(activeId).catch(() => undefined);
    }
    abortRef.current?.abort();
    setBusy(false);
    setTurn(null);
  };

  const confirmScope = async () => {
    if (!activeId) return;
    const confirmed = await api.confirmReviewScope(activeId, { review_id: activeId });
    setReviewScope(confirmed);
    await loadSessions();
  };

  const fork = async () => {
    if (!activeId) return;
    const result = await api.forkSession(activeId, {});
    await loadSessions();
    setActiveId(result.session.session_id);
  };

  const activeSession = sessions.find((session) => session.session_id === activeId) || null;
  const providers = meta?.providers || [];
  const seatModel = findModel(providers, selection.provider_id, selection.model);
  const seatProvider = providers.find((item) => item.provider_id === selection.provider_id);

  return (
    <aside className="assistant">
      <div className="assistant-head">
        <strong style={{ fontSize: 12 }}>复盘助手</strong>
        <span className="muted" style={{ fontSize: 11 }}>
          {activeSession ? activeSession.title : '未选择会话'}
        </span>
        <div style={{ flex: 1 }} />
        <button className="ghost" onClick={() => setShowSessions((prev) => !prev)} title="会话列表">
          会话
        </button>
        <button className="ghost" onClick={startSession} title="新建会话">新建</button>
        {activeId ? <button className="ghost" onClick={fork} title="分叉会话">分叉</button> : null}
        {onClose ? <button className="ghost" onClick={onClose}>收起</button> : null}
      </div>

      {showSessions ? (
        <div style={{ maxHeight: 200, overflow: 'auto', borderBottom: '1px solid var(--border)' }}>
          {sessions.length === 0 ? <div className="muted" style={{ padding: 10 }}>还没有会话</div> : null}
          {sessions.map((session) => (
            <button
              key={session.session_id}
              className={'nav-item' + (session.session_id === activeId ? ' active' : '')}
              onClick={() => { setActiveId(session.session_id); setShowSessions(false); }}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{session.title}</span>
              <span className="muted" style={{ fontSize: 10 }}>{session.status}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="assistant-body" ref={bodyRef}>
        {reviewScope && !reviewScope.confirmed ? (
          <div className="notice" style={{ fontSize: 12, lineHeight: 1.6 }}>
            <strong>请先确认本次复盘范围</strong>
            <div className="muted" style={{ marginTop: 4 }}>
              DSH 只会收到脱敏后的摘要；决策时间：{String(reviewScope.envelope.scope.decision_time || '—')}。
            </div>
            <button className="primary" style={{ marginTop: 8 }} onClick={() => void confirmScope()}>
              确认范围并继续
            </button>
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
        {!unavailable && events.length === 0 && !turn ? (
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
            return <div key={event.event_id} className="bubble error">{String(event.payload.text || '')}</div>;
          }
          return null;
        })}

        {turn ? (
          <>
            {turn.toolCalls.map((call) => (
              <details key={call.callId} className="tool-card" open>
                <summary>
                  工具调用 · {call.name} {call.result === undefined ? <span className="muted">（进行中）</span> : null}
                </summary>
                <pre>{JSON.stringify({ arguments: call.arguments, result: call.result }, null, 2)}</pre>
              </details>
            ))}
            {turn.text ? <div className="bubble assistant"><Markdown text={turn.text} /></div> : null}
            {turn.error ? <div className="bubble error">{turn.error}</div> : null}
          </>
        ) : null}
      </div>

      <div className="assistant-foot">
        <textarea
          value={input}
          disabled={Boolean(unavailable)}
          placeholder="描述你想复盘的问题（回车发送，Shift+回车换行）"
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
          <ModelPicker
            providers={providers}
            selection={selection}
            onSelect={(next) => void applySelection(next)}
          />
          <div className="row" style={{ gap: 8, marginLeft: 'auto' }}>
            {busy ? (
              <button className="ghost" onClick={() => void stop()}>停止</button>
            ) : (
              <button className="primary" onClick={send} disabled={!input.trim() || Boolean(unavailable)}>发送</button>
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
