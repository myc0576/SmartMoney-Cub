import { test, expect } from './fixtures/test-fixtures';

test('preferences traps focus, closes on Escape, and does not offer fictitious currency conversion', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page); await page.goto('/'); await waitForAppReady(page);
  const trigger = page.getByRole('button', { name: '偏好', exact: true });
  await trigger.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('保留原始币种');
  await expect(dialog.getByLabel('显示币种')).toHaveCount(0);
  const first = dialog.getByRole('button', { name: '关闭', exact: true }).first();
  await expect(first).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', { name: '关闭', exact: true }).last()).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test('all shell locales use complete native hints and action labels', async ({ page, mockWorkbenchApis, waitForAppReady }) => {
  await mockWorkbenchApis(page); await page.goto('/'); await waitForAppReady(page);
  const actual = await page.evaluate(async () => {
    const { LOCALES, translate } = await import('/src/i18n.ts');
    return LOCALES.map(locale => [locale, translate('replay.pause', locale), translate('hint.connections', locale)]);
  });
  expect(actual.map(row => row[1])).toEqual(['暂停', 'Pause', '暫停', '一時停止', '일시 정지', 'Pausar', 'Pausar', 'Anhalten', 'Suspendre']);
  for (const [locale, , hint] of actual) {
    expect(hint.length).toBeGreaterThan(5);
    if (!['zh-CN', 'zh-TW', 'ja-JP'].includes(locale)) expect(hint).not.toMatch(/[\u4e00-\u9fff]/);
  }
});
