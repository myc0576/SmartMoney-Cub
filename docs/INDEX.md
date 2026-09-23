# Smartmoney-Cub 设计与技术文档轻量索引 (Documentation Index)

> **按需加载原则 (Progressive Disclosure)**：本目录包含 29 篇详细设计文档。
> **严禁盲目全文检索或全量载入 context**。先通过本索引表格定位目标领域的 1~2 篇文档，再有针对性地按需读取。

## 核心文档索引表

| 领域分类 | 文档名称 (大小) | 核心内容提要 | 何时查阅 |
|---|---|---|---|
| Agent集成指南 | [agent-integration.md](agent-integration.md) (4.8KB) | 大语言模型 Provider 接入、API Key 管理与环境配置 | 添加或修改 LLM Provider (DeepSeek/OpenAI/Anthropic) 时 |
| Agent执行循环 | [agent-loop.md](agent-loop.md) (1.7KB) | ReAct 循环、工具调用轮次控制与超时熔断 | 排查智能体死循环或工具调用异常时 |
| 整体系统架构 | [architecture.md](architecture.md) (6.7KB) | 核心数据管道、本地离线模式、Workbench服务与GUI架构 | 需要掌握系统全局数据流与模块依赖时 |
| 多源收敛设计 | [convergence.md](convergence.md) (3.5KB) | 多模态数据输入与统一时序对齐收敛机制 | 调试时序数据对齐或多源冲突时 |
| 封面与视觉规范 | [cover-design.md](cover-design.md) (1.1KB) | 视觉资产设计规范与封面尺寸定义 | 设计或修改品牌视觉资产时 |
| 交易决策Schema | [decision-schema.md](decision-schema.md) (5.3KB) | DecisionEnvelope、invalidation条件、time stop与数据质量口径 | 修改或验证决策输出数据结构时 |
| 规则演化机制 | [evolution-loop.md](evolution-loop.md) (0.8KB) | Challenger -> Champion 规则晋级流程与人工确认要求 | 修改策略优化与进化逻辑时 |
| Harness核心契约 | [harness-contract.md](harness-contract.md) (3.0KB) | 离线运行、只读市场数据、安全铁律、无订单无撤单声明 | 开发或修改核心接口与安全边界时 |
| 全球复盘与调研决策 | [global-journal-decisions.md](global-journal-decisions.md) | 模式归因、回放用途、只读账户连接覆盖与验证限制 | 检查全球化功能的产品依据及实际边界时 |
| 外部服务集成 | [integrations.md](integrations.md) (12.1KB) | 27项收录开源项目矩阵、只读连接器与格式转换适配器 | 新增数据导入或只读市场连接器时 |
| 开源维护与上游贡献 | [open-source-maintenance.md](open-source-maintenance.md) (6.6KB) | Fork、上游 PR、合并后同步与持续维护检查清单，含 Awesome Jev 收录记录 | Fork、公开发布、提交或更新上游 PR 时 |
| Jev生态与评测基准 | [jev-ecosystem.md](jev-ecosystem.md) (5.9KB) | Jev 四轨金融审查架构、JevBackend协议与finance-jev-v1基准评测指南 | 接入Jev审查后端或运行金融基准评测时 |
| 记忆循环系统 | [memory-loop.md](memory-loop.md) (1.1KB) | 短期会话上下文与长期交易日志经验检索 | 排查交易记忆召回或历史对账时 |
| 设计哲学 | [philosophy.md](philosophy.md) (3.7KB) | Smartmoney-Cub 设计理念、核心权衡与不可妥协边界 | 做重大设计决策或架构评审时 |
| 插件开发指南 | [plugin-development.md](plugin-development.md) (6.0KB) | 如何开发、测试和打包第三方交易复盘与分析插件 | 创建新插件或编写测试用例时 |
| 插件体系全景 | [plugins.md](plugins.md) (11.7KB) | 内置插件清单、真实安装向导通道、生命周期钩子与外部扩展机制 | 开发、安装或调试特定插件时 |
| 数据隐私保护 | [privacy.md](privacy.md) (3.8KB) | 用户个人交易日志本地化、凭据隔离与脱敏机制 | 处理用户敏感数据或审计数据泄露时 |
| 公开与私有知识库边界 | [public-vs-private-quantkb.md](public-vs-private-quantkb.md) (0.9KB) | 开源核心与专有策略知识库的隔离准则 | 涉及敏感策略或知识库分类时 |
| 复盘智能体规范 | [review-agent.md](review-agent.md) (6.1KB) | Review Agent 决策循环、提示词与多模态复盘交互规则 | 优化或调试 AI 对话复盘引擎时 |
| 复盘工作台规范 | [review-workspace.md](review-workspace.md) (4.8KB) | 本地工作台 Web 服务、API 端点、组件通信与离线持久化 | 开发前后端交互或工作台功能时 |
| 复盘工作台中文规范 | [review-workspace.zh-CN.md](review-workspace.zh-CN.md) (4.9KB) | 工作台前端与后端通信规范的中文说明 | 中文查阅工作台协议时 |
| 安全与风控规范 | [safety.md](safety.md) (1.5KB) | READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE 强制声明与前置拦截 | 添加新工具、新市场源或模型集成时 |
| 分享数据包规范 | [share-pack.md](share-pack.md) (2.0KB) | 匿名化交易分享包打包、签名与去敏感化标准 | 实现或调试交易复盘导出/分享时 |
| Trader API 接口 | [trader-api.md](trader-api.md) (8.6KB) | REST API 契约、请求与响应体格式、离线状态响应 | 前后端联调或调用本地服务时 |
| Trader Oracle 预测机 | [trader-oracle.md](trader-oracle.md) (4.4KB) | 回测、前瞻偏差防护（available_at验证）与胜率检验 | 调试策略验证或指标回测机制时 |
| 交易员产品规格说明 | [trader-product-spec.md](trader-product-spec.md) (3.8KB) | 产品设计目标、核心用例、数据流与技术栈约束 | 对齐产品交互与业务逻辑时 |
| 交易产品全景 | [trader-product.md](trader-product.md) (8.0KB) | 功能特性全景、用户体验闭环、多账户与多资产支持 | 宏观了解产品形态与交付范围时 |
| TradingAgents适配器 | [tradingagents-adapter.md](tradingagents-adapter.md) (5.3KB) | TradingAgents 框架通信协议与数据结构映射 | 与外部 TradingAgents 库联调时 |
| 用户操作指南 | [user-guide.md](user-guide.md) (1.2KB) | 客户端安装、启动、复盘与日志导出操作流程 | 编写帮助文档或用户指引时 |
| 版本管理与兼容性 | [versioning.md](versioning.md) (4.3KB) | SemVer 语义化版本规范与数据迁移方案 | 准备发布新版本或迁移数据库模式时 |

## 推荐查阅路径 (Workflow Routing)

1. **核心安全与只读契约**：harness-contract.md -> safety.md -> privacy.md
2. **复盘智能体与模型集成**：review-agent.md -> agent-integration.md -> agent-loop.md
3. **本地工作台与API**：review-workspace.md -> trader-api.md -> decision-schema.md
4. **插件与扩展系统**：plugins.md -> plugin-development.md -> tradingagents-adapter.md
5. **Fork 与上游贡献**：open-source-maintenance.md -> versioning.md -> harness-contract.md
