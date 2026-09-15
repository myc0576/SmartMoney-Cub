import { useCallback, useEffect, useMemo, useState } from 'react';
import { trader } from '../api';
import type { TradeLogEntry, TraderAccount } from '../types';
import { Banner, Empty, Panel, formatMoney, formatPct, toneOf } from '../components/common';

/**
 * The trade log: closed round trips, sortable and filterable.
 *
 * Filters go to the endpoint, which is where the whole journal lives: filtering
 * only the loaded page would silently hide matches the page does not contain.
 *
 * Filter inputs are held as a draft and only applied when 查询 is pressed (or
 * Enter is hit). Binding the request to the live inputs would fire one fetch
 * per keystroke, and a half-typed symbol would briefly filter the table to
 * nothing. Sorting stays local: re-querying per column click would make a sort
 * look like a fetch, and the page is bounded.
 */

const PAGE_SIZE = 200;

interface Filters {
  symbol: string;
  from: string;
  to: string;
  accountId: string;
}

const NO_FILTERS: Filters = { symbol: '', from: '', to: '', accountId: '' };

type SortKey = 'exit_time' | 'symbol' | 'quantity' | 'return_pct' | 'net_pnl' | 'holding_days';

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: 'symbol', label: '标的' },
  { key: 'exit_time', label: '平仓时间' },
  { key: 'quantity', label: '数量', numeric: true },
  { key: 'return_pct', label: '收益', numeric: true },
  { key: 'net_pnl', label: '净盈亏', numeric: true },
  { key: 'holding_days', label: '持有', numeric: true },
];

