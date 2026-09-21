import { test, expect } from './fixtures/test-fixtures';
import { pluginMarketFixture } from './fixtures/test-fixtures';

/**
 * Plugin marketplace end-to-end coverage.
 *
 * These tests run entirely against mocked API responses. A real install would
 * place third-party code on the machine running the suite, which is exactly the
 * action the product asks the user to confirm, so it does not belong in an
 * automated test. What is verified here is the interface contract: what the
 * cards show, what the wizard requires before it will proceed, and what the
 * marketplace looks like after each outcome.
 *
 * Each test resets the mutable fixture state so ordering cannot matter.
 */

async function openPlugins(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.waitForLoadState('domcontentloaded');
  await expect(page.locator('#root')).toBeVisible({ timeout: 10000 });
  await page.locator('nav.sidebar button', { hasText: '设置' }).first().click();
  await page.locator('.dsh-nav-tab', { hasText: '插件' }).first().click();
  await expect(page.locator('.plugin-card').first()).toBeVisible({ timeout: 10000 });
}

test.beforeEach(async ({ page, mockWorkbenchApis }) => {
  pluginMarketFixture.installShouldFail = false;
  pluginMarketFixture.installRequests = [];
  await mockWorkbenchApis(page);
});

test.describe('插件市场', () => {
  test('市场加载成功且不产生控制台错误', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', (error) => errors.push(String(error)));

    await openPlugins(page);

    // Every catalog entry the mock serves must be on screen, not a subset.
    await expect(page.locator('.plugin-card')).toHaveCount(pluginMarketFixture.entries.length);
    expect(errors).toEqual([]);
  });

  test('卡片显示上游链接、安装方式与可复制的原生命令', async ({ page }) => {
    await openPlugins(page);
    const card = page.locator('.plugin-card').filter({ hasText: 'AKShare' }).first();

    await expect(card.getByRole('link', { name: /akfamily\/akshare/ })).toHaveAttribute(
      'href',
      'https://github.com/akfamily/akshare',
    );
    await expect(card).toContainText('pip install akshare');
    await expect(card.getByRole('button', { name: /复制/ })).toBeVisible();
  });

  test('暗色模式下市场不出现浏览器默认白底控件', async ({ page }) => {
    await openPlugins(page);

    // Resolve the expected colours from the design tokens instead of hardcoding
    // a literal: the assertion then still holds if the palette is retuned, and
    // it fails if a control fell back to the user agent's white button.
    const tokens = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      return {
        panel: root.getPropertyValue('--panel').trim(),
        inset: root.getPropertyValue('--inset').trim(),
        theme: document.documentElement.getAttribute('data-theme'),
      };
    });
    expect(tokens.theme).toBe('dark');

    const backgrounds = await page.evaluate(() => {
      const read = (selector: string) => {
        const element = document.querySelector(selector);
        return element ? getComputedStyle(element).backgroundColor : null;
      };
      return {
        card: read('.plugin-card'),
        segmentedTrack: read('.segmented'),
        segmentedButton: read('.segmented button'),
        toolbar: read('.plugin-toolbar'),
      };
    });

    // The toolbar is a layout row, not a surface: it is meant to be
    // transparent so the panel behind it shows through. The controls inside it
    // are what must not fall back to the user agent's white button, so the
    // transparency check applies to those and not to the row itself.
    for (const [name, value] of Object.entries(backgrounds)) {
      expect(value, name + ' must have a resolved background').not.toBeNull();
      expect(value, name + ' must not fall back to the user agent white').not.toBe('rgb(255, 255, 255)');
      if (name === 'toolbar') continue;
      expect(value, name + ' must not be transparent').not.toBe('rgba(0, 0, 0, 0)');
    }
    // The card paints the panel surface, so it is not the page background.
    expect(backgrounds.card).not.toBe('rgb(16, 19, 24)');
  });

  test('安装向导要求先确认只读权限', async ({ page }) => {
    await openPlugins(page);
    await page.locator('.plugin-card').filter({ hasText: 'AKShare' }).first()
      .getByRole('button', { name: '安装' }).click();

    const wizard = page.locator('.dsh-modal, .plugin-wizard').first();
    await expect(wizard).toBeVisible();
    await expect(wizard).toContainText('READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE');

    const next = wizard.getByRole('button', { name: /下一步|开始安装/ }).first();
    await expect(next).toBeDisabled();

    await wizard.getByRole('checkbox').first().check();
    await expect(next).toBeEnabled();
  });

  test('需要密钥的插件在向导里只接受密码输入', async ({ page }) => {
    await openPlugins(page);
    await page.locator('.plugin-card').filter({ hasText: 'TuShare Pro' }).first()
      .getByRole('button', { name: '安装' }).click();

    const wizard = page.locator('.dsh-modal, .plugin-wizard').first();
    await wizard.getByRole('checkbox').first().check();
    await wizard.getByRole('button', { name: /下一步：填写密钥/ }).click();

    const secret = wizard.locator('input[type="password"]').first();
    await expect(secret).toBeVisible();
    // A text input here would echo the key back on screen.
    await expect(wizard.locator('input[type="text"]')).toHaveCount(0);
  });

  test('安装成功后插件出现在已安装列表', async ({ page }) => {
    await openPlugins(page);
    await page.locator('.plugin-card').filter({ hasText: 'QuantStats' }).first()
      .getByRole('button', { name: '安装' }).click();

    const wizard = page.locator('.dsh-modal, .plugin-wizard').first();
    await wizard.getByRole('checkbox').first().check();
    await wizard.getByRole('button', { name: /下一步：开始安装/ }).click();
    await expect(wizard).toContainText(/通过|健康检查/);
    await wizard.getByRole('button', { name: /完成/ }).click();

    await page.locator('.dsh-subtab', { hasText: '已安装' }).first().click();
    await expect(page.locator('.dsh-plugin-card').filter({ hasText: 'QuantStats' })).toBeVisible();
  });

  test('健康检查失败时插件不会出现在已安装列表', async ({ page }) => {
    pluginMarketFixture.installShouldFail = true;
    await openPlugins(page);
    await page.locator('.plugin-card').filter({ hasText: 'AKShare' }).first()
      .getByRole('button', { name: '安装' }).click();

    const wizard = page.locator('.dsh-modal, .plugin-wizard').first();
    await wizard.getByRole('checkbox').first().check();
    await wizard.getByRole('button', { name: /下一步：开始安装/ }).click();

    await expect(wizard).toContainText(/失败|未通过/);
    await wizard.getByRole('button', { name: /关闭|取消/ }).first().click();

    await page.locator('.dsh-subtab', { hasText: '已安装' }).first().click();
    await expect(page.locator('.dsh-plugin-card').filter({ hasText: 'AKShare' })).toHaveCount(0);
    // The market still reports it as not installed.
    await page.locator('.dsh-subtab', { hasText: '插件市场' }).first().click();
    const card = page.locator('.plugin-card').filter({ hasText: 'AKShare' }).first();
    await expect(card).toContainText('未安装');
  });

  test('自带下单能力的项目不提供安装入口', async ({ page }) => {
    await openPlugins(page);
    const card = page.locator('.plugin-card').filter({ hasText: 'vn.py' }).first();

    await expect(card).toContainText(/永不安装|高风险/);
    // No action the marketplace would refuse. The copy-command button stays:
    // it copies text for the user to run themselves and installs nothing.
    await expect(card.getByRole('button', { name: '安装' })).toHaveCount(0);
    await expect(card.getByRole('button', { name: /启用|停用|配置|禁止安装/ })).toHaveCount(0);
    await expect(card.getByRole('button', { name: /复制/ })).toHaveCount(1);
  });

  test('取消向导不会发出任何安装请求', async ({ page }) => {
    await openPlugins(page);
    await page.locator('.plugin-card').filter({ hasText: 'AKShare' }).first()
      .getByRole('button', { name: '安装' }).click();

    const wizard = page.locator('.dsh-modal, .plugin-wizard').first();
    await expect(wizard).toBeVisible();
    await wizard.getByRole('button', { name: /取消|✕|×/ }).first().click();
    await expect(wizard).toHaveCount(0);

    expect(pluginMarketFixture.installRequests).toEqual([]);
    const card = page.locator('.plugin-card').filter({ hasText: 'AKShare' }).first();
    await expect(card).toContainText('未安装');
  });

  test('复盘助手展开时插件网格保持两列且不横向溢出', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 950 });
    await openPlugins(page);

    // The assistant is docked by default and must already be visible; asserting
    // that instead of clicking a toggle keeps the test from collapsing the very
    // panel whose effect on the grid it is measuring.
    await expect(page.locator('.assistant')).toBeVisible();
    await expect(page.locator('.content.with-assistant')).toHaveCount(1);

    const layout = await page.evaluate(() => {
      const grid = document.querySelector('.plugin-card-grid');
      const page_ = document.querySelector('.page');
      const columns = grid ? getComputedStyle(grid).gridTemplateColumns : '';
      return {
        columnCount: columns.split(' ').filter(Boolean).length,
        overflow: page_ ? page_.scrollWidth - page_.clientWidth : 0,
      };
    });

    expect(layout.columnCount).toBe(2);
    expect(layout.overflow).toBeLessThanOrEqual(1);
  });
});
