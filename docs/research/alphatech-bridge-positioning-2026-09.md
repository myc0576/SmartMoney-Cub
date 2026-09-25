# AlphaTech 中转站与 SmartMoney-Cub 桥接定位调研

日期：2026-09-25

## 结论先行

AlphaTech 不适合继续把“更多模型、更低价格、更稳定的 API 中转”作为主定位。这个市场已经被 one-api/new-api、LiteLLM、OpenRouter、Vercel AI Gateway、Cloudflare AI Gateway 以及大量中转站覆盖，单纯转发能力很难形成长期差异化。

更有价值的定位是：**面向 Agent 和团队的 AI 调用账本与证据网关**。它把一次业务运行中的模型调用、工具调用、数据来源、最终产物和费用，串成一条可以核对、追责、复盘的记录。

这会形成一个清晰的产品组合：

1. AlphaTech Gateway：统一入口、路由、鉴权、重试、配额和结算。
2. AlphaTech Ledger：跨供应商成本、预算、租户、团队、功能和任务的对账与归因。
3. AlphaTech Tool Hub：MCP/HTTP 工具注册、托管、权限、版本、调用计量和健康度。
4. SmartMoney-Cub：一个高价值的垂直证据应用，展示这套网关如何服务高敏感、强审计、只读的交易复盘场景。

这里的“访问全网痛点”不应被理解为无限抓取互联网，而应落实为一套可持续的痛点信号管道：公开论坛和 issue 的原始链接、客户工单、网关运行日志、账单差异、失败请求、工具调用失败和复盘结果都进入同一套证据模型。平台的价值是把信号变成可核对的产品决策，而不是只做搜索聚合。

## 已核实的痛点

### 1. 三方账单天然对不上

公开文档已经显示出结构性问题：

- OpenRouter 的 BYOK 文档说明，使用用户自带 key 的花费不计入其 guardrail 预算。
- Helicone 的迁移文档说明，网关侧费用不一定反映真实供应商成本。
- Vercel AI Gateway 的计费文档将平台成本与供应商账单分开说明。
- Linux.do 的中转站讨论中，用户直接指出中转商可能“对成本一无所知，很容易被误导”。
- Reddit 的中转站讨论把“比较余额和账目数字”、invoice、enterprise、SLA、private relay 并列为实际需求。

这不是一个单纯的价格展示问题。至少有三本账：供应商账、平台账、客户业务账。当前很多产品只解决其中一到两本，无法回答“这次 Agent 运行到底花了多少钱、为什么由这个团队承担、供应商账单是否一致”。

### 2. 用户愿意为稳定性和可见性付费

关于 OpenRouter 的公开讨论中，有用户明确表示自己不追求最低价格，而是需要“能用”，同时希望看到统计来监控用量。另一些用户因为付费线路更可靠而回到付费方案。

因此中转站的核心价值应从“便宜”提升为“可预期”：请求是否成功、延迟是否恶化、哪个上游在降级、余额是否异常、哪个任务在烧钱，都应能被解释。

### 3. 网关基础能力已严重同质化

多 provider 转发、OpenAI 兼容协议、基础日志和 key 预算已经有成熟开源项目覆盖。LiteLLM 还逐步覆盖 MCP 代理、多协议接入和基础花费追踪。单独再做一个兼容层，研发成本会进入价格竞争。

## 三种值得桥接的组合

### 组合 A：AI 成本账本与 Agent 运行审计

组成：现有 new-api 网关 + LiteLLM 或 OpenAI 兼容入口 + Langfuse/OpenTelemetry + 自有 Ledger 服务。

产品回答四个问题：

- 一次 Agent run 调用了哪些模型和工具？
- 每一步消耗了多少 token、时间、上游单位和平台额度？
- 费用应归属哪个租户、团队、功能、客户或任务？
- 平台账、供应商账和客户侧账单哪里不一致？

