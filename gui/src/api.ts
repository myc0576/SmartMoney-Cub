import type {
  JevConnection, AgentActionResponse, AgentsResponse, BenchmarkLatestResponse, JevStatusResponse, JevTracksResponse,
  AuditRecord, Extraction, Meta, Overview, RuleRecord,
  SessionEvent, SessionSummary, UploadResult,
  PluginCatalogResponse, PluginDetailResponse,
  BacktestRunDetail, BacktestRuns, MarketBars, MarketProviders, Playbook,
  Playbooks, ReplaySession, TraderAccounts, TraderBreakdown, TraderBreakdownMap,
  TraderCalendar, TradeLogDetail, TraderHealth, TraderImportResult, TraderMeta,
  TraderSummaryEnvelope, TraderTrades,
} from './types';

// Every call goes to the local service on 127.0.0.1. There is no telemetry and
// no third-party endpoint anywhere in this file.
//
// Why the API base is derived rather than written as a bare '/api': a hosted
// deployment publishes the product under a path prefix (nginx maps
// /trader/ to the app). A request for the absolute '/api/trader/health' leaves
// that prefix, matches the proxy's default location, and 404s — the interface
// would load its shell and then fail every call. Resolving against the current
// document instead keeps the calls inside whatever prefix the app was served
// under, and still resolves to '/api/...' when the app is served at the root
// (the local single-user case), so both deployments work from one build.

