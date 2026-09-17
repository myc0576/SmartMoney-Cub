import { useEffect, useState } from 'react';
import { api } from '../api';
import type {
  AuditRecord, CatalogEntry, KeyStatus, Meta, ModelEntry, ProviderView, ProtocolOption, ReasoningEffort,
} from '../types';
import { Badge, Panel } from '../components/common';
import { effortLabel } from '../components/ModelPicker';
import { PluginsView } from './PluginsView';

// Settings -> 模型 Providers, rebuilt against DSH's Settings -> Models page.
//
// Three rules carry most of the behaviour here:
//
//   1. A provider is one compact row, and only one row is expanded at a time.
//      Drafts live above the rows, so collapsing a card puts the typed values
//      away instead of discarding them, and closing one card never disturbs
//      another one's draft.
//   2. The key dot states only what is confirmed: green when a key is
//      configured, red when a named reference is confirmed missing, and no dot
//      at all when we cannot tell. "Cannot tell" must never read as "broken".
//   3. Discovery never writes. It is asked against the endpoint as currently
//      typed in the form, and its answer opens a chooser whose confirm only
//      fills the draft - the card's own 保存 is the single write.

const KEY_STATUS_LABELS: Record<KeyStatus, string> = {
  configured: '密钥已配置',
  missing: '缺少密钥',
  unknown: '密钥状态未知',
};

const PROVIDER_ID_HINT = '必须以小写字母开头，只能包含小写字母、数字和连字符，长度 2-40。';
const PROVIDER_ID_RE = /^[a-z][a-z0-9-]{1,39}$/;
const CAPACITY_HINT = '可填整数，或带 K / M 后缀（例如 128K、1M）。留空表示不设置。';

/** The dot state, resolved from what the server actually told us. */
function keyStatusOf(provider: ProviderView): KeyStatus {
  if (provider.key_status) return provider.key_status;
  // A provider that reports a stored key has one; anything else stays unknown
  // rather than being presented as a failure.
  return provider.has_key ? 'configured' : 'unknown';
}

function keyDotClass(status: KeyStatus): string {
  return 'key-dot ' + (status === 'configured' ? 'ok' : status === 'missing' ? 'error' : 'unknown');
}

/** What the dot means in words. It names the kind of storage, never a variable. */
function keyStatusNote(provider: ProviderView): string {
  const status = keyStatusOf(provider);
  if (status === 'configured') {
    return provider.key_source === 'environment'
      ? '密钥：已配置（来自启动环境）'
      : '密钥：已配置（保存在本机凭据文件）';
  }
  if (status === 'missing') return '密钥：尚未配置';
  return '密钥：状态未知，界面不做判断';
}

/** How many catalog rows were never confirmed against the live endpoint. */
function unverifiedCount(provider: ProviderView): number {
  return (provider.models || []).filter((model) => model.stale || model.verified === false).length;
}

/**
 * Read a capacity the way DSH's editor does: an integer, optionally with a
 * decimal K or M suffix (256K, 1.5M; K counts 1000). An empty box means "unset"
 * rather than zero, so clearing it drops the value instead of storing one the
 * schema would refuse.
 */
function parseCapacity(text: string): { ok: boolean; value?: number } {
  const raw = text.trim();
  if (!raw) return { ok: true };
  const cleaned = raw.split(' ').join('').split('_').join('');
  const match = /^([0-9]+([.][0-9]+)?)([kKmM]?)$/.exec(cleaned);
  if (!match) return { ok: false };
  const suffix = match[3].toLowerCase();
  const scale = suffix === 'k' ? 1000 : suffix === 'm' ? 1000000 : 1;
  const value = Number(match[1]) * scale;
  if (!Number.isFinite(value) || value <= 0 || !Number.isInteger(value)) return { ok: false };
  return { ok: true, value };
}

/** The shortest form that reads back as the same number: 256K, 1.5M, 8192. */
function formatCapacity(value: number | undefined): string {
  if (!value || value <= 0) return '';
  if (value >= 1000000 && value % 100000 === 0) return String(value / 1000000) + 'M';
  if (value >= 1000 && value % 100 === 0) return String(value / 1000) + 'K';
  return String(value);
}

/**
 * The one place a typed key is judged, before either a save or a probe. A key
 * is never echoed back, so a message may only say what is wrong with it - never
 * repeat it. A rejected key blocks the probe too, so the page does not spend a
 * round trip to learn what the field already said.
 */
function keyProblem(value: string, hasKey: boolean): string {
  if (value === '') return '';
  const raw = value.trim();
  if (!raw) {
    return '密钥只包含空白。留空表示'
      + (hasKey ? '不修改已保存的密钥' : '改用其他鉴权方式')
      + '；要替换密钥请粘贴完整内容。';
  }
  if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(raw)) {
    return '看起来粘贴了整行的 NAME=value 环境变量。请只粘贴等号右边的密钥本身。';
  }
  if (!/^[!-~]+$/.test(raw)) {
    return '密钥含空格或非 ASCII 字符，HTTP 请求头无法承载。请只粘贴密钥本身。';
  }
  return '';
}

/** Model ids pasted by hand: one per line, or comma separated. */
function parseIdList(text: string): string[] {
  const parts: string[] = [];
  for (const chunk of text.split(',')) {
    for (const line of chunk.split('\n')) {
      const id = line.trim();
      if (id) parts.push(id);
    }
  }
  return Array.from(new Set(parts));
}

/**
 * One editable model row. Capacity is held as typed text so a value like 256K
 * survives a keystroke; it is parsed once, on save.
 */
interface ModelRow {
  id: string;
  label: string;
  contextWindow: string;
  maxTokens: string;
  reasoning_efforts: string[];
  default_effort: string;
  effort_details?: ReasoningEffort[];
  description: string;
  stale: boolean;
  verified?: boolean;
  open: boolean;
}

interface ProviderDraft {
  name: string;
  key: string;
  clearKey: boolean;
  baseUrl: string;
  protocol: string;
  models: ModelRow[];
  advancedOpen: boolean;
}

interface CustomDraft {
  providerId: string;
  name: string;
  baseUrl: string;
  protocol: string;
  key: string;
  models: ModelRow[];
}

function blankModelRow(): ModelRow {
  return {
    id: '',
    label: '',
    contextWindow: '',
    maxTokens: '',
    reasoning_efforts: [],
    default_effort: 'off',
    description: '',
    stale: false,
    open: false,
  };
}

function modelRowOf(model: ModelEntry): ModelRow {
  return {
    id: model.id,
    label: model.label || '',
    contextWindow: formatCapacity(model.context_window),
    maxTokens: formatCapacity(model.max_tokens),
    reasoning_efforts: model.reasoning_efforts || [],
    default_effort: model.default_effort || 'off',
    effort_details: model.effort_details,
    description: model.description || '',
    stale: Boolean(model.stale),
    verified: model.verified,
    open: false,
  };
}

function blankCustomDraft(): CustomDraft {
  return { providerId: '', name: '', baseUrl: '', protocol: '', key: '', models: [] };
}

/** The draft a row's editor starts from, before anything is typed. */
function draftOf(provider: ProviderView): ProviderDraft {
  return {
    name: provider.label,
    key: '',
    clearKey: false,
    baseUrl: provider.base_url || '',
    protocol: provider.protocol || 'openai-chat',
    models: (provider.models || []).map(modelRowOf),
    advancedOpen: false,
  };
}

