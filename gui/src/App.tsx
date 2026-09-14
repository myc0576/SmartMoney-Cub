import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import type { Meta, Overview } from './types';
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
import { formatMoney } from './components/common';
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
// next idea, then the plumbing. `needsOverview` marks the views that render
// from the shared overview payload rather than fetching their own.
const NAV: { section: string; items: { key: TabKey; label: string; hint: string; needsOverview?: boolean }[] }[] = [
  {
    section: '复盘',
    items: [
      { key: 'overview', label: '总览', hint: '收益、回撤与待复盘', needsOverview: true },
      { key: 'tradelog', label: '交易日志', hint: '可排序、可筛选的平仓交易' },
      { key: 'calendar', label: '复盘日历', hint: '按日查看盈亏', needsOverview: true },
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
      { key: 'import', label: '数据导入', hint: '截图 / PDF / CSV' },
      { key: 'plugins', label: '插件', hint: '只读数据来源' },
      { key: 'settings', label: '设置', hint: '模型、隐私与诊断' },
    ],
  },
];

const TABS = NAV.flatMap((group) => group.items);

export function App() {
  const [tab, setTab] = useState<TabKey>('overview');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [scheme, setScheme] = useState<'cn' | 'intl'>('cn');
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
      const [metaResult, overviewResult] = await Promise.all([api.meta(), api.overview()]);
      setMeta(metaResult);
      setOverview(overviewResult);
      setScheme(metaResult.trend_color_scheme === 'intl' ? 'intl' : 'cn');
      setError('');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const toggleScheme = async () => {
    const next = scheme === 'cn' ? 'intl' : 'cn';
    setScheme(next);
    try {
      await api.updateSettings({ trend_color_scheme: next });
    } catch {
      // A colour preference that fails to persist is not worth blocking on.
    }
  };

  if (error && !overview) {
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
    portfolio_id: overview?.portfolio_id,
    round_trip_id: openTradeId || undefined,
  };

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">
          SmartMoney-Cub
          <small>本地复盘工作台 v{meta?.version || '1.0.0'}</small>
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
          {meta?.safety || 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE'}
          <div style={{ marginTop: 6 }}>本机 {meta?.store_counts?.fill_record ?? 0} 笔成交 · 全部数据离线保存</div>
        </div>
      </nav>

      <main className="main">
        <header className="topbar">
          <h1>{TABS.find((item) => item.key === tab)?.label}</h1>
          <span className="muted" style={{ fontSize: 11 }}>{TABS.find((item) => item.key === tab)?.hint}</span>
          <div className="spacer" />
          {overview ? (
            <select
              value={overview.portfolio_id}
              onChange={() => { /* single portfolio in 1.0 */ }}
              disabled
              title="1.0 使用本地默认组合"
            >
              {overview.portfolios.map((portfolio) => (
                <option key={portfolio.portfolio_id} value={portfolio.portfolio_id}>{portfolio.name}</option>
              ))}
            </select>
          ) : null}
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
          {overview && summaryChip(overview)}
          <button className="ghost" onClick={() => setAssistantOpen((prev) => !prev)}>
            {assistantOpen ? '收起助手' : '打开助手'}
          </button>
        </header>

        <div className={'content' + (assistantOpen ? ' with-assistant' : '')}>
          <div className="page">
            {tab === 'overview' && overview ? (
              <OverviewView
                data={overview}
                scheme={scheme}
                onOpenTrade={(id) => {
                  if (id === '__import__') setTab('import');
                  else setOpenTradeId(id);
                }}
              />
            ) : null}
            {tab === 'trades' ? <TradesView scheme={scheme} onOpenTrade={setOpenTradeId} /> : null}
            {tab === 'tradelog' ? <TradeLogView scheme={scheme} /> : null}
            {tab === 'calendar' && overview ? (
              <CalendarView scheme={scheme} initial={{ year: overview.year, month: overview.month }} />
            ) : null}
            {tab === 'reports' ? <ReportsView scheme={scheme} /> : null}
            {tab === 'analytics' ? <AnalyticsView scheme={scheme} /> : null}
            {tab === 'playbooks' ? <PlaybookView scheme={scheme} /> : null}
            {tab === 'backtest' ? <BacktestView scheme={scheme} /> : null}
            {tab === 'replay' ? <ReplayView scheme={scheme} /> : null}
            {tab === 'propfirm' ? <PropFirmView scheme={scheme} /> : null}
            {tab === 'rules' ? <RulesView /> : null}
            {tab === 'import' ? <ImportView onImported={() => void load()} /> : null}
            {tab === 'plugins' ? <PluginsView /> : null}
            {tab === 'settings' ? <SettingsView meta={meta} onMetaChange={() => void load()} /> : null}
          </div>

          {assistantOpen ? (
            <AssistantPanel
              meta={meta}
              context={assistantContext}
              onMetaReload={() => void load()}
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

function summaryChip(overview: Overview) {
  const summary = overview.summary;
  return (
    <span className="muted" style={{ fontSize: 11 }}>
      {/* `total_net_pnl` is a sum of floats, so it arrives as something like
          31253.399999999994. It is formatted here rather than interpolated raw,
          which is what the tables already do. */}
      {summary.trade_count} 笔 · 胜率 {summary.win_rate}% · 净盈亏 {formatMoney(summary.total_net_pnl)}
    </span>
  );
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
