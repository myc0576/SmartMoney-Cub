import { useEffect, useState } from 'react';
import { api } from '../api';
import type { BenchmarkLatestResponse } from '../types';
import { Badge, Empty, Kpi, Panel } from '../components/common';

const IMAGE_CATEGORIES = [
  { key: 'all', label: '全部评分图 (All)' },
  { key: 'overview', label: '全景与排行 (Overview & Leaderboard)' },
  { key: 'domains', label: '分赛道雷达 (Domain Tracks)' },
  { key: 'analysis', label: '校准与质量象限 (Calibration & Latency)' },
];

const IMAGE_META: Record<string, { label: string; category: string; desc: string }> = {
  'benchmark-hero-1200x630.png': {
    label: '全景展示卡 (Hero 1200x630)',
    category: 'overview',
    desc: '包含核心准确率、宏平均 F1、覆盖率及四赛道样本概览',
  },
  'benchmark-leaderboard.png': {
    label: '模型综合排行榜 (Leaderboard)',
    category: 'overview',
    desc: '基准规则 vs 各推理系统对比、置信区间及 McNemar 显著性',
  },
  'benchmark-card-compact.png': {
    label: '紧凑型评测卡 (Compact Card)',
    category: 'overview',
    desc: '适合社区分享的紧凑版得分指标速览',
  },
  'benchmark-quality-cost-latency.png': {
    label: '质量 · 成本 · 延迟象限图 (Quality vs Cost vs Latency)',
    category: 'analysis',
    desc: '多模型推理耗时与成本效益分布',
  },
  'benchmark-calibration.png': {
    label: '可靠性校准曲线 (Reliability Calibration)',
    category: 'analysis',
    desc: '预测置信度与真实命中率的校准拟合表现 (ECE / Brier)',
  },
  'benchmark-domain-trading-review.png': {
    label: '赛道细分：交易复盘 (Trading Review)',
    category: 'domains',
    desc: '交易逻辑合规性、时效性与反向证据判定',
  },
  'benchmark-domain-financial-filings.png': {
    label: '赛道细分：财务财报 (Financial Filings)',
    category: 'domains',
    desc: '财报指标披露口径与财务数据矛盾校验',
  },
  'benchmark-domain-industry-events.png': {
    label: '赛道细分：行业事件 (Industry Events)',
    category: 'domains',
    desc: '行业突发事件对产业链及供应链的传导影响',
  },
  'benchmark-domain-macro-policy.png': {
    label: '赛道细分：宏观政策 (Macro Policy)',
    category: 'domains',
    desc: '宏观货币与财政政策转向的预期与定性评估',
  },
};

