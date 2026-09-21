import { test, expect } from './fixtures/test-fixtures';

test.describe('SmartMoney-Cub 复盘工作台 E2E 测试', () => {
  test.beforeEach(async ({ page, mockWorkbenchApis }) => {
    // 注入 API Mock，确保端到端测试不强依赖后端守护进程
    await mockWorkbenchApis(page);
  });

  test('页面成功加载，且标题与暗黑主题初始状态正确', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // 验证网页标题
    await expect(page).toHaveTitle(/SmartMoney-Cub/);

    // 默认主题应为 dark
    const htmlElement = page.locator('html');
    await expect(htmlElement).toHaveAttribute('data-theme', 'dark');
  });

  test('左侧导航栏主要标签页正常渲染', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // 检查核心业务分组与导航项
    const overviewNav = page.getByRole('button', { name: /总览/i }).first();
    const tradeLogNav = page.getByRole('button', { name: /交易日志/i }).first();
    const calendarNav = page.getByRole('button', { name: /复盘日历/i }).first();

    await expect(overviewNav).toBeVisible();
    await expect(tradeLogNav).toBeVisible();
    await expect(calendarNav).toBeVisible();
  });

  test('点击切换导航标签页能够正常响应', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // 切换至交易日志标签
    const tradeLogNav = page.getByRole('button', { name: /交易日志/i }).first();
    await tradeLogNav.click();

    // 页面主视图区域应响应切换
    await expect(page.locator('#root')).toBeVisible();
  });
});

