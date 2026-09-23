import { test as base, expect, Page } from '@playwright/test';

export interface CustomFixtures {
  waitForAppReady: (page: Page) => Promise<void>;
  mockWorkbenchApis: (page: Page) => Promise<void>;
}


/* ---- plugin marketplace mocks --------------------------------------- *
 * The marketplace talks to four endpoints. They are mocked here so the
 * end-to-end suite never depends on a running backend or on a real install,
 * which matters because an install would put third-party code on the machine
 * running the tests.
 *
 * marketplaceInstallResult is mutable on purpose: the failure and success
 * paths differ only in what the install call returns, and a test that could
 * only exercise the happy path would not prove that a failed health check
 * leaves the plugin uninstalled.
 */
const PLUGIN_MARKET_ENTRIES = [
  {
    plugin_id: 'akshare',
    name: 'AKShare',
    category: '数据',
    description: 'A 股公开数据适配器。',
    repo: 'https://github.com/akfamily/akshare',
    docs_url: null,
    install: { kind: 'pypi', package: 'akshare', module: 'akshare', version: null },
    license: 'MIT',
    level: 'adapter',
    capabilities: ['market_context'],
    requires_credentials: false,
    network_required: true,
    execution_risk: 'low',
    boundary: '只读行情数据，不连接券商、不下单、不改账户。',
    source: 'smartmoney-cub/official-curated',
    safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
    manual_command: 'pip install akshare',
    state: 'AVAILABLE',
    installed: false,
    enabled: false,
    mounted: false,
    health: 'pending',
    last_error: null,
    updated_at: null,
  },
  {
    plugin_id: 'quantstats',
    name: 'QuantStats',
    category: '绩效与风险',
    description: '绩效报告与风险统计。',
    repo: 'https://github.com/ranaroussi/quantstats',
    docs_url: null,
    install: { kind: 'pypi', package: 'quantstats', module: 'quantstats', version: null },
    license: 'Apache-2.0',
    level: 'adapter',
    capabilities: ['report_renderer', 'evaluator'],
    requires_credentials: false,
    network_required: false,
    execution_risk: 'low',
    boundary: '只读报表；不产生买卖指令。',
    source: 'smartmoney-cub/official-curated',
    safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
    manual_command: 'pip install quantstats',
    state: 'AVAILABLE',
    installed: false,
    enabled: false,
    mounted: false,
    health: 'pending',
    last_error: null,
    updated_at: null,
  },
  {
    plugin_id: 'tushare-pro',
    name: 'TuShare Pro',
    category: '数据',
    description: '需要官方 token 的历史行情。',
    repo: 'https://tushare.pro',
    docs_url: 'https://github.com/waditu/tushare',
    install: { kind: 'pypi', package: 'tushare', module: 'tushare', version: null },
    license: 'BSD-3-Clause',
    level: 'adapter',
    capabilities: ['market_context'],
    requires_credentials: true,
    network_required: true,
    execution_risk: 'low',
    boundary: '只读行情数据，不连接券商、不下单、不改账户。',
    source: 'smartmoney-cub/official-curated',
    safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
    manual_command: 'pip install tushare',
    state: 'AVAILABLE',
    installed: false,
    enabled: false,
    mounted: false,
    health: 'pending',
    last_error: null,
    updated_at: null,
  },
  {
    plugin_id: 'tradingagents',
    name: 'TradingAgents',
    category: 'Agent',
    description: '多智能体交易分析框架。',
    repo: 'https://github.com/TauricResearch/TradingAgents',
    docs_url: null,
    install: {
      kind: 'git',
      repo: 'https://github.com/TauricResearch/TradingAgents',
      module: 'tradingagents',
      tag: null,
    },
    license: 'Apache-2.0',
    level: 'companion',
    capabilities: ['reviewer', 'agent_bridge'],
    requires_credentials: true,
    network_required: true,
    execution_risk: 'medium',
    boundary: '用户自备密钥；输出只能作为复盘证据。',
    source: 'smartmoney-cub/official-curated',
    safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
    manual_command: 'git clone --depth 1 https://github.com/TauricResearch/TradingAgents',
    state: 'AVAILABLE',
    installed: false,
    enabled: false,
    mounted: false,
    health: 'pending',
    last_error: null,
    updated_at: null,
  },
  {
    plugin_id: 'uzi-skill',
    name: 'UZI-Skill',
    category: 'Agent',
    description: '外部分析技能。',
    repo: 'https://github.com/wbh604/UZI-Skill',
    docs_url: null,
    install: {
      kind: 'git',
      repo: 'https://github.com/wbh604/UZI-Skill',
      module: 'uzi_skill',
      tag: null,
    },
    license: 'unverified',
    level: 'companion',
    capabilities: ['reviewer'],
    requires_credentials: false,
    network_required: false,
    execution_risk: 'low',
    boundary: '只能描述为推荐搭配，不得变成买卖指令。',
    source: 'smartmoney-cub/official-curated',
    safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
    manual_command: 'git clone --depth 1 https://github.com/wbh604/UZI-Skill',
    state: 'AVAILABLE',
    installed: false,
    enabled: false,
    mounted: false,
    health: 'pending',
    last_error: null,
    updated_at: null,
  },
  {
    plugin_id: 'multi-agent-trade-review',
    name: '多 Agent 复盘',
    category: 'Agent',
    description: 'harness 内置的复盘协作链。',
    repo: 'builtin://smartmoney-cub/multi-agent-review',
    docs_url: null,
    install: { kind: 'builtin', note: 'harness 内置的复盘协作链' },
    license: 'builtin',
    level: 'adapter',
    capabilities: ['reviewer', 'challenger'],
    requires_credentials: false,
    network_required: false,
    execution_risk: 'low',
    boundary: '只生成 challenger 候选；champion 变更必须人工确认。',
    source: 'smartmoney-cub/official-curated',
    safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
    manual_command: 'harness 内置的复盘协作链',
    state: 'AVAILABLE',
    installed: false,
    enabled: false,
    mounted: false,
    health: 'pending',
    last_error: null,
    updated_at: null,
  },
  {
    plugin_id: 'vnpy',
    name: 'vn.py',
    category: 'Agent',
    description: '自带下单能力的交易框架，永不安装。',
    repo: 'https://github.com/vnpy/vnpy',
    docs_url: null,
    install: { kind: 'git', repo: 'https://github.com/vnpy/vnpy', module: 'vnpy', tag: null },
    license: 'MIT',
    level: 'companion',
    capabilities: ['market_context'],
    requires_credentials: true,
    network_required: true,
    execution_risk: 'high',
    boundary: '自带下单与账户能力，harness 绝不安装、挂载或调用它。',
    source: 'smartmoney-cub/official-curated',
    safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
    manual_command: 'git clone --depth 1 https://github.com/vnpy/vnpy',
    state: 'AVAILABLE',
    installed: false,
    enabled: false,
    mounted: false,
    health: 'pending',
    last_error: null,
    updated_at: null,
  },
  {
    plugin_id: 'baostock',
    name: 'BaoStock',
    category: '数据',
    description: '已安装示例。',
    repo: 'https://www.baostock.com',
    docs_url: null,
    install: { kind: 'pypi', package: 'baostock', module: 'baostock', version: null },
    license: 'Apache-2.0',
    level: 'adapter',
    capabilities: ['market_context'],
    requires_credentials: false,
    network_required: true,
    execution_risk: 'low',
    boundary: '只读行情数据。',
    source: 'smartmoney-cub/official-curated',
    safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
    manual_command: 'pip install baostock',
    state: 'ENABLED',
    installed: true,
    enabled: true,
    mounted: true,
    health: 'healthy',
    last_error: null,
  updated_at: '2026-09-21T10:00:00+08:00',
  },
];

