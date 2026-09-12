import React, { useState, useEffect } from 'react';
import { api } from './api';
import { AppDataResponse, ColorScheme, TabKey, TradeAnalysis } from './types';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { WorkbenchView } from './components/WorkbenchView';
import { TradesView } from './components/TradesView';
import { RegimeView } from './components/RegimeView';
import { RulesView } from './components/RulesView';
import { PluginsView } from './components/PluginsView';
import { WorkspaceView } from './components/WorkspaceView';
import { SharePackModal } from './components/SharePackModal';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabKey>('workbench');
  const [colorScheme, setColorScheme] = useState<ColorScheme>('cn'); // 默认 A股红涨绿跌
  const [data, setData] = useState<AppDataResponse | null>(null);
  const [selectedTrade, setSelectedTrade] = useState<TradeAnalysis | null>(null);
  const [isShareModalOpen, setIsShareModalOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      setLoading(true);
      const res = await api.getData();
      setData(res);
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleToggleColorScheme = () => {
    setColorScheme((prev) => (prev === 'cn' ? 'intl' : 'cn'));
  };

  const handleSelectRegime = async (regime: string) => {
    try {
      await api.setRegime(regime);
      await fetchData();
    } catch (e: any) {
      alert('切换情绪周期失败: ' + e.message);
    }
  };

  const handleUploadCsv = async (csvContent: string) => {
    try {
      const res = await api.uploadCsv(csvContent);
      await fetchData();
      setActiveTab('trades');
      alert(`成功加载 ${res.loaded_trades_count || 0} 笔有效平仓交易记录`);
    } catch (e: any) {
      alert('导入交割单失败: ' + e.message);
    }
  };

  const handleResetDemo = async () => {
    if (!confirm('确认恢复预设的典型游资交割单案例吗？')) return;
    try {
      await api.resetDemo();
      await fetchData();
      setSelectedTrade(null);
    } catch (e: any) {
      alert('重置失败: ' + e.message);
    }
  };

  const handleAddRule = async (ruleObj: any) => {
    try {
      await api.addRule(ruleObj);
      await fetchData();
      setActiveTab('rules');
      alert(`规则 [${ruleObj.rule_id}] 已采纳至 Challenger 候选规则池`);
    } catch (e: any) {
      alert('采纳规则失败: ' + e.message);
    }
  };

  const handleRequestPromotion = async (ruleId: string) => {
    try {
      // 第一阶段：向后端发送请求，获取门禁评估结果
      const res = await api.requestPromotion(ruleId);
      if (res.status === 'not_found') {
        alert(`未找到规则: ${ruleId}`);
        return;
      }
      if (res.blockers && res.blockers.length > 0) {
        alert(
          `规则 [${ruleId}] 暂不可晋升为 Champion 现役铁律。\n\n未通过的门禁:\n` +
          res.blockers.map((b: string) => '  - ' + b).join('\n') +
          `\n\n系统严格遵循实战样本与风险硬约束，绝不在 UI 中自动假晋级。`,
        );
        return;
      }

      // 第二阶段：门禁已过，要求人工填写确认审核 note
      const note = prompt(
        `规则 [${ruleId}] 已满足样本数与风险门禁。\n\n请在下方输入本次显式人工审核确认的理由（此 note 将被写入不可变晋级证据包中）：`,
      );
      if (note === null || !note.trim()) {
        alert('已取消或留空说明。Champion 铁律未发生任何变动。');
        return;
      }

      const confirmRes = await api.requestPromotion(ruleId, true, note.trim());
      if (confirmRes.champion_mutated) {
        alert(`恭喜！规则 [${ruleId}] 已正式晋级为 Champion 现役核心铁律！审核记录已归档。`);
        await fetchData();
      } else {
        alert('晋级未成功: ' + ((confirmRes.blockers || []).join(', ') || '未知原因'));
      }
    } catch (e: any) {
      alert('晋升请求失败: ' + e.message);
    }
  };

  if (loading && !data) {
    return (
      <div className="min-h-screen bg-[#131722] text-[#d1d4dc] flex flex-col items-center justify-center font-mono text-xs gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-[#2962ff] border-t-transparent animate-spin" />
        <span>SMARTMONEY-CUB TERMINAL INITIALIZING...</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-[#131722] text-[#d1d4dc] flex flex-col items-center justify-center text-xs gap-2">
        <div className="text-rose-400 font-bold">无法连接本地复盘服务</div>
        <button onClick={fetchData} className="px-3 py-1 bg-[#2a2e39] rounded border border-[#363a45]">
          重试
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#131722] text-[#d1d4dc]">
      {/* 极窄左侧边栏 */}
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        colorScheme={colorScheme}
        onToggleColorScheme={handleToggleColorScheme}
      />

      {/* 主界面内容区 */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* 顶部状态栏 */}
        <Header
          activeTab={activeTab}
          activeRegime={data.active_regime}
          regimeInfo={data.regime_info}
          regimePhases={data.regime_phases}
          dataOrigin={data.data_origin}
          onSelectRegime={handleSelectRegime}
          onUploadCsv={handleUploadCsv}
          onResetDemo={handleResetDemo}
          onOpenShareModal={() => setIsShareModalOpen(true)}
        />

        {/* 页面视图路由 */}
        <main className="flex-1 flex overflow-hidden">
          {activeTab === 'workbench' && (
            <WorkbenchView
              summary={data.report.summary}
              trades={data.report.analyzed_trades}
              needsReview={data.needs_review}
              colorScheme={colorScheme}
              onSelectTrade={(t) => {
                setSelectedTrade(t);
                setActiveTab('trades');
              }}
              onViewAllTrades={() => setActiveTab('trades')}
            />
          )}

          {activeTab === 'trades' && (
            <TradesView
              trades={data.report.analyzed_trades}
              reviews={data.challenger_reviews}
              selectedTrade={selectedTrade}
              onSelectTrade={setSelectedTrade}
              colorScheme={colorScheme}
              onAddRuleToChallenger={handleAddRule}
            />
          )}

          {activeTab === 'regime' && (
            <RegimeView
              activeRegime={data.active_regime}
              regimePhases={data.regime_phases}
              onSelectRegime={handleSelectRegime}
            />
          )}

          {activeTab === 'rules' && (
            <RulesView
              champions={data.rules.champions}
              challengers={data.rules.challengers}
              onRequestPromotion={handleRequestPromotion}
            />
          )}

          {activeTab === 'plugins' && <PluginsView />}

          {activeTab === 'workspace' && <WorkspaceView />}
        </main>
      </div>

      {/* 匿名分享包弹窗 */}
      <SharePackModal
        isOpen={isShareModalOpen}
        onClose={() => setIsShareModalOpen(false)}
      />
    </div>
  );
};
