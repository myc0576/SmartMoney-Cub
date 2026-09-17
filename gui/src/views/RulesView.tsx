import { useEffect, useState } from 'react';
import { api } from '../api';
import type { RuleRecord } from '../types';
import { Empty, Panel } from '../components/common';

// A blocker code arrives as a machine-readable token from the same threshold
// check the rest of the product uses. Showing the raw token teaches the reader
// nothing, so each known code gets one plain sentence; an unknown code falls
// back to itself rather than being silently dropped, because a gate the reader
// cannot see is worse than an ugly label.
const BLOCKER_TEXT: Record<string, string> = {
  sample_count_below_20: '样本不足 20 笔',
  'false_alert_rate_above_0.2': '误报率高于 0.2',
  'missed_opportunity_rate_above_0.25': '错过率高于 0.25',
  future_leakage_detected: '存在未来数据泄漏',
  risk_contract_violations_detected: '存在风险契约违规',
  evidence_failures_detected: '证据本身有失败项',
};

function blockerText(code: string): string {
  return BLOCKER_TEXT[code] || code.replace(/_/g, ' ');
}

export function RulesView() {
  const [rules, setRules] = useState<RuleRecord[]>([]);
  const [error, setError] = useState('');
  // The rule id whose note box is open, and the text typed into it. Promotion is
  // two deliberate steps -- open, then submit a written reason -- because the
  // product's contract makes the note, not the button, the thing that authorizes
  // a champion row.
  const [promoting, setPromoting] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const [message, setMessage] = useState('');

  const load = () =>
    api
      .rules()
      .then((result) => {
        setRules(result.rules);
        setError('');
      })
      .catch((reason) => {
        // A failed read is reported as a failed read. The rule registry belongs to
        // the local review workbench, so on a host that closes that surface the
        // answer is "not available here" rather than "no rules exist" -- different
        // claims.
        setError(reason instanceof Error ? reason.message : String(reason));
      });

  useEffect(() => {
    void load();
    const onUpdate = () => { void load(); };
    window.addEventListener('smcub:rules-updated', onUpdate);
    window.addEventListener('focus', onUpdate);
    const timer = setInterval(() => { void load(); }, 2000);
    return () => {
      window.removeEventListener('smcub:rules-updated', onUpdate);
      window.removeEventListener('focus', onUpdate);
      clearInterval(timer);
    };
  }, []);

  const champions = rules.filter((rule) => rule.status === 'champion');
  const challengers = rules.filter((rule) => rule.status === 'challenger');

  const submit = async (ruleId: string) => {
    const reason = note.trim();
    if (!reason) {
      // The server enforces this too. Refusing here makes the rule visible
      // before a round trip rather than after one.
      setFailure('晋级必须写一条确认说明，说明会随规则一起留档。');
      return;
    }
    setBusy(true);
    setFailure('');
    setMessage('');
    try {
      await api.promoteRule(ruleId, reason);
      setPromoting(null);
      setNote('');
      setMessage('规则「' + ruleId + '」已晋级为 champion。');
      await load();
      window.dispatchEvent(new CustomEvent('smcub:rules-updated'));
    } catch (thrown) {
      setFailure(thrown instanceof Error ? thrown.message : String(thrown));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice">
        晋级必须经过人工确认：challenger 规则需要满足样本与风险门禁，并写入一条明确的确认说明，才会变成 champion。
        没有未满足门禁时会先给出晋级建议，但建议本身不改动规则；只有人写下的说明才会让规则变成 champion。
      </div>
      {message ? <div className="notice">{message}</div> : null}
      {failure ? <Empty text={failure} /> : null}
      <Panel title={'Champion 规则（' + champions.length + '）'}>
        {error ? <Empty text={'规则库读取失败：' + error} /> : null}
        {!error && champions.length === 0 ? <Empty text="还没有已晋级的规则" /> : null}
        {!error && champions.length > 0 ? <RuleTable rules={champions} /> : null}
      </Panel>
      <Panel title={'Challenger 候选（' + challengers.length + '）'}>
        {!error && challengers.length === 0 ? <Empty text="还没有候选规则" /> : null}
        {!error && challengers.length > 0 ? (
          <RuleTable
            rules={challengers}
            promoting={promoting}
            note={note}
            busy={busy}
            onNote={setNote}
            onOpen={(ruleId) => {
              setPromoting(promoting === ruleId ? null : ruleId);
              setNote('');
              setFailure('');
              setMessage('');
            }}
            onSubmit={submit}
          />
        ) : null}
      </Panel>
    </div>
  );
}

interface TableProps {
  rules: RuleRecord[];
  promoting?: string | null;
  note?: string;
  busy?: boolean;
  onNote?: (value: string) => void;
  onOpen?: (ruleId: string) => void;
  onSubmit?: (ruleId: string) => void;
}

function RuleTable({ rules, promoting, note, busy, onNote, onOpen, onSubmit }: TableProps) {
  const actionable = Boolean(onOpen);
  return (
    <div className="scroll-x">
      <table>
        <thead>
          <tr>
            <th>规则 ID</th>
            <th>标题</th>
            <th>族</th>
            <th>状态</th>
            <th className="num">样本</th>
            <th>还缺什么</th>
            <th>更新时间</th>
            {actionable ? <th>晋级</th> : null}
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => {
            const blockers = rule.promotion_blockers || [];
            const open = promoting === rule.rule_id;
            return [
              <tr key={rule.rule_id}>
                <td>{rule.rule_id}</td>
                <td>{rule.title || '—'}</td>
                <td className="muted">{rule.family || '—'}</td>
                <td>
                  {rule.status === 'champion' ? (
                    <span className="badge ok">champion</span>
                  ) : (
                    <span className="badge warn">challenger</span>
                  )}
                </td>
                <td className="num">{String((rule.metrics?.sample_count as number) ?? '—')}</td>
                <td className="muted" style={{ fontSize: 11 }}>
                  {blockers.length === 0 ? '门禁已满足' : blockers.map(blockerText).join('；')}
                </td>
                <td className="muted">{rule.updated_at}</td>
                {actionable ? (
                  <td>
                    <button className="ghost" onClick={() => onOpen?.(rule.rule_id)}>
                      {open ? '取消' : '晋级…'}
                    </button>
                  </td>
                ) : null}
              </tr>,
              open ? (
                <tr key={rule.rule_id + '-note'}>
                  <td colSpan={actionable ? 8 : 7}>
                    <div className="grid" style={{ gap: 8 }}>
                      <div className="muted" style={{ fontSize: 11 }}>
                        写清这条规则为什么可以晋级。说明会存进规则库，并作为 champion 的确认依据留档。
                        {blockers.length > 0
                          ? ' 当前仍有门禁未满足，晋级前请确认这是你判断后的决定。'
                          : ' 门禁已满足，但仍然需要这条人工确认。'}
                      </div>
                      <textarea
                        value={note}
                        onChange={(event) => onNote?.(event.target.value)}
                        rows={3}
                        placeholder="例如：样本已到 24 笔，误报率 0.12，我确认把它纳入执行规则。"
                        aria-label="晋级确认说明"
                      />
                      <div className="row">
                        <button className="primary" disabled={busy} onClick={() => onSubmit?.(rule.rule_id)}>
                          {busy ? '提交中…' : '确认晋级'}
                        </button>
                      </div>
                    </div>
                  </td>
                </tr>
              ) : null,
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}
