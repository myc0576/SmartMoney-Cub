import { useEffect, useState } from 'react';
import { trader } from '../api';
import type { OpenPosition, TradeLogEntry } from '../types';
import { Banner, Empty, Panel, formatMoney, formatPct, toneOf } from '../components/common';

/**
 * The trade ledger: the journal's closed round trips and what is still open.
 *
 * The rows come from /api/trader/trades, the same store the import writes, where
 * this view used to read the review workbench's trades route and so showed an
 * empty table over a full journal. A row is addressed by its round trip id: the
 * trader route falls back to the journal's own id, which is what the drawer
 * opens.
 *
 * A journal row may carry no regime or tags, so those render as an em dash
 * rather than as a confident empty value.
 */

export function TradesView({ scheme, onOpenTrade }: {
  scheme: 'cn' | 'intl';
  onOpenTrade: (id: string) => void;
}) {
  const [trades, setTrades] = useState<TradeLogEntry[]>([]);
  const [openPositions, setOpenPositions] = useState<OpenPosition[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async (symbol?: string) => {
    setLoading(true);
    try {
      // The endpoint filters by symbol, so the same call answers both the
      // unfiltered view and the search box.
      const result = await trader.trades(symbol ? { symbol } : {});
      setTrades(result.trades || []);
      setOpenPositions(result.open_positions || []);
      setError('');
    } catch (failure) {
      // A read that failed is not an empty journal. Saying so is the difference
      // between a trader seeing no trades and not knowing the page did not load.
      setTrades([]);
      setOpenPositions([]);
      setError(failure instanceof Error ? failure.message : String(failure));
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
        {!loading && error ? <Banner>成交台账读取失败：{error}</Banner> : null}
        {!loading && !error && trades.length === 0 ? <Empty text="还没有已确认的平仓交易" /> : null}
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
                  <tr key={trade.round_trip_id || trade.trade_id} onClick={() => openTrade(onOpenTrade, trade)}>
                    <td>
                      {trade.name || trade.symbol}<span className="muted"> {trade.symbol}</span>
                      {trade.tags && trade.tags.length ? <span className="tag" style={{ marginLeft: 6 }}>{trade.tags[0]}</span> : null}
                    </td>
                    <td className="muted">{trade.regime || '—'}</td>
                    <td className="muted">{trade.entry_time || '—'}</td>
                    <td className="muted">{trade.exit_time || '—'}</td>
                    <td className="num">{number(trade.quantity).toLocaleString('zh-CN')}</td>
                    <td className={'num ' + toneOf(number(trade.return_pct), scheme)}>{formatPct(number(trade.return_pct))}</td>
                    <td className={'num ' + toneOf(number(trade.net_pnl), scheme)}>{formatMoney(number(trade.net_pnl))}</td>
                    <td className="num muted">{trade.holding_days === undefined || trade.holding_days === null ? '—' : trade.holding_days + ' 天'}</td>
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

/** Open the drawer for a row that carries an id. An unpaired execution has no
 *  round trip to show, so clicking one does nothing rather than opening a
 *  detail panel for a record the route cannot address. */
function openTrade(onOpenTrade: (id: string) => void, trade: TradeLogEntry): void {
  const id = trade.round_trip_id || trade.trade_id;
  if (id) onOpenTrade(id);
}

/** A numeric column tolerates a null or a string from the wire. */
function number(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
