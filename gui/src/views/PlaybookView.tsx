import { useCallback, useEffect, useState } from 'react';
import { trader } from '../api';
import type { Playbook, PlaybookStats } from '../types';
import { Banner, Empty, Panel, formatMoney, formatPct, toneOf } from '../components/common';
import { useLegacyI18n } from '../locales/legacy';

/**
 * Playbooks: the trader's own setups, and what each one actually returned.
 *
 * A playbook is a written plan, so the form treats entry/exit/risk rules as
 * one-per-line lists rather than free text. That keeps a rule a rule: a column
 * of lines the trader can scan and score against, not a paragraph to re-read.
 *
 * The outcome column is keyed by the playbook's name, because that is the field
 * a trade carries. A playbook with no matching trades shows as "—" rather than
 * zero, which would read as a measured loss.
 */

interface Draft {
  name: string;
  description: string;
  setup: string;
  entry_rules: string;
  exit_rules: string;
  risk_rules: string;
  tags: string;
}

const EMPTY_DRAFT: Draft = {
  name: '', description: '', setup: '', entry_rules: '', exit_rules: '', risk_rules: '', tags: '',
};

export function PlaybookView({ scheme }: { scheme: 'cn' | 'intl' }) {
  const { t } = useLegacyI18n();
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [stats, setStats] = useState<Record<string, PlaybookStats>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');

  const load = useCallback(async () => {
    try {
      const result = await trader.playbooks();
      const list = Array.isArray(result.playbooks) ? result.playbooks : [];
      setPlaybooks(list);
      setStats(result.stats || {});
      setSelected((current) => (current && list.some((item) => item.playbook_id === current) ? current : list[0]?.playbook_id ?? null));
      setError('');
    } catch (failure) {
      setPlaybooks([]);
      setStats({});
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const current = playbooks.find((item) => item.playbook_id === selected) || null;

  const submit = async () => {
    const name = draft.name.trim();
    if (!name) {
      setError(t('playbook.errorName'));
      return;
    }
    setBusy(true);
    setError('');
    try {
      await trader.createPlaybook({
        name,
        description: draft.description.trim(),
        setup: draft.setup.trim(),
        entry_rules: lines(draft.entry_rules),
        exit_rules: lines(draft.exit_rules),
        risk_rules: lines(draft.risk_rules),
        tags: splitTags(draft.tags),
      });
      setDraft(EMPTY_DRAFT);
      setCreating(false);
      setStatus(t('playbook.saved', { name }));
      await load();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice">
        {t('playbook.notice')}
      </div>

      {error ? <Banner>{error}</Banner> : null}
      {status ? <div className="muted" style={{ fontSize: 11 }}>{status}</div> : null}

      <Panel
        title={t('playbook.title', { count: playbooks.length })}
        actions={
          <button className="ghost" onClick={() => { setCreating((previous) => !previous); setError(''); }}>
            {creating ? t('playbook.cancelAdd') : t('playbook.add')}
          </button>
        }
      >
        {creating ? (
          <div className="grid" style={{ gap: 10, marginBottom: 14 }}>
            <div className="grid split">
              <div className="field">
                <label>{t('playbook.name')}</label>
                <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder={t('playbook.namePlaceholder')} />
              </div>
              <div className="field">
                <label>{t('playbook.tags')}</label>
                <input value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} placeholder={t('playbook.tagsPlaceholder')} />
              </div>
            </div>
            <div className="field">
              <label>{t('playbook.description')}</label>
              <input value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
            </div>
            <div className="field">
              <label>{t('playbook.setup')}</label>
              <input value={draft.setup} onChange={(event) => setDraft({ ...draft, setup: event.target.value })} placeholder={t('playbook.setupPlaceholder')} />
            </div>
            <div className="grid split">
              <div className="field">
                <label>{t('playbook.entry')}</label>
                <textarea value={draft.entry_rules} onChange={(event) => setDraft({ ...draft, entry_rules: event.target.value })} placeholder={t('playbook.entryPlaceholder')} />
              </div>
              <div className="field">
                <label>{t('playbook.exit')}</label>
                <textarea value={draft.exit_rules} onChange={(event) => setDraft({ ...draft, exit_rules: event.target.value })} placeholder={t('playbook.exitPlaceholder')} />
              </div>
            </div>
            <div className="field">
              <label>{t('playbook.risk')}</label>
              <textarea value={draft.risk_rules} onChange={(event) => setDraft({ ...draft, risk_rules: event.target.value })} placeholder={t('playbook.riskPlaceholder')} />
            </div>
            <div className="row">
              <button className="primary" onClick={() => void submit()} disabled={busy}>{busy ? t('playbook.saving') : t('playbook.save')}</button>
              <span className="muted" style={{ fontSize: 11 }}>{t('playbook.matchHint')}</span>
            </div>
          </div>
        ) : null}

        {playbooks.length === 0 ? (
          <Empty text={t('playbook.empty')} />
        ) : (
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>{t('playbook.name')}</th><th>{t('playbook.scene')}</th><th className="num">{t('reports.count')}</th><th className="num">{t('reports.winRate')}</th>
                  <th className="num">{t('reports.netPnl')}</th><th className="num">{t('playbook.avgReturn')}</th><th>{t('playbook.tags')}</th>
                </tr>
              </thead>
              <tbody>
                {playbooks.map((playbook) => {
                  const outcome = stats[playbook.name];
                  return (
                    <tr
                      key={playbook.playbook_id}
                      onClick={() => setSelected(playbook.playbook_id)}
                      style={{ background: playbook.playbook_id === selected ? 'var(--panel-2)' : undefined }}
                    >
                      <td>{playbook.name}</td>
                      <td className="muted">{playbook.setup || '—'}</td>
                      <td className="num">{outcome ? outcome.trade_count : '—'}</td>
                      <td className="num">{outcome ? outcome.win_rate + '%' : '—'}</td>
                      <td className={'num ' + (outcome ? toneOf(outcome.net_pnl, scheme) : 'muted')}>
                        {outcome ? formatMoney(outcome.net_pnl) : '—'}
                      </td>
                      <td className={'num ' + (outcome ? toneOf(outcome.avg_return_pct, scheme) : 'muted')}>
                        {outcome ? formatPct(outcome.avg_return_pct) : '—'}
                      </td>
                      <td>{(playbook.tags || []).map((tag) => <span className="tag" key={tag}>{tag}</span>)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {current ? (
        <Panel title={t('playbook.detail', { name: current.name })}>
          <RuleList title={t('playbook.entry').replace('（每行一条）', '')} rules={current.entry_rules} emptyLabel={t('playbook.unrecorded')} />
          <RuleList title={t('playbook.exit').replace('（每行一条）', '')} rules={current.exit_rules} emptyLabel={t('playbook.unrecorded')} />
          <RuleList title={t('playbook.risk').replace('（每行一条）', '')} rules={current.risk_rules} emptyLabel={t('playbook.unrecorded')} />
          {stats[current.name]?.small_sample ? (
            <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>{t('playbook.smallSample')}</div>
          ) : null}
          {current.description ? (
            <div className="muted" style={{ fontSize: 12, marginTop: 10, lineHeight: 1.7 }}>{current.description}</div>
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}

function RuleList({ title, rules, emptyLabel }: { title: string; rules: string[] | undefined; emptyLabel: string }) {
  const items = Array.isArray(rules) ? rules : [];
  return (
    <div style={{ marginBottom: 10 }}>
      <div className="kpi-label">{title}</div>
      {items.length === 0 ? (
        <div className="muted" style={{ fontSize: 12 }}>{emptyLabel}</div>
      ) : (
        <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 12.5, lineHeight: 1.7 }}>
          {items.map((rule, index) => <li key={index}>{rule}</li>)}
        </ul>
      )}
    </div>
  );
}

function lines(text: string): string[] {
  return text.split('\n').map((line) => line.trim()).filter(Boolean);
}

function splitTags(text: string): string[] {
  return text.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean);
}
