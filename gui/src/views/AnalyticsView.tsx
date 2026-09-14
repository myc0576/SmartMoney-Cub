import { useEffect, useState } from 'react';
import { trader } from '../api';
import type { BreakdownRow, TraderSummary } from '../types';
import { Bars, Kpi, Panel, formatMoney, formatPct, toneOf } from '../components/common';

/**
 * Performance attribution: the headline metrics and the groups behind them.
 *
 * Both reads go to the journal — /api/trader/analytics/summary for the metrics
 * and /api/trader/analytics/breakdown for the groups — where this view used to
 * read the review workbench's analytics route, a different store that the
 * import never wrote. The KPI labels are unchanged; the sample note under the
 * bars comes from the summary so the two halves of the page cannot disagree.
 */

const DIMENSION_LABELS: Record<string, string> = {
  symbol: '按标的',
  regime: '按市场状态',
  weekday: '按星期',
  holding: '按持有周期',
  tag: '按标签',
};

export function AnalyticsView({ scheme }: { scheme: 'cn' | 'intl' }) {
  const [summary, setSummary] = useState<TraderSummary | null>(null);
  const [breakdown, setBreakdown] = useState<Record<string, BreakdownRow[]>>({});
  const [dimension, setDimension] = useState('symbol');
  const [error, setError] = useState('');

  useEffect(() => {
    // One unnamed breakdown request returns every group the view can show, so
    // switching a chip never costs a fetch.
    void Promise.all([trader.summary(), trader.breakdownAll()])
      .then(([summaryResult, breakdownResult]) => {
        setSummary(summaryResult);
        setBreakdown(breakdownResult.breakdown || {});
        setError('');
      })
      // Clearing the summary would leave this page on its loading line forever,
      // so a failed read is reported as a failed read instead.
      .catch((failure) => setError(failure instanceof Error ? failure.message : String(failure)));
  }, []);

  if (error && !summary) {
    return (
      <div className="grid" style={{ gap: 14 }}>
        <div className="notice">绩效分析读取失败：{error}</div>
      </div>
    );
  }
  if (!summary) return <div className="muted">加载中…</div>;
  const rows = breakdown[dimension] || [];

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="grid kpi">
        <Kpi label="样本量" value={summary.trade_count + ' 笔'} note="自选复盘历史，不是对照实验" />
        <Kpi label="平均收益" value={formatPct(summary.avg_return_pct)} tone={toneOf(summary.avg_return_pct, scheme)} />
        <Kpi label="平均盈利" value={formatPct(summary.avg_win_pct)} tone={toneOf(summary.avg_win_pct, scheme)} />
        <Kpi label="平均亏损" value={formatPct(summary.avg_loss_pct)} tone={toneOf(summary.avg_loss_pct, scheme)} />
        <Kpi label="盈亏比" value={summary.profit_factor === null ? '—' : String(summary.profit_factor)} note={summary.profit_factor_note} />
        <Kpi label="最大回撤" value={formatMoney(summary.max_drawdown)} tone={toneOf(summary.max_drawdown, scheme)} />
      </div>

      <Panel
        title="归因分析"
        actions={
          <div className="row">
            {Object.keys(DIMENSION_LABELS).map((key) => (
              <button key={key} className={'chip' + (key === dimension ? ' active' : '')} onClick={() => setDimension(key)}>
                {DIMENSION_LABELS[key]}
              </button>
            ))}
          </div>
        }
      >
        <Bars rows={rows} scheme={scheme} />
        <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
          {summary.sample_note} 带 * 的分组样本不足 5 笔，只作提示，不构成规律。
        </div>
      </Panel>

      <Panel title="分组明细">
        <div className="scroll-x">
          <table>
            <thead>
              <tr><th>分组</th><th className="num">笔数</th><th className="num">胜率</th><th className="num">净盈亏</th><th className="num">平均收益</th><th className="num">盈亏比</th></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key}>
                  <td>{row.key}{row.small_sample ? <span className="muted"> *</span> : null}</td>
                  <td className="num">{row.trade_count}</td>
                  <td className="num">{row.win_rate}%</td>
                  <td className={'num ' + toneOf(row.net_pnl, scheme)}>{formatMoney(row.net_pnl)}</td>
                  <td className={'num ' + toneOf(row.avg_return_pct, scheme)}>{formatPct(row.avg_return_pct)}</td>
                  <td className="num">{row.profit_factor === null ? '—' : row.profit_factor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
