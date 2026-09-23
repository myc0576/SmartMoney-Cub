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

    // 检查核心业务分组与导航项：收敛后的八个入口
    const labels = ['总览', '交易日志', '复盘日历', '报告', '洞察', '策略实验室', '演练', '设置'];
    for (const label of labels) {
      const item = page.locator('nav.sidebar button', { hasText: label }).first();
      await expect(item).toBeVisible();
    }
  });

  test('合并后的页面保留原来的能力入口', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // 交易日志同时承载未配对持仓与每行的详情抽屉
    await page.locator('nav.sidebar button', { hasText: '交易日志' }).first().click();
    await expect(page.getByRole('heading', { name: /未配对持仓/ })).toBeVisible();

    // 策略实验室把 Playbook、规则库与回测收在一页
    await page.locator('nav.sidebar button', { hasText: '策略实验室' }).first().click();
    await expect(page.getByRole('tab', { name: /Playbook/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /规则库/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /回测/ })).toBeVisible();

    // 洞察页把重复错误与 Edge 库收在一页
    await page.locator('nav.sidebar button', { hasText: '洞察' }).first().click();
    await expect(page.getByRole('tab', { name: /重复错误/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /Edge 库/ })).toBeVisible();

    // 演练只保留真实回放和模拟训练，不再混入账户考核。
    await page.locator('nav.sidebar button', { hasText: '演练' }).first().click();
    await expect(page.getByRole('tab', { name: /自营账户/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '开始回放', exact: true })).toBeVisible();
  });

  test('导入改为交易页动作而不是一级入口', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // 侧边栏里不再有「数据导入」入口
    await expect(page.locator('nav.sidebar button', { hasText: '数据导入' })).toHaveCount(0);

    // 顶栏紧凑的「导入」按钮打开导入页。
    await page.getByRole('button', { name: '导入', exact: true }).click();
    await expect(page.locator('h1', { hasText: '数据导入' })).toBeVisible();
  });

  test('工程向入口下沉到设置', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // Jev 引擎与基准评测不再是一级入口
    await expect(page.locator('nav.sidebar button', { hasText: 'Jev 引擎' })).toHaveCount(0);
    await expect(page.locator('nav.sidebar button', { hasText: '基准评测' })).toHaveCount(0);

    // 设置在设置页内可达
    await page.locator('nav.sidebar button', { hasText: '设置' }).first().click();
    await expect(page.locator('.dsh-nav-tab', { hasText: '插件' }).first()).toBeVisible();
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
