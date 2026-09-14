import { useEffect, useState } from 'react';
import { api } from '../api';
import type { RuleRecord } from '../types';
import { Empty, Panel } from '../components/common';

export function RulesView() {
  const [rules, setRules] = useState<RuleRecord[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    // A failed read is reported as a failed read. The rule registry belongs to the
    // local review workbench, so on a host that closes that surface the answer is
    // "not available here" rather than "no rules exist" -- different claims.
    void api
      .rules()
      .then((result) => setRules(result.rules))
      .catch((failure) => setError(failure instanceof Error ? failure.message : String(failure)));
  }, []);

  const champions = rules.filter((rule) => rule.status === 'champion');
  const challengers = rules.filter((rule) => rule.status === 'challenger');

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice">
        晋级必须经过人工确认：challenger 规则需要满足样本与风险门禁，并写入一条明确的确认说明，才会变成 champion。
      </div>
      <Panel title={'Champion 规则（' + champions.length + '）'}>
        {error ? <Empty text={'规则库读取失败：' + error} /> : null}
        {!error && champions.length === 0 ? <Empty text="还没有已晋级的规则" /> : null}
        {!error && champions.length > 0 ? <RuleTable rules={champions} /> : null}
      </Panel>
      <Panel title={'Challenger 候选（' + challengers.length + '）'}>
        {!error && challengers.length === 0 ? <Empty text="还没有候选规则" /> : null}
        {!error && challengers.length > 0 ? <RuleTable rules={challengers} /> : null}
      </Panel>
    </div>
  );
}

function RuleTable({ rules }: { rules: RuleRecord[] }) {
  return (
    <div className="scroll-x">
      <table>
        <thead><tr><th>规则 ID</th><th>标题</th><th>族</th><th>状态</th><th className="num">样本</th><th>更新时间</th></tr></thead>
        <tbody>
          {rules.map((rule) => (
            <tr key={rule.rule_id}>
              <td>{rule.rule_id}</td>
              <td>{rule.title || '—'}</td>
              <td className="muted">{rule.family || '—'}</td>
              <td>{rule.status === 'champion' ? <span className="badge ok">champion</span> : <span className="badge warn">challenger</span>}</td>
              <td className="num">{String((rule.metrics?.sample_count as number) ?? '—')}</td>
              <td className="muted">{rule.updated_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
