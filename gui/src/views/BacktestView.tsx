import { useCallback, useEffect, useState } from 'react';
import { trader } from '../api';
import type { BacktestRunDetail, BacktestRunSummary, MarketProvider } from '../types';
import { CandleChart } from '../components/CandleChart';
import { Banner, Empty, Panel, formatMoney, formatPct, toneOf } from '../components/common';

/**
 * Backtesting: a JSON strategy in, a deterministic run out.
 *
 * The strategy is edited as raw JSON rather than through a form. That is
 * deliberate: the DSL is a frozen vocabulary that rejects unknown keys, and a
 * form would either silently drop a key the trader typed or invent a shape the
 * validator does not accept. Raw JSON keeps the editor and the validator honest
 * — what you see is exactly what will be validated.
 *
 * The default strategy is a minimal valid payload, so the view runs something
 * on first open instead of showing an empty editor and an error.
 */

const EXAMPLE_STRATEGY = {
  version: 1,
  name: '均线交叉示例',
  universe: { symbol: '600519', interval: '1d' },
  indicators: [
    { id: 'fast', kind: 'sma', source: 'close', period: 10 },
    { id: 'slow', kind: 'sma', source: 'close', period: 30 },
  ],
  entry: { all: [{ crosses_above: ['fast', 'slow'] }] },
  exit: { all: [{ crosses_below: ['fast', 'slow'] }] },
  stop: { kind: 'percent', value: 5 },
  target: { kind: 'r_multiple', value: 2 },
  sizing: { kind: 'fixed_fraction', value: 0.25 },
  filters: { session: null, min_bars: 30 },
  fill: 'next_open',
};

