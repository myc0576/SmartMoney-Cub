import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { api, trader } from './api';
import { BRAND_MARK_SRC } from './assets/brand';
import type { Issue, Meta, OpenPosition, TradeLogEntry, TraderMeta, TraderSummary } from './types';
import { AssistantPanel } from './components/AssistantPanel';
import { OverviewView } from './views/OverviewView';
const CalendarView = lazy(() => import('./views/CalendarView').then(module => ({ default: module.CalendarView })));
const ImportView = lazy(() => import('./views/ImportView').then(module => ({ default: module.ImportView })));
const SettingsView = lazy(() => import('./views/SettingsView').then(module => ({ default: module.SettingsView })));
import { TradeDrawer } from './views/TradeDrawer';
const TradeLogView = lazy(() => import('./views/TradeLogView').then(module => ({ default: module.TradeLogView })));
const ReportsView = lazy(() => import('./views/ReportsView').then(module => ({ default: module.ReportsView })));
const LabView = lazy(() => import('./views/LabView').then(module => ({ default: module.LabView })));
const DrillView = lazy(() => import('./views/DrillView').then(module => ({ default: module.DrillView })));
const InsightView = lazy(() => import('./views/InsightView').then(module => ({ default: module.InsightView })));
const ConnectionsView = lazy(() => import('./views/ConnectionsView').then(module => ({ default: module.ConnectionsView })));
import { PreferencesView } from './views/PreferencesView';
import { setTraderAccountScope } from './api';
import { LOCALE_LABELS, LOCALES, useI18n } from './i18n';
import type { MessageKey } from './i18n';

// A-plan layout: navigation and portfolio switch on the left, the working page
// in the middle, and the review assistant docked on the right.

type TabKey =
  | 'overview' | 'tradelog' | 'calendar' | 'reports' | 'insight'
  | 'lab' | 'drill' | 'connections' | 'import' | 'settings';

// The sidebar is grouped by what a trader is doing, not by which subsystem
// answers the call: review the journal, study what it says, then plan and test
// the next idea.
//
// Three pairs that used to be separate destinations now live together because
// they read the same rows: the closed-trade log and the unpaired positions are
// one page, the reports and the attribution view are one page, and the playbook,
// rules, and backtest are one laboratory. Import became a button on the trade
// page rather than a destination, because a trader goes there to fix a ledger
// and not to browse. Settings sits below the groups: it is plumbing, not a place
// a review happens.
type NavItem = { key: TabKey; labelKey: MessageKey; hintKey: MessageKey };
const NAV_KEYS: { sectionKey: MessageKey; items: NavItem[] }[] = [
  {
    sectionKey: 'nav.review',
    items: [
      { key: 'overview', labelKey: 'nav.overview', hintKey: 'hint.overview' },
      { key: 'tradelog', labelKey: 'nav.trades', hintKey: 'hint.trades' },
      { key: 'calendar', labelKey: 'nav.calendar', hintKey: 'hint.calendar' },
    ],
  },
  {
    sectionKey: 'nav.research',
    items: [
      { key: 'reports', labelKey: 'nav.reports', hintKey: 'hint.reports' },
      { key: 'insight', labelKey: 'nav.insight', hintKey: 'hint.insight' },
    ],
  },
  {
    sectionKey: 'nav.strategy',
    items: [
      { key: 'lab', labelKey: 'nav.lab', hintKey: 'hint.lab' },
      { key: 'drill', labelKey: 'nav.drill', hintKey: 'hint.drill' },
    ],
  },
  { sectionKey: 'nav.research', items: [{ key: 'connections', labelKey: 'nav.connections', hintKey: 'hint.connections' }] },
];

// Settings renders at the foot of the sidebar from its own entry rather than as
// a member of a working group.
const SETTINGS_ITEM: NavItem = {
  key: 'settings', labelKey: 'nav.settings', hintKey: 'hint.settings',
};

const TABS = NAV_KEYS.flatMap((group) => group.items);

// Import is reachable as a page without being a sidebar destination.
const IMPORT_ITEM: NavItem = { key: 'import', labelKey: 'nav.import', hintKey: 'hint.import' };
const ALL_NAV_ITEMS: NavItem[] = [...TABS, SETTINGS_ITEM, IMPORT_ITEM];

// How many recent closes the shell asks for, so the overview panel has
// newest-first rows to choose from. The routes build round trips inside the
// page they return and fills and round trips are not one to one, so the request
// is larger than the panel it feeds.
const RECENT_FETCH = 24;