最小版本不需要重做网关。先为每次请求生成稳定的 run_id、trace_id、tenant_id、feature_id 和 tool_call_id，把上游响应中的 usage facts 原样保存，再由平台统一计算价格。插件只负责数据变换和上报事实，计费、重试、轮询、结算继续由 host 控制，这与现有 Task Plugin API v1 的边界完全一致。

### 组合 B：MCP 工具即服务

组成：MCP Registry + FastMCP/官方 MCP server + Docker MCP Gateway 或 LiteLLM Proxy + 权限、限流、健康检查与计量层。

核心差异不在“能不能接 MCP”，而在于：工具是否可审计、可撤销、可按租户计量、可按版本回放。现有方案通常把注册、运行时、代理和观测拆在不同项目里，缺少“发现、安装、授权、调用、计费、回滚”一条链。

最小版本只托管 3 类低风险工具：文档检索、网页内容抽取、结构化数据转换。每个工具都有来源、版本、权限声明、输入输出 schema、调用次数、失败率、延迟和费用。涉及交易或账户写入的工具不进入默认目录。

### 组合 C：垂直 Agent 证据工作台

组成：AlphaTech Ledger/Tool Hub + SmartMoney-Cub + 一个受限的本地 Agent adapter。

SmartMoney-Cub 不负责预测行情，也不负责下单。它负责把用户自己的成交、市场数据、复盘对话、工具输出和回测结果组织成可复核证据。AlphaTech 负责模型和工具的调用控制、身份、配额、成本与审计。

这是三个组合里最适合先做的一个，因为现有项目已经具备：

- agent_bridge 能力；
- 插件清单和生命周期；
- Evidence Envelope；
- decision_time 与 available_at 的时间可用性检查；
- READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE 安全边界；
- AlphaTech 平台 tenant 身份和 /trader 产品入口。

## 推荐定位

对外一句话：

> AlphaTech 是面向 Agent 工作流的可核对 AI 调用与工具运行平台：统一接入模型和工具，记录每一步证据，按真实业务归属成本。

首个付费切口：

> 给使用多个模型、多个工具和多个团队的企业，提供 AI 账单对账、Agent 成本归因、工具调用治理和可回放审计。

SmartMoney-Cub 是第一个垂直样板：

> 给交易复盘提供只读、可追溯、可回放的 Agent 证据工作台。

这样，中转站不再是 SmartMoney-Cub 的附属 API 供应商，而是它的运行控制面；SmartMoney-Cub 也不需要改变交易产品的安全承诺。

## Web SaaS 还是其他形态

建议采用“Web 控制台 + 兼容 API + 可选本地组件”的三层形态。

Web 控制台适合展示跨团队成本、账单差异、上游健康度、工具目录、权限和审计记录。API 兼容层保证现有客户端可以迁移，减少换网关的阻力。本地组件用于 SmartMoney-Cub 的离线复盘、敏感数据脱敏和本地 Agent 连接。

不建议第一阶段做纯浏览器里的大而全 Agent 平台。它会同时承担模型编排、工具安全、数据隐私、支付、工作流和用户体验，边界太宽。也不建议把 SmartMoney-Cub 的交易数据默认上传到云端；交易日志和证据包应保持本地优先，只上传脱敏后的 usage facts 或用户明确选择的复盘摘要。

## SmartMoney-Cub 的具体收益

### 网关侧新增四类事实

每次模型或工具调用至少记录：

    run_id, trace_id, tenant_id, agent_id, provider, model,
    tool_name, tool_version, usage_facts, started_at, finished_at,
    status, input_hash, output_hash

这些字段不应包含 API key、cookie、绝对路径、原始交易文件或未经脱敏的账户标识。SmartMoney-Cub 只消费需要的证据引用和 usage facts。

### 复盘侧保留三条边界

1. Agent 可以解释、提问、生成 challenger 候选和整理证据，不能自动晋级 champion。
2. 外部模型可以参与 review，但回测仍由确定性的本地 DSL 执行。
3. 任何工具结果都必须经过 provenance、时间可用性和安全声明检查；交易执行能力永远不进入插件能力清单。

