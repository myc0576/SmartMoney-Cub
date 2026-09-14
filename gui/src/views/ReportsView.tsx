import { useCallback, useEffect, useState } from 'react';
import { trader } from '../api';
import type { BreakdownRow, TraderCalendar, TraderSummary } from '../types';
import { Bars, Empty, Kpi, Panel, Sparkline, formatCost, formatMoney, formatPct, toneOf } from '../components/common';

/**
 * Reports: performance, risk, symbols, and day-time.
 *
 * One shared summary fetch feeds every tab; only the symbol and day-time tabs
 * ask the breakdown endpoint for a dimension. That keeps switching tabs free
 * and means the four views cannot disagree about the headline numbers, because
 * there is only one set of them.
 */

type ReportTab = 'performance' | 'risk' | 'symbols' | 'daytime';

const TABS: { key: ReportTab; label: string }[] = [
  { key: 'performance', label: '绩效' },
  { key: 'risk', label: '风险' },
  { key: 'symbols', label: '标的' },
  { key: 'daytime', label: '日/时段' },
];

export function ReportsView({ scheme }: { scheme: 'cn' | 'intl' }) {
  const [tab, setTab] = useState<ReportTab>('performance');
  const [summary, setSummary] = useState<TraderSummary | null>(null);
  const [calendar, setCalendar] = useState<TraderCalendar | null>(null);
  const [symbols, setSymbols] = useState<BreakdownRow[]>([]);
  const [weekdays, setWeekdays] = useState<BreakdownRow[]>([]);
  const [holdings, setHoldings] = useState<BreakdownRow[]>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const now = new Date();
      const [summaryResult, calendarResult, symbolResult, weekdayResult, holdingResult] = await Promise.all([
        trader.summary(),
        trader.calendar({ year: now.getFullYear(), month: now.getMonth() + 1 }),
        trader.breakdown({ dimension: 'symbol' }),
        trader.breakdown({ dimension: 'weekday' }),
        trader.breakdown({ dimension: 'holding' }),
      ]);
      setSummary(summaryResult);
      setCalendar(calendarResult);
      setSymbols(rowsOf(symbolResult.rows));
      setWeekdays(rowsOf(weekdayResult.rows));
      setHoldings(rowsOf(holdingResult.rows));
      setError('');
    } catch (failure) {
      setSummary(null);
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (error) {
    return (
      <div className="grid" style={{ gap: 14 }}>
        <div className="notice">
          报告数据读取失败：{error}
          <button className="ghost" style={{ marginLeft: 10, fontSize: 11 }} onClick={() => void load()}>重试</button>
        </div>
      </div>
    );
  }
  if (!summary) return <div className="muted">加载中…</div>;

  const days = calendar ? calendar.days.filter((day) => day.trade_count > 0) : [];
  const bestDay = days.reduce<TraderCalendar['days'][number] | null>(
    (best, day) => (best === null || day.net_pnl > best.net_pnl ? day : best), null,
  );
  const worstDay = days.reduce<TraderCalendar['days'][number] | null>(
    (worst, day) => (worst === null || day.net_pnl < worst.net_pnl ? day : worst), null,
  );
  const grossProfit = summary.gross_profit ?? 0;
  const grossLoss = summary.gross_loss ?? 0;
  const expectancy = summary.trade_count > 0 ? summary.total_net_pnl / summary.trade_count : 0;

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="row">
        {TABS.map((item) => (
          <button
            key={item.key}
            className={'chip' + (tab === item.key ? ' active' : '')}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
        <div className="spacer" style={{ flex: 1 }} />
        <span className="muted" style={{ fontSize: 11 }}>{summary.sample_note}</span>
      </div>

      {tab === 'performance' ? (
        <>
          <div className="grid kpi">
            <Kpi label="交易笔数" value={summary.trade_count + ' 笔'} note={summary.win_count + ' 胜 / ' + summary.loss_count + ' 负 / ' + summary.flat_count + ' 平'} />
            <Kpi label="净盈亏" value={formatMoney(summary.total_net_pnl)} tone={toneOf(summary.total_net_pnl, scheme)} />
            <Kpi label="胜率" value={summary.win_rate + '%'} />
            <Kpi label="单笔期望" value={formatMoney(expectancy)} tone={toneOf(expectancy, scheme)} note="净盈亏 / 笔数" />
            <Kpi label="平均收益" value={formatPct(summary.avg_return_pct)} tone={toneOf(summary.avg_return_pct, scheme)} />
            <Kpi label="手续费合计" value={formatCost(summary.total_fees)} />
          </div>
          <div className="grid split">
            <Panel title="盈利与亏损">
              <table>
                <tbody>
                  <tr><td>总盈利</td><td className={'num ' + toneOf(grossProfit, scheme)}>{formatMoney(grossProfit)}</td></tr>
                  <tr><td>总亏损</td><td className={'num ' + toneOf(-grossLoss, scheme)}>{formatMoney(-grossLoss)}</td></tr>
                  <tr><td>平均盈利</td><td className={'num ' + toneOf(summary.avg_win_pct, scheme)}>{formatPct(summary.avg_win_pct)}</td></tr>
                  <tr><td>平均亏损</td><td className={'num ' + toneOf(summary.avg_loss_pct, scheme)}>{formatPct(summary.avg_loss_pct)}</td></tr>
                  <tr><td>盈亏比</td><td className="num">{summary.profit_factor === null ? '—' : summary.profit_factor}</td></tr>
                </tbody>
              </table>
              {summary.profit_factor === null ? <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>{summary.profit_factor_note}</div> : null}
            </Panel>
            <Panel title="当月最佳与最差">
              {days.length === 0 ? <Empty text="这个月还没有平仓交易" /> : (
                <table>
                  <tbody>
                    <tr>
                      <td>最佳交易日</td>
                      <td className="muted">{bestDay ? bestDay.date : '—'}</td>
                      <td className={'num ' + toneOf(bestDay ? bestDay.net_pnl : 0, scheme)}>{formatMoney(bestDay ? bestDay.net_pnl : 0)}</td>
                    </tr>
                    <tr>
                      <td>最差交易日</td>
                      <td className="muted">{worstDay ? worstDay.date : '—'}</td>
                      <td className={'num ' + toneOf(worstDay ? worstDay.net_pnl : 0, scheme)}>{formatMoney(worstDay ? worstDay.net_pnl : 0)}</td>
                    </tr>
                    <tr>
                      <td>盈利天数</td>
                      <td className="muted">{days.filter((day) => day.net_pnl > 0).length} 天</td>
                      <td className="num muted">{days.filter((day) => day.net_pnl < 0).length} 天亏损</td>
                    </tr>
                  </tbody>
                </table>
              )}
            </Panel>
          </div>
        </>
      ) : null}

      {tab === 'risk' ? (
        <>
          <div className="grid kpi">
            <Kpi label="最大回撤" value={formatMoney(summary.max_drawdown)} tone={toneOf(summary.max_drawdown, scheme)} note="按平仓顺序累计" />
            <Kpi label="平均持有" value={summary.avg_holding_days + ' 天'} />
            <Kpi label="未配对持仓" value={summary.open_position_count + ' 个'} note="尚无平仓结果" />
            <Kpi label="手续费占净盈亏" value={feeShare(summary)} />
          </div>
          <Panel title="回撤与费用">
            <div className="grid split">
              <div>
                <div className="kpi-label">回撤来源</div>
                <div className="muted" style={{ fontSize: 12, lineHeight: 1.8, marginTop: 6 }}>
                  最大回撤按平仓顺序累计，衡量的是已实现权益从峰值回落的最大幅度。
                  它不包含未平仓浮亏，也不预测未来风险。
                </div>
              </div>
              <div>
                <div className="kpi-label">费用结构</div>
                <div className="muted" style={{ fontSize: 12, lineHeight: 1.8, marginTop: 6 }}>
                  手续费合计 {formatCost(summary.total_fees)}，覆盖 {summary.trade_count} 笔平仓交易。
                  费用会直接压低净盈亏，报告里的净值已经是扣费后的数字。
                </div>
              </div>
            </div>
          </Panel>
          <Panel title="累计盈亏曲线">
            <Sparkline points={(summary.equity_curve || []).map((point) => point.cumulative_pnl)} scheme={scheme} />
            {(summary.equity_curve || []).length >= 2 ? (
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                曲线按平仓时间累计，每笔已扣手续费。它反映已实现盈亏，不含未平仓浮盈浮亏。
              </div>
            ) : null}
          </Panel>
        </>
      ) : null}

      {tab === 'symbols' ? (
        <Panel title="按标的">
          {symbols.length === 0 ? <Empty text="还没有可以按标的归因的样本" /> : (
            <BreakdownTable rows={symbols} scheme={scheme} />
          )}
        </Panel>
      ) : null}

      {tab === 'daytime' ? (
        <div className="grid" style={{ gap: 14 }}>
          <Panel title="按星期">
            {weekdays.length === 0 ? <Empty text="还没有可以按星期归因的样本" /> : (
              <>
                <Bars rows={weekdays} scheme={scheme} />
                <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                  带 * 的分组样本不足 5 笔，只作提示，不构成规律。
                </div>
              </>
            )}
          </Panel>
          <Panel title="按持有周期">
            {holdings.length === 0 ? <Empty text="还没有可以按持有周期归因的样本" /> : (
              <BreakdownTable rows={holdings} scheme={scheme} />
            )}
          </Panel>
        </div>
      ) : null}
    </div>
  );
}

function BreakdownTable({ rows, scheme }: { rows: BreakdownRow[]; scheme: 'cn' | 'intl' }) {
  return (
    <div className="scroll-x">
      <table>
        <thead>
          <tr>
            <th>分组</th><th className="num">笔数</th><th className="num">胜率</th>
            <th className="num">净盈亏</th><th className="num">平均收益</th><th className="num">盈亏比</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isSt = row.is_st || (row.name && row.name.toUpperCase().includes('ST'));
            return (
              <tr key={row.key}>
                <td>
                  <span style={{ fontWeight: 600 }}>{row.key}</span>
                  {row.name ? <span style={{ marginLeft: 6 }}>{row.name}</span> : null}
                  {isSt ? <span className="badge warn" style={{ marginLeft: 5, fontSize: 10, padding: '0 4px', verticalAlign: 'middle' }}>ST</span> : null}
                  {row.small_sample ? <span className="muted"> *</span> : null}
                </td>
                <td className="num">{row.trade_count}</td>
                <td className="num">{row.win_rate}%</td>
                <td className={'num ' + toneOf(row.net_pnl, scheme)}>{formatMoney(row.net_pnl)}</td>
                <td className={'num ' + toneOf(row.avg_return_pct, scheme)}>{formatPct(row.avg_return_pct)}</td>
                <td className="num">{row.profit_factor === null ? '—' : row.profit_factor}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function feeShare(summary: TraderSummary): string {
  const gross = Math.abs(summary.total_net_pnl) + Math.abs(summary.total_fees);
  if (!gross || Number.isNaN(gross)) return '—';
  return ((Math.abs(summary.total_fees) / gross) * 100).toFixed(1) + '%';
}

function rowsOf(rows: BreakdownRow[] | null | undefined): BreakdownRow[] {
  return Array.isArray(rows) ? rows : [];
}
