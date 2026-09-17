---
name: workflow-cost-optimizer
description: Multi-Agent & developer workflow cost reduction engine. Enforces the 3 core principles (need-only context, zero irrelevant context, zero duplicated context) and 10 proven optimization techniques from real-world harness engineering, reducing token consumption by 50%-65%. Triggers on coding, architecture, testing, refactoring, or multi-agent dispatch tasks.
---

# Workflow Cost Optimizer (工作流成本与上下文优化引擎)

基于微信公众号实战沉淀（《靠这10个优化点，我们把Multi-Agent工作流成本降了50%以上》），旨在系统性消除研发过程中的 Context 臃肿与 Token 浪费，保证高交付质量的同时降低 50%~65% 推理开销。

---

## 3 大核心铁律 (The 3 Golden Principles)

1. **让 AI 只看到当前需要的上下文**：该加载的按需加载，绝不一次性全量常驻。
2. **减少无关的上下文**：不该看到的东西（跨领域 Schema、盲搜冗余文件），从源头隔离。
3. **减少重复的上下文**：同一份信息在多轮对话中不反复计费，最大化命中 KV Prompt Cache。

---

## 规模预判分流矩阵 (S / M / L Scale Triage)

动手写代码或拆分 Agent 之前，必须先判断任务规模。**严禁为小需求无谓启动多 Agent（系统提示词乘数开销远超收益）**：

| 模式 | 判定标准 | 推荐执行策略 | 上下文边界 |
|---|---|---|---|
| **S 模式 (Small)** | ≤ 3 个文件修改，单点 Bug 修复、局部单测、配置微调 | **单 Agent 直接闭环** | 不派生子 Agent，直接基于已有知识与精准定位修改并验证 |
| **M 模式 (Medium)** | 跨组件联动、接口契约扩展、4~10 个文件修改 | **分 Wave 单会话阶段推进** | Wave 1 方案/契约 -> Wave 2 编码 -> Wave 3 自动化门禁验证；状态外化至文件 |
| **L 模式 (Large)** | 架构重构、全新子系统开发、> 10 个文件 | **多 Agent 调度 (TL + 垂直子 Agent)** | 专职 TL 调度，子 Agent 专职单一领域（跑完即销毁，打断历史滚雪球） |

---

## 10 大优化落地执行规约 (The 10 Action Rules)

### 1. 渐进式披露 (Progressive Disclosure - L2/L3 分层)
- 本 SKILL.md 只保留骨架（职责、分流标准、核心检查清单）。
- 具体规则、模板与技术细节一律外置到 `references/` 目录，需要时通过精准 `read_file` 加载。详见 [references/progressive-disclosure.md](references/progressive-disclosure.md)。

### 2. 确定性操作由脚本执行 (Deterministic CLI over LLM Trial)
- 严禁 LLM 在终端中反复试错拼接端口、参数、启动命令与数据库连接串。
- 统一使用仓库提供的确定性管理脚本：
  ```bash
  ./build/dev-env.sh test [all|agent|bridge|replica|web]
  ./build/dev-env.sh build [all|web|replica]
  ./build/dev-env.sh verify
  ```

### 3. MCP / 大数据获取子 Agent 化 (Sub-Agent for Heavy Payloads)
- 当面临大型第三方 JSON、CAD 原始几何实体、设计稿万行节点树等海量数据源时：
  - 严禁由长生命周期主会话直接读取原始 Payload。
  - 委派短命子 Agent 或独立脚本提取**紧凑结构化摘要**，主流程只吸收摘要。

### 4. 长期记忆按需索引加载 (INDEX.md Lightweight Routing)
- 严禁对 `docs/` 目录或项目文档进行全量读入或粗暴全文扫描。
- 必须先阅读轻量级目录索引 [docs/INDEX.md](docs/INDEX.md)（仅几十行表格），根据分类与标签计算相关度，仅对 Top 1~2 篇针对性读取。

### 5. 单 Agent 按需拆分为角色子 Agent (Decoupled Lifecycles)
- 中大型需求按前后端/测试/审查划分，子 Agent 携带独立任务执行，完成后立即销毁，彻底终结 Append-only 历史堆叠。

### 6. Agent 专属配置与模型分层 (Tool Whitelist & Model Tiering)
- 子 Agent 仅开放最小必要工具白名单（后端开发不暴露 CAD/UI MCP；跑测试不暴露生成类工具）。
- 机械性强、重复轮次多的审查/测试执行，优先路由至高性价比轻量模型。

### 7. 代码图谱替代盲搜 (Code Graph over Blind Grep)
- **禁止在不清楚结构时直接用 grep 全仓大面积盲搜**（容易带入数十个无关文件的无用行进上下文）。
- 先通过代码图谱定位：
  ```bash
  ./build/dev-env.sh graph query "<核心类名或概念>"
  ```
  详见 [references/code-graph-guide.md](references/code-graph-guide.md)。

### 8. 稳定前缀与状态外化 (Prompt Cache & Externalized State)
- **稳定前缀优先**：系统指令与稳定规则排在 Prompt 前端，变动参数与动态任务文档统一后置，确保最大化复用服务端 KV Cache。
- **状态外化**：进度看板、DoD 勾选记录、跨轮排查事实一律写入文件（如 `ledger.md` 或 `progress.md`），每轮唤醒先读文件恢复现场，不在对话历史中累积输出整屏看板。

### 9. 避免重复加载 Skill (Upstream Once, Pass via Artifact)
- 上游规划阶段收集完架构与规范后，沉淀到项目方案文档中；下游各阶段直接读取产物文档，不再重复调用 `use_skill` 重新加载数百行 SKILL.md。

### 10. RTK 压缩 CLI 输出与工具调用并行化 (RTK & Concurrent Tools)
- 终端操作前缀 `rtk`（如 `rtk git status`, `rtk npm test`），过滤 60%~90% 噪音输出。
- 无依赖关系的工具调用在同一轮消息并发发起，避免串行轮次累积历史。详见 [references/rtk-guide.md](references/rtk-guide.md)。
