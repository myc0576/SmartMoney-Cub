import { useEffect, useState } from 'react';
import { api } from '../api';
import type { CalendarDay } from '../types';
import { Panel, formatMoney, toneOf } from '../components/common';

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'];

export function CalendarView({ scheme, initial }: { scheme: 'cn' | 'intl'; initial: { year: number; month: number } }) {
  const [year, setYear] = useState(initial.year);
  const [month, setMonth] = useState(initial.month);
  const [days, setDays] = useState<CalendarDay[]>([]);
  const [selected, setSelected] = useState<CalendarDay | null>(null);

  useEffect(() => {
    void api.calendar({ year, month }).then((result) => setDays(result.days));
  }, [year, month]);

  const first = new Date(year, month - 1, 1);
  const startOffset = (first.getDay() + 6) % 7;
  const total = new Date(year, month, 0).getDate();
  const byDate = new Map(days.map((day) => [day.date, day]));
  const cells: (CalendarDay | null)[] = [
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
        title={year + ' 年 ' + month + ' 月'}
        actions={
          <div className="row">
            <span className={'muted'} style={{ marginRight: 8 }}>
              当月合计 <span className={toneOf(monthTotal, scheme)}>{formatMoney(monthTotal)}</span>
            </span>
            <button className="ghost" onClick={() => shift(-1)}>上月</button>
            <button className="ghost" onClick={() => shift(1)}>下月</button>
          </div>
        }
      >
        <div className="calendar">
          {WEEKDAYS.map((weekday) => <div key={weekday} className="weekday">{weekday}</div>)}
        </div>
        <div className="calendar" style={{ marginTop: 4 }}>
          {cells.map((day, index) => {
            if (!day) return <div key={'empty-' + index} className="cell empty" />;
            const active = day.trade_count > 0;
            return (
              <button
                key={day.date}
                className="cell"
                style={{ textAlign: 'left', background: active ? undefined : '#12161d' }}
                onClick={() => setSelected(day)}
              >
                <div className="day">{Number(day.date.slice(-2))}</div>
                {active ? (
                  <>
                    <div className={'pnl ' + toneOf(day.net_pnl, scheme)}>{formatMoney(day.net_pnl, 0)}</div>
                    <div className="muted" style={{ fontSize: 10 }}>{day.trade_count} 笔 · 胜 {day.win_count}</div>
                  </>
                ) : null}
              </button>
            );
          })}
        </div>
      </Panel>

      {selected ? (
        <Panel title={'当日明细 · ' + selected.date}>
          {selected.trades.length === 0 ? <div className="muted">这一天没有已确认的平仓交易。</div> : (
            <table>
              <thead><tr><th>标的</th><th className="num">收益</th><th className="num">净盈亏</th></tr></thead>
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

