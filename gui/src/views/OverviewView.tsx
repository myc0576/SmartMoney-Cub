import { useMemo } from 'react';
import type { Issue, OpenPosition, TradeLogEntry, TraderSummary } from '../types';
import { Kpi, Panel, Sparkline, formatCost, formatMoney, formatPct, toneOf } from '../components/common';
import { monetaryTotal, currencyTotals } from '../money';
import { getLocale, useI18n } from '../i18n';

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
  const { t } = useI18n();
  const curve = summary.equity_curve.map((point) => point.cumulative_pnl);
  // A blocking issue is what drives the ledger to needs_review, so the notice
  // counts errors rather than every warning the matcher recorded.
  const blocking = issues.filter((issue) => issue.severity === 'error');
  const shown = recent.slice(0, RECENT_LIMIT);
  const isEmptyLedger = recent.length === 0 && openPositions.length === 0 && summary.trade_count === 0;

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
          {t('overview.needsReview', { count: blocking.length })}
          <button className="ghost" style={{ marginLeft: 10, fontSize: 11 }} onClick={onGoToImport}>
            {t('overview.resolve')}
          </button>
        </div>
      ) : null}

      {isEmptyLedger ? (
        <section className="panel onboarding-card" data-testid="first-run-onboarding">
          <div className="onboarding-kicker">{t('overview.onboarding.kicker')}</div>
          <h2 className="onboarding-title">{t('overview.onboarding.title')}</h2>
          <p className="onboarding-body">{t('overview.onboarding.body')}</p>
          <ol className="onboarding-steps">
            <li>{t('overview.onboarding.step1')}</li>
            <li>{t('overview.onboarding.step2')}</li>
            <li>{t('overview.onboarding.step3')}</li>
          </ol>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="primary" onClick={onGoToImport}>{t('overview.onboarding.ctaImport')}</button>
            {onOpenAssistant ? (
              <button className="ghost" onClick={onOpenAssistant}>{t('overview.onboarding.ctaAssistant')}</button>
            ) : null}
          </div>
        </section>
      ) : null}

      {/* Today, first. */}
      <Panel title={t('overview.today.title')}>
        <div className="today-head">
          {todayRows.length === 0 ? (
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="muted">
                {t('overview.today.empty')}
                {recent.length === 0 ? t('overview.today.emptyLedger') : ''}
              </div>
              {recent.length === 0 ? (
                <button className="ghost" style={{ fontSize: 11 }} onClick={onGoToImport}>
                  {t('overview.card.review.importAction')} →
                </button>
              ) : null}
            </div>
          ) : (
            <>
              <div className="today-line">
                {t('overview.today.summary', { count: todayRows.length })}
                <span className={'num ' + toneOf(todayPnl, scheme)} style={{ fontWeight: 600 }}>{formatMoney(todayPnl)}</span>
                {currencyTotals(todayRows).map(total => <span className="tag" key={total.currency}>{total.currency} {formatMoney(total.value)}</span>)}
                {todayAssessed.length > 0 ? (
                  <>
                    {' · '}
                    {t('overview.today.planCheck', { assessed: todayAssessed.length, deviations: todayDeviations.length })}
                  </>
                ) : null}
              </div>
              {todayUnrecorded > 0 ? (
                <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                  {t('overview.today.unrecorded', { count: todayUnrecorded })}
                </div>
              ) : null}
            </>
          )}
        </div>
      </Panel>

      <div className="today-cards">
        <ActionCard
          kicker={t('overview.card.worst.kicker')}
          title={
            worstToday
              ? t('overview.card.worst.title', { name: worstToday.name || worstToday.symbol, amount: formatMoney(number(worstToday.net_pnl)) })
              : todayPnl === null ? t('overview.card.worst.mixedTitle') : t('overview.card.worst.noneTitle')
          }
          body={
            worstToday
              ? t('overview.card.worst.body', { symbol: worstToday.symbol, time: worstToday.exit_time || t('overview.unrecorded') })
              : todayPnl === null
                ? t('overview.card.worst.mixedBody')
                : recent.length === 0 ? t('overview.card.worst.emptyBody') : t('overview.card.worst.noneBody')
          }
          action={onOpenTrade && worstToday && (worstToday.round_trip_id || worstToday.trade_id)
            ? { label: t('overview.card.worst.action'), onClick: () => onOpenTrade(String(worstToday.round_trip_id || worstToday.trade_id)) }
            : recent.length === 0 ? { label: t('overview.card.review.importAction'), onClick: onGoToImport } : undefined}
        />
        <ActionCard
          kicker={t('overview.card.pattern.kicker')}
          title={repeated ? t('overview.card.pattern.title', { symbol: repeated[0] }) : t('overview.card.pattern.noneTitle')}
          body={repeated
            ? t('overview.card.pattern.body', { total: recent.length, symbol: repeated[0], count: repeated[1].length, pnl: formatMoney(monetaryTotal(repeated[1])) })
            : t('overview.card.pattern.noneBody')}
          action={onOpenInsight ? { label: t('overview.card.pattern.action'), onClick: onOpenInsight } : undefined}
        />
        <ActionCard
          kicker={t('overview.card.review.kicker')}
          title={todayRows.length === 0 ? t('overview.card.review.noneTitle') : t('overview.card.review.countTitle', { count: todayRows.length })}
          body={recent.length === 0
            ? t('overview.card.review.emptyBody')
            : todayRows.length === 0
              ? t('overview.card.review.noneBody')
              : t('overview.card.review.body')}
          action={recent.length === 0
            ? { label: t('overview.card.review.importAction'), onClick: onGoToImport }
            : onOpenAssistant ? { label: t('overview.card.review.action'), onClick: onOpenAssistant } : undefined}
        />
      </div>

      <div className="grid kpi">
        <Kpi label={t('overview.kpi.netPnl')} value={formatMoney(summary.total_net_pnl)} tone={toneOf(summary.total_net_pnl, scheme)} note={t('overview.kpi.closedCount', { count: summary.trade_count })} />
        <Kpi label={t('overview.kpi.winRate')} value={summary.win_rate + '%'} note={t('overview.kpi.winLoss', { wins: summary.win_count, losses: summary.loss_count })} />
        <Kpi
          label={t('overview.kpi.profitFactor')}
          value={summary.profit_factor === null ? '—' : String(summary.profit_factor)}
          note={summary.profit_factor === null ? summary.profit_factor_note : t('overview.kpi.pfFormula')}
        />
        <Kpi label={t('overview.kpi.maxDrawdown')} value={formatMoney(summary.max_drawdown)} tone={toneOf(summary.max_drawdown, scheme)} note={t('overview.kpi.closeOrder')} />
        <Kpi label={t('overview.kpi.avgHolding')} value={t('overview.kpi.daysUnit', { days: summary.avg_holding_days })} note={t('overview.kpi.avgReturn', { pct: formatPct(summary.avg_return_pct) })} />
        <Kpi label={t('overview.kpi.fees')} value={formatCost(summary.total_fees)} note={t('overview.kpi.openCount', { count: summary.open_position_count })} />
      </div>

      <Panel title={t('overview.curve.title')}>
        <Sparkline points={curve} scheme={scheme} />
        <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>{summary.sample_note}</div>
      </Panel>

      <div className="grid split">
        <Panel
          title={t('overview.recent.title')}
          actions={
            recent.length > shown.length ? (
              <button className="ghost" style={{ fontSize: 11 }} onClick={onOpenLog}>
                {t('overview.recent.viewAll')}
              </button>
            ) : null
          }
        >
          {recent.length === 0 ? (
            <div className="empty">
              <div>{t('overview.recent.empty')}</div>
              <button className="ghost" style={{ marginTop: 10, fontSize: 11 }} onClick={onGoToImport}>
                {t('overview.onboarding.ctaImport')} →
              </button>
            </div>
          ) : (
            <div className="scroll-x">
              <table>
                <thead>
                  <tr>
                    <th>{t('overview.col.symbol')}</th><th>{t('overview.col.exitTime')}</th><th className="num">{t('overview.col.return')}</th><th className="num">{t('overview.col.netPnl')}</th>
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
                      title={onOpenTrade ? t('overview.recent.openHint') : t('overview.recent.logHint')}
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

        <Panel title={t('overview.openPositions.title')}>
          {openPositions.length === 0 ? (
            <div className="muted">{t('overview.openPositions.empty')}</div>
          ) : (
            <div className="scroll-x">
              <table>
                <thead><tr><th>{t('overview.col.symbol')}</th><th className="num">{t('overview.col.qty')}</th><th className="num">{t('overview.col.avgCost')}</th><th>{t('overview.col.openedAt')}</th></tr></thead>
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
            </div>
          )}
        </Panel>
      </div>

      <Panel title={t('overview.issues.title')}>
        {issues.length === 0 ? (
          <div className="muted">{t('overview.issues.empty')}</div>
        ) : (
          <div className="scroll-x">
            <table>
              <thead><tr><th>{t('overview.issues.severity')}</th><th>{t('overview.issues.code')}</th><th>{t('overview.col.symbol')}</th><th>{t('overview.issues.detail')}</th></tr></thead>
              <tbody>
                {issues.slice(0, 12).map((issue, index) => (
                  <tr key={issue.code + index}>
                    <td>{issue.severity === 'error' ? <span className="badge error">{t('overview.issues.error')}</span> : <span className="badge warn">{t('overview.issues.warn')}</span>}</td>
                    <td className="muted">{issue.code}</td>
                    <td>{issue.symbol || '—'}</td>
                    <td style={{ whiteSpace: 'normal' }}>{issue.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
