---
name: agent-browser-verify
description: 负责全栈与前端变更后的最后一轮视觉 QA 门禁。集成 Playwright / agent-browser 自动化驱动无头浏览器，遍历全量导航视图与交互状态，自动化检测白屏、Console Error、水平布局溢出、暗色反色缺陷与封闭信任边界防御，产出可审计的视觉报告与截图。
metadata:
  role: visual-qa-lead
  category: automated-qa
  priority: 4
---

# Agent Browser Verify (自动化视觉 QA 与布局门禁)

本技能专注于 **前端代码或组件变更后的终局视觉 QA 验证**。
严禁大模型通过“代码看起来没问题”自我宣布交付，必须通过无头浏览器自动化巡检，获取客观渲染证据（DOM 节点数、面板存在性、控制台 0 Error、0 水平溢出、视觉截图）。

---

## 核心核验流水线 (Automated Verification Pipeline)

在执行任何前端页面重构或功能增补后，必须执行以下验证阶段：

### 阶段 1: 基础静态与契约检查
- 执行 `cd gui && npm run typecheck`，确保 TypeScript 类型 0 错误。
- 执行 `cd gui && npm run build`，确保 Vite 生产构建顺利打包无警告退出。

### 阶段 2: 自动化视觉巡检驱动 (Visual Check Script)
运行仓库内置的确定性 Playwright 驱动巡检：
```bash
./scripts/visual-check.sh
# 或在统一 CLI 中执行：
./scripts/dev-env.sh test e2e
```

该脚本将自动执行三大轮次严格检查：
1. **15 个全量核心导航视图遍历巡检**：
   - 包含：总览、交易日志、复盘日历、绩效分析、规则库、数据导入、设置、报告、Playbook、回测、K线回放、自营账户、成交台账、Jev引擎、基准评测。
   - **通过标准 (Pass Criteria)**：
     - DOM 节点数正常渲染（> 1500）。
     - 必须包含本视图专用 panel/table/grid。
     - 绝无「读取失败」、「加载失败」或未捕获的错误 Banner。
     - 水平宽度无溢出（`scrollWidth <= clientWidth + 2`）。
     - 浏览器控制台致命错误数 = 0。

2. **复盘助手 (AssistantPanel) 深度交互与挤压测试**：
   - 测试右侧助手展开时，主页面卡片网格响应式降级（无水平溢出、卡片列数平滑适应）。
   - 模型选择器（ModelPicker）打开、推理强度（Effort Stage）逐级说明、设置-模型目录完整性。
   - 检查插件市场卡片在助手同时打开时的双列布局。

3. **封闭信任边界 (Trust Boundary Simulation)**：
   - 模拟后端 403 封闭边界，核验复盘助手是否展示醒目的「不可用」且输入框处于 `disabled` 状态。
   - 验证规则库与插件库在边界关闭时是否诚实报错「读取失败」，杜绝谎称「暂无数据」。

### 阶段 3: 视觉差异与证据留存
- 自动写入全套视图片段至 `artifacts/visual/*.png` 与 `artifacts/visual/report.json`。
- 只有在 `report.json` 中 `summary.failed.length === 0` 时，方可判定视觉 QA 通过！

---

## 快速故障排查指南 (Triaging Failures)

| 失败现象 | 根因排查方向 | 修复策略 |
|---|---|---|
| `overflow=true` | 某子元素设置了绝对宽度 `width: 1200px` 或未添加 `min-width: 0` | 检查 Flex/Grid 容器，使用 `min-width: 0` 与百分比/fr 单位 |
| `whiteControls > 0` | 暗色模式下按钮或卡片漏写类名，回退到浏览器白底 | 补充 `tokens.css` 语义类，统一使用 `var(--color-surface-*)` |
| `console_errors > 0` | 异步数据空值访问（`TypeError: cannot read properties of undefined`）| 增加可选链操作符 `?.` 与默认值降级 |
| `hasErrorBanner=true` | 模拟数据接口未 mock 或种子数据缺少关联字段 | 检查 `scripts/visual-check.sh` 中的 toy fixture 注入 |