/**
 * The last question sent to the assistant, held across the turn and the reload.
 *
 * The panel posts a question, streams the answer, then re-reads the transcript
 * from the server. A mock that forgets the question between those two calls makes
 * the reload erase what the test just watched the page do, so the question is
 * remembered here and returned by the detail call.
 */
let lastTurnText = '';

export const pluginMarketFixture = {
  entries: PLUGIN_MARKET_ENTRIES,
  /** Set by a test to make the next install call fail its health check. */
  installShouldFail: false,
  /** Every install request the page actually sent, for absence assertions. */
  installRequests: [] as string[],
};

function pluginMarketResponse() {
  const installed = PLUGIN_MARKET_ENTRIES.filter((e) => e.installed);
  return {
    status: 'ok',
    schema: 'smartmoney_cub_plugin_catalog.v2',
    source: 'official-curated',
    categories: ['数据', '绩效与风险', '研究与评估', 'Agent'],
    catalog: PLUGIN_MARKET_ENTRIES,
    counts: {
      total: PLUGIN_MARKET_ENTRIES.length,
      installed: installed.length,
      by_category: {},
      by_install_kind: { pypi: 3, git: 3, builtin: 1 },
    },
    policy: '目录只描述上游来源与安装方式。',
    safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
  };
}

export const test = base.extend<CustomFixtures>({
  waitForAppReady: async ({}, use) => {
    await use(async (page: Page) => {
      await page.waitForLoadState('domcontentloaded');
      await expect(page.locator('#root')).toBeVisible({ timeout: 10000 });
    });
  },

  mockWorkbenchApis: async ({}, use) => {
    await use(async (page: Page) => {
      // 拦截所有 /api 请求并提供完整的符合前端契约的 Mock 数据
      await page.route('**/api/**', async (route) => {
        const url = route.request().url();

        if (url.includes('/api/trader/meta')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
              read_only: true,
              store_path: ':memory:',
              active_account_id: 'default',
              accounts: [
                {
                  account_id: 'default',
                  name: '离线复盘账户',
                  broker: 'offline',
                  currency: 'CNY',
                },
              ],
            }),
          });
        } else if (url.includes('/api/trader/analytics/summary')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              status: 'ok',
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
              ledger_status: 'ok',
              counts: {
                closed_trades: 0,
                open_positions: 0,
                executions: 0,
                total_pnl: 0,
              },
              summary: {
                trade_count: 0,
                win_count: 0,
                loss_count: 0,
                flat_count: 0,
                win_rate: 0,
                profit_factor: null,
                profit_factor_note: '暂无数据',
                total_net_pnl: 0,
                total_fees: 0,
                avg_return_pct: 0,
                avg_win_pct: 0,
                avg_loss_pct: 0,
                avg_holding_days: 0,
                max_drawdown: 0,
                open_position_count: 0,
                sample_note: '离线测试空数据',
                equity_curve: [],
              },
            }),
          });
        } else if (url.includes('/api/trader/trades')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
              trades: [],
              open_positions: [],
              issues: [],
              ledger_status: 'ok',
              total: 0,
            }),
          });
        } else if (url.includes('/api/assistant/sessions')) {
          // Creating a session is a POST to the same path as the list, and the
          // two answer different shapes. The mock used to return the list body
          // for both, so the panel's create call read session_id off an object
          // that has none -- which surfaced as "无法新建会话" rather than as the
          // fixture gap it was.
          const method = route.request().method();
          // The stream path is /messages; /resume is the retry path for a stream
          // that dropped, and answers the same shape.
          const turn = /\/api\/assistant\/sessions\/[^/]+\/(messages|resume)/.test(url);
          const detail = !turn && method === 'GET'
            && /\/api\/assistant\/sessions\/[^?/]+(\?.*)?$/.test(url);
          if (turn) {
            // The turn is a Server-Sent Events stream, not JSON. Answering it with
            // a JSON body made the reader parse zero frames and the panel then
            // reload the transcript from the detail call, which the mock was also
            // answering with the session list -- so a question a test had just
            // asked disappeared. Both shapes are answered here now.
            const posted = route.request().postDataJSON() || {};
            lastTurnText = String(posted.text || '');
            const frames = [
              { kind: 'turn_started', safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE' },
              { kind: 'delta', text: '已读取台账，正在整理。' },
              { kind: 'turn_completed', safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE' },
              { kind: 'done', safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE' },
            ];
            await route.fulfill({
              status: 200,
              contentType: 'text/event-stream',
              body: frames.map((frame) => 'data: ' + JSON.stringify(frame) + '\n\n').join(''),
            });
            return;
          }
          if (detail) {
            // The transcript the store would hold: the question that was asked and
            // the answer that came back, which is what the panel re-reads after a
            // turn finishes.
            await route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify({
                session: {
                  session_id: 'e2e-session-1',
                  title: lastTurnText.slice(0, 18) || 'e2e',
                  status: 'active',
                  provider_id: 'alphatech',
                  model: '',
                  reasoning: 'off',
                },
                events: lastTurnText
                  ? [
                      {
                        event_id: 1, seq: 1, kind: 'user_message', role: 'user',
                        payload: { text: lastTurnText }, created_at: '2026-01-01T00:00:00+00:00',
                      },
                      {
                        event_id: 2, seq: 2, kind: 'assistant_message', role: 'assistant',
                        payload: { text: '已读取台账，正在整理。' }, created_at: '2026-01-01T00:00:01+00:00',
                      },
                    ]
                  : [],
                safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
              }),
            });
            return;
          }
          const creatingSession = method === 'POST';
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(creatingSession
              ? {
                  session: {
                    session_id: 'e2e-session-1',
                    title: 'e2e',
                    status: 'active',
                    provider_id: 'alphatech',
                    model: '',
                    reasoning: 'off',
                    created_at: '2026-01-01T00:00:00+00:00',
                  },
                  safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
                }
              : { sessions: [] }),
          });
        } else if (url.includes('/api/trader/health')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              status: 'ok',
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
              read_only: true,
            }),
          });
        } else if (url.includes('/api/meta')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              // A routable seat, because the assistant refuses to send without
              // one -- and it is right to. The panel gates the composer on this
              // meta, so a fixture that omits providers tests the refusal path in
              // every spec that expects a question to go through, which is how a
              // missing provider looked like a missing feature.
              app: 'smartmoney-cub-workbench',
              version: '1.0.0',
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
              redaction_policy: 'identity_and_size_redacted',
              engine: {},
              providers: [
                {
                  provider_id: 'alphatech',
                  label: 'AlphaTech API',
                  protocol: 'openai',
                  protocol_label: 'OpenAI 兼容',
                  base_url: '',
                  routing: 'direct',
                  routable: true,
                  available: true,
                  models: [
                    {
                      id: 'e2e-model',
                      label: 'E2E Model',
                      reasoning_efforts: ['off', 'medium'],
                      default_reasoning: 'off',
                    },
                  ],
                },
              ],
              default_provider: 'alphatech',
              default_model: 'e2e-model',
              default_reasoning: 'off',
              store_counts: {},
              trend_color_scheme: 'cn',
              read_only: true,
              tenant: 'e2e-test',
              mode: 'offline',
            }),
          });
        } else if (url.includes('/api/overview')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
              portfolio_id: 'default',
              summary: { total_pnl: 0, win_rate: 0, trade_count: 0 },
            }),
          });
        } else if (url.includes('/api/jev/status')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ status: 'ok', ready: true }),
          });
        } else if (url.includes('/api/plugins/market')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(pluginMarketResponse()),
          });
        } else if (url.includes('/api/plugins/install')) {
          pluginMarketFixture.installRequests.push(url);
          const pluginId = String((route.request().postDataJSON() || {}).plugin_id || '');
          if (pluginMarketFixture.installShouldFail) {
            await route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify({
                status: 'error',
                steps: [
                  { step: 'permissions', status: 'ok', detail: '已确认只读权限' },
                  { step: 'fetch', status: 'ok', detail: '已获取上游产物' },
                  { step: 'health', status: 'failed', detail: 'import 校验失败：模块不可用' },
                ],
                health: { ok: false, detail: 'import 校验失败：模块不可用' },
                error: '健康检查未通过，插件未安装',
                safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
              }),
            });
            return;
          }
          const entry = PLUGIN_MARKET_ENTRIES.find((e) => e.plugin_id === pluginId);
          if (entry) {
            entry.installed = true;
            entry.enabled = true;
            entry.mounted = true;
            entry.state = 'ENABLED';
            entry.health = 'healthy';
          }
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              status: 'ok',
              plugin: entry,
              steps: [
                { step: 'permissions', status: 'ok', detail: '已确认只读权限' },
                { step: 'fetch', status: 'ok', detail: '已获取上游产物' },
                { step: 'health', status: 'ok', detail: 'import 校验通过' },
              ],
              health: { ok: true, detail: 'import 校验通过' },
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
            }),
          });
        } else if (url.includes('/api/plugins/uninstall')) {
          const pluginId = String((route.request().postDataJSON() || {}).plugin_id || '');
          const entry = PLUGIN_MARKET_ENTRIES.find((e) => e.plugin_id === pluginId);
          if (entry) {
            entry.installed = false;
            entry.enabled = false;
            entry.mounted = false;
            entry.state = 'AVAILABLE';
          }
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ status: 'ok', plugin_id: pluginId, safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE' }),
          });
        } else if (url.includes('/api/plugins/probe')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ status: 'ok', healthy: true, detail: 'ok', safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE' }),
          });
        } else if (url.includes('/api/plugins')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              status: 'ok',
              profile: 'default-offline',
              plugins: PLUGIN_MARKET_ENTRIES.filter((e) => e.installed).map((e) => ({
                plugin_id: e.plugin_id,
                name: e.name,
                version: '1.0.0',
                state: 'ACTIVE',
                capabilities: e.capabilities,
                isolation: 'subprocess',
                enabled: true,
                last_error: null,
                health: { healthy: true },
              })),
              rejected: [],
              installed_entry_points: [],
              marketplace: pluginMarketResponse(),
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
            }),
          });
        } else if (url.includes('/api/jev/tracks')) {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ tracks: [] }),
          });
        } else {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
              ok: true,
            }),
          });
        }
      });
    });
  },
});

export { expect };
