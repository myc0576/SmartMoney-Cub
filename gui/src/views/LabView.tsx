import { useState } from 'react';
import { PlaybookView } from './PlaybookView';
import { RulesView } from './RulesView';
import { BacktestView } from './BacktestView';

/**
 * The strategy laboratory: what the system believes, how it is being tested, and
 * what the tests say.
 *
 * These three used to be separate sidebar destinations — a playbook page, a rule
 * library, and a backtest page — which asked the trader to know that "playbook"
 * is the plan, "rules" is the governance, and "backtest" is the evidence, and to
 * walk between them by hand. They are one subject: a strategy that is declared,
 * gated, and measured. Keeping them on one page with three tabs means the
 * declared-versus-observed numbers, the rule that governs them, and the run that
 * tests them never disagree about which subject is on screen.
 *
 * The tabs are rendered eagerly rather than lazily: each view holds its own
 * fetch, and mounting only the active one would refetch on every tab switch,
 * which is slower and makes the counts jump.
 */

type LabTab = 'playbooks' | 'rules' | 'backtest';

const TABS: { key: LabTab; label: string; hint: string }[] = [
  { key: 'playbooks', label: 'Playbook', hint: '声明与观察到的战法，各自打分' },
  { key: 'rules', label: '规则库', hint: 'challenger / champion 与进化时间线' },
  { key: 'backtest', label: '回测', hint: '策略、运行与权益曲线' },
];

export function LabView({ scheme }: { scheme: 'cn' | 'intl' }) {
  const [tab, setTab] = useState<LabTab>('playbooks');
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
      <div className="muted" style={{ fontSize: 11 }}>{active.hint}</div>

      {tab === 'playbooks' ? <PlaybookView scheme={scheme} /> : null}
      {tab === 'rules' ? <RulesView /> : null}
      {tab === 'backtest' ? <BacktestView scheme={scheme} /> : null}
    </div>
  );
}

