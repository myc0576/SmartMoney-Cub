import React, { useState } from 'react';
import {
  Search,
  Filter,
  ArrowUpDown,
  X,
  ShieldAlert,
  Flame,
  CheckCircle2,
  Plus,
  LayoutGrid,
  List,
} from 'lucide-react';
import { ChallengerReview, ColorScheme, TradeAnalysis } from '../types';

interface TradesViewProps {
  trades: TradeAnalysis[];
  reviews: ChallengerReview[];
  selectedTrade: TradeAnalysis | null;
  onSelectTrade: (trade: TradeAnalysis | null) => void;
  colorScheme: ColorScheme;
  onAddRuleToChallenger: (rule: any) => void;
}

export const TradesView: React.FC<TradesViewProps> = ({
  trades,
  reviews,
  selectedTrade,
  onSelectTrade,
  colorScheme,
  onAddRuleToChallenger,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [regimeFilter, setRegimeFilter] = useState('ALL');
  const [winFilter, setWinFilter] = useState<'ALL' | 'WIN' | 'LOSS'>('ALL');
  const [viewMode, setViewMode] = useState<'table' | 'cards'>('table');

  const positiveColor = colorScheme === 'cn' ? 'text-[#f23645]' : 'text-[#089981]';
  const negativeColor = colorScheme === 'cn' ? 'text-[#089981]' : 'text-[#f23645]';

  // 多维筛选
  const filteredTrades = trades.filter((t) => {
    if (searchTerm) {
      const match =
        t.symbol.includes(searchTerm) ||
        t.name.includes(searchTerm) ||
        t.thesis.includes(searchTerm);
      if (!match) return false;
    }
    if (regimeFilter !== 'ALL' && t.regime !== regimeFilter) {
      return false;
    }
    if (winFilter === 'WIN' && t.return_pct < 0) return false;
    if (winFilter === 'LOSS' && t.return_pct >= 0) return false;
    return true;
  });

  // 查出当前选中交易的 AI 杠精质问
  const currentReview = selectedTrade
    ? reviews.find((r) => r.trade_id === selectedTrade.trade_id) || reviews[0]
    : null;

  return (
    <div className="flex-1 flex overflow-hidden relative">
      {/* 主流水展示区 */}
      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto p-5 space-y-4">
        {/* TradeZella 风格过滤工具条 */}
        <div className="bg-[#1e222d] p-3 rounded-xl border border-[#2a2e39] flex flex-wrap items-center justify-between gap-3 select-none">
          <div className="flex flex-wrap items-center gap-2.5">
            {/* 标的搜索框 */}
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 text-[#787b86]" size={13} />
              <input
                type="text"
                placeholder="搜索代码 / 标的 / 理由..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="h-8 pl-8 pr-3 bg-[#131722] border border-[#363a45] rounded-lg text-xs text-[#d1d4dc] placeholder-[#787b86] focus:outline-none focus:border-[#2962ff] w-48"
              />
            </div>

            {/* 情绪周期筛选 */}
            <select
              value={regimeFilter}
              onChange={(e) => setRegimeFilter(e.target.value)}
              className="h-8 px-2.5 bg-[#131722] border border-[#363a45] rounded-lg text-xs text-[#d1d4dc] focus:outline-none focus:border-[#2962ff]"
            >
              <option value="ALL">全部周期 (All)</option>
              <option value="初生">初生期</option>
              <option value="生长">生长主升</option>
              <option value="亢龙">亢龙加速</option>
              <option value="衰退">衰退退潮</option>
              <option value="潜藏">潜藏混沌</option>
            </select>

            {/* 胜负筛选 */}
            <div className="flex items-center gap-1 bg-[#131722] p-0.5 rounded-lg border border-[#363a45] text-xs">
              {(['ALL', 'WIN', 'LOSS'] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setWinFilter(mode)}
                  className={`px-2.5 py-1 rounded text-[11px] font-medium transition-all ${
                    winFilter === mode
                      ? 'bg-[#2962ff] text-white shadow-sm'
                      : 'text-[#787b86] hover:text-[#d1d4dc]'
                  }`}
                >
                  {mode === 'ALL' ? '全部' : mode === 'WIN' ? '盈利单' : '亏损单'}
                </button>
              ))}
            </div>
          </div>

          {/* 右侧：统计概况与视图模式切换 */}
          <div className="flex items-center gap-3">
            <span className="text-xs text-[#787b86] font-mono">
              共 <strong className="text-[#f0f3fa]">{filteredTrades.length}</strong> / {trades.length} 笔交易
            </span>
            <div className="flex items-center gap-1 bg-[#131722] p-0.5 rounded-lg border border-[#363a45]">
              <button
                onClick={() => setViewMode('table')}
                className={`p-1.5 rounded ${viewMode === 'table' ? 'bg-[#2a2e39] text-[#2962ff]' : 'text-[#787b86]'}`}
                title="表格视图"
              >
                <List size={14} />
              </button>
              <button
                onClick={() => setViewMode('cards')}
                className={`p-1.5 rounded ${viewMode === 'cards' ? 'bg-[#2a2e39] text-[#2962ff]' : 'text-[#787b86]'}`}
                title="瀑布流卡片视图"
              >
                <LayoutGrid size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* 模式 1: 紧凑型专业表格 (TradingView Style Table) */}
        {viewMode === 'table' ? (
          <div className="bg-[#1e222d] rounded-xl border border-[#2a2e39] overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-[#d1d4dc]">
                <thead className="bg-[#131722] text-[#787b86] border-b border-[#2a2e39] text-[11px] font-mono uppercase">
                  <tr>
                    <th className="py-2.5 px-3">标的代码/名称</th>
                    <th className="py-2.5 px-3">情绪周期</th>
                    <th className="py-2.5 px-3">买入价 / 离场价</th>
                    <th className="py-2.5 px-3 text-right">收益率 / 盈亏</th>
                    <th className="py-2.5 px-3">纪律得分</th>
                    <th className="py-2.5 px-3">计划防守止损</th>
                    <th className="py-2.5 px-3">违规 / 纪律警报</th>
                    <th className="py-2.5 px-3 text-center">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2a2e39]/60 font-mono">
                  {filteredTrades.map((t) => {
                    const isWin = t.return_pct >= 0;
                    const isSelected = selectedTrade?.trade_id === t.trade_id;
                    return (
                      <tr
                        key={t.trade_id}
                        onClick={() => onSelectTrade(t)}
                        className={`cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-[#2a2e39]/80 border-l-2 border-l-[#2962ff]'
                            : 'hover:bg-[#2a2e39]/40'
                        }`}
                      >
                        <td className="py-2.5 px-3">
                          <div className="font-bold text-[#f0f3fa]">{t.symbol}</div>
                          <div className="text-[11px] text-[#787b86] font-sans truncate max-w-[120px]">
                            {t.name}
                          </div>
                        </td>
                        <td className="py-2.5 px-3 font-sans">
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#131722] text-[#787b86] border border-[#363a45]">
                            {t.regime}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="text-[#f0f3fa]">¥{t.entry_price} &rarr; ¥{t.exit_price}</div>
                          <div className="text-[10px] text-[#787b86]">{t.entry_time.slice(5, 16)}</div>
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <div className={`font-bold text-sm ${isWin ? positiveColor : negativeColor}`}>
                            {isWin ? '+' : ''}{t.return_pct}%
                          </div>
                          <div className="text-[11px] text-[#787b86]">
                            {isWin ? '+' : ''}{t.pnl_amount} 元
                          </div>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className={`text-[11px] px-2 py-0.5 rounded font-medium ${
                            t.discipline_score >= 80
                              ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800'
                              : t.discipline_score >= 60
                              ? 'bg-amber-950/60 text-amber-400 border border-amber-800'
                              : 'bg-rose-950/60 text-rose-400 border border-rose-800'
                          }`}>
                            {t.discipline_score} 分
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          {t.invalidation_price ? (
                            <span className="text-[#787b86]">¥{t.invalidation_price}</span>
                          ) : (
                            <span className="text-[10px] text-rose-400">无防守位</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-sans max-w-[200px]">
                          {t.violations.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {t.violations.map((v, i) => (
                                <span
                                  key={i}
                                  className="text-[10px] px-1.5 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-900/60 truncate"
                                  title={v}
                                >
                                  {v}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-[11px] text-emerald-400 flex items-center gap-1 font-mono">
                              <CheckCircle2 size={12} /> 知行合一
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectTrade(t);
                            }}
                            className="px-2 py-1 rounded bg-[#2a2e39] hover:bg-[#363a45] text-[#2962ff] text-xs font-medium"
                          >
                            复盘质问
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          /* 模式 2: 瀑布流卡片列表 */
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {filteredTrades.map((t) => {
              const isWin = t.return_pct >= 0;
              const isSelected = selectedTrade?.trade_id === t.trade_id;
              return (
                <div
                  key={t.trade_id}
                  onClick={() => onSelectTrade(t)}
                  className={`bg-[#1e222d] p-4 rounded-xl border cursor-pointer transition-all space-y-2.5 ${
                    isSelected
                      ? 'border-[#2962ff] ring-1 ring-[#2962ff]'
                      : 'border-[#2a2e39] hover:border-[#363a45]'
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-sm text-[#f0f3fa]">{t.symbol}</span>
                        <span className="text-xs font-bold text-[#d1d4dc]">{t.name}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#131722] text-[#787b86]">
                          {t.regime}
                        </span>
                      </div>
                      <p className="text-xs text-[#787b86] mt-1 line-clamp-1">{t.thesis || '盘中跟随开仓'}</p>
                    </div>
                    <div className="text-right">
                      <div className={`font-mono font-bold text-base ${isWin ? positiveColor : negativeColor}`}>
                        {isWin ? '+' : ''}{t.return_pct}%
                      </div>
                      <div className="text-[11px] text-[#787b86] font-mono">
                        {isWin ? '+' : ''}{t.pnl_amount} 元
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-2 border-t border-[#2a2e39]/60 text-xs text-[#787b86] font-mono">
                    <span>¥{t.entry_price} &rarr; ¥{t.exit_price}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                      t.discipline_score >= 80 ? 'bg-emerald-950/60 text-emerald-400' : 'bg-rose-950/60 text-rose-400'
                    }`}>
                      纪律: {t.discipline_score}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 右侧滑出式深度复盘抽屉 (Trade Review Slide-over) */}
      {selectedTrade && (
        <div className="w-96 shrink-0 bg-[#1e222d] border-l border-[#2a2e39] flex flex-col h-full z-20 shadow-2xl animate-in slide-in-from-right duration-200">
          {/* 抽屉头部 */}
          <div className="p-4 border-b border-[#2a2e39] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#2962ff]" />
              <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider">
                单笔穿透复盘诊断
              </h3>
            </div>
            <button
              onClick={() => onSelectTrade(null)}
              className="w-7 h-7 rounded-lg hover:bg-[#2a2e39] flex items-center justify-center text-[#787b86] hover:text-[#d1d4dc]"
            >
              <X size={15} />
            </button>
          </div>

          {/* 抽屉滚动内容区 */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
            {/* 标的概况卡 */}
            <div className="p-3.5 rounded-xl bg-[#131722] border border-[#2a2e39] space-y-2">
              <div className="flex justify-between items-start">
                <div>
                  <div className="text-base font-black text-[#f0f3fa] font-mono">
                    {selectedTrade.symbol} {selectedTrade.name}
                  </div>
                  <div className="text-[11px] text-[#787b86] mt-0.5">
                    买入: {selectedTrade.entry_time}
                  </div>
                </div>
                <div className="text-right">
                  <div className={`text-base font-black font-mono ${
                    selectedTrade.return_pct >= 0 ? positiveColor : negativeColor
                  }`}>
                    {selectedTrade.return_pct >= 0 ? '+' : ''}{selectedTrade.return_pct}%
                  </div>
                  <div className="text-[11px] text-[#787b86] font-mono">
                    {selectedTrade.pnl_amount >= 0 ? '+' : ''}{selectedTrade.pnl_amount} 元
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-[#2a2e39] text-[11px] font-mono">
                <div>入场均价: <strong className="text-[#d1d4dc]">¥{selectedTrade.entry_price}</strong></div>
                <div>离场均价: <strong className="text-[#d1d4dc]">¥{selectedTrade.exit_price}</strong></div>
                <div>计划止损: <strong className={selectedTrade.invalidation_price ? 'text-amber-300' : 'text-rose-400'}>
                  {selectedTrade.invalidation_price ? `¥${selectedTrade.invalidation_price}` : '未设防守'}
                </strong></div>
                <div>最大回撤: <strong className="text-rose-400">{selectedTrade.max_adverse_excursion_pct}%</strong></div>
              </div>

              <div className="pt-2 border-t border-[#2a2e39] text-[11px]">
                <span className="text-[#787b86]">买入理由: </span>
                <span className="text-[#d1d4dc]">{selectedTrade.thesis || '无明文逻辑 (凭感觉)'}</span>
              </div>
            </div>

            {/* AI 杠精 · 席位严师冷酷质问 (Challenger Cross-examination) */}
            {currentReview && (
              <div className="p-3.5 rounded-xl bg-gradient-to-b from-rose-950/30 to-[#131722] border border-rose-900/40 space-y-3">
                <div className="flex items-center gap-2">
                  <Flame className="text-rose-400" size={16} />
                  <div>
                    <div className="text-xs font-bold text-rose-300">
                      {currentReview.persona.name}
                    </div>
                    <div className="text-[10px] text-rose-200/60 font-mono">
                      {currentReview.persona.motto}
                    </div>
                  </div>
                </div>

                {/* 当头棒喝金句 */}
                <blockquote className="p-2.5 rounded bg-rose-950/40 border-l-2 border-rose-500 text-[11px] text-rose-200/90 italic leading-relaxed">
                  “{currentReview.critique_quote}”
                </blockquote>

                {/* 灵魂质问三连 */}
                <div className="space-y-1.5">
                  <div className="text-[11px] font-bold text-rose-300 flex items-center gap-1">
                    <ShieldAlert size={12} />
                    <span>盘后灵魂质问:</span>
                  </div>
                  <div className="space-y-1.5">
                    {currentReview.cross_examination_questions.map((q, idx) => (
                      <div key={idx} className="p-2 rounded bg-[#1e222d] border border-rose-900/30 text-[11px] text-[#d1d4dc] leading-relaxed">
                        <strong className="text-rose-400 mr-1">Q{idx + 1}.</strong>
                        {q}
                      </div>
                    ))}
                  </div>
                </div>

                {/* 提炼的候选防御规则 (Challenger Rule Proposal) */}
                {currentReview.proposed_rule && (
                  <div className="p-2.5 rounded-lg bg-[#1e222d] border border-amber-500/30 space-y-2 mt-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono text-amber-400 bg-amber-950/80 px-1.5 py-0.5 rounded border border-amber-800">
                        提炼规则候选: {currentReview.proposed_rule.rule_id}
                      </span>
                      <span className="text-[10px] text-amber-300 font-bold">
                        {currentReview.proposed_rule.title}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#787b86]">
                      {currentReview.proposed_rule.condition}
                    </p>
                    <button
                      onClick={() => onAddRuleToChallenger(currentReview.proposed_rule)}
                      className="w-full py-1.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-xs font-medium flex items-center justify-center gap-1 transition-all"
                    >
                      <Plus size={13} />
                      <span>采纳到 Challenger 候选池</span>
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
