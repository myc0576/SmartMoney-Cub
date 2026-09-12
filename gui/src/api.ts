import type {
  AuditRecord, Extraction, KeyValue, Meta, Overview, RoundTrip, RuleRecord,
  SessionEvent, SessionSummary, Summary, UploadResult,
} from './types';

// Every call goes to the local service on 127.0.0.1. There is no telemetry and
// no third-party endpoint anywhere in this file.

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
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

export const api = {
  meta: () => request<Meta>('/api/meta'),
  overview: (params: { portfolio_id?: string; year?: number; month?: number } = {}) =>
    request<Overview>('/api/overview?' + new URLSearchParams(clean(params)).toString()),
  trades: (params: { portfolio_id?: string; symbol?: string; regime?: string } = {}) =>
    request<{ trades: RoundTrip[]; open_positions: Overview['open_positions']; issues: Overview['issues']; count: number }>(
      '/api/trades?' + new URLSearchParams(clean(params)).toString(),
    ),
  tradeDetail: (id: string) =>
    request<{ trade: RoundTrip; fill_revisions: Record<string, any>[] }>('/api/trades/' + encodeURIComponent(id)),
  calendar: (params: { portfolio_id?: string; year?: number; month?: number }) =>
    request<{ year: number; month: number; days: Overview['calendar'] }>(
      '/api/calendar?' + new URLSearchParams(clean(params)).toString(),
    ),
  analytics: (params: { portfolio_id?: string } = {}) =>
    request<{ summary: Summary; breakdown: Record<string, KeyValue[]>; dimensions: string[] }>(
      '/api/analytics?' + new URLSearchParams(clean(params)).toString(),
    ),
  rules: () => request<{ rules: RuleRecord[] }>('/api/rules'),
  plugins: () => request<Record<string, any>>('/api/plugins'),
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
  testProvider: (payload: Record<string, unknown>) =>
    request<Record<string, any>>('/api/settings/test', { method: 'POST', body: JSON.stringify(payload) }),
  audit: (limit = 50) => request<{ audits: AuditRecord[] }>('/api/audit?limit=' + limit),
  doctor: () => request<Record<string, any>>('/api/doctor'),

  upload: (payload: { file_name: string; media_type: string; content_base64: string; portfolio_id?: string }) =>
    request<UploadResult>('/api/import/upload', { method: 'POST', body: JSON.stringify(payload) }),
  commitImport: (payload: Record<string, unknown>) =>
    request<Record<string, any>>('/api/import/commit', { method: 'POST', body: JSON.stringify(payload) }),
  addManualFill: (payload: Record<string, unknown>) =>
    request<Record<string, any>>('/api/import/manual', { method: 'POST', body: JSON.stringify(payload) }),

  sessions: () => request<{ sessions: SessionSummary[] }>('/api/assistant/sessions'),
  createSession: (payload: Record<string, unknown>) =>
    request<{ session: SessionSummary }>('/api/assistant/sessions', { method: 'POST', body: JSON.stringify(payload) }),
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
  const response = await fetch('/api/assistant/sessions/' + encodeURIComponent(sessionId) + '/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
    signal: handlers.signal,
  });
  if (!response.ok || !response.body) {
    const detail = await response.text().catch(() => '');
    handlers.onError(detail || 'stream failed: ' + response.status);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() || '';
    for (const frame of frames) {
      const line = frame.split('\n').find((item) => item.startsWith('data:'));
      if (!line) continue;
      try {
        handlers.onEvent(JSON.parse(line.slice(5).trim()));
      } catch {
        // A partial frame is not worth failing the whole turn over.
      }
    }
  }
  handlers.onDone();
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

