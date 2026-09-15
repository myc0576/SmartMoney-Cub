import { useCallback, useEffect, useMemo, useState } from 'react';
import { trader } from '../api';
import type { TraderAccount, TraderSummary } from '../types';
import { Banner, Empty, Kpi, Panel, formatCost, formatMoney, toneOf } from '../components/common';

/**
 * Accounts and evaluation rules.
 *
 * A prop-firm evaluation is a set of arithmetic gates: a profit target and a
 * drawdown floor, both stated against the account's own starting balance. The
 * gate thresholds are ratios this page fixes and states openly; the trader's
 * own figures come from the account row and that account's summary, so the page
 * cannot invent a target the trader did not set.
 *
 * The gates are presented as trailing thresholds, never as pass/fail advice.
 * Nothing here recommends a position, a direction, or a size.
 */

interface StageRule {
  key: string;
  label: string;
  /** Fraction of the initial balance. */
  target: number;
  /** Trailing drawdown as a fraction of the initial balance. */
  drawdown: number;
  note: string;
}

const STAGES: StageRule[] = [
  { key: 'evaluation', label: '第一阶段 · 评估', target: 0.08, drawdown: 0.06, note: '达标后进入验证阶段' },
  { key: 'verification', label: '第二阶段 · 验证', target: 0.05, drawdown: 0.06, note: '达标后进入资金账户' },
  { key: 'funded', label: '资金账户', target: 0.0, drawdown: 0.05, note: '没有盈利目标，只有回撤限制' },
];

