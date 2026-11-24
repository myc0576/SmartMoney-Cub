# 社区痛点调研开源工具链与方法

日期：2026-09-25

## 结论

目前没有一个开源项目同时把 X、Reddit、GitHub、论坛和评论采集、去重、痛点识别、跨社区聚类、证据留存、用户访谈和付费验证全部做好。更现实的方案是组合工具，并在工具之上建立自己的痛点证据层。

当前最适合验证 AlphaTech 和 SmartMoney-Cub 方向的组合是：OpenMagpie 负责跨社区采集和语义监听；Harken 负责本地存储、去重、主题聚类和趋势视图；SmartMoney-Cub 的 Evidence Envelope 负责记录来源、模型、时间和输入输出 hash；人工访谈和试用负责最终验证。

如果只选择一个项目，优先选择 OpenMagpie。如果目标是长期掌握真实痛点，而不是只收到提醒，建议把 Harken 的数据模型和本地存储方式也吸收进来。

本轮继续核验后，推荐把产品拆成两个边界清楚的部分：

1. **研究雷达**：监听用户已经授权或公开可访问的来源，发现与指定任务有关的讨论，保留原始链接和上下文。
2. **证据工作台**：去重、跨社区归并、人工复核，并把访谈、试用、数据提供和付费行为写成验证事件。

这两个部分不能混成一个“AI 自动发现商机”按钮。前者解决发现，后者解决判断；真正的需求证据还需要用户行为验证。

## 本轮补充核验

### X 的覆盖是有成本和窗口的

本轮可取得的 X 官方文档搜索结果显示，Recent Search 面向最近 7 天的帖子，单次返回量为 10 到 100 条，按返回帖子计费，并有按月读取上限；官方还单独列出应用和用户级速率限制。具体价格、额度和规则可能调整，正式产品必须以账户实际适用的官方页面为准。

这会改变 AlphaTech 的产品设计：

- 不承诺无边界的“全网实时扫描”，而是让用户指定社区、关键词、时间窗和预算上限。
- 为每次查询保存 query、时间窗口、结果游标、返回数、失败状态和成本估算。
- 同一帖子在不同批次命中时只保留引用关系和内容 hash，避免重复计费和重复统计。
- 将“没有搜到”区分为无匹配、窗口外、额度不足、速率限制、接口失败和权限不足。

OpenMagpie 的价值在于用自然语言语义过滤减少送入模型的候选量，但其 X 连接路径需要按具体版本检查授权方式和平台规则。Harken 若通过官方凭据连接 X，更适合作为研究台的来源适配参考；两者都不能替代平台许可和数据保留设计。

### Reddit 不能因为公开就默认可以商业化

Reddit 的官方 Data API、开发者条款和 Responsible Builder Policy 需要单独核验用途、速率、数据保留、删除、再分发、衍生数据和模型使用要求。当前命令行无法稳定访问 Reddit 官方页面，因此本报告不把失败响应当成条款结论；上线前应由负责人依据适用条款和商业场景完成一次法律与平台政策核对。

工程上先按以下原则设计：

- 保存来源 URL、帖子或评论外部 ID、抓取时间和原文 hash，避免把平台内容默认当作永久资产。
- 研究记录与模型产物分开，支持删除和过期清理，并保留删除原因。
- 对外共享优先输出问题簇、计数、匿名化观察和链接，不把抓取到的整段原文当作可转售数据。
- 访问受限、删除、内容不完整或上下文缺失时，结果进入 `data_quality`，不能变成“没有痛点”。

## 真实痛点研究的可复用方法

### 1. 先定义“最近一次事件”

每个研究主题先写成一个可追问的事件，而不是一个宽泛关键词。例如：

```text
在最近一次多模型 Agent 任务中，团队什么时候发现平台账、供应商账和业务归属对不上？
当时由谁发现，花了多少时间，用什么临时办法补救，最后有没有造成超支、延迟或客户争议？
```

对 SmartMoney-Cub，问题应写成“最近一次导入成交记录后，哪一笔无法和券商交割单对上？用户如何查出差异？”；“交易复盘痛点”过于宽，无法验证。

### 2. 每条候选必须过事实字段

自动提取时允许模型提出候选，但必须要求它引用原文片段或返回空值。至少记录：

| 字段 | 能证明什么 | 不能证明什么 |
|---|---|---|
| first_person | 是否本人经历 | 不能证明问题普遍 |
| trigger | 何时发生、触发了什么 | 不能证明损失大小 |
| workaround | 当前怎么解决 | 不能证明愿意买单 |
| time_or_money_loss | 是否付出时间或金钱 | 不能证明预算属于谁 |
| switching_signal | 是否寻找替代或准备迁移 | 不能证明会持续使用 |
| payment_signal | 是否给出预算、试用或购买行为 | 不能证明规模市场 |
| counter_evidence | 谁没有这个问题或已被解决 | 不能直接否定局部高价值场景 |

模型没有找到原文证据时，字段必须为 `unknown`，不能让模型根据语气猜测。

### 3. 统计“独立经历”，不要统计“热度”

