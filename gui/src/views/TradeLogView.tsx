import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { trader, getTraderAccountScope } from '../api';
import type { OpenPosition, TradeLogEntry, TraderAccount } from '../types';
import { Banner, Empty, Panel, formatMoney, formatPct, toneOf } from '../components/common';
import { monetaryTotal, currencyTotals } from '../money';
import { formatDateTime, getLocale, useI18n } from '../i18n';
import { useJournalCopy } from '../locales/journal';
import { useLegacyI18n } from '../locales/legacy';

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

export function TradeLogView({ scheme, onOpenTrade, onGoToImport }: {
  scheme: 'cn' | 'intl';
  onOpenTrade?: (id: string) => void;
  onGoToImport?: () => void;
}) {
  const { t } = useI18n();
  const { t: legacy } = useLegacyI18n();
  const c = useJournalCopy();
  const columns: { key: SortKey; label: string; numeric?: boolean }[] = [
    { key: 'symbol', label: legacy('calendar.symbol') },
    { key: 'exit_time', label: c('closedAt') },
    { key: 'quantity', label: c('quantity'), numeric: true },
    { key: 'return_pct', label: legacy('calendar.return'), numeric: true },
    { key: 'net_pnl', label: legacy('calendar.netPnl'), numeric: true },
    { key: 'holding_days', label: c('holding'), numeric: true },
  ];
  const [rows, setRows] = useState<TradeLogEntry[]>([]);
  const [openPositions, setOpenPositions] = useState<OpenPosition[]>([]);
  const [accounts, setAccounts] = useState<TraderAccount[]>([]);
  const [draft, setDraft] = useState<Filters>(NO_FILTERS);
  const [applied, setApplied] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<{ key: SortKey; descending: boolean }>({ key: 'exit_time', descending: true });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [count, setCount] = useState(0);
  const [offset, setOffset] = useState(0);
  const generation = useRef(0);
  const [accountError, setAccountError] = useState('');
  const invalidRange = Boolean(draft.from && draft.to && draft.from > draft.to);
  const applyFilters = () => { if (!invalidRange) { setOffset(0); setApplied({ ...draft }); } };

  const load = useCallback(async () => {
    const requestGeneration = ++generation.current;
    setLoading(true);
    setError('');
    try {
      const result = await trader.trades({ ...cleanFilters(applied), limit: PAGE_SIZE, offset });
      if (requestGeneration !== generation.current) return;
      setRows(listOf(result.trades));
      // The unpaired side of the book arrives on the same response. It belongs
      // beside the closed rows: both answer "what is my position", and a journal
      // that only shows what is closed forgets what is still held.
      setOpenPositions(listOf(result.open_positions));
      // The endpoint returns its own count; when it exceeds the page there are
      // rows this view has not seen, and saying so is better than a filter that
      // quietly misses them.
      setCount(number(result.count));
      setError('');
    } catch (failure) {
      if (requestGeneration !== generation.current) return;
      setRows([]);
      setOpenPositions([]);
      setError(messageOf(failure));
    } finally {
      if (requestGeneration === generation.current) setLoading(false);
    }
  }, [applied, offset]);

  useEffect(() => { void load(); return () => { generation.current += 1; }; }, [load]);

  useEffect(() => {
    // A missing account list is not worth failing the page over: the filter
    // simply offers no options.
    void trader.accounts()
      .then((result) => setAccounts(listOf(result.accounts)))
      .catch(failure => { setAccounts([]); setAccountError(messageOf(failure)); });
  }, []);

  const visible = useMemo(() => {
    const sorted = [...rows].sort((left, right) => compareRows(left, right, sort.key));
    if (sort.descending) sorted.reverse();
    return sorted;
  }, [rows, sort]);

  const netTotal = monetaryTotal(visible);
  const totals = currencyTotals(visible);
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
        title={t('nav.trades') + ' (' + count + ')'}
        actions={
          <div className="row">
            <input
              placeholder={c('symbolPlaceholder')}
              value={draft.symbol}
              onChange={(event) => setDraft({ ...draft, symbol: event.target.value })}
              onKeyDown={(event) => { if (event.key === 'Enter') applyFilters(); }}
              aria-label={c('symbolFilter')}
            />
            <input type="date" value={draft.from} onChange={(event) => setDraft({ ...draft, from: event.target.value })} aria-label={c('start')} />
            <input type="date" value={draft.to} onChange={(event) => setDraft({ ...draft, to: event.target.value })} aria-label={c('end')} />
            {!getTraderAccountScope() ? <select value={draft.accountId} disabled={Boolean(accountError)} onChange={(event) => setDraft({ ...draft, accountId: event.target.value })} aria-label={c('accountFilter')}>
              <option value="">{t('top.allAccounts')}</option>
              {accounts.map((account) => (
                <option key={account.account_id} value={account.account_id}>{account.name || account.account_id}</option>
              ))}
            </select> : null}
            <button className="ghost" disabled={loading || invalidRange} onClick={applyFilters}>{c('query')}</button>
            {hasFilters(applied) || hasFilters(draft) ? (
              <button className="ghost" disabled={loading} onClick={() => { setOffset(0); setDraft(NO_FILTERS); setApplied(NO_FILTERS); }}>{c('clear')}</button>
            ) : null}
          </div>
        }
      >
        {invalidRange ? <p role="alert">{c('invalidRange')}</p> : null}
        {accountError ? <Banner>{t('error.read')}: {accountError}</Banner> : null}
        {!loading && !error && visible.length > 0 ? (
        <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
          <span className="muted" style={{ fontSize: 11 }}>
            {c('total')} <span className={toneOf(netTotal, scheme)}>{formatMoney(netTotal)}</span>
            {' · '}{legacy('reports.wins')} {wins} · {legacy('reports.losses')} {visible.filter(row => number(row.net_pnl) < 0).length}
            {totals.map(total => <span className="tag" key={total.currency}>{total.currency} {formatMoney(total.value)}</span>)}
          </span>
          <span className="muted" style={{ fontSize: 11 }}>
            {c('sortHint')}
          </span>
        </div>
        ) : null}

        {error ? <Banner>{t('error.read')}: {error} <button onClick={() => void load()}>{t('state.retry')}</button></Banner> : null}
        {loading ? <div className="muted">{t('state.loading')}</div> : null}
        {!loading && !error && visible.length === 0 ? (
          /* The empty list is where a trader learns the journal is empty, so the
             way to fill it is offered here rather than only in the sidebar. */
          <Empty text={c('empty')} />
        ) : null}
        {!loading && !error && visible.length === 0 && onGoToImport ? (
          <div className="row" style={{ justifyContent: 'center', marginTop: 8 }}>
            <button className="primary" onClick={onGoToImport}>{c('import')}</button>
          </div>
        ) : null}

        {!loading && !error && visible.length > 0 ? (
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  {columns.map((column) => (
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
                  <th>{legacy('settings.status')}</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row, index) => (
                    <tr
                      key={row.round_trip_id || row.trade_id || row.symbol + '-' + index}
                      onClick={() => openRow(onOpenTrade, row)}
                      title={onOpenTrade ? c('openTrade') : undefined}
                    >
                    <td>
                      {row.name || row.symbol}
                      <span className="muted"> {row.symbol}</span>
                      {(row.tags || []).slice(0, 1).map((tag) => (
                        <span className="tag" style={{ marginLeft: 6 }} key={tag}>{tag}</span>
                      ))}
                    </td>
                    <td className="muted">{formatDateTime(row.exit_time)}</td>
                    <td className="num">{number(row.quantity).toLocaleString(getLocale())}</td>
                    <td className={'num ' + toneOf(row.return_pct, scheme)}>{formatPct(row.return_pct)}</td>
                    <td className={'num ' + toneOf(row.net_pnl, scheme)}>{row.currency || 'UNKNOWN'} {formatMoney(row.net_pnl)}</td>
                    <td className="num muted">{row.holding_days === undefined || row.holding_days === null ? '—' : row.holding_days + ' ' + legacy('reports.days')}</td>
                    <td className="muted">{row.regime || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="row">
          <button className="ghost" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))}>{c('previous')}</button>
          <span className="num">{count ? offset + 1 : 0}–{Math.min(offset + visible.length, count)} / {count}</span>
          <button className="ghost" disabled={loading || offset + PAGE_SIZE >= count} onClick={() => setOffset(value => value + PAGE_SIZE)}>{c('next')}</button>
        </div>
      </Panel>

      {!error && !loading ? <Panel title={legacy('reports.openPositions') + ' (' + openPositions.length + ')'}>
        {openPositions.length === 0 ? (
          <div className="muted">{c('noPositions')}</div>
        ) : (
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>{legacy('calendar.symbol')}</th><th>{c('openedAt')}</th>
                  <th className="num">{c('quantity')}</th><th className="num">{c('averageCost')}</th>
                </tr>
              </thead>
              <tbody>
                {openPositions.map((position) => (
                  <tr key={position.position_id}>
                    <td>{position.name || position.symbol}<span className="muted"> {position.symbol}</span></td>
                    <td className="muted">{formatDateTime(position.opened_at)}</td>
                    <td className="num">{number(position.quantity).toLocaleString(getLocale())}</td>
                    <td className="num">{position.currency || 'UNKNOWN'} {position.avg_cost ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel> : null}
    </div>
  );
}

/** Open the review workbench for a row the detail route can address. A row
 *  without a round trip id has nothing to open, so the click is inert rather
 *  than opening a drawer over a record the route cannot fetch. */
function openRow(onOpenTrade: ((id: string) => void) | undefined, row: TradeLogEntry): void {
  const id = row.round_trip_id || row.trade_id;
  if (onOpenTrade && id) onOpenTrade(id);
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
  if (key === 'net_pnl' && left.currency !== right.currency) return String(left.currency || 'UNKNOWN').localeCompare(String(right.currency || 'UNKNOWN'));
  if (key === 'symbol') return String(left.symbol || '').localeCompare(String(right.symbol || ''));
  if (key === 'exit_time') return String(left.exit_time || '').localeCompare(String(right.exit_time || ''));
  return number(left[key]) - number(right[key]);
}

export function messageOf(failure: unknown): string {
  return failure instanceof Error ? failure.message : String(failure);
}
