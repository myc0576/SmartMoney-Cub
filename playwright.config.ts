import { defineConfig, devices } from '@playwright/test';

/**
 * Microsoft Playwright E2E 测试配置文件
 * 官方文档: https://playwright.dev/docs/test-configuration
 * GitHub 仓库: https://github.com/microsoft/playwright
 */
export default defineConfig({
  testDir: './e2e',
  /* 单个测试用例最大超时时间 */
  timeout: 30 * 1000,
  expect: {
    timeout: 5000,
  },
  /* 并行执行所有测试 */
  fullyParallel: true,
  /* CI 环境下禁止 test.only */
  forbidOnly: !!process.env.CI,
  /* 重试策略：CI 环境重试 2 次，本地重试 0 次 */
  retries: process.env.CI ? 2 : 0,
  /* 并发 worker 数量 */
  workers: process.env.CI ? 1 : undefined,
  /* 测试报告输出格式：控制台 list 列表 + 离线 html 报告 */
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  /* 产物（追踪、截图、视频）输出目录 */
  outputDir: 'test-results',

  /* 所有项目共享的基础配置 */
  use: {
    /* 前端界面基础 URL */
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5173',
    /* 失败时录制追踪信息 */
    trace: 'on-first-retry',
    /* 仅在失败时截图 */
    screenshot: 'only-on-failure',
    /* 失败时保留视频录制 */
    video: 'retain-on-failure',
  },

  /* 浏览器项目配置：默认启用当前环境已就绪的 Chromium；如需启用 Firefox/WebKit 可运行 npx playwright install */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // 如需跨浏览器测试，可运行 `npx playwright install firefox webkit` 后解除下方注释：
    // {
    //   name: 'firefox',
    //   use: { ...devices['Desktop Firefox'] },
    // },
    // {
    //   name: 'webkit',
    //   use: { ...devices['Desktop Safari'] },
    // },
  ],

  /* 运行端到端测试前自动启动前端开发服务器 */
  webServer: {
    command: 'npm run dev --prefix gui -- --host 127.0.0.1 --port 5173',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60 * 1000,
  },
});

