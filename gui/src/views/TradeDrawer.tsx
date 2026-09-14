import { useEffect, useState } from 'react';
import { trader } from '../api';
import type { TradeLogDetail, TradeLogEntry } from '../types';
import { Empty, formatMoney, formatPct, toneOf } from '../components/common';

/** The journal stores optional fields, so the drawer reads them defensively. */
function money(value: number | undefined): string {
  return formatMoney(value === undefined ? 0 : value);
}

function pct(value: number | undefined): string {
  return formatPct(value === undefined ? 0 : value);
}

function lotsOf(detail: TradeLogDetail) {
  return detail.matched_lots || detail.trade.matched_lots || [];
}

export function TradeDrawer({ tradeId, scheme, onClose }: {
  tradeId: string;
  scheme: 'cn' | 'intl';
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<TradeLogDetail | null>(null);
  const [error, setError] = useState('');
  const trade: TradeLogEntry | null = detail ? detail.trade : null;

  useEffect(() => {
    // Read the journal, like every other view. The workbench detail endpoint
    // serves a different store, so a journal id resolved to a 404 there and the
    // drawer reported an error over data the trading log had just listed.
    trader.trade(tradeId)
      .then((payload: TradeLogDetail) => setDetail(payload))
      .catch((failure: unknown) => setError(failure instanceof Error ? failure.message : String(failure)));
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
              <div className="panel"><div className="kpi-label">收益</div><div className={'kpi-value ' + toneOf(trade.return_pct, scheme)}>{pct(trade.return_pct)}</div></div>
              <div className="panel"><div className="kpi-label">净盈亏</div><div className={'kpi-value ' + toneOf(trade.net_pnl, scheme)}>{money(trade.net_pnl)}</div></div>
              <div className="panel"><div className="kpi-label">持有</div><div className="kpi-value">{trade.holding_days === undefined ? '—' : trade.holding_days + ' 天'}</div></div>
              <div className="panel"><div className="kpi-label">费用</div><div className="kpi-value">{money(trade.fees)}</div></div>
            </div>

            <div className="panel">
              <div className="row" style={{ gap: 16 }}>
                <div><span className="muted">市场状态 </span>{trade.regime || '—'}</div>
                <div><span className="muted">开仓 </span>{trade.entry_time || '—'} @ {trade.entry_price === undefined ? '—' : trade.entry_price}</div>
                <div><span className="muted">平仓 </span>{trade.exit_time || '—'} @ {trade.exit_price === undefined ? '—' : trade.exit_price}</div>
              </div>
              <div style={{ marginTop: 8 }} className="muted">开仓理由：{trade.thesis || '未记录'}</div>
              {trade.tags && trade.tags.length ? <div style={{ marginTop: 8 }}>{trade.tags.map((tag) => <span key={tag} className="tag">{tag}</span>)}</div> : null}
            </div>

            <div className="panel">
              <h2>配对明细</h2>
              {lotsOf(detail!).length === 0 ? <Empty text="没有配对到买入批次" /> : (
                <table>
                  <thead><tr><th>买入时间</th><th className="num">价格</th><th className="num">数量</th><th className="num">分摊买入费用</th></tr></thead>
                  <tbody>
                    {lotsOf(detail!).map((lot, index) => (
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

            {/* The fill-revision history panel was removed: it belonged to the
                review workbench's versioned fill records, and the journal does
                not expose that feed. Showing the matched lots here under a
                "revision history" heading would have labelled pairing rows as
                edit history, so the panel is gone rather than mislabelled. */}
          </div>
        ) : null}
      </div>
    </div>
  );
}
