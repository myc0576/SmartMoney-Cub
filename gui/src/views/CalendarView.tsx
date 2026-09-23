import { useEffect, useState } from 'react';
import { trader } from '../api';
import type { TraderCalendarDay } from '../types';
import { Panel, formatMoney, toneOf } from '../components/common';
import { useLegacyI18n } from '../locales/legacy';

/**
 * The review calendar: closed round trips aggregated by exit day.
 *
 * The days come from /api/trader/calendar, the journal's own store. This view
 * used to read the review workbench's calendar, which is a different database:
 * an import wrote the journal and left this grid empty. The day shape this view
 * renders is the trader route's own — date, trade count, net pnl, win count and
 * the rows behind them — so the grid, the month total, and the day sheet all
 * read the journal the import filled.
 */

export function CalendarView({ scheme, initial }: { scheme: 'cn' | 'intl'; initial: { year: number; month: number } }) {
  const { locale, t } = useLegacyI18n();
  const weekdayFormatter = new Intl.DateTimeFormat(locale, { weekday: 'short' });
  const weekdays = Array.from({ length: 7 }, (_, index) => weekdayFormatter.format(new Date(2024, 0, index + 1)));
  const [year, setYear] = useState(initial.year);
  const [month, setMonth] = useState(initial.month);
  const [days, setDays] = useState<TraderCalendarDay[]>([]);
  const [selected, setSelected] = useState<TraderCalendarDay | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    void trader
      .calendar({ year, month })
      .then((result) => {
        if (!cancelled) setDays(result.days || []);
      })
      .catch(() => {
        if (!cancelled) {
          setDays([]);
          setError(true);
        }
      });
    return () => { cancelled = true; };
  }, [year, month, revision]);

  const first = new Date(year, month - 1, 1);
  const startOffset = (first.getDay() + 6) % 7;
  const total = new Date(year, month, 0).getDate();
  const byDate = new Map(days.map((day) => [day.date, day]));
  const cells: (TraderCalendarDay | null)[] = [
    ...Array.from({ length: startOffset }, () => null),
    ...Array.from({ length: total }, (_, index) => {
      const date = year + '-' + String(month).padStart(2, '0') + '-' + String(index + 1).padStart(2, '0');
      return byDate.get(date) || { date, trade_count: 0, net_pnl: 0, win_count: 0, trades: [] };
    }),
  ];
  const monthTotal = days.reduce((sum, day) => sum + day.net_pnl, 0);

  const shift = (delta: number) => {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
    setSelected(null);
  };

  return (
    <div className="grid" style={{ gap: 14 }}>
      <Panel
        title={t('calendar.month', { year, month })}
        actions={
          <div className="row">
            <span className={'muted'} style={{ marginRight: 8 }}>
              {t('calendar.total')} <span className={toneOf(monthTotal, scheme)}>{formatMoney(monthTotal)}</span>
            </span>
            <button className="ghost" onClick={() => shift(-1)}>{t('calendar.previous')}</button>
            <button className="ghost" onClick={() => shift(1)}>{t('calendar.next')}</button>
          </div>
        }
      >
        {error ? (
          <div className="banner" role="alert" style={{ marginBottom: 12 }}>
            日历数据读取失败。请检查本地服务后重试。{' '}
            <button className="ghost" onClick={() => setRevision((value) => value + 1)}>重试</button>
          </div>
        ) : null}
        <div className="calendar">
          {weekdays.map((weekday) => <div key={weekday} className="weekday">{weekday}</div>)}
        </div>
        <div className="calendar" style={{ marginTop: 4 }}>
          {cells.map((day, index) => {
            if (!day) return <div key={'empty-' + index} className="cell empty" />;
            const active = day.trade_count > 0;
            return (
              <button
                key={day.date}
                className="cell"
                style={{ textAlign: 'left', background: active ? undefined : 'var(--inset)' }}
                onClick={() => setSelected(day)}
              >
                <div className="day">{Number(day.date.slice(-2))}</div>
                {active ? (
                  <>
                    <div className={'pnl ' + toneOf(day.net_pnl, scheme)}>{formatMoney(day.net_pnl, 0)}</div>
                    <div className="muted" style={{ fontSize: 10 }}>{t('calendar.trades', { count: day.trade_count })} · {t('calendar.wins', { count: day.win_count })}</div>
                  </>
                ) : null}
              </button>
            );
          })}
        </div>
      </Panel>

      {selected ? (
        <Panel title={t('calendar.detail', { date: selected.date })}>
          {selected.trades.length === 0 ? <div className="muted">{t('calendar.empty')}</div> : (
            <table>
              <thead><tr><th>{t('calendar.symbol')}</th><th className="num">{t('calendar.return')}</th><th className="num">{t('calendar.netPnl')}</th></tr></thead>
              <tbody>
                {selected.trades.map((trade) => (
                  <tr key={trade.round_trip_id}>
                    <td>{trade.name || trade.symbol}<span className="muted"> {trade.symbol}</span></td>
                    <td className={'num ' + toneOf(trade.return_pct, scheme)}>{trade.return_pct}%</td>
                    <td className={'num ' + toneOf(trade.net_pnl, scheme)}>{formatMoney(trade.net_pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      ) : null}
    </div>
  );
}
