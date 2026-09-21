import { test as base, expect, Page } from '@playwright/test';

export interface CustomFixtures {
  waitForAppReady: (page: Page) => Promise<void>;
  mockWorkbenchApis: (page: Page) => Promise<void>;
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
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              sessions: [],
            }),
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
              safety: 'READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE',
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

