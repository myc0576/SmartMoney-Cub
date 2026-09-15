import { useCallback, useEffect, useState } from 'react';
import { trader } from '../api';
import type { Playbook, PlaybookStats } from '../types';
import { Banner, Empty, Panel, formatMoney, formatPct, toneOf } from '../components/common';

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
      setError('playbook 需要一个名字。');
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
      setStatus('已保存 playbook「' + name + '」。');
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
        playbook 记录的是你自己的计划：什么条件进场、什么条件离场、单笔承担多少风险。
        收益数字只在有匹配交易时出现，样本不足会明确标注，不会用 0 冒充结果。
      </div>

      {error ? <Banner>{error}</Banner> : null}
      {status ? <div className="muted" style={{ fontSize: 11 }}>{status}</div> : null}

      <Panel
        title={'Playbooks（' + playbooks.length + '）'}
        actions={
          <button className="ghost" onClick={() => { setCreating((previous) => !previous); setError(''); }}>
            {creating ? '取消新增' : '新增 playbook'}
          </button>
        }
      >
        {creating ? (
          <div className="grid" style={{ gap: 10, marginBottom: 14 }}>
            <div className="grid split">
              <div className="field">
                <label>名称</label>
                <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="例如：开盘区间突破" />
              </div>
              <div className="field">
                <label>标签（逗号分隔）</label>
                <input value={draft.tags} onChange={(event) => setDraft({ ...draft, tags: event.target.value })} placeholder="突破, A 级机会" />
              </div>
            </div>
            <div className="field">
              <label>一句话说明</label>
              <input value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} />
            </div>
            <div className="field">
              <label>适用场景</label>
              <input value={draft.setup} onChange={(event) => setDraft({ ...draft, setup: event.target.value })} placeholder="例如：高开缺口、趋势日" />
            </div>
            <div className="grid split">
              <div className="field">
                <label>进场条件（每行一条）</label>
                <textarea value={draft.entry_rules} onChange={(event) => setDraft({ ...draft, entry_rules: event.target.value })} placeholder="价格站上开盘区间上沿" />
              </div>
              <div className="field">
                <label>离场条件（每行一条）</label>
                <textarea value={draft.exit_rules} onChange={(event) => setDraft({ ...draft, exit_rules: event.target.value })} placeholder="跌破 VWAP 离场；到达 2R 分批止盈" />
              </div>
            </div>
            <div className="field">
              <label>风险规则（每行一条）</label>
              <textarea value={draft.risk_rules} onChange={(event) => setDraft({ ...draft, risk_rules: event.target.value })} placeholder="单笔风险不超过账户 1%；连续两笔亏损后降半仓" />
            </div>
            <div className="row">
              <button className="primary" onClick={() => void submit()} disabled={busy}>{busy ? '保存中…' : '保存'}</button>
              <span className="muted" style={{ fontSize: 11 }}>保存后按名称与你的交易自动匹配。</span>
            </div>
          </div>
        ) : null}

        {playbooks.length === 0 ? (
          <Empty text="还没有 playbook。用「新增 playbook」写下第一个计划。" />
        ) : (
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>名称</th><th>场景</th><th className="num">笔数</th><th className="num">胜率</th>
                  <th className="num">净盈亏</th><th className="num">平均收益</th><th>标签</th>
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
        <Panel title={'计划详情 · ' + current.name}>
          <RuleList title="进场条件" rules={current.entry_rules} />
          <RuleList title="离场条件" rules={current.exit_rules} />
          <RuleList title="风险规则" rules={current.risk_rules} />
          {stats[current.name]?.small_sample ? (
            <div className="muted" style={{ fontSize: 11, marginTop: 10 }}>* 该 playbook 的匹配样本不足 5 笔，数字只作提示。</div>
          ) : null}
          {current.description ? (
            <div className="muted" style={{ fontSize: 12, marginTop: 10, lineHeight: 1.7 }}>{current.description}</div>
          ) : null}
        </Panel>
      ) : null}
    </div>
  );
}

function RuleList({ title, rules }: { title: string; rules: string[] | undefined }) {
  const items = Array.isArray(rules) ? rules : [];
  return (
    <div style={{ marginBottom: 10 }}>
      <div className="kpi-label">{title}</div>
      {items.length === 0 ? (
        <div className="muted" style={{ fontSize: 12 }}>未记录</div>
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
