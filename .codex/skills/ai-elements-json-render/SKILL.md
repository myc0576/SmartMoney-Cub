---
name: ai-elements-json-render
description: 专门指导右侧复盘 Agent (AssistantPanel) 的架构重构与流式结构化渲染。集成 AI Elements 交互体系与 json-render 结构化协议，处理 UIMessage 多模态分片（思考链、工具调用卡片、审批流、结构化产物与 Markdown 代码高亮），杜绝 raw JSON 泄露与消息卡顿。
metadata:
  role: agent-ui-architect
  target: gui/src/components/AssistantPanel.tsx
  category: ai-frontend
  priority: 3
---

# AI Elements + JSON-Render (右侧复盘 Agent 重构指南)

本技能专门面向 **智能复盘助手 (Right-Side AssistantPanel)** 及其下游组件的深度重构与流式渲染优化。
统一采用 Vercel AI Elements 的设计范式与 `json-render` 结构化消息处理协议。

---

## 核心架构原则 (Architectural Principles)

1. **UIMessage 多分片 (Parts-Based) 规范协议**:
   - 彻底废弃单一臃肿的 `turn.text` 字符串拼装，全面迁移至标准 `UIMessage.parts` 数组架构：
     - `{ type: 'text', text: string }`：常规自然语言回答，集成高性能流式 Markdown 渲染。
     - `{ type: 'reasoning', text: string }`：深度思考链 (CoT / Thinking Process)，采用可折叠的手风琴式面板展示，带有微妙的动画与计时标签。
     - `{ type: 'tool-<name>', toolCallId, state, input, output }`：结构化工具调用卡片。
     - `{ type: 'artifact', artifactType, payload }`：生成的复盘报告、挑战者规则提案 (Rule Proposal)、交易对比图表等结构化产物。

2. **工具调用卡片全生命周期状态机 (Tool Call Lifecycle)**:
   - 针对金融量化复盘中的每一个工具调用（如 `search_trades`, `calculate_drawdown`, `propose_rule`）：
     - `call` (调用中)：呈现微妙脉冲呼吸动画与参数概览。
     - `output-available` (调用完成)：展示紧凑的结果摘要或图表，默认收起原始 payload，支持一键展开 JSON 详情。
     - `approval-requested` (等待人工确认)：如晋级挑战者规则、敏感状态修改等，提供原生的「确认批准 / 拒绝提案」操作按钮与审批表单。
     - `error` (执行失败)：展示结构化诊断错误（非红屏 crash）。

3. **流式增量渲染与打字机性能优化 (Streaming Performance)**:
   - 流式 Token 推送过程中，利用 `requestAnimationFrame` 或节流（Throttle）防止 React 高频全树 Re-render 造成 UI 卡死。
   - 底部视口跟随（Auto-scroll pinning）：仅在用户处于最底部时自动滚动，若用户向上翻阅历史消息，保持视口位置并提供「滚动到底部」小药丸按钮。

4. **金融量化业务专用结构化渲染器 (Domain-Specific Renderers)**:
   - **挑战者规则卡片 (Challenger Rule Proposal)**：渲染带晋级置信度、回测夏普比、逻辑条件、对比差异的专用卡片，支持直接一键「加入挑战者池」。
   - **交易案例证据卡片 (Trade Evidence Card)**：展示交易代码、成交时间、买卖方向（带红绿标签）、盈亏金额与对应 K 线跳转链接。
   - **错误与限额诊断卡片 (Quota & Rate-Limit Diagnostics)**：遇到 403 封闭边界、429 配额耗尽或服务下线时，精准呈现友好诊断图文，而非原始报错堆栈。

5. **会话控制与本地事件持久化 (Session Resilience)**:
   - 保证会话的断点续传与持久化存储：刷新浏览器、关闭右侧面板重新打开后，完整还原思考链与工具调用卡片。
   - 提供会话分支（Fork）、重试当轮（Retry）、停止生成（AbortController）的确定性控制按钮。

---

## 落地重构步骤 (Refactoring Checklist for AssistantPanel)

- [ ] **重构类型契约**：在 `gui/src/types.ts` 中确立 `UIMessage`、`UIMessagePart`、`ToolInvocationState`。
- [ ] **抽取独立组件**：
  - `gui/src/components/ai/MessageItem.tsx`：单条消息容器。
  - `gui/src/components/ai/ReasoningPanel.tsx`：折叠思考过程展示。
  - `gui/src/components/ai/ToolCallCard.tsx`：工具调用与审批交互。
  - `gui/src/components/ai/StructuredArtifactView.tsx`：挑战者规则/交易证据卡。
- [ ] **集成到 AssistantPanel**：替换旧有的无格式文本渲染，无缝衔接现有本地 SQLite/SSE 事件流。

