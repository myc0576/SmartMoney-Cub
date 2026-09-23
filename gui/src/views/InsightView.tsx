import { useEffect, useState } from 'react';
import { trader } from '../api';
import type { MistakeCluster, MistakeResponse, EdgeResponse, InsightEvidence, InsightObservation, InsightPatternsResponse, PatternCandidate, Playbook } from '../types';
import { Banner, Empty, Panel, formatMoney, formatPct, toneOf } from '../components/common';

/**
 * Insight: the two questions a journal can answer about a trader rather than
 * about a set of trades.
 *
 * "What do I keep doing wrong" and "what actually pays" are the same subtraction
 * run in opposite directions, and both are harder than a statistic because the
 * answer has to be believable. So every row here carries how it was found (the
 * trigger and the threshold), how many trades it covers, and the observation
 * envelope the repository requires: how the finding would be invalidated, when
 * it expires, where the data came from, when that data was available, and how
 * good it is. A row that cannot state one of those says so; none of them are
 * filled in with a plausible default.
 */

type InsightTab = 'mistakes' | 'edges' | 'patterns';

const TABS: { key: InsightTab; label: string; hint: string }[] = [
  { key: 'mistakes', label: '重复错误', hint: '可观察的重复行为，不据此判断情绪或动机' },
  { key: 'edges', label: 'Edge 库', hint: '历史分组结果只是待验证假设，不代表稳定优势' },
  { key: 'patterns', label: '模式画像', hint: '从成交事实推断趋势、超短和日内行为' },
];

export function InsightView({ scheme, onOpenTrade }: {
  scheme: 'cn' | 'intl';
  onOpenTrade?: (id: string) => void;
}) {
  const [tab, setTab] = useState<InsightTab>('patterns');
  const [mistakes, setMistakes] = useState<MistakeResponse | null>(null);
  const [edges, setEdges] = useState<EdgeResponse | null>(null);
  const [patterns, setPatterns] = useState<InsightPatternsResponse | null>(null);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [playbookError, setPlaybookError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([trader.insightMistakes(), trader.insightEdges(), trader.insightPatterns()])
      .then(([mistakeResult, edgeResult, patternResult]) => {
        if (cancelled) return;
        setMistakes(mistakeResult);
        setEdges(edgeResult);
        setPatterns(patternResult);
        setError('');
      })
      .catch((failure) => {
        if (cancelled) return;
        // A read that failed is reported as a failed read. "No mistakes" and
        // "the mistake scan did not run" are different claims and only one of
        // them is good news.
        setMistakes(null);
        setEdges(null);
        setPatterns(null);
        setError(failure instanceof Error ? failure.message : String(failure));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [revision]);

  useEffect(() => {
    let cancelled = false;
    trader.playbooks().then((result) => {
      if (!cancelled) { setPlaybooks(result.playbooks || []); setPlaybookError(''); }
    }).catch(failure => {
      if (!cancelled) { setPlaybooks([]); setPlaybookError(failure instanceof Error ? failure.message : String(failure)); }
    });
    return () => { cancelled = true; };
  }, [revision]);

  const active = TABS.find((item) => item.key === tab) || TABS[0];

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="subnav" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.key}
            role="tab"
            aria-selected={tab === item.key}
            className={'subnav-item' + (tab === item.key ? ' active' : '')}
            onClick={() => setTab(item.key)}
            title={item.hint}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? <Banner>洞察数据读取失败：{error} <button onClick={() => setRevision(value => value + 1)}>重试</button></Banner> : null}
      {playbookError ? <Banner>交易计划读取失败：{playbookError} <button onClick={() => setRevision(value => value + 1)}>重试</button></Banner> : null}
      {loading ? <div className="muted">正在扫描台账…</div> : null}

      {!loading && !error && tab === 'mistakes' ? (
        <MistakesPanel data={mistakes} scheme={scheme} onOpenTrade={onOpenTrade} />
      ) : null}
      {!loading && !error && tab === 'edges' ? (
        <EdgesPanel data={edges} scheme={scheme} />
      ) : null}
      {!loading && !error && tab === 'patterns' ? (
        <PatternsPanel data={patterns} playbooks={playbooks} onOpenTrade={onOpenTrade} onRefresh={async () => {
          setPatterns(await trader.insightPatterns());
        }} />
      ) : null}

      <div className="muted" style={{ fontSize: 11 }}>{active.hint}</div>
    </div>
  );
}

