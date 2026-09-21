import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import type { PluginCatalogEntry, PluginCatalogResponse, PluginDetailResponse, PluginItem } from '../types';
import { Badge, Empty, Panel } from '../components/common';

type PluginTab = 'market' | 'inventory' | 'config' | 'catalog';

export function PluginsView() {
  const [tab, setTab] = useState<PluginTab>('market');
  const [plugins, setPlugins] = useState<PluginItem[]>([]);
  const [catalogData, setCatalogData] = useState<PluginCatalogResponse | null>(null);
  const [marketData, setMarketData] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [marketCategory, setMarketCategory] = useState('全部');

  // Drawer / modal for plugin inspection & events
  const [activePluginId, setActivePluginId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PluginDetailResponse | null>(null);

  // Configuration draft state: pluginId -> config dict
  const [configDrafts, setConfigDrafts] = useState<Record<string, Record<string, any>>>({});
  const [savingConfig, setSavingConfig] = useState<string | null>(null);

  const loadPlugins = async () => {
    setLoading(true);
    try {
      const res = await api.plugins();
      const list = (res.plugins as PluginItem[]) || [];
      setPlugins(list);
      setError('');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setLoading(false);
    }
  };

  const loadCatalog = async () => {
    try {
      const res = await api.pluginCatalog();
      setCatalogData(res);
    } catch {
      // Catalog error is non-fatal
    }
  };

  const loadMarket = async () => {
    try {
      setMarketData(await api.pluginMarket());
    } catch {
      // The official market is additive; local inventory remains usable.
    }
  };

  useEffect(() => {
    void loadPlugins();
    void loadCatalog();
    void loadMarket();
  }, []);

  const openDetail = async (pluginId: string) => {
    setActivePluginId(pluginId);
    try {
      const res = await api.pluginDetail(pluginId);
      setDetail(res);
      if (res.config && !configDrafts[pluginId]) {
        setConfigDrafts((prev) => ({ ...prev, [pluginId]: { ...res.config } }));
      }
    } catch {
      setDetail(null);
    }
  };

  const togglePlugin = async (plugin: PluginItem) => {
    const isServing = plugin.state === 'ACTIVE' || plugin.enabled;
    const action = isServing ? api.disablePlugin : api.enablePlugin;
    setError('');
    setNotice('');
    try {
      await action(plugin.plugin_id);
      setNotice("插件「" + (plugin.name || plugin.plugin_id) + "」已" + (isServing ? "停用" : "启用"));
      await loadPlugins();
      if (activePluginId === plugin.plugin_id) {
        await openDetail(plugin.plugin_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleReload = async () => {
    setLoading(true);
    setError('');
    try {
      await api.reloadPlugins();
      setNotice('已重新扫描本地插件目录');
      await loadPlugins();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const saveConfig = async (pluginId: string) => {
    const config = configDrafts[pluginId] || {};
    setSavingConfig(pluginId);
    setError('');
    try {
      await api.configurePlugin(pluginId, config);
      setNotice("插件「" + pluginId + "」配置已保存");
      if (activePluginId === pluginId) {
        await openDetail(pluginId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingConfig(null);
    }
  };

  const installMarket = async (pluginId: string) => {
    setError('');
    setNotice('');
    try {
      const entry = ((marketData?.catalog || []) as Record<string, any>[]).find((item) => item.plugin_id === pluginId);
      const config = entry && !entry.requires_credentials ? { permissions_confirmed: true } : {};
      const result = await api.installMarketPlugin(pluginId, config);
      setNotice(result.status === 'configuration_required'
        ? '插件已进入配置向导：请先确认权限、密钥与健康检查。'
        : '官方插件已启用。');
      await loadMarket();
      await loadPlugins();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  const filteredPlugins = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return plugins;
    return plugins.filter((p) => {
      const matchId = p.plugin_id.toLowerCase().includes(q);
      const matchName = (p.name || '').toLowerCase().includes(q);
      const matchCaps = (p.capabilities || []).some((c) => c.toLowerCase().includes(q));
      const matchIso = (p.isolation || '').toLowerCase().includes(q);
      return matchId || matchName || matchCaps || matchIso;
    });
  }, [plugins, search]);

  const activeCount = useMemo(() => {
    return plugins.filter((p) => p.state === 'ACTIVE' || p.enabled).length;
  }, [plugins]);

  const marketEntries = useMemo(() => {
    const q = search.trim().toLowerCase();
    return ((marketData?.catalog || []) as Record<string, any>[]).filter((item) => {
      const categoryMatch = marketCategory === '全部' || item.category === marketCategory;
      const searchMatch = !q || [item.plugin_id, item.name, item.description, item.category]
        .some((value) => String(value || '').toLowerCase().includes(q));
      return categoryMatch && searchMatch;
    });
  }, [marketData, marketCategory, search]);
  const marketCategories = ['全部', ...Array.from(new Set(((marketData?.catalog || []) as Record<string, any>[]).map((item) => String(item.category || '其他'))))];

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <strong>复盘安全底线：</strong>插件只能读取外部数据并作为复盘证据使用。禁止下单、改账户与绕过脱敏。任何 <code>available_at</code> 晚于决策时间的数据都会被判定为未来数据拒绝。
        </div>
        <Badge kind="ok">READ_ONLY</Badge>
      </div>

      {notice ? <div className="notice" role="status" style={{ borderLeftColor: 'var(--color-accent)' }}>{notice}</div> : null}
      {error ? <div className="notice" role="alert" style={{ borderLeftColor: 'var(--neg)' }}>{error}</div> : null}

      <div className="dsh-subtabs">
        <button
          className={'dsh-subtab' + (tab === 'market' ? ' active' : '')}
          onClick={() => setTab('market')}
        >
          官方插件市场
          <span className="dsh-tab-badge">{marketData?.catalog?.length || 21}</span>
        </button>
        <button
          className={'dsh-subtab' + (tab === 'inventory' ? ' active' : '')}
          onClick={() => setTab('inventory')}
        >
          已安装插件
          <span className="dsh-tab-badge">{plugins.length}</span>
        </button>
        <button
          className={'dsh-subtab' + (tab === 'config' ? ' active' : '')}
          onClick={() => setTab('config')}
        >
          插件配置
        </button>
        <button
          className={'dsh-subtab' + (tab === 'catalog' ? ' active' : '')}
          onClick={() => setTab('catalog')}
        >
          开源生态目录
          <span className="dsh-tab-badge">{catalogData?.entries?.length || 0}</span>
        </button>
      </div>

      {tab === 'inventory' ? (
        <Panel>
          <div className="dsh-inventory-header">
            <div className="dsh-search-bar">
              <svg className="dsh-search-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="7" cy="7" r="5" />
                <path d="m11 11 3.5 3.5" strokeLinecap="round" />
              </svg>
              <input
                type="search"
                className="dsh-search-input"
                placeholder="搜索插件 ID、名称、能力或隔离模式..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search ? (
                <button className="dsh-clear-btn" onClick={() => setSearch('')}>✕</button>
              ) : null}
            </div>

            <div className="row" style={{ gap: 8, alignItems: 'center' }}>
              <span className="muted" style={{ fontSize: 12 }}>
                已发现 {plugins.length} 个插件（{activeCount} 已启用）
              </span>
              <button className="ghost" onClick={handleReload} disabled={loading} title="重新扫描插件目录">
                {loading ? '扫描中...' : '重新扫描'}
              </button>
            </div>
          </div>

          {filteredPlugins.length === 0 ? (
            <Empty text={plugins.length === 0 ? '还没有发现任何本地插件' : '没有匹配当前搜索的插件'} />
          ) : (
            <div className="dsh-cards-grid">
              {filteredPlugins.map((plugin) => {
                const isServing = plugin.state === 'ACTIVE' || plugin.enabled;
                return (
                  <div className="dsh-plugin-card" key={plugin.plugin_id}>
                    <div className="dsh-plugin-card-head">
                      <div className="row" style={{ gap: 8, alignItems: 'center', minWidth: 0 }}>
                        <span
                          className={'dsh-status-dot ' + (isServing ? 'active' : 'inactive')}
                          title={isServing ? '已启用 (Serving)' : '已停用 (Disabled)'}
                        />
                        <strong className="dsh-plugin-title" title={plugin.plugin_id}>
                          {plugin.name || plugin.plugin_id}
                        </strong>
                        <span className="dsh-version-tag">v{plugin.version || '0.1.0'}</span>
                      </div>

                      <button
                        className={'dsh-switch-btn ' + (isServing ? 'active' : '')}
                        onClick={() => void togglePlugin(plugin)}
                        title={isServing ? '点击停用' : '点击启用'}
                      >
                        {isServing ? '已启用' : '已停用'}
                      </button>
                    </div>

                    <div className="dsh-plugin-card-body">
                      <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
                        标识符：<code>{plugin.plugin_id}</code> · 隔离：{plugin.isolation || 'subprocess'}
                      </div>

                      <div className="row" style={{ gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
                        {(plugin.capabilities || []).map((cap) => (
                          <span className="dsh-cap-tag" key={cap}>{cap}</span>
                        ))}
                      </div>

                      {plugin.last_error ? (
                        <div className="notice" style={{ padding: '4px 8px', fontSize: 11, margin: '4px 0' }}>
                          错误：{plugin.last_error}
                        </div>
                      ) : null}
                    </div>

                    <div className="dsh-plugin-card-foot">
                      <button
                        className="ghost"
                        style={{ fontSize: 11, padding: '4px 8px' }}
                        onClick={() => void openDetail(plugin.plugin_id)}
                      >
                        详情与日志
                      </button>
                      <button
                        className="ghost"
                        style={{ fontSize: 11, padding: '4px 8px' }}
                        onClick={() => {
                          setTab('config');
                          void openDetail(plugin.plugin_id);
                        }}
                      >
                        配置参数
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      ) : null}

      {tab === 'config' ? (
        <Panel title="插件配置与参数调优">
          <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>
            配置各项插件的运行参数（如阈值、抽样率、本地数据路径等）。参数持久化在本机插件数据库中，运行时即刻生效。
          </div>

          <div className="grid" style={{ gap: 14 }}>
            {plugins.map((plugin) => {
              const pId = plugin.plugin_id;
              const draft = configDrafts[pId] || {};
              return (
                <div className="provider-card" key={pId}>
                  <div className="provider-head">
                    <div>
                      <span className="provider-title">{plugin.name || pId}</span>
                      <span className="provider-id">{pId}</span>
                    </div>
                    <span className={'dsh-status-dot ' + (plugin.state === 'ACTIVE' || plugin.enabled ? 'active' : 'inactive')} />
                  </div>

                  <div className="provider-meta">
                    声明能力：{(plugin.capabilities || []).join(', ') || '—'} · 隔离：{plugin.isolation}
                  </div>

                  <div className="dsh-field-group">
                    <div className="dsh-field">
                      <label>配置参数 JSON (Key-Value 键值对)</label>
                      <textarea
                        style={{ fontFamily: 'monospace', fontSize: 12, minHeight: 80 }}
                        value={JSON.stringify(draft, null, 2)}
                        placeholder={"{threshold: 0.8}"}
                        onChange={(e) => {
                          try {
                            const parsed = JSON.parse(e.target.value);
                            setConfigDrafts((prev) => ({ ...prev, [pId]: parsed }));
                          } catch {
                            // allow typing
                          }
                        }}
                      />
                      <span className="muted" style={{ fontSize: 11 }}>
                        输入合法的 JSON 对象。修改后点击保存即持久化至插件状态库。
                      </span>
                    </div>
                  </div>

                  <div className="row" style={{ gap: 8, marginTop: 10 }}>
                    <button
                      className="primary"
                      disabled={savingConfig === pId}
                      onClick={() => void saveConfig(pId)}
                    >
                      {savingConfig === pId ? '保存中...' : '保存配置'}
                    </button>
                    <button
                      className="ghost"
                      onClick={() => setConfigDrafts((prev) => ({ ...prev, [pId]: {} }))}
                    >
                      恢复默认
                    </button>
                    <button
                      className="ghost"
                      onClick={() => void openDetail(pId)}
                    >
                      查看事件审计
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      ) : null}

      {tab === 'catalog' ? (
        <Panel title="推荐外部插件与适配器生态">
          <div className="muted" style={{ fontSize: 12, marginBottom: 14 }}>
            {catalogData?.policy || '生态目录收录经过安全与只读契约审核的外部量化与分析组件。安装后作为只读证据来源使用，禁止下单或修改账户。'}
          </div>

          <div className="grid" style={{ gap: 12 }}>
            {(catalogData?.entries || []).map((item: PluginCatalogEntry) => (
              <div className="provider-card" key={item.project}>
                <div className="provider-head">
                  <div>
                    <span className="provider-title">{item.project}</span>
                    <a
                      href={item.repo}
                      target="_blank"
                      rel="noreferrer"
                      className="provider-id"
                      style={{ textDecoration: 'underline' }}
                    >
                      {item.repo}
                    </a>
                  </div>
                  <Badge kind={item.execution_risk === 'low' ? 'ok' : item.execution_risk === 'medium' ? 'warn' : 'error'}>
                    风险：{item.execution_risk.toUpperCase()}
                  </Badge>
                </div>

                <div className="provider-meta">
                  级别：<strong>{item.level}</strong> · 许可证：{item.license} · 维护状态：{item.maintained} · 联网：{item.network_required ? '需要' : '离线'}
                </div>

                <div style={{ fontSize: 12, marginTop: 6 }}>
                  <strong>安全边界与限制：</strong>
                  <span className="muted">{item.boundary}</span>
                </div>

                <div className="row" style={{ gap: 6, marginTop: 8 }}>
                  {(item.capabilities || []).map((c) => (
                    <span className="dsh-cap-tag" key={c}>{c}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      {tab === 'market' ? (
        <Panel title="官方插件市场">
          <div className="plugin-market-head">
            <div className="muted" style={{ fontSize: 12, lineHeight: 1.6 }}>
              官方精选插件只读接入复盘证据。安装会先进入配置向导，确认权限、密钥与健康检查后才会挂载。
            </div>
            <Badge kind="ok">READ_ONLY</Badge>
          </div>
          <div className="plugin-toolbar" style={{ marginTop: 12 }}>
            <div className="segmented" role="tablist" aria-label="插件市场分类">
              {marketCategories.map((category) => (
                <button key={category} className={marketCategory === category ? 'active' : ''} onClick={() => setMarketCategory(category)}>
                  {category}
                </button>
              ))}
            </div>
            <span className="muted" style={{ fontSize: 11 }}>已收录 {marketData?.catalog?.length || 0} 个精选插件</span>
          </div>
          <div className="plugin-card-grid">
            {marketEntries.map((item) => (
              <div className="plugin-card" key={item.plugin_id}>
                <div className="plugin-card-top">
                  <div className="plugin-icon">✦</div>
                  <div className="grow">
                    <strong>{item.name || item.plugin_id}</strong>
                    <div className="mono muted">{item.plugin_id} · v{item.version}</div>
                  </div>
                </div>
                <p>{item.description}</p>
                <div className="plugin-tags">
                  <span className="tag">{item.category}</span>
                  {item.requires_credentials ? <span className="tag">需要密钥</span> : <span className="tag">免密钥</span>}
                </div>
                <div className="plugin-card-foot">
                  <span className="muted">{item.installed ? '已安装 · ' + item.state : '官方精选 · 只读沙箱'}</span>
                  <button className={item.installed ? 'ghost' : 'primary'} onClick={() => void installMarket(item.plugin_id)}>
                    {item.installed ? '继续配置' : '安装'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      {activePluginId && detail ? (
        <div className="dsh-modal-backdrop" onClick={() => setActivePluginId(null)}>
          <div className="dsh-modal" onClick={(e) => e.stopPropagation()}>
            <div className="dsh-modal-head">
              <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                <span className={'dsh-status-dot ' + (detail.plugin.state === 'ACTIVE' || detail.plugin.enabled ? 'active' : 'inactive')} />
                <strong style={{ fontSize: 15 }}>{detail.plugin.name || detail.plugin_id}</strong>
                <span className="dsh-version-tag">v{detail.plugin.version}</span>
              </div>
              <button className="ghost" onClick={() => setActivePluginId(null)}>✕</button>
            </div>

            <div className="dsh-modal-body">
              <div className="grid" style={{ gap: 12 }}>
                <div>
                  <div className="muted" style={{ fontSize: 11 }}>状态与隔离</div>
                  <div>当前状态：<strong>{detail.plugin.state}</strong> · 隔离环境：{detail.plugin.isolation}</div>
                </div>

                <div>
                  <div className="muted" style={{ fontSize: 11 }}>能力与服务</div>
                  <div className="row" style={{ gap: 4, marginTop: 4 }}>
                    {(detail.plugin.capabilities || []).map((cap) => (
                      <span className="dsh-cap-tag" key={cap}>{cap}</span>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>清单描述 (Manifest)</div>
                  <pre className="dsh-code-box">
                    {JSON.stringify(detail.manifest, null, 2)}
                  </pre>
                </div>

                <div>
                  <div className="muted" style={{ fontSize: 11, marginBottom: 4 }}>生命周期事件审计日志（最近 {detail.events.length} 条）</div>
                  {detail.events.length === 0 ? (
                    <div className="muted" style={{ fontSize: 12 }}>暂无事件记录</div>
                  ) : (
                    <div className="scroll-x">
                      <table>
                        <thead><tr><th>时间</th><th>状态变迁</th><th>详情说明</th></tr></thead>
                        <tbody>
                          {detail.events.map((ev) => (
                            <tr key={ev.id}>
                              <td className="muted" style={{ fontSize: 11 }}>{ev.created_at}</td>
                              <td>{(ev.from_state || '—') + ' → ' + ev.to_state}</td>
                              <td className="muted">{ev.detail || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div className="dsh-modal-actions">
              <button className="primary" onClick={() => setActivePluginId(null)}>完成</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
