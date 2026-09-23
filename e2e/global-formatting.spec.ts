import { test, expect } from './fixtures/test-fixtures';

test('trade log shows separate currency amounts without adding them', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/trader/trades?*', route => route.fulfill({ json: {
    trades: [{ round_trip_id: 'toy-us', symbol: 'TOY-USD', quantity: 1, net_pnl: 10, currency: 'USD' },
      { round_trip_id: 'toy-jp', symbol: 'TOY-JPY', quantity: 1, net_pnl: 1000, currency: 'JPY' }],
    open_positions: [], count: 2, issues: [],
  } }));
  await page.goto('/'); await waitForAppReady(page);
  await page.getByRole('button', { name: '交易日志', exact: true }).click();
  await expect(page.getByText('TOY-USD', { exact: false }).first()).toBeVisible();
  await expect(page.locator('main')).not.toContainText('+1,010.00');
  await expect(page.locator('main')).toContainText('USD +10.00');
  await expect(page.locator('main')).toContainText('JPY +1,000.00');
});

test('money aggregates refuse mixed or unknown units and incomplete values', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page); await page.goto('/'); await waitForAppReady(page);
  const results = await page.evaluate(async () => {
    const { monetaryTotal } = await import('/src/money.ts');
    return [
      monetaryTotal([{ currency: 'USD', net_pnl: 10 }, { currency: 'JPY', net_pnl: 1000 }]),
      monetaryTotal([{ currency: 'UNKNOWN', net_pnl: 10 }]),
      monetaryTotal([{ currency: 'USD', net_pnl: null }]),
      monetaryTotal([{ currency: 'USD', net_pnl: 10 }, { currency: 'USD', net_pnl: -2 }]),
    ];
  });
  expect(results).toEqual([null, null, null, 8]);
});

test('date-only values never shift to a previous calendar day or invent a time', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page); await page.goto('/'); await waitForAppReady(page);
  const result = await page.evaluate(async () => {
    const { formatDate, formatDateTime } = await import('/src/i18n.ts');
    return [formatDate('2026-09-23', 'en-US', 'America/Los_Angeles'), formatDateTime('2026-09-23', 'en-US', 'America/Los_Angeles')];
  });
  expect(result).toEqual(['Sep 23, 2026', 'Sep 23, 2026']);
});
