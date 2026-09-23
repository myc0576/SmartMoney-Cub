import { useCallback, useEffect, useMemo, useState } from 'react';
import { trader } from '../api';
import type { CandleMarker } from '../components/CandleChart';
import { CandleChart } from '../components/CandleChart';
import type { MarketBar, MarketProvider, ReplayMarker, ReplaySession } from '../types';
import { Banner, Empty, Panel, formatPct, toneOf } from '../components/common';
import { useI18n } from '../i18n';
import { useReplayCopy } from '../locales/replay';

/**
 * Candle replay: step through a historical series, with trade markers attached.
 *
 * The cursor is persisted by the replay service. Advancing reveals bars; it
 * never edits the series or refetches it, so a replay cannot see a future bar it
 * has not stepped to, and the same session resumes safely after a reload.
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
  const { t } = useI18n();
  const c = useReplayCopy();
  const [providers, setProviders] = useState<MarketProvider[]>([]);
  const [provider, setProvider] = useState('');
  const [symbol, setSymbol] = useState('');
  const [interval, setInterval] = useState('1d');
  const [mode, setMode] = useState<'review' | 'training'>('review');
  const [session, setSession] = useState<ReplaySession | null>(null);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [catalogError, setCatalogError] = useState('');
  const [historyError, setHistoryError] = useState('');
  const [history, setHistory] = useState<ReplaySession[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [quantity, setQuantity] = useState('1');

  useEffect(() => {
    let cancelled = false;
    void trader.marketProviders()
      .then((catalog) => {
        if (cancelled) return;
        const list = Array.isArray(catalog.providers) ? catalog.providers : [];
        setProviders(list);
        setCatalogError('');
        setProvider((current) => current || list.find(item => !item.availability || item.availability === 'available')?.provider_id || '');
      })
      .catch((failure) => { if (!cancelled) { setProviders([]); setProvider(''); setCatalogError(String(failure.message || failure)); } });
    setHistoryLoading(true);
    void trader.replaySessions().then(result => {
      if (!cancelled) { setHistory(result.sessions); setHistoryError(''); }
    }).catch(failure => { if (!cancelled) setHistoryError(String(failure.message || failure)); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [revision]);

  async function resume(id: string) {
    if (busy) return;
    setPlaying(false); setBusy(true); setError('');
    try {
      const saved = await trader.replaySession(id);
      setSession(saved); setCursor(saved.cursor); setSymbol(saved.symbol);
      setInterval(saved.interval); setMode(saved.mode);
    } catch (failure) { setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { setBusy(false); }
  }

  const bars: MarketBar[] = useMemo(
    () => (Array.isArray(session?.bars) ? session.bars : []),
    [session],
  );
  const barCount = session?.bar_count || bars.length;

  const start = useCallback(async () => {
    setBusy(true);
    setError('');
    setPlaying(false);
    try {
      const created = await trader.createReplaySession({
        provider,
        symbol: symbol.trim(),
        interval,
        mode,
      });
      setSession(created);
      setCursor(created.cursor);
      setRevision(value => value + 1);
    } catch (failure) {
      setSession(null);
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }, [mode, provider, symbol, interval]);

  const act = useCallback(async (action: 'step' | 'seek' | 'rewind' | 'simulate', index?: number, extra: Record<string, unknown> = {}) => {
    if (!session || busy) return;
    setBusy(true);
    setError('');
    try {
      const updated = await trader.replayAction(session.session_id, {
        action,
        ...(index === undefined ? {} : { index }),
        ...extra,
      });
      setSession(updated);
      setCursor(updated.cursor);
      if (updated.session_id !== session.session_id) setRevision(value => value + 1);
    } catch (failure) {
      setPlaying(false);
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  }, [busy, session]);

  useEffect(() => {
    if (!playing || !session || bars.length === 0 || cursor >= barCount - 1) return;
    const step = SPEEDS[Math.min(speed, SPEEDS.length - 1)].ms;
    const timer = window.setInterval(() => {
      void act('step');
    }, step);
    return () => window.clearInterval(timer);
  }, [act, barCount, bars.length, cursor, playing, session, speed]);

  const visible = bars;
  const currentBar = bars.length ? bars[bars.length - 1] : null;
  const first = visible[0]?.close ?? 0;
  const last = currentBar?.close ?? 0;
  const changePct = first ? ((last - first) / first) * 100 : 0;
  const markers = markersOf(session?.markers, visible);

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice">
        {c('notice')}
      </div>

      {error ? <Banner>{c('failed')}: {error}</Banner> : null}
      {catalogError ? <Banner>{t('error.read')}: {catalogError} <button onClick={() => setRevision(value => value + 1)}>{t('state.retry')}</button></Banner> : null}
      <Panel title={t('replay.history')}>
        {historyLoading ? <p>{t('state.loading')}</p> : historyError ? <Banner>{c('historyError')}: {historyError} <button onClick={() => setRevision(value => value + 1)}>{t('state.retry')}</button></Banner> : history.length ? (
          <div className="row">{history.map(item => <button className="ghost" key={item.session_id} disabled={busy} onClick={() => void resume(item.session_id)}>{c('resume')} · {item.symbol} · {item.interval} · {item.cursor + 1}/{item.bar_count} · {item.mode === 'training' ? t('replay.training') : t('replay.review')}</button>)}</div>
        ) : <Empty text={c('noHistory')} />}
      </Panel>

      <Panel
        title={c('settings')}
        actions={
          <div className="row">
            <button className="ghost" onClick={() => { setPlaying(false); void act('rewind', Math.max(0, cursor - 1)); }} disabled={!bars.length || cursor <= 0 || busy}>{t('replay.back')}</button>
            <button className="ghost" onClick={() => { setPlaying(false); void act('step'); }} disabled={!bars.length || cursor >= barCount - 1 || busy}>{t('replay.step')}</button>
            <button className="ghost" onClick={() => setPlaying((previous) => !previous)} disabled={!bars.length || cursor >= barCount - 1 || busy}>
              {playing ? t('replay.pause') : t('replay.play')}
            </button>
            <select value={speed} onChange={(event) => setSpeed(Number(event.target.value))} aria-label={c('speed')}>
              {SPEEDS.map((item, index) => <option key={item.label} value={index}>{item.label}</option>)}
            </select>
          </div>
        }
      >
        <div className="row">
          <div className="field">
            <label htmlFor="replay-purpose">{c('purpose')}</label>
            <select id="replay-purpose" value={mode} disabled={busy} onChange={(event) => setMode(event.target.value as 'review' | 'training')}>
              <option value="review">{t('replay.review')}</option>
              <option value="training">{t('replay.training')}</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="replay-source">{c('source')}</label>
            <select id="replay-source" value={provider} disabled={busy || !providers.length} onChange={(event) => setProvider(event.target.value)}>
              {!provider ? <option value="">{c('noSources')}</option> : null}
              {providers.map((item) => (
                /* Replay shares the picker with backtest, so it shares the rule:
                   an unreachable source keeps its place and states the reason. */
                <option
                  key={item.provider_id}
                  value={item.provider_id}
                  disabled={Boolean(item.availability) && item.availability !== 'available'}
                >
                  {item.label}
                  {item.availability && item.availability !== 'available'
                    ? ' · ' + t('state.unavailable') + ': ' + (item.availability_reason || item.availability)
                    : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="replay-symbol">{c('symbol')}</label>
            <input id="replay-symbol" value={symbol} disabled={busy} onChange={(event) => setSymbol(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="replay-interval">{c('interval')}</label>
            <select id="replay-interval" value={interval} disabled={busy} onChange={(event) => setInterval(event.target.value)}>
              {['1m', '5m', '15m', '30m', '60m', '1d', '1w', '1M'].map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ justifyContent: 'flex-end' }}>
            <button className="primary" onClick={() => void start()} disabled={busy || !provider || !symbol.trim()}>
              {busy ? t('state.loading') : t('replay.start')}
            </button>
          </div>
        </div>
      </Panel>

      {!session ? (
        <Panel title={c('replay')}>
          <Empty text={c('empty')} />
        </Panel>
      ) : bars.length === 0 ? (
        <Panel title={c('replay')}>
          <Empty text={c('noBars')} />
        </Panel>
      ) : (
        <>
          {session.historical_evidence !== 'verified' ? <div className="notice">{c('unverified')}</div> : null}
          <Panel
            title={session.symbol + ' · ' + session.interval}
            actions={
              <span className="muted" style={{ fontSize: 11 }}>
                {cursor + 1} / {barCount} · {c('source')} {session.provider || provider} · {c('time')} {currentBar?.open_time || '—'}
              </span>
            }
          >
            <CandleChart bars={visible} markers={markers} scheme={scheme} height={320} />
            <input
              type="range"
              min={0}
              max={Math.max(0, barCount - 1)}
              value={cursor}
              disabled={busy}
              onChange={(event) => { setPlaying(false); void act('seek', Number(event.target.value)); }}
              style={{ width: '100%', marginTop: 12 }}
              aria-label={c('cursor')}
            />
            <div className="row" style={{ justifyContent: 'space-between', marginTop: 4 }}>
              <span className="muted" style={{ fontSize: 11 }}>{visible[0]?.open_time || ''}</span>
              <span className="muted" style={{ fontSize: 11 }}>{currentBar?.open_time || ''}</span>
            </div>
          </Panel>

          <div className="grid split">
            <Panel title={c('current')}>
              <table>
                <tbody>
                  <tr><td>{c('open')}</td><td className="num">{currentBar ? currentBar.open : '—'}</td></tr>
                  <tr><td>{c('high')}</td><td className="num">{currentBar ? currentBar.high : '—'}</td></tr>
                  <tr><td>{c('low')}</td><td className="num">{currentBar ? currentBar.low : '—'}</td></tr>
                  <tr><td>{c('close')}</td><td className="num">{currentBar ? currentBar.close : '—'}</td></tr>
                  <tr>
                    <td>{c('change')}</td>
                    <td className={'num ' + toneOf(changePct, scheme)}>{formatPct(changePct)}</td>
                  </tr>
                </tbody>
              </table>
            </Panel>
            <Panel title={c('markers') + ' (' + markers.length + ')'}>
              {markers.length === 0 ? (
                <Empty text={c('noMarkers')} />
              ) : (
                <table>
                  <thead><tr><th>{c('type')}</th><th>{c('time')}</th><th className="num">{c('price')}</th><th>{c('description')}</th></tr></thead>
                  <tbody>
                    {markers.map((marker, index) => (
                      <tr key={(marker.time || '') + '-' + index}>
                        <td>{marker.kind === 'exit' ? c('exit') : c('entry')}</td>
                        <td className="muted">{marker.time}</td>
                        <td className="num">{marker.price}</td>
                        <td className="muted">{marker.label || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                {c('markerNote')}
              </div>
            </Panel>
          </div>
          {session.mode === 'training' ? (
            <Panel title={t('replay.training')}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="muted" style={{ fontSize: 11 }}>{t('replay.simulated')}</span>
                <div className="row">
                  <label htmlFor="replay-quantity">{c('quantity')}</label>
                  <input id="replay-quantity" type="number" min="0" step="any" value={quantity} disabled={busy} onChange={event => setQuantity(event.target.value)} />
                  <button className="ghost" disabled={busy || !Number.isFinite(Number(quantity)) || Number(quantity) <= 0 || cursor >= barCount - 1} onClick={() => { setPlaying(false); void act('simulate', undefined, { side: 'BUY', quantity }); }}>{c('buy')}</button>
                  <button className="ghost" disabled={busy || !Number.isFinite(Number(quantity)) || Number(quantity) <= 0 || cursor >= barCount - 1} onClick={() => { setPlaying(false); void act('simulate', undefined, { side: 'SELL', quantity }); }}>{c('sell')}</button>
                </div>
              </div>
              {session.training?.orders?.filter(order => order.status === 'pending').length ? <p role="status">{c('pending')} · {session.training.orders.filter(order => order.status === 'pending').length}</p> : null}
              {session.training?.fills?.length ? <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>{c('fills')}: {session.training.fills.length}</div> : null}
            </Panel>
          ) : null}
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
