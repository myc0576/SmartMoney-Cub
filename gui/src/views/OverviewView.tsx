import type { Overview } from '../types';
import { Kpi, Panel, Sparkline, formatCost, formatMoney, formatPct, toneOf } from '../components/common';

export function OverviewView({ data, scheme, onOpenTrade }: {
  data: Overview;
  scheme: 'cn' | 'intl';
  onOpenTrade: (id: string) => void;
}) {
  const summary = data.summary;
  const curve = summary.equity_curve.map((point) => point.cumulative_pnl);
  return (
    <div className="grid" style={{ gap: 14 }}>
      {data.ledger_status === 'needs_review' ? (
        <div className="notice">
          台账中有 {data.blocking_issues.length} 条需要先确认的问题，未确认前这些成交不会进入统计。
          <button className="ghost" style={{ marginLeft: 10, fontSize: 11 }} onClick={() => onOpenTrade('__import__')}>
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
        <Panel title="最近平仓">
          {data.recent_trades.length === 0 ? (
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
                  {data.recent_trades.map((trade) => (
                    <tr key={trade.round_trip_id} onClick={() => onOpenTrade(trade.round_trip_id)}>
                      <td>{trade.name || trade.symbol}<span className="muted"> {trade.symbol}</span></td>
                      <td className="muted">{trade.exit_time}</td>
                      <td className={'num ' + toneOf(trade.return_pct, scheme)}>{formatPct(trade.return_pct)}</td>
                      <td className={'num ' + toneOf(trade.net_pnl, scheme)}>{formatMoney(trade.net_pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="未配对持仓">
          {data.open_positions.length === 0 ? (
            <div className="muted">没有未配对持仓。</div>
          ) : (
            <table>
              <thead><tr><th>标的</th><th className="num">数量</th><th className="num">均价</th><th>开仓时间</th></tr></thead>
              <tbody>
                {data.open_positions.map((position) => (
                  <tr key={position.position_id}>
                    <td>{position.name || position.symbol}</td>
                    <td className="num">{position.quantity.toLocaleString('zh-CN')}</td>
                    <td className="num">{position.avg_cost}</td>
                    <td className="muted">{position.opened_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <Panel title="待复盘清单">
        {data.issues.length === 0 ? (
          <div className="muted">台账没有发现问题。</div>
        ) : (
          <table>
            <thead><tr><th>级别</th><th>代码</th><th>标的</th><th>说明</th></tr></thead>
            <tbody>
              {data.issues.slice(0, 12).map((issue, index) => (
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