function MistakesPanel({ data, scheme, onOpenTrade }: {
  data: MistakeResponse | null;
  scheme: 'cn' | 'intl';
  onOpenTrade?: (id: string) => void;
}) {
  const rows = data?.rows || [];
  const triggers = data?.triggers || [];

  return (
    <Panel title={'重复错误（' + rows.length + ' 个簇）'}>
      {/*
        The triggers that found nothing are listed too. A scan that says "checked
        six triggers, four matched nothing" is a different statement from a scan
        that only shows what it found, and only the first one lets the reader tell
        a clean month from an unchecked one.
      */}
      {triggers.length ? (
        <div className="muted" style={{ fontSize: 11, marginBottom: 10, lineHeight: 1.7 }}>
          已检查 {triggers.length} 类触发：
          {triggers.map((trigger) => (
            <span key={trigger.kind} className="chip" style={{ marginLeft: 6 }} title={trigger.skipped_reason || ''}>
              {trigger.label} {trigger.matched > 0 ? trigger.matched + ' 笔' : '无匹配'}
            </span>
          ))}
        </div>
      ) : null}

      {rows.length === 0 ? (
        <Empty text="确定性触发没有找到成簇的坏交易。这不等于没有问题，只说明这些触发条件没有成簇命中。" />
      ) : (
        <div className="grid" style={{ gap: 10 }}>
          {rows.map((row) => (
            <MistakeCard key={row.cluster_id} row={row} scheme={scheme} onOpenTrade={onOpenTrade} />
          ))}
        </div>
      )}
    </Panel>
  );
}

