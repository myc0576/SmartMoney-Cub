import { useEffect, useState } from 'react';
import { api } from '../api';
import type { RoundTrip } from '../types';
import { Empty, Panel, formatMoney, formatPct, toneOf } from '../components/common';

export function TradesView({ scheme, onOpenTrade }: {
  scheme: 'cn' | 'intl';
  onOpenTrade: (id: string) => void;
}) {
  const [trades, setTrades] = useState<RoundTrip[]>([]);
  const [openPositions, setOpenPositions] = useState<{ position_id: string; symbol: string; name: string; quantity: number; avg_cost: number; opened_at: string }[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);

  const load = async (symbol?: string) => {
    setLoading(true);
    try {
      const result = await api.trades(symbol ? { symbol } : {});
      setTrades(result.trades);
      setOpenPositions(result.open_positions);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  return (
    <div className="grid" style={{ gap: 14 }}>
      <Panel
        title={'已平仓交易（' + trades.length + '）'}
        actions={
          <div className="row">
            <input
              placeholder="代码或名称"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => { if (event.key === 'Enter') void load(query || undefined); }}
            />
            <button className="ghost" onClick={() => void load(query || undefined)}>筛选</button>
            {query ? <button className="ghost" onClick={() => { setQuery(''); void load(); }}>清除</button> : null}
          </div>
        }
      >
        {loading ? <div className="muted">加载中…</div> : null}
        {!loading && trades.length === 0 ? <Empty text="还没有已确认的平仓交易" /> : null}
        {trades.length > 0 ? (
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>标的</th><th>周期</th><th>开仓</th><th>平仓</th>
                  <th className="num">数量</th><th className="num">收益</th><th className="num">净盈亏</th><th className="num">持有</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => (
                  <tr key={trade.round_trip_id} onClick={() => onOpenTrade(trade.round_trip_id)}>
                    <td>
                      {trade.name || trade.symbol}<span className="muted"> {trade.symbol}</span>
                      {trade.tags.length ? <span className="tag" style={{ marginLeft: 6 }}>{trade.tags[0]}</span> : null}
                    </td>
                    <td className="muted">{trade.regime || '—'}</td>
                    <td className="muted">{trade.entry_time}</td>
                    <td className="muted">{trade.exit_time}</td>
                    <td className="num">{trade.quantity.toLocaleString('zh-CN')}</td>
                    <td className={'num ' + toneOf(trade.return_pct, scheme)}>{formatPct(trade.return_pct)}</td>
                    <td className={'num ' + toneOf(trade.net_pnl, scheme)}>{formatMoney(trade.net_pnl)}</td>
                    <td className="num muted">{trade.holding_days} 天</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Panel>

      <Panel title={'未配对持仓（' + openPositions.length + '）'}>
        {openPositions.length === 0 ? <div className="muted">没有未配对持仓。</div> : (
          <table>
            <thead><tr><th>标的</th><th>开仓时间</th><th className="num">数量</th><th className="num">均价</th></tr></thead>
            <tbody>
              {openPositions.map((position) => (
                <tr key={position.position_id}>
                  <td>{position.name || position.symbol}<span className="muted"> {position.symbol}</span></td>
                  <td className="muted">{position.opened_at}</td>
                  <td className="num">{position.quantity.toLocaleString('zh-CN')}</td>
                  <td className="num">{position.avg_cost}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

