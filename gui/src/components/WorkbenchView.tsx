import React, { useState } from 'react';
import {
  TrendingUp,
  Percent,
  Scale,
  Award,
  AlertTriangle,
  Calendar as CalendarIcon,
  ChevronRight,
  Info,
} from 'lucide-react';
import { ColorScheme, PortfolioSummary, TradeAnalysis } from '../types';

interface WorkbenchViewProps {
  summary: PortfolioSummary;
  trades: TradeAnalysis[];
  needsReview: any[];
  colorScheme: ColorScheme;
  onSelectTrade: (trade: TradeAnalysis) => void;
  onViewAllTrades: () => void;
}

export const WorkbenchView: React.FC<WorkbenchViewProps> = ({
  summary,
  trades,
  needsReview,
  colorScheme,
  onSelectTrade,
  onViewAllTrades,
}) => {
  const [curveRange, setCurveRange] = useState<'ALL' | '30D' | '10D'>('ALL');
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  // 根据当前配色方案决定正/负颜色类名
  const positiveColor = colorScheme === 'cn' ? 'text-[#f23645]' : 'text-[#089981]';
  const negativeColor = colorScheme === 'cn' ? 'text-[#089981]' : 'text-[#f23645]';
  const positiveBg = colorScheme === 'cn' ? 'bg-[#f23645]/10 border-[#f23645]/30' : 'bg-[#089981]/10 border-[#089981]/30';
  const negativeBg = colorScheme === 'cn' ? 'bg-[#089981]/10 border-[#089981]/30' : 'bg-[#f23645]/10 border-[#f23645]/30';

  // 计算累积盈亏点列（用于 SVG 净值曲线）
  let runningPnl = 0;
  const equityPoints = trades.map((t, idx) => {
    runningPnl += t.pnl_amount;
    return {
      index: idx + 1,
      date: t.entry_time.split(' ')[0],
      tradeId: t.trade_id,
      symbol: t.symbol,
      pnl: t.pnl_amount,
      cumPnl: Math.round(runningPnl),
    };
  });

  const filteredEquity = curveRange === '10D'
    ? equityPoints.slice(-10)
    : curveRange === '30D'
    ? equityPoints.slice(-30)
    : equityPoints;

  // SVG 坐标映射
  const minCum = Math.min(0, ...filteredEquity.map((p) => p.cumPnl));
  const maxCum = Math.max(100, ...filteredEquity.map((p) => p.cumPnl));
  const rangeY = maxCum - minCum || 1;
  const width = 600;
  const height = 180;
  const padding = 20;

  const svgCoords = filteredEquity.map((p, i) => {
    const x = padding + (i / Math.max(1, filteredEquity.length - 1)) * (width - padding * 2);
    const y = height - padding - ((p.cumPnl - minCum) / rangeY) * (height - padding * 2);
    return { x, y, ...p };
  });

  const pathD = svgCoords.length > 0
    ? `M ${svgCoords[0].x} ${svgCoords[0].y} ` +
      svgCoords.slice(1).map((p) => `L ${p.x} ${p.y}`).join(' ')
    : '';

  // 聚类每日盈亏（用于 TradeZella 风格日历热力图）
  const dailyPnL: Record<string, { pnl: number; count: number; trades: TradeAnalysis[] }> = {};
  trades.forEach((t) => {
    const day = t.entry_time.split(' ')[0];
    if (!dailyPnL[day]) dailyPnL[day] = { pnl: 0, count: 0, trades: [] };
    dailyPnL[day].pnl += t.pnl_amount;
    dailyPnL[day].count += 1;
    dailyPnL[day].trades.push(t);
  });

  const calendarDays = Object.entries(dailyPnL).sort(([a], [b]) => a.localeCompare(b));

  const isNetPositive = summary.total_profit >= summary.total_loss;
  const netPnlTotal = Math.round(summary.total_profit - summary.total_loss);

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5">
      {/* 待核对异常警告 (needs_review) */}
      {needsReview && needsReview.length > 0 && (
        <div className="bg-rose-950/20 border border-rose-500/40 rounded-xl p-4 flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="text-rose-400 shrink-0 mt-0.5" size={18} />
            <div>
              <h4 className="text-xs font-bold text-rose-300">
                交割单存在 {needsReview.length} 处歧义记录，已触发严格只读审查保护 (needs_review)
              </h4>
              <p className="text-[11px] text-rose-200/70 mt-1">
                系统拒绝盲目 FIFO 配对以防止伪造交易。异常项（如先卖后买、T+1违规）已被阻断并不计入统计。
              </p>
              <div className="flex flex-wrap gap-2 mt-2">
                {needsReview.slice(0, 4).map((issue, idx) => (
                  <span
                    key={idx}
                    className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-800/50"
                  >
                    {issue.code}: {issue.detail}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <button
            onClick={onViewAllTrades}
            className="text-xs font-medium text-rose-400 hover:text-rose-300 underline shrink-0"
          >
            查看详情
          </button>
        </div>
      )}

      {/* 顶部 6 个核心 KPI 卡片 (TradeZella 风格) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* 1. 净收益 Net P&L */}
        <div className="bg-[#1e222d] p-3.5 rounded-xl border border-[#2a2e39] hover:border-[#363a45] transition-all flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#787b86] text-xs">
            <span>净收益 Net P&L</span>
            <TrendingUp size={13} className={isNetPositive ? positiveColor : negativeColor} />
          </div>
          <div className="mt-2">
            <div className={`text-lg font-black font-mono tracking-tight ${isNetPositive ? positiveColor : negativeColor}`}>
              {netPnlTotal >= 0 ? '+' : ''}{netPnlTotal.toLocaleString()} <span className="text-[11px] font-sans">元</span>
            </div>
            <div className="text-[11px] text-[#787b86] mt-0.5 font-mono">
              胜额 ¥{Math.round(summary.total_profit).toLocaleString()} / 亏额 ¥{Math.round(summary.total_loss).toLocaleString()}
            </div>
          </div>
        </div>

        {/* 2. 胜率 Win Rate % */}
        <div className="bg-[#1e222d] p-3.5 rounded-xl border border-[#2a2e39] hover:border-[#363a45] transition-all flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#787b86] text-xs">
            <span>实战胜率</span>
            <Percent size={13} className="text-[#2962ff]" />
          </div>
          <div className="mt-2">
            <div className={`text-lg font-black font-mono tracking-tight ${summary.win_rate >= 50 ? positiveColor : negativeColor}`}>
              {summary.win_rate || 0}%
            </div>
            <div className="text-[11px] text-[#787b86] mt-0.5 font-mono">
              胜 {summary.win_count || 0} 笔 · 负 {summary.loss_count || 0} 笔
            </div>
          </div>
        </div>

        {/* 3. 盈亏比 Profit Factor */}
        <div className="bg-[#1e222d] p-3.5 rounded-xl border border-[#2a2e39] hover:border-[#363a45] transition-all flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#787b86] text-xs">
            <span>盈亏比 (PF)</span>
            <Scale size={13} className="text-[#2962ff]" />
          </div>
          <div className="mt-2">
            <div className="text-lg font-black font-mono text-[#f0f3fa]">
              {summary.profit_loss_ratio || 0}
            </div>
            <div className="text-[11px] text-[#787b86] mt-0.5">
              期望值: {summary.profit_loss_ratio >= 1.8 ? '极其优秀' : '需控制亏损'}
            </div>
          </div>
        </div>

        {/* 4. 知行合一纪律评分 */}
        <div className="bg-[#1e222d] p-3.5 rounded-xl border border-[#2a2e39] hover:border-[#363a45] transition-all flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#787b86] text-xs">
            <span>知行合一评分</span>
            <Award size={13} className="text-amber-400" />
          </div>
          <div className="mt-2">
            <div className={`text-lg font-black font-mono ${
              summary.avg_discipline_score >= 80 ? 'text-[#089981]' : summary.avg_discipline_score >= 60 ? 'text-amber-400' : 'text-rose-400'
            }`}>
              {summary.avg_discipline_score || 0} <span className="text-xs font-sans text-[#787b86]">/ 100</span>
            </div>
            <div className="text-[11px] text-[#787b86] mt-0.5 flex items-center gap-1">
              <span>评级:</span>
              <span className="font-bold text-amber-300 font-mono">{summary.grade_tag || 'B'}</span>
            </div>
          </div>
        </div>

        {/* 5. 违规操作总数 */}
        <div className="bg-[#1e222d] p-3.5 rounded-xl border border-[#2a2e39] hover:border-[#363a45] transition-all flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#787b86] text-xs">
            <span>违规操作数</span>
            <AlertTriangle size={13} className="text-rose-400" />
          </div>
          <div className="mt-2">
            <div className={`text-lg font-black font-mono ${summary.total_violations > 0 ? 'text-rose-400' : 'text-[#089981]'}`}>
              {summary.total_violations || 0} <span className="text-xs font-sans text-[#787b86]">次</span>
            </div>
            <div className="text-[11px] text-[#787b86] mt-0.5 truncate">
              {summary.total_violations > 0 ? '存在死扛或乱开仓' : '严格执行铁律'}
            </div>
          </div>
        </div>

        {/* 6. 总流水笔数 */}
        <div className="bg-[#1e222d] p-3.5 rounded-xl border border-[#2a2e39] hover:border-[#363a45] transition-all flex flex-col justify-between">
          <div className="flex items-center justify-between text-[#787b86] text-xs">
            <span>总平仓流水</span>
            <CalendarIcon size={13} className="text-[#787b86]" />
          </div>
          <div className="mt-2">
            <div className="text-lg font-black font-mono text-[#f0f3fa]">
              {summary.total_trades || 0} <span className="text-xs font-sans text-[#787b86]">笔</span>
            </div>
            <div className="text-[11px] text-[#787b86] mt-0.5">
              已对齐 T+1 费率
            </div>
          </div>
        </div>
      </div>

      {/* 中部分栏：累积 P&L 净值曲线 + TradeZella 月度日历热力图 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* 累积收益净值曲线 (7 Cols) */}
        <div className="lg:col-span-7 bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] flex flex-col justify-between shadow-sm">
          <div className="flex items-center justify-between pb-3 border-b border-[#2a2e39]/60">
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider">
                累积净收益曲线 (Cumulative Equity Curve)
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#131722] text-[#787b86]">
                真实成交复现
              </span>
            </div>
            <div className="flex items-center gap-1 bg-[#131722] p-0.5 rounded border border-[#2a2e39] text-[11px]">
              {(['ALL', '30D', '10D'] as const).map((range) => (
                <button
                  key={range}
                  onClick={() => setCurveRange(range)}
                  className={`px-2 py-0.5 rounded transition-all ${
                    curveRange === range
                      ? 'bg-[#2962ff] text-white font-medium'
                      : 'text-[#787b86] hover:text-[#d1d4dc]'
                  }`}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>

          {/* SVG 矢量折线图 */}
          <div className="relative w-full h-44 my-2 flex items-center justify-center">
            {svgCoords.length > 0 ? (
              <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full overflow-visible">
                {/* 零轴基线 */}
                {minCum < 0 && maxCum > 0 && (
                  <line
                    x1={padding}
                    y1={height - padding - ((0 - minCum) / rangeY) * (height - padding * 2)}
                    x2={width - padding}
                    y2={height - padding - ((0 - minCum) / rangeY) * (height - padding * 2)}
                    stroke="#363a45"
                    strokeDasharray="3 3"
                    strokeWidth="1"
                  />
                )}
                {/* 曲线路径 */}
                <path
                  d={pathD}
                  fill="none"
                  stroke={isNetPositive ? (colorScheme === 'cn' ? '#f23645' : '#089981') : (colorScheme === 'cn' ? '#089981' : '#f23645')}
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {/* 数据点 */}
                {svgCoords.map((pt, i) => (
                  <circle
                    key={i}
                    cx={pt.x}
                    cy={pt.y}
                    r="3.5"
                    className="cursor-pointer transition-all hover:r-5 fill-[#1e222d]"
                    stroke={pt.pnl >= 0 ? (colorScheme === 'cn' ? '#f23645' : '#089981') : (colorScheme === 'cn' ? '#089981' : '#f23645')}
                    strokeWidth="2"
                  >
                    <title>{`${pt.date} | ${pt.symbol}: ${pt.pnl >= 0 ? '+' : ''}${pt.pnl} 元 (累积: ${pt.cumPnl} 元)`}</title>
                  </circle>
                ))}
              </svg>
            ) : (
              <div className="text-xs text-[#787b86]">暂无交易点位数据</div>
            )}
          </div>

          <div className="flex justify-between items-center text-[11px] text-[#787b86] pt-2 border-t border-[#2a2e39]/60 font-mono">
            <span>起始净值: ¥0</span>
            <span>当前累积: {isNetPositive ? '+' : ''}{netPnlTotal} 元</span>
          </div>
        </div>

        {/* TradeZella 月度盈亏日历热力图 (5 Cols) */}
        <div className="lg:col-span-5 bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] flex flex-col justify-between shadow-sm">
          <div className="flex items-center justify-between pb-3 border-b border-[#2a2e39]/60">
            <div className="flex items-center gap-2">
              <CalendarIcon size={14} className="text-[#2962ff]" />
              <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider">
                复盘日历 (TradeZella Calendar)
              </h3>
            </div>
            <span className="text-[11px] text-[#787b86]">点击日期联动</span>
          </div>

          {/* 日历格子区域 */}
          <div className="my-2 min-h-44">
            {calendarDays.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {calendarDays.map(([date, data]) => {
                  const isDayWin = data.pnl >= 0;
                  const isSelected = selectedDate === date;
                  return (
                    <div
                      key={date}
                      onClick={() => setSelectedDate(isSelected ? null : date)}
                      className={`p-2.5 rounded-lg border cursor-pointer transition-all flex flex-col justify-between ${
                        isDayWin ? positiveBg : negativeBg
                      } ${isSelected ? 'ring-2 ring-[#2962ff] shadow-md' : 'hover:scale-[1.02]'}`}
                    >
                      <div className="flex justify-between items-center text-[11px] text-[#d1d4dc] font-mono">
                        <span>{date.slice(5)}</span>
                        <span className="text-[10px] text-[#787b86]">{data.count}笔</span>
                      </div>
                      <div className={`text-xs font-bold font-mono mt-1.5 ${isDayWin ? positiveColor : negativeColor}`}>
                        {isDayWin ? '+' : ''}{Math.round(data.pnl).toLocaleString()}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-[#787b86]">
                暂无日期流水
              </div>
            )}
          </div>

          {/* 选中特定日期的快速流水穿透 */}
          {selectedDate && dailyPnL[selectedDate] && (
            <div className="mt-2 p-2 rounded bg-[#131722] border border-[#363a45] text-xs">
              <div className="flex justify-between items-center text-[#787b86] mb-1 font-mono text-[11px]">
                <span>{selectedDate} 交易明细:</span>
                <span className={dailyPnL[selectedDate].pnl >= 0 ? positiveColor : negativeColor}>
                  合计: {dailyPnL[selectedDate].pnl >= 0 ? '+' : ''}{dailyPnL[selectedDate].pnl} 元
                </span>
              </div>
              <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
                {dailyPnL[selectedDate].trades.map((t) => (
                  <div
                    key={t.trade_id}
                    onClick={() => onSelectTrade(t)}
                    className="flex justify-between items-center p-1.5 rounded hover:bg-[#1e222d] cursor-pointer text-[11px]"
                  >
                    <span className="font-mono text-[#d1d4dc] font-bold">{t.symbol} {t.name}</span>
                    <span className={t.return_pct >= 0 ? positiveColor : negativeColor}>
                      {t.return_pct >= 0 ? '+' : ''}{t.return_pct}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 违规归因与情绪分布分析 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* 违规动作分布统计 */}
        <div className="bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39]">
          <div className="flex items-center justify-between pb-3 border-b border-[#2a2e39]/60">
            <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider flex items-center gap-1.5">
              <AlertTriangle size={13} className="text-rose-400" />
              <span>纪律扣分与违规归因分布 (Mistakes Analysis)</span>
            </h3>
            <span className="text-[11px] text-[#787b86]">击穿铁律排行</span>
          </div>

          <div className="mt-3 space-y-2.5">
            {summary.violation_categories && Object.entries(summary.violation_categories).length > 0 ? (
              Object.entries(summary.violation_categories).map(([cat, count]) => (
                <div key={cat} className="space-y-1">
                  <div className="flex justify-between text-xs text-[#d1d4dc]">
                    <span className="truncate max-w-[80%]">{cat}</span>
                    <span className="font-mono font-bold text-rose-400">{count} 次</span>
                  </div>
                  <div className="w-full bg-[#131722] rounded-full h-1.5 overflow-hidden">
                    <div
                      className="bg-rose-500 h-1.5 rounded-full"
                      style={{ width: `${Math.min(100, (count / (summary.total_violations || 1)) * 100)}%` }}
                    />
                  </div>
                </div>
              ))
            ) : (
              <div className="py-6 text-center text-xs text-[#787b86] flex flex-col items-center gap-1">
                <span className="text-emerald-400 font-bold">知行合一典范</span>
                <span>本周期未检测到触犯铁律的严重违规</span>
              </div>
            )}
          </div>
        </div>

        {/* 快捷穿透到复盘流水列表 */}
        <div className="bg-[#1e222d] p-4 rounded-xl border border-[#2a2e39] flex flex-col justify-between">
          <div className="flex items-center justify-between pb-3 border-b border-[#2a2e39]/60">
            <h3 className="text-xs font-bold text-[#f0f3fa] uppercase tracking-wider flex items-center gap-1.5">
              <Info size={13} className="text-[#2962ff]" />
              <span>最近交易体检速览</span>
            </h3>
            <button
              onClick={onViewAllTrades}
              className="text-xs text-[#2962ff] hover:underline flex items-center gap-0.5"
            >
              <span>查看全部流水</span>
              <ChevronRight size={13} />
            </button>
          </div>

          <div className="space-y-2 my-2 max-h-48 overflow-y-auto pr-1">
            {trades.slice(0, 4).map((t) => (
              <div
                key={t.trade_id}
                onClick={() => onSelectTrade(t)}
                className="p-2.5 rounded-lg bg-[#131722] hover:bg-[#2a2e39]/50 border border-[#2a2e39] flex items-center justify-between cursor-pointer transition-all"
              >
                <div className="flex items-center gap-2.5">
                  <span className="font-mono font-bold text-xs text-[#f0f3fa]">{t.symbol}</span>
                  <span className="text-xs text-[#d1d4dc]">{t.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1e222d] text-[#787b86] border border-[#363a45]">
                    {t.regime}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`font-mono text-xs font-bold ${t.return_pct >= 0 ? positiveColor : negativeColor}`}>
                    {t.return_pct >= 0 ? '+' : ''}{t.return_pct}%
                  </span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                    t.discipline_score >= 80 ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800' : 'bg-rose-950/60 text-rose-400 border border-rose-800'
                  }`}>
                    纪律:{t.discipline_score}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="pt-2 border-t border-[#2a2e39]/60 flex justify-between items-center text-[11px] text-[#787b86]">
            <span>系统总评: <strong className="text-amber-300">{summary.overall_grade || '良好'}</strong></span>
            <span>点击任意行开启席位严师质问</span>
          </div>
        </div>
      </div>
    </div>
  );
};