问题簇至少要同时显示独立作者数、独立社区数、首次出现、最近出现、重复发生数、workaround 数、损失信号数和反证数。点赞、转发、评论量只用于安排人工阅读顺序。

一个可执行的归并流程是：先用 `source_type + external_id` 去重，再用原文 hash 去重，最后用作者匿名标识、引用链和相似文本识别转发。跨社区聚类完成后，人工抽查簇内最早、最新、最具体和最反对的样本。

### 4. 用行为验证把 E3 推到 E4

公开帖子通常最多提供 E3：用户描述了 workaround、成本或迁移意愿。要进入产品决策，给问题簇设计一个最小验证动作：

1. 访谈：围绕最近一次事件追问过程、后果和当前替代流程。
2. 数据验证：请用户提供脱敏账单、失败日志、导入文件或一周样本。
3. 人工服务：先由团队完成一次对账、归因、复盘或报告生成。
4. 试用：让用户在自己的真实数据上重复使用，并观察是否安排第二次。
5. 付费信号：报价、预购、定金、采购流程或主动介绍同类用户。

“愿意点赞”“说这个很需要”“愿意注册”只能作为弱信号。真实证据是用户愿意付出数据、时间、迁移成本或金钱。

## 推荐的最小产品形态

第一阶段做内部或受限客户版的 **Community Evidence Workbench**：

```text
官方 API / 用户导入 / 有边界的公开 Feed
        -> OpenMagpie 语义监听
        -> SQLite/Harken Mention 与去重
        -> BERTopic 或规则辅助聚类
        -> Argilla/Label Studio 人工复核
        -> SmartMoney-Cub Evidence Envelope
        -> 访谈、人工服务、试用和付费事件
```

AlphaTech 的差异点应放在“每条结论能否回到证据，以及一次研究运行花了多少钱”，而不是再做一个泛化的情绪分析面板。后续如果产品化为 Web SaaS，应支持本地采集器或用户自带数据源，使敏感内容可以留在客户环境，只上传 hash、统计结果和经用户批准的摘要。

## 选择建议

| 目标 | 首选 | 原因 |
|---|---|---|
| 先快速监听 X/Reddit 等来源 | OpenMagpie | 自然语言语义过滤、Feed/Watch、Webhook，最接近雷达 |
| 做本地历史库和趋势台 | Harken | SQLite、去重、来源游标、主题和导出较完整 |
| 快速验证 Reddit 结构化输出 | Reddit Pain Point Discovery | 字段和看板直观，但模型评分不能当市场证据 |
| 扩展公开网页上下文 | Crawl4AI | 适合补父贴、评论、FAQ 和文档，需遵守访问边界 |
| 建人工审核集 | Argilla 或 Label Studio | 可以把事实字段、反证和 E0-E3 标注固定下来 |
| 做跨社区相似案例召回 | BERTopic + Qdrant | 适合聚类和检索，不能代替验证 |

如果只能投入一周，接 OpenMagpie、SQLite 和一个简单的人工审核表；如果投入一个月，再加 Harken 的时间线/去重思路和 Evidence Envelope；只有当样本量和人工标注稳定后，才引入向量库和复杂自动聚类。

## 开源项目核验

### 1. OpenMagpie：最接近跨社区真实问题监听

仓库：<https://github.com/obris-dev/openmagpie>

许可证：Apache 2.0，许可证同时保留了 ee 目录的独立许可边界，商业集成前需要检查实际使用的目录。

截至本次核验，仓库最新提交为 2026-09-01 的 0.9.0 发布提交。README 明确列出 X/Twitter、YouTube、Reddit、Hacker News 和 RSS/Atom 连接器；X 和部分 YouTube 路径使用浏览器会话 cookie，并在文档中提示非官方路径和服务条款风险。

它的关键设计不是把所有内容都送进模型，而是：Feed 负责收集来源和保存条目；Watch 订阅一个或多个 Feed；semantic_filter 用自然语言描述什么值得关注；本地或兼容 OpenAI 的模型只对候选条目做相关性判断；通过 webhook 或日志输出命中条目；每次判断和 webhook 投递都有可查询的活动记录；支持导出活动数据。

它很适合监听：只保留那些明确描述 AI API 中转、模型调用成本、供应商账单、MCP 工具失败、配额失控或企业审计困难的帖子，排除营销文案、纯新闻转发和没有实际使用经历的泛泛讨论。

局限也很清楚：它当前更像及时发现相关对话的监听器，不是完整的用户研究系统。它不会自动判断一个痛点是否高频、是否造成损失、用户是否已经尝试付费解决，也没有跨时间的需求生命周期模型。

### 2. Harken：适合做本地研究数据库和趋势台

仓库：<https://github.com/VladUZH/harken>

许可证：MIT。核验到的最新提交为 2026-07-22。

Harken 的定位是 self-hosted social listening。README 明确支持 Hacker News、Reddit、Mastodon、Bluesky、Stack Overflow、RSS、X 和 YouTube；其中 Hacker News、Bluesky 和 Stack Overflow 可以在无凭据条件下工作，其他来源按连接器配置。

