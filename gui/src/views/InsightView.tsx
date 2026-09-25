import { useEffect, useState } from 'react';
import { trader } from '../api';
import type { MistakeCluster, MistakeResponse, EdgeResponse, InsightEvidence, InsightObservation, InsightPatternsResponse, PatternCandidate, Playbook } from '../types';
import { Banner, Empty, Panel, formatMoney, formatPct, toneOf } from '../components/common';
import { useI18n } from '../i18n';
import { insightCopy, localizeInsightField, localizeInsightValue } from '../locales/insight';

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

export function InsightView({ scheme, onOpenTrade }: {
  scheme: 'cn' | 'intl';
  onOpenTrade?: (id: string) => void;
}) {
  const { locale } = useI18n();
  const copy = insightCopy(locale);
  const tabs: { key: InsightTab; label: string; hint: string }[] = [
    { key: 'mistakes', label: copy.tabs.mistakes, hint: copy.hints.mistakes },
    { key: 'edges', label: copy.tabs.edges, hint: copy.hints.edges },
    { key: 'patterns', label: copy.tabs.patterns, hint: copy.hints.patterns },
  ];
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

  const active = tabs.find((item) => item.key === tab) || tabs[0];

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="subnav" role="tablist">
        {tabs.map((item) => (
          <button
            key={item.key}
            role="tab"
            aria-selected={tab === item.key}
            data-insight-tab={item.key}
            className={'subnav-item' + (tab === item.key ? ' active' : '')}
            onClick={() => setTab(item.key)}
            title={item.hint}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? <Banner>{copy.readFailed}: {error} <button onClick={() => setRevision(value => value + 1)}>{copy.retry}</button></Banner> : null}
      {playbookError ? <Banner>交易计划读取失败：{playbookError} <button onClick={() => setRevision(value => value + 1)}>重试</button></Banner> : null}
      {loading ? <div className="muted">{copy.scanning}</div> : null}

      {!loading && !error && tab === 'mistakes' ? (
        <MistakesPanel data={mistakes} scheme={scheme} onOpenTrade={onOpenTrade} copy={copy} />
      ) : null}
      {!loading && !error && tab === 'edges' ? (
        <EdgesPanel data={edges} scheme={scheme} copy={copy} />
      ) : null}
      {!loading && !error && tab === 'patterns' ? (
        <PatternsPanel data={patterns} playbooks={playbooks} onOpenTrade={onOpenTrade} copy={copy} onRefresh={async () => {
          setPatterns(await trader.insightPatterns());
        }} />
      ) : null}

      <div className="muted" style={{ fontSize: 11 }}>{active.hint}</div>
    </div>
  );
}

function MistakesPanel({ data, scheme, onOpenTrade, copy }: {
  data: MistakeResponse | null;
  scheme: 'cn' | 'intl';
  onOpenTrade?: (id: string) => void;
  copy: ReturnType<typeof insightCopy>;
}) {
  const rows = data?.rows || [];
  const triggers = data?.triggers || [];

  return (
    <Panel title={copy.tabs.mistakes + ' (' + rows.length + ')'}>
      {/*
        The triggers that found nothing are listed too. A scan that says "checked
        six triggers, four matched nothing" is a different statement from a scan
        that only shows what it found, and only the first one lets the reader tell
        a clean month from an unchecked one.
      */}
      {triggers.length ? (
        <div className="muted" style={{ fontSize: 11, marginBottom: 10, lineHeight: 1.7 }}>
          {copy.other} {triggers.length} checks:
          {triggers.map((trigger) => (
            <span key={trigger.kind} className="chip" style={{ marginLeft: 6 }} title={trigger.skipped_reason || ''}>
              {localizeInsightValue(trigger.label || trigger.kind, copy)} {trigger.matched > 0 ? trigger.matched + ' ' + copy.evidenceCount : copy.unknown}
            </span>
          ))}
        </div>
      ) : null}

      {rows.length === 0 ? (
        <Empty text={copy.noMistakes} />
      ) : (
        <div className="grid" style={{ gap: 10 }}>
          {rows.map((row) => (
            <MistakeCard key={row.cluster_id} row={row} scheme={scheme} onOpenTrade={onOpenTrade} copy={copy} />
          ))}
        </div>
      )}
    </Panel>
  );
}

function MistakeCard({ row, scheme, onOpenTrade, copy }: {
  row: MistakeCluster;
  scheme: 'cn' | 'intl';
  onOpenTrade?: (id: string) => void;
  copy: ReturnType<typeof insightCopy>;
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
          {copy.evidenceCount}:
          {distinctEvidence(row.evidence).map((item) => (
            <span key={item.field + item.comparator + String(item.threshold)} className="chip" style={{ marginLeft: 6 }}>
              {localizeInsightField(item.field, copy)} {copy.evidence[item.comparator] || copy.other} {String(item.threshold)}
            </span>
          ))}
          <span style={{ marginLeft: 6 }}>{row.evidence.length} {copy.evidenceCount}</span>
        </div>
      ) : null}

      <div className="row" style={{ marginTop: 8, flexWrap: 'wrap', gap: 6 }}>
        {shown.map((id) => (
          <button
            key={id}
            className="chip chip-action"
            onClick={() => onOpenTrade?.(id)}
            disabled={!onOpenTrade}
            title={onOpenTrade ? copy.viewEvidence : copy.unknown}
          >
            {id}
          </button>
        ))}
        {openable.length > 6 ? (
          <button className="chip chip-action" onClick={() => setOpen((previous) => !previous)}>
            {open ? copy.hideEvidence : copy.other + ' ' + (openable.length - 6)}
          </button>
        ) : null}
        {openable.length === 0 ? (
          <span className="muted" style={{ fontSize: 11 }}>
            {fillCount} {copy.evidenceCount}; no linked trade detail is available.
          </span>
        ) : null}
      </div>

      <ObservationNote row={row} copy={copy} />
    </div>
  );
}

