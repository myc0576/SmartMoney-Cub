import React, { useState, useEffect } from 'react';
import {
  Blocks,
  Puzzle,
  Layers,
  Shield,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Power,
  RotateCcw,
  Download,
  FolderPlus,
} from 'lucide-react';
import { api } from '../api';
import { PluginCatalogEntry, PluginItem, ProfileItem } from '../types';

export const PluginsView: React.FC = () => {
  const [plugins, setPlugins] = useState<PluginItem[]>([]);
  const [catalog, setCatalog] = useState<PluginCatalogEntry[]>([]);
  const [activeProfile, setActiveProfile] = useState('default-offline');
  const [profiles, setProfiles] = useState<Record<string, ProfileItem>>({});
  const [installPath, setInstallPath] = useState('');
  const [installMsg, setInstallMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);
  const [loading, setLoading] = useState(false);

  const loadAll = async () => {
    try {
      setLoading(true);
      const [pluginsRes, catalogRes, profilesRes] = await Promise.all([
        api.getPlugins(),
        api.getPluginCatalog(),
        api.getProfiles(),
      ]);
      setPlugins(pluginsRes.plugins || []);
      setCatalog(catalogRes.entries || []);
      setActiveProfile(profilesRes.active_profile || 'default-offline');
      setProfiles(profilesRes.profiles || {});
    } catch (e: any) {
      console.error('Failed to load plugins config:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleToggle = async (pluginId: string, currentEnabled: boolean) => {
    try {
      await api.togglePlugin(pluginId, !currentEnabled);
      await loadAll();
    } catch (e: any) {
      alert('切换状态失败: ' + e.message);
    }
  };

  const handleSwitchProfile = async (profileName: string) => {
    try {
      await api.switchProfile(profileName);
      await loadAll();
    } catch (e: any) {
      alert('切换 Profile 失败: ' + e.message);
    }
  };

  const handleInstallLocal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!installPath.trim()) return;
    setInstallMsg(null);
    try {
      const res = await api.installPlugin(installPath.trim());
      if (res.status === 'ok') {
        setInstallMsg({ type: 'ok', text: '本地插件注册成功 (已默认置为 DISABLED 状态，可在右侧按需启用)' });
        setInstallPath('');
        await loadAll();
      } else {
        setInstallMsg({ type: 'err', text: res.error?.message || '注册失败' });
      }
    } catch (e: any) {
      setInstallMsg({ type: 'err', text: e.message || '安装请求失败' });
    }
  };

  const currentProfileObj = profiles[activeProfile];

  // 能力槽位映射
  const capabilitySeams = [
    { key: 'trade_import', title: '交割单流水导入 (trade_import)', desc: '标准化同花顺/券商原始成交记录并生成 T+1 持仓' },
    { key: 'market_context', title: '市场行情上下文 (market_context)', desc: '提供周期情绪阶段、涨跌停统计与板块梯队' },
    { key: 'reviewer', title: '复盘诊断观察员 (reviewer)', desc: '生成买卖点执行力与知行合一扣分诊断' },
    { key: 'challenger', title: '反方严师质问 (challenger)', desc: '对严重亏损与违规交易发起灵魂三问并提炼候选规则' },
    { key: 'evaluator', title: '回测与样本评估 (evaluator)', desc: '对候选防御规则进行 point-in-time 样本门禁审核' },
    { key: 'report_renderer', title: '复盘报告渲染 (report_renderer)', desc: '生成本地 Markdown 记忆与静态复盘分享包' },
  ];

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">
      {/* 顶部 Profile 管理器 (DeepSeek Harness 核心架构) */}
      <div className="bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] space-y-3 shadow-sm">
        <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-3">
          <div className="flex items-center gap-2">
            <Layers className="text-[#2962ff]" size={16} />
            <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider">
              Profile 组合配置 (DSH Composition)
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#787b86]">当前 Profile:</span>
            <div className="flex items-center gap-1 bg-[#131722] p-1 rounded-lg border border-[#363a45]">
              {Object.keys(profiles).map((name) => (
                <button
                  key={name}
                  onClick={() => handleSwitchProfile(name)}
                  className={`px-2.5 py-1 rounded text-xs font-mono font-medium transition-all ${
                    activeProfile === name
                      ? 'bg-[#2962ff] text-white shadow'
                      : 'text-[#787b86] hover:text-[#d1d4dc] hover:bg-[#2a2e39]'
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 权限安全审计指示条 */}
        {currentProfileObj && (
          <div className="p-3 rounded-lg bg-[#131722] border border-[#2a2e39] flex flex-wrap items-center justify-between gap-3 text-xs">
            <p className="text-[#787b86] text-[11px] max-w-xl leading-relaxed">
              {currentProfileObj.description}
            </p>
            <div className="flex items-center gap-3 font-mono text-[11px]">
              <span className="flex items-center gap-1 text-[#d1d4dc]">
                <Shield size={12} className={currentProfileObj.allow_network ? 'text-amber-400' : 'text-emerald-400'} />
                <span>网络: {currentProfileObj.allow_network ? '已授权 (Opt-in)' : '离线锁定 (Off)'}</span>
              </span>
              <span className="flex items-center gap-1 text-[#d1d4dc]">
                <Shield size={12} className={currentProfileObj.allow_external_llm ? 'text-amber-400' : 'text-emerald-400'} />
                <span>外部模型: {currentProfileObj.allow_external_llm ? '已授权' : '默认禁用'}</span>
              </span>
              <span className="flex items-center gap-1 text-emerald-400">
                <CheckCircle2 size={12} />
                <span>绝对只读: ON</span>
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 主分栏：左侧插件生态市场 (Inventory) + 右侧已安装插件与挂载图谱 (Manager) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* 左侧：精选生态项目与本地注册 (7 Cols) */}
        <div className="lg:col-span-7 space-y-4">
          {/* 本地插件注册框 */}
          <div className="bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-[#f0f3fa]">
              <FolderPlus size={15} className="text-[#2962ff]" />
              <span>本地插件注册 (Local Plugin Registration)</span>
            </div>
            <p className="text-[11px] text-[#787b86]">
              系统支持接入本地目录或已安装包（遵循 DSH 插件规范）。遵循安全准则，严禁自动从远程 URL 下载未经验证的代码。
            </p>
            <form onSubmit={handleInstallLocal} className="flex gap-2">
              <input
                type="text"
                placeholder="输入本地插件路径 (例如 ./examples/toy_plugin 或 my-plugin)"
                value={installPath}
                onChange={(e) => setInstallPath(e.target.value)}
                className="flex-1 h-8 px-3 bg-[#131722] border border-[#363a45] rounded-lg text-xs text-[#d1d4dc] placeholder-[#787b86] focus:outline-none focus:border-[#2962ff]"
              />
              <button
                type="submit"
                className="h-8 px-3.5 rounded bg-[#2962ff] hover:bg-[#2962ff]/80 text-white text-xs font-medium transition-all shadow shrink-0"
              >
                注册插件
              </button>
            </form>
            {installMsg && (
              <div className={`p-2.5 rounded text-xs leading-relaxed ${
                installMsg.type === 'ok'
                  ? 'bg-emerald-950/40 text-emerald-300 border border-emerald-500/40'
                  : 'bg-rose-950/40 text-rose-300 border border-rose-500/40'
              }`}>
                {installMsg.text}
              </div>
            )}
          </div>

          {/* 插件目录与开源交易项目列表 (Plugin Inventory) */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider flex items-center gap-1.5">
                <Puzzle size={13} className="text-[#2962ff]" />
                <span>精选交易开源项目接入清单 ({catalog.length})</span>
              </h3>
              <span className="text-[11px] text-[#787b86]">按需通过插件接入复盘</span>
            </div>

            <div className="space-y-2.5 max-h-[520px] overflow-y-auto pr-1">
              {catalog.map((item) => (
                <div
                  key={item.project}
                  className="bg-[#1e222d] p-3.5 rounded-xl border border-[#2a2e39] hover:border-[#363a45] transition-all space-y-2 text-xs"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <a
                          href={item.repo}
                          target="_blank"
                          rel="noreferrer"
                          className="font-bold text-[#f0f3fa] hover:text-[#2962ff] flex items-center gap-1"
                        >
                          <span>{item.project}</span>
                          <ExternalLink size={11} className="text-[#787b86]" />
                        </a>
                        <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono border ${
                          item.level === 'adapter'
                            ? 'bg-[#2962ff]/15 text-[#2962ff] border-[#2962ff]/30'
                            : 'bg-[#131722] text-[#787b86] border-[#363a45]'
                        }`}>
                          {item.level}
                        </span>
                      </div>
                      <div className="text-[11px] text-[#787b86] mt-0.5 font-mono">
                        开源协议: {item.license} · 维护状态: {item.maintained}
                      </div>
                    </div>

                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono shrink-0 ${
                      item.execution_risk === 'high'
                        ? 'bg-rose-950/60 text-rose-300 border border-rose-800'
                        : item.execution_risk === 'medium'
                        ? 'bg-amber-950/60 text-amber-300 border border-amber-800'
                        : 'bg-[#131722] text-[#787b86] border border-[#363a45]'
                    }`}>
                      风险: {item.execution_risk}
                    </span>
                  </div>

                  <p className="text-[#787b86] text-[11px] leading-relaxed bg-[#131722] p-2 rounded border border-[#2a2e39]/60">
                    <strong className="text-[#d1d4dc]">安全边界: </strong>
                    {item.boundary}
                  </p>

                  {item.capabilities.length > 0 && (
                    <div className="flex flex-wrap gap-1 items-center pt-1 text-[10px] font-mono">
                      <span className="text-[#50535e]">可提供能力:</span>
                      {item.capabilities.map((c) => (
                        <span key={c} className="px-1.5 py-0.5 rounded bg-[#2a2e39] text-[#d1d4dc]">
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 右侧：已挂载插件控制台与能力图谱 (5 Cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* 已安装插件列表 */}
          <div className="bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-[#2a2e39]/60">
              <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider flex items-center gap-1.5">
                <Blocks size={13} className="text-[#2962ff]" />
                <span>已安装插件状态 ({plugins.length})</span>
              </h3>
              <button
                onClick={loadAll}
                className="text-[11px] text-[#787b86] hover:text-[#d1d4dc] flex items-center gap-1"
                title="刷新插件状态"
              >
                <RotateCcw size={11} />
                <span>刷新</span>
              </button>
            </div>

            <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
              {plugins.length > 0 ? (
                plugins.map((p) => {
                  const isActive = p.state === 'ACTIVE';
                  return (
                    <div
                      key={p.plugin_id}
                      className="p-3 rounded-lg bg-[#131722] border border-[#2a2e39] flex items-center justify-between gap-3 text-xs"
                    >
                      <div className="space-y-0.5 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-[#f0f3fa] truncate">
                            {p.plugin_id}
                          </span>
                          <span className="text-[10px] text-[#787b86] font-mono">v{p.version}</span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] font-mono">
                          <span className={`px-1.5 py-0.2 rounded ${
                            isActive
                              ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                              : 'bg-slate-800 text-slate-400 border border-slate-700'
                          }`}>
                            {p.state}
                          </span>
                          <span className="text-[#50535e]">隔离: {p.isolation}</span>
                        </div>
                      </div>

                      {/* 启用/禁用开关联动 */}
                      <button
                        onClick={() => handleToggle(p.plugin_id, isActive)}
                        className={`px-2.5 py-1 rounded text-xs font-medium flex items-center gap-1 transition-all shrink-0 ${
                          isActive
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30'
                            : 'bg-[#2a2e39] text-[#787b86] border border-[#363a45] hover:text-[#d1d4dc]'
                        }`}
                        title={isActive ? '点击禁用插件并回滚服务引用' : '点击启用插件'}
                      >
                        <Power size={11} />
                        <span>{isActive ? '已启用' : '已停用'}</span>
                      </button>
                    </div>
                  );
                })
              ) : (
                <div className="py-6 text-center text-xs text-[#787b86]">
                  暂无已安装插件，可在左侧注册本地插件
                </div>
              )}
            </div>
          </div>

          {/* 能力挂载图谱 (Capability Seams Map) */}
          <div className="bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] space-y-3">
            <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider pb-2 border-b border-[#2a2e39]/60">
              能力服务挂载图谱 (Capability Seams)
            </h3>
            <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
              {capabilitySeams.map((seam) => {
                // 判断当前是否有 ACTIVE 的插件提供此能力
                const provider = plugins.find(
                  (p) => p.state === 'ACTIVE' && p.capabilities.includes(seam.key)
                );
                return (
                  <div
                    key={seam.key}
                    className="p-2.5 rounded-lg bg-[#131722] border border-[#2a2e39] flex items-center justify-between gap-3 text-xs"
                  >
                    <div className="min-w-0">
                      <div className="font-bold text-[#d1d4dc] truncate">{seam.title}</div>
                      <div className="text-[10px] text-[#787b86] truncate">{seam.desc}</div>
                    </div>
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded shrink-0 ${
                      provider
                        ? 'bg-[#2962ff]/20 text-[#2962ff] border border-[#2962ff]/40 font-bold'
                        : 'bg-[#2a2e39] text-[#50535e]'
                    }`}>
                      {provider ? provider.plugin_id : '离线核心默认'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
