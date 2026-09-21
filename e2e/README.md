# SmartMoney-Cub 端到端测试 (Playwright E2E)

基于 [Microsoft Playwright](https://github.com/microsoft/playwright) 构建的自动化端到端测试套件，用于验证复盘工作台（GUI 前端）与交易工作流的完整链路。

---

## 目录结构

```text
├── e2e/
│   ├── fixtures/
│   │   └── test-fixtures.ts   # 扩展 Fixture：封装通用页面准备与 API 契约 Mock
│   ├── example.spec.ts        # Playwright 环境基础冒烟测试
│   ├── workbench.spec.ts      # 复盘工作台核心功能 E2E 测试
│   ├── tsconfig.json          # E2E 专属 TypeScript 配置
│   └── README.md              # 本说明文档
├── playwright.config.ts       # Playwright 全局配置文件（包含 webServer 自动拉起等）
├── package.json               # 注册常用 E2E 脚本命令
└── scripts/dev-env.sh         # 支持 `./scripts/dev-env.sh test e2e` 确定性执行
```

---

## 核心特性

1. **零外部配置即用**：
   - 配置文件已集成 `webServer`，运行测试时会自动编译并以非阻塞方式启动 `gui` 前端（`http://127.0.0.1:5173`），测试完成后自动释放端口。
2. **离线与契约安全**：
   - 提供 `mockWorkbenchApis` Fixture，预设严格对齐系统安全声明 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` 的 Mock 数据，支持在完全离线、无后端守护进程的环境下秒级执行端到端验证。
3. **跨浏览器支持**：
   - 默认启用环境内开箱即用的 Chromium 内核；保留 Firefox 与 WebKit 配置，可一键扩展。

---

## 常用命令

### 1. 运行测试
```bash
# 运行全量 E2E 测试（无头模式）
npm run test:e2e

# 或通过 dev-env CLI 确定性运行
./scripts/dev-env.sh test e2e
```

### 2. 交互式 UI 模式（推荐调试）
Playwright 强大的交互式时间旅行调试器：
```bash
npm run test:e2e:ui
```

### 3. 有头浏览器模式（观察执行过程）
```bash
npm run test:e2e:headed
```

### 4. 单步断点调试
```bash
npm run test:e2e:debug
```

### 5. 查看测试报告
测试完成后可在浏览器中打开生成的富文本报告与失败追踪：
```bash
npm run test:e2e:report
```

---

## 扩展多浏览器支持

默认配置使用本地已有的 Chromium。如需在 Firefox 或 WebKit（Safari）中运行：

1. 安装浏览器内核：
   ```bash
   npx playwright install firefox webkit
   ```
2. 打开根目录下的 `playwright.config.ts`，取消 `projects` 中 `firefox` 与 `webkit` 的注释即可。

---

## 编写新的测试用例

推荐引入 `e2e/fixtures/test-fixtures` 中的 `test` 与 `expect`：

```typescript
import { test, expect } from './fixtures/test-fixtures';

test.describe('新功能模块测试', () => {
  test.beforeEach(async ({ page, mockWorkbenchApis }) => {
    // 注入 API Mock 数据
    await mockWorkbenchApis(page);
  });

  test('验证用户操作流程', async ({ page, waitForAppReady }) => {
    await page.goto('/');
    await waitForAppReady(page);

    // 优先通过角色与可访问性属性定位元素
    const targetButton = page.getByRole('button', { name: /某按钮/i });
    await expect(targetButton).toBeVisible();
    await targetButton.click();

    // 验证结果
    await expect(page.getByText('操作成功')).toBeVisible();
  });
});
```