export function PropFirmView({ scheme }: { scheme: 'cn' | 'intl' }) {
  const [accounts, setAccounts] = useState<TraderAccount[]>([]);
  const [summary, setSummary] = useState<TraderSummary | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [draft, setDraft] = useState({ name: '', broker: '', currency: 'USD', initial_balance: '50000' });

  const loadAccounts = useCallback(async () => {
    try {
      const accountResult = await trader.accounts();
      const list = Array.isArray(accountResult.accounts) ? accountResult.accounts : [];
      setAccounts(list);
      setSelected((current) => (current && list.some((item) => item.account_id === current) ? current : list[0]?.account_id ?? null));
      setError('');
    } catch (failure) {
      setAccounts([]);
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, []);

  useEffect(() => { void loadAccounts(); }, [loadAccounts]);

  // The summary is read per account, not once for the whole journal. A gate is
  // a statement about one account's balance, so attributing the journal-wide
  // net P&L to whichever account happens to be selected would understate one
  // account and overstate the next.
  useEffect(() => {
    if (!selected) {
      setSummary(null);
      return;
    }
    let live = true;
    void trader.summary({ account_id: selected })
      .then((result) => { if (live) setSummary(result); })
      .catch(() => { if (live) setSummary(null); });
    return () => { live = false; };
  }, [selected]);

  const current = accounts.find((account) => account.account_id === selected) || null;

  const netPnl = summary ? summary.total_net_pnl : 0;
  const drawdown = summary ? Math.abs(summary.max_drawdown) : 0;
  const balance = current ? current.initial_balance + netPnl : 0;

  const progress = useMemo(() => {
    if (!current) return [];
    const base = current.initial_balance || 0;
    return STAGES.map((stage) => {
      const targetAmount = base * stage.target;
      const floorAmount = base * stage.drawdown;
      const targetHit = stage.target === 0 ? null : netPnl >= targetAmount;
      const floorBreached = drawdown >= floorAmount;
      return { stage, targetAmount, floorAmount, targetHit, floorBreached };
    });
  }, [current, netPnl, drawdown]);

  const submit = async () => {
    const name = draft.name.trim();
    if (!name) {
      setError('账户需要一个名字。');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const created = await trader.createAccount({
        name,
        broker: draft.broker.trim(),
        currency: draft.currency.trim() || 'USD',
        initial_balance: Number(draft.initial_balance) || 0,
      });
      setStatus('已新建账户「' + name + '」。');
      setDraft({ name: '', broker: '', currency: draft.currency, initial_balance: draft.initial_balance });
      setCreating(false);
      await loadAccounts();
      if (created.account) setSelected(created.account.account_id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid" style={{ gap: 14 }}>
      <div className="notice">
        这里的评估规则是常见的自营账户门槛（目标收益与回溯回撤），用来对照你自己的账户状态。
        它不构成建议，也不会因为「接近达标」而提示加仓或提高风险。账户规则以你实际签约的条款为准。
      </div>

      {error ? <Banner>{error}</Banner> : null}
      {status ? <div className="muted" style={{ fontSize: 11 }}>{status}</div> : null}

      <Panel
        title={'账户（' + accounts.length + '）'}
        actions={<button className="ghost" onClick={() => { setCreating((previous) => !previous); setError(''); }}>{creating ? '取消新增' : '新建账户'}</button>}
      >
        {creating ? (
          <div className="row" style={{ marginBottom: 14, alignItems: 'flex-end' }}>
            <div className="field">
              <label>名称</label>
              <input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="例如：Apex 50K" />
            </div>
            <div className="field">
              <label>券商 / 平台</label>
              <input value={draft.broker} onChange={(event) => setDraft({ ...draft, broker: event.target.value })} />
            </div>
            <div className="field">
              <label>币种</label>
              <input value={draft.currency} onChange={(event) => setDraft({ ...draft, currency: event.target.value })} style={{ width: 80 }} />
            </div>
            <div className="field">
              <label>初始资金</label>
              <input value={draft.initial_balance} onChange={(event) => setDraft({ ...draft, initial_balance: event.target.value })} style={{ width: 120 }} inputMode="decimal" />
            </div>
            <button className="primary" onClick={() => void submit()} disabled={busy}>{busy ? '保存中…' : '保存'}</button>
          </div>
        ) : null}

        {accounts.length === 0 ? (
          <Empty text="还没有账户。用「新建账户」登记一个，评估门槛会按它的初始资金计算。" />
        ) : (
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>名称</th><th>券商</th><th>币种</th>
                  <th className="num">初始资金</th><th>状态</th>
                </tr>
              </thead>
              <tbody>
                {/* The list route carries balances and descriptions, not per-account
                    performance: the outcome numbers are fetched for one account at a
                    time and shown below, so this table does not repeat one account's
                    P&L on every row. */}
                {accounts.map((account) => (
                  <tr
                    key={account.account_id}
                    onClick={() => setSelected(account.account_id)}
                    style={{ background: account.account_id === selected ? 'var(--panel-2)' : undefined }}
                  >
                    <td>{account.name || account.account_id}</td>
                    <td className="muted">{account.broker || '—'}</td>
                    <td className="muted">{account.currency || '—'}</td>
                    <td className="num">{formatCost(account.initial_balance)}</td>
                    <td className="muted">{account.account_id === selected ? '正在查看' : '点击查看'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {current ? (
        <>
          <div className="grid kpi">
            <Kpi label="初始资金" value={formatCost(current.initial_balance)} note={current.currency} />
            <Kpi label="当前权益" value={formatCost(balance)} tone={toneOf(balance - current.initial_balance, scheme)} note="初始资金 + 该账户已实现净盈亏" />
            <Kpi label="已实现净盈亏" value={formatMoney(netPnl)} tone={toneOf(netPnl, scheme)} note={summary ? summary.trade_count + ' 笔平仓' : '该账户还没有可用统计'} />
            <Kpi label="当前回撤" value={formatMoney(-drawdown)} tone={toneOf(-drawdown, scheme)} note={summary ? '按已平仓累计的峰值回落' : '该账户还没有可用统计'} />
          </div>

          <Panel title={'评估门槛 · ' + current.name}>
            <div className="grid" style={{ gap: 12 }}>
              {progress.map(({ stage, targetAmount, floorAmount, targetHit, floorBreached }) => (
                <div key={stage.key} className="stage-row">
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <strong style={{ fontSize: 12.5 }}>{stage.label}</strong>
                    <span className="muted" style={{ fontSize: 11 }}>{stage.note}</span>
                  </div>
                  <div className="grid split" style={{ marginTop: 8, gap: 12 }}>
                    <div>
                      <div className="kpi-label">目标收益</div>
                      {stage.target === 0 ? (
                        <div className="muted" style={{ marginTop: 4 }}>无目标，只需守住回撤上限</div>
                      ) : (
                        <>
                          <div className="meter"><span style={{ width: meterWidth(netPnl, targetAmount) + '%' }} /></div>
                          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                            {formatMoney(netPnl)} / {formatCost(targetAmount)}
                            {targetHit === true ? ' · 已达标' : targetHit === false ? ' · 未达标' : ''}
                          </div>
                        </>
                      )}
                    </div>
                    <div>
                      <div className="kpi-label">回撤上限</div>
                      <div className="meter loss"><span style={{ width: meterWidth(drawdown, floorAmount) + '%' }} /></div>
                      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                        {formatCost(drawdown)} / {formatCost(floorAmount)}
                        {floorBreached ? ' · 已超过上限' : ' · 在上限内'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 12 }}>
              门槛按初始资金的比例计算：目标 {Math.round(STAGES[0].target * 100)}% / 验证 {Math.round(STAGES[1].target * 100)}%，
              回撤上限 {Math.round(STAGES[0].drawdown * 100)}%。数字只用于对照，达标与否由你与平台的账目决定。
            </div>
          </Panel>
        </>
      ) : null}
    </div>
  );
}

/** Progress against a threshold, clamped to a readable 0-100 range. */
function meterWidth(value: number, threshold: number): number {
  if (!threshold || threshold <= 0) return 0;
  const ratio = Math.abs(value) / threshold;
  if (!Number.isFinite(ratio)) return 0;
  return Math.max(2, Math.min(100, ratio * 100));
}
