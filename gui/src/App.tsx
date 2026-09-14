import { useCallback, useEffect, useState } from 'react';
import { api, trader } from './api';
import type { Issue, Meta, OpenPosition, TradeLogEntry, TraderMeta, TraderSummary } from './types';
import { AssistantPanel } from './components/AssistantPanel';
import { OverviewView } from './views/OverviewView';
import { TradesView } from './views/TradesView';
import { CalendarView } from './views/CalendarView';
import { AnalyticsView } from './views/AnalyticsView';
import { RulesView } from './views/RulesView';
import { ImportView } from './views/ImportView';
import { SettingsView } from './views/SettingsView';
import { PluginsView } from './views/PluginsView';
import { TradeDrawer } from './views/TradeDrawer';
import { formatMoney, toneOf } from './components/common';
import { TradeLogView } from './views/TradeLogView';
import { ReportsView } from './views/ReportsView';
import { PlaybookView } from './views/PlaybookView';
import { BacktestView } from './views/BacktestView';
import { ReplayView } from './views/ReplayView';
import { PropFirmView } from './views/PropFirmView';

// A-plan layout: navigation and portfolio switch on the left, the working page
// in the middle, and the review assistant docked on the right.

type TabKey =
  | 'overview' | 'tradelog' | 'calendar' | 'reports' | 'analytics'
  | 'playbooks' | 'backtest' | 'replay' | 'propfirm'
  | 'trades' | 'rules' | 'import' | 'plugins' | 'settings';

// The sidebar is grouped by what a trader is doing, not by which subsystem
// answers the call: review the journal, study what it says, plan and test the
// next idea, then the plumbing.
const NAV: { section: string; items: { key: TabKey; label: string; hint: string }[] }[] = [
  {
    section: '复盘',
    items: [
      { key: 'overview', label: '总览', hint: '收益、回撤与待复盘' },
      { key: 'tradelog', label: '交易日志', hint: '可排序、可筛选的平仓交易' },
      { key: 'calendar', label: '复盘日历', hint: '按日查看盈亏' },
    ],
  },
  {
    section: '研究',
    items: [
      { key: 'reports', label: '报告', hint: '绩效、风险、标的与日时段' },
      { key: 'analytics', label: '绩效分析', hint: '归因与样本量' },
      { key: 'playbooks', label: 'Playbook', hint: '计划、规则与单计划盈亏' },
    ],
  },
  {
    section: '测试',
    items: [
      { key: 'backtest', label: '回测', hint: 'JSON 策略、运行与权益曲线' },
      { key: 'replay', label: 'K 线回放', hint: '逐根推进并标出成交' },
      { key: 'propfirm', label: '自营账户', hint: '账户与多阶段评估门槛' },
    ],
  },
  {
    section: '系统',
    items: [
      { key: 'trades', label: '成交台账', hint: '已确认的平仓交易' },
      { key: 'rules', label: '规则库', hint: 'challenger / champion' },
      { key: 'import', label: '数据导入', hint: 'Excel / CSV / PDF / 截图' },
      { key: 'plugins', label: '插件', hint: '只读数据来源' },
      { key: 'settings', label: '设置', hint: '模型、隐私与诊断' },
    ],
  },
];

const TABS = NAV.flatMap((group) => group.items);

// How many recent closes the shell asks for, so the overview panel has
// newest-first rows to choose from. The routes build round trips inside the
// page they return and fills and round trips are not one to one, so the request
// is larger than the panel it feeds.
const RECENT_FETCH = 24;