export function App() {
  const [tab, setTab] = useState<TabKey>('overview');
  const { locale, setLocale, t } = useI18n();
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
  const [reviewTradeId, setReviewTradeId] = useState<string | null>(null);
  const [accountScope, setAccountScope] = useState('');
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [accounts, setAccounts] = useState<{ account_id: string; name: string; currency: string }[]>([]);
  const [syncing, setSyncing] = useState(false);
  const loadGeneration = useRef(0);

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

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  useEffect(() => {
    void trader.accounts().then((result) => {
      const next = (result.accounts || []).map((item) => ({ account_id: item.account_id, name: item.name, currency: item.currency }));
      setAccounts(next);
      const stored = readStoredAccount();
      const active = stored && next.some((item) => item.account_id === stored) ? stored : '';
      setAccountScope(active);
      setTraderAccountScope(active);
      if (active) { loadGeneration.current += 1; setSummary(null); setRecent([]); setOpenPositions([]); }
    }).catch(() => setAccounts([]));
  }, []);

  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    try {
      const [metaResult, summaryResult, tradesResult] = await Promise.all([
        trader.meta(),
        trader.summary(),
        trader.trades({ limit: RECENT_FETCH }),
      ]);
      if (generation !== loadGeneration.current) return;
      setTraderMeta(metaResult);
      setSummary(summaryResult);
      setRecent(newestFirst(tradesResult.trades));
      setOpenPositions(tradesResult.open_positions ?? []);
      setIssues(tradesResult.issues ?? []);
      setLedgerStatus(tradesResult.ledger_status ?? 'ok');
      setError('');
    } catch (failure) {
      if (generation !== loadGeneration.current) return;
      setError(failure instanceof Error ? failure.message : String(failure));
    }
  }, [accountScope]);

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

  const changeAccountScope = (value: string) => {
    loadGeneration.current += 1;
    setSummary(null); setRecent([]); setOpenPositions([]); setOpenTradeId(null);
    setAccountScope(value);
    setTraderAccountScope(value);
    try { value ? window.localStorage.setItem('smcub.account', value) : window.localStorage.removeItem('smcub.account'); } catch { /* optional preference */ }
  };

  const syncLedger = async () => {
    setSyncing(true);
    try { await load(); } finally { setSyncing(false); }
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

  // What the assistant is told about where the trader is standing. The page and
  // the open round trip are the two things most questions silently depend on
  // ("this trade", "this month"), and both are cheap to send. It is a snapshot,
  // not a subscription: the panel records it when a session starts, exactly as it
  // already recorded the round trip id.
  const assistantContext = {
    page: tab,
    page_label: t(ALL_NAV_ITEMS.find((item) => item.key === tab)?.labelKey || 'nav.overview'),
    round_trip_id: openTradeId || undefined,
  };

  return (
    <div className="shell">
      <nav className="sidebar">
        <div className="brand">
          {/* The mark sits beside the name rather than replacing it: the name
              stays real text so it keeps a real font and stays selectable. The
              image carries nothing the name does not, so alt="" keeps a screen
              reader from reading the brand out twice. */}
          <div className="brand-head">
            <img className="brand-mark" src={BRAND_MARK_SRC} alt="" width={26} height={26} />
            <span className="brand-name">SmartMoney-Cub</span>
          </div>
          <small>本地复盘工作台 v{traderMeta?.version || '1.0.0'}</small>
        </div>
        {NAV_KEYS.map((group) => (
          <div className="nav-group" key={group.items[0]?.key || group.sectionKey}>
            <div className="nav-section">{t(group.sectionKey)}</div>
            {group.items.map((item) => (
              <button
                key={item.key}
                className={'nav-item' + (tab === item.key ? ' active' : '')}
                onClick={() => setTab(item.key)}
                title={t(item.hintKey)}
              >
                <span>{t(item.labelKey)}</span>
              </button>
            ))}
          </div>
        ))}
        <div className="sidebar-locale">
          <label htmlFor="sidebar-locale-select">{t('prefs.locale')}</label>
          <select id="sidebar-locale-select" value={locale} onChange={(event) => setLocale(event.target.value as typeof locale)}>
            {LOCALES.map((item) => (
              <option key={item} value={item}>{LOCALE_LABELS[item]}</option>
            ))}
          </select>
        </div>
        {/* Settings is plumbing rather than a working area, so it renders at the
            foot of the sidebar instead of inside a working group. */}
        <div className="nav-group nav-group-foot">
          <button
            className={'nav-item' + (tab === SETTINGS_ITEM.key ? ' active' : '')}
            onClick={() => setTab(SETTINGS_ITEM.key)}
            title={t(SETTINGS_ITEM.hintKey)}
          >
              <span>{t('nav.settings')}</span>
          </button>
        </div>
      </nav>

      <main className="main">
        <header className="topbar">
          <h1>{t(ALL_NAV_ITEMS.find((item) => item.key === tab)?.labelKey || 'nav.overview')}</h1>
          <span className="muted" style={{ fontSize: 11 }}>{t(ALL_NAV_ITEMS.find((item) => item.key === tab)?.hintKey || 'hint.overview')}</span>
          <div className="spacer" />
          {/* The contract's markets and execution side is single-purpose, so
              there is one journal per install and nothing to switch between.
              The label names that default instead of offering a control whose
              only effect would be to look interactive. */}
          <label className="topbar-scope"><span className="muted">{t('top.account')}</span><select value={accountScope} onChange={(event) => changeAccountScope(event.target.value)}><option value="">{t('top.allAccounts')}</option>{accounts.map((account) => <option key={account.account_id} value={account.account_id}>{account.name || account.account_id} · {account.currency}</option>)}</select></label>
          <button className="ghost" onClick={() => void syncLedger()} disabled={syncing} title={t('top.sync')}>{syncing ? '…' : t('top.sync')}</button>
          {/* Import is a ledger fix rather than a destination: it sits with the
              other page actions, and the empty states that need it link here. */}
          <button className="ghost" onClick={() => setTab('import')} title={t('top.import')}>{t('top.import')}</button>
          <button className="ghost" onClick={() => setPreferencesOpen(true)} title={t('top.preferences')}>{t('top.preferences')}</button>
          <button className="ghost" onClick={() => setAssistantOpen((prev) => !prev)}>
            {assistantOpen ? t('top.assistant.close') : t('top.assistant.open')}
          </button>
        </header>

        <div className={'content' + (assistantOpen ? ' with-assistant' : '')}>
          <div className="page" key={accountScope}>
            <Suspense fallback={<p role="status">{t('state.loading')}</p>}>
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
                onOpenInsight={() => setTab('insight')}
                onOpenAssistant={() => setAssistantOpen(true)}
                onOpenTrade={setOpenTradeId}
              />
            ) : null}
            {/* The closed log and the unpaired positions are one page: both read
                /api/trader/trades, and a trader looking at a round trip wants the
                still-open side of the book in the same glance. */}
            {tab === 'tradelog' ? (
              <TradeLogView scheme={scheme} onOpenTrade={setOpenTradeId} onGoToImport={() => setTab('import')} />
            ) : null}
            {tab === 'calendar' ? <CalendarView scheme={scheme} initial={thisMonth()} /> : null}
            {tab === 'reports' ? <ReportsView scheme={scheme} /> : null}
            {tab === 'insight' ? <InsightView scheme={scheme} onOpenTrade={setOpenTradeId} /> : null}
            {tab === 'lab' ? <LabView scheme={scheme} /> : null}
            {tab === 'drill' ? <DrillView scheme={scheme} /> : null}
            {tab === 'connections' ? <ConnectionsView /> : null}
            {tab === 'import' ? <ImportView onImported={() => void load()} /> : null}
            {tab === 'settings' ? (
              <SettingsView
                meta={meta}
                onMetaChange={() => void loadMeta()}
                scheme={scheme}
                theme={theme}
                onToggleScheme={toggleScheme}
                onToggleTheme={() => setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))}
              />
            ) : null}
            </Suspense>
          </div>

          {assistantOpen ? (
            <AssistantPanel
              meta={meta}
              context={assistantContext}
              onMetaReload={() => void loadMeta()}
              reviewTradeId={reviewTradeId}
              onReviewTradeHandled={() => setReviewTradeId(null)}
            />
          ) : null}
        </div>
      </main>

            {openTradeId ? (
        <TradeDrawer
          tradeId={openTradeId}
          scheme={scheme}
          onClose={() => setOpenTradeId(null)}
          onOpenAssistant={(id) => { setOpenTradeId(id); setReviewTradeId(id); setAssistantOpen(true); }}
        />
      ) : null}
      {preferencesOpen ? <PreferencesView scheme={scheme} theme={theme} onToggleScheme={toggleScheme} onToggleTheme={() => setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))} onClose={() => setPreferencesOpen(false)} /> : null}
    </div>
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

function readStoredAccount(): string {
  try { return window.localStorage.getItem('smcub.account') || ''; } catch { return ''; }
}