/**
 * Read the model rows the way the store will.
 *
 * Rows that were never touched are skipped rather than failing the save, but a
 * row with content and no id, a duplicate id, or an unreadable capacity is
 * refused before the request is sent, so the failure names the field while the
 * user is still looking at it.
 */
function buildModels(rows: ModelRow[]): { models?: Record<string, unknown>[]; problem?: string } {
  const built: Record<string, unknown>[] = [];
  const seen = new Set<string>();
  for (const [index, row] of rows.entries()) {
    const id = row.id.trim();
    if (!id) {
      const touched = row.label.trim() !== '' || row.contextWindow.trim() !== '' || row.maxTokens.trim() !== '';
      if (!touched) continue;
      return { problem: '第 ' + (index + 1) + ' 行有内容但缺少模型 id。' };
    }
    if (seen.has(id)) return { problem: '模型 id 重复：' + id + '。' };
    seen.add(id);
    const context = parseCapacity(row.contextWindow);
    if (!context.ok) return { problem: '「' + id + '」的上下文窗口无法识别。' + CAPACITY_HINT };
    const maxTokens = parseCapacity(row.maxTokens);
    if (!maxTokens.ok) return { problem: '「' + id + '」的最大输出 token 无法识别。' + CAPACITY_HINT };
    const entry: Record<string, unknown> = {
      id,
      label: row.label.trim() || id,
      reasoning_efforts: row.reasoning_efforts,
      default_effort: row.default_effort,
    };
    if (context.value) entry.context_window = context.value;
    if (maxTokens.value) entry.max_tokens = maxTokens.value;
    if (row.description) entry.description = row.description;
    built.push(entry);
  }
  return { models: built };
}

/** The same shape, built from the stored rows, so a save can tell if they moved. */
function serverModels(provider: ProviderView): Record<string, unknown>[] {
  return (provider.models || []).map((model) => {
    const entry: Record<string, unknown> = {
      id: model.id,
      label: model.label || model.id,
      reasoning_efforts: model.reasoning_efforts || [],
      default_effort: model.default_effort || 'off',
    };
    if (model.context_window) entry.context_window = model.context_window;
    if (model.max_tokens) entry.max_tokens = model.max_tokens;
    if (model.description) entry.description = model.description;
    return entry;
  });
}

