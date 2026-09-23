import { test, expect } from './fixtures/test-fixtures';
const bar = { open_time: '2026-01-01T00:00:00Z', open: 10, high: 12, low: 9, close: 11, volume: 1 };
const saved = { session_id: 'toy-session', mode: 'training', symbol: 'TOY', interval: '1d',
  provider: 'toy', cursor: 0, bar_count: 3, historical_evidence: 'unverified',
  bars: [bar], markers: [], training: { fills: [], orders: [] } };

test('replay resumes a saved cursor and clearly queues a fractional simulation', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/trader/market/providers', route => route.fulfill({ json: { providers: [] } }));
  await page.route('**/api/trader/replay/sessions', route => route.fulfill({ json: { sessions: [saved] } }));
  await page.route('**/api/trader/replay/sessions/toy-session', route => route.fulfill({ json: { session: saved } }));
  let submitted: any;
  await page.route('**/api/trader/replay/sessions/toy-session/actions', route => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ json: { session: { ...saved, training: { fills: [], orders: [{ status: 'pending', quantity: '0.25', side: 'BUY' }] } } } });
  });
  await page.goto('/'); await waitForAppReady(page);
  await page.getByRole('button', { name: '演练', exact: true }).click();
  await page.getByRole('button', { name: /恢复.*TOY/ }).click();
  await expect(page.getByText(/历史可得时间未验证/)).toBeVisible();
  await page.getByLabel('模拟数量').fill('0.25');
  await page.getByRole('button', { name: '模拟买入', exact: true }).click();
  await expect.poll(() => submitted?.quantity).toBe('0.25');
  await expect(page.getByText(/待下一根开盘成交/)).toBeVisible();
});

test('provider lookup failure is not disguised as an empty catalogue', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/trader/market/providers', route => route.fulfill({ status: 403, json: { error: 'toy_closed_boundary' } }));
  await page.route('**/api/trader/replay/sessions', route => route.fulfill({ json: { sessions: [] } }));
  await page.goto('/'); await waitForAppReady(page);
  await page.getByRole('button', { name: '演练', exact: true }).click();
  await expect(page.getByText(/toy_closed_boundary/)).toBeVisible();
  await expect(page.getByRole('button', { name: '开始回放', exact: true })).toBeDisabled();
});