function MistakeCard({ row, scheme, onOpenTrade }: {
  row: MistakeCluster;
  scheme: 'cn' | 'intl';
  onOpenTrade?: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  // The round trips are what a click can open; the fills are the evidence. When
  // the route resolved no round trip for a fill, the fill id is still listed --
  // it is the fact the trigger fired on -- but it is not offered as a link.
  const openable = row.round_trip_ids || [];
  const shown = open ? openable : openable.slice(0, 6);
  const fillCount = row.trade_ids.length;

  return (
    <div className="insight-card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <strong>{row.label}</strong>
        <span className={'num ' + toneOf(row.net_pnl, scheme)} style={{ fontWeight: 600 }}>
          {formatMoney(row.net_pnl)}
        </span>
      </div>

      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
        {row.count} 笔 · 平均收益 <span className={toneOf(row.avg_return_pct, scheme)}>{formatPct(row.avg_return_pct)}</span>
        {' · '}{row.first_at} → {row.last_at}
      </div>

      {/*
        The trigger, said once.

        The backend reports one evidence row per matched trade, which is the right
        shape for a record and the wrong shape for this card: a cluster of 185
        trades rendered 185 identical chips and buried the card under its own
        proof. What a reader needs here is the rule that was applied and how many
        trades it caught; the per-trade values are the same rule measured again,
        and they belong to the trade list below rather than to the definition.
      */}
      {row.evidence?.length ? (
        <div className="muted" style={{ fontSize: 11, marginTop: 6, lineHeight: 1.7 }}>
          判定依据：
          {distinctEvidence(row.evidence).map((item) => (
            <span key={item.field + item.comparator + String(item.threshold)} className="chip" style={{ marginLeft: 6 }}>
              {item.field} {item.comparator} {String(item.threshold)}
            </span>
          ))}
          <span style={{ marginLeft: 6 }}>命中 {row.evidence.length} 次</span>
        </div>
      ) : null}

      <div className="row" style={{ marginTop: 8, flexWrap: 'wrap', gap: 6 }}>
        {shown.map((id) => (
          <button
            key={id}
            className="chip chip-action"
            onClick={() => onOpenTrade?.(id)}
            disabled={!onOpenTrade}
            title={onOpenTrade ? '打开这一笔' : '该交易无法直接打开'}
          >
            {id}
          </button>
        ))}
        {openable.length > 6 ? (
          <button className="chip chip-action" onClick={() => setOpen((previous) => !previous)}>
            {open ? '收起' : '还有 ' + (openable.length - 6) + ' 笔'}
          </button>
        ) : null}
        {openable.length === 0 ? (
          <span className="muted" style={{ fontSize: 11 }}>
            这 {fillCount} 条触发成交没有配成已平仓回合，所以没有可以打开的交易明细。
          </span>
        ) : null}
      </div>

      <ObservationNote row={row} />
    </div>
  );
}

function EdgesPanel({ data, scheme }: { data: EdgeResponse | null; scheme: 'cn' | 'intl' }) {
  const rows = data?.rows || [];
  return (
    <Panel title={'Edge 库（' + rows.length + ' 个）'}>
      {rows.length === 0 ? (
        <Empty text="还没有可以成组的盈利模式。标签、市场状态或持有周期需要先有成交才会出现分组。" />
      ) : (
        <div className="scroll-x">
          <table>
            <thead>
              <tr>
                <th>维度</th><th>模式</th>
                <th className="num">样本</th><th className="num">胜率</th>
                <th className="num">平均收益</th><th className="num">盈亏比</th><th className="num">净盈亏</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.edge_id}>
                  <td className="muted">{dimensionLabel(row.dimension)}</td>
                  <td>
                    {row.name || row.key}
                    {row.small_sample ? (
                      <span className="badge warn" style={{ marginLeft: 6 }} title="样本不足，不能当成模式">样本少</span>
                    ) : null}
                  </td>
                  <td className="num">{row.trade_count}</td>
                  <td className="num">{row.win_rate}%</td>
                  <td className={'num ' + toneOf(row.avg_return_pct, scheme)}>{formatPct(row.avg_return_pct)}</td>
                  <td className="num">{row.profit_factor === null ? '—' : row.profit_factor}</td>
                  <td className={'num ' + toneOf(row.net_pnl, scheme)}>{formatMoney(row.net_pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length ? (
        <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
          按净盈亏排序。样本少的行带标记，它的期望值不能当成结论。
        </div>
      ) : null}
    </Panel>
  );
}

function PatternsPanel({ data, playbooks, onRefresh, onOpenTrade }: { data: InsightPatternsResponse | null; playbooks: Playbook[]; onRefresh: () => Promise<void>; onOpenTrade?: (id: string) => void }) {
  const [pending, setPending] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [page, setPage] = useState(0);
  const [rename, setRename] = useState<Record<string, string>>({});
  const candidates = data?.candidates || [];
  const decide = async (candidate: PatternCandidate, action: 'confirm' | 'reject' | 'rename', playbookId?: string) => {
    const label = action === 'rename' ? (playbookId ? candidate.label : (rename[candidate.pattern_id] || '').trim()) : undefined;
    if (action === 'rename' && !label) return;
    setPending(candidate.pattern_id + ':' + action);
    setActionError('');
    try {
      await trader.decidePattern({ pattern_id: candidate.pattern_id, action, label, ...(playbookId ? { playbook_id: playbookId } : {}) });
      await onRefresh();
    } catch (failure) {
      setActionError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setPending(null);
    }
  };
  return (
    <div className="grid" style={{ gap: 12 }}>
      {actionError ? <div className="banner" role="alert">{actionError}</div> : null}
      <Panel title="模式总览">
        <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
          <span>样本 {data?.profile?.sample_count ?? 0}</span>
          <span>数据质量 {data?.profile?.data_quality || 'unknown'}</span>
          <span className="muted" style={{ fontSize: 11 }}>确认只改变本地标签，不会把推断变成交易建议。</span>
        </div>
        <div className="grid split" data-testid="pattern-axes">
          {Object.entries(data?.profile?.axes || {}).map(([axis, value]) => <section className="insight-card" key={axis}>
            <strong>{axis}</strong><p>{value.label || 'unknown'}</p>
            {Object.entries(value.counts).map(([label, count]) => <div className="row" key={label}><span>{label}</span><span className="num">{count}</span></div>)}
          </section>)}
        </div>
        {data?.profile?.limitations?.length ? <ul className="muted" style={{ fontSize: 11, margin: '8px 0 0 16px' }}>{data.profile.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : null}
      </Panel>
      <Panel title={'候选模式（' + candidates.length + '）'}>
        {candidates.length === 0 ? <Empty text="当前成交不足以形成可解释的模式画像。" /> : (
          <div className="grid" style={{ gap: 10 }}>
            {candidates.slice(page * 50, (page + 1) * 50).map((candidate) => (
              <div className="insight-card" key={candidate.pattern_id}>
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <strong>{candidate.label}</strong>
                  <span className="badge">{candidate.status} · 证据支持度 {candidate.confidence}</span>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{candidate.axis} · {candidate.data_quality} · {candidate.trade_ids.length} 条证据</div>
                {candidate.missing_data.length ? <div className="notice" style={{ marginTop: 8, fontSize: 11 }}>数据限制：{candidate.missing_data.join('、')}</div> : null}
                <div className="row">
                  <button className="ghost" aria-expanded={Boolean(expanded[candidate.pattern_id])} onClick={() => setExpanded(current => ({ ...current, [candidate.pattern_id]: !current[candidate.pattern_id] }))}>查看证据</button>
                  {candidate.round_trip_id && onOpenTrade ? <button className="ghost" onClick={() => onOpenTrade(candidate.round_trip_id!)}>打开交易</button> : null}
                </div>
                {expanded[candidate.pattern_id] ? <dl className="observation">{candidate.evidence.map((item, index) => <div key={index}><dt>{String(item.field || index)}</dt><dd>{typeof item.observed === 'object' ? JSON.stringify(item.observed) : String(item.observed ?? 'unknown')}</dd></div>)}</dl> : null}
                <ObservationNote row={candidate} />
                <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                  <button className="ghost" disabled={Boolean(pending)} onClick={() => void decide(candidate, 'confirm')}>确认模式</button>
                  <button className="ghost" disabled={Boolean(pending)} onClick={() => void decide(candidate, 'reject')}>否决</button>
                  <input aria-label="新模式名称" placeholder="重命名" disabled={Boolean(pending)} value={rename[candidate.pattern_id] || ''} onChange={(event) => setRename((current) => ({ ...current, [candidate.pattern_id]: event.target.value }))} style={{ width: 130 }} />
                  <button className="ghost" disabled={Boolean(pending) || !(rename[candidate.pattern_id] || '').trim()} onClick={() => void decide(candidate, 'rename')}>保存名称</button>
                  {playbooks.length ? <select aria-label="关联 playbook" disabled={Boolean(pending)} value={candidate.decision?.playbook_id || ''} onChange={(event) => { if (event.target.value) void decide(candidate, 'rename', event.target.value); }}><option value="">关联 playbook</option>{playbooks.map((playbook) => <option key={playbook.playbook_id} value={playbook.playbook_id}>{playbook.name}</option>)}</select> : null}
                </div>
              </div>
            ))}
          </div>
        )}
        {candidates.length > 50 ? <div className="row"><button disabled={page === 0} onClick={() => setPage(value => value - 1)}>上一页</button><span>{page + 1}/{Math.ceil(candidates.length / 50)}</span><button disabled={(page + 1) * 50 >= candidates.length} onClick={() => setPage(value => value + 1)}>下一页</button></div> : null}
      </Panel>
    </div>
  );
}

/**
 * The observation envelope, rendered once per card.
 *
 * It is deliberately plain text rather than a tooltip: the contract makes these
 * fields part of the claim, and a claim whose limits are hidden behind a hover
 * is not stating them.
 */
function ObservationNote({ row }: { row: InsightObservation }) {
  const [open, setOpen] = useState(false);
  const items: [string, string][] = [
    ['失效条件', row.invalidation],
    ['时间止损', row.time_stop],
    ['放弃条件', row.give_up],
    ['数据来源', row.data_source],
    ['数据可用时间', row.available_at],
    ['数据质量', row.data_quality],
  ];
  return (
    <div style={{ marginTop: 8 }}>
      <button className="ghost" style={{ fontSize: 11 }} onClick={() => setOpen((previous) => !previous)}>
        {open ? '收起观察条件' : '查看观察条件'}
      </button>
      {open ? (
        <dl className="observation">
          {items.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value || 'unknown'}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

const DIMENSION_LABELS: Record<string, string> = {
  tag: '标签', regime: '市场状态', holding: '持有周期', symbol: '标的', weekday: '星期',
};

/**
 * The distinct rules behind a cluster, in the order they first appear.
 *
 * A cluster carries one evidence row per matched trade. The rule is the same
 * every time and only the observed value differs, so the definition is shown
 * once and the count carries the volume. Returning the first row per
 * (field, comparator, threshold) keeps the display honest about which rule was
 * applied without pretending the repeats are different findings.
 */
function distinctEvidence(evidence: InsightEvidence[]): InsightEvidence[] {
  const seen = new Map<string, InsightEvidence>();
  for (const item of evidence) {
    const key = item.field + '|' + item.comparator + '|' + String(item.threshold);
    if (!seen.has(key)) seen.set(key, item);
  }
  return [...seen.values()];
}

function dimensionLabel(dimension: string): string {
  return DIMENSION_LABELS[dimension] || dimension;
}
