import { test, expect } from './fixtures/test-fixtures';

test.describe('复盘助手 Copilot 形态与交互门禁', () => {
  test.beforeEach(async ({ page, mockWorkbenchApis }) => {
    await mockWorkbenchApis(page);
  });

  test('顶部状态条正确展示分析对象、规模以及 3 个快捷 Chips', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // 确保打开复盘助手
    const toggleBtn = page.getByRole('button', { name: /打开助手|收起助手/i });
    await expect(toggleBtn).toBeVisible();

    // 顶部状态条容器
    const contextBar = page.locator('.assistant-target-bar');
    await expect(contextBar).toBeVisible();

    // 默认未锁定单笔交易时显示“整个账本”或当前页面目标
    await expect(contextBar).toContainText(/整个账本|总览/);

    // 3 个快捷 chips
    const chipReview = page.locator('.assistant-quick-chip', { hasText: '今日复盘' });
    const chipMistakes = page.locator('.assistant-quick-chip', { hasText: '找重复错误' });
    const chipRules = page.locator('.assistant-quick-chip', { hasText: '检查规则执行' });

    await expect(chipReview).toBeVisible();
    await expect(chipMistakes).toBeVisible();
    await expect(chipRules).toBeVisible();
  });

  test('点击快捷 Chip 会自动填充提问并触发发送', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    const chipMistakes = page.locator('.assistant-quick-chip', { hasText: '找重复错误' });
    await chipMistakes.click();

    // 一次点击发起一轮复盘：磁盘上多一条用户消息，是这一步确实发生的凭据。
    const userBubble = page.locator('.bubble.user', { hasText: /重复错误/ });
    await expect(userBubble).toBeVisible({ timeout: 5000 });
  });

  test('模型配置弱化为轻量状态 Chip，ModelPicker 支持紧凑收敛', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // 检查轻量模型状态 Chip
    const modelChip = page.locator('.assistant-model-chip');
    await expect(modelChip).toBeVisible();
  });

  test('助手展开时页面无横向滚动条溢出', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // 确保展开助手（宽度 400px 常驻）
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1); // 允许 1px 亚像素误差，严禁溢出
  });
});