export function BacktestView({ scheme }: { scheme: 'cn' | 'intl' }) {
  const [providers, setProviders] = useState<MarketProvider[]>([]);
  const [provider, setProvider] = useState('');
  const [symbol, setSymbol] = useState('600519');
  const [interval, setInterval] = useState('1d');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [strategy, setStrategy] = useState(() => JSON.stringify(EXAMPLE_STRATEGY, null, 2));
  const [runs, setRuns] = useState<BacktestRunSummary[]>([]);
  const [result, setResult] = useState<BacktestRunDetail | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  const loadRuns = useCallback(async () => {
    try {
      const listed = await trader.backtestRuns();
      setRuns(Array.isArray(listed.runs) ? listed.runs : []);
    } catch {
      // A failed history read should not block running a new backtest.
      setRuns([]);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
    void trader.marketProviders()
      .then((catalog) => {
        const list = Array.isArray(catalog.providers) ? catalog.providers : [];
        setProviders(list);
        setProvider((current) => current || list[0]?.provider_id || '');
      })
      .catch(() => setProviders([]));
  }, [loadRuns]);

  const run = async () => {
    setError('');
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(strategy) as Record<string, unknown>;
    } catch (parseFailure) {
      setError('策略 JSON 无法解析：' + (parseFailure instanceof Error ? parseFailure.message : String(parseFailure)));
      return;
    }
    setRunning(true);
    try {
      const detail = await trader.runBacktest({
        strategy: parsed,
        provider: provider || undefined,
        symbol: symbol.trim() || undefined,
        interval: interval || undefined,
        start: start || undefined,
        end: end || undefined,
      });
      setResult(detail);
      await loadRuns();
    } catch (failure) {
      setResult(null);
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setRunning(false);
    }
  };

  const openRun = async (runId: string) => {
    setError('');
    try {
      setResult(await trader.backtestRun(runId));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  };

  // An equity curve has one value per point. It is drawn in line mode rather
  // than as candles: an open/high/low copied from the same number would draw a
  // body with no range, which looks like data and is not.
  const equity = (result?.equity_curve || []).map((point) => ({
    open_time: String(point.open_time || ''),
    close: number(point.equity),
  }));

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice">
        回测只读取历史行情，不接触任何交易通道。相同输入会产生完全相同的输出，
        指标口径与交易日志共用同一套实现，因此回测和复盘不会对同一指标给出两个答案。
      </div>

      {error ? <Banner>{error}</Banner> : null}

      <div className="grid split">
        <Panel
          title="策略（JSON）"
          actions={
            <div className="row">
              <button className="ghost" onClick={() => setStrategy(JSON.stringify(EXAMPLE_STRATEGY, null, 2))}>恢复示例</button>
              <button className="primary" onClick={() => void run()} disabled={running}>{running ? '运行中…' : '运行回测'}</button>
            </div>
          }
        >
          <textarea
            value={strategy}
            onChange={(event) => setStrategy(event.target.value)}
            spellCheck={false}
            style={{ width: '100%', minHeight: 320, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12, lineHeight: 1.6 }}
            aria-label="策略 JSON"
          />
          <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
            DSL 只接受白名单里的键：未知字段会被拒绝，而不是被忽略。
          </div>
        </Panel>

        <Panel title="数据来源">
          <div className="grid" style={{ gap: 10 }}>
            <div className="field">
              <label>行情来源</label>
              <select value={provider} onChange={(event) => setProvider(event.target.value)}>
                {providers.length === 0 ? <option value="">没有可用来源</option> : null}
                {providers.map((item) => (
                  <option key={item.provider_id} value={item.provider_id}>
                    {item.label}（{item.source_quality}）
                  </option>
                ))}
              </select>
            </div>
            <div className="grid split" style={{ gap: 10 }}>
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
            </div>
            <div className="grid split" style={{ gap: 10 }}>
              <div className="field">
                <label>开始日期</label>
                <input type="date" value={start} onChange={(event) => setStart(event.target.value)} />
              </div>
              <div className="field">
                <label>结束日期</label>
                <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
              </div>
            </div>
            <div className="muted" style={{ fontSize: 11, lineHeight: 1.7 }}>
              行情只在点击运行时按需拉取。抓取会记录来源、抓取时间和质量标记；
              任何 <code>available_at</code> 晚于决策时间的序列都会被拒绝。
            </div>
          </div>
        </Panel>
      </div>

      {result ? (
        <div className="grid" style={{ gap: 14 }}>
          <div className="grid kpi">
            <Metric label="期末权益" value={formatMoney(number(result.final_equity))} tone={toneOf(number(result.final_equity) - number(result.initial_cash), scheme)} />
            <Metric label="初始资金" value={formatMoney(number(result.initial_cash))} />
            <Metric label="成交笔数" value={String(metricValue(result.metrics, 'trade_count') ?? result.trades.length)} />
            <Metric label="胜率" value={pctMetric(result.metrics, 'win_rate')} />
            <Metric label="盈亏比" value={metricText(result.metrics, 'profit_factor')} />
            <Metric label="最大回撤" value={metricText(result.metrics, 'max_drawdown')} />
          </div>

          <Panel title={'权益曲线 · ' + (result.strategy_name || result.run_id)}>
            {equity.length < 2 ? <Empty text="这次运行没有产生可绘制的权益点" /> : (
              <CandleChart bars={equity} variant="line" height={220} emptyText="这次运行没有产生可绘制的权益点" />
            )}
          </Panel>

          <Panel title={'成交明细（' + (result.trades || []).length + '）'}>
            {(result.trades || []).length === 0 ? <Empty text="这次运行没有触发任何成交" /> : (
              <div className="scroll-x">
                <table>
                  <thead>
                    <tr>
                      <th>标的</th><th>方向</th><th>进场</th><th>离场</th>
                      <th className="num">数量</th><th className="num">盈亏</th><th>离场原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.trades.map((trade, index) => (
                      <tr key={(trade.entry_time || '') + '-' + index}>
                        <td>{trade.symbol}</td>
                        <td className="muted">{trade.side}</td>
                        <td className="muted">{trade.entry_time}</td>
                        <td className="muted">{trade.exit_time}</td>
                        <td className="num">{number(trade.quantity).toLocaleString('zh-CN')}</td>
                        <td className={'num ' + toneOf(number(trade.pnl), scheme)}>{formatMoney(number(trade.pnl))}</td>
                        <td className="muted">{trade.exit_reason || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </div>
      ) : (
        <Panel title="结果">
          <Empty text="还没有运行结果。设置好策略和数据来源后点「运行回测」。" />
        </Panel>
      )}

      <Panel title={'历史运行（' + runs.length + '）'}>
        {runs.length === 0 ? <Empty text="还没有保存过的回测运行" /> : (
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>策略</th><th>标的</th><th>周期</th><th className="num">交易数</th>
                  <th className="num">净盈亏</th><th>运行时间</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((runSummary) => (
                  <tr key={runSummary.run_id} onClick={() => void openRun(runSummary.run_id)}>
                    <td>{runSummary.strategy_name || runSummary.run_id}</td>
                    <td className="muted">{runSummary.symbol || '—'}</td>
                    <td className="muted">{runSummary.interval || '—'}</td>
                    <td className="num">{metricValue(runSummary.metrics, 'trade_count') ?? '—'}</td>
                    <td className="num">{metricText(runSummary.metrics, 'total_net_pnl')}</td>
                    <td className="muted">{runSummary.started_at || runSummary.created_at}</td>
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

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="panel">
      <div className="kpi-label">{label}</div>
      <div className={'kpi-value ' + (tone || '')}>{value}</div>
    </div>
  );
}

function metricValue(metrics: Record<string, number | string | null> | undefined, key: string): number | null {
  const raw = metrics ? metrics[key] : null;
  if (raw === null || raw === undefined || raw === '') return null;
  const parsed = typeof raw === 'number' ? raw : Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

function metricText(metrics: Record<string, number | string | null> | undefined, key: string): string {
  const value = metricValue(metrics, key);
  if (value === null) return '—';
  if (key.includes('pct') || key === 'win_rate') return formatPct(value);
  return formatMoney(value);
}

function pctMetric(metrics: Record<string, number | string | null> | undefined, key: string): string {
  const value = metricValue(metrics, key);
  return value === null ? '—' : value.toFixed(2) + '%';
}

function number(value: unknown): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}