它的基础数据流是：来源 -> 统一 Mention -> 内容去重 -> 情绪 -> 主题聚类 -> SQLite -> 看板和 CLI。

对研究最有价值的能力包括：所有内容留在本地 SQLite；按内容 hash 去重；主题聚类和情绪分析可以不依赖模型；可选接入 OpenAI、Anthropic 或 Ollama 做主题命名；支持历史回填和来源游标；按项目聚合关键词、来源、主题和时间线；支持导出、备份、保留期清理、Webhook、邮件和 Prometheus 指标。

Harken 更像研究台，而不是机会发现引擎。它能回答人们最近在谈什么，但还需要自定义字段回答他们是否愿意为解决方案付费、问题是否阻碍工作、现在用什么替代方案、不解决会发生什么。

### 3. Obsei：通用数据观察、分析和输出框架

仓库：<https://github.com/obsei/obsei>

许可证：Apache 2.0。README 将项目标为 alpha，仓库核验到的最新提交为 2024-10-04，因此需要先做小规模 PoC 再决定是否作为长期依赖。

Obsei 的结构是三段：Observer 从 Twitter、Reddit、Facebook、应用商店、Google Reviews、Amazon、新闻和网页采集；Analyzer 做分类、情绪、翻译和 PII 等分析；Informer 把分析结果写入工单、数据存储或 DataFrame。

它适合借鉴来源、分析器、输出端都是可替换组件的结构，也可以作为一次性离线批处理框架。它的问题是对产品研究来说过于通用，默认能力更偏分类和情绪，不等于用户痛点发现；项目成熟度也低于 OpenMagpie 和 Harken。

### 4. Reddit Pain Point Discovery：适合概念验证，不适合直接作为判断标准

仓库：<https://github.com/lefttree/reddit-pain-points>

许可证：MIT。它可以抓取指定 subreddit 的帖子和评论，用关键词先筛选，再由 LLM 提取 pain point、受众、严重程度、潜在解决方案、已有工具和 opportunity score，并提供 FastAPI 加 React 看板。

它的价值是把 Reddit 帖子变成结构化机会卡片，适合快速试验。它的局限更重要：目标社区偏 SaaS、创业、开发和生产力，容易产生创业者回声；关键词筛选会漏掉没有使用痛苦词汇的真实抱怨，也会把夸张表达当成需求；点赞数、评论数和 LLM 严重程度综合评分，容易把热门话题误认为高价值问题；market size 不能从一条帖子可靠推出；项目没有把用户是否尝试付费、是否反复遇到、当前替代流程和预算约束作为硬证据。

可以借鉴它的字段设计，但不要直接相信它的 opportunity score。

### 5. Huginn 与 RSS-Bridge：适合做来源接入层

Huginn：<https://github.com/huginn/huginn>

许可证：MIT。GitHub API 核验到仓库仍在维护，最新推送时间为 2026-09-24。Huginn 是自托管的事件代理系统，按 Agent 组成事件流，可以监听网页变化、RSS、Webhook 和多个外部服务，也可以在条件满足时发送通知或继续传递事件。它的价值在于把“来源 -> 规则 -> 输出”编排起来，适合作为 OpenMagpie 之外的补充接入层。

RSS-Bridge：<https://github.com/RSS-Bridge/rss-bridge>

许可证：Unlicense。README 列出 Reddit、YouTube、TikTok、Telegram、Mastodon 和通用 CSS/XPath 等 Bridge，并支持过滤、合并和降噪。它适合把没有 RSS 的公开页面转换成统一 Feed，再交给后续系统分析。它只解决“拿到内容”，不会解决作者去重、上下文完整性、语义聚类或真实需求验证。

这两个项目的共同限制是：它们可以扩展来源覆盖，却会把服务条款、访问频率、公开性和内容留存责任交给部署者。X、Reddit 或其他站点若依赖非官方访问路径，必须单独审查平台规则和账号风险。对 AlphaTech 来说，它们更适合内部研究基础设施，不适合直接包装成“全网抓取”卖点。

### 6. Crawl4AI：适合补齐长网页和评论上下文

仓库：<https://github.com/unclecode/crawl4ai>

许可证：Apache 2.0。GitHub API 核验到项目仍在维护，README 当前列出自托管浏览器爬取、Markdown 清洗、结构化提取、缓存、批量 URL、动态页面和 Docker 服务。它适合在发现帖子后抓取公开的父贴、评论树、FAQ、产品文档和迁移页面，保留更完整的上下文。

它不应被当作 X 或 Reddit 的绕过工具。登录墙、验证码、付费墙、限流和访问控制都应保留为边界；它抓到的 Markdown 仍然是原始材料，必须保存源 URL、抓取时间、原文哈希和抓取失败状态。长上下文抓取很容易带来重复转发和隐私数据，必须在入库前去重和脱敏。

### 7. BERTopic、Qdrant：适合做问题簇，而不是做机会评分

BERTopic：<https://github.com/MaartenGr/BERTopic>

许可证：MIT。README 明确支持多语言、动态主题、在线/增量主题、监督和半监督主题建模，也能输出文档级主题和概率。它适合把“账单不一致”“余额对不上”“BYOK 不计入预算”等不同表述归到待审核的问题簇。