export function BenchmarkView() {
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
        <Empty text="加载 Benchmark 评测数据中..." />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <div className="banner" style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', padding: '12px 16px', borderRadius: 'var(--radius)', color: 'var(--text)' }}>
          <div><strong>加载失败:</strong> {error}</div>
          <button className="ghost" style={{ marginTop: 8 }} onClick={() => void loadBenchmark()}>重试</button>
        </div>
      </div>
    );
  }

  if (!data || !data.run_id) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div className="banner" style={{ background: 'var(--panel)', border: '1px solid var(--border)', padding: '10px 14px', borderRadius: 'var(--radius)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <strong>Finance-Jev-v1 基准评测</strong>
            <Badge kind="ok">{data?.safety || 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE'}</Badge>
          </div>
        </div>
        <Panel title="暂无评测记录">
          <Empty text="尚未找到 Benchmark 运行记录。可通过命令行运行 'smcub benchmark run' 生成评测数据与评分图片。" />
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
            <strong style={{ fontSize: 13 }}>Finance-Jev-v1 评测基准与排行榜</strong>
            {data.source && (
              <Badge kind={data.source === 'local' ? 'ok' : 'warn'}>
                {data.source === 'local' ? '本地生成运行 (Local)' : '预置发布运行 (Bundled)'}
              </Badge>
            )}
            <span className="muted" style={{ marginLeft: 4, fontSize: 11 }}>240 例离线玩具案例 · 4 大赛道 · 确定性指标与评分可视化</span>
          </div>
          <Badge kind="ok">{data.safety || 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE'}</Badge>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        <Kpi
          label="评测运行 ID (Run ID)"
          value={<span style={{ fontSize: 12 }}>{data.run_id}</span>}
          note={
            (data.source === 'bundled' ? '来源: 仓库预置发布产物' : '来源: 本地评测运行') +
            (data.run_date ? ' · ' + new Date(data.run_date).toLocaleString('zh-CN') : '')
          }
        />
        <Kpi
          label="案例总数 (Cases)"
          value={data.sample_count || 240}
          note="4 赛道 x 60 例 (30 dev + 30 holdout)"
        />
        <Kpi
          label="基准准确率 (Baseline Accuracy)"
          value={baselineSystem?.metrics ? (baselineSystem.metrics.accuracy * 100).toFixed(1) + '%' : '—'}
          note={baselineSystem?.metrics?.confidence_interval_95 ? '95% CI: [' + (baselineSystem.metrics.confidence_interval_95[0] * 100).toFixed(1) + '%, ' + (baselineSystem.metrics.confidence_interval_95[1] * 100).toFixed(1) + '%]' : '规则基准'}
        />
        <Kpi
          label="运行 Hash (Run Hash)"
          value={<code style={{ fontSize: 10 }}>{data.run_hash ? data.run_hash.slice(0, 12) : '—'}</code>}
          note={'Git SHA: ' + (data.git_sha ? data.git_sha.slice(0, 8) : '—')}
        />
      </div>

      {/* Systems Leaderboard Panel */}
      <Panel
        title="模型系统评测排行榜 (Systems Leaderboard)"
        actions={
          <button className="ghost" onClick={() => void loadBenchmark()} disabled={loading}>
            {loading ? '加载中...' : '刷新'}
          </button>
        }
      >
        <div style={{ marginBottom: 12, color: 'var(--muted)', fontSize: 12 }}>
          评测严格遵守确定性门禁：未运行系统清晰标明状态及未运行原因，不将缺失分数显示为 0。
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>系统标识 (System ID)</th>
                <th>状态 (Status)</th>
                <th>请求 / 解析模型</th>
                <th>准确率 (Accuracy)</th>
                <th>宏平均 F1</th>
                <th>召回率 (Recall)</th>
                <th>覆盖率</th>
                <th>P50 延迟</th>
                <th>单例成本</th>
                <th>McNemar 检验</th>
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
                        <Badge kind="ok">已完成 (completed)</Badge>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                          <Badge kind="warn">未运行 (not_run)</Badge>
                          {sys.reason ? (
                            <small className="muted" style={{ fontSize: 10 }}>
                              {sys.reason === 'missing_credential' ? '缺少 API 密钥' : sys.reason}
                            </small>
                          ) : null}
                        </div>
                      )}
                    </td>
                    <td>
                      <div><code>{sys.model_requested || '—'}</code></div>
                      {sys.model_resolved ? (
                        <small className="muted">解析: <code>{sys.model_resolved}</code></small>
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
        <Panel title="分赛道细分指标 (Track-Level Metrics)">
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
                  <th>系统 (System)</th>
                  <th>赛道准确率</th>
                  <th>宏平均 F1</th>
                  <th>召回率</th>
                  <th>误报率 (FPR)</th>
                  <th>Brier Score</th>
                  <th>校准误差 (ECE)</th>
                  <th>95% 置信区间</th>
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
      <Panel title="内嵌评分可视化图表 (Rendered Score Artifacts)">
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
          {IMAGE_CATEGORIES.map((cat) => (
            <button
              key={cat.key}
              className={activeCategory === cat.key ? 'primary' : 'ghost'}
              onClick={() => setActiveCategory(cat.key)}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {filteredImages.length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: 16 }}>
            {filteredImages.map((img) => {
              const meta = IMAGE_META[img.name] || {
                label: img.name,
                desc: 'Benchmark 评测图表',
              };
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
                    <strong style={{ fontSize: 13 }}>{meta.label}</strong>
                    <code style={{ fontSize: 11, color: 'var(--muted)' }}>{img.name}</code>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>{meta.desc}</div>
                  <div style={{ width: '100%', overflow: 'hidden', borderRadius: 'var(--radius)', border: '1px solid var(--border)', background: '#fff' }}>
                    <img
                      src={img.url}
                      alt={meta.label}
                      loading="lazy"
                      style={{ width: '100%', height: 'auto', display: 'block', objectFit: 'contain' }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <Empty text="该分类下没有相关评测图片" />
        )}
      </Panel>
    </div>
  );
}