function EdgesPanel({ data, scheme, copy }: { data: EdgeResponse | null; scheme: 'cn' | 'intl'; copy: ReturnType<typeof insightCopy> }) {
  const rows = data?.rows || [];
  return (
    <Panel title={copy.tabs.edges + ' (' + rows.length + ')'}>
      {rows.length === 0 ? (
        <Empty text={copy.noEdges} />
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
                <td className="muted">{localizeInsightField(row.dimension, copy)}</td>
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

function PatternsPanel({ data, playbooks, onRefresh, onOpenTrade, copy }: { data: InsightPatternsResponse | null; playbooks: Playbook[]; onRefresh: () => Promise<void>; onOpenTrade?: (id: string) => void; copy: ReturnType<typeof insightCopy> }) {
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
      <Panel title={copy.tabs.patterns}>
        <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
          <span>{copy.sample} {data?.profile?.sample_count ?? 0}</span>
          <span>{copy.fields.data_quality}: {localizeInsightValue(data?.profile?.data_quality, copy)}</span>
          <span className="muted" style={{ fontSize: 11 }}>{copy.confirmNote}</span>
        </div>
        <div className="grid split" data-testid="pattern-axes">
          {Object.entries(data?.profile?.axes || {}).map(([axis, value]) => <section className="insight-card" key={axis}>
            <strong>{localizeInsightField(axis, copy)}</strong><p>{localizeInsightValue(value.label, copy)}</p>
            {Object.entries(value.counts).map(([label, count]) => <div className="row" key={label}><span>{localizeInsightValue(label, copy)}</span><span className="num">{count}</span></div>)}
          </section>)}
        </div>
        {data?.profile?.limitations?.length ? <ul className="muted" style={{ fontSize: 11, margin: '8px 0 0 16px' }}>{data.profile.limitations.map((item) => <li key={item}>{item}</li>)}</ul> : null}
      </Panel>
      <Panel title={copy.tabs.patterns + ' (' + candidates.length + ')'}>
        {candidates.length === 0 ? <Empty text={copy.noPatterns} /> : (
          <div className="grid" style={{ gap: 10 }}>
            {candidates.slice(page * 50, (page + 1) * 50).map((candidate) => (
              <div className="insight-card" key={candidate.pattern_id}>
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <strong>{candidate.label}</strong>
                  <span className="badge">{localizeInsightValue(candidate.status, copy)} · {copy.fields.confidence} {localizeInsightValue(candidate.confidence, copy)}</span>
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{localizeInsightField(candidate.axis, copy)} · {localizeInsightValue(candidate.data_quality, copy)} · {candidate.trade_ids.length} {copy.evidenceCount}</div>
                {candidate.missing_data.length ? <div className="notice" style={{ marginTop: 8, fontSize: 11 }}>{copy.dataLimits}: {candidate.missing_data.map((item) => localizeInsightValue(item, copy)).join('、')}</div> : null}
                <div className="row">
                  <button className="ghost" aria-expanded={Boolean(expanded[candidate.pattern_id])} onClick={() => setExpanded(current => ({ ...current, [candidate.pattern_id]: !current[candidate.pattern_id] }))}>{expanded[candidate.pattern_id] ? copy.hideEvidence : copy.viewEvidence}</button>
                  {candidate.round_trip_id && onOpenTrade ? <button className="ghost" onClick={() => onOpenTrade(candidate.round_trip_id!)}>打开交易</button> : null}
                </div>
                {expanded[candidate.pattern_id] ? <dl className="observation">{candidate.evidence.map((item, index) => <div key={index}><dt>{localizeInsightField(item.field || index, copy)}</dt><dd>{typeof item.observed === 'object' ? JSON.stringify(item.observed) : localizeInsightValue(item.observed, copy)}</dd></div>)}</dl> : null}
                <ObservationNote row={candidate} copy={copy} />
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
function ObservationNote({ row, copy }: { row: InsightObservation; copy: ReturnType<typeof insightCopy> }) {
  const [open, setOpen] = useState(false);
  const items: [string, string][] = [
    [copy.fields.invalidation, row.invalidation],
    [copy.fields.time_stop, row.time_stop],
    [copy.fields.give_up, row.give_up],
    [copy.fields.data_source, row.data_source],
    [copy.fields.available_at, row.available_at],
    [copy.fields.data_quality, localizeInsightValue(row.data_quality, copy)],
  ];
  return (
    <div style={{ marginTop: 8 }}>
      <button className="ghost" style={{ fontSize: 11 }} onClick={() => setOpen((previous) => !previous)}>
        {open ? copy.hideConditions : copy.viewConditions}
      </button>
      {open ? (
        <dl className="observation">
          {items.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value || copy.unknown}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

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
