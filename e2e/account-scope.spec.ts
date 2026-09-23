import { test, expect } from './fixtures/test-fixtures';

test('changing the topbar account reloads the active journal instead of retaining another account', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/trader/accounts', route => route.fulfill({ json: { accounts: [
    { account_id: 'toy-a', name: 'Toy A', currency: 'USD' }, { account_id: 'toy-b', name: 'Toy B', currency: 'JPY' },
  ] } }));
  await page.route('**/api/trader/trades?*', route => {
    const id = new URL(route.request().url()).searchParams.get('account_id') || 'all';
    return route.fulfill({ json: { trades: [{ round_trip_id: id, symbol: 'SCOPE-' + id, quantity: 1, net_pnl: 1, currency: 'USD' }], open_positions: [], count: 1, issues: [] } });
  });
  await page.goto('/'); await waitForAppReady(page);
  await page.getByRole('button', { name: '交易日志', exact: true }).click();
  await expect(page.locator('main')).toContainText('SCOPE-all');
  await page.locator('.topbar-scope select').selectOption('toy-a');
  await expect(page.locator('main')).toContainText('SCOPE-toy-a');
  await expect(page.locator('main')).not.toContainText('SCOPE-all');
  await page.locator('.topbar-scope select').selectOption('toy-b');
  await expect(page.locator('main')).toContainText('SCOPE-toy-b');
  await expect(page.locator('main')).not.toContainText('SCOPE-toy-a');
});