### 第一批真正有用的页面

- 本次复盘消耗：模型、工具、耗时、失败重试、估算成本。
- 证据链：哪段日志、哪份行情、哪个工具结果支持了结论。
- 账单核对：平台成本、供应商 usage、租户额度三者差异。
- Agent 质量：重复调用、无效工具调用、超时、人工驳回和 challenger 采纳率。
- 数据边界：哪些内容留在本地，哪些摘要被发送给外部模型。

## 90 天落地顺序

### 第 1 阶段：两周，先把账记完整

在 new-api host 侧增加统一 correlation id 和 usage facts 事件；不改现有计费逻辑。做一个只读 Ledger 页面，能按 tenant、model、provider、task 和日期查看成本与失败率。

验收标准：同一请求可以从平台账单追到上游响应；重试不会重复结算；缺失 usage 时显示“未知”而不是猜价格。

### 第 2 阶段：三到四周，接入工具级计量

选 3 个低风险 MCP/HTTP 工具，建立工具目录、版本、权限、健康检查和调用记录。将 agent run -> tool call -> model call -> evidence 串成 trace。

验收标准：能按工具看调用次数、延迟、错误、租户归属和成本；工具升级后旧证据仍能回放。

### 第 3 阶段：四到六周，做 SmartMoney-Cub 样板

让 SmartMoney-Cub 的 agent_bridge 读取脱敏的运行证据，向本地 Evidence Envelope 写入 provider、模型版本、工具版本、时间和 hash。把复盘成本和证据链放进 /trader 的工作台。

验收标准：离线模式无网络也能打开已有证据；联网模式失败时不丢失复盘记录；所有输出继续携带 READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE。

## 需要主动验证的假设

下面几项应该用 5 到 10 个真实团队访谈或试用验证：

- 企业是否愿意单独为“AI 账单对账”付费，而不是把它视作网关附赠功能。
- 工具级计费更适合按调用次数、执行时间、数据量还是订阅套餐。
- SmartMoney-Cub 的第一批付费用户是半专业交易者、交易教练、prop firm，还是企业内部研究团队。
- 企业是否允许交易日志留在本地，同时把匿名 usage facts 上传到云端。
- 统一账本是否能覆盖用户自带 key、平台代付、免费额度和供应商异步计费等复杂情形。

## 证据与来源

- OpenRouter BYOK：<https://openrouter.ai/docs/features/byok>
- Helicone 迁移：<https://docs.helicone.ai/migrate/overview>
- Vercel AI Gateway 计费：<https://vercel.com/docs/ai-gateway/pricing>
- Linux.do 中转站生态讨论：<https://linux.do/t/topic/2659020>
- Reddit 中转站推荐讨论：<https://www.reddit.com/r/BuyFromHere/comments/1tedb2w>
- Reddit 轻量模型网关讨论：<https://www.reddit.com/r/LocalLLaMA/comments/1n2x4ws>
- Reddit OpenRouter 可靠性讨论：<https://www.reddit.com/r/SillyTavernAI/comments/o6zglu/is-openrouter-reliable-these-days/>
- LiteLLM：<https://github.com/BerriAI/litellm>
- IBM ContextForge：<https://github.com/IBM/mcp-context-forge>
- LeVo：<https://github.com/syxc/LeVo>
- SmartMoney-Cub：docs/trader-product.md、docs/trader-product-spec.md、docs/plugins.md、docs/agent-integration.md
- AlphaTech Task Plugin API：本地研究材料（未随仓库发布）

## 证据等级说明

公开 URL 是本轮调研中已取得的来源；论坛内容用于证明用户表达的痛点，不用于证明市场规模或付费率。子代理曾给出 TradeZella、TraderVue、TradesViz 等竞品和价格信息，但本报告没有把未经官方页面核实的价格写成事实。MCP 计量、Agent 成本归因和 SmartMoney-Cub 的商业付费意愿仍属于产品假设，需要通过真实试用和访谈收敛。
