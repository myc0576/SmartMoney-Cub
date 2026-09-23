import { test, expect } from './fixtures/test-fixtures';

test('journal reaches older pages and clears old positions after a failed read', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/trader/trades?*', route => {
    const url = new URL(route.request().url());
    const offset = Number(url.searchParams.get('offset') || 0);
    if (offset >= 400) return route.fulfill({ status: 503, json: { error: 'toy_page_unavailable' } });
    return route.fulfill({ json: { count: 401, trades: [{ round_trip_id: 'toy-' + offset, symbol: 'PAGE-' + offset, currency: 'USD', net_pnl: 1, quantity: 1 }],
      open_positions: [{ position_id: 'toy-position', symbol: 'TOY-OPEN', quantity: 1, avg_cost: 5, currency: 'USD' }], issues: [] } });
  });
  await page.goto('/'); await waitForAppReady(page);
  await page.getByRole('button', { name: '交易日志', exact: true }).click();
  await expect(page.locator('main')).toContainText('PAGE-0');
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  await expect(page.locator('main')).toContainText('PAGE-200');
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  await expect(page.locator('main')).toContainText('toy_page_unavailable');
  await expect(page.locator('.page')).not.toContainText('TOY-OPEN');
  await expect(page.getByRole('button', { name: '重试', exact: true })).toBeVisible();
});