function apiUrl(path: string): string {
  const base = document.baseURI || window.location.href;
  return new URL(path.replace(/^\//, ''), base).toString();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  const text = await response.text();
  let payload: any = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(text.slice(0, 300) || 'invalid response');
  }
  if (!response.ok) {
    throw new Error(payload?.error || 'request failed: ' + response.status);
  }
  return payload as T;
}

// The trader product lives under /api/trader/* on the same local service, so
// one process serves the review workbench and the journal. The route list is
// frozen by the backend task; the calls below mirror it one-for-one.
export const trader = {
  health: () => request<TraderHealth>('/api/trader/health'),
  meta: () => request<TraderMeta>('/api/trader/meta'),

  marketProviders: () => request<MarketProviders>('/api/trader/market/providers'),
  marketBars: (params: {
    provider: string; symbol: string; interval: string;
    start?: string; end?: string; limit?: number;
  }) => request<MarketBars>('/api/trader/market/bars?' + new URLSearchParams(clean(params)).toString()),

  trades: (params: {
    account_id?: string; symbol?: string; from?: string; to?: string;
    limit?: number; offset?: number;
  } = {}) => request<TraderTrades>('/api/trader/trades?' + new URLSearchParams(clean(params)).toString()),
  trade: (roundTripId: string) =>
    request<TradeLogDetail>('/api/trader/trades/' + encodeURIComponent(roundTripId)),
  /** Writes fills into the tenant journal. Send rows, or raw CSV text. */
  importTrades: (payload: {
    rows?: Array<Record<string, unknown>>;
    content?: string;
    format?: string;
    account_id?: string;
  }) => request<TraderImportResult>('/api/trader/trades/import', {
    method: 'POST', body: JSON.stringify(payload),
  }),

  accounts: () => request<TraderAccounts>('/api/trader/accounts'),
  createAccount: (payload: {
    name: string; broker?: string; currency?: string; initial_balance?: number;
  }) => request<{ account: TraderAccounts['accounts'][number]; safety: string }>('/api/trader/accounts', {
    method: 'POST', body: JSON.stringify(payload),
  }),

  // The summary route nests its metrics under `summary`, beside the ledger
  // counts and status. Unwrapping here keeps a caller reading the metrics
  // directly, and the counts ride along on the returned object so the shell can
  // report how many executions the journal holds without a second request.
  summary: (params: { from?: string; to?: string; account_id?: string } = {}) =>
    request<TraderSummaryEnvelope>('/api/trader/analytics/summary?' + new URLSearchParams(clean(params)).toString())
      .then((envelope) => ({ ...envelope.summary, counts: envelope.counts })),
  breakdown: (params: { dimension: string; from?: string; to?: string }) =>
    request<TraderBreakdown>('/api/trader/analytics/breakdown?' + new URLSearchParams(clean(params)).toString()),
  // An unnamed dimension asks the same route for every group at once, which is
  // the shape the grouping view renders. The named form above stays for the
  // callers that want one dimension.
  // The refresh flag asks the server to reconcile symbol names against the live
  // quote feed before grouping, which is how a rename or an ST change lands.
  breakdownAll: (params: { from?: string; to?: string; refresh?: string } = {}) =>
    request<TraderBreakdownMap>('/api/trader/analytics/breakdown?' + new URLSearchParams(clean(params)).toString()),
  calendar: (params: { year: number; month: number }) =>
    request<TraderCalendar>('/api/trader/calendar?' + new URLSearchParams(clean(params)).toString()),

  playbooks: () => request<Playbooks>('/api/trader/playbooks'),
  createPlaybook: (payload: Partial<Playbook> & { name: string }) =>
    request<{ playbook: Playbook; safety: string }>('/api/trader/playbooks', {
      method: 'POST', body: JSON.stringify(payload),
    }),

  runBacktest: (payload: { strategy: Record<string, unknown>; provider?: string; symbol?: string; interval?: string;
    start?: string; end?: string; initial_cash?: number; fees_bps?: number }) =>
    request<BacktestRunDetail>('/api/trader/backtest/run', { method: 'POST', body: JSON.stringify(payload) }),
  backtestRuns: () => request<BacktestRuns>('/api/trader/backtest/runs'),
  backtestRun: (runId: string) =>
    request<BacktestRunDetail>('/api/trader/backtest/runs/' + encodeURIComponent(runId)),

  createReplaySession: (payload: { provider: string; symbol: string; interval: string;
    start?: string; end?: string; limit?: number; notes?: string }) =>
    request<ReplaySession>('/api/trader/replay/sessions', { method: 'POST', body: JSON.stringify(payload) }),
  replaySession: (sessionId: string) =>
    request<ReplaySession>('/api/trader/replay/sessions/' + encodeURIComponent(sessionId)),
};

export const api = {
  meta: () => request<Meta>('/api/meta'),
  overview: (params: { portfolio_id?: string; year?: number; month?: number } = {}) =>
    request<Overview>('/api/overview?' + new URLSearchParams(clean(params)).toString()),
  rules: () => request<{ rules: RuleRecord[] }>('/api/rules'),
  // Promotion is the one rule-library write, and it is deliberately a separate
  // call with an explicit note: the server refuses a champion row without a
  // written human confirmation, so the note is not an optional field here.
  promoteRule: (ruleId: string, note: string) =>
    // The response carries the promoted rule in the same shape as one entry of
    // the list, so the view can render it without a second fetch.
    request<{ rule: RuleRecord; promotion_note: string; safety: string }>(
      '/api/rules/' + encodeURIComponent(ruleId) + '/promote',
      { method: 'POST', body: JSON.stringify({ note }) },
    ),
  plugins: () => request<Record<string, any>>('/api/plugins'),
  pluginMarket: () => request<Record<string, any>>('/api/plugins/market'),
  installMarketPlugin: (pluginId: string, config: Record<string, unknown> = {}) =>
    request<Record<string, any>>('/api/plugins/market/' + encodeURIComponent(pluginId) + '/install', {
      method: 'POST', body: JSON.stringify({ config }),
    }),
  updateMarketPlugin: (pluginId: string, confirm = false) =>
    request<Record<string, any>>('/api/plugins/market/' + encodeURIComponent(pluginId) + '/update', {
      method: 'POST', body: JSON.stringify({ confirm }),
    }),
  setMarketPluginEnabled: (pluginId: string, enabled: boolean) =>
    request<Record<string, any>>('/api/plugins/market/' + encodeURIComponent(pluginId) + '/' + (enabled ? 'enable' : 'disable'), {
      method: 'POST', body: JSON.stringify({ enabled }),
    }),
  enablePlugin: (pluginId: string) =>
    request<{ status: string; plugin: any; safety: string }>('/api/plugins/enable', {
      method: 'POST', body: JSON.stringify({ plugin_id: pluginId }),
    }),
  disablePlugin: (pluginId: string) =>
    request<{ status: string; plugin: any; safety: string }>('/api/plugins/disable', {
      method: 'POST', body: JSON.stringify({ plugin_id: pluginId }),
    }),
  pluginCatalog: () => request<PluginCatalogResponse>('/api/plugins/catalog'),
  pluginDetail: (pluginId: string) =>
    request<PluginDetailResponse>('/api/plugins/detail?plugin_id=' + encodeURIComponent(pluginId)),
  configurePlugin: (pluginId: string, config: Record<string, any>) =>
    request<{ status: string; config: Record<string, any>; safety: string }>('/api/plugins/configure', {
      method: 'POST', body: JSON.stringify({ plugin_id: pluginId, config }),
    }),
  reloadPlugins: () =>
    request<{ status: string; safety: string }>('/api/plugins/reload', {
      method: 'POST', body: JSON.stringify({}),
    }),
  openConfigFile: () =>
    request<{ status: string; path?: string; error?: string; safety: string }>('/api/settings/open-file', {
      method: 'POST', body: JSON.stringify({}),
    }),
  documents: (params: { portfolio_id?: string } = {}) =>
    request<{ documents: Overview['recent_documents'] }>('/api/documents?' + new URLSearchParams(clean(params)).toString()),
  settings: () => request<Record<string, any>>('/api/settings'),
  updateSettings: (payload: Record<string, unknown>) =>
    request<Record<string, any>>('/api/settings', { method: 'POST', body: JSON.stringify(payload) }),
  addProvider: (payload: Record<string, unknown>) =>
    request<Record<string, any>>('/api/settings/providers', { method: 'POST', body: JSON.stringify(payload) }),
  updateProvider: (providerId: string, payload: Record<string, unknown>) =>
    request<Record<string, any>>('/api/settings/providers/' + encodeURIComponent(providerId), {
      method: 'POST', body: JSON.stringify(payload),
    }),
  removeProvider: (providerId: string) =>
    request<Record<string, any>>('/api/settings/providers/' + encodeURIComponent(providerId) + '/remove', {
      method: 'POST', body: JSON.stringify({}),
    }),
  discoverModels: (payload: Record<string, unknown>) =>
    request<{ models: string[] }>('/api/settings/discover', { method: 'POST', body: JSON.stringify(payload) }),
  // Reconcile the declared model list against the live endpoint. Answers "is
  // this model list still true?" without ever deleting a configured model.
  checkModels: (providerId: string, payload: Record<string, unknown> = {}) =>
    request<Record<string, any>>(
      '/api/settings/providers/' + encodeURIComponent(providerId) + '/check-models',
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  testProvider: (payload: Record<string, unknown>) =>
    request<Record<string, any>>('/api/settings/test', { method: 'POST', body: JSON.stringify(payload) }),
  audit: (limit = 50) => request<{ audits: AuditRecord[] }>('/api/audit?limit=' + limit),
  doctor: () => request<Record<string, any>>('/api/doctor'),
  governance: () => request<Record<string, any>>('/api/governance'),
  requestStrategyPromotion: (strategyId: string) =>
    request<Record<string, any>>('/api/governance/strategies/' + encodeURIComponent(strategyId) + '/promote', {
      method: 'POST', body: JSON.stringify({}),
    }),
  confirmStrategyPromotion: (promotionId: string, note: string) =>
    request<Record<string, any>>('/api/governance/promotions/' + encodeURIComponent(promotionId) + '/confirm', {
      method: 'POST', body: JSON.stringify({ note }),
    }),

  upload: (payload: { file_name: string; media_type: string; content_base64: string; portfolio_id?: string }) =>
    request<UploadResult>('/api/import/upload', { method: 'POST', body: JSON.stringify(payload) }),
  commitImport: (payload: Record<string, unknown>) =>
    request<Record<string, any>>('/api/import/commit', { method: 'POST', body: JSON.stringify(payload) }),
  addManualFill: (payload: Record<string, unknown>) =>
    request<Record<string, any>>('/api/import/manual', { method: 'POST', body: JSON.stringify(payload) }),

  sessions: () => request<{ sessions: SessionSummary[] }>('/api/assistant/sessions'),
  createSession: (payload: Record<string, unknown>, signal?: AbortSignal) =>
    request<{ session: SessionSummary }>('/api/assistant/sessions', { method: 'POST', body: JSON.stringify(payload), signal }),
  sessionDetail: (id: string, afterSeq = 0) =>
    request<{ session: SessionSummary; events: SessionEvent[] }>(
      '/api/assistant/sessions/' + encodeURIComponent(id) + '?after_seq=' + afterSeq,
    ),
  updateSession: (id: string, payload: Record<string, unknown>) =>
    request<{ session: SessionSummary }>('/api/assistant/sessions/' + encodeURIComponent(id), {
      method: 'POST', body: JSON.stringify(payload),
    }),
  forkSession: (id: string, payload: Record<string, unknown> = {}) =>
    request<{ session: SessionSummary }>('/api/assistant/sessions/' + encodeURIComponent(id) + '/fork', {
      method: 'POST', body: JSON.stringify(payload),
    }),
  reviewScope: (id: string) =>
    request<import('./types').ReviewScopeResponse>(
      '/api/assistant/sessions/' + encodeURIComponent(id) + '/review/scope',
    ),
  confirmReviewScope: (id: string, payload: Record<string, unknown> = {}) =>
    request<import('./types').ReviewScopeResponse & { session: SessionSummary }>(
      '/api/assistant/sessions/' + encodeURIComponent(id) + '/review/confirm',
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  recordReviewPackage: (id: string, payload: Record<string, unknown>) =>
    request<Record<string, any>>(
      '/api/assistant/sessions/' + encodeURIComponent(id) + '/review/package',
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  jevConnection: () => request<JevConnection>('/api/settings/jev'),
  saveJevConnection: (payload: { api_key?: string; clear_key?: boolean }) =>
    request<JevConnection>('/api/settings/jev', { method: 'POST', body: JSON.stringify(payload) }),
  testJevConnection: () => request<JevConnection>('/api/settings/jev/test', { method: 'POST', body: '{}' }),
  jevStatus: () => request<JevStatusResponse>('/api/jev/status'),
  jevTracks: () => request<JevTracksResponse>('/api/jev/tracks'),
  agents: () => request<AgentsResponse>('/api/agents'),
  agentApply: (agentId: string, dryRun = false) =>
    request<AgentActionResponse>('/api/agents/apply', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId, dry_run: dryRun }),
    }),
  agentDisable: (agentId: string) =>
    request<AgentActionResponse>('/api/agents/disable', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId }),
    }),
  agentRestore: (agentId: string) =>
    request<AgentActionResponse>('/api/agents/restore', {
      method: 'POST',
      body: JSON.stringify({ agent_id: agentId }),
    }),
  benchmarkLatest: () => request<BenchmarkLatestResponse>('/api/benchmark/latest'),

  cancelTurn: (id: string, signal?: AbortSignal) =>
    request<{ status: string; session: SessionSummary }>(
      '/api/assistant/sessions/' + encodeURIComponent(id) + '/cancel',
      { method: 'POST', body: JSON.stringify({}), signal },
    ),
  resumeTurn: (id: string, text = '', handlers?: StreamHandlers) =>
    handlers
      ? streamResume(id, text, handlers)
      : Promise.reject(new Error('resume handlers are required')),
};

