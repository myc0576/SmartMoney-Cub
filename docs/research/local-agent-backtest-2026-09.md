# 本地 Agent 接入与回测竞品调研（2026-09）

## 结论

SmartMoney-Cub 适合采用“受限本地 Agent 适配器 + 自有回测 DSL”的组合。Agent 可以帮助解释交易日志、生成候选复盘结论和提出 challenger 规则；回测仍由本地确定性运行时执行。外部 Agent、Qlib 或 Backtrader 都不应获得下单、撤单、账户修改、券商自动化或任意文件访问能力。

OpenCodex 可以作为可选的本地 provider proxy 研究对象，但公开资料没有证明它已经适配 SmartMoney-Cub 的复盘协议。Qlib 和 Backtrader 更适合作为离线研究适配或导入导出边界，不能直接替换本仓库的时间可用性校验和安全契约。

## 证据等级与仓库边界

- **已验证事实**：来自项目契约、官方仓库 README 或官方文档页面的直接内容。
- **设计建议**：根据这些事实和本仓库约束推导出的方案，不代表功能已经实现。
- **未核验**：本轮没有足够官方原文支持，因此不把产品宣传或印象写成事实。

本仓库的安全声明必须保持为 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`。复盘 Agent 只能读取复盘数据，并提出 challenger rule；champion 晋级必须由用户明确确认。回测输入必须是确定性、可审计的本地数据，且任何 `available_at > decision_time` 的数据都必须拒绝。非静默观察还必须带有 `invalidation`、`time_stop`、`give_up`、`data_source`、`available_at` 和 `data_quality`。

## 本地 Agent 接入

### OpenCodex：已验证事实

官方仓库 README 将 `lidge-jun/opencodex` 描述为本地 provider proxy，并说明可以通过 `ocx start` 启动；README 给出的默认本地 dashboard/proxy 地址是 `http://localhost:10100`。README 声称它可以在 Codex Responses API 与其他 provider 协议之间转换，并提到 streaming、tool calls、reasoning tokens 和 images 的双向转换。

README 还列出 Codex、Claude Code、Claude Desktop、Grok Build 等客户端，给出 npm 包 `@bitkyc08/opencodex`、Node 18+ 要求、provider 配置和模型选择说明，并提到默认绑定 `127.0.0.1:10100`、可用 Docker Compose 启动以及 healthz/readyz。以上是上游 README 的文档事实；本报告没有把它们当作本仓库已经运行验证的结果。

来源：

- <https://github.com/lidge-jun/opencodex>
- <https://raw.githubusercontent.com/lidge-jun/opencodex/main/README.md>
- <https://opencodex.me/>
- <https://www.npmjs.com/package/@bitkyc08/opencodex>

### 对 SmartMoney-Cub 的接入建议

1. 增加受限的 `local-agent` 适配层，只允许预先登记的本地客户端或 `localhost` proxy。用户不能直接输入任意 command、argv、环境变量或远程 endpoint。
2. 统一输入为脱敏、结构化的 review envelope；只发送复盘所需的 journal 摘要、证据引用和策略元数据，不发送凭据、账户标识、绝对路径、附件、data URL、base64 或原始交易文件。
3. 只解析约定的 JSON/SSE 输出。超时、取消、非零退出、协议不兼容和输出无法校验都要呈现为明确错误；stderr 不应直接作为业务结论展示。
4. 将状态拆成 `not_detected`、`detected`、`configured`、`protocol_incompatible`、`disabled` 和 `error`。检测到可执行文件不等于已连通，也不等于支持 streaming 或 SmartMoney-Cub review envelope。
5. 不自动静默切换到其他 Agent。用户在复盘助手中选择 Agent 后，应显示实际 provider、模型、版本、连接状态和本次会话的审计记录。
6. Agent 输出必须经过 schema、provenance、时间可用性和安全声明校验；策略建议只能进入 challenger，不能自动修改 champion。

这些建议是设计推断。OpenCodex 的公开资料没有证明其 CLI 输出天然符合 SmartMoney-Cub 的 review envelope，也没有证明它会自动隔离本仓库数据。因此“识别到客户端”只应驱动配置提示，不能直接宣称已完成接入。

## 回测竞品证据

### Qlib

**已验证事实**：Microsoft 的 Qlib README 将其描述为面向 AI 的量化投资平台，覆盖数据处理、模型训练和回测，并列出 alpha seeking、risk modeling、portfolio optimization、order execution 等研究链路。README 说明组件是松耦合的，可以单独使用；官方文档提供 strategy、data 等组件说明，并区分 offline 和 online mode。README 当前列出 Python 3.8 至 3.12 支持。

来源：

- <https://github.com/microsoft/qlib>
- <https://raw.githubusercontent.com/microsoft/qlib/main/README.md>
- <https://qlib.readthedocs.io/en/latest/>
- <https://qlib.readthedocs.io/en/latest/component/strategy.html>
- <https://qlib.readthedocs.io/en/latest/component/data.html>
- <https://arxiv.org/abs/2009.11189>