Qdrant：<https://github.com/qdrant/qdrant>

许可证：Apache 2.0。它是向量数据库和相似度检索引擎，适合保存帖子片段的 embedding 和结构化元数据，用于相似案例召回、重复检测和问题簇回溯。

这两个组件都只能提供相似性或主题结构。相似内容可能来自同一篇转发、同一位作者的重复发帖或同一个营销叙事；主题概率也不代表严重程度、预算或购买意愿。因此，问题簇必须同时保留独立作者数、独立社区数、原始 URL 和反证。

### 8. Argilla 与 Label Studio：适合建立人工复核集

Argilla：<https://github.com/argilla-io/argilla>

许可证：Apache 2.0。项目定位是让 AI 工程师和领域专家协作构建高质量数据集，支持文本标注、人机协作和反馈驱动的数据改进。

Label Studio：<https://github.com/HumanSignal/label-studio>

许可证：Apache 2.0。项目提供通用的数据标注和审核界面，可处理文本等多种数据类型，并有标准化导出格式。

对于本研究，二者不负责采集和聚类，而是把每周的候选内容送给人工复核。建议标注的不是“好项目/坏项目”，而是可回溯的事实字段：是否本人经历、是否描述具体触发场景、是否存在 workaround、是否提到时间/金钱/损失、是否寻找替代品、是否有反证、证据等级属于 E0-E3 哪一级。人工标注结果再回写问题簇，形成后续规则和模型的校准集。

### 9. 新出现的“用户意图发现”小工具：适合快速 PoC，不适合当核心依赖

本轮 GitHub API 还核验到几类更贴近用户需求发现的项目：

- SignalScout：<https://github.com/rszhd/signalscout>，描述为从公开对话中找出正在描述某类问题的人；MIT 之外的许可证字段在 GitHub API 中显示为 NOASSERTION，截至核验只有 8 stars，适合阅读设计和快速试验，使用前需要直接检查仓库许可证文件。
- social-media-research-skill：<https://github.com/skainguyen1412/social-media-research-skill>，MIT，描述为分析 Reddit 和 X 的公开讨论与引用；截至核验 59 stars，更像一个面向 Agent 的研究技能，而不是完整数据库或采集平台。
- customer-discovery-agent：<https://github.com/alex-jb/customer-discovery-agent>，MIT，描述为 Reddit pain-point scraper、Claude 聚类和结构化输出；截至核验 3 stars，适合一次性 PoC，不宜承担长期数据治理。
- trendscope：<https://github.com/mamboyepez17/trendscope>，MIT，描述为聚合 Reddit、Google Trends、X、Amazon 和 TikTok 的趋势基础设施，并提供 CLI、REST API 和 MCP；截至核验 3 stars，需重点审查每个数据源的授权、失败处理和原始证据留存。
- prismis：<https://github.com/nickpending/prismis>，MIT，描述为本地优先的 RSS/Reddit/YouTube 内容智能守护进程，带 AI 优先级评分和 TUI；截至核验 13 stars，适合借鉴本地优先和可查询消费界面。
- ClawRadar：<https://github.com/tenlifejosh/clawradar>，公开描述为面向 AI builder 的 X/Reddit 实时趋势监控，使用新鲜度、互动和关键词相关性做排序；更适合捕捉突发话题和热门信号，不是 embedding/LLM 语义痛点系统。

这些项目共同说明一个趋势：社区痛点研究正在从“关键词监控”转向“问题表达 + 购买意图 + 结构化输出”。但项目规模、许可证或数据来源契约还不足以支撑 AlphaTech 的长期核心。可以把它们作为候选发现器，与 OpenMagpie/Harken 的原始记录和 SmartMoney-Cub 的证据封装组合。

本轮公开搜索也暴露出一个需要长期坚持的核验规则：GitHub API 的 `license` 字段可能是 `NOASSERTION`，不能据此直接判断项目没有许可证；必须继续读取仓库中的 LICENSE 文件，并检查子目录是否有独立许可。反过来，README 写了“开源”也不能替代许可证和数据源条款核验。

## 工具职责矩阵

| 层 | 推荐组件 | 负责 | 不负责 |
|---|---|---|---|
| 来源发现 | OpenMagpie、Huginn、RSS-Bridge | 监听、Feed、规则、Webhook | 证明需求真实、绕过访问控制 |
| 网页补全 | Crawl4AI | 公开页面、父贴、评论和文档上下文 | 绕过登录墙、代替平台官方授权 |
| 本地研究库 | Harken、SQLite | Mention、去重、时间线、趋势、导出 | 付费意愿判断 |
| 聚类检索 | BERTopic、Qdrant | 相似案例、主题簇、动态趋势 | 严重程度、市场规模、购买意愿 |
| 人工复核 | Argilla 或 Label Studio | 标注事实、反证和证据等级 | 自动替用户作商业决策 |
| 证据治理 | SmartMoney-Cub Evidence Envelope | 来源、时间、哈希、模型和安全边界 | 代替访谈、试用和交易验证 |

