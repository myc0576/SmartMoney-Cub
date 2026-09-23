import { useMemo } from 'react';
import type { Issue, OpenPosition, TradeLogEntry, TraderSummary } from '../types';
import { Kpi, Panel, Sparkline, formatCost, formatMoney, formatPct, toneOf } from '../components/common';
import { monetaryTotal, currencyTotals } from '../money';
import { getLocale } from '../i18n';

/**
 * Overview: what today asks of the trader, before it shows what the account has
 * done.
 *
 * The page used to open on six KPI tiles and an equity curve. Those numbers are
 * true and they are not an answer to the question a person brings to the app in
 * the morning, which is what to do next. So the top of the page is today -- the
 * session's result, how much of it followed the plan, and three cards that name
 * a concrete next action. The metrics and the curve are still here, below, where
 * a trader goes once the question is answered.
 *
 * Everything on this page comes from the tenant's own ledger:
 * /api/trader/analytics/summary for the metrics and /api/trader/trades for the
 * rows behind them. Nothing is derived from the review workbench's store, so one
 * import fills the whole page.
 *
 * What the data cannot answer, the page says it cannot answer. A plan-following
 * count over trades with no recorded plan would be a fabricated number, and a
 * fabricated discipline score is the most damaging thing this page could show.
 */

/** How many recent closes the panel lists before it offers the full log. */
const RECENT_LIMIT = 8;

