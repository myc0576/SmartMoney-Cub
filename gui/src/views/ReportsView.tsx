import { useCallback, useEffect, useState } from 'react';
import { trader } from '../api';
import type { BreakdownRow, TraderCalendar, TraderSummary } from '../types';
import { Bars, Empty, Kpi, Panel, Sparkline, formatCost, formatMoney, formatPct, toneOf } from '../components/common';
import { useLegacyI18n } from '../locales/legacy';

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
  const { t } = useLegacyI18n();
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
          {t('reports.readFailed', { error })}
          <button className="ghost" style={{ marginLeft: 10, fontSize: 11 }} onClick={() => void load()}>{t('reports.retry')}</button>
        </div>
      </div>
    );
  }
  if (!summary) return <div className="muted">{t('reports.loading')}</div>;

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
            {t('reports.' + item.key as Parameters<typeof t>[0])}
          </button>
        ))}
        <div className="spacer" style={{ flex: 1 }} />
        <span className="muted" style={{ fontSize: 11 }}>{summary.sample_note}</span>
      </div>

      {tab === 'performance' ? (
        <>
          <div className="grid kpi">
            <Kpi label={t('reports.tradeCount')} value={summary.trade_count + ' ' + t('reports.tradeUnit')} note={summary.win_count + ' ' + t('reports.wins') + ' / ' + summary.loss_count + ' ' + t('reports.losses') + ' / ' + summary.flat_count + ' ' + t('reports.flat')} />
            <Kpi label={t('reports.netPnl')} value={formatMoney(summary.total_net_pnl)} tone={toneOf(summary.total_net_pnl, scheme)} />
            <Kpi label={t('reports.winRate')} value={summary.win_rate + '%'} />
            <Kpi label={t('reports.expectancy')} value={formatMoney(expectancy)} tone={toneOf(expectancy, scheme)} note={t('reports.expectancyNote')} />
            <Kpi label={t('reports.avgReturn')} value={formatPct(summary.avg_return_pct)} tone={toneOf(summary.avg_return_pct, scheme)} />
            <Kpi label={t('reports.fees')} value={formatCost(summary.total_fees)} />
          </div>
          <div className="grid split">
            <Panel title={t('reports.gross')}>
              <table>
                <tbody>
                  <tr><td>{t('reports.grossProfit')}</td><td className={'num ' + toneOf(grossProfit, scheme)}>{formatMoney(grossProfit)}</td></tr>
                  <tr><td>{t('reports.grossLoss')}</td><td className={'num ' + toneOf(-grossLoss, scheme)}>{formatMoney(-grossLoss)}</td></tr>
                  <tr><td>{t('reports.avgWin')}</td><td className={'num ' + toneOf(summary.avg_win_pct, scheme)}>{formatPct(summary.avg_win_pct)}</td></tr>
                  <tr><td>{t('reports.avgLoss')}</td><td className={'num ' + toneOf(summary.avg_loss_pct, scheme)}>{formatPct(summary.avg_loss_pct)}</td></tr>
                  <tr><td>{t('reports.profitFactor')}</td><td className="num">{summary.profit_factor === null ? '—' : summary.profit_factor}</td></tr>
                </tbody>
              </table>
              {summary.profit_factor === null ? <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>{summary.profit_factor_note}</div> : null}
            </Panel>
            <Panel title={t('reports.monthBestWorst')}>
              {days.length === 0 ? <Empty text={t('reports.noClosedThisMonth')} /> : (
                <table>
                  <tbody>
                    <tr>
                      <td>{t('reports.bestDay')}</td>
                      <td className="muted">{bestDay ? bestDay.date : '—'}</td>
                      <td className={'num ' + toneOf(bestDay ? bestDay.net_pnl : 0, scheme)}>{formatMoney(bestDay ? bestDay.net_pnl : 0)}</td>
                    </tr>
                    <tr>
                      <td>{t('reports.worstDay')}</td>
                      <td className="muted">{worstDay ? worstDay.date : '—'}</td>
                      <td className={'num ' + toneOf(worstDay ? worstDay.net_pnl : 0, scheme)}>{formatMoney(worstDay ? worstDay.net_pnl : 0)}</td>
                    </tr>
                    <tr>
                      <td>{t('reports.profitableDays')}</td>
                      <td className="muted">{days.filter((day) => day.net_pnl > 0).length} {t('reports.days')}</td>
                      <td className="num muted">{days.filter((day) => day.net_pnl < 0).length} {t('reports.lossDays')}</td>
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
            <Kpi label={t('reports.maxDrawdown')} value={formatMoney(summary.max_drawdown)} tone={toneOf(summary.max_drawdown, scheme)} note={t('reports.drawdownNote')} />
            <Kpi label={t('reports.avgHolding')} value={summary.avg_holding_days + ' ' + t('reports.days')} />
            <Kpi label={t('reports.openPositions')} value={summary.open_position_count + ' ' + t('reports.positions')} note={t('reports.noClosedResult')} />
            <Kpi label={t('reports.feeShare')} value={feeShare(summary)} />
          </div>
          <Panel title={t('reports.drawdownFees')}>
            <div className="grid split">
              <div>
                <div className="kpi-label">{t('reports.drawdownSource')}</div>
                <div className="muted" style={{ fontSize: 12, lineHeight: 1.8, marginTop: 6 }}>{t('reports.drawdownSourceText')}</div>
              </div>
              <div>
                <div className="kpi-label">{t('reports.feeStructure')}</div>
                <div className="muted" style={{ fontSize: 12, lineHeight: 1.8, marginTop: 6 }}>{t('reports.feeStructureText', { fees: formatCost(summary.total_fees), count: summary.trade_count })}</div>
              </div>
            </div>
          </Panel>
          <Panel title={t('reports.equityCurve')}>
            <Sparkline points={(summary.equity_curve || []).map((point) => point.cumulative_pnl)} scheme={scheme} />
            {(summary.equity_curve || []).length >= 2 ? (
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                {t('reports.equityCurveText')}
              </div>
            ) : null}
          </Panel>
        </>
      ) : null}

      {tab === 'symbols' ? (
        <Panel title={t('reports.bySymbol')}>
          {symbols.length === 0 ? <Empty text={t('reports.noSymbolSamples')} /> : (
            <BreakdownTable rows={symbols} scheme={scheme} />
          )}
        </Panel>
      ) : null}

      {tab === 'daytime' ? (
        <div className="grid" style={{ gap: 14 }}>
          <Panel title={t('reports.byWeekday')}>
            {weekdays.length === 0 ? <Empty text={t('reports.noWeekdaySamples')} /> : (
              <>
                <Bars rows={weekdays} scheme={scheme} />
                <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                  {t('reports.smallSample')}
                </div>
              </>
            )}
          </Panel>
          <Panel title={t('reports.byHolding')}>
            {holdings.length === 0 ? <Empty text={t('reports.noHoldingSamples')} /> : (
              <BreakdownTable rows={holdings} scheme={scheme} />
            )}
          </Panel>
        </div>
      ) : null}
    </div>
  );
}

function BreakdownTable({ rows, scheme }: { rows: BreakdownRow[]; scheme: 'cn' | 'intl' }) {
  const { t } = useLegacyI18n();
  return (
    <div className="scroll-x">
      <table>
        <thead>
          <tr>
            <th>{t('reports.group')}</th><th className="num">{t('reports.count')}</th><th className="num">{t('reports.winRate')}</th>
            <th className="num">{t('reports.netPnl')}</th><th className="num">{t('reports.avgReturn')}</th><th className="num">{t('reports.profitFactor')}</th>
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
