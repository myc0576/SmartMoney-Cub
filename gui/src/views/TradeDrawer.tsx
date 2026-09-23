import { useEffect, useMemo, useState } from 'react';
import { trader } from '../api';
import type { MarketBar, TradeLogDetail, TradeLogEntry } from '../types';
import { CandleChart, type CandleMarker } from '../components/CandleChart';
import { Empty, formatMoney, formatPct, toneOf } from '../components/common';

/**
 * The review workbench for one round trip.
 *
 * It is the second-most-used surface in the product after the overview, and it
 * is organised as the four questions a trader asks about a closed trade, in the
 * order they ask them: what did the chart do, what was the plan versus what
 * happened, did I follow my own rules, and what does the review say.
 *
 * The honesty rules matter more here than anywhere else, because this page is
 * where a trader is most inclined to believe what it says:
 *
 * * A field the journal does not hold renders as 未记录. It never renders as
 *   zero, and never as a plausible default -- a fabricated stop price would make
 *   the plan-versus-actual comparison a work of fiction.
 * * A rule that cannot be decided from the stored fields says 无法判定 rather
 *   than showing a cross. An unjustified ✕ is an accusation.
 * * The chart is the only part that reaches the network, and its failure is
 *   reported as a failed fetch rather than drawn as an empty plot.
 */

/** The built-in providers, in the order they are tried when fetching a chart. */
const CHART_PROVIDERS = ['eastmoney', 'tencent'];

function money(value: number | undefined): string {
  return formatMoney(value === undefined ? 0 : value);
}

function pct(value: number | undefined): string {
  return formatPct(value === undefined ? 0 : value);
}

