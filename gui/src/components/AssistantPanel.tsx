import { useEffect, useRef, useState } from 'react';
import { api, streamTurn } from '../api';
import { Markdown } from './common';
import { ModelPicker, effortLabel, findModel } from './ModelPicker';
import type { Meta, ReviewAgent, SessionEvent, SessionSummary } from '../types';
import { useLocale, type Locale } from '../i18n';

const REVIEW_AGENT_LABELS: Record<Locale, { builtIn: string; available: string; preparing: string; incomplete: string }> = {
  'zh-CN': { builtIn: '内置模型', available: '可用于复盘', preparing: '正在准备这笔交易的复盘', incomplete: '本轮未完成' },
  'en-US': { builtIn: 'Built-in model', available: 'Available for review', preparing: 'Preparing this trade review', incomplete: 'This review did not complete' },
  'zh-TW': { builtIn: '內建模型', available: '可用於複盤', preparing: '正在準備這筆交易的複盤', incomplete: '本輪未完成' },
  'ja-JP': { builtIn: '内蔵モデル', available: 'レビューに使用可能', preparing: 'この取引のレビューを準備中', incomplete: 'レビューを完了できませんでした' },
  'ko-KR': { builtIn: '내장 모델', available: '복기에 사용 가능', preparing: '이 거래 복기를 준비하는 중', incomplete: '복기를 완료하지 못했습니다' },
  'es-ES': { builtIn: 'Modelo integrado', available: 'Disponible para revisión', preparing: 'Preparando la revisión de esta operación', incomplete: 'La revisión no se completó' },
  'pt-BR': { builtIn: 'Modelo integrado', available: 'Disponível para revisão', preparing: 'Preparando a revisão desta operação', incomplete: 'A revisão não foi concluída' },
  'de-DE': { builtIn: 'Integriertes Modell', available: 'Für Reviews verfügbar', preparing: 'Review dieses Trades wird vorbereitet', incomplete: 'Review wurde nicht abgeschlossen' },
  'fr-FR': { builtIn: 'Modèle intégré', available: 'Disponible pour les revues', preparing: 'Préparation de la revue de cette opération', incomplete: 'La revue n’est pas terminée' },
};

function canUseReviewAgent(agent: ReviewAgent): boolean {
  return agent.status === 'runnable' && agent.detected && agent.enabled && agent.protocol?.compatible !== false;
}

// The assistant panel mirrors the harness interaction model: a session list, a
// transcript with expandable tool cards, and a live connection indicator. Every
// event shown here is also stored locally, so a reload restores the transcript.

interface TurnState {
  text: string;
  toolCalls: {
    callId: string;
    name: string;
    arguments: string;
    result?: unknown;
    /** The backend's readable step line, when it sent one. */
    title?: string;
    summary?: string;
    status?: string;
    durationMs?: number;
  }[];
  error?: string;
}

/**
 * The three questions this panel is opened to ask.
 *
 * They are not generic prompts: each one is a question the journal can answer
 * from the trader's own rows, and each fires the read-only tools the assistant
 * already has. A shortcut that could not be answered would be worse than no
 * shortcut, because it would teach the reader the assistant guesses.
 */
const QUICK_ACTIONS: { label: string; prompt: string }[] = [
  { label: '今日复盘', prompt: '复盘我今天的交易：做了什么、和计划差在哪里、下一步该注意什么。' },
  // The prompt repeats the button's own words on purpose. The transcript is read
  // later, next to a sidebar of shortcuts, and a question whose wording does not
  // match the action that asked it reads like a different question.
  { label: '找重复错误', prompt: '在我的台账里找出重复错误，请引用具体的交易编号作为证据。' },
  { label: '检查规则执行', prompt: '对照我的 Champion 规则，检查最近这些交易里哪些出现了规则偏离。' },
];

/** What a tool call is doing, said in the reader's terms. The backend sends a
 *  title with each result; this map is the fallback for a stream that predates
 *  that field, or for a tool the map does not know, where the raw name is
 *  shown rather than "undefined". */
