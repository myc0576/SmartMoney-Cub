import { test, expect } from './fixtures/test-fixtures';

test.describe('基础端到端环境冒烟测试', () => {
  test('Playwright 测试环境与断言功能正常运行', async ({ page }) => {
    // 验证 Playwright 核心页面操作与内置断言
    await page.setContent(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>Playwright E2E Starter</title>
        </head>
        <body>
          <header>
            <h1 id="title">SmartMoney-Cub E2E 测试套件</h1>
          </header>
          <main>
            <button id="counter-btn">点击次数: 0</button>
            <input id="search-input" placeholder="输入关键字搜索..." />
            <div id="status" class="ready">就绪</div>
          </main>
          <script>
            let count = 0;
            const btn = document.getElementById('counter-btn');
            btn.addEventListener('click', () => {
              count++;
              btn.textContent = '点击次数: ' + count;
            });
          </script>
        </body>
      </html>
    `);

    // 1. 验证标题与基本 DOM 渲染
    await expect(page).toHaveTitle('Playwright E2E Starter');
    const title = page.locator('#title');
    await expect(title).toHaveText('SmartMoney-Cub E2E 测试套件');

    // 2. 验证用户交互：输入与点击
    const input = page.locator('#search-input');
    await input.fill('EURUSD');
    await expect(input).toHaveValue('EURUSD');

    const button = page.locator('#counter-btn');
    await expect(button).toHaveText('点击次数: 0');
    await button.click();
    await expect(button).toHaveText('点击次数: 1');

    // 3. 验证属性与样式类
    const status = page.locator('#status');
    await expect(status).toHaveClass('ready');
  });
});

