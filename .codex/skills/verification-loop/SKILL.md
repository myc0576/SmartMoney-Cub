---
name: verification-loop
description: Deterministic verification gate loop. Forces running builds, type checks, linting, test suites, and contract audits before completing any code changes. Disallows completion without fresh execution evidence.
---

# Verification Loop (确定性门禁循环)

## 核心铁律 (The Iron Law)

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
（无当轮最新执行证据，严禁声明任务完成）
```

只要修改了任何代码或配置，在宣称“修复成功”、“测试通过”或“完成交付”之前，必须强制完整运行当前工作区的自动化验证流水线。

---

## 分级门禁流水线 (Gate Pipeline)

任何代码提交或任务终结，必须自上而下通过以下门禁。前序步骤失败时立即短路，进入修复模式：

```
Gate 1: 静态检查 (Syntax / Formatting / Lint)
   |     - 确保无低级语法错误、无死代码、无未导入变量
   v
Gate 2: 类型与编译检查 (Type Check / Compile)
   |     - 确保编译通过、类型契约无破坏 (tsc / mypy / dotnet build)
   v
Gate 3: 领域安全与契约审计 (Domain Contract & Safety Audit)
   |     - 运行项目特有的安全合规脚本与契约检查 (如 doctor / safety check)
   v
Gate 4: 自动化测试套件 (Test Suite - Unit & Regression)
   |     - 执行单元测试与回归测试，必须 100% 通过 (0 failures, 0 errors)
   v
Gate 5: 端到端与产物自检 (Build Artifact & Smoke Test)
         - 确保关键入口或产物存在且可用，无构建损毁
```

---

## 门禁执行协议 (Execution Protocol)

每次准备结束任务或提交 PR 前，必须执行如下 4 步：

1. **IDENTIFY**: 确认能确凿证明代码正确性的全部命令集合。
2. **RUN**: 完整、全新地在终端中执行这些命令（不依赖历史记忆）。
3. **READ**: 读取完整输出，检查 exit code 与错误统计。
4. **VERIFY & REPORT**: 
   - 若失败：如实引用报错片段，进入修复分支；
   - 若通过：在最终回答中附带关键执行摘要（通过数量、耗时、退出码）。

---

## 修复与振荡防御 (Anti-Thrashing)

当某一门禁失败时：
1. **抓取精准堆栈**：不要泛泛猜测，定位到抛出异常的具体文件与行号。
2. **针对性修复**：仅修复引起报错的本质原因，避免过度重构引入新变量。
3. **全量重新回归**：修复后必须从 Gate 1 重新跑完整条流水线，防止“按下葫芦浮起瓢”（修复当前报错却导致既有测试回归失败）。
4. **单轮严禁假装通过**：绝不允许在报告中用“应该可以通过”代替真实的终端运行日志。

