import { useEffect, useState } from 'react';
import { api } from '../api';
import type { RoundTrip } from '../types';
import { Badge, Empty, formatMoney, formatPct, toneOf } from '../components/common';

export function TradeDrawer({ tradeId, scheme, onClose }: {
  tradeId: string;
  scheme: 'cn' | 'intl';
  onClose: () => void;
}) {
  const [trade, setTrade] = useState<RoundTrip | null>(null);
  const [revisions, setRevisions] = useState<Record<string, any>[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    api.tradeDetail(tradeId)
      .then((detail) => {
        setTrade(detail.trade);
        setRevisions(detail.fill_revisions);
      })
      .catch((failure) => setError(failure instanceof Error ? failure.message : String(failure)));
  }, [tradeId]);

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(6,8,12,0.62)', zIndex: 40,
        display: 'flex', justifyContent: 'flex-end',
      }}
      onClick={onClose}
    >
      <div
        style={{ width: 'min(680px, 94vw)', height: '100%', overflow: 'auto', background: 'var(--panel)', borderLeft: '1px solid var(--border)', padding: 16 }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
          <strong>{trade ? (trade.name || trade.symbol) + ' ' + trade.symbol : '交易详情'}</strong>
          <button className="ghost" onClick={onClose}>关闭</button>
        </div>

        {error ? <div className="notice">{error}</div> : null}
        {!trade && !error ? <div className="muted">加载中…</div> : null}

        {trade ? (
          <div className="grid" style={{ gap: 14 }}>
            <div className="grid kpi">
              <div className="panel"><div className="kpi-label">收益</div><div className={'kpi-value ' + toneOf(trade.return_pct, scheme)}>{formatPct(trade.return_pct)}</div></div>
              <div className="panel"><div className="kpi-label">净盈亏</div><div className={'kpi-value ' + toneOf(trade.net_pnl, scheme)}>{formatMoney(trade.net_pnl)}</div></div>
              <div className="panel"><div className="kpi-label">持有</div><div className="kpi-value">{trade.holding_days} 天</div></div>
              <div className="panel"><div className="kpi-label">费用</div><div className="kpi-value">{formatMoney(trade.fees)}</div></div>
            </div>

            <div className="panel">
              <div className="row" style={{ gap: 16 }}>
                <div><span className="muted">市场状态 </span>{trade.regime || '—'}</div>
                <div><span className="muted">开仓 </span>{trade.entry_time} @ {trade.entry_price}</div>
                <div><span className="muted">平仓 </span>{trade.exit_time} @ {trade.exit_price}</div>
              </div>
              {trade.invalidation_price !== null ? (
                <div style={{ marginTop: 6 }}><span className="muted">计划止损 </span>{trade.invalidation_price}</div>
              ) : null}
              <div style={{ marginTop: 8 }} className="muted">开仓理由：{trade.thesis || '未记录'}</div>
              {trade.tags.length ? <div style={{ marginTop: 8 }}>{trade.tags.map((tag) => <span key={tag} className="tag">{tag}</span>)}</div> : null}
            </div>

            <div className="panel">
              <h2>配对明细</h2>
              {trade.matched_lots.length === 0 ? <Empty text="没有配对到买入批次" /> : (
                <table>
                  <thead><tr><th>买入时间</th><th className="num">价格</th><th className="num">数量</th><th className="num">分摊买入费用</th></tr></thead>
                  <tbody>
                    {trade.matched_lots.map((lot, index) => (
                      <tr key={index}>
                        <td className="muted">{lot.entry_time}</td>
                        <td className="num">{lot.entry_price}</td>
                        <td className="num">{lot.quantity.toLocaleString('zh-CN')}</td>
                        <td className="num">{lot.buy_fee}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="panel">
              <h2>成交版本历史</h2>
              <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>
                修正会写入新版本，旧版本保留可查，不会被覆盖。
              </div>
              <div className="scroll-x">
                <table>
                  <thead><tr><th>日期</th><th>方向</th><th className="num">价格</th><th className="num">数量</th><th className="num">版本</th><th>来源</th><th>状态</th></tr></thead>
                  <tbody>
                    {revisions.map((row) => (
                      <tr key={row.fill_id}>
                        <td className="muted">{row.trade_date} {row.trade_time}</td>
                        <td>{row.side === 'BUY' ? '买入' : '卖出'}</td>
                        <td className="num">{row.price}</td>
                        <td className="num">{Number(row.quantity).toLocaleString('zh-CN')}</td>
                        <td className="num">{row.revision}</td>
                        <td className="muted">{row.edited_by}</td>
                        <td>{row.superseded ? <Badge kind="warn">已被修正</Badge> : <Badge kind="ok">当前</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