如果只做一个可运行的内部版本，推荐 OpenMagpie -> SQLite/Harken -> Argilla -> SmartMoney-Cub Evidence Envelope。如果公开网页上下文经常缺失，再加入 Crawl4AI；如果来源数量变多，再引入 Huginn 或 RSS-Bridge。BERTopic 和 Qdrant 应在有了足够人工标注和重复数据后再引入，避免一开始就把复杂度放在向量搜索上。

## 公开数据的商业化边界

这条边界会直接影响 AlphaTech 最终做内部研究台还是对外 Web SaaS。

Reddit 官方 Data API Terms 和 Responsible Builder Policy 当前对商业使用、数据保留、再分发、衍生数据和模型训练设有额外限制；官方帮助页也要求开发者准确申报用途、遵守速率限制和平台政策。对于一个收费的社区情报 SaaS，不能因为数据公开就默认可以批量抓取、长期保存并向客户出售分析结果。上线前必须取得适用的 Reddit 平台批准或合同，并把删除、保留、再分发和模型使用规则设计进系统。

X 官方文档显示，近期帖子搜索是按返回条数计费，覆盖窗口和月度读取上限也有明确限制。搜索成本会直接影响“全网扫描”的商业模型，不能用一个没有预算上限的定时任务承诺全量监控。更稳妥的做法是：先用用户指定的社区、关键词和时间范围做有界研究；缓存原始结果的 hash 和必要元数据；把平台原文展示、客户共享和模型训练分开设计。

因此，第一阶段建议把 AlphaTech 定位成“帮助团队整理自己有权访问的公开研究材料的证据工作台”，而不是“替所有客户抓取全网社交数据”。后者的合规、成本和平台依赖会迅速超过中转站本身的研发问题。

## 与 SmartMoney-Cub Evidence Envelope 的映射

社区研究结果可以作为一个只读、非交易的外部插件能力接入。建议使用以下映射：