export function App() {
  const [tab, setTab] = useState<TabKey>('overview');
  // The workbench meta still feeds the review assistant and the settings page,
  // which are workbench features. It no longer feeds the shell.
  const [meta, setMeta] = useState<Meta | null>(null);
  // The shell reads the trader product: the journal's own metrics and the rows
  // behind them, from the same store the journal views read. That is what makes
  // one import through /api/trader/trades/import fill in the whole product.
  const [traderMeta, setTraderMeta] = useState<TraderMeta | null>(null);
  const [summary, setSummary] = useState<TraderSummary | null>(null);
  const [recent, setRecent] = useState<TradeLogEntry[]>([]);
  const [openPositions, setOpenPositions] = useState<OpenPosition[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [ledgerStatus, setLedgerStatus] = useState('ok');
  const [scheme, setScheme] = useState<'cn' | 'intl'>(() => readStoredScheme());
  const [theme, setTheme] = useState<'light' | 'dark'>(() => readStoredTheme());
  const [error, setError] = useState('');
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [openTradeId, setOpenTradeId] = useState<string | null>(null);

  // The theme lives on the document element, not in a wrapper class, so the
  // tokens resolve for portalled and fixed-position surfaces too (the trade
  // drawer and the model picker both render outside this tree).
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try {
      window.localStorage.setItem('smcub.theme', theme);
    } catch {
      // A blocked localStorage is not a reason to fail a theme switch.
    }
  }, [theme]);

  const load = useCallback(async () => {
    try {
      const [metaResult, summaryResult, tradesResult] = await Promise.all([
        trader.meta(),
        trader.summary(),
        trader.trades({ limit: RECENT_FETCH }),
      ]);
      setTraderMeta(metaResult);
      setSummary(summaryResult);
      setRecent(newestFirst(tradesResult.trades));
      setOpenPositions(tradesResult.open_positions ?? []);
      setIssues(tradesResult.issues ?? []);
      setLedgerStatus(tradesResult.ledger_status ?? 'ok');
      setError('');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, []);

  // The workbench meta is loaded separately from the journal. It feeds the
  // assistant's model seat and the settings page, and a journal that loads
  // without it still shows every number the shell owns, so its failure is not
  // reported as a failure of this page.
  const loadMeta = useCallback(async () => {
    try {
      setMeta(await api.meta());
    } catch {
      setMeta(null);
    }
  }, []);

  useEffect(() => { void load(); void loadMeta(); }, [load, loadMeta]);

  const toggleScheme = () => {
    const next = scheme === 'cn' ? 'intl' : 'cn';
    setScheme(next);
    try {
      window.localStorage.setItem('smcub.scheme', next);
    } catch {
      // A colour preference that fails to persist is not worth blocking on.
    }
  };

  if (error && !summary) {
    return (
      <div className="shell">
        <div style={{ margin: 'auto', textAlign: 'center' }}>
          <div style={{ marginBottom: 10 }}>无法连接本地复盘服务</div>
          <div className="muted" style={{ marginBottom: 12, fontSize: 11 }}>{error}</div>
          <button className="primary" onClick={() => void load()}>重试</button>
        </div>
      </div>
    );
  }

  const assistantContext = {
    round_trip_id: openTradeId || undefined,
  };

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">
          SmartMoney-Cub
          <small>本地复盘工作台 v{traderMeta?.version || '1.0.0'}</small>
        </div>
        {NAV.map((group) => (
          <div className="nav-group" key={group.section}>
            <div className="nav-section">{group.section}</div>
            {group.items.map((item) => (
              <button
                key={item.key}
                className={'nav-item' + (tab === item.key ? ' active' : '')}
                onClick={() => setTab(item.key)}
                title={item.hint}
              >
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        ))}
        <div className="sidebar-footer">
          {traderMeta?.safety || summary?.safety || 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE'}
          <div style={{ marginTop: 6 }}>本机 {summary?.counts?.fills ?? recent.length} 笔成交 · 全部数据离线保存</div>
        </div>
      </nav>

      <main className="main">
        <header className="topbar">
          <h1>{TABS.find((item) => item.key === tab)?.label}</h1>
          <span className="muted" style={{ fontSize: 11 }}>{TABS.find((item) => item.key === tab)?.hint}</span>
          <div className="spacer" />
          {/* The contract's markets and execution side is single-purpose, so
              there is one journal per install and nothing to switch between.
              The label names that default instead of offering a control whose
              only effect would be to look interactive. */}
          <span className="muted" style={{ fontSize: 11 }} title={traderMeta?.tenant?.display_name || '本地账本'}>
            {traderMeta?.tenant?.display_name || '本地账本'} · 单账本
          </span>
          <button className="ghost" onClick={toggleScheme} title="切换涨跌配色">
            {scheme === 'cn' ? '红涨绿跌' : '绿涨红跌'}
          </button>
          <button
            className="ghost"
            onClick={() => setTheme((previous) => (previous === 'dark' ? 'light' : 'dark'))}
            title="切换明暗主题"
          >
            {theme === 'dark' ? '深色' : '浅色'}
          </button>
          {summary && summaryChip(summary, scheme)}
          <button className="ghost" onClick={() => setAssistantOpen((prev) => !prev)}>
            {assistantOpen ? '收起助手' : '打开助手'}
          </button>
        </header>

        <div className={'content' + (assistantOpen ? ' with-assistant' : '')}>
          <div className="page">
            {tab === 'overview' && summary ? (
              <OverviewView
                summary={summary}
                recent={recent}
                openPositions={openPositions}
                issues={issues}
                ledgerStatus={ledgerStatus}
                scheme={scheme}
                onGoToImport={() => setTab('import')}
                onOpenLog={() => setTab('tradelog')}
              />
            ) : null}
            {tab === 'trades' ? <TradesView scheme={scheme} onOpenTrade={setOpenTradeId} /> : null}
            {tab === 'tradelog' ? <TradeLogView scheme={scheme} /> : null}
            {tab === 'calendar' ? <CalendarView scheme={scheme} initial={thisMonth()} /> : null}
            {tab === 'reports' ? <ReportsView scheme={scheme} /> : null}
            {tab === 'analytics' ? <AnalyticsView scheme={scheme} /> : null}
            {tab === 'playbooks' ? <PlaybookView scheme={scheme} /> : null}
            {tab === 'backtest' ? <BacktestView scheme={scheme} /> : null}
            {tab === 'replay' ? <ReplayView scheme={scheme} /> : null}
            {tab === 'propfirm' ? <PropFirmView scheme={scheme} /> : null}
            {tab === 'rules' ? <RulesView /> : null}
            {tab === 'import' ? <ImportView onImported={() => void load()} /> : null}
            {tab === 'plugins' ? <PluginsView /> : null}
            {tab === 'settings' ? <SettingsView meta={meta} onMetaChange={() => void loadMeta()} /> : null}
          </div>

          {assistantOpen ? (
            <AssistantPanel
              meta={meta}
              context={assistantContext}
              onMetaReload={() => void loadMeta()}
            />
          ) : null}
        </div>
      </main>

      {openTradeId ? (
        <TradeDrawer tradeId={openTradeId} scheme={scheme} onClose={() => setOpenTradeId(null)} />
      ) : null}
    </div>
  );
}

function summaryChip(summary: TraderSummary, scheme: 'cn' | 'intl') {
  if (summary.trade_count === 0) return null;
  return (
    <span className="muted" style={{ fontSize: 11 }}>
      {/* `total_net_pnl` is a sum of floats, so it arrives as something like
          31253.399999999994. It is formatted here rather than interpolated raw,
          which is what the tables already do. */}
      {summary.trade_count} 笔 · 胜率 {summary.win_rate}% · 净盈亏{' '}
      <span className={toneOf(summary.total_net_pnl, scheme)}>{formatMoney(summary.total_net_pnl)}</span>
    </span>
  );
}

/** Newest close first. The list route orders fills newest first; a row that
 *  carries no exit time sorts last rather than jumping to the top. */
function newestFirst(trades: TradeLogEntry[]): TradeLogEntry[] {
  return [...trades].sort((left, right) =>
    String(right.exit_time || '').localeCompare(String(left.exit_time || '')),
  );
}

/** The calendar opens on the current month. The trader payload carries no
 *  selected month, so the shell no longer borrows one from the workbench. */
function thisMonth(): { year: number; month: number } {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

/** The colour convention is the domestic default; a stored choice wins. Reading
 *  it lazily keeps the initializer pure and safe when storage is blocked. */
function readStoredScheme(): 'cn' | 'intl' {
  try {
    return window.localStorage.getItem('smcub.scheme') === 'intl' ? 'intl' : 'cn';
  } catch {
    return 'cn';
  }
}

/** Dark is the product's default; a stored choice wins. Reading the value
 *  lazily keeps the initializer pure and safe when storage is blocked. */
function readStoredTheme(): 'light' | 'dark' {
  try {
    return window.localStorage.getItem('smcub.theme') === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}