export function SettingsView({
  meta,
  onMetaChange,
  scheme,
  theme,
  onToggleScheme,
  onToggleTheme,
}: {
  meta: Meta | null;
  onMetaChange: () => void;
  scheme?: 'cn' | 'intl';
  theme?: 'light' | 'dark';
  onToggleScheme?: () => void;
  onToggleTheme?: () => void;
}) {
  const [providers, setProviders] = useState<ProviderView[]>([]);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [protocols, setProtocols] = useState<ProtocolOption[]>([]);
  const [defaults, setDefaults] = useState<{ provider_id: string; model: string; reasoning: string }>({ provider_id: '', model: '', reasoning: 'off' });
  const [audits, setAudits] = useState<AuditRecord[]>([]);
  const [doctor, setDoctor] = useState<Record<string, any> | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  // Each family of card keeps its own open state, so opening the add card does
  // not close the row being edited, and vice versa.
  const [openProvider, setOpenProvider] = useState<string | null>(null);
  const [addMode, setAddMode] = useState<'catalog' | 'custom' | null>(null);
  // Drafts outlive the cards they belong to.
  const [drafts, setDrafts] = useState<Record<string, ProviderDraft>>({});
  const [catalogKey, setCatalogKey] = useState('');
  const [custom, setCustom] = useState<CustomDraft>(blankCustomDraft);
  const [activeSection, setActiveSection] = useState<'general' | 'models' | 'plugins' | 'agent' | 'privacy'>('models');
  const [agentPresets, setAgentPresets] = useState<{ system_prompt: string; default_effort: string; context_strategy: string }>({
    system_prompt: '',
    default_effort: 'medium',
    context_strategy: 'summary_compact',
  });
  const [openingFile, setOpeningFile] = useState(false);

  const load = async (): Promise<ProviderView[]> => {
    const settings = await api.settings();
    // The legacy offline provider remains readable for migration, but is not
    // presented as a selectable model. A missing key should surface as setup
    // guidance, never as a fake local answer route.
    const next = ((settings.providers as ProviderView[]) || []).filter(
      (provider) => provider.provider_id !== 'offline',
    );
    setProviders(next);
    setCatalog((settings.catalog as CatalogEntry[]) || []);
    setProtocols((settings.protocols as ProtocolOption[]) || []);
    setDefaults(settings.defaults || { provider_id: '', model: '', reasoning: 'off' });
    if (settings.agent_presets) {
      setAgentPresets({
        system_prompt: settings.agent_presets.system_prompt || '',
        default_effort: settings.agent_presets.default_effort || 'medium',
        context_strategy: settings.agent_presets.context_strategy || 'summary_compact',
      });
    }
    setAudits((await api.audit()).audits);
    setDoctor(await api.doctor());
    return next;
  };

  const fail = (caught: unknown) => {
    setStatus('');
    setError(caught instanceof Error ? caught.message : String(caught));
  };

  const notice = (message: string) => {
    setError('');
    setStatus(message);
  };

  const refresh = async (): Promise<ProviderView[]> => {
    const next = await load();
    onMetaChange();
    return next;
  };

  useEffect(() => {
    void load().catch(fail);
    // The page reads once on mount; every later read follows an action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setDefault = async (providerId: string, model: string) => {
    try {
      await api.updateSettings({ default_provider_id: providerId, default_model: model });
      notice('默认对话模型已切换为 ' + providerId + ' · ' + model);
      await refresh();
    } catch (caught) { fail(caught); }
  };

  const openEditor = (provider: ProviderView) => {
    setDrafts((prev) => (
      prev[provider.provider_id] ? prev : { ...prev, [provider.provider_id]: draftOf(provider) }
    ));
    setOpenProvider(provider.provider_id);
    setError('');
  };

  const patchDraft = (provider: ProviderView, patch: Partial<ProviderDraft>) => {
    setDrafts((prev) => {
      const base = prev[provider.provider_id] || draftOf(provider);
      return { ...prev, [provider.provider_id]: { ...base, ...patch } };
    });
  };

  /**
   * A save re-reads the store and then rebuilds the draft from what came back,
   * so the card shows stored values rather than the values it just sent. The
   * advanced section stays open, because a user editing capacities is usually
   * still editing them.
   */
  const saved = async (providerId: string, message: string) => {
    const keepAdvanced = (drafts[providerId] || { advancedOpen: false }).advancedOpen;
    const fresh = await refresh();
    const updated = fresh.find((provider) => provider.provider_id === providerId);
    setDrafts((prev) => {
      const next = { ...prev };
      if (updated) next[providerId] = { ...draftOf(updated), advancedOpen: keepAdvanced };
      else delete next[providerId];
      return next;
    });
    notice(message);
  };

  const removeProvider = async (provider: ProviderView) => {
    if (!confirm('确认删除 Provider「' + provider.label + '」（' + provider.provider_id + '）吗？保存在本机的密钥也会一并删除。')) return;
    try {
      await api.removeProvider(provider.provider_id);
      if (openProvider === provider.provider_id) setOpenProvider(null);
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[provider.provider_id];
        return next;
      });
      await refresh();
      notice('已删除「' + provider.label + '」。');
    } catch (caught) { fail(caught); }
  };

  const addFromCatalog = async (entry: CatalogEntry) => {
    try {
      await api.addProvider({
        provider_id: entry.provider_id,
        from_catalog: true,
        api_key: catalogKey.trim() || undefined,
      });
      setCatalogKey('');
      setAddMode(null);
      await refresh();
      notice('已添加「' + entry.label + '」。填好密钥后即可使用。');
    } catch (caught) { fail(caught); }
  };

  const createCustom = async (payload: Record<string, unknown>, label: string) => {
    try {
      await api.addProvider(payload);
      setCustom(blankCustomDraft());
      setAddMode(null);
      await refresh();
      notice('已添加自定义 Provider「' + label + '」。');
    } catch (caught) { fail(caught); }
  };

  const handleOpenFile = async () => {
    setOpeningFile(true);
    try {
      const res = await api.openConfigFile();
      if (res.status === 'ok') {
        notice('已在默认文本编辑器中打开配置文件：' + (res.path || ''));
      } else {
        fail(res.error || '无法打开配置文件');
      }
    } catch (caught) {
      fail(caught);
    } finally {
      setOpeningFile(false);
    }
  };

  const saveAgentPresets = async () => {
    try {
      await api.updateSettings({ agent_presets: agentPresets });
      notice('Agent 预设已保存');
      await refresh();
    } catch (caught) {
      fail(caught);
    }
  };

  return (
    <div className="dsh-settings-container">
      {/* Top action header: aligned with DSH Settings modal header */}
      <div className="dsh-settings-topbar">
        <div>
          <h2 className="dsh-settings-heading">设置</h2>
          <span className="muted" style={{ fontSize: 12 }}>
            配置模型提供方、Agent 预设、外观与系统选项
          </span>
        </div>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <button
            className="dsh-open-config-btn"
            onClick={() => void handleOpenFile()}
            disabled={openingFile}
            title="学习 DSH 交互：在本地文本编辑器中直接打开配置文件"
          >
            <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ marginRight: 6 }}>
              <path d="M2 4a1 1 0 0 1 1-1h4l2 2h4a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V4z" />
            </svg>
            {openingFile ? '正在打开...' : '打开配置文件'}
          </button>
        </div>
      </div>

      {status ? <div className="notice" role="status" style={{ borderLeftColor: 'var(--color-accent)', marginBottom: 12 }}>{status}</div> : null}
      {error ? <div className="notice" role="alert" style={{ borderLeftColor: 'var(--neg)', marginBottom: 12 }}>{error}</div> : null}

      <div className="dsh-settings-layout">
        {/* Left Vertical Sub-Navigation: DSH Architecture */}
        <nav className="dsh-settings-sidebar">
          <button
            className={'dsh-nav-tab' + (activeSection === 'general' ? ' active' : '')}
            onClick={() => { setActiveSection('general'); setError(''); }}
          >
            <span>通用设置</span>
          </button>

          <button
            className={'dsh-nav-tab' + (activeSection === 'models' ? ' active' : '')}
            onClick={() => { setActiveSection('models'); setError(''); }}
          >
            <span>模型</span>
            <span className="dsh-tab-badge">{providers.length}</span>
          </button>

          <button
            className={'dsh-nav-tab' + (activeSection === 'plugins' ? ' active' : '')}
            onClick={() => { setActiveSection('plugins'); setError(''); }}
          >
            <span>插件</span>
          </button>

          <button
            className={'dsh-nav-tab' + (activeSection === 'agent' ? ' active' : '')}
            onClick={() => { setActiveSection('agent'); setError(''); }}
          >
            <span>Agent 预设</span>
          </button>

          <button
            className={'dsh-nav-tab' + (activeSection === 'privacy' ? ' active' : '')}
            onClick={() => { setActiveSection('privacy'); setError(''); }}
          >
            <span>隐私与诊断</span>
          </button>
        </nav>

        {/* Right Content Panel */}
        <div className="dsh-settings-content">
          {/* 1. 通用设置 */}
          {activeSection === 'general' ? (
            <Panel title="通用设置">
              <div className="grid" style={{ gap: 16 }}>
                <div className="provider-form">
                  <div className="field">
                    <label>涨跌配色显示</label>
                    <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                      <button
                        className={scheme === 'cn' ? 'primary' : 'ghost'}
                        onClick={onToggleScheme}
                      >
                        红涨绿跌（国内惯例）
                      </button>
                      <button
                        className={scheme === 'intl' ? 'primary' : 'ghost'}
                        onClick={onToggleScheme}
                      >
                        绿涨红跌（国际惯例）
                      </button>
                    </div>
                  </div>

                  <div className="field">
                    <label>界面色彩主题</label>
                    <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                      <button
                        className={theme === 'dark' ? 'primary' : 'ghost'}
                        onClick={onToggleTheme}
                      >
                        深色模式 (Dark)
                      </button>
                      <button
                        className={theme === 'light' ? 'primary' : 'ghost'}
                        onClick={onToggleTheme}
                      >
                        浅色模式 (Light)
                      </button>
                    </div>
                  </div>
                </div>

                <div className="stage-row" style={{ marginTop: 8 }}>
                  <div style={{ fontWeight: 500, marginBottom: 6 }}>单账本与离线持久化机制</div>
                  <div className="muted" style={{ fontSize: 12, lineHeight: 1.6 }}>
                    SmartMoney-Cub 遵循单人本地优先原则，所有交易记录、回放行情与复盘会话均离线存储在本地 SQLite 数据库中，不向任何中心化服务器回传明细。
                  </div>
                  <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                    安全合约声明：<code>READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE</code>
                  </div>
                </div>
              </div>
            </Panel>
          ) : null}

          {/* 2. 模型设置 */}
          {activeSection === 'models' ? (
            <Panel title={'模型提供方（' + providers.length + '）'}>
              <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
                填入各提供方的 API 密钥即可使用其模型。密钥只写入本机凭据文件，界面绝不回显。
              </div>

              <div className="grid" style={{ gap: 10 }}>
                {providers.map((provider) => (
                  openProvider === provider.provider_id ? (
                    <ProviderEditCard
                      key={provider.provider_id}
                      provider={provider}
                      draft={drafts[provider.provider_id] || draftOf(provider)}
                      defaults={defaults}
                      protocols={protocols}
                      isDefault={defaults.provider_id === provider.provider_id}
                      onPatch={(patch) => patchDraft(provider, patch)}
                      onClose={() => setOpenProvider(null)}
                      onDelete={() => void removeProvider(provider)}
                      onSaved={(msg) => saved(provider.provider_id, msg)}
                      onSetDefault={setDefault}
                      onFail={fail}
                      onNotice={notice}
                    />
                  ) : (
                    <ProviderRow
                      key={provider.provider_id}
                      provider={provider}
                      isDefault={defaults.provider_id === provider.provider_id}
                      onEdit={() => openEditor(provider)}
                      onDelete={() => void removeProvider(provider)}
                    />
                  )
                ))}
                {providers.length === 0 ? (
                  <div className="muted">还没有配置任何 Provider。用下面的按钮从内置目录添加，或手工声明自定义路由。</div>
                ) : null}
              </div>

              {addMode === 'catalog' ? (
                <div style={{ marginTop: 10 }}>
                  <CatalogAddCard
                    catalog={catalog}
                    installed={providers.map((p) => p.provider_id)}
                    apiKey={catalogKey}
                    onApiKey={setCatalogKey}
                    onClose={() => setAddMode(null)}
                    onAdd={(entry) => void addFromCatalog(entry)}
                  />
                </div>
              ) : null}

              {addMode === 'custom' ? (
                <div style={{ marginTop: 10 }}>
                  <CustomAddCard
                    providers={providers}
                    protocols={protocols}
                    draft={custom}
                    onChange={(patch) => setCustom((prev) => ({ ...prev, ...patch }))}
                    onClose={() => setAddMode(null)}
                    onCreate={(payload, label) => void createCustom(payload, label)}
                    onFail={fail}
                  />
                </div>
              ) : null}

              {addMode === null ? (
                <div className="add-row" style={{ marginTop: 12 }}>
                  <button className="add-card" onClick={() => { setAddMode('catalog'); setError(''); }}>+ 添加提供方</button>
                  <button className="add-card" onClick={() => { setAddMode('custom'); setError(''); }}>+ 添加自定义提供方</button>
                </div>
              ) : null}
            </Panel>
          ) : null}

          {/* 3. 插件设置 */}
          {activeSection === 'plugins' ? (
            <PluginsView />
          ) : null}

          {/* 4. Agent 预设 */}
          {activeSection === 'agent' ? (
            <Panel title="复盘助手 Agent 预设">
              <div className="grid" style={{ gap: 16 }}>
                <div className="muted" style={{ fontSize: 12 }}>
                  自定义复盘助手的思考偏好与系统指令。此处的设定会在创建新复盘会话时自动注入。
                </div>

                <div className="provider-form">
                  <div className="field">
                    <label>默认推理思考强度</label>
                    <select
                      value={agentPresets.default_effort}
                      onChange={(e) => setAgentPresets((prev) => ({ ...prev, default_effort: e.target.value }))}
                    >
                      <option value="off">不思考（直接作答）</option>
                      <option value="low">低推理（轻量推理）</option>
                      <option value="medium">中等推理（均衡主力）</option>
                      <option value="high">高推理（深入归因）</option>
                      <option value="max">最大推理（极限推理）</option>
                    </select>
                  </div>

                  <div className="field">
                    <label>上下文压缩策略</label>
                    <select
                      value={agentPresets.context_strategy}
                      onChange={(e) => setAgentPresets((prev) => ({ ...prev, context_strategy: e.target.value }))}
                    >
                      <option value="summary_compact">结构化摘要压缩 (默认)</option>
                      <option value="full_recent">仅保留最近轮次全文</option>
                    </select>
                  </div>
                </div>

                <div className="field">
                  <label>系统提示词定制要求 (Agent Prompt)</label>
                  <textarea
                    style={{ minHeight: 120, fontFamily: 'inherit', fontSize: 13, lineHeight: 1.5 }}
                    placeholder="在此输入您期望复盘助手始终遵守的分析风格或特定要求（例如：注重盈亏比分析，严格指出执行计划外交易的错误...）"
                    value={agentPresets.system_prompt}
                    onChange={(e) => setAgentPresets((prev) => ({ ...prev, system_prompt: e.target.value }))}
                  />
                  <div className="row" style={{ justifyContent: 'space-between', marginTop: 4 }}>
                    <span className="muted" style={{ fontSize: 11 }}>
                      字符数：{agentPresets.system_prompt.length}
                    </span>
                    <button
                      className="ghost"
                      style={{ fontSize: 11 }}
                      onClick={() => setAgentPresets((prev) => ({ ...prev, system_prompt: '' }))}
                    >
                      清空定制要求
                    </button>
                  </div>
                </div>

                <div>
                  <button className="primary" onClick={() => void saveAgentPresets()}>
                    保存 Agent 预设
                  </button>
                </div>
              </div>
            </Panel>
          ) : null}

          {/* 5. 隐私与诊断 */}
          {activeSection === 'privacy' ? (
            <div className="grid" style={{ gap: 14 }}>
              <Panel title="隐私与脱敏">
                <div className="grid" style={{ gap: 8 }}>
                  <div>外发策略：<strong>{meta?.redaction_policy || 'redaction.v1'}</strong></div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    发送给模型的字段在离开本机前会被替换：账号与姓名变成别名，证券代码与组合名变成设备内稳定的哈希别名，
                    精确数量与金额变成区间，精确时间变成 15 分钟时段。截图、PDF、CSV 原文永远不进入网络请求。
                  </div>
                  <div className="row" style={{ marginTop: 6 }}>
                    <span>本地识别引擎：</span>
                    {meta?.engine?.rapidocr ? <Badge kind="ok">已安装</Badge> : <Badge kind="warn">未安装</Badge>}
                    <span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>
                      截图与扫描 PDF 需要它：pip install "smartmoney-cub-harness[ocr]"
                    </span>
                  </div>
                </div>
              </Panel>

              <Panel title={'外发审计（最近 ' + audits.length + ' 条）'}>
                {audits.length === 0 ? (
                  <div className="muted">还没有向外部模型发送过请求。未配置可路由模型时，助手会停在设置引导，不会发起请求。</div>
                ) : (
                  <div className="scroll-x">
                    <table>
                      <thead><tr><th>时间</th><th>Provider</th><th>模型</th><th>字段数</th><th>脱敏</th><th>结果</th></tr></thead>
                      <tbody>
                        {audits.map((audit) => (
                          <tr key={audit.audit_id}>
                            <td className="muted">{audit.created_at}</td>
                            <td>{audit.provider_id}</td>
                            <td className="muted">{audit.model || '—'}</td>
                            <td className="num">{audit.sent_keys.length}</td>
                            <td className="muted">{String(audit.redaction_summary?.total ?? 0)} 处替换</td>
                            <td>{audit.blocked ? <Badge kind="error">已阻断</Badge> : <Badge kind="ok">已发送</Badge>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Panel>

              <Panel title="本地系统诊断">
                {doctor ? (
                  <table>
                    <thead><tr><th>检查项</th><th>状态</th><th>说明</th></tr></thead>
                    <tbody>
                      {((doctor.checks as { name: string; status: string; detail: string }[] | undefined) || []).map((check) => (
                        <tr key={check.name}>
                          <td>{check.name}</td>
                          <td>
                            {check.status === 'ok' ? (
                              <Badge kind="ok">正常</Badge>
                            ) : check.status === 'warn' ? (
                              <Badge kind="warn">提示</Badge>
                            ) : (
                              <Badge kind="error">异常</Badge>
                            )}
                          </td>
                          <td className="muted">{check.detail}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="muted">未能读取诊断信息。</div>
                )}
              </Panel>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ProviderRow({ provider, isDefault, onEdit, onDelete }: {
  provider: ProviderView;
  isDefault: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const status = keyStatusOf(provider);
  const unverified = unverifiedCount(provider);
  return (
    <div className="provider-row">
      <div className="provider-row-main">
        <span className={keyDotClass(status)} title={KEY_STATUS_LABELS[status]} aria-label={KEY_STATUS_LABELS[status]} />
        <span className="provider-row-name">{provider.label}</span>
        <span className="muted" style={{ fontSize: 11 }}>{provider.provider_id}</span>
        {isDefault ? <span className="tag accent">当前默认</span> : null}
        {provider.is_custom ? <span className="tag">自定义</span> : null}
        {provider.protocol === 'offline' ? <span className="tag">离线</span> : null}
        {provider.protocol !== 'offline' && !provider.base_url ? <span className="tag">未设置端点</span> : null}
        {unverified > 0 ? <span className="tag warn">{unverified} 个模型未校验</span> : null}
        {provider.models_error ? <span className="tag warn" title={provider.models_error}>上次目录查询失败</span> : null}
      </div>
      <div className="provider-row-actions">
        <button className="ghost" onClick={onEdit}>编辑</button>
        {provider.removable ? <button className="ghost danger" onClick={onDelete}>删除</button> : null}
      </div>
    </div>
  );
}

/** The expanded editor for one row: the row is replaced, not duplicated. */
function ProviderEditCard({
  provider, draft, defaults, protocols, isDefault, onPatch, onClose, onDelete, onSaved, onSetDefault, onFail, onNotice,
}: {
  provider: ProviderView;
  draft: ProviderDraft;
  defaults: { provider_id: string; model: string; reasoning: string };
  protocols: ProtocolOption[];
  isDefault: boolean;
  onPatch: (patch: Partial<ProviderDraft>) => void;
  onClose: () => void;
  onDelete: () => void;
  onSaved: (message: string) => Promise<void>;
  onSetDefault: (providerId: string, model: string) => Promise<void>;
  onFail: (value: unknown) => void;
  onNotice: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [probing, setProbing] = useState(false);
  const [picking, setPicking] = useState(false);
  const [checking, setChecking] = useState(false);
  const offline = provider.protocol === 'offline';
  const status = keyStatusOf(provider);
  const keyMessage = keyProblem(draft.key, provider.has_key);
  const protocolOptions: ProtocolOption[] = protocols.length > 0
    ? protocols
    : [{ id: provider.protocol, label: provider.protocol_label || provider.protocol }];

  const save = async () => {
    const problem = keyMessage || buildModels(draft.models).problem;
    if (problem) { onFail(problem); return; }
    const models = buildModels(draft.models).models || [];
    // Send the model list only when it actually moved. The store normalizes
    // whatever it is handed, so an untouched list is left alone rather than
    // round-tripped through a normalizer that does not carry every field.
    const changed = JSON.stringify(models) !== JSON.stringify(serverModels(provider));
    setBusy(true);
    try {
      await api.updateProvider(provider.provider_id, {
        display_name: draft.name.trim() || provider.label,
        base_url: offline ? undefined : draft.baseUrl.trim(),
        protocol: offline ? undefined : draft.protocol,
        ...(changed ? { models } : {}),
        api_key: draft.key.trim() || undefined,
        clear_key: draft.clearKey,
      });
      await onSaved('已保存「' + provider.label + '」。密钥只写入本机凭据文件，界面不会回显。');
    } catch (caught) {
      onFail(caught);
    } finally {
      setBusy(false);
    }
  };

  const probe = async () => {
    if (keyMessage) { onFail(keyMessage); return; }
    setProbing(true);
    onNotice('');
    try {
      const result = await api.testProvider({
        provider_id: provider.provider_id,
        base_url: draft.baseUrl.trim() || undefined,
        protocol: draft.protocol,
      });
      if (result.status === 'ok') {
        const found = (result.models as string[] | undefined) || [];
        onNotice('「' + provider.label + '」连接成功'
          + (found.length ? '，端点公布 ' + found.length + ' 个模型。' : '。'));
      } else {
        onFail('「' + provider.label + '」连接失败：' + (result.error || '未知原因'));
      }
    } catch (caught) {
      onFail(caught);
    } finally {
      setProbing(false);
    }
  };

  /**
   * Reconcile the saved model list against what the endpoint actually serves.
   *
   * This is the action that answers "is this list still the latest": it asks the
   * endpoint, marks anything withdrawn as 已下架, and appends what is new. It is
   * deliberately separate from 获取可用模型, which only offers candidates for
   * the user to pick - this one reports the truth about what we already ship.
   */
  const checkModels = async () => {
    setChecking(true);
    onNotice('');
    try {
      const result = await api.checkModels(provider.provider_id);
      if (result.error) {
        // A failed lookup is a failed lookup. It must not be reported as "every
        // model is gone", because an outage teaches us nothing.
        onFail('查询失败，模型目录保持原样：' + result.error);
        return;
      }
      const added = Number(result.added_count || 0);
      const stale = Number(result.stale_count || 0);
      const parts: string[] = [];
      if (added > 0) parts.push('新发现 ' + added + ' 个');
      if (stale > 0) parts.push('已下架 ' + stale + ' 个（保留，可继续使用）');
      // Re-read the store so the card shows the reconciled list it just wrote,
      // and let the save path own the notice so the two cannot disagree.
      await onSaved(
        '「' + provider.label + '」模型目录已校验'
          + (parts.length ? '：' + parts.join('，') + '。' : '，没有变化。'),
      );
    } catch (caught) {
      onFail(caught);
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="provider-card">
      <div className="provider-head">
        <div>
          <span className="provider-title">{draft.name.trim() || provider.label}</span>
          <span className="provider-id">{provider.provider_id}</span>
        </div>
        <div className="row">
          <span className={keyDotClass(status)} title={KEY_STATUS_LABELS[status]} aria-label={KEY_STATUS_LABELS[status]} />
          <span className="tag">{KEY_STATUS_LABELS[status]}</span>
          {provider.is_custom ? <span className="tag">自定义</span> : null}
          {isDefault ? <span className="tag accent">当前默认</span> : null}
        </div>
      </div>
      <div className="provider-meta">{provider.description}</div>
      {provider.incomplete ? (
        <div className="notice" style={{ marginBottom: 8 }}>这个 Provider 还缺少必要的配置，补全后即可使用。</div>
      ) : null}

      <div className="provider-form">
        <div className="field">
          <label>显示名称</label>
          <input
            style={{ width: 200 }}
            value={draft.name}
            placeholder={provider.provider_id}
            onChange={(event) => onPatch({ name: event.target.value })}
          />
        </div>
        <div className="field">
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <label style={{ margin: 0 }}>API 密钥（只写，不会回显）</label>
            {(provider.portal_url || provider.provider_id === 'alphatech') ? (
              <a
                href={provider.portal_url || 'https://alphatech.net.cn'}
                target="_blank"
                rel="noreferrer"
                className="dsh-get-key-link"
                title="打开官方控制台注册并创建 API 密钥"
              >
                <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ marginRight: 4 }}>
                  <circle cx="5" cy="11" r="3" />
                  <path d="M7 9l7-7M12 2l2 2M10 4l2 2" />
                </svg>
                获取 {provider.label} 密钥 ↗
              </a>
            ) : null}
          </div>
          <input
            type="password"
            autoComplete="off"
            style={{ width: 240 }}
            value={draft.key}
            placeholder={provider.has_key
              ? '已保存（留空表示不修改）'
              : (provider.requires_key ? '粘贴密钥' : '留空则沿用其他鉴权方式')}
            onChange={(event) => onPatch({ key: event.target.value, clearKey: false })}
          />
        </div>
      </div>
      <div className="provider-meta">
        {keyStatusNote(provider)}{draft.clearKey ? ' · 保存后会清除已保存的密钥' : ''}
      </div>
      {keyMessage ? <div className="notice">{keyMessage}</div> : null}

      <div className="provider-form">
        <button className="primary" onClick={() => void save()} disabled={busy}>{busy ? '保存中…' : '保存'}</button>
        {offline ? null : (
          <button
            className="ghost"
            onClick={() => void probe()}
            disabled={probing || Boolean(keyMessage)}
            title={keyMessage || '用当前表单里的地址与密钥测一次连接'}
          >
            {probing ? '测试中…' : '测试连接'}
          </button>
        )}
        {provider.has_key && !draft.clearKey ? (
          <button className="ghost" onClick={() => onPatch({ clearKey: true, key: '' })}>清除密钥</button>
        ) : null}
        {draft.clearKey ? (
          <button className="ghost" onClick={() => onPatch({ clearKey: false })}>撤销清除</button>
        ) : null}
        <button className="ghost" onClick={onClose}>收起</button>
        {provider.removable ? (
          <span className="provider-row-actions">
            <button className="ghost danger" onClick={onDelete}>删除</button>
          </span>
        ) : null}
      </div>

      <div className="row" style={{ justifyContent: 'space-between', marginTop: 12 }}>
        <span className="muted" style={{ fontSize: 11 }}>
          模型目录（{draft.models.length}）· 点模型可设为默认对话模型
          {provider.models_checked_at ? ' · 上次校验 ' + String(provider.models_checked_at).slice(0, 16).replace('T', ' ') : ''}
        </span>
        {offline ? null : (
          <div className="row" style={{ gap: 6 }}>
            <button
              className="ghost"
              disabled={Boolean(keyMessage) || checking}
              title={keyMessage || '向端点核对已保存的模型，标出已下架并补上新增的模型'}
              onClick={() => void checkModels()}
            >
              {checking ? '校验中…' : '校验模型目录'}
            </button>
            <button
              className="ghost"
              disabled={Boolean(keyMessage)}
              title={keyMessage || '向当前表单里的端点查询可用模型'}
              onClick={() => setPicking(true)}
            >
              获取可用模型
            </button>
          </div>
        )}
      </div>
      {draft.models.length === 0 ? (
        <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
          这个 Provider 还没有模型。用「获取可用模型」查询端点，或在下面的「自定义设置」里手工填 id。
        </div>
      ) : null}
      <div className="model-chips">
        {draft.models.map((row, index) => {
          const id = row.id.trim();
          const active = defaults.provider_id === provider.provider_id && defaults.model === id;
          return (
            <button
              key={index}
              className={'model-chip' + (active ? ' active' : '')}
              disabled={!id}
              title={active ? '当前默认对话模型' : '设为默认对话模型'}
              onClick={() => { if (id) void onSetDefault(provider.provider_id, id); }}
            >
              {row.label.trim() || id || '（未命名）'}
              {row.reasoning_efforts.length > 1
                ? <span className="effort"> {effortLabel(row.default_effort)}</span>
                : null}
              {row.stale
                ? <span className="tag warn" style={{ marginLeft: 5 }}>已下架</span>
                : (row.verified === false ? <span className="tag" style={{ marginLeft: 5 }}>未校验</span> : null)}
            </button>
          );
        })}
      </div>
      {provider.models_error ? (
        <div className="notice" style={{ marginTop: 8 }}>
          上次向这个端点查询模型失败：{provider.models_error}。模型仍可手工维护。
        </div>
      ) : null}

      <button
        className="collapse-head"
        aria-expanded={draft.advancedOpen}
        onClick={() => onPatch({ advancedOpen: !draft.advancedOpen })}
      >
        <span>{draft.advancedOpen ? '▾' : '▸'}</span>
        <span>自定义设置</span>
        <span className="muted">Base URL · API 协议 · 模型目录</span>
      </button>
      {draft.advancedOpen ? (
        <div>
          {offline ? (
            <div className="provider-meta">本地 Provider 不需要地址与协议，也不会发出任何网络请求。</div>
          ) : (
            <div className="provider-form">
              <div className="field">
                <label>Base URL</label>
                <input
                  style={{ width: 300 }}
                  value={draft.baseUrl}
                  placeholder="https://gateway.example/v1"
                  onChange={(event) => onPatch({ baseUrl: event.target.value })}
                />
              </div>
              <div className="field">
                <label>API 协议</label>
                <select value={draft.protocol} onChange={(event) => onPatch({ protocol: event.target.value })}>
                  {protocolOptions.map((item) => (
                    <option key={item.id} value={item.id}>{item.label}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
          <ModelRowsEditor rows={draft.models} onChange={(models) => onPatch({ models })} />
        </div>
      ) : null}

      {picking ? (
        <DiscoverModal
          providerId={provider.provider_id}
          baseUrl={draft.baseUrl.trim()}
          protocol={draft.protocol}
          apiKey={draft.key.trim()}
          existingIds={draft.models.map((row) => row.id.trim()).filter(Boolean)}
          onClose={() => setPicking(false)}
          onApply={(added) => {
            onPatch({ models: [...draft.models, ...added.map(modelRowOf)] });
            setPicking(false);
            onNotice('已把 ' + added.length + ' 个模型加入草稿。点「保存」之后才会写入。');
          }}
        />
      ) : null}
    </div>
  );
}

/**
 * The model catalog, one row per model: id on the left, display name beside it,
 * capacities tucked into that row's own expander, and a delete action per row.
 */
function ModelRowsEditor({ rows, onChange }: { rows: ModelRow[]; onChange: (rows: ModelRow[]) => void }) {
  const patch = (index: number, next: Partial<ModelRow>) => {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...next } : row)));
  };

  return (
    <div style={{ marginTop: 6 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="muted" style={{ fontSize: 11 }}>
          模型目录（{rows.length}）· 一行一个模型
        </span>
        <button className="ghost" onClick={() => onChange([...rows, blankModelRow()])}>+ 添加模型行</button>
      </div>
      {rows.length === 0 ? (
        <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
          还没有模型行。空目录表示沿用这个 Provider 自带的模型列表。
        </div>
      ) : null}
      {rows.map((row, index) => {
        const context = parseCapacity(row.contextWindow);
        const maxTokens = parseCapacity(row.maxTokens);
        return (
          <div key={index}>
            <div className="model-line">
              <input
                className="grow"
                value={row.id}
                placeholder="模型 id"
                onChange={(event) => patch(index, { id: event.target.value })}
              />
              <input
                className="grow"
                value={row.label}
                placeholder={row.id.trim() || '显示名称'}
                onChange={(event) => patch(index, { label: event.target.value })}
              />
              <span className="model-row-tags">
                {row.stale ? <span className="tag warn">已下架</span> : null}
                {!row.stale && row.verified === false ? <span className="tag">未校验</span> : null}
              </span>
              <button
                className="collapse-head"
                style={{ width: 'auto' }}
                aria-expanded={row.open}
                onClick={() => patch(index, { open: !row.open })}
              >
                {row.open ? '▾ 容量' : '▸ 容量'}
              </button>
              <span className="provider-row-actions">
                <button
                  className="ghost danger"
                  title="删除这一行"
                  onClick={() => onChange(rows.filter((_, i) => i !== index))}
                >
                  删除
                </button>
              </span>
            </div>
            {row.open ? (
              <div className="provider-form" style={{ marginTop: 2, alignItems: 'flex-start' }}>
                <div className="field">
                  <label>上下文窗口{context.ok ? '' : '（无法识别）'}</label>
                  <input
                    style={{ width: 150 }}
                    value={row.contextWindow}
                    placeholder="例如 128K"
                    onChange={(event) => patch(index, { contextWindow: event.target.value })}
                  />
                  {context.ok ? null : <span className="tag warn">无法识别</span>}
                </div>
                <div className="field">
                  <label>最大输出 token{maxTokens.ok ? '' : '（无法识别）'}</label>
                  <input
                    style={{ width: 150 }}
                    value={row.maxTokens}
                    placeholder="例如 8K"
                    onChange={(event) => patch(index, { maxTokens: event.target.value })}
                  />
                  {maxTokens.ok ? null : <span className="tag warn">无法识别</span>}
                </div>
                <span className="muted" style={{ fontSize: 10.5 }}>{CAPACITY_HINT}</span>
                {/* Read-only, deliberately: the levels a model accepts are a
                    property of that model, so there is no provider-wide control
                    that could not be wrong for some of its models. */}
                {row.effort_details && row.effort_details.length > 0 ? (
                  <div className="field" style={{ width: '100%' }}>
                    <label>这个模型声明的推理强度</label>
                    <div className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
                      {row.effort_details.map((effort) => (
                        <div className="effort-row" style={{ display: 'flex' }} key={effort.level}>
                          <span className="effort-name">
                            {effort.label}{effort.level === row.default_effort ? ' · 默认' : ''}
                          </span>
                          {effort.description ? <span className="effort-desc">{effort.description}</span> : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/**
 * The model chooser.
 *
 * It asks the endpoint as currently typed in the form - including a base URL
 * and a key that have not been saved - and the answer is only ever offered.
 * Candidates already in the catalog start unchecked and cannot be re-added, so
 * adopting a selection can never overwrite a capacity the user corrected.
 */
function DiscoverModal({
  providerId, baseUrl, protocol, apiKey, existingIds, onClose, onApply,
}: {
  providerId: string;
  baseUrl: string;
  protocol: string;
  apiKey: string;
  existingIds: string[];
  onClose: () => void;
  onApply: (added: ModelEntry[]) => void;
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [available, setAvailable] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [manual, setManual] = useState('');

  const known = new Set(existingIds);

  const run = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api.discoverModels({
        provider_id: providerId || undefined,
        base_url: baseUrl || undefined,
        protocol,
        api_key: apiKey || undefined,
      });
      setAvailable((result.models || []).filter((id) => Boolean(id)));
    } catch (caught) {
      // An endpoint that refuses to be asked is a detour, not a dead end: the
      // adapter's own message is shown beside the rows, and ids can still be
      // typed in below.
      setAvailable([]);
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void run();
    // Asked once for the form values captured when the chooser opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const candidates = Array.from(new Set([...available, ...parseIdList(manual)]));
  const selectable = candidates.filter((id) => !known.has(id));
  const chosen = selectable.filter((id) => selected.has(id));

  const toggle = (id: string, on: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected(selectable.every((id) => selected.has(id)) ? new Set<string>() : new Set(selectable));
  };

  const apply = () => {
    // Nothing is written here. The chosen ids go back to the card as draft
    // rows, and the card's 保存 is what reaches the store.
    onApply(chosen.map((id) => ({
      id,
      label: id,
      reasoning_efforts: [],
      default_effort: 'off',
      verified: false,
    })));
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <h3>选择要添加的模型</h3>
        <div className="hint">
          这里是端点对当前表单里的地址与密钥的回应。勾选只会加入卡片草稿，点卡片上的「保存」之后才会写入设置。
          已经在目录里的候选默认不勾选。
        </div>
        <div className="row" style={{ marginBottom: 8 }}>
          <button className="ghost" onClick={toggleAll} disabled={selectable.length === 0}>全选 / 取消全选</button>
          <button className="ghost" onClick={() => void run()} disabled={loading}>{loading ? '获取中…' : '重新获取'}</button>
          <span className="muted" style={{ fontSize: 11 }}>已选 {chosen.length} 个</span>
        </div>
        {loading ? <div className="muted" style={{ marginBottom: 8 }}>正在向当前表单里的端点查询模型…</div> : null}
        {error ? (
          <div className="notice" style={{ marginBottom: 8 }}>
            端点没有回应可用模型：{error}。仍可在下面手工填写模型 id。
          </div>
        ) : null}
        <div className="checklist">
          {!loading && candidates.length === 0 ? (
            <div className="muted" style={{ padding: 10 }}>
              {error ? '等待手工填写模型 id。' : '端点没有公布任何模型。'}
            </div>
          ) : null}
          {candidates.map((id) => {
            const configured = known.has(id);
            return (
              <div className="checklist-row" key={id}>
                <input
                  type="checkbox"
                  checked={selected.has(id)}
                  disabled={configured}
                  onChange={(event) => toggle(id, event.target.checked)}
                />
                <label>{id}</label>
                {configured ? <span className="tag">已配置</span> : null}
              </div>
            );
          })}
        </div>
        <div className="field" style={{ marginTop: 10 }}>
          <label>手工添加模型 id（每行一个，或逗号分隔）</label>
          <textarea
            value={manual}
            placeholder="deepseek-v3"
            onChange={(event) => setManual(event.target.value)}
          />
        </div>
        <div className="modal-actions">
          <button className="ghost" onClick={onClose}>取消</button>
          <button className="primary" onClick={apply} disabled={chosen.length === 0}>添加所选</button>
        </div>
      </div>
    </div>
  );
}

/** The catalog side of the add flow: pick a shipped provider, key optional. */
function CatalogAddCard({ catalog, installed, apiKey, onApiKey, onClose, onAdd }: {
  catalog: CatalogEntry[];
  installed: string[];
  apiKey: string;
  onApiKey: (value: string) => void;
  onClose: () => void;
  onAdd: (entry: CatalogEntry) => void;
}) {
  const known = new Set(installed);
  return (
    <div className="provider-card">
      <div className="provider-head">
        <div>
          <span className="provider-title">添加提供方</span>
          <span className="provider-id">来自内置目录</span>
        </div>
        {known.size > 0 ? <span className="tag">已安装 {known.size} 个</span> : null}
      </div>
      <div className="provider-meta">
        选择一个内置 Provider，它会带上端点、协议和模型列表。密钥只写入本机凭据文件，界面不会回显，也可以之后在行里再填。
      </div>
      <div className="provider-form">
        <div className="field">
          <label>API 密钥（可选，只写）</label>
          <input
            type="password"
            autoComplete="off"
            style={{ width: 240 }}
            value={apiKey}
            placeholder="粘贴密钥（也可以稍后再填）"
            onChange={(event) => onApiKey(event.target.value)}
          />
        </div>
      </div>
      <div className="checklist" style={{ marginTop: 10 }}>
        {catalog.map((entry) => (
          <div className="checklist-row" key={entry.provider_id}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="row" style={{ gap: 6, alignItems: 'center' }}>
                <span>{entry.label}</span>
                <span className="muted" style={{ fontSize: 11 }}>{entry.provider_id}</span>
                {(entry.portal_url || entry.provider_id === 'alphatech') ? (
                  <a
                    href={entry.portal_url || 'https://alphatech.net.cn'}
                    target="_blank"
                    rel="noreferrer"
                    className="dsh-get-key-link"
                    style={{ fontSize: 11, padding: '1px 6px' }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    获取密钥 ↗
                  </a>
                ) : null}
                {entry.has_env_key ? <span className="tag">已检测到启动环境里的密钥</span> : null}
              </div>
              <div className="muted" style={{ fontSize: 11 }}>
                {entry.protocol_label} · {entry.models.length} 个模型
              </div>
            </div>
            <button
              className="ghost"
              disabled={known.has(entry.provider_id)}
              onClick={() => onAdd(entry)}
            >
              {known.has(entry.provider_id) ? '已添加' : '添加'}
            </button>
          </div>
        ))}
        {catalog.length === 0 ? <div className="muted" style={{ padding: 10 }}>内置目录是空的。</div> : null}
      </div>
      <div className="provider-form">
        <button className="ghost" onClick={onClose}>取消</button>
      </div>
    </div>
  );
}

/**
 * The other add flow: declare a route the catalog does not ship.
 *
 * It is a card of its own rather than fields on an editor, because the route id
 * is chosen here and no settings address exists before that choice. The create
 * button stays enabled and names whatever is missing, so the failure points at
 * the field while the user is still looking at it.
 */
function CustomAddCard({ providers, protocols, draft, onChange, onClose, onCreate, onFail }: {
  providers: ProviderView[];
  protocols: ProtocolOption[];
  draft: CustomDraft;
  onChange: (patch: Partial<CustomDraft>) => void;
  onClose: () => void;
  onCreate: (payload: Record<string, unknown>, label: string) => void;
  onFail: (value: unknown) => void;
}) {
  const [picking, setPicking] = useState(false);
  const id = draft.providerId.trim();
  const idShapeOk = PROVIDER_ID_RE.test(id);
  const taken = providers.some((provider) => provider.provider_id === id);
  const protocol = draft.protocol || protocols[0]?.id || 'openai-chat';
  const ids = draft.models.map((row) => row.id.trim()).filter(Boolean);
  const duplicateIds = ids.length !== new Set(ids).size;
  const capacitiesOk = draft.models.every(
    (row) => parseCapacity(row.contextWindow).ok && parseCapacity(row.maxTokens).ok,
  );
  const keyMessage = keyProblem(draft.key, false);

  const missing: string[] = [];
  if (!id) missing.push('Provider ID');
  else if (!idShapeOk) missing.push('格式正确的 Provider ID');
  else if (taken) missing.push('尚未被占用的 Provider ID');
  if (!draft.baseUrl.trim()) missing.push('Base URL');
  if (keyMessage) missing.push('没问题的 API 密钥');
  else if (!draft.key.trim()) missing.push('API 密钥（留空则沿用其他鉴权方式）');
  if (ids.length === 0) missing.push('至少一个模型 id');
  if (duplicateIds) missing.push('不重复的模型 id');
  if (!capacitiesOk) missing.push('可识别的容量数字');

  const create = () => {
    if (!id) { onFail('请先填 Provider ID。'); return; }
    if (!idShapeOk) { onFail('Provider ID 不对：' + PROVIDER_ID_HINT); return; }
    if (taken) { onFail('Provider ID「' + id + '」已经被占用。'); return; }
    if (!draft.baseUrl.trim()) { onFail('请填 Base URL。'); return; }
    if (keyMessage) { onFail(keyMessage); return; }
    const checked = buildModels(draft.models);
    if (checked.problem) { onFail(checked.problem); return; }
    const models = checked.models || [];
    if (models.length === 0) { onFail('请至少填一个模型 id，或先用「获取可用模型」查询端点。'); return; }
    onCreate({
      provider_id: id,
      from_catalog: false,
      display_name: draft.name.trim() || id,
      base_url: draft.baseUrl.trim(),
      protocol,
      api_key: draft.key.trim() || undefined,
      models,
    }, draft.name.trim() || id);
  };

  return (
    <div className="provider-card">
      <div className="provider-head">
        <div>
          <span className="provider-title">添加自定义提供方</span>
          <span className="provider-id">目录里没有的路由</span>
        </div>
        <span className="tag">自定义</span>
      </div>
      <div className="provider-meta">
        用于公司中转站、自建服务或目录里没有的网关。Provider ID 会成为本地设置里的键，创建后不改名。
      </div>
      <div className="provider-form">
        <div className="field">
          <label>Provider ID</label>
          <input
            style={{ width: 180 }}
            value={draft.providerId}
            placeholder="my-gateway"
            onChange={(event) => onChange({ providerId: event.target.value })}
          />
        </div>
        <div className="field">
          <label>显示名称（可留空，默认用 id）</label>
          <input
            style={{ width: 180 }}
            value={draft.name}
            placeholder={id || '公司中转站'}
            onChange={(event) => onChange({ name: event.target.value })}
          />
        </div>
        <div className="field">
          <label>API 密钥（只写）</label>
          <input
            type="password"
            autoComplete="off"
            style={{ width: 200 }}
            value={draft.key}
            placeholder="留空则沿用其他鉴权方式"
            onChange={(event) => onChange({ key: event.target.value })}
          />
        </div>
      </div>
      {id && !idShapeOk ? <div className="notice">Provider ID 不对：{PROVIDER_ID_HINT}</div> : null}
      {taken ? <div className="notice">Provider ID「{id}」已经被占用。</div> : null}
      {keyMessage ? <div className="notice">{keyMessage}</div> : null}
      <div className="provider-form">
        <div className="field">
          <label>Base URL</label>
          <input
            style={{ width: 300 }}
            value={draft.baseUrl}
            placeholder="https://gateway.example/v1"
            onChange={(event) => onChange({ baseUrl: event.target.value })}
          />
        </div>
        <div className="field">
          <label>API 协议</label>
          <select value={protocol} onChange={(event) => onChange({ protocol: event.target.value })}>
            {protocols.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="row" style={{ justifyContent: 'space-between', marginTop: 10 }}>
        <span className="muted" style={{ fontSize: 11 }}>模型至少要有一个 id，它决定这个路由提供什么</span>
        <button
          className="ghost"
          disabled={Boolean(keyMessage) || !draft.baseUrl.trim()}
          title={keyMessage || '向当前表单里的端点查询可用模型'}
          onClick={() => setPicking(true)}
        >
          获取可用模型
        </button>
      </div>
      <ModelRowsEditor rows={draft.models} onChange={(models) => onChange({ models })} />
      <div className="provider-form">
        <button className="primary" onClick={create}>创建</button>
        <button className="ghost" onClick={onClose}>取消</button>
        {missing.length > 0
          ? <span className="muted" style={{ fontSize: 11 }}>还差：{missing.join('、')}</span>
          : null}
      </div>

      {picking ? (
        <DiscoverModal
          providerId=""
          baseUrl={draft.baseUrl.trim()}
          protocol={protocol}
          apiKey={draft.key.trim()}
          existingIds={ids}
          onClose={() => setPicking(false)}
          onApply={(added) => {
            onChange({ models: [...draft.models, ...added.map(modelRowOf)] });
            setPicking(false);
          }}
        />
      ) : null}
    </div>
  );
}
