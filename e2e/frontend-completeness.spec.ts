import { test, expect } from './fixtures/test-fixtures';

test.describe('frontend completeness states', () => {
  test('calendar reports a failed monthly read instead of an empty month', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
    await mockWorkbenchApis(page);
    await page.route('**/api/trader/calendar**', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'calendar service unavailable' }),
      });
    });

    await page.goto('/');
    await waitForAppReady(page);
    await page.getByRole('button', { name: '复盘日历' }).click();

    await expect(page.getByText(/日历数据读取失败/)).toBeVisible();
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible();
  });
});