const TOOL_LABELS: Record<string, string> = {
  list_trades: '检索交易',
  get_trade: '读取单笔交易',
  analytics_summary: '汇总绩效指标',
  calendar_month: '读取月度日历',
  open_positions: '读取未配对持仓',
  list_rules: '读取规则库',
  data_quality_report: '检查数据质量',
  propose_challenger_rule: '提出 Challenger 规则',
  search_memory: '检索复盘记忆',
  read_ledger: '读取进化账本',
};

function toolLabel(name: string): string {
  return TOOL_LABELS[name] || name.replace(/_/g, ' ');
}

/** What the assistant is pointed at, in one line.
 *
 * The shell sends the page and, when one is open, the round trip. The label is
 * built here rather than in the shell so the panel can say "整个账本" for a page
 * that carries no subject — a silent empty string would read as a bug.
 */
function contextLabel(context: Record<string, unknown>): string {
  const page = String(context.page_label || context.page || '').trim();
  const trade = String(context.round_trip_id || '').trim();
  if (trade) return page ? page + ' · 这一笔交易 ' + trade : '这一笔交易 ' + trade;
  return page ? page + ' · 整个账本' : '整个账本';
}

/** What has been read so far, from counts the panel already holds. It reports
 *  what exists rather than a fixed claim: no session and no message is a real
 *  state, and saying "已读取 0" beats hiding the line. */
function contextSummary(context: Record<string, unknown>, eventCount: number, sessionCount: number): string {
  const parts: string[] = [];
  if (context.round_trip_id) parts.push('已锁定 1 笔交易');
  if (eventCount > 0) parts.push('本会话 ' + eventCount + ' 条事件');
  if (sessionCount > 0) parts.push('本地会话 ' + sessionCount + ' 个');
  parts.push('台账 · 规则 · 数据质量随本轮校验');
  return parts.join(' / ');
}

/**
 * One step of the agent's activity, as a row rather than a payload.
 *
 * The default face is the thing a person asked for: what it looked up, what it
 * found, and whether it is still working. The arguments and the raw result are
 * one click away, which is where a debugger belongs — visible on request and not
 * in the way of reading the answer. Every field it does not have is simply
 * absent rather than printed as the string "undefined".
 */
function renderStep(input: {
  key: string | number;
  name: string;
  title?: string;
  summary?: string;
  status?: string;
  durationMs?: number;
  arguments?: unknown;
  result?: unknown;
  state: 'running' | 'done' | 'unknown';
}) {
  const title = input.title || toolLabel(input.name);
  const failed = input.status === 'error';
  const seconds = typeof input.durationMs === 'number' ? (input.durationMs / 1000).toFixed(1) + 's' : '';
  return (
    <li
      key={input.key}
      className={'step' + (input.state === 'running' ? ' running' : '') + (failed ? ' failed' : '')}
    >
      <span className="step-dot" />
      <span className="step-body">
        <span className="step-title">{title}</span>
        {input.summary ? <span className="step-summary">{input.summary}</span> : null}
        {seconds ? <span className="muted">{seconds}</span> : null}
        {/* A running step says so; a finished one does not need to. */}
        {input.state === 'running' ? <span className="muted">进行中</span> : null}
        <details className="step-detail">
          <summary>查看技术细节</summary>
          <pre>{JSON.stringify({ name: input.name, arguments: input.arguments, result: input.result }, null, 2)}</pre>
        </details>
      </span>
    </li>
  );
}

