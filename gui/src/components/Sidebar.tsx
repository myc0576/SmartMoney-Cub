import React from 'react';
import {
  LayoutDashboard,
  ReceiptText,
  Compass,
  ShieldCheck,
  Blocks,
  Database,
  ArrowUpDown,
} from 'lucide-react';
import { ColorScheme, TabKey } from '../types';

interface SidebarProps {
  activeTab: TabKey;
  onSelectTab: (tab: TabKey) => void;
  colorScheme: ColorScheme;
  onToggleColorScheme: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  colorScheme,
  onToggleColorScheme,
}) => {
  const navItems = [
    { id: 'workbench' as TabKey, label: '工作台 (TradeZella 看板)', icon: LayoutDashboard },
    { id: 'trades' as TabKey, label: '交割单与复盘瀑布流', icon: ReceiptText },
    { id: 'regime' as TabKey, label: '易经情绪罗盘时钟', icon: Compass },
    { id: 'rules' as TabKey, label: '规则进化 (Champion/Challenger)', icon: ShieldCheck },
    { id: 'plugins' as TabKey, label: '生态与插件配置 (DSH)', icon: Blocks },
    { id: 'workspace' as TabKey, label: '本地 SQLite 数据集', icon: Database },
  ];

  return (
    <aside className="w-14 shrink-0 bg-[#131722] border-r border-[#2a2e39] flex flex-col items-center justify-between py-3 z-40 select-none">
      <div className="flex flex-col items-center gap-4">
        <div
          onClick={() => onSelectTab('workbench')}
          className="w-9 h-9 rounded-lg bg-[#1e222d] border border-[#363a45] hover:border-[#2962ff] flex items-center justify-center cursor-pointer transition-all shadow-md group"
          title="SmartMoney-Cub 首页"
        >
          <span className="text-lg transition-transform group-hover:scale-110">🐻</span>
        </div>

        <nav className="flex flex-col gap-1.5 mt-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`relative w-10 h-10 rounded-lg flex items-center justify-center transition-all group ${
                  isActive
                    ? 'bg-[#2962ff] text-white shadow-sm shadow-[#2962ff]/30'
                    : 'text-[#787b86] hover:text-[#d1d4dc] hover:bg-[#2a2e39]/60'
                }`}
                title={item.label}
              >
                <Icon size={18} strokeWidth={isActive ? 2.2 : 1.8} />
                <div className="absolute left-14 px-2.5 py-1 bg-[#1e222d] text-[#d1d4dc] border border-[#363a45] text-xs rounded whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl font-medium">
                  {item.label}
                </div>
              </button>
            );
          })}
        </nav>
      </div>

      <div className="flex flex-col items-center gap-2.5">
        <button
          onClick={onToggleColorScheme}
          className="w-10 h-10 rounded-lg bg-[#1e222d] border border-[#363a45] hover:border-[#787b86] flex flex-col items-center justify-center text-[10px] text-[#787b86] hover:text-[#d1d4dc] transition-all relative group"
          title={`当前涨跌配色: ${colorScheme === 'cn' ? 'A股习惯 (红涨绿跌)' : '国际习惯 (绿涨红跌)'}，点击切换`}
        >
          <ArrowUpDown size={13} className="text-[#2962ff]" />
          <span className="font-bold text-[9px] mt-0.5 font-mono">
            {colorScheme === 'cn' ? 'CN' : 'INTL'}
          </span>
          <div className="absolute left-14 px-2.5 py-1 bg-[#1e222d] text-[#d1d4dc] border border-[#363a45] text-xs rounded whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-xl">
            切换配色: {colorScheme === 'cn' ? 'A股习惯 (红涨绿跌)' : '国际习惯 (绿涨红跌)'}
          </div>
        </button>

        <div
          className="w-8 h-8 rounded-full bg-emerald-950/60 border border-emerald-500/40 flex items-center justify-center text-emerald-400 cursor-help relative group"
          title="只读契约锁定: READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
        >
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <div className="absolute left-14 bottom-0 px-3 py-1.5 bg-[#1e222d] text-emerald-300 border border-emerald-500/40 text-xs rounded whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50 shadow-2xl font-mono">
            READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
            <div className="text-[10px] text-[#787b86] mt-0.5 font-sans">
              已启用绝对只读安全保护，禁止下单/撤单/账户自动化
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};