export function OverviewView({
  summary, recent, openPositions, issues, ledgerStatus, scheme,
  onGoToImport, onOpenLog, onOpenInsight, onOpenAssistant, onOpenTrade,
}: {
  summary: TraderSummary;
  recent: TradeLogEntry[];
  openPositions: OpenPosition[];
  issues: Issue[];
  ledgerStatus: string;
  scheme: 'cn' | 'intl';
  onGoToImport: () => void;
  onOpenLog: () => void;
  onOpenInsight?: () => void;
  onOpenAssistant?: () => void;
  onOpenTrade?: (id: string) => void;
}) {
  const curve = summary.equity_curve.map((point) => point.cumulative_pnl);
  // A blocking issue is what drives the ledger to needs_review, so the notice
  // counts errors rather than every warning the matcher recorded.
  const blocking = issues.filter((issue) => issue.severity === 'error');
  const shown = recent.slice(0, RECENT_LIMIT);

  const today = useMemo(() => localDayKey(new Date()), []);
  const todayRows = useMemo(
    () => recent.filter((row) => localDayKeyOf(row.exit_time) === today),
    [recent, today],
  );
  const todayPnl = monetaryTotal(todayRows);

  // The plan fields the journal actually stores. A row with no invalidation price
  // cannot be judged against a plan, so it is counted as unrecorded rather than as
  // a violation or a pass.
  const todayAssessed = todayRows.filter((row) => stored(row.invalidation_price) !== null);
  const todayDeviations = todayAssessed.filter(
    (row) => stored(row.exit_price) !== null && (row.position_side === 'SHORT'
      ? stored(row.exit_price)! > stored(row.invalidation_price)!
      : stored(row.exit_price)! < stored(row.invalidation_price)!),
  );
  const todayUnrecorded = todayRows.length - todayAssessed.length;

  // The heaviest single loss today, which is the concrete thing worth looking at
  // first. A day with no loss has no such trade, and the card says so.
  const worstToday = (todayPnl === null ? [] : todayRows)
    .filter((row) => number(row.net_pnl) < 0)
    .sort((left, right) => number(left.net_pnl) - number(right.net_pnl))[0];

  // A pattern has to be a repeat to be a pattern. Three or more closes of the
  // same symbol inside the loaded window is the weakest count that still means
  // something, and the card prints that count so the reader can judge it.
  const repeated = useMemo(() => {
    const seen = new Map<string, TradeLogEntry[]>();
    for (const row of recent) {
      const key = String(row.symbol || '').trim();
      if (!key) continue;
      seen.set(key, [...(seen.get(key) || []), row]);
    }
    return [...seen.entries()]
      .filter(([, rows]) => rows.length >= 3)
      .sort((left, right) => right[1].length - left[1].length)[0] || null;
  }, [recent]);

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

      {/* Today, first. */}
      <Panel title="今天你需要关注什么">
        <div className="today-head">
          {todayRows.length === 0 ? (
            <div className="muted">
              今天还没有平仓交易。
              {recent.length === 0 ? ' 台账里还没有已确认的平仓，先导入成交。' : ''}
            </div>
          ) : (
            <>
              <div className="today-line">
                今天完成 <strong>{todayRows.length}</strong> 笔，净收益{' '}
                <span className={toneOf(todayPnl, scheme)} style={{ fontWeight: 600 }}>{formatMoney(todayPnl)}</span>
                {currencyTotals(todayRows).map(total => <span className="tag" key={total.currency}>{total.currency} {formatMoney(total.value)}</span>)}
                {todayAssessed.length > 0 ? (
                  <>
                    {' · '}
                    对照了计划的 <strong>{todayAssessed.length}</strong> 笔中{' '}
                    <strong>{todayDeviations.length}</strong> 笔平仓价越过失效价
                  </>
                ) : null}
              </div>
              {todayUnrecorded > 0 ? (
                <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                  其中 {todayUnrecorded} 笔没有记录失效价，无法判断是否遵守计划。
                </div>
              ) : null}
            </>
          )}
        </div>
      </Panel>

      <div className="today-cards">
        <ActionCard
          kicker="今日最重要问题"
          title={
            worstToday
              ? (worstToday.name || worstToday.symbol) + ' 亏了 ' + formatMoney(number(worstToday.net_pnl))
              : todayPnl === null ? '币种不同或未知，无法比较最大亏损' : '今天没有亏损平仓'
          }
          body={
            worstToday
              ? '今天最大的一笔亏损来自 ' + worstToday.symbol + '，平仓于 ' + (worstToday.exit_time || '未记录') + '。'
              : todayPnl === null ? '请选择同一已知币种的账户查看，不进行未经汇率换算的金额比较。' : '今天平仓的交易里没有亏损，或者今天还没有平仓。这一格不是表扬，只是事实。'
          }
          action={onOpenTrade && worstToday && (worstToday.round_trip_id || worstToday.trade_id)
            ? { label: '打开这一笔', onClick: () => onOpenTrade(String(worstToday.round_trip_id || worstToday.trade_id)) }
            : undefined}
        />
        <ActionCard
          kicker="正在形成的模式"
          title={repeated ? repeated[0] + ' 反复出现' : '还没有形成重复的模式'}
          body={repeated
            ? '最近载入的 ' + recent.length + ' 笔平仓里，' + repeated[0] + ' 出现 ' + repeated[1].length + ' 次，合计净盈亏 '
              + formatMoney(monetaryTotal(repeated[1])) + '。次数不算多，先看是什么模式。'
            : '最近载入的平仓里没有任何标的重合到 3 笔以上。样本不够就不叫模式。'}
          action={onOpenInsight ? { label: '交给洞察分析', onClick: onOpenInsight } : undefined}
        />
        <ActionCard
          kicker="今日待复盘"
          title={todayRows.length === 0 ? '今天没有需要复盘的交易' : todayRows.length + ' 笔今日交易可复盘'}
          body={todayRows.length === 0
            ? '等今天有平仓之后，这里会列出可以复盘的对象。'
            : '复盘助手会读这些交易的成交、台账问题与 Champion 规则，在右侧给出结论并引用证据。'}
          action={onOpenAssistant ? { label: '打开复盘助手', onClick: onOpenAssistant } : undefined}
        />
      </div>

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
                查看全部
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
                      onClick={() => {
                        const id = trade.round_trip_id || trade.trade_id;
                        if (onOpenTrade && id) onOpenTrade(id);
                        else onOpenLog();
                      }}
                      title={onOpenTrade ? '打开这一笔的复盘工作台' : '在交易日志中查看'}
                    >
                      <td>{trade.name || trade.symbol}<span className="muted"> {trade.symbol}</span></td>
                      <td className="muted">{trade.exit_time || '—'}</td>
                      <td className={'num ' + toneOf(trade.return_pct, scheme)}>{formatPct(trade.return_pct)}</td>
                      <td className={'num ' + toneOf(trade.net_pnl, scheme)}>{trade.currency || 'UNKNOWN'} {formatMoney(trade.net_pnl)}</td>
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
                    <td className="num">{number(position.quantity).toLocaleString(getLocale())}</td>
                    <td className="num">{position.currency || 'UNKNOWN'} {position.avg_cost ?? '—'}</td>
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

/** One thing worth doing next, with the action that starts it. */
function ActionCard({ kicker, title, body, action }: {
  kicker: string;
  title: string;
  body: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="action-card">
      <div className="action-kicker">{kicker}</div>
      <div className="action-title">{title}</div>
      <div className="action-body">{body}</div>
      {action ? (
        <button className="ghost action-go" onClick={action.onClick}>{action.label} →</button>
      ) : null}
    </div>
  );
}

/** A stored number, or null when the journal does not hold one. */
function stored(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** The calendar day a timestamp belongs to, in the reader's own zone. */
function localDayKey(when: Date): string {
  const month = String(when.getMonth() + 1).padStart(2, '0');
  const day = String(when.getDate()).padStart(2, '0');
  return when.getFullYear() + '-' + month + '-' + day;
}

/** The day part of a stored timestamp, which arrives as a space-separated local
 *  string rather than as ISO-8601 with a zone. */
function localDayKeyOf(value: unknown): string {
  const text = String(value || '').trim();
  if (!text) return '';
  return text.split(/[ T]/)[0] || '';
}

/** A numeric column tolerates a null or a string from the wire. */
function number(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
