# SmartMoney-Cub 增长与差异化

2026-11-23 · 按 DevFest 2026 Builder 三方向审视产品价值、结构演进和交付维护。产品假设是让盘后有成交记录、愿意改进交易流程的用户，从一条记录追到当时可用的证据，再复算规则的表现。GitHub 快照为 **26 stars、1 fork、20 个 topics**。市场和执行持续只读，用户可以写入自己的日志。安全声明为 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`。[仓库元数据](https://api.github.com/repos/myc0576/SmartMoney-Cub) · [项目契约](../harness-contract.md)

## 产品化

### 竞品地图

开源数据为当日 GitHub stars / forks，商业产品采用官网自报口径。数字只能用于观察分发和采用信号，各产品的活跃用户规模无法从这些数字直接推导。

| 项目 | 定位与公开采用信号 | 对方更强的环节 | SmartMoney-Cub 的结构差异 | 来源 |
| --- | --- | --- | --- | --- |
| TradingAgents | 多角色 LLM 市场研究，123,631 / 23,675 | 分析师分工、多空辩论、标的研究与回测生态 | 主对象是用户已有成交、决策记录和复盘证据，规则更新有独立审批 | [项目](https://github.com/TauricResearch/TradingAgents) |
| FinRobot | 金融 Agent 研究框架，8,469 / 1,431 | 财报/估值工作流、跨模态研究和开发者用例 | 用同一证据链串起日志、D1/D3 结果、复算与规则状态 | [项目](https://github.com/AI4Finance-Foundation/FinRobot) |
| OpenBB | 金融数据平台，75,687 / 7,894 | 供应商覆盖、标准查询、数据分发 | 核心离线可运行，数据适配器把来源和可用时间交给复盘校验 | [项目](https://github.com/OpenBB-finance/OpenBB) |
| TradeNote | 自托管开源日记，985 / 288 | 成交入库后按日浏览、打标、统计，使用场景直接 | 日志之外有可回放的证据包、时点校验和候选规则治理 | [项目](https://github.com/Eleven-Trading/TradeNote) |
| Trading-Journal-AI | 本地优先 AI 日记，2026-09 创建，128 / 50 | 自然语言和手写日记匹配成交，提取策略和情绪，录入省力 | 本地优先和 AI 已是同类能力，项目可用时点防线、审查轨迹和可复算基准证明差异 | [项目](https://github.com/simonro/Trading-Journal-AI) |
| RoninFlow | 自托管期货等交易日志，2026-11 创建，14 / 4 | ATAS 等工具的同步路径、prop firm 规则和风险档位 | 用户导入或授权只读接入，AI 产物进入用户可审查的证据和规则流程 | [项目](https://github.com/coreyheyman/roninflow) |
| Tradervue | 商业成交日志，官网展示约 20.8 万交易者 | 券商导入、多时间尺度交易标记图和报表 | 离线重放的对象同时包含时点证据和规则评估 | [官网](https://www.tradervue.com/) |
| TraderSync | 商业 AI 复盘平台，官网称 30 万+交易者 | Cypher、市场回放模拟器、多资产导入 | 复盘结果可追到证据、评估器和明确的规则升级状态 | [官网](https://tradersync.com/) |
| Edgewonk | 商业行为复盘，官网称服务超十年、数千交易者 | 心理日志与纪律指标、Edge Finder | 把改进规则交给 challenger 评估和人工确认，保留状态变更记录 | [官网](https://edgewonk.com/) · [采用口径](https://edgewonk.com/pricing) |
| TradeZella | 商业 AI 日志与回放，官网称 10 万+交易者、500+ 连接 | 券商与 prop firm 接入、回放和社区整合 | 用离线样例、开放证据格式和可核验 benchmark 降低验证成本 | [官网](https://www.tradezella.com/) |
| daily_stock_analysis | 2026 A 股起家的 AI 市场简报，74,077 / 58,267 | 多市场自选、每日摘要、飞书等现成分发 | 产品起点是用户的历史记录与可用时点，市场数据供复盘取证 | [项目](https://github.com/ZhuLinsen/daily_stock_analysis) |
| Vibe AStock | 2026 A 股短线复盘工作台，1,116 / 299 | 连板、题材、情绪等 A 股场景深度，集成交易日志 | 核心离线、证据可移植，规则变更由确定性评估及人工审批控制 | [项目](https://github.com/simonlin1212/vibe-astock) |
| UZI-Skill | 2026 股票分析 Skill，7,681 / 1,070 | 中文使用路径、角色化多维数据解读、输入哈希绑定 | SmartMoney-Cub 把哈希、来源、可用时点和规则治理用于个人复盘证据 | [项目](https://github.com/wbh604/UZI-Skill) |

### 差异化赌注

各项为 1–5 分。价值按用户复盘收益打分，防御性按端到端复刻难度打分，成本按维护和验证负担打分，5 代表高。分数是排序假设。

| 赌注 | 价值 / 防御性 / 成本 | 最小价值验证 |
| --- | --- | --- |
| 只读执行面的可验证信任 | 5 / 3 / 2 | 无账户和模型密钥完成 toy 复盘，用户能准确复述日志写权限与市场权限 |
| 证据的时点溯源 | 5 / 5 / 3 | 评审者能从结论定位来源、质量与可用时间，复算并识别发布日期晚于决策的案例 |
| 挑战者 → 冠军规则治理 | 4 / 5 / 3 | 用户能指出阻断升级的具体指标，人工确认前后可以用审计记录核对状态 |
| 可复算的金融审查 benchmark | 4 / 4 / 4 | 第三方复现基线图表、失败样本与覆盖率。公开成本、延迟、区间和运行指纹 |
| 可移植的脱敏证据包 | 4 / 4 / 2 | 两个独立环境复跑相同的 toy 包，匹配哈希、结果和错误码 |

### 九项能力体检

| 方向 | 能力（关键词） | 判定与文件证据 |
| --- | --- | --- |
| 产品化 | 需求洞察（用户/场景/痛点） | **弱**。规格有交易记录、盘后复盘等场景，仍缺首次价值路径的访谈和行为基线。[trader-product-spec.md](../trader-product-spec.md) |
| 产品化 | 体验设计（路径/视觉交互/反馈） | **弱**。导入、日志、报告已有入口，零数据用户仍需自己串起导入→证据→复盘。[App.tsx](../../gui/src/App.tsx) · [ImportView.tsx](../../gui/src/views/ImportView.tsx) |
| 产品化 | 价值验证（效果/代价/心智） | **缺失**。评测记录了模型效果、成本和时延，仓库未见复盘用时、完成率或理解安全边界的用户实验。[benchmark/runner.py](../../src/smartmoney_cub_harness/benchmark/runner.py) · [评测报告](../../assets/benchmark/run.json) |
| 架构化 | 职责划分（分工/模块/边界） | **强**。HTTP dispatch、领域服务、存储与评测适配器的核心边界可定位，WorkbenchService 的跨域职责见下文。[trader/api](../../src/smartmoney_cub_harness/trader/api) · [jev](../../src/smartmoney_cub_harness/jev) |
| 架构化 | 协作设计（契约/依赖/状态） | **弱**。业务操作表和审查事件已有契约，HTTP、流式 Agent、插件结果仍由不同入口各自翻译。[control_operations.py](../../src/smartmoney_cub_harness/control_operations.py) · [plugins/envelope.py](../../src/smartmoney_cub_harness/plugins/envelope.py) |
| 架构化 | 演进设计（变化/耦合/权衡） | **强**。规则审批允许从评估过的候选逐步升级，Jev Protocol 支持替换实现。[governance.py](../../src/smartmoney_cub_harness/governance.py) · [jev/__init__.py](../../src/smartmoney_cub_harness/jev/__init__.py) |
| 工程化 | 交付实施（实现/构建/发布） | **强**。Python 打包、npm 启动和 Release 工作流已有入口，正式 GitHub 发布节奏仍有空档。[pyproject.toml](../../pyproject.toml) · [release.yml](../../.github/workflows/release.yml) · [Releases](https://github.com/myc0576/SmartMoney-Cub/releases) |
| 工程化 | 质量保障（验收/测试/回归） | **强**。Doctor、安全声明、测试和 CLI/HTTP 一致性已有回归，真实用户首轮体验尚待专项测量。[verify.sh](../../scripts/verify.sh) · [test_cli_http_parity.py](../../tests/test_cli_http_parity.py) |
| 工程化 | 运行维护（观测/诊断/恢复） | **弱**。会话事件持久化并支持恢复，多个渠道的错误码、状态和重试语义缺统一契约。[store.py](../../src/smartmoney_cub_harness/store.py) · [agent/runtime.py](../../src/smartmoney_cub_harness/agent/runtime.py) |

**优先修复五项产品缺口**

1. **Neon + 后端**把零凭据体验压缩成一个可复现的 toy 路径：35 秒 GIF 讲清输入、证据和产物，试用目标为 5 位新手中至少 4 位在 5 分钟内完成首次复盘。
2. **后端 + Neon**把导入预览做成可修复反馈：定位缺列、格式、时区或重复行，再重试其中一行，三份代表性 toy CSV 均可获得明确结果。
3. **Neon + 后端**在复盘结论旁显示来源、可用时间、质量标记和只读说明。用一道判断题检查试用者能否辨认一条晚到证据和它的阻断原因。
4. **后端 + Neon**从规则页直达失败样本及确认记录。用一条达标、一条被阻断的 toy 候选，核验用户能解释为什么升级以及谁确认。
5. **Neon + 后端**先访谈 5 位有复盘习惯的用户，记录首次完成率、复盘耗时与 7 日自愿回访。采集自报耗时、路径和错误类别，交易内容留在用户本地。

## 架构化审计

以 MVC 图里的统一消息作为对照。View 呈现与收集输入，Controller 驱动状态和权限，Model 定义业务数据与不变量。各渠道 adapter 输入请求、输出 event/result/error，底层共享服务运行的是日志、取证、评估与回放。

| 图中职责 | 当前落点 | 边界与耦合 |
| --- | --- | --- |
| View | `gui/src` 渲染、`gui/src/api.ts` 封装 HTTP/SSE、`cli.py` 与 `control_cli.py` 做 CLI 呈现 | CLI 和 GUI 的列表/错误有一致性测试，SSE 仍需前端识别多种事件形状。 |
| Controller | `trader/api/routes.py` 的 `Request` / `dispatch`；`control_operations.py` 的 `Operation`；`control_runtime.py`、`workbench/server.py`、`agent/runtime.py` | `ControlRuntime._invoke` 一路构造 HTTP 形状并调用本地 dispatch，另一路按 `inspect.signature` 绑定 Workbench 方法。Workbench 同时组合服务、导入、审查会话和权限，处理器与业务边界容易一起变化。 |
| Model | `schemas.py`、`review_contracts.py`、`manifest.py`、`registry.py` / `governance.py`，以及 `jev/questions.py` 的 `JevQuestion` / `JevAnswer` | 已有领域类型，复盘时点和插件证据、模型事件分别表达。时间检查此前包括字符串比较和不同解析器，偏移量可触发不一致。 |
| 渠道 / Provider adapters | `agent/providers.py` 提供请求序列化、SSE 解析、模型目录与配置；`agent/route_chain.py` 处理回退；`agent/dsh_bridge.py` 提供版本化 stdio；`jev/` 提供 `JevBackend` 协议和 Direct/OpenRouter | Jev 请求→评估结果已有类型，聊天 Provider 仍返回字典分片，DSH 有独立 JSON-RPC 事件。Provider 模块把传输、凭据持久化与目录管理集中在一处。 |
| Plugin adapters | `plugin_cli.py` 暴露命令，`plugin_marketplace.py` 管目录/状态，`plugin_installer.py` 管安装及凭据，`plugins/runtime.py` 执行插件并生成证据 envelope | `plugin_installer.py` 直接复用聊天 Provider 的凭据读写。插件产物有统一的证据 envelope，调用、事件、错误仍按各入口处理。 |
| 本地 mock | `ReviewAgentRuntime._offline_turn`、`InMemoryDshTransport`、Jev 注入式测试传输、toy fixtures | 已有确定性本地路径，缺共享接口上的 mock adapter；当前可用现有测试覆盖各自渠道的结果。 |
| 共享服务与持久化 | `TraderService` 做导入、分析、回放；`store.Store` 保存本地复盘/会话事件；`trader/storage` 的 `TenantStore` 隔离日志；插件有 `PluginStateStore` | Agent 同时做分流、工具周期与事件写入。业务服务依赖本地复盘状态、租户日志、插件状态三套存储，跨入口的恢复和一致性需要在应用服务层定义。 |

**演进顺序**。从 `assistant.send/resume` 一条纵切面加内部类型契约，沿用 `Operation` 的操作名。请求带版本、请求/会话 ID、调用者授权范围与业务载荷，响应以 `event`（带序号）、`result` 或 `error`（稳定码、可重试性）区分。用一个离线 adapter 与现有 HTTP/SSE、CLI、stdio 做契约用例，adapter 负责翻译，控制器持有授权和状态转换，底层服务保留现有存储所有权。迁移其余渠道前先检验事件顺序、错误和会话恢复在首个切面的一致性。

**本次实现**。Jev 审查复用 manifest 的 ISO 解析函数，比较带时区的时间点；有全局决策时点时，嵌套证据受全局和记录自身时点中较早者约束。回归覆盖跨偏移量的同刻接受、未来拒绝、时区缺失和嵌套覆盖。BenchmarkCase 构造器仍有独立字符串比较，应在后续时间校验收敛时覆盖。[jev/questions.py](../../src/smartmoney_cub_harness/jev/questions.py) · [回归测试](../../tests/test_jev_questions.py) · [benchmark/cases.py](../../src/smartmoney_cub_harness/benchmark/cases.py)

## 工程化与 GitHub 增长

| 排名 / 窗口 | Owner | 交付与验收 |
| --- | --- | --- |
| 1 · 第 1 周 | Neon 主责，后端验证 | 双语 README 首屏放一句复盘定位、一条 toy 快速开始和 35 秒 GIF，展示导入→证据→复盘结果。把安装、benchmark、插件分别链接到专项页，记录 5 人首轮体验结果。 |
| 2 · 第 1–2 周 | 后端产出，Neon 包装 | 发布公开 benchmark 结果与复算命令。卡片展示样本覆盖、无结果/失败量、准确率及区间、成本和时延，链接到固定版本的运行报告及基线。已有 240 个合成样本、四任务轨、每系统 1,020 个评分项作为起点，榜单的解释范围限于该合成集。[报告](../../assets/benchmark/run.json) · [评测协议](../jev-ecosystem.md) |
| 3 · 第 2 周 | Neon 文案，维护者应用 | 把 20 个 topics 收敛为 `trading-journal`、`trading-review`、`decision-logging`、`local-first`、`ai-agent`、`human-in-the-loop`、`rule-evolution`、`benchmark`、`read-only`、`jev`。合并 `ai-agents` 同义项，将免责声明和模型品牌写进说明，核对主题页流量与搜索描述。[GitHub topics 数据](https://api.github.com/repos/myc0576/SmartMoney-Cub/topics) |
| 4 · 第 2–3 周 | Neon 发布素材，后端维护者答疑 | **Show HN** 以可运行 toy 日志和时点回归为主线。**V2EX 分享创造**用中文短 GIF 征集一次真实安装反馈。**少数派**用本地记录的盘后复盘工作流写体验，按投稿通道管理首发。**掘金**写跨时区时间回归与 CLI/HTTP 契约。**知乎**以“后验信息怎么污染复盘”为题复算一个带时间线的公开 toy 案例。每处跟进一个渠道独有的问题，7 天后比较有效复现数与反馈。[Show HN](https://news.ycombinator.com/showhn.html) · [V2EX](https://www.v2ex.com/go/create) · [少数派投稿通道](https://sspai.com/post/72089) |
| 5 · 第 2–4 周 | 后端主责，Neon 做 changelog | 以四周为一个可验证发布窗口，给出安装冒烟、迁移说明、doctor 和评测结果。准备 3 个带期望输出的 `good first issue`（toy CSV 格式、失败案例文档、评测复算），维护者一周内回应。 |
| 6 · 第 4 周后 | 后端做资格核验，Neon 写一句话 | 复核已合并的 Awesome Jev #9 和默认分支条目。面向 Awesome Quant 先核对评测/研究分类和收录要求，面向 Awesome Selfhosted 先核对本地工作台符合其收录条件，再各准备一项可复现链接和简述。提交时核验 fork parent、PR base/head、合并后的最终措辞与 fork 同步状态。[Awesome Jev #9](https://github.com/kraayenjon/awesome-jev/pull/9) · [已收录条目](https://github.com/kraayenjon/awesome-jev#business-and-vertical-apps) · [Awesome Quant](https://github.com/wilsonfreitas/awesome-quant) · [Awesome Selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted) · [上游维护流程](../open-source-maintenance.md) |

30 天跟踪 GitHub unique visitors、成功完成 toy 复盘的自愿反馈数、独立 benchmark 复算数、来自新贡献者的 PR 数。以第一次测量建立基线，stars/forks 用作分发信号。
