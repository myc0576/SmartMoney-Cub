import { useCallback, useEffect, useMemo, useState } from 'react';
import { trader } from '../api';
import type { CandleMarker } from '../components/CandleChart';
import { CandleChart } from '../components/CandleChart';
import type { MarketBar, MarketProvider, ReplayMarker, ReplaySession } from '../types';
import { Banner, Empty, Panel, formatPct, toneOf } from '../components/common';

/**
 * Candle replay: step through a historical series, with trade markers attached.
 *
 * The cursor is client-side and monotonic. Advancing reveals bars; it never
 * edits the series or refetches it, so a replay cannot see a future bar it has
 * not stepped to, and stepping back and forth is free.
 *
 * Auto-play is opt-in and stops at the end of the series rather than looping:
 * a replay that silently restarted would invite reading the same bar as a new
 * one. The control is a plain interval, cleared on unmount and on any manual
 * step, and it respects the reduced-motion preference by not autostarting.
 */

const SPEEDS = [
  { label: '0.5×', ms: 800 },
  { label: '1×', ms: 400 },
  { label: '2×', ms: 200 },
];

export function ReplayView({ scheme }: { scheme: 'cn' | 'intl' }) {
  const [providers, setProviders] = useState<MarketProvider[]>([]);
  const [provider, setProvider] = useState('');
  const [symbol, setSymbol] = useState('600519');
  const [interval, setInterval] = useState('1d');
  const [session, setSession] = useState<ReplaySession | null>(null);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void trader.marketProviders()
      .then((catalog) => {
        const list = Array.isArray(catalog.providers) ? catalog.providers : [];
        setProviders(list);
        setProvider((current) => current || list[0]?.provider_id || '');
      })
      .catch(() => setProviders([]));
  }, []);

  const bars: MarketBar[] = useMemo(
    () => (Array.isArray(session?.bars) ? session.bars : []),
    [session],
  );

  const start = useCallback(async () => {
    setBusy(true);
    setError('');
    setPlaying(false);
    try {
      const created = await trader.createReplaySession({
        provider,
        symbol: symbol.trim(),
        interval,
      });
      setSession(created);
      const total = Array.isArray(created.bars) ? created.bars.length : 0;
      // Open partway in, so the first paint already has a series to read; a
      // replay that starts with one bar on screen is not a replay.
      setCursor(Math.min(Math.max(1, Math.floor(total / 3)), Math.max(1, total - 1)));
    } catch (failure) {
      setSession(null);
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }, [provider, symbol, interval]);

  useEffect(() => {
    if (!playing || bars.length === 0) return;
    const step = SPEEDS[Math.min(speed, SPEEDS.length - 1)].ms;
    const timer = window.setInterval(() => {
      setCursor((current) => {
        if (current >= bars.length) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, step);
    return () => window.clearInterval(timer);
  }, [playing, bars.length, speed]);

  const visible = bars.slice(0, Math.max(1, Math.min(cursor, bars.length)));
  const currentBar = bars.length ? bars[Math.min(Math.max(0, cursor - 1), bars.length - 1)] : null;
  const first = visible[0]?.close ?? 0;
  const last = currentBar?.close ?? 0;
  const changePct = first ? ((last - first) / first) * 100 : 0;
  const markers = markersOf(session?.markers, visible);

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice">
        回放只向前推进游标，不修改序列，也不会重新抓取。你看到的每一根 K 线都是当时就已经存在的历史数据。
        自动播放到达末尾会停下，不会循环——循环会让人把同一根 K 线当成新的行情。
      </div>

      {error ? <Banner>回放会话创建失败：{error}</Banner> : null}

      <Panel
        title="回放设置"
        actions={
          <div className="row">
            <button className="ghost" onClick={() => setCursor((current) => Math.max(1, current - 1))} disabled={!bars.length}>上一步</button>
            <button className="ghost" onClick={() => setCursor((current) => Math.min(bars.length, current + 1))} disabled={!bars.length || cursor >= bars.length}>下一步</button>
            <button className="ghost" onClick={() => setPlaying((previous) => !previous)} disabled={!bars.length || cursor >= bars.length}>
              {playing ? '暂停' : '播放'}
            </button>
            <select value={speed} onChange={(event) => setSpeed(Number(event.target.value))} aria-label="播放速度">
              {SPEEDS.map((item, index) => <option key={item.label} value={index}>{item.label}</option>)}
            </select>
          </div>
        }
      >
        <div className="row">
          <div className="field">
            <label>行情来源</label>
            <select value={provider} onChange={(event) => setProvider(event.target.value)}>
              {providers.length === 0 ? <option value="">没有可用来源</option> : null}
              {providers.map((item) => (
                <option key={item.provider_id} value={item.provider_id}>{item.label}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>标的</label>
            <input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
          </div>
          <div className="field">
            <label>周期</label>
            <select value={interval} onChange={(event) => setInterval(event.target.value)}>
              {['1m', '5m', '15m', '30m', '60m', '1d', '1w', '1M'].map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ justifyContent: 'flex-end' }}>
            <button className="primary" onClick={() => void start()} disabled={busy || !provider || !symbol.trim()}>
              {busy ? '抓取中…' : '开始回放'}
            </button>
          </div>
        </div>
      </Panel>

      {!session ? (
        <Panel title="回放">
          <Empty text="还没有回放会话。选择来源、标的与周期后点「开始回放」。" />
        </Panel>
      ) : bars.length === 0 ? (
        <Panel title="回放">
          <Empty text="这个会话没有返回任何 K 线" />
        </Panel>
      ) : (
        <>
          <Panel
            title={session.symbol + ' · ' + session.interval}
            actions={
              <span className="muted" style={{ fontSize: 11 }}>
                {cursor} / {bars.length} 根 · 来源 {session.provider} · 游标时间 {currentBar?.open_time || '—'}
              </span>
            }
          >
            <CandleChart bars={visible} markers={markers} height={320} />
            <input
              type="range"
              min={1}
              max={Math.max(1, bars.length)}
              value={cursor}
              onChange={(event) => { setPlaying(false); setCursor(Number(event.target.value)); }}
              style={{ width: '100%', marginTop: 12 }}
              aria-label="回放游标"
            />
            <div className="row" style={{ justifyContent: 'space-between', marginTop: 4 }}>
              <span className="muted" style={{ fontSize: 11 }}>{visible[0]?.open_time || ''}</span>
              <span className="muted" style={{ fontSize: 11 }}>{currentBar?.open_time || ''}</span>
            </div>
          </Panel>

          <div className="grid split">
            <Panel title="当前位置">
              <table>
                <tbody>
                  <tr><td>开盘</td><td className="num">{currentBar ? currentBar.open : '—'}</td></tr>
                  <tr><td>最高</td><td className="num">{currentBar ? currentBar.high : '—'}</td></tr>
                  <tr><td>最低</td><td className="num">{currentBar ? currentBar.low : '—'}</td></tr>
                  <tr><td>收盘</td><td className="num">{currentBar ? currentBar.close : '—'}</td></tr>
                  <tr>
                    <td>区间涨跌</td>
                    <td className={'num ' + toneOf(changePct, scheme)}>{formatPct(changePct)}</td>
                  </tr>
                </tbody>
              </table>
            </Panel>
            <Panel title={'交易标记（' + markers.length + '）'}>
              {markers.length === 0 ? (
                <Empty text="这个区间还没有进场/离场标记" />
              ) : (
                <table>
                  <thead><tr><th>类型</th><th>时间</th><th className="num">价格</th><th>说明</th></tr></thead>
                  <tbody>
                    {markers.map((marker, index) => (
                      <tr key={(marker.time || '') + '-' + index}>
                        <td>{marker.kind === 'exit' ? '离场' : '进场'}</td>
                        <td className="muted">{marker.time}</td>
                        <td className="num">{marker.price}</td>
                        <td className="muted">{marker.label || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                标记来自已记录的成交时间与价格；没有成交时这一栏会是空的。
              </div>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}

/** Only markers on or before the cursor are revealed: a replay must not show a
 *  future exit before its bar has been stepped to. */
function markersOf(markers: ReplayMarker[] | undefined, visible: MarketBar[]): CandleMarker[] {
  if (!Array.isArray(markers) || visible.length === 0) return [];
  const window = new Set(visible.map((bar) => bar.open_time));
  return markers
    .filter((marker) => window.has(marker.time))
    .map((marker) => ({
      time: marker.time,
      price: Number(marker.price),
      kind: marker.kind,
      label: marker.label,
    }))
    .filter((marker) => Number.isFinite(marker.price));
}
