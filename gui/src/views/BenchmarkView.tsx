import { useEffect, useState } from 'react';
import { api } from '../api';
import type { BenchmarkLatestResponse } from '../types';
import { Badge, Empty, Kpi, Panel } from '../components/common';
import { useLegacyI18n } from '../locales/legacy';

const IMAGE_CATEGORIES = [
  { key: 'all', labelKey: 'benchmark.allImages' as const },
  { key: 'overview', labelKey: 'benchmark.overview' as const },
  { key: 'domains', labelKey: 'benchmark.domains' as const },
  { key: 'analysis', labelKey: 'benchmark.analysis' as const },
];

const IMAGE_META: Record<string, { labelKey: 'benchmark.heroLabel' | 'benchmark.leaderboardImageLabel' | 'benchmark.compactLabel' | 'benchmark.qualityLabel' | 'benchmark.calibrationLabel' | 'benchmark.tradingLabel' | 'benchmark.filingsLabel' | 'benchmark.eventsLabel' | 'benchmark.macroLabel'; category: string; descKey: 'benchmark.heroDesc' | 'benchmark.leaderboardImageDesc' | 'benchmark.compactDesc' | 'benchmark.qualityDesc' | 'benchmark.calibrationDesc' | 'benchmark.tradingDesc' | 'benchmark.filingsDesc' | 'benchmark.eventsDesc' | 'benchmark.macroDesc' }> = {
  'benchmark-hero-1200x630.png': {
    labelKey: 'benchmark.heroLabel',
    category: 'overview',
    descKey: 'benchmark.heroDesc',
  },
  'benchmark-leaderboard.png': {
    labelKey: 'benchmark.leaderboardImageLabel',
    category: 'overview',
    descKey: 'benchmark.leaderboardImageDesc',
  },
  'benchmark-card-compact.png': {
    labelKey: 'benchmark.compactLabel',
    category: 'overview',
    descKey: 'benchmark.compactDesc',
  },
  'benchmark-quality-cost-latency.png': {
    labelKey: 'benchmark.qualityLabel',
    category: 'analysis',
    descKey: 'benchmark.qualityDesc',
  },
  'benchmark-calibration.png': {
    labelKey: 'benchmark.calibrationLabel',
    category: 'analysis',
    descKey: 'benchmark.calibrationDesc',
  },
  'benchmark-domain-trading-review.png': {
    labelKey: 'benchmark.tradingLabel',
    category: 'domains',
    descKey: 'benchmark.tradingDesc',
  },
  'benchmark-domain-financial-filings.png': {
    labelKey: 'benchmark.filingsLabel',
    category: 'domains',
    descKey: 'benchmark.filingsDesc',
  },
  'benchmark-domain-industry-events.png': {
    labelKey: 'benchmark.eventsLabel',
    category: 'domains',
    descKey: 'benchmark.eventsDesc',
  },
  'benchmark-domain-macro-policy.png': {
    labelKey: 'benchmark.macroLabel',
    category: 'domains',
    descKey: 'benchmark.macroDesc',
  },
};

