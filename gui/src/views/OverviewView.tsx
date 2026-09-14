import type { Issue, OpenPosition, TradeLogEntry, TraderSummary } from '../types';
import { Kpi, Panel, Sparkline, formatCost, formatMoney, formatPct, toneOf } from '../components/common';

/**
 * Overview: the headline numbers of the trader's own journal.
 *
 * Everything here comes from the tenant's ledger — /api/trader/analytics/summary
 * for the metrics and /api/trader/trades for the rows behind them. The view used
 * to read the review workbench's overview payload, which is a different store:
 * an import wrote the journal and left this page reading zero. Reading the same
 * endpoints the journal views read is what makes one import populate the whole
 * product.
 *
 * The KPI labels are the ones this page already showed. Where the summary has no
 * equivalent (holding time is measured in days, fees in currency), the value
 * comes from the summary field that does exist rather than from a placeholder,
 * so a confident zero is never shown over data the journal actually holds.
 */

/** How many recent closes the panel lists before it offers the full log. */
const RECENT_LIMIT = 8;

export function OverviewView({ summary, recent, openPositions, issues, ledgerStatus, scheme, onGoToImport, onOpenLog }: {
  summary: TraderSummary;
  recent: TradeLogEntry[];
  openPositions: OpenPosition[];
  issues: Issue[];
  ledgerStatus: string;
  scheme: 'cn' | 'intl';
  onGoToImport: () => void;
  onOpenLog: () => void;
}) {
  const curve = summary.equity_curve.map((point) => point.cumulative_pnl);
  // A blocking issue is what drives the ledger to needs_review, so the notice
  // counts errors rather than every warning the matcher recorded.
  const blocking = issues.filter((issue) => issue.severity === 'error');
  const shown = recent.slice(0, RECENT_LIMIT);
  const hasData = summary.trade_count > 0 || openPositions.length > 0 || recent.length > 0;

  if (!hasData) {
    return (
      <div className="grid" style={{ gap: 14 }}>
        {ledgerStatus === 'needs_review' ? (
          <div className="notice">
            台账中有 {blocking.length} 条需要先确认的问题，未确认前这些成交不会进入统计。
            <button className="ghost" style={{ marginLeft: 10, fontSize: 11 }} onClick={onGoToImport}>
              去处理
            </button>
          </div>
        ) : null}

        <Panel title="开始使用">
          <div style={{ padding: '28px 16px', maxWidth: 660 }}>
            <h2 style={{ fontSize: 20, margin: '0 0 10px', fontWeight: 600 }}>欢迎使用 SmartMoney-Cub 交易复盘工作台</h2>
            <p className="muted" style={{ fontSize: 13, lineHeight: 1.6, margin: '0 0 24px' }}>
              当前账本暂无交易记录。你可以直接导入交割单或进行单笔手工录入，系统将自动进行先进先出（FIFO）撮合配对，实时生成多维绩效归因、收益曲线与复盘日历。
            </p>

            <div className="row" style={{ gap: 12, marginBottom: 28 }}>
              <button className="primary" onClick={onGoToImport}>
                导入交割数据 (CSV / PDF / 截图)
              </button>
              <button className="ghost" onClick={onGoToImport}>
                手工补录成交
              </button>
            </div>

            <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
              <div style={{ padding: '14px 16px', borderRadius: 8, background: 'var(--panel-2)', border: '1px solid var(--border)' }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>1. 导入数据</div>
                <div className="muted" style={{ fontSize: 12, lineHeight: 1.5 }}>支持主流券商交割单、CSV 格式拖拽批量解析，或单笔快速录入。</div>
              </div>
              <div style={{ padding: '14px 16px', borderRadius: 8, background: 'var(--panel-2)', border: '1px solid var(--border)' }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>2. 自动归因</div>
                <div className="muted" style={{ fontSize: 12, lineHeight: 1.5 }}>自动计算真实净盈亏、最大回撤、盈亏比与月度日历热力图。</div>
              </div>
              <div style={{ padding: '14px 16px', borderRadius: 8, background: 'var(--panel-2)', border: '1px solid var(--border)' }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>3. 策略回测</div>
                <div className="muted" style={{ fontSize: 12, lineHeight: 1.5 }}>内置 Playbook 纪律评分、K 线逐笔回放与纯 JSON 策略回测引擎。</div>
              </div>
            </div>
          </div>
        </Panel>
      </div>
    );
  }

  return (
    <div className="grid" style={{ gap: 14 }}>
      {ledgerStatus === 'needs_review' ? (
        <div className="notice">
          台账中有 {blocking.length} 条需要先确认的问题，未确认前这些成交不会进入统计。
          <button className="ghost" style={{ marginLeft: 10, fontSize: 11 }} onClick={onGoToImport}>
            去处理
          </button>
        </div>
      ) : null}

      <div className="grid kpi">
        <Kpi label="净盈亏合计" value={formatMoney(summary.total_net_pnl)} tone={toneOf(summary.total_net_pnl, scheme)} note={'已确认平仓 ' + summary.trade_count + ' 笔'} />
        <Kpi label="胜率" value={summary.win_rate + '%'} note={summary.win_count + ' 胜 / ' + summary.loss_count + ' 负'} />
        <Kpi
          label="盈亏比"
          value={summary.profit_factor === null ? '—' : String(summary.profit_factor)}
          note={summary.profit_factor === null ? summary.profit_factor_note : '总盈利 / 总亏损绝对值'}
        />
        <Kpi label="最大回撤" value={formatMoney(summary.max_drawdown)} tone={toneOf(summary.max_drawdown, scheme)} note="按平仓顺序累计" />
        <Kpi label="平均持有" value={summary.avg_holding_days + ' 天'} note={'平均收益 ' + formatPct(summary.avg_return_pct)} />
        <Kpi label="手续费合计" value={formatCost(summary.total_fees)} note={'仍未配对持仓 ' + summary.open_position_count + ' 个'} />
      </div>

      <Panel title="累计盈亏曲线">
        <Sparkline points={curve} scheme={scheme} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{summary.sample_note}</div>
      </Panel>

      <div className="grid split">
        <Panel
          title="最近平仓"
          actions={
            recent.length > shown.length ? (
              <button className="ghost" style={{ fontSize: 11 }} onClick={onOpenLog}>
                查看全部 {recent.length} 笔
              </button>
            ) : null
          }
        >
          {recent.length === 0 ? (
            <div className="muted">还没有已确认的平仓交易。到「数据导入」上传交割单或手工补录。</div>
          ) : (
            <div className="scroll-x">
              <table>
                <thead>
                  <tr>
                    <th>标的</th><th>平仓时间</th><th className="num">收益</th><th className="num">净盈亏</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((trade, index) => (
                    <tr
                      key={trade.round_trip_id || trade.trade_id || trade.symbol + '-' + index}
                      onClick={onOpenLog}
                      title="在交易日志中查看"
                    >
                      <td>{trade.name || trade.symbol}<span className="muted"> {trade.symbol}</span></td>
                      <td className="muted">{trade.exit_time || '—'}</td>
                      <td className={'num ' + toneOf(number(trade.return_pct), scheme)}>{formatPct(number(trade.return_pct))}</td>
                      <td className={'num ' + toneOf(number(trade.net_pnl), scheme)}>{formatMoney(number(trade.net_pnl))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="未配对持仓">
          {openPositions.length === 0 ? (
            <div className="muted">没有未配对持仓。</div>
          ) : (
            <table>
              <thead><tr><th>标的</th><th className="num">数量</th><th className="num">均价</th><th>开仓时间</th></tr></thead>
              <tbody>
                {openPositions.map((position) => (
                  <tr key={position.position_id}>
                    <td>{position.name || position.symbol}</td>
                    <td className="num">{number(position.quantity).toLocaleString('zh-CN')}</td>
                    <td className="num">{number(position.avg_cost)}</td>
                    <td className="muted">{position.opened_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <Panel title="待复盘清单">
        {issues.length === 0 ? (
          <div className="muted">台账没有发现问题。</div>
        ) : (
          <table>
            <thead><tr><th>级别</th><th>代码</th><th>标的</th><th>说明</th></tr></thead>
            <tbody>
              {issues.slice(0, 12).map((issue, index) => (
                <tr key={issue.code + index}>
                  <td>{issue.severity === 'error' ? <span className="badge error">阻断</span> : <span className="badge warn">提示</span>}</td>
                  <td className="muted">{issue.code}</td>
                  <td>{issue.symbol || '—'}</td>
                  <td style={{ whiteSpace: 'normal' }}>{issue.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

/** A numeric column tolerates a null or a string from the wire. */
function number(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