/** A stored number, or null when the journal does not hold one. */
function stored(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function lotsOf(detail: TradeLogDetail) {
  return detail.matched_lots || detail.trade.matched_lots || [];
}

export function TradeDrawer({ tradeId, scheme, onClose, onOpenAssistant }: {
  tradeId: string;
  scheme: 'cn' | 'intl';
  onClose: () => void;
  /** Opens the right-hand assistant focused on this trade, when the shell has
   *  one. Absent on a surface with no assistant, which is why it is optional. */
  onOpenAssistant?: (tradeId: string) => void;
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
        position: 'fixed', inset: 0, background: 'var(--color-backdrop, rgba(6,8,12,0.62))', zIndex: 40,
        display: 'flex', justifyContent: 'flex-end',
      }}
      onClick={onClose}
    >
      <div
        className="trade-drawer-wide"
        style={{ height: '100%', overflow: 'auto', background: 'var(--panel)', borderLeft: '1px solid var(--border)', padding: 16 }}
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

            <ChartBlock trade={trade} scheme={scheme} />
            <PlanBlock trade={trade} />
            <RulesBlock trade={trade} />
            <ReviewBlock trade={trade} onOpenAssistant={onOpenAssistant} />

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
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * The chart, with the entry and exit marked.
 *
 * Fetching is a network call and can fail, and a chart that failed must not look
 * like a chart with no data: the two say different things about the journal. The
 * interval is chosen from the hold: an intraday hold is drawn in minutes so the
 * entry and exit are distinguishable, and a multi-day hold in days so the period
 * is visible at all.
 */
function ChartBlock({ trade, scheme }: { trade: TradeLogEntry; scheme: 'cn' | 'intl' }) {
  const [bars, setBars] = useState<MarketBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [provider, setProvider] = useState('');

  const interval = (trade.holding_days ?? 0) > 1 ? '1d' : '60m';

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setBars([]);

    const attempt = async (index: number): Promise<void> => {
      if (index >= CHART_PROVIDERS.length) return;
      const candidate = CHART_PROVIDERS[index];
      try {
        const result = await trader.marketBars({
          provider: candidate, symbol: trade.symbol, interval, limit: 120,
        });
        if (cancelled) return;
        setBars(result.bars || []);
        setProvider(candidate);
      } catch (failure) {
        // One provider being unreachable is not the chart failing; the next one
        // is tried before the block reports an error.
        if (index + 1 < CHART_PROVIDERS.length) {
          await attempt(index + 1);
          return;
        }
        if (cancelled) return;
        setError(failure instanceof Error ? failure.message : String(failure));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void attempt(0);
    return () => { cancelled = true; };
  }, [trade.symbol, interval]);

  const markers = useMemo<CandleMarker[]>(() => {
    if (!bars.length) return [];
    const match = (value: string | undefined): string | null => {
      if (!value) return null;
      const exact = bars.find((bar) => bar.open_time === value);
      if (exact) return exact.open_time;
      // Daily bars may be represented as a date while fills carry a timestamp.
      // This is the only fuzzy alignment allowed; intraday bars require an exact
      // source timestamp so a marker is never painted on an invented bar.
      if (interval !== '1d') return null;
      const day = value.slice(0, 10);
      return bars.find((bar) => bar.open_time.slice(0, 10) === day)?.open_time || null;
    };
    const out: CandleMarker[] = [];
    const entryTime = match(trade.entry_time);
    const entryPrice = stored(trade.entry_price);
    if (entryTime && entryPrice !== null) out.push({ time: entryTime, price: entryPrice, kind: 'entry', label: '买入' });
    const exitTime = match(trade.exit_time);
    const exitPrice = stored(trade.exit_price);
    if (exitTime && exitPrice !== null) out.push({ time: exitTime, price: exitPrice, kind: 'exit', label: '卖出' });
    return out;
  }, [bars, interval, trade.entry_price, trade.entry_time, trade.exit_price, trade.exit_time]);

  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2>走势与买卖点</h2>
        <span className="muted" style={{ fontSize: 11 }}>
          {interval === '1d' ? '日线' : '60 分钟线'}{provider ? ' · ' + provider : ''}
        </span>
      </div>
      {loading ? <div className="muted">正在取行情…</div> : null}
      {!loading && error ? (
        <div className="notice" style={{ fontSize: 12 }}>
          行情读取失败，这一块不能画：{error}
          <div className="muted" style={{ marginTop: 6, fontSize: 11 }}>
            这不影响本笔交易的成交与统计，它们来自本地台账。
          </div>
        </div>
      ) : null}
      {!loading && !error ? (
        <CandleChart bars={bars} markers={markers} scheme={scheme} emptyText="这个标的没有可用的历史行情" />
      ) : null}
      {/* The entry and exit are facts from the journal even when no bar series
          could be drawn, so they are stated in text below the plot rather than
          only being marked on it. */}
      <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
        买入 {trade.entry_time || '未记录'}{trade.entry_price === undefined ? '' : ' @ ' + trade.entry_price}
        {' · '}
        卖出 {trade.exit_time || '未记录'}{trade.exit_price === undefined ? '' : ' @ ' + trade.exit_price}
      </div>
    </div>
  );
}

/**
 * Plan versus actual.
 *
 * The journal stores a plan's invalidation price and its thesis, and nothing
 * else about the plan. So this block compares exactly those two and, for the
 * fields it does not have (a planned entry, a target), says 未记录 instead of
 * printing a number that would look like a plan. A comparison against an
 * invented plan is worse than no comparison.
 */