export function TradeLogView({ scheme }: { scheme: 'cn' | 'intl' }) {
  const [rows, setRows] = useState<TradeLogEntry[]>([]);
  const [accounts, setAccounts] = useState<TraderAccount[]>([]);
  const [draft, setDraft] = useState<Filters>(NO_FILTERS);
  const [applied, setApplied] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<{ key: SortKey; descending: boolean }>({ key: 'exit_time', descending: true });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [truncated, setTruncated] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await trader.trades({ ...cleanFilters(applied), limit: PAGE_SIZE });
      setRows(listOf(result.trades));
      // The endpoint returns its own count; when it exceeds the page there are
      // rows this view has not seen, and saying so is better than a filter that
      // quietly misses them.
      setTruncated(number(result.count) > listOf(result.trades).length);
      setError('');
    } catch (failure) {
      setRows([]);
      setTruncated(false);
      setError(messageOf(failure));
    } finally {
      setLoading(false);
    }
  }, [applied]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    // A missing account list is not worth failing the page over: the filter
    // simply offers no options.
    void trader.accounts()
      .then((result) => setAccounts(listOf(result.accounts)))
      .catch(() => setAccounts([]));
  }, []);

  const visible = useMemo(() => {
    const sorted = [...rows].sort((left, right) => compareRows(left, right, sort.key));
    if (sort.descending) sorted.reverse();
    return sorted;
  }, [rows, sort]);

  const netTotal = visible.reduce((sum, row) => sum + number(row.net_pnl), 0);
  const wins = visible.filter((row) => number(row.net_pnl) > 0).length;

  const toggleSort = (key: SortKey) => {
    setSort((previous) =>
      previous.key === key
        ? { key, descending: !previous.descending }
        : { key, descending: true },
    );
  };

  return (
    <div className="grid" style={{ gap: 14 }}>
      <Panel
        title={'交易日志（' + visible.length + ' 笔）'}
        actions={
          <div className="row">
            <input
              placeholder="代码或名称"
              value={draft.symbol}
              onChange={(event) => setDraft({ ...draft, symbol: event.target.value })}
              onKeyDown={(event) => { if (event.key === 'Enter') setApplied(draft); }}
              aria-label="按标的筛选"
            />
            <input type="date" value={draft.from} onChange={(event) => setDraft({ ...draft, from: event.target.value })} aria-label="开始日期" />
            <input type="date" value={draft.to} onChange={(event) => setDraft({ ...draft, to: event.target.value })} aria-label="结束日期" />
            <select value={draft.accountId} onChange={(event) => setDraft({ ...draft, accountId: event.target.value })} aria-label="按账户筛选">
              <option value="">全部账户</option>
              {accounts.map((account) => (
                <option key={account.account_id} value={account.account_id}>{account.name || account.account_id}</option>
              ))}
            </select>
            <button className="ghost" onClick={() => setApplied(draft)}>查询</button>
            {hasFilters(applied) || hasFilters(draft) ? (
              <button className="ghost" onClick={() => { setDraft(NO_FILTERS); setApplied(NO_FILTERS); }}>清除</button>
            ) : null}
          </div>
        }
      >
        {visible.length > 0 ? (
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
          <span className="muted" style={{ fontSize: 11 }}>
            当前结果合计 <span className={toneOf(netTotal, scheme)}>{formatMoney(netTotal)}</span>
            {' · '}盈利 {wins} 笔 · 亏损 {Math.max(0, visible.length - wins)} 笔
          </span>
          <span className="muted" style={{ fontSize: 11 }}>
            {truncated ? '已载入最近 ' + PAGE_SIZE + ' 笔，合计仅覆盖本页 · ' : ''}点击表头排序 · 再点一次反序
          </span>
        </div>
        ) : null}

        {error ? <Banner>交易日志读取失败：{error}</Banner> : null}
        {loading ? <div className="muted">加载中…</div> : null}
        {!loading && !error && visible.length === 0 ? (
          <Empty text="还没有已配对平仓的交易。先到「数据导入」录入成交。" />
        ) : null}

        {visible.length > 0 ? (
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  {COLUMNS.map((column) => (
                    <th
                      key={column.key}
                      className={column.numeric ? 'num' : undefined}
                      aria-sort={sort.key === column.key ? (sort.descending ? 'descending' : 'ascending') : 'none'}
                    >
                      <button className="th-sort" onClick={() => toggleSort(column.key)}>
                        {column.label}
                        <span className="muted">{sort.key === column.key ? (sort.descending ? ' ▼' : ' ▲') : ''}</span>
                      </button>
                    </th>
                  ))}
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row, index) => (
                  <tr key={row.round_trip_id || row.trade_id || row.symbol + '-' + index}>
                    <td>
                      {row.name || row.symbol}
                      <span className="muted"> {row.symbol}</span>
                      {(row.tags || []).slice(0, 1).map((tag) => (
                        <span className="tag" style={{ marginLeft: 6 }} key={tag}>{tag}</span>
                      ))}
                    </td>
                    <td className="muted">{row.exit_time || '—'}</td>
                    <td className="num">{number(row.quantity).toLocaleString('zh-CN')}</td>
                    <td className={'num ' + toneOf(number(row.return_pct), scheme)}>{formatPct(number(row.return_pct))}</td>
                    <td className={'num ' + toneOf(number(row.net_pnl), scheme)}>{formatMoney(number(row.net_pnl))}</td>
                    <td className="num muted">{row.holding_days === undefined || row.holding_days === null ? '—' : row.holding_days + ' 天'}</td>
                    <td className="muted">{row.regime || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

function hasFilters(filters: Filters): boolean {
  return Boolean(filters.symbol || filters.from || filters.to || filters.accountId);
}

function cleanFilters(filters: Filters): { symbol?: string; from?: string; to?: string; account_id?: string } {
  const out: { symbol?: string; from?: string; to?: string; account_id?: string } = {};
  if (filters.symbol.trim()) out.symbol = filters.symbol.trim();
  if (filters.from) out.from = filters.from;
  if (filters.to) out.to = filters.to;
  if (filters.accountId) out.account_id = filters.accountId;
  return out;
}

/** A response that is missing its list is an empty list, never a crash. */
function listOf<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

/** Numeric columns tolerate a null or a string from the wire. */
function number(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function compareRows(left: TradeLogEntry, right: TradeLogEntry, key: SortKey): number {
  if (key === 'symbol') return String(left.symbol || '').localeCompare(String(right.symbol || ''));
  if (key === 'exit_time') return String(left.exit_time || '').localeCompare(String(right.exit_time || ''));
  return number(left[key]) - number(right[key]);
}

export function messageOf(failure: unknown): string {
  return failure instanceof Error ? failure.message : String(failure);
}
