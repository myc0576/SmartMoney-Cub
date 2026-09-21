import { useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import type {
  PluginDetailResponse,
  PluginItem,
  PluginMarketEntry,
  PluginMarketResponse,
} from '../types';
import { Badge, Empty, Panel } from '../components/common';
import { PluginSetupWizard } from '../components/PluginSetupWizard';

type PluginTab = 'market' | 'inventory';

export function PluginsView() {
  const [tab, setTab] = useState<PluginTab>('market');
  const [plugins, setPlugins] = useState<PluginItem[]>([]);
  const [marketData, setMarketData] = useState<PluginMarketResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');
  const [marketCategory, setMarketCategory] = useState('全部');

  // Wizard state
  const [wizardEntry, setWizardEntry] = useState<PluginMarketEntry | null>(null);

  // Detail modal state
  const [activePluginId, setActivePluginId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PluginDetailResponse | null>(null);
  const [uninstalling, setUninstalling] = useState(false);

  // Copy feedback state: plugin_id -> boolean
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Action pending state
  const [actionPendingId, setActionPendingId] = useState<string | null>(null);

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

  const loadMarket = async () => {
    try {
      const res = await api.pluginMarket();
      setMarketData(res);
    } catch {
      // The official market is additive; local inventory remains usable.
    }
  };

  const refreshAll = async () => {
    await Promise.all([loadPlugins(), loadMarket()]);
  };

  useEffect(() => {
    void refreshAll();
  }, []);

  const openDetail = async (pluginId: string) => {
    setActivePluginId(pluginId);
    try {
      const res = await api.pluginDetail(pluginId);
      setDetail(res);
    } catch {
      setDetail(null);
    }
  };

  const togglePlugin = async (plugin: PluginItem) => {
    const isServing = plugin.state === 'ACTIVE' || plugin.enabled;
    const action = isServing ? api.disablePlugin : api.enablePlugin;
    setError('');
    setNotice('');
    setActionPendingId(plugin.plugin_id);
    try {
      await action(plugin.plugin_id);
      setNotice('插件「' + (plugin.name || plugin.plugin_id) + '」已' + (isServing ? '停用' : '启用'));
      await refreshAll();
      if (activePluginId === plugin.plugin_id) {
        await openDetail(plugin.plugin_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionPendingId(null);
    }
  };

  const handleReload = async () => {
    setLoading(true);
    setError('');
    try {
      await api.reloadPlugins();
      setNotice('已重新扫描本地插件目录');
      await refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleUninstall = async (pluginId: string) => {
    if (!window.confirm('确认卸载插件「' + pluginId + '」吗？此操作将移除本地运行时挂载及配置。')) {
      return;
    }
    setUninstalling(true);
    setError('');
    try {
      const res = await api.pluginUninstall(pluginId);
      if (res.status === 'ok') {
        setNotice('插件「' + pluginId + '」已成功卸载');
        setActivePluginId(null);
        setDetail(null);
        await refreshAll();
      } else {
        setError(res.error || '卸载失败');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUninstalling(false);
    }
  };

  const copyCommand = (id: string, cmd: string) => {
    if (!cmd) return;
    navigator.clipboard.writeText(cmd).then(() => {
      setCopiedId(id);
      setTimeout(() => {
        setCopiedId((curr) => (curr === id ? null : curr));
      }, 2000);
    }).catch(() => {
      // ignore clipboard error
    });
  };

  const handleMarketAction = (entry: PluginMarketEntry) => {
    if (entry.state === 'AVAILABLE' || entry.state === 'ERROR') {
      setWizardEntry(entry);
    } else if (entry.state === 'INSTALLED' || entry.state === 'DISABLED') {
      // Call enable
      void (async () => {
        setActionPendingId(entry.plugin_id);
        setError('');
        try {
          await api.enablePlugin(entry.plugin_id);
          setNotice('插件「' + (entry.name || entry.plugin_id) + '」已启用');
          await refreshAll();
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err));
        } finally {
          setActionPendingId(null);
        }
      })();
    } else if (entry.state === 'ENABLED') {
      // Configure or disable
      setWizardEntry(entry);
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
    const catalog = marketData?.catalog || [];
    return catalog.filter((item) => {
      const categoryMatch = marketCategory === '全部' || item.category === marketCategory;
      const searchMatch = !q || [item.plugin_id, item.name, item.description, item.category]
        .some((value) => String(value || '').toLowerCase().includes(q));
      return categoryMatch && searchMatch;
    });
  }, [marketData, marketCategory, search]);

  const marketCategories = useMemo(() => {
    const fromApi = marketData?.categories || [];
    if (fromApi.length > 0) {
      return ['全部', ...fromApi];
    }
    const set = new Set((marketData?.catalog || []).map((item) => String(item.category || '其他')));
    return ['全部', ...Array.from(set)];
  }, [marketData]);

  const totalMarketCount = marketData?.counts?.total ?? (marketData?.catalog?.length || 0);

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
          <span className="dsh-tab-badge">{totalMarketCount}</span>
        </button>
        <button
          className={'dsh-subtab' + (tab === 'inventory' ? ' active' : '')}
          onClick={() => setTab('inventory')}
        >
          已安装插件
          <span className="dsh-tab-badge">{plugins.length}</span>
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
                const isPending = actionPendingId === plugin.plugin_id;
                return (
                  <div className="dsh-plugin-card" key={plugin.plugin_id}>
                    <div className="dsh-plugin-card-head">
                      <div className="row" style={{ gap: 8, alignItems: 'center', minWidth: 0 }}>
                        <span
                          className={'dsh-status-dot ' + (isServing ? 'active' : 'inactive')}
                          aria-label={isServing ? '已启用 (Serving)' : '已停用 (Disabled)'}
                          title={isServing ? '已启用 (Serving)' : '已停用 (Disabled)'}
                        />
                        <strong className="dsh-plugin-title" title={plugin.plugin_id}>
                          {plugin.name || plugin.plugin_id}
                        </strong>
                        <span className="dsh-version-tag">v{plugin.version || '0.1.0'}</span>
                      </div>

                      <button
                        role="switch"
                        aria-checked={isServing}
                        className={'dsh-switch-btn ' + (isServing ? 'active' : '')}
                        disabled={isPending}
                        onClick={() => void togglePlugin(plugin)}
                        title={isServing ? '点击停用' : '点击启用'}
                      >
                        {isPending ? '切换中…' : isServing ? '停用' : '启用'}
                      </button>
                    </div>

                    <div className="dsh-plugin-card-body">
                      <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
                        标识符：<code className="mono">{plugin.plugin_id}</code> · 隔离：{plugin.isolation || 'subprocess'}
                      </div>

                      <div className="row" style={{ gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
                        {(plugin.capabilities || []).map((cap) => (
                          <span className="dsh-cap-tag" key={cap}>{cap}</span>
                        ))}
                      </div>

                      {plugin.last_error ? (
                        <div className="notice" style={{ padding: '4px 8px', fontSize: 11, margin: '4px 0', borderLeftColor: 'var(--neg)' }}>
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
                    </div>
                  </div>
                );
              })}
            </div>
          )}
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
                <button
                  key={category}
                  className={marketCategory === category ? 'active' : ''}
                  onClick={() => setMarketCategory(category)}
                >
                  {category}
                </button>
              ))}
            </div>
            <span className="muted" style={{ fontSize: 11 }}>已收录 {totalMarketCount} 个精选插件</span>
          </div>
          <div className="plugin-card-grid">
            {marketEntries.map((item) => {
              const isActionPending = actionPendingId === item.plugin_id;
              const installKind = item.install?.kind === 'pypi'
                ? 'PyPI'
                : item.install?.kind === 'git'
                ? '源码'
                : '内置';
              const isCopied = copiedId === item.plugin_id;

              return (
                <div className="plugin-card" key={item.plugin_id}>
                  <div className="plugin-card-top">
                    <div className="plugin-icon">✦</div>
                    <div className="grow" style={{ minWidth: 0 }}>
                      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                        <strong title={item.name || item.plugin_id}>{item.name || item.plugin_id}</strong>
                        <Badge kind={item.execution_risk === 'high' ? 'error' : item.execution_risk === 'medium' ? 'warn' : 'ok'}>
                          {item.execution_risk.toUpperCase()} 风险
                        </Badge>
                      </div>
                      <div className="mono muted" style={{ fontSize: 11, marginTop: 2 }}>
                        {item.plugin_id} · v{item.install?.version || '最新'} · {item.level}
                      </div>
                    </div>
                  </div>

                  <p style={{ margin: '8px 0', fontSize: 12, lineHeight: 1.5 }}>{item.description}</p>

                  <div className="plugin-tags" style={{ marginBottom: 8 }}>
                    <span className="tag">{item.category}</span>
                    <span className="tag">{installKind}</span>
                    <span className="tag">{item.license}</span>
                    {item.requires_credentials ? <span className="tag warn">需要密钥</span> : <span className="tag">免密钥</span>}
                  </div>

                  <div style={{ fontSize: 11, marginBottom: 8 }}>
                    <span className="muted">上游地址：</span>
                    <a
                      href={item.repo}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        textDecoration: 'underline',
                        color: 'var(--color-accent)',
                        // A repository URL is one long token with no spaces, so
                        // it has to be allowed to break or it widens the card.
                        wordBreak: 'break-all',
                      }}
                    >
                      {item.repo}
                    </a>
                  </div>

                  {item.manual_command ? (
                    <div style={{ marginBottom: 8 }}>
                      <div className="muted" style={{ fontSize: 10.5, marginBottom: 2 }}>上游原生安装命令：</div>
                      <div className="row" style={{ gap: 6, alignItems: 'center' }}>
                        <code className="mono" style={{ fontSize: 11, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', background: 'var(--inset)', padding: '2px 6px', borderRadius: 4 }}>
                          {item.manual_command}
                        </code>
                        <button
                          className="ghost"
                          style={{ fontSize: 10.5, padding: '2px 6px', whiteSpace: 'nowrap' }}
                          onClick={() => copyCommand(item.plugin_id, item.manual_command)}
                        >
                          {isCopied ? '已复制！' : '复制'}
                        </button>
                      </div>
                    </div>
                  ) : null}

                  {item.last_error ? (
                    <div className="notice" style={{ padding: '4px 8px', fontSize: 11, margin: '4px 0', borderLeftColor: 'var(--neg)' }}>
                      错误：{item.last_error}
                    </div>
                  ) : null}

                  <div className="plugin-card-foot">
                    <span className="muted" style={{ fontSize: 11 }}>
                      {item.installed ? '已安装 · ' + item.state : '未安装'}
                    </span>

                    <div className="row" style={{ gap: 6 }}>
                      {item.state === 'AVAILABLE' ? (
                        item.execution_risk === 'high' ? (
                          // A disabled install button still reads as "you could
                          // install this". For a project that ships order
                          // placement, the honest control is no control: say
                          // why, and offer nothing to click.
                          <span className="muted" style={{ fontSize: 11 }} title={item.boundary}>
                            永不安装 · 自带下单能力
                          </span>
                        ) : (
                          <button
                            className="primary"
                            disabled={isActionPending}
                            onClick={() => handleMarketAction(item)}
                          >
                            {isActionPending ? '正在安装…' : '安装'}
                          </button>
                        )
                      ) : null}

                      {item.state === 'INSTALLED' ? (
                        <>
                          <button
                            className="primary"
                            disabled={isActionPending}
                            onClick={() => handleMarketAction(item)}
                          >
                            {isActionPending ? '正在启用…' : '启用'}
                          </button>
                          <button
                            className="ghost"
                            onClick={() => setWizardEntry(item)}
                          >
                            配置
                          </button>
                        </>
                      ) : null}

                      {item.state === 'ENABLED' ? (
                        <>
                          <button
                            className="ghost"
                            onClick={() => setWizardEntry(item)}
                          >
                            配置
                          </button>
                          <button
                            className="ghost"
                            disabled={isActionPending}
                            onClick={() => void (async () => {
                              setActionPendingId(item.plugin_id);
                              try {
                                await api.disablePlugin(item.plugin_id);
                                setNotice('插件「' + (item.name || item.plugin_id) + '」已停用');
                                await refreshAll();
                              } catch (err) {
                                setError(err instanceof Error ? err.message : String(err));
                              } finally {
                                setActionPendingId(null);
                              }
                            })()}
                          >
                            {isActionPending ? '正在停用…' : '停用'}
                          </button>
                        </>
                      ) : null}

                      {item.state === 'DISABLED' ? (
                        <button
                          className="primary"
                          disabled={isActionPending}
                          onClick={() => handleMarketAction(item)}
                        >
                          {isActionPending ? '正在启用…' : '启用'}
                        </button>
                      ) : null}

                      {item.state === 'ERROR' ? (
                        <button
                          className="primary"
                          disabled={isActionPending}
                          onClick={() => handleMarketAction(item)}
                        >
                          重试安装
                        </button>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      ) : null}

      {/* Setup Wizard Modal */}
      {wizardEntry ? (
        <PluginSetupWizard
          entry={wizardEntry}
          onClose={() => setWizardEntry(null)}
          onSuccess={() => void refreshAll()}
        />
      ) : null}

      {/* Detail & Audit Modal */}
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

            <div className="dsh-modal-actions" style={{ justifyContent: 'space-between' }}>
              <button
                className="ghost danger"
                disabled={uninstalling}
                onClick={() => void handleUninstall(detail.plugin_id)}
              >
                {uninstalling ? '正在卸载…' : '卸载插件'}
              </button>
              <button className="primary" onClick={() => setActivePluginId(null)}>完成</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
