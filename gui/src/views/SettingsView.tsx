import { useEffect, useState } from 'react';
import { api } from '../api';
import type { AuditRecord, CatalogEntry, Meta, ModelEntry, ProviderView, ProtocolOption } from '../types';
import { Badge, Panel } from '../components/common';
import { effortLabel } from '../components/ModelPicker';

// Settings -> 模型, following the harness layout: the installed providers each
// get a card, the catalog offers Add provider, and a custom provider form covers
// company gateways. Model ids are never typed: they are discovered from the
// endpoint and picked from a searchable list.

export function SettingsView({ meta, onMetaChange }: { meta: Meta | null; onMetaChange: () => void }) {
  const [providers, setProviders] = useState<ProviderView[]>([]);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [protocols, setProtocols] = useState<ProtocolOption[]>([]);
  const [defaults, setDefaults] = useState<{ provider_id: string; model: string; reasoning: string }>({ provider_id: '', model: '', reasoning: 'off' });
  const [audits, setAudits] = useState<AuditRecord[]>([]);
  const [doctor, setDoctor] = useState<Record<string, any> | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [adding, setAdding] = useState(false);

  const load = async () => {
    const settings = await api.settings();
    setProviders((settings.providers as ProviderView[]) || []);
    setCatalog((settings.catalog as CatalogEntry[]) || []);
    setProtocols((settings.protocols as ProtocolOption[]) || []);
    setDefaults(settings.defaults || { provider_id: '', model: '', reasoning: 'off' });
    setAudits((await api.audit()).audits);
    setDoctor(await api.doctor());
  };

  useEffect(() => { void load(); }, []);

  const refresh = async () => {
    await load();
    onMetaChange();
  };

  const fail = (caught: unknown) => {
    setError(caught instanceof Error ? caught.message : String(caught));
  };

  const setDefault = async (providerId: string, model: string) => {
    setError('');
    try {
      await api.updateSettings({ default_provider_id: providerId, default_model: model });
      setStatus('默认对话模型已切换为 ' + providerId + ' · ' + model);
      await refresh();
    } catch (caught) { fail(caught); }
  };

  return (
    <div className="grid" style={{ gap: 14 }}>
      <Panel title="隐私与脱敏">
        <div className="grid" style={{ gap: 8 }}>
          <div>外发策略：<strong>{meta?.redaction_policy || 'redaction.v1'}</strong></div>
          <div className="muted">
            发送给模型的字段在离开本机前会被替换：账号与姓名变成别名，证券代码与组合名变成设备内稳定的哈希别名，
            精确数量与金额变成区间，精确时间变成 15 分钟时段。截图、PDF、CSV 原文永远不进入请求。
          </div>
          <div className="muted">每次外发都会在本地写入一条审计记录，只记录「发送了哪些字段」和脱敏统计，不记录密钥。</div>
          <div className="row">
            <span>本地识别引擎：</span>
            {meta?.engine?.rapidocr ? <Badge kind="ok">已安装</Badge> : <Badge kind="warn">未安装</Badge>}
            <span className="muted">截图与扫描 PDF 需要它，安装命令：pip install "smartmoney-cub-harness[ocr]"</span>
          </div>
        </div>
      </Panel>

      <Panel
        title={'模型 Providers（' + providers.length + '）'}
        actions={<button className="primary" onClick={() => setAdding(true)}>添加 Provider</button>}
      >
        <div className="grid" style={{ gap: 12 }}>
          {providers.map((provider) => (
            <ProviderCard
              key={provider.provider_id}
              provider={provider}
              defaults={defaults}
              onChanged={refresh}
              onError={fail}
              onStatus={setStatus}
              onSetDefault={setDefault}
            />
          ))}
        </div>
        {error ? <div className="notice" style={{ marginTop: 10 }}>{error}</div> : null}
        {status ? <div className="muted" style={{ marginTop: 10 }}>{status}</div> : null}
      </Panel>

      <Panel title={'外发审计（最近 ' + audits.length + ' 条）'}>
        {audits.length === 0 ? (
          <div className="muted">还没有向外部模型发送过请求。本地离线复盘不会产生外发记录。</div>
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

      <Panel title="本地诊断">
        {doctor ? (
          <table>
            <thead><tr><th>检查项</th><th>状态</th><th>说明</th></tr></thead>
            <tbody>
              {(doctor.checks as { name: string; status: string; detail: string }[]).map((check) => (
                <tr key={check.name}>
                  <td>{check.name}</td>
                  <td>{check.status === 'ok' ? <Badge kind="ok">正常</Badge> : <Badge kind="warn">{check.status}</Badge>}</td>
                  <td className="muted" style={{ whiteSpace: 'normal' }}>{check.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="muted">加载中…</div>}
      </Panel>

      {adding ? (
        <AddProviderModal
          catalog={catalog}
          protocols={protocols}
          providers={providers}
          onClose={() => setAdding(false)}
          onDone={async (message) => {
            setAdding(false);
            setStatus(message);
            setError('');
            await refresh();
          }}
          onError={fail}
        />
      ) : null}
    </div>
  );
}

function ProviderCard({ provider, defaults, onChanged, onError, onStatus, onSetDefault }: {
  provider: ProviderView;
  defaults: { provider_id: string; model: string; reasoning: string };
  onChanged: () => Promise<void>;
  onError: (value: unknown) => void;
  onStatus: (value: string) => void;
  onSetDefault: (providerId: string, model: string) => Promise<void>;
}) {
  const [key, setKey] = useState('');
  const [name, setName] = useState(provider.label);
  const [baseUrl, setBaseUrl] = useState(provider.base_url);
  const [protocol, setProtocol] = useState(provider.protocol);
  const [models, setModels] = useState<ModelEntry[]>(provider.models || []);
  const [picking, setPicking] = useState(false);

  useEffect(() => {
    setName(provider.label);
    setBaseUrl(provider.base_url);
    setProtocol(provider.protocol);
    setModels(provider.models || []);
  }, [provider]);

  const isDefaultProvider = defaults.provider_id === provider.provider_id;

  const save = async () => {
    try {
      await api.updateProvider(provider.provider_id, {
        display_name: name,
        base_url: provider.protocol === 'offline' ? undefined : baseUrl,
        protocol: provider.protocol === 'offline' ? undefined : protocol,
        models,
        api_key: key || undefined,
      });
      setKey('');
      onStatus('已保存「' + provider.label + '」。密钥只写入本机凭据文件，界面不会回显。');
      await onChanged();
    } catch (caught) { onError(caught); }
  };

  const test = async () => {
    onStatus('');
    try {
      const result = await api.testProvider({ provider_id: provider.provider_id });
      if (result.status === 'ok') {
        onStatus('「' + provider.label + '」连接成功' + (result.models?.length ? '，可用模型 ' + result.models.length + ' 个。' : '。'));
      } else {
        onError('「' + provider.label + '」连接失败：' + result.error);
      }
    } catch (caught) { onError(caught); }
  };

  const remove = async () => {
    if (!confirm('确认移除 Provider「' + provider.label + '」吗？它的本地密钥也会一并删除。')) return;
    try {
      await api.removeProvider(provider.provider_id);
      onStatus('已移除「' + provider.label + '」。');
      await onChanged();
    } catch (caught) { onError(caught); }
  };

  return (
    <div className="provider-card">
      <div className="provider-head">
        <div>
          <span className="provider-title">{provider.label}</span>
          <span className="provider-id">{provider.provider_id}</span>
        </div>
        <div className="row">
          {isDefaultProvider ? <Badge kind="ok">当前默认</Badge> : null}
          {provider.has_key ? <Badge kind="ok">已配置密钥</Badge> : <Badge kind="warn">未配置密钥</Badge>}
          <span className="muted" style={{ fontSize: 11 }}>来源 {provider.key_source}</span>
        </div>
      </div>
      <div className="provider-meta">{provider.description}</div>
      {provider.incomplete ? (
        <div className="notice" style={{ marginBottom: 8 }}>这个 Provider 还缺少必要的配置，补全后即可使用。</div>
      ) : null}

      <div className="provider-form">
        <div className="field">
          <label>显示名称</label>
          <input style={{ width: 180 }} value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="field">
          <label>API Key</label>
          <input
            type="password"
            style={{ width: 200 }}
            value={key}
            placeholder={provider.has_key ? '已保存（留空表示不修改）' : '粘贴密钥'}
            onChange={(event) => setKey(event.target.value)}
          />
        </div>
      </div>
      {provider.protocol === 'offline' ? (
        <div className="provider-meta" style={{ marginTop: 8 }}>
          本地 Provider 不需要地址与协议，也不会发出任何网络请求。
        </div>
      ) : (
        <div className="provider-form">
          <div className="field">
            <label>Base URL</label>
            <input style={{ width: 280 }} value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
          </div>
          <div className="field">
            <label>API 协议</label>
            <select value={protocol} onChange={(event) => setProtocol(event.target.value)}>
              <option value="openai-chat">OpenAI Chat Completions</option>
              <option value="openai-responses">OpenAI Responses</option>
              <option value="anthropic-messages">Anthropic Messages</option>
            </select>
          </div>
        </div>
      )}
      <div className="provider-form">
        <button className="primary" onClick={save}>保存</button>
        {provider.protocol === 'offline' ? null : <button className="ghost" onClick={test}>测试连接</button>}
        {provider.has_key ? (
          <button
            className="ghost"
            onClick={async () => {
              await api.updateProvider(provider.provider_id, { clear_key: true });
              onStatus('已清除「' + provider.label + '」的本地密钥。');
              await onChanged();
            }}
          >
            清除密钥
          </button>
        ) : null}
        {provider.removable ? <button className="ghost" onClick={remove}>移除</button> : null}
      </div>

      <div className="row" style={{ justifyContent: 'space-between', marginTop: 12 }}>
        <span className="muted" style={{ fontSize: 11 }}>
          模型目录（{models.length}）· 点模型可设为默认对话模型
        </span>
        <div className="row">
          <button className="ghost" onClick={() => setPicking(true)}>获取可用模型</button>
        </div>
      </div>
      {models.length === 0 ? (
        <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
          还没有模型。用「获取可用模型」从端点拉取，或手工添加。
        </div>
      ) : null}
      <div className="model-chips">
        {models.map((model) => (
          <button
            key={model.id}
            className={'model-chip' + (isDefaultProvider && defaults.model === model.id ? ' active' : '')}
            onClick={() => void onSetDefault(provider.provider_id, model.id)}
            title="设为默认对话模型"
          >
            {model.label || model.id}
            {model.reasoning_efforts.length > 1
              ? <span className="effort">{effortLabel(model.default_effort)}</span>
              : null}
          </button>
        ))}
      </div>

      {picking ? (
        <ModelPickerModal
          provider={provider}
          existing={models}
          onClose={() => setPicking(false)}
          onApply={async (next) => {
            setModels(next);
            setPicking(false);
            try {
              await api.updateProvider(provider.provider_id, { models: next });
              onStatus('「' + provider.label + '」的模型目录已更新为 ' + next.length + ' 个。');
              await onChanged();
            } catch (caught) { onError(caught); }
          }}
        />
      ) : null}
    </div>
  );
}

function ModelPickerModal({ provider, existing, onClose, onApply }: {
  provider: ProviderView;
  existing: ModelEntry[];
  onClose: () => void;
  onApply: (models: ModelEntry[]) => void;
}) {
  const [available, setAvailable] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(
    new Set(existing.map((model) => model.id)),
  );
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState('');
  const [manual, setManual] = useState('');

  const fetchModels = async () => {
    setLoading(true);
    setNote('');
    try {
      const result = await api.discoverModels({ provider_id: provider.provider_id });
      setAvailable(result.models);
      setSelected((prev) => {
        const next = new Set(prev);
        // Nothing is added automatically; the list is only offered.
        return next;
      });
    } catch (caught) {
      setNote(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void fetchModels(); }, []);

  const filtered = available.filter((id) => !query.trim() || id.toLowerCase().includes(query.trim().toLowerCase()));

  const apply = () => {
    const known = new Map(existing.map((model) => [model.id, model]));
    const next: ModelEntry[] = [];
    for (const id of [...available, ...manual.split(/[\n,]/).map((item) => item.trim()).filter(Boolean)]) {
      if (!id || !selected.has(id)) continue;
      const previous = known.get(id);
      next.push(
        previous || {
          id,
          label: id,
          reasoning_efforts: [],
          default_effort: 'off',
        },
      );
    }
    onApply(next);
  };

  const toggleAll = () => {
    if (selected.size === available.length) setSelected(new Set());
    else setSelected(new Set(available));
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <h3>选择要添加的模型</h3>
        <div className="hint">
          以下是端点回应的可用模型，勾选要添加的模型。端点不回应目录时，可以在下方手工填写模型 id。
        </div>
        <div className="row" style={{ marginBottom: 8 }}>
          <input
            className="picker-search"
            placeholder="搜索模型"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            style={{ flex: 1 }}
          />
          <button className="ghost" onClick={toggleAll}>全选 / 取消全选</button>
          <button className="ghost" onClick={fetchModels} disabled={loading}>
            {loading ? '获取中…' : '重新获取'}
          </button>
        </div>
        {note ? <div className="notice" style={{ marginBottom: 8 }}>{note}</div> : null}
        <div className="checklist">
          {loading ? <div className="muted" style={{ padding: 10 }}>正在向端点请求模型目录…</div> : null}
          {!loading && filtered.length === 0 && !note ? (
            <div className="muted" style={{ padding: 10 }}>没有匹配的模型。</div>
          ) : null}
          {filtered.map((id) => (
            <div className="checklist-row" key={id}>
              <input
                type="checkbox"
                checked={selected.has(id)}
                onChange={(event) => {
                  setSelected((prev) => {
                    const next = new Set(prev);
                    if (event.target.checked) next.add(id);
                    else next.delete(id);
                    return next;
                  });
                }}
              />
              <label>{id}</label>
            </div>
          ))}
        </div>
        <div className="field" style={{ marginTop: 10 }}>
          <label>手工添加模型 id（每行一个，或逗号分隔）</label>
          <textarea
            value={manual}
            placeholder="deepseek-v3"
            onChange={(event) => {
              setManual(event.target.value);
              const ids = event.target.value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
              setSelected((prev) => {
                const next = new Set(prev);
                ids.forEach((id) => next.add(id));
                return next;
              });
            }}
          />
        </div>
        <div className="modal-actions">
          <button className="ghost" onClick={onClose}>取消</button>
          <button className="primary" onClick={apply}>添加所选</button>
        </div>
      </div>
    </div>
  );
}

function AddProviderModal({ catalog, protocols, providers, onClose, onDone, onError }: {
  catalog: CatalogEntry[];
  protocols: ProtocolOption[];
  providers: ProviderView[];
  onClose: () => void;
  onDone: (message: string) => Promise<void>;
  onError: (value: unknown) => void;
}) {
  const [mode, setMode] = useState<'catalog' | 'custom'>('catalog');
  const [providerId, setProviderId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [protocol, setProtocol] = useState(protocols[0]?.id || 'openai-chat');
  const [key, setKey] = useState('');
  const [manual, setManual] = useState('');

  const installed = new Set(providers.map((provider) => provider.provider_id));

  const addFromCatalog = async (entry: CatalogEntry) => {
    try {
      await api.addProvider({
        provider_id: entry.provider_id,
        from_catalog: true,
        api_key: key || undefined,
      });
      await onDone('已添加「' + entry.label + '」。填入密钥后即可使用。');
    } catch (caught) { onError(caught); }
  };

  const addCustom = async () => {
    try {
      await api.addProvider({
        provider_id: providerId,
        from_catalog: false,
        display_name: displayName || providerId,
        base_url: baseUrl,
        protocol,
        api_key: key || undefined,
        models: manual.split(/[\n,]/).map((item) => item.trim()).filter(Boolean),
      });
      await onDone('已添加自定义 Provider「' + (displayName || providerId) + '」。');
    } catch (caught) { onError(caught); }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        {mode === 'catalog' ? (
          <>
            <h3>添加 Provider</h3>
            <div className="hint">
              选择内置目录里的 Provider，它会带上端点、协议和模型列表。密钥只写入本机凭据文件。
            </div>
            <div className="field" style={{ marginBottom: 10 }}>
              <label>API Key（可选，稍后也可以填）</label>
              <input type="password" value={key} onChange={(event) => setKey(event.target.value)} />
            </div>
            <div className="checklist">
              {catalog.map((entry) => (
                <div className="checklist-row" key={entry.provider_id}>
                  <div style={{ flex: 1 }}>
                    <div>{entry.label}<span className="provider-id">{entry.provider_id}</span></div>
                    <div className="muted" style={{ fontSize: 11 }}>
                      {entry.protocol_label} · {entry.models.length} 个模型
                      {entry.has_env_key ? ' · 已检测到环境变量密钥' : ''}
                    </div>
                  </div>
                  <button
                    className="ghost"
                    disabled={installed.has(entry.provider_id)}
                    onClick={() => void addFromCatalog(entry)}
                  >
                    {installed.has(entry.provider_id) ? '已添加' : '添加'}
                  </button>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button className="ghost" onClick={() => setMode('custom')}>添加自定义 Provider</button>
              <button className="ghost" onClick={onClose}>关闭</button>
            </div>
          </>
        ) : (
          <>
            <h3>添加自定义 Provider</h3>
            <div className="hint">
              用于公司中转站、自建服务或目录里没有的服务。Protocol 必须与网关实际支持的一致。
            </div>
            <div className="grid" style={{ gap: 10 }}>
              <div className="field">
                <label>Provider ID（小写字母、数字、连字符；创建后不可改名）</label>
                <input value={providerId} placeholder="my-gateway" onChange={(event) => setProviderId(event.target.value)} />
              </div>
              <div className="field">
                <label>显示名称</label>
                <input value={displayName} placeholder="公司中转站" onChange={(event) => setDisplayName(event.target.value)} />
              </div>
              <div className="field">
                <label>Base URL</label>
                <input value={baseUrl} placeholder="https://gateway.example/v1" onChange={(event) => setBaseUrl(event.target.value)} />
              </div>
              <div className="field">
                <label>API 协议</label>
                <select value={protocol} onChange={(event) => setProtocol(event.target.value)}>
                  {protocols.map((item) => (
                    <option key={item.id} value={item.id}>{item.label}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>API Key</label>
                <input type="password" value={key} onChange={(event) => setKey(event.target.value)} />
              </div>
              <div className="field">
                <label>模型 id（每行一个，或逗号分隔；也可以创建后再获取）</label>
                <textarea value={manual} placeholder="deepseek-v3" onChange={(event) => setManual(event.target.value)} />
              </div>
            </div>
            <div className="modal-actions">
              <button className="ghost" onClick={() => setMode('catalog')}>返回目录</button>
              <button className="ghost" onClick={onClose}>取消</button>
              <button className="primary" onClick={addCustom} disabled={!providerId || !baseUrl}>创建</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