| 社区研究字段 | Envelope 字段 | 说明 |
|---|---|---|
| OpenMagpie/Harken/抓取器版本 | `plugin_id`, `plugin_version` | 固定工具和配置版本 |
| 仓库提交、配置文件或来源 URL | `source_ref` | 既记录工具来源，也记录具体数据来源 |
| 帖子原文与上下文快照 | `output` | 保存脱敏后的结构化记录，不把摘要当作原文 |
| 原始输入文件或 JSONL | `input_sha256` | 记录本批次输入的 hash |
| 结构化研究结果 | `output_sha256` | 记录输出包的 hash |
| 事实帖子、聚类统计、模型摘要、人工观察 | `result_kind` | 分别使用 `fact_data`、`statistical_result`、`model_opinion`、`review_observation` |
| 抓取时间与帖子发布时间 | `available_at` 与扩展元数据 | 不混淆发布时间、抓取时间和研究决策时间 |
| 公共网页/Reddit/X/RSS | `data_source` | 具体到平台和连接器 |
| 抓取失败、内容不完整、需登录 | `data_quality` | 不能用空结果假装没有痛点 |
| 社区监听是否联网 | `network_used` | 应为 `true`，并保留具体访问边界 |
| LLM 过滤或聚类是否使用模型 | `model_used` | 记录模型名称、版本和提示模板到扩展字段 |
| 研究用途、不能产生交易动作 | `permission` 与 `safety` | 继续携带 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` |

这里有一个需要明确的语义边界：`fact_data` 只能表示“帖子中确实出现了这段内容”或“统计程序确实算出了这个数量”，不能表示“这个痛点已经被证实”或“应该做这个产品”。“已验证需求”必须作为人工研究状态写入，并且至少附带 E3 以上证据和 E4 的访谈、试用或预算信号。

## 推荐的 AlphaTech 研究工作流

### 第一层：广泛捕获

用 OpenMagpie 维护多个独立 Feed，而不是把所有来源混进一个关键词搜索：

1. X：产品名、竞品名、模型名、broken、unreliable、invoice、quota、cost、alternative 等组合。
2. Reddit：目标产品社区、开发者社区、创业者社区、行业垂直社区分别监听。
3. Hacker News：Ask HN、Show HN 和评论流分开监听。
4. GitHub：仓库 issue、discussion、release 反馈和重复出现的 bug 作为高价值工程痛点来源。
5. RSS 和论坛：官方社区、独立博客、行业论坛和产品 changelog。

每个来源都需要保存原始 URL、社区、作者匿名标识、发布时间、抓取时间、标题、正文、上下文父贴和互动指标。互动指标只作为发现排序，不能作为需求强度的直接证明。

### 第二层：低成本过滤

先用规则过滤，再用本地模型做语义判断。规则不负责判断真假，只负责减少模型成本。

候选可以分成：明确痛苦、替代需求、付费信号、现有流程、结果损失和反证。模型判断应输出相关性，不要直接输出这是一个好项目。

### 第三层：痛点结构化

每条候选记录至少包含：source_url、source_type、community、published_at、captured_at、author_pseudonym、raw_text_hash、pain_statement、user_segment、trigger_situation、current_workaround、existing_products_mentioned、frequency_signal、severity_signal、money_signal、switching_signal、verbatim_evidence、counter_evidence、llm_model 和 human_review_status。

关键是把痛点描述和商业价值分开。模型可以帮忙提炼痛点，但 money_signal、frequency_signal 和 switching_signal 必须能回指原文，不能只靠模型猜测。

### 第四层：跨社区合并

同一问题可能以不同词出现。例如 X 说账单对不上，Reddit 说余额不准，GitHub issue 说 BYOK 不计入 guardrail，Hacker News 说 gateway cost attribution is impossible。这些应该归入同一个问题簇，但保留不同来源的原文和上下文。

聚类键应优先使用用户任务、阻碍和后果，而不是单纯关键词。簇级字段应包含 problem_cluster_id、canonical_problem、affected_segments、source_count、unique_author_count、community_count、first_seen_at、last_seen_at、repeat_mention_count、explicit_workaround_count、explicit_payment_count、switching_count、severity_range、contradicting_evidence 和 confidence。

unique_author_count 和 community_count 比总点赞数更重要。一个人反复发十条帖子，不等于十个用户；同一个帖子被转发，也不等于独立需求。

### 第五层：人工复核和真实验证

每个高分问题簇都要人工抽查原始上下文，至少回答：这是本人真实使用经历，还是转述或观点；问题是否反复发生；用户当前用什么办法解决；这个办法花了多少时间、钱或人力；用户是否明确寻找替代品或愿意迁移；问题是否只属于一个平台或一个极端案例；是否存在反向证据。

只要这些问题无法从公开上下文回答，就把它标成线索，不要标成已验证需求。

## 如何判断最真实的痛点

建议使用五级证据等级，而不是单一机会分数：

| 等级 | 证据 | 含义 |
|---|---|---|
| E0 | 关键词命中 | 可能相关，不能作判断 |
| E1 | 一条具体使用经历 | 真实个案线索 |
| E2 | 多个独立作者或社区重复出现 | 重复问题 |
| E3 | 明确描述 workaround、迁移或成本损失 | 有现实代价 |
| E4 | 用户愿意试用、提供数据、接受访谈或给出预算 | 有验证意愿 |
| E5 | 用户持续使用、付费或主动介绍同类用户 | 已有商业证据 |

自动化工具最多把素材从 E0 推到 E2。E3 需要上下文核查，E4 和 E5 必须通过访谈、试用或真实交易验证。任何模型都不应直接把 E0 变成 E4。

## 针对 SmartMoney-Cub 的研究主题

不要泛泛监听交易软件。应拆成具体任务：交易记录导入和券商交割单对账；多账户、多市场、多币种的统一复盘；交易规则违规后的解释和证据留存；复盘数据的隐私、本地化和导出；交易教练或 prop firm 的审阅、批注和留痕；AI 复盘结论如何被验证；回测结果与真实成交记录的时间口径差异。

监听结果必须继续服从 SmartMoney-Cub 的安全边界。外部帖子、模型分析和社区建议只能成为研究证据，不能变成交易建议，也不能触发订单、撤单或账户修改。

## 可直接运行的监听规则

监听规则的目标是减少噪声和模型成本，不是提前决定结论。每条规则都应绑定一个用户任务、一个失败结果和一个需要寻找的证据字段。下面是一组适合 AlphaTech 与 SmartMoney-Cub 第一轮验证的规则主题：

| 规则主题 | 关注表达 | 必须补齐的证据 | 主要反证 |
|---|---|---|---|
| AI API 成本和账单不一致 | invoice、usage、bill、cost、quota、BYOK、balance、charged、overcharged | 是否有具体账单、时间范围、金额或核对过程 | 只是询价或泛泛比较价格 |
| MCP 工具失败和权限问题 | MCP、tool failed、permission、auth、timeout、schema、rate limit | 失败步骤、重试方式、是否阻塞任务、当前替代方案 | 单次配置错误或教程提问 |
| 多账户交易记录导入和对账 | broker import、fill、execution、CSV、statement、reconcile、multi-account | 账户类型、文件格式、对账差异、人工耗时 | 只想要一个格式转换脚本 |
| 交易复盘隐私、本地化和导出 | local-first、privacy、self-hosted、export、offline、data ownership | 用户拒绝云端的具体原因、现有本地流程 | 对隐私的抽象表达，没有实际行为 |
| 教练或 prop firm 审阅和批注 | trading journal review、coach、prop firm、annotation、audit trail | 审阅角色、批注频率、共享流程、责任边界 | 单个交易员的个人偏好 |

OpenMagpie 的语义过滤可以把规则写成自然语言，例如：

```text
保留那些由本人描述的 AI API 或模型网关使用经历，且明确提到账单、余额、配额、成本归属或账单核对失败。
优先保留包含当前 workaround、重复发生、迁移计划、金额、时间损失或正在寻找替代方案的内容。
排除新闻转发、营销文案、纯价格询问、没有使用上下文的观点和只有一个词的抱怨。
输出原文 URL、发布时间、社区、作者匿名标识、触发场景、当前 workaround、损失信号、替代信号和反证字段。
```

每个主题至少配置两条相反方向的规则：一条找痛苦，一条找满意、无需替代或已经解决的内容。只有收集负面帖子，会把产品方向系统性地推向过度修复。

## 最小 SQLite 研究模型

第一版不需要先引入 Qdrant 或复杂数据仓库。SQLite 足以支持去重、回溯、人工复核和问题簇统计，关键是把原始材料、模型推断和人工判断分开保存。建议至少有以下六张表：

```sql
CREATE TABLE mentions (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_url TEXT NOT NULL,
  community TEXT NOT NULL,
  external_id TEXT,
  published_at TEXT,
  captured_at TEXT NOT NULL,
  author_pseudonym TEXT,
  title TEXT,
  raw_text TEXT NOT NULL,
  raw_text_sha256 TEXT NOT NULL,
  parent_url TEXT,
  engagement_json TEXT,
  access_status TEXT NOT NULL,
  UNIQUE(source_type, external_id),
  UNIQUE(source_type, raw_text_sha256)
);

