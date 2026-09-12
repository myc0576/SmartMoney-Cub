import React, { useRef } from 'react';
import { Upload, RotateCcw, Share2, Sparkles } from 'lucide-react';
import { RegimeInfo, TabKey } from '../types';

interface HeaderProps {
  activeTab: TabKey;
  activeRegime: string;
  regimeInfo?: RegimeInfo;
  regimePhases: Record<string, RegimeInfo>;
  dataOrigin: 'demo_fixture' | 'user_csv';
  onSelectRegime: (regime: string) => void;
  onUploadCsv: (content: string) => void;
  onResetDemo: () => void;
  onOpenShareModal: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  activeRegime,
  regimeInfo,
  regimePhases,
  dataOrigin,
  onSelectRegime,
  onUploadCsv,
  onResetDemo,
  onOpenShareModal,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const tabTitles: Record<TabKey, { title: string; subtitle: string }> = {
    workbench: { title: '复盘总览看板', subtitle: 'TradeZella 风格多维统计大盘与盈亏日历' },
    trades: { title: '交割单与交易体检', subtitle: 'A股短线周期契合诊断与流水穿透复盘' },
    regime: { title: '易经情绪周期罗盘', subtitle: '初生·生长·亢龙·衰退·潜藏五阶段操盘心法' },
    rules: { title: '规则进化矩阵', subtitle: 'Champion 现役铁律库与 Challenger 候选防御规则' },
    plugins: { title: '生态插件配置中心', subtitle: 'DeepSeek Harness 架构：Everything is a Plugin' },
    workspace: { title: '本地 SQLite 数据集', subtitle: '离线不可变证据包与 D1/D3 结果回放' },
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (content) {
        onUploadCsv(content);
      }
    };
    reader.readAsText(file);
    if (e.target) e.target.value = '';
  };

  const currentMeta = tabTitles[activeTab] || { title: '复盘控制台', subtitle: '' };

  return (
    <header className="h-14 bg-[#1e222d] border-b border-[#2a2e39] px-5 flex items-center justify-between gap-4 shrink-0 select-none">
      {/* 隐藏的文件上传 input */}
      <input
        type="file"
        ref={fileInputRef}
        accept=".csv,.txt"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* 左侧模块标题与数据来源标记 */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-bold text-[#f0f3fa] tracking-tight truncate">
              {currentMeta.title}
            </h2>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#131722] text-[#787b86] border border-[#363a45]">
              v0.2.0
            </span>
          </div>
          <span className="text-[11px] text-[#787b86] hidden sm:block truncate">
            {currentMeta.subtitle}
          </span>
        </div>

        {/* 数据来源 Badge */}
        {dataOrigin === 'demo_fixture' ? (
          <span
            className="text-[10px] font-medium px-2 py-0.5 rounded bg-amber-950/40 text-amber-300 border border-amber-500/40 flex items-center gap-1 cursor-help shrink-0"
            title="当前为内置演示交割单案例，用于流程体验。导入真实 CSV 后将自动转为真实统计。"
          >
            <Sparkles size={11} />
            <span>DEMO 案例数据</span>
          </span>
        ) : (
          <span
            className="text-[10px] font-medium px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-500/40 flex items-center gap-1 shrink-0"
            title="数据来源：本地导入的 CSV 交割单"
          >
            <span>真实交割单</span>
          </span>
        )}
      </div>

      {/* 中间/右侧：情绪周期胶囊与快捷操作 */}
      <div className="flex items-center gap-3 shrink-0">
        {/* 情绪周期选择 Pill */}
        <div className="hidden lg:flex items-center gap-1 bg-[#131722] p-1 rounded-lg border border-[#2a2e39]">
          <span className="text-[11px] text-[#787b86] px-1.5 font-medium">当前情绪:</span>
          {Object.entries(regimePhases).map(([name, phase]) => {
            const isSelected = activeRegime === name;
            return (
              <button
                key={name}
                onClick={() => onSelectRegime(name)}
                className={`px-2 py-0.5 rounded text-xs font-medium transition-all ${
                  isSelected
                    ? 'bg-[#2962ff] text-white shadow-sm'
                    : 'text-[#787b86] hover:text-[#d1d4dc] hover:bg-[#2a2e39]'
                }`}
                title={phase.description}
              >
                {name}
              </button>
            );
          })}
        </div>

        {/* 操作按钮组 */}
        <div className="flex items-center gap-2">
          {/* 上传 CSV */}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="h-8 px-3 rounded bg-[#2a2e39] hover:bg-[#363a45] text-xs text-[#d1d4dc] hover:text-white font-medium border border-[#363a45] flex items-center gap-1.5 transition-all shadow-sm"
            title="上传同花顺或券商交割单 CSV 文件"
          >
            <Upload size={13} className="text-[#2962ff]" />
            <span>导入交割单</span>
          </button>

          {/* 恢复预设演示案例 */}
          {dataOrigin !== 'demo_fixture' && (
            <button
              onClick={onResetDemo}
              className="h-8 px-2.5 rounded bg-[#1e222d] hover:bg-[#2a2e39] text-xs text-[#787b86] hover:text-[#d1d4dc] border border-[#363a45] flex items-center gap-1 transition-all"
              title="清除当前导入，恢复内置典型游资复盘案例"
            >
              <RotateCcw size={12} />
              <span className="hidden sm:inline">重置案例</span>
            </button>
          )}

          {/* 生成匿名复盘分享包 */}
          <button
            onClick={onOpenShareModal}
            className="h-8 px-3 rounded bg-[#10b981]/15 hover:bg-[#10b981]/25 text-emerald-400 hover:text-emerald-300 text-xs font-medium border border-emerald-500/40 flex items-center gap-1.5 transition-all shadow-sm"
            title="生成经过严格隐私脱敏的离线静态 HTML 复盘分享包"
          >
            <Share2 size={13} />
            <span>分享复盘包</span>
          </button>
        </div>
      </div>
    </header>
  );
};
