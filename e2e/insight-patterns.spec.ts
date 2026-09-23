import { test, expect } from './fixtures/test-fixtures';
const candidate = { pattern_id: 'PAT-toy', round_trip_id: 'RT-toy', axis: 'holding_horizon', label: 'intraday',
  status: 'observed', confidence: 'medium', evidence: [{ field: 'holding_seconds', observed: 1800 }],
  trade_ids: ['toy-fill'], missing_data: [], data_quality: 'observed_execution',
  invalidation: 'Toy revision', time_stop: 'Toy review', give_up: 'Toy unknown', data_source: 'toy', available_at: '2026-01-01', version: 'toy' };
test('patterns expose profile distribution and evidence, and failed decisions remain visible', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page);
  await page.route('**/api/trader/insight/mistakes*', route => route.fulfill({ json: { rows: [], triggers: [] } }));
  await page.route('**/api/trader/insight/edges*', route => route.fulfill({ json: { rows: [] } }));
  await page.route('**/api/trader/insight/patterns*', route => route.fulfill({ json: { profile: { sample_count: 20, account_count: 1, axes: { holding_horizon: { counts: { intraday: 20 }, dominant: 'intraday', label: 'intraday' } }, data_quality: 'descriptive', limitations: [] }, candidates: [candidate] } }));
  await page.route('**/api/trader/insight/patterns/decisions', route => route.fulfill({ status: 503, json: { error: 'toy_decision_not_saved' } }));
  await page.goto('/'); await waitForAppReady(page);
  await page.getByRole('button', { name: '洞察', exact: true }).click();
  await page.getByRole('tab', { name: '模式画像', exact: true }).click();
  await expect(page.getByTestId('pattern-axes')).toContainText('20');
  await page.getByRole('button', { name: '查看证据', exact: true }).click();
  await expect(page.getByText('holding_seconds', { exact: true })).toBeVisible();
  await expect(page.getByText('1800', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '确认模式', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('toy_decision_not_saved');
});