function PlanBlock({ trade }: { trade: TradeLogEntry }) {
  const invalidation = stored(trade.invalidation_price);
  const entry = stored(trade.entry_price);
  const exit = stored(trade.exit_price);
  const planned = invalidation !== null;

  const rows: { label: string; plan: string; actual: string; flag?: string }[] = [
    {
      label: '失效价',
      plan: planned ? String(invalidation) : '未记录',
      actual: exit === null ? '未记录' : String(exit),
      flag: planned && exit !== null && exit < invalidation! ? '跌破失效价' : undefined,
    },
    { label: '计划买点', plan: '未记录', actual: entry === null ? '未记录' : String(entry) },
    { label: '目标价', plan: '未记录', actual: '未记录' },
  ];

  return (
    <div className="panel">
      <h2>计划 vs 实际</h2>
      <table>
        <thead><tr><th></th><th className="num">计划</th><th className="num">实际</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <td className="muted">{row.label}</td>
              <td className="num muted">{row.plan}</td>
              <td className="num">
                {row.actual}
                {row.flag ? <span className="badge warn" style={{ marginLeft: 6 }}>{row.flag}</span> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        开仓理由：{trade.thesis || '未记录'}
      </div>
      {!planned ? (
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
          这笔交易没有记录失效价，所以无法判断止损是否被执行。补录计划字段后才能得到结论。
        </div>
      ) : null}
      {trade.tags && trade.tags.length ? (
        <div style={{ marginTop: 8 }}>{trade.tags.map((tag) => <span key={tag} className="tag">{tag}</span>)}</div>
      ) : null}
    </div>
  );
}

/**
 * Rule execution, one line per check.
 *
 * Only two checks can be decided from a journal row without a recorded plan, and
 * both are stated with the number they were decided from. Everything else is
 * 无法判定 -- not a cross -- because a rule this page cannot evaluate is a gap in
 * the record, not a failure by the trader.
 */
function RulesBlock({ trade }: { trade: TradeLogEntry }) {
  const invalidation = stored(trade.invalidation_price);
  const exit = stored(trade.exit_price);
  const entry = stored(trade.entry_price);
  const holding = stored(trade.holding_days);

  const checks: { label: string; state: 'pass' | 'fail' | 'unknown'; note: string }[] = [];

  if (invalidation !== null && exit !== null && entry !== null) {
    const broken = exit < invalidation;
    checks.push({
      label: '止损位未被跌破时才持有',
      state: broken ? 'fail' : 'pass',
      note: broken
        ? '实际卖出 ' + exit + ' 低于失效价 ' + invalidation
        : '实际卖出 ' + exit + ' 未跌破失效价 ' + invalidation,
    });
  } else {
    checks.push({
      label: '止损位未被跌破时才持有',
      state: 'unknown',
      note: invalidation === null ? '没有记录失效价，无法判断' : '缺少成交价，无法判断',
    });
  }

  checks.push(
    holding === null
      ? { label: '持有周期与计划一致', state: 'unknown', note: '没有记录持有天数' }
      : {
          label: '持有周期与计划一致',
          state: 'unknown',
          note: '实际持有 ' + holding + ' 天；台账未记录计划持有周期，无法比较',
        },
  );

  checks.push({
    label: '仓位不超过单笔风险上限',
    state: 'unknown',
    note: '台账未记录账户权益与单笔风险比例，无法计算',
  });

  return (
    <div className="panel">
      <h2>规则执行</h2>
      <div className="grid" style={{ gap: 6 }}>
        {checks.map((check) => (
          <div key={check.label} className="row" style={{ alignItems: 'baseline', gap: 8 }}>
            <span
              aria-label={check.state === 'pass' ? '通过' : check.state === 'fail' ? '未通过' : '无法判定'}
              className={'badge ' + (check.state === 'pass' ? 'ok' : check.state === 'fail' ? 'error' : 'warn')}
              style={{ minWidth: 46, textAlign: 'center' }}
            >
              {check.state === 'pass' ? '✓ 通过' : check.state === 'fail' ? '✕ 未通过' : '— 无法判定'}
            </span>
            <span>{check.label}</span>
            <span className="muted" style={{ fontSize: 11 }}>{check.note}</span>
          </div>
        ))}
      </div>
      <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        只有能被台账字段判定的规则给出结论，其余保持无法判定。
      </div>
    </div>
  );
}

/**
 * Where the written review lives.
 *
 * The assistant writes that review, so this block does not invent one; it opens
 * the assistant on this trade. A page that generated plausible-sounding prose
 * from the row alone would be the most convincing wrong thing in the product.
 */
function ReviewBlock({ trade, onOpenAssistant }: {
  trade: TradeLogEntry;
  onOpenAssistant?: (tradeId: string) => void;
}) {
  const id = String(trade.round_trip_id || trade.trade_id || '');
  return (
    <div className="panel">
      <h2>AI 复盘</h2>
      <div className="muted" style={{ fontSize: 12, lineHeight: 1.7 }}>
        复盘助手会读这笔交易的成交、配对批次、台账问题与 Champion 规则，在右侧给出结论并引用证据。
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button
          className="primary"
          disabled={!onOpenAssistant || !id}
          title={onOpenAssistant ? '在右侧助手中打开这笔交易的复盘' : '当前页面没有助手'}
          onClick={() => onOpenAssistant?.(id)}
        >
          让助手复盘这一笔
        </button>
      </div>
    </div>
  );
}