CREATE TABLE evidence_items (
  id TEXT PRIMARY KEY,
  mention_id TEXT NOT NULL REFERENCES mentions(id),
  evidence_kind TEXT NOT NULL,
  quoted_text TEXT NOT NULL,
  locator TEXT,
  result_kind TEXT NOT NULL,
  model_used TEXT,
  input_sha256 TEXT,
  output_sha256 TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE problem_clusters (
  id TEXT PRIMARY KEY,
  canonical_problem TEXT NOT NULL,
  user_segment TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT,
  source_count INTEGER NOT NULL DEFAULT 0,
  unique_author_count INTEGER NOT NULL DEFAULT 0,
  community_count INTEGER NOT NULL DEFAULT 0,
  workaround_count INTEGER NOT NULL DEFAULT 0,
  payment_signal_count INTEGER NOT NULL DEFAULT 0,
  switching_signal_count INTEGER NOT NULL DEFAULT 0,
  counter_evidence TEXT,
  confidence TEXT NOT NULL
);

CREATE TABLE human_reviews (
  id TEXT PRIMARY KEY,
  mention_id TEXT NOT NULL REFERENCES mentions(id),
  reviewer TEXT NOT NULL,
  is_first_person_experience INTEGER,
  has_concrete_trigger INTEGER,
  has_workaround INTEGER,
  has_cost_or_loss INTEGER,
  has_switching_signal INTEGER,
  evidence_level TEXT NOT NULL,
  decision TEXT NOT NULL,
  rejection_reason TEXT,
  reviewed_at TEXT NOT NULL
);

CREATE TABLE validation_events (
  id TEXT PRIMARY KEY,
  cluster_id TEXT NOT NULL REFERENCES problem_clusters(id),
  event_type TEXT NOT NULL,
  participant_pseudonym TEXT,
  offer_or_question TEXT,
  observed_behavior TEXT,
  evidence_level TEXT NOT NULL,
  amount_or_time TEXT,
  occurred_at TEXT NOT NULL
);
```

`mentions` 保留来源事实，`evidence_items` 保留可定位原文和模型处理痕迹，`human_reviews` 保留人工判断，`validation_events` 才记录访谈、试用、数据提供、预购或付费。这样可以避免把模型生成的 `pain_statement` 当作原文，也避免把“用户说想要”误当成“用户愿意付费”。

如果后续引入向量库，向量记录必须只作为 `mention_id` 或 `evidence_item_id` 的检索索引，不能成为唯一证据来源。

## 30 天验证计划

### 第 1 周：接入、边界和采样

选定 5 类来源：Reddit、X、Hacker News、GitHub Issues/Discussions 和公开 RSS。每个来源固定时间窗口、查询规则、结果上限和保留字段。先运行 OpenMagpie 或等价采集器，把数据落到 JSONL 和 SQLite；保留来源 URL、发布时间、抓取时间、外部 ID、原文 hash 和失败状态。

这一周的交付不是“找到最多痛点”，而是得到一份可回溯样本：任何一条结构化记录都能回到原文，任何抓取失败都不会伪装成没有结果。

### 第 2 周：人工标注和去重

每天抽取 10 到 15 条候选，至少两个人独立标注其中 20% 的样本。重点标注是否本人经历、是否具体触发、是否有 workaround、是否有时间或金钱损失、是否寻找替代品、是否存在反证。把争议样本单独留下，用来改规则和提示词。

这一周结束时，淘汰只靠关键词、营销文案、重复转发和单纯情绪表达形成的候选。不要根据 LLM 的严重程度排序直接进入产品决策。

### 第 3 周：问题簇、反证和用户分层

把不同平台的表述合并成问题簇，例如“余额不准”“账单对不上”“BYOK 不计入预算”可能属于同一类成本归因问题。每个簇同时维护支持证据和反证，区分独立作者、独立社区和同一作者的多次发言。

本周只保留 E2 以上的问题簇，并为每个簇写出一条可被用户确认的假设：

```text
对于使用多个模型或多个工具的团队，无法把一次 Agent 任务的供应商成本、平台额度和业务归属对齐，导致他们每周需要人工核账，且现有网关无法提供可回放的证据链。
```

这条假设必须能被访谈对象明确回答“发生过/没有发生过”，而不是“你觉得这个功能酷不酷”。

### 第 4 周：访谈、试用和付费信号

每个重点问题簇访谈 5 到 8 名具有实际使用经历的人，优先寻找能提供脱敏样本、账单、工作流或失败日志的人。访谈围绕最近一次真实事件进行：什么时候发生、造成什么后果、当前怎么解决、花了多少时间或钱、谁有预算、为什么还没有解决。

随后提供一个极小的人工或半自动服务，例如帮助对齐一周的模型账单和任务成本，或把一批交易记录导入并生成对账差异报告。观察用户是否愿意提供真实数据、安排第二次使用、邀请同事、接受报价或支付定金。

四周后的判断规则：E2 只能进入继续观察；E3 才能进入产品假设；E4 才能进入小规模试用；E5 才能作为产品化和定价依据。

## 推荐的真实痛点评分

建议用“证据闸门 + 维度记录”，不要用一个黑盒 opportunity score。内部可以用下面的排序辅助，但任何一项都不能替代原文和人工复核：

```text
priority =
  2 * independent_author_count
  + 2 * community_count
  + 3 * explicit_workaround_count
  + 3 * explicit_loss_or_cost_count
  + 4 * switching_or_payment_signal_count
  - 3 * duplicate_or_repost_risk
  - 2 * counter_evidence_strength
```

这个数只用于安排下一步人工工作。对外或对产品决策输出时，必须同时显示每个分量、样本量、缺失字段和证据等级。尤其不能用点赞数、评论数或模型情绪分数直接替代独立作者数和现实代价。

## 需要规避的误判

- 高互动不等于高痛苦。争议和娱乐内容更容易获得互动。
- 高频抱怨不等于愿意付费。有些用户只想要免费功能或平台补偿。
- “有没有工具”不等于购买意向。用户可能只是在寻找一次性脚本。
- 创业社区的痛点不等于终端用户痛点。需要跨到真实使用社区验证。
- 一个大客户的严重问题不等于大众市场，但可能是企业高价值切口。
- LLM 的严重程度和市场规模字段都属于推断，必须保留原始证据和不确定性。
- X 的公开监听若依赖浏览器 cookie 或非官方接口，需要单独评估服务条款、账号风险和数据留存规则。

## 给 AlphaTech 的最小可行版本

第一版可以只做一个本地研究工作台，不急于做对外 SaaS：

1. 用 OpenMagpie 监听 5 个来源和 20 组自然语言规则。
2. 把命中条目以 JSONL 或 webhook 送入一个本地 SQLite 研究库。
3. 用 Harken 的 Mention、去重、主题和时间线思路做本地看板。
4. 用 SmartMoney-Cub 的 Evidence Envelope 记录来源、模型、时间和输入输出 hash。
5. 每周人工审核前 30 条候选，记录接受、拒绝和拒绝原因。
6. 两周后只统计 E2 以上的问题簇，四周后再挑 E3 以上的问题做访谈。

第一版的成功标准不是抓到多少帖子，而是：能从一个问题簇回到所有原始帖子；能区分独立作者和转发或重复内容；能看到问题首次出现、持续时间和最近变化；能清楚区分事实、模型推断和人工判断；能记录哪些判断后来被访谈或试用推翻。

## 项目清单

- OpenMagpie：<https://github.com/obris-dev/openmagpie>
- Harken：<https://github.com/VladUZH/harken>
- Obsei：<https://github.com/obsei/obsei>
- Reddit Pain Point Discovery：<https://github.com/lefttree/reddit-pain-points>
- SignalScout：<https://github.com/rszhd/signalscout>
- social-media-research-skill：<https://github.com/skainguyen1412/social-media-research-skill>
- customer-discovery-agent：<https://github.com/alex-jb/customer-discovery-agent>
- trendscope：<https://github.com/mamboyepez17/trendscope>
- prismis：<https://github.com/nickpending/prismis>
- ClawRadar：<https://github.com/tenlifejosh/clawradar>
- Huginn：<https://github.com/huginn/huginn>
- RSS-Bridge：<https://github.com/RSS-Bridge/rss-bridge>
- Crawl4AI：<https://github.com/unclecode/crawl4ai>
- BERTopic：<https://github.com/MaartenGr/BERTopic>
- Qdrant：<https://github.com/qdrant/qdrant>
- Argilla：<https://github.com/argilla-io/argilla>
- Label Studio：<https://github.com/HumanSignal/label-studio>
- Reddit API 文档：<https://www.reddit.com/dev/api/>
- X API 文档：<https://docs.x.com/x-api/introduction>

## 最终建议

把 OpenMagpie 当作雷达，把 Harken 当作本地研究数据库，把 SmartMoney-Cub 的 Evidence Envelope 当作证据标准，把人工访谈和试用当作最终验证环节。Obsei 和 Reddit Pain Point Discovery 可以用于借鉴组件和快速做 PoC，但不应让它们的自动评分直接决定 AlphaTech 的产品方向。