export function BenchmarkView() {
  const { t, locale } = useLegacyI18n();
  const [data, setData] = useState<BenchmarkLatestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState('all');
  const [selectedTrackBreakdown, setSelectedTrackBreakdown] = useState<string>('trading-review');

  const loadBenchmark = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.benchmarkLatest();
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadBenchmark();
  }, []);

  if (loading && !data) {
    return (
      <div style={{ padding: 24 }}>
        <Empty text={t('benchmark.loading')} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <div className="banner" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', padding: '12px 16px', borderRadius: 'var(--radius)', color: 'var(--text)' }}>
          <div><strong>{t('benchmark.failed')}</strong> {error}</div>
          <button className="ghost" style={{ marginTop: 8 }} onClick={() => void loadBenchmark()}>{t('benchmark.retry')}</button>
        </div>
      </div>
    );
  }

  if (!data || !data.run_id) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className="banner" style={{ background: 'var(--panel)', border: '1px solid var(--border)', padding: '10px 14px', borderRadius: 'var(--radius)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <strong>{t('benchmark.title')}</strong>
            <Badge kind="ok">{data?.safety || 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE'}</Badge>
          </div>
        </div>
        <Panel title={t('benchmark.noRuns')}>
          <Empty text={t('benchmark.noRunsText')} />
        </Panel>
      </div>
    );
  }

  const systems = data.systems || [];
  const completedSystems = systems.filter((s) => s.status === 'completed' && s.metrics);
  const baselineSystem = systems.find((s) => s.system_id === 'deterministic_baseline');

  const imageList = (data.images || []).map((img) => {
    if (typeof img === 'string') {
      return { name: img, url: '/api/benchmark/images/' + data.run_id + '/' + img };
    }
    return img;
  });

  const filteredImages = imageList.filter((img) => {
    if (activeCategory === 'all') return true;
    const meta = IMAGE_META[img.name];
    return meta?.category === activeCategory;
  });

  return (
    <div className="benchmark-view" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Top Banner with Safety Declaration */}
      <div className="banner" style={{ background: 'var(--panel)', border: '1px solid var(--border)', padding: '10px 14px', borderRadius: 'var(--radius)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <strong style={{ fontSize: 13 }}>{t('benchmark.title')}</strong>
            {data.source && (
              <Badge kind={data.source === 'local' ? 'ok' : 'warn'}>
                {data.source === 'local' ? t('benchmark.local') : t('benchmark.bundled')}
              </Badge>
            )}
            <span className="muted" style={{ marginLeft: 4, fontSize: 11 }}>{t('benchmark.summary')}</span>
          </div>
          <Badge kind="ok">{data.safety || 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE'}</Badge>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        <Kpi
          label={t('benchmark.runId')}
          value={<span style={{ fontSize: 12 }}>{data.run_id}</span>}
          note={
            (data.source === 'bundled' ? t('benchmark.sourceBundled') : t('benchmark.sourceLocal')) +
            (data.run_date ? ' · ' + new Date(data.run_date).toLocaleString(locale) : '')
          }
        />
        <Kpi
          label={t('benchmark.cases')}
          value={data.sample_count || 240}
          note={t('benchmark.casesNote')}
        />
        <Kpi
          label={t('benchmark.baseline')}
          value={baselineSystem?.metrics ? (baselineSystem.metrics.accuracy * 100).toFixed(1) + '%' : '—'}
          note={baselineSystem?.metrics?.confidence_interval_95 ? '95% CI: [' + (baselineSystem.metrics.confidence_interval_95[0] * 100).toFixed(1) + '%, ' + (baselineSystem.metrics.confidence_interval_95[1] * 100).toFixed(1) + '%]' : t('benchmark.ruleBaseline')}
        />
        <Kpi
          label={t('benchmark.runHash')}
          value={<code style={{ fontSize: 10 }}>{data.run_hash ? data.run_hash.slice(0, 12) : '—'}</code>}
          note={t('benchmark.gitSha', { sha: data.git_sha ? data.git_sha.slice(0, 8) : '—' })}
        />
      </div>

      {/* Systems Leaderboard Panel */}
      <Panel
        title={t('benchmark.leaderboard')}
        actions={
          <button className="ghost" onClick={() => void loadBenchmark()} disabled={loading}>
            {loading ? t('benchmark.refreshing') : t('benchmark.refresh')}
          </button>
        }
      >
        <div style={{ marginBottom: 12, color: 'var(--muted)', fontSize: 12 }}>
          {t('benchmark.gate')}
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('benchmark.systemId')}</th><th>{t('benchmark.status')}</th><th>{t('benchmark.models')}</th><th>{t('benchmark.accuracy')}</th><th>{t('benchmark.f1')}</th><th>{t('benchmark.recall')}</th><th>{t('benchmark.coverage')}</th><th>{t('benchmark.latency')}</th><th>{t('benchmark.cost')}</th><th>{t('benchmark.mcnemar')}</th>
              </tr>
            </thead>
            <tbody>
              {systems.map((sys) => {
                const isCompleted = sys.status === 'completed' && sys.metrics;
                return (
                  <tr key={sys.system_id}>
                    <td>
                      <strong>{sys.system_id}</strong>
                    </td>
                    <td>
                      {isCompleted ? (
                        <Badge kind="ok">{t('benchmark.completed')}</Badge>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          <Badge kind="warn">{t('benchmark.notRun')}</Badge>
                          {sys.reason ? (
                            <small className="muted" style={{ fontSize: 10 }}>
                              {sys.reason === 'missing_credential' ? t('benchmark.missingCredential') : sys.reason}
                            </small>
                          ) : null}
                        </div>
                      )}
                    </td>
                    <td>
                      <div><code>{sys.model_requested || '—'}</code></div>
                      {sys.model_resolved ? (
                        <small className="muted">{t('benchmark.resolved')} <code>{sys.model_resolved}</code></small>
                      ) : null}
                    </td>
                    <td>
                      {isCompleted && sys.metrics ? (
                        <div>
                          <strong>{(sys.metrics.accuracy * 100).toFixed(2)}%</strong>
                          {sys.metrics.confidence_interval_95 ? (
                            <div className="muted" style={{ fontSize: 10 }}>
                              CI: [{(sys.metrics.confidence_interval_95[0] * 100).toFixed(1)}%, {(sys.metrics.confidence_interval_95[1] * 100).toFixed(1)}%]
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {isCompleted && sys.metrics ? (
                        <span>{(sys.metrics.macro_f1 * 100).toFixed(2)}%</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {isCompleted && sys.metrics ? (
                        <span>{(sys.metrics.recall * 100).toFixed(2)}%</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {isCompleted && sys.metrics ? (
                        <span>{(sys.metrics.coverage * 100).toFixed(1)}%</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {isCompleted && sys.metrics ? (
                        <span>{sys.metrics.p50_latency_ms.toFixed(3)} ms</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {isCompleted && sys.metrics ? (
                        <span>{'$' + sys.metrics.cost_per_case.toFixed(4)}</span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      {isCompleted && sys.metrics?.mcnemar_against_baseline ? (
                        <span style={{ fontSize: 11 }}>
                          {'p=' + sys.metrics.mcnemar_against_baseline.p_value.toFixed(3)}
                        </span>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Domain Breakdown Table for Completed Systems */}
      {completedSystems.length > 0 && (
        <Panel title={t('benchmark.trackMetrics')}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            {['trading-review', 'financial-filings', 'industry-events', 'macro-policy'].map((t) => (
              <button
                key={t}
                className={selectedTrackBreakdown === t ? 'primary' : 'ghost'}
                onClick={() => setSelectedTrackBreakdown(t)}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('benchmark.system')}</th><th>{t('benchmark.trackAccuracy')}</th><th>{t('benchmark.f1')}</th><th>{t('benchmark.recall')}</th><th>{t('benchmark.falsePositive')}</th>
                  <th>Brier Score</th>
                  <th>{t('benchmark.calibration')}</th><th>{t('benchmark.ci')}</th>
                </tr>
              </thead>
              <tbody>
                {completedSystems.map((sys) => {
                  const tm = sys.track_metrics?.[selectedTrackBreakdown];
                  if (!tm) return null;
                  return (
                    <tr key={sys.system_id}>
                      <td><strong>{sys.system_id}</strong></td>
                      <td><strong>{(tm.accuracy * 100).toFixed(2)}%</strong></td>
                      <td>{(tm.macro_f1 * 100).toFixed(2)}%</td>
                      <td>{(tm.recall * 100).toFixed(2)}%</td>
                      <td>{(tm.fpr * 100).toFixed(2)}%</td>
                      <td>{tm.brier.toFixed(4)}</td>
                      <td>{tm.ece.toFixed(4)}</td>
                      <td>
                        {tm.confidence_interval_95 ? (
                          <span>{'[' + (tm.confidence_interval_95[0] * 100).toFixed(1) + '%, ' + (tm.confidence_interval_95[1] * 100).toFixed(1) + '%]'}</span>
                        ) : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {/* Inline Score Images Section */}
      <Panel title={t('benchmark.artifacts')}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
          {IMAGE_CATEGORIES.map((cat) => (
            <button
              key={cat.key}
              className={activeCategory === cat.key ? 'primary' : 'ghost'}
              onClick={() => setActiveCategory(cat.key)}
            >
              {t(cat.labelKey)}
            </button>
          ))}
        </div>

        {filteredImages.length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 16 }}>
            {filteredImages.map((img) => {
              const meta = IMAGE_META[img.name] || {
                labelKey: null,
                descKey: null,
              };
              const label = meta.labelKey ? t(meta.labelKey) : img.name;
              const description = meta.descKey ? t(meta.descKey) : t('benchmark.defaultImageDesc');
              return (
                <div
                  key={img.name}
                  style={{
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)',
                    background: 'var(--bg)',
                    padding: 12,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <strong style={{ fontSize: 13 }}>{label}</strong>
                    <code style={{ fontSize: 11, color: 'var(--muted)' }}>{img.name}</code>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>{description}</div>
                  <div style={{ width: '100%', overflow: 'hidden', borderRadius: 'var(--radius)', border: '1px solid var(--border)', background: '#fff' }}>
                    <img
                      src={img.url}
                      alt={label}
                      loading="lazy"
                      style={{ width: '100%', height: 'auto', display: 'block', objectFit: 'contain' }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <Empty text={t('benchmark.emptyImages')} />
        )}
      </Panel>
    </div>
  );
}