export function AssistantPanel({ meta, context, onClose, onMetaReload, reviewTradeId, onReviewTradeHandled }: {
  meta: Meta | null;
  context: Record<string, unknown>;
  onClose?: () => void;
  onMetaReload?: () => void;
  reviewTradeId?: string | null;
  onReviewTradeHandled?: () => void;
}) {
  const [locale] = useLocale();
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
  const [reviewAgents, setReviewAgents] = useState<ReviewAgent[]>([]);
  const [reviewAgentId, setReviewAgentId] = useState<string | null>(null);
  const [reviewAgentsReady, setReviewAgentsReady] = useState(false);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const handledReviewRef = useRef<string | null>(null);

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
    void Promise.all([api.reviewAgents(), api.reviewAgentDefault()]).then(([agents, defaultAgent]) => {
      setReviewAgents(agents.agents || []);
      const candidate = defaultAgent.default?.agent_id || null;
      setReviewAgentId(candidate && (agents.agents || []).some((agent) => agent.agent_id === candidate && canUseReviewAgent(agent)) ? candidate : null);
    }).catch(() => setReviewAgents([])).finally(() => setReviewAgentsReady(true));
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

  const send = async (explicit?: string, sessionOverride?: string) => {
    // A quick action sends its own question; the composer sends what is typed.
    // One code path serves both, so the transcript, the session title, and the
    // busy state cannot differ between a typed question and a clicked one.
    const text = (explicit ?? input).trim();
    if (!text || busy) return;

    // The question is shown before the session is created, and that order is
    // deliberate. Creating a session is a round trip that can fail -- a closed
    // trust boundary, a store error -- and this used to append the message only
    // after it succeeded, so a failed create swallowed what the trader had
    // written and showed nothing at all. The transcript now records the question
    // first, where the trader can see it and retry it.
    setInput('');
    setBusy(true);
    setCurrentAction('正在连接模型');
    setTurn({ text: '', toolCalls: [] });
    setLiveArtifacts([]);
    const controller = new AbortController();
    abortRef.current = controller;
    setEvents((prev) => [
      ...prev,
      {
        event_id: -1, seq: -1, kind: 'user_message', role: 'user',
        payload: { text }, created_at: new Date().toISOString(),
      },
    ]);

    let sessionId = sessionOverride || activeId || null;
    if (!sessionId) {
      try {
        const created = await api.createSession({
          title: text.slice(0, 18),
          context,
          provider_id: selection.provider_id,
          model: selection.model,
          reasoning: selection.reasoning,
          agent_id: reviewAgentId,
        });
        sessionId = created.session.session_id;
        setActiveId(sessionId);
        await loadSessions();
      } catch (failure) {
        // The question stays on screen with the reason it went nowhere.
        const message = failure instanceof Error ? failure.message : String(failure);
        setBusy(false);
        setCurrentAction('');
        setTurn({ text: '', toolCalls: [], error: '无法新建会话：' + message });
        return;
      }
    }

    await streamTurn(sessionId, text, {
      signal: controller.signal,
      onEvent: (event) => {
        if (event.kind === 'delta') {
          setTurn((prev) => ({ text: (prev?.text || '') + event.text, toolCalls: prev?.toolCalls || [] }));
        } else if (event.kind === 'tool_call') {
          setCurrentAction(toolLabel(String(event.name || '')));
          setTurn((prev) => ({
            text: prev?.text || '',
            toolCalls: [...(prev?.toolCalls || []), {
              callId: event.call_id,
              name: event.name,
              arguments: event.arguments,
              // The backend sends a readable title with the call; the local map
              // is the fallback for a stream that predates the field.
              title: event.title,
            }],
          }));
        } else if (event.kind === 'tool_result') {
          setCurrentAction('证据已返回，正在整理');
          setTurn((prev) => ({
            text: prev?.text || '',
            toolCalls: (prev?.toolCalls || []).map((call) =>
              call.callId === event.call_id
                ? {
                    ...call,
                    result: event.result,
                    // The step line and its numbers come from the backend, which
                    // is the only place that can count what a tool actually
                    // returned. The number is never computed here from the
                    // rendered payload.
                    summary: event.step_summary,
                    status: event.status,
                    durationMs: event.duration_ms,
                  }
                : call,
            ),
          }));
        } else if (event.kind === 'error') {
          setCurrentAction('本轮未完成');
          setTurn((prev) => ({ text: prev?.text || '', toolCalls: prev?.toolCalls || [], error: event.error }));
        } else if (event.kind === 'artifact') {
          const artifact = event.artifact || event.payload?.artifact;
          if (artifact) setLiveArtifacts((prev) => [...prev, artifact]);
          setCurrentAction('已生成 Challenger，等待评估');
          window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
        }
      },
      onError: (message) => {
        setCurrentAction('连接中断');
        setTurn((prev) => ({ text: prev?.text || '', toolCalls: prev?.toolCalls || [], error: message }));
      },
      onDone: () => {
        setBusy(false);
        setCurrentAction('');
        setTurn(null);
        void api.sessionDetail(sessionId!).then((detail) => setEvents(detail.events));
        setLiveArtifacts([]);
        void loadSessions();
        window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
      },
    });
  };

  useEffect(() => {
    if (!reviewTradeId || !reviewAgentsReady || handledReviewRef.current === reviewTradeId || busy) return;
    handledReviewRef.current = reviewTradeId;
    setCurrentAction(agentLabels.preparing);
    void api.reviewFromTrade({ round_trip_id: reviewTradeId, agent_id: reviewAgentId, locale: document.documentElement.lang || 'zh-CN' })
      .then((result) => {
        setActiveId(result.session.session_id);
        setShowSessions(false);
        return send(result.prompt, result.session.session_id);
      })
      .catch((failure) => {
        setBusy(false);
        setCurrentAction(agentLabels.incomplete);
        setTurn({ text: '', toolCalls: [], error: failure instanceof Error ? failure.message : String(failure) });
      })
      .finally(() => onReviewTradeHandled?.());
  }, [reviewTradeId, reviewAgentId, reviewAgentsReady, busy]);

  const stop = () => {
    abortRef.current?.abort();
    setBusy(false);
    setTurn(null);
    setCurrentAction('已停止');
  };

  const fork = async () => {
    if (!activeId) return;
    const result = await api.forkSession(activeId, {});
    await loadSessions();
    setActiveId(result.session.session_id);
  };

  const activeSession = sessions.find((session) => session.session_id === activeId) || null;
  const agentLabels = REVIEW_AGENT_LABELS[locale];
  const usableReviewAgents = reviewAgents.filter(canUseReviewAgent);
  // The offline template is a retired migration record. Keep it in backend
  // state for old sessions, but never offer it as a selectable model route.
  const providers = (meta?.providers || []).filter((provider) => provider.protocol !== 'offline');
  const seatModel = findModel(providers, selection.provider_id, selection.model);
  const seatProvider = providers.find((item) => item.provider_id === selection.provider_id);
  // What the seat is, in one line. It is a label rather than a control: the
  // provider, the model, and the reasoning effort are configuration, and the
  // place configuration is changed is the settings page. Keeping them out of the
  // composer leaves the panel asking one question -- what do you want reviewed --
  // instead of two.
  const seatLabel = [
    seatProvider ? seatProvider.label : '未配置 Provider',
    seatModel ? (seatModel.label || seatModel.id) : '',
    seatModel && seatModel.reasoning_efforts.length > 1 ? effortLabel(selection.reasoning) : '',
  ].filter(Boolean).join(' · ');

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
        <button className="ghost" onClick={startSession} title="新建会话">新建</button>
        {activeId ? <button className="ghost" onClick={fork} title="分叉会话">分叉</button> : null}
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
              onClick={() => { setActiveId(session.session_id); setShowSessions(false); }}
            >
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{session.title}</span>
              <span className="muted" style={{ fontSize: 10 }}>{session.status}</span>
            </button>
          ))}
        </div>
      ) : null}

      <div className="assistant-body" ref={bodyRef}>
        {/* What the assistant is looking at, stated before anything is asked.
            This is the difference between a chat box and a copilot: the reader
            can see which page, which trade, and which book the answer will be
            about, instead of having to describe it in the prompt. */}
        <div className="copilot-head assistant-target-bar">
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
            <strong style={{ fontSize: 12 }}>AI 复盘副驾</strong>
            <span className="muted" style={{ fontSize: 11 }}>
              {busy ? '正在分析' : '已就绪'}
            </span>
          </div>
          <div className="muted copilot-context" style={{ fontSize: 11 }}>
            正在分析：{contextLabel(context)}
          </div>
          <div className="muted copilot-context" style={{ fontSize: 11 }}>
            {contextSummary(context, events.length, sessions.length)}
          </div>
          <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action.label}
                className="chip chip-action assistant-quick-chip"
                disabled={busy || Boolean(unavailable)}
                title={action.prompt}
                onClick={() => void send(action.prompt)}
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
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
            return renderStep({
              key: event.event_id,
              name: String(event.payload.name || ''),
              title: event.payload.title ? String(event.payload.title) : undefined,
              summary: result?.payload.step_summary ? String(result.payload.step_summary) : undefined,
              status: result?.payload.status ? String(result.payload.status) : undefined,
              durationMs: typeof result?.payload.duration_ms === 'number' ? result.payload.duration_ms : undefined,
              arguments: event.payload.arguments,
              result: result?.payload.result,
              state: result ? 'done' : 'unknown',
            });
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
            {/* The live stream renders the same step row as the restored
                transcript: one line a reader can scan, with the payload one
                click away. */}
            <ol className="steps">
              {turn.toolCalls.map((call) => renderStep({
                key: call.callId,
                name: call.name,
                title: call.title,
                summary: call.summary,
                status: call.status,
                durationMs: call.durationMs,
                arguments: call.arguments,
                result: call.result,
                state: call.result === undefined ? 'running' : 'done',
              }))}
              {busy ? (
                <li className="step running">
                  <span className="step-dot" />
                  <span className="step-body">
                    <span className="step-title">{currentAction || '正在分析本地证据'}</span>
                    <span className="muted">可随时停止</span>
                  </span>
                </li>
              ) : null}
            </ol>
            {turn.text ? <div className="bubble assistant"><Markdown text={turn.text} /></div> : null}
            {turn.error ? <div className="bubble error">{turn.error}</div> : null}
          </>
        ) : null}
        {liveArtifacts.map((artifact, index) => renderArtifact(artifact, 'live-' + index))}
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
          {/* One line for the seat, one control for sending. The picker stays
              available behind this chip: a trader changing models mid-review is
              a real thing to do, and hiding the control entirely would force a
              trip to settings for it. What is gone is the picker as a permanent
              third of the composer. */}
          <details className="assistant-seat">
            <summary className="assistant-model-chip" title="模型与推理强度">
              {seatLabel || '未配置模型'}
            </summary>
            <div className="assistant-seat-body">
              <ModelPicker
                providers={providers}
                selection={selection}
                onSelect={(next) => void applySelection(next)}
              />
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                默认模型保存在设置页；这里的改动只影响当前会话。
              </div>
            </div>
          </details>
          <label className="assistant-agent-select" title={agentLabels.available}>
            <span className="sr-only">复盘 Agent</span>
            <select
              value={reviewAgentId || ''}
              disabled={Boolean(unavailable) || busy}
              onChange={(event) => setReviewAgentId(event.target.value || null)}
            >
              <option value="">{agentLabels.builtIn}</option>
              {usableReviewAgents.map((agent) => <option key={agent.agent_id} value={agent.agent_id}>{agent.display_name} · {agentLabels.available}</option>)}
            </select>
          </label>
          <div className="row" style={{ gap: 8, marginLeft: 'auto' }}>
            {busy ? (
              <button className="ghost" onClick={stop}>停止</button>
            ) : (
              <button className="primary" onClick={() => void send()} disabled={!input.trim() || Boolean(unavailable) || !hasRoutableModel}>发送</button>
            )}
          </div>
        </div>
        <div className="muted" style={{ fontSize: 10.5, lineHeight: 1.6 }}>
          原文只在本机解析 · 外发字段已脱敏
        </div>
      </div>
    </aside>
  );
}