**设计建议**：不要把 Qlib 全量嵌入交易者的点击路径。可以提供可选的、离线运行的 Qlib export/import adapter，用于研究人员导出数据或导入经过审计的结果。导入前必须重新做 schema 校验、数据时间校验、数据质量记录和安全声明补充。Qlib 文档中的 order execution 能力只能视为研究/模拟概念，不能进入 SmartMoney-Cub 的执行路径。

### Backtrader

**已验证事实**：Backtrader 官方文档以 `Cerebro` 和 `Strategy` 作为核心文档入口；官方站点也将这两部分作为主要使用概念。可确认的证据支持“策略定义 + 回测运行器”的用户心智模型，但本报告没有据此推断其全部 API 或部署特性。

来源：

- <https://www.backtrader.com/>
- <https://www.backtrader.com/docu/cerebro/>
- <https://www.backtrader.com/docu/strategy/>

**设计建议**：借鉴分层，把 `Strategy` 转成交易者可填写的表单，把 `Cerebro` 类运行配置收敛为数据区间、周期、成交时机、手续费、滑点、仓位和退出条件。不要允许用户提交任意 Python 策略代码，也不要把 Backtrader 的 broker/execution API 暴露到本仓库运行路径。若未来适配，应只接受受限 DSL 或预注册策略模板，并把结果转换回本仓库的确定性 outcome schema。

### TradingView 与 Composer

本轮只保留官方入口作为后续竞品核验起点，没有把具体产品能力写成已验证事实。原因是当前检索没有取得足够稳定、可引用的官方策略编辑器、回测器、组合配置或自动化文档原文；不应凭产品印象断言其功能、限制或安全边界。

入口：

- <https://www.tradingview.com/>
- <https://www.tradingview.com/support/>
- <https://www.composer.trade/>

后续核验应优先查官方帮助中心和产品文档，并分别记录：策略表达方式、数据时间规则、费用/滑点模型、结果指标、是否支持代码、是否存在执行或券商连接，以及数据和策略是否可导出。

## 可落地路线

1. 保留 SmartMoney-Cub 当前 JSON strategy DSL，先把它包装成交易者表单：标的范围、周期、指标、入场条件、加仓/减仓、止损止盈、持仓上限、成交时机、费用和滑点。
2. 表单生成 DSL，并在提交时返回字段级错误；不允许未知字段被静默忽略。用“买入条件”“卖出条件”“持有多久”“每次投入多少”这样的交易者语言展示参数，底层字段只在高级详情中显示。
3. 回测结果至少显示样本数量、总收益、最大回撤、胜率、Profit Factor、费用和滑点影响、数据源、可用时间和数据质量；同时明确“研究模拟”标签。
4. Agent 只负责解释、复盘和生成 challenger 候选，回测运行器负责确定性执行。Agent 生成的策略先经过 DSL、provenance、anti-lookahead 和安全声明校验，再允许用户点击运行。
5. 先做一个最小本地 Agent adapter：固定 provider id、模型、版本、协议能力和健康状态；输入输出经过 schema 校验和本地审计。OpenCodex 可作为 provider proxy 试验项，Codex/Claude Code 等本地客户端可作为后续适配项，但不能把客户端存在误认成协议兼容。
6. Qlib/Backtrader 先做离线 PoC 和结果转换，不放入默认安装和默认点击路径；任何外部结果都必须重新通过本仓库的数据时间和只读安全检查。

## 风险与未验证项

- OpenCodex 的 provider/proxy 能力来自上游 README 自述，本轮未在 SmartMoney-Cub 中运行验证。
- 外部 CLI 没有被证明统一支持 SmartMoney-Cub 的 review envelope、challenger schema 或审计格式。
- 当前仓库已有 Agent 检测/选择相关界面或元数据时，不应把 detected 显示成 streaming/protocol compatible；真正的本地 CLI 路由仍需独立实现和验证。
- Qlib 和 Backtrader 的依赖体积、数据格式和结果语义尚未完成 PoC。
- TradingView/Composer 的具体能力在本轮未完成官方文档核验。
- 外部产品的宣传内容不构成本仓库的安全保证；所有接入都必须服从 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`。

## URL 清单

- OpenCodex: <https://github.com/lidge-jun/opencodex>
- OpenCodex README: <https://raw.githubusercontent.com/lidge-jun/opencodex/main/README.md>
- OpenCodex site: <https://opencodex.me/>
- OpenCodex npm: <https://www.npmjs.com/package/@bitkyc08/opencodex>
- Qlib: <https://github.com/microsoft/qlib>
- Qlib README: <https://raw.githubusercontent.com/microsoft/qlib/main/README.md>
- Qlib docs: <https://qlib.readthedocs.io/en/latest/>
- Qlib strategy docs: <https://qlib.readthedocs.io/en/latest/component/strategy.html>
- Qlib data docs: <https://qlib.readthedocs.io/en/latest/component/data.html>
- Qlib paper: <https://arxiv.org/abs/2009.11189>
- Backtrader: <https://www.backtrader.com/>
- Backtrader Cerebro docs: <https://www.backtrader.com/docu/cerebro/>
- Backtrader Strategy docs: <https://www.backtrader.com/docu/strategy/>
- TradingView: <https://www.tradingview.com/>
- TradingView support: <https://www.tradingview.com/support/>
- Composer: <https://www.composer.trade/>