function clean(params: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') out[key] = String(value);
  }
  return out;
}

export interface StreamHandlers {
  onEvent: (event: Record<string, any>) => void;
  onError: (message: string) => void;
  onDone: () => void;
  signal?: AbortSignal;
}

// The assistant turn is a server-sent event stream. The same events are stored
// locally, so a dropped stream can be recovered by reloading the session.
export async function streamTurn(sessionId: string, text: string, handlers: StreamHandlers): Promise<void> {
  return streamRequest(sessionId, 'messages', text, handlers);
}

export async function streamResume(sessionId: string, text: string, handlers: StreamHandlers): Promise<void> {
  return streamRequest(sessionId, 'resume', text, handlers);
}

/** onDone finalizes the transport on every path; only a server `done` event
 * means the turn succeeded. Never swallow parser errors or treat EOF as success. */
async function streamRequest(sessionId: string, action: string, text: string, handlers: StreamHandlers): Promise<void> {
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  try {
    const response = await fetch(apiUrl('/api/assistant/sessions/' + encodeURIComponent(sessionId) + '/' + action), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }), signal: handlers.signal,
    });
    if (!response.ok || !response.body) {
      throw new Error('复盘请求失败（HTTP ' + response.status + '），请检查服务后重试。');
    }
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let terminal = false;
    while (!terminal) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      // Normalize only complete CRLF sequences: a chunk may end on the CR.
      buffer = buffer.replace(/\r\n/g, '\n');
      let boundary: number;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const data = frame.split('\n').filter(line => line.startsWith('data:'))
          .map(line => line.slice(5).trimStart()).join('\n');
        if (!data) continue;
        let event: Record<string, any>;
        try { event = JSON.parse(data); }
        catch { throw new Error('复盘数据流格式异常；已保留收到的内容。'); }
        if (!event || typeof event.kind !== 'string') throw new Error('复盘数据流缺少事件类型。');
        terminal = ['done', 'error', 'cancelled'].includes(event.kind);
        handlers.onEvent(event);
        if (terminal) break;
      }
      if (buffer.length > 2 * 1024 * 1024) throw new Error('复盘数据帧过大，已停止接收。');
      if (done) {
        if (!terminal) throw new Error('连接提前结束；已保留收到的内容，请重试。');
        break;
      }
    }
  } catch (error) {
    if (!handlers.signal?.aborted) {
      handlers.onError(error instanceof Error ? error.message : String(error));
    }
  } finally {
    if (reader) {
      await reader.cancel().catch(() => undefined);
      reader.releaseLock();
    }
    handlers.onDone();
  }
}

export function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      resolve(result.slice(result.indexOf(',') + 1));
    };
    reader.onerror = () => reject(new Error('could not read the selected file'));
    reader.readAsDataURL(file);
  });
}

export type { Extraction };
