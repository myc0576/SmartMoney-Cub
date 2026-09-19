# smartmoney-cub-harness

<div align="center">

<img src="assets/smartmoney-cub-mark.png" alt="SmartMoney-Cub" width="88" height="88" />

![smartmoney-cub-harness cover](assets/smartmoney-cub-harness-cover.png)

## 游资复盘引擎 · 让每一次决策都变成系统的进化

*"散户靠感觉，高手靠系统。把你的感觉，变成可复盘、可验证、可进化的规则。"*

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-informational)](tests/)
[![Read-only](https://img.shields.io/badge/mode-read--only-brightgreen)](docs/safety.md)
[![Local-first](https://img.shields.io/badge/local--first-no%20telemetry-success)](docs/privacy.md)
[![Agent-ready](https://img.shields.io/badge/agent--ready-loop%20artifacts-blueviolet)](docs/agent-loop.md)
[![UZI-Skill](https://img.shields.io/badge/ecosystem-UZI--Skill-orange)](docs/integrations.md)
[![TradingAgents-ready](https://img.shields.io/badge/TradingAgents--ready-optional--adapter-informational)](docs/tradingagents-adapter.md)

只读 AI 复盘与规则进化 harness · 决策记录 · D1/D3 结果验证 · 本地 Markdown 记忆 · challenger -> champion 治理

[30 秒上手](#30-秒上手) · [5 秒体验闭环](#5-秒体验复盘闭环) · [核心理念](#核心理念系统--感觉) · [AI 助手接入](#给-ai-助手只读复盘协作) · [开源生态矩阵](#优秀开源项目集成矩阵) · [安全边界](#安全边界你的系统只属于你) · [CLI](#cli-commands)

`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`

![Finance-JEV Benchmark Hero](artifacts/benchmark/run_20260919_121535_240/benchmark-hero-1200x630.png)

### 30 秒极速上手

```bash
# 1. 安装核心库与开发依赖
pip install -e ".[dev]"

# 2. 环境健康检查与确定性安全声明验证
smcub doctor

# 3. 最短离线复盘体验闭环 (捕获决策并执行回放)
smcub capture-run --mode after-close --preset toy --sandbox --decision-time "2026-06-01T15:31:00+08:00"
smcub replay-evidence-pack tmp/sandbox/20260601/*-after-close
```


[English](README.md)

</div>

![SmartMoney-Cub 中英双语系统流程](assets/smartmoney-cub-system-flow-bilingual.png)

只读输入 → 核心控制平面（捕获 → 反未来函数 → 决策与风险契约 → 冻结证据）→ 延迟复盘（D1/D3 结果 → 确定性回放 → 评估与反方证据 → 记忆与案例库 → 挑战者规则 → 人工显式晋级门禁）→ 下一次计划。可选开源工具始终在可信核心外部，仅作为复盘证据加入。

对应文本与可维护 Mermaid 流程见 [docs/architecture.md](docs/architecture.md)。

---

游资和散户最大的区别是什么？不是信息差，不是资金量，而是系统。

高手每一次决策都有计划、有证据、有复盘、有规则迭代。普通人最容易掉进的坑，是复盘时翻聊天记录、翻交易软件、翻截图，折腾半天还是说不清当时为什么买、错在什么地方、下一次该怎么改。

`smartmoney-cub-harness` 是一个本地优先的 AI 复盘引擎。它帮你记录每一次决策的完整逻辑，追踪 D1/D3 的结果，把教训变成规则，把规则沉淀成系统。

它不是个股建议软件，不是自动交易系统，不是券商连接器，也不是财务建议系统。它是你的私人交易日志与复盘伙伴：对市场和执行只读，对你自己的日志可写。

更准确地说，`smartmoney-cub-harness` 是一个**本地优先、对市场与执行只读、不绑定任何 Agent 的交易日志与复盘 harness**：外部 Agent 或 CLI 调用方 → Run Envelope → 冻结的 Benchmark/Evidence Pack → 确定性回放 → 人工显式晋级门禁。它的核心**不内置 LLM**、**不连接券商**、**不自动交易**，控制平面完全离线运行；复盘助手是一个独立的、需要显式配置的入口，它只调用你自己配置的 Provider，并且只发送脱敏后的结构化字段。它不替用户选股、不运行后台自主交易 Agent、不自动修改核心规则。

```bash
smcub capture-run --mode after-close --preset toy --sandbox --decision-time "2026-06-01T15:31:00+08:00" --agent-name "toy-doc-agent-zh" --agent-version "1.0" --agent-interface "cli"
smcub validate-envelope tmp/sandbox/20260601/20260601_153100-after-close/run_envelope.json
smcub build-outcome tmp/sandbox/20260601/20260601_153100-after-close --horizon d1 --price-source smartmoney_cub_harness:data/sample_prices.json
smcub build-evidence-pack tmp/toy-evidence-pack --sample tmp/sandbox/20260601/20260601_153100-after-close --rule-candidate examples/toy_strategy/sample_rule_candidate.json --horizon d1
smcub replay-evidence-pack tmp/toy-evidence-pack
```

Run Envelope 的权限范围是**声明式、未经验证的策略记录**（`enforcement: declarative`、`verified: false`），不是子进程沙箱。CLI 的 `--sandbox` 只选择一次性的 `tmp/sandbox` 输出目录，并不隔离进程；不可信命令必须放在操作系统或容器沙箱中运行。`evidence_pack.sha256` 用于本地篡改检测，不是经过身份认证的数字签名；任何不一致只会进入 `pending_review` 或 `blocked`，绝不会自动晋级。

## 🧭 复盘工作台（1.0 · 本地优先）

工作台是三栏布局：左侧导航，中间业务页，右侧常驻复盘助手。导入券商交割文件或截图，
校对本地识别结果，然后让助手基于脱敏字段做复盘。

```bash
npx smartmoney-cub                      # 用户端不需要手工配置 Python
npx smartmoney-cub install --with-ocr   # 识别截图与扫描 PDF 所需的本地 OCR
smcub workbench                         # 也可以直接用 Python 包启动
smcub skill install --target codex      # 安装 Agent Skill
```

页面：总览（权益曲线、月历热力图、待复盘清单）、交易日志（表格 + 详情抽屉 + 成交版本历史）、
复盘日历、绩效分析（按标的／市场状态／星期／持有周期／标签归因，并显示样本量）、规则库、
数据导入、插件、设置（Provider、隐私与诊断）。

### 对话驱动的规则进化

复盘助手可以从已确认的证据里提出候选（challenger）规则，并且这条候选会和规则库页面读的是
同一个库：门禁缺口会被记录，同时在 workspace 数据库旁追加一条 `evolution_ledger.jsonl`
记录和一段可读的 `memory.md` 片段。

晋升是单独的一步，也是唯一能产生 champion 的写入：

```bash
smcub workspace rules
smcub workspace promote-rule RULE-1 --note "样本 24 笔，误报率 0.12，确认纳入"
```

那条确认说明就是门禁本身：说明为空或缺失时一律拒绝，且不写入任何东西——命令行与界面的
晋升接口行为一致。两道门禁刻意分开：样本与风险阈值只决定是否给出晋升建议，人写下的确认
说明才是规则变成 champion 的依据。助手、插件、导入的报告都不能替代它。

### 🔒 默认脱敏

助手默认走脱敏路径，界面不提供关闭开关：

- 券商截图、PDF、CSV 原文**只在本机解析**，**从不上传**到 AlphaTech 或任何其他模型 API。
- 账号、姓名与直接身份标识会被移除，或替换为设备内稳定的假名。
- 证券代码、组合名、精确数量、精确金额与精确时间会被替换为假名、区间或 15 分钟时段。
- 收益率、持有周期、执行偏差与统计特征会被保留，否则复盘没有意义。
- 每次外发都会在本机写入审计记录，说明发送了哪些字段、替换了多少处。
- 未配置 Provider 密钥时，助手只使用本地数据，不发出任何请求。
- Provider 来自目录：可添加内置 Provider、添加自定义网关（需指定协议）、从端点拉取模型目录，
  并在输入框旁的选择器里切换模型与推理强度。详见 [docs/review-agent.md](docs/review-agent.md)。

详见 [docs/review-agent.md](docs/review-agent.md) 与 [docs/convergence.md](docs/convergence.md)。

---

## 🏢 Trader 产品（托管模式）

同一个包还带有托管版 Trader 产品：一套多租户的交易日志与复盘界面，作为 alphatech 平台
（[alphatech.net.cn/trader](https://alphatech.net.cn/trader)）的一个平级入口，与 Alpha Canvas、
Commerce Workbench 并列。它导入你自己的成交、计算绩效分析、为 Playbook 打分、
回测一套 JSON 策略 DSL，并回放历史 K 线。

一条命令用同一个进程、同一个端口同时提供两个产品：

```bash
pip install "smartmoney-cub-harness[hosted]"   # hosted 额外依赖：psycopg，用于 Postgres
smcub trader serve --mode local                # 单个离线用户，SQLite
smcub trader serve --mode hosted \
  --database-url "postgresql://user:pass@host:5432/smcub" \
  --host 0.0.0.0 --token "$TRADER_ACCESS_TOKEN" --no-browser
```

`smcub trader serve` 把 trader API 挂在 `/api/trader/*`，
并与复盘工作台共用同一个 socket。`smcub workbench` 是本地单用户正门，
为单个离线用户挂载同一套 `/api/trader/*` 接口；
`smcub trader serve --mode hosted` 才是那个按请求解析平台身份的入口。
托管模式必须提供 `postgresql://` 地址，绝不回退到本地文件；
绑定到非回环地址必须提供 `--token`。

本产品不下单、不撤单、不修改券商账户、不自动化执行，也不是投资建议。
v1 覆盖了什么、明确的非目标、以及推迟到 v1 之后的功能，都写在
[Trader 产品说明](docs/trader-product.md)；HTTP 接口见 [docs/trader-api.md](docs/trader-api.md)，
三条部署路径见 [deploy/README.md](deploy/README.md)。

---

## 🧩 Everything is a Plugin（插件协议）

仓库自带插件协议、示例插件与精选目录。外部交易项目不进入核心发布包，用户安装插件后，
Harness 会自动发现、校验、注入并挂载能力，无需修改核心代码。详见 [docs/plugins.md](docs/plugins.md) 与 [docs/plugin-development.md](docs/plugin-development.md)。

```bash
smcub plugin inspect examples/toy_plugin/plugin.json
smcub plugin doctor  --plugin-dir examples/toy_plugin
smcub plugin run     toy.review-tagger \
  --request request.json \
  --decision-time 2026-09-10T15:00:00+08:00 \
  --available-at  2026-09-10T14:00:00+08:00
smcub plugin catalog
smcub profile show a-share-review
```

自动的部分：发现、校验、依赖注入、激活、证据封装。
不自动的部分：安装、联网、外部模型、凭证——一律需要用户主动触发。

每个插件输出都会封装为 Evidence Envelope，记录插件版本、源码引用、输入/输出哈希、时间语义与数据质量。
若 available_at 晚于 decision_time，直接判定为未来数据泄漏并拒绝执行。

## 📓 复盘工作区与分享包

```bash
smcub workspace import-csv exports/fills.csv
smcub workspace list-cases --action AVOID
smcub workspace summary
smcub share-pack --csv exports/fills.csv --output tmp/share-pack --write
```

工作区用 SQLite 保存复盘用例、D1/D3 结果、插件证据与规则状态。
分享包是离线静态 HTML，证券代码、名称、金额与盘中时间会按策略降精度，并经过隐私审计；
系统不会自动上传。详见 [docs/share-pack.md](docs/share-pack.md) 与 [docs/review-workspace.md](docs/review-workspace.md)。

---
## 30 秒上手

任何 agent 里丢一句话，让它按本仓库的安全合同跑 toy 离线闭环。公开仓库只使用 toy offline data。

| 你用的 agent | 直接丢这句 |
| --- | --- |
| Claude Code | `阅读 AGENTS.md 和 docs/harness-contract.md，运行 smcub loop --preset toy --agent-trigger "自进化"，只做只读复盘，不连接券商，不下单。` |
| Codex / OpenAI CLI | `在这个仓库里按 README 跑 smartmoney-cub-harness toy loop：smcub loop --preset toy --agent-trigger "自进化"，然后阅读 loop_report.md 和 trace.jsonl。` |
| Cursor | `请按 docs/agent-loop.md 使用本项目，跑 toy loop 并总结复盘产物；所有规则更新只能保持 challenger 状态。` |
| Gemini CLI | `请阅读 docs/harness-contract.md，执行 toy offline loop，确认输出包含 READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE。` |
| OpenCode / OpenClaw | `帮我用这个仓库做一次只读复盘演示：运行 smcub doctor，再运行 smcub loop --preset toy --agent-trigger "自进化"。` |
| CLI 直用 | `git clone https://github.com/myc0576/SmartMoney-Cub.git && cd SmartMoney-Cub && pip install -e ".[dev]" && smcub loop --preset toy --agent-trigger "自进化"` |

### 隔离安装与版本确认

不要把开发版本直接装进全局 Python。Windows 推荐使用项目内虚拟环境：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\smcub.exe --version
.\.venv\Scripts\smcub.exe doctor
```

macOS / Linux：

```bash
python -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/smcub --version
./.venv/bin/smcub doctor
```

如果电脑里安装过多个 Python，直接输入 `smcub` 可能命中另一个环境中的旧版本。安装后请运行 `smcub --version` 和 `smcub doctor`；`doctor` 会以不暴露本地路径的方式提示启动器冲突。

当前发行渠道是 GitHub Releases。普通 CLI 用户可用 pipx 从最新修复 tag 安装，让命令拥有独立环境：

```bash
pipx install "git+https://github.com/myc0576/SmartMoney-Cub.git@v1.0.0"
```

未来正式发布到 PyPI 后，可改用更短的安装和升级命令：

```bash
pipx install smartmoney-cub-harness
pipx upgrade smartmoney-cub-harness
```

现有安装不会自动同步。Git editable、pip、pipx 和源码压缩包用户的升级方式，以及 SemVer、Git tag、GitHub Release、PyPI 发布顺序，见 [版本与升级政策](docs/versioning.md)。

装好后最常用的安全命令：

```bash
smcub doctor
smcub privacy-audit
smcub loop --preset toy --agent-trigger "自进化"
smcub inspect-artifacts <run_dir>
```

本地私有 CSV 复盘可以使用自进化流程，但 champion 规则变更仍然必须人工确认：

```bash
smcub self-evolve --input-csv path/to/private_cases.csv --max-iterations 20 --time-budget-min 10 --horizon d1
smcub confirm-promotion state/self_evolve/<loop_id>/promotion_packet.json --decision promote --note "manual approval"
```

## 5 秒体验复盘闭环

真正有价值的复盘，不是看一眼盈亏就完事，而是把每一次判断拆成：计划是什么、证据是什么、结果是什么、下次怎么改。

一条命令跑完整个 toy 闭环：

```bash
git clone https://github.com/myc0576/SmartMoney-Cub.git
cd SmartMoney-Cub
pip install -e ".[dev]"
smcub loop --preset toy --agent-trigger "自进化"
```

运行后会在本地生成：

- `loop_report.md`
- `trace.jsonl`
- `case_record.json`
- `memory.md`
- `evolution_ledger.jsonl`

输出摘要会保持这个形状：

```json
{
  "status": "ok",
  "loop_name": "observe_candidate_plan_position_outcome_review_rule_update",
  "preset": "toy",
  "champion_mutated": false,
  "network_required": false,
  "telemetry": false,
  "safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
}
```

## 核心理念：系统 > 感觉

单次判断会忘，系统会进化。

`smartmoney-cub-harness` 把一次复盘拆成一条可审计链路：

```text
Plan -> Observe -> Record -> Outcome -> Evaluate -> Memory -> Rule Candidate
```

这条链路对应的是：

| 环节 | 作用 |
| --- | --- |
| Plan | 写清楚当时的计划、假设和风险条件 |
| Observe | 记录只读观察，不把观察变成买卖指令 |
| Record | 生成 manifest、decision、trace 等可审计产物 |
| Outcome | 等 D1/D3 结果出现后再评价，不偷看未来 |
| Evaluate | 检查决策质量、数据质量和安全合同 |
| Memory | 把复盘变成本地 Markdown 记忆 |
| Rule Candidate | 只提出 challenger 规则候选，不自动改 champion |

每一次错误都应该被拆解，每一条规则都应该被验证或淘汰。这个项目做的不是预测，而是帮你把主观判断训练成可复盘的系统。

## 给普通用户

你不需要券商 API，不需要量化背景，也不需要把私有资料放进公开仓库。你可以在本地整理这些只读输入：

- 交易计划文本。
- 交易日志 CSV。
- 同花顺或券商截图。
- 只读导出文件。
- 手写复盘笔记。
- toy offline 示例，用来先学习流程。

Harness 帮你结构化这些问题：

- 当时的 thesis 是什么？
- invalidation、time stop、give-up conditions 是否写清楚？
- 数据源、available time、data quality 是否可靠？
- D1/D3 之后结果如何？
- 这次失败是执行问题、证据问题，还是规则问题？
- 有没有值得进入 challenger 状态的规则候选？

## 给 AI 助手：只读复盘协作

AI 助手在这个仓库里只能扮演 reviewer、challenger、archivist、drift detector 或 systems assistant。它们帮助你复盘，不替你承担交易动作。

| 角色 | 可以做什么 | 不能做什么 |
| --- | --- | --- |
| Reviewer | 总结计划、证据、延迟结果和复盘评分 | 把复盘结论改写成买卖指令 |
| Challenger | 生成反方证据问题和缺失风险清单 | 只挑支持原判断的证据 |
| Archivist | 把本地产物整理成可携带 Markdown 记忆 | 把真实账户、截图或私有路径提交到公开仓库 |
| Drift Detector | 对比当前行为和历史规则 | 绕过指标与人工确认提升 champion |
| Systems Assistant | 拆解目标、风险、心理和结果 | 覆盖人的最终判断或执行交易 |

安全 agent workflow：

1. 读 `AGENTS.md` 和 [docs/harness-contract.md](docs/harness-contract.md)。
2. 运行 `smcub doctor`。
3. 运行 `smcub loop --preset toy --agent-trigger "自进化"`。
4. 打开 `loop_report.md` 和 `trace.jsonl`。
5. 提出复盘、安全、redaction、schema 或 workflow 改进。
6. 规则更新保持 challenger 状态。
7. champion 变更只通过显式人工确认路径发生。

详见 [docs/agent-loop.md](docs/agent-loop.md) 和 [docs/agent-integration.md](docs/agent-integration.md)。

## 优秀开源项目集成矩阵

这个 harness 会持续预留优秀开源项目的接入位。集成的目标不是制造更激进的交易信号，而是把外部工具的输出纳入只读复盘、证据整理和规则治理。

| 项目 / 类别 | 当前状态 | 可以怎样接入 harness | 安全边界 |
| --- | --- | --- | --- |
| [wbh604/UZI-Skill](https://github.com/wbh604/UZI-Skill) | 推荐搭配 / 生态接入位 | 作为外部分析报告或 agent skill 灵感来源，输出只能作为本地复盘材料进入 reviewer / challenger 流程 | 不声明内置运行时集成；不把分析结论变成买卖指令 |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | optional documented adapter / 用户自选外部引擎 | 用户本地运行 TradingAgents 生成多智能体分析/候选报告，或显式开启 optional local bridge 生成只读 review packet；该 packet 进入 reviewer / challenger / D1-D3 outcome review / rule candidate 流程 | 用户自行配置 LLM/API key；harness 不保存、不收集、不上传 key；不连接券商；不下单；不把 TradingAgents 输出直接当交易指令 |
| 数据源适配项目 | 预留 | 只读导出、toy fixture、公开样例 schema | 不接 broker execution，不写账户，不下单 |
| 报告生成项目 | 预留 | 把 `loop_report.md`、case record、ledger 转成更好的本地阅读材料 | 不上传私有复盘，不发布真实持仓 |
| Agent skill 项目 | 预留 | 增强 reviewer、challenger、archivist、drift detector 的协作体验 | 不允许越权到交易执行 |
| 评估 / 回测项目 | 预留 | 帮助评估规则候选和样本质量 | 不跳过 D1/D3 provenance 与 future-leakage 检查 |
| 知识记忆项目 | 预留 | 管理本地 Markdown memory、case bank、evolution ledger | 不上传私有交易逻辑 |

接入规则见 [docs/integrations.md](docs/integrations.md)。

## 可选接入 TradingAgents

TradingAgents 适合已经会配置 LLM provider、并希望把外部多智能体金融分析能力接入本地复盘系统的用户。默认 toy loop 不需要 TradingAgents，也不需要任何 LLM/API key；`smartmoney-cub-harness` 本身不托管、不读取明文、不提交、不上传 TradingAgents 的 key。

推荐两种模式：

1. `report-only mode`：用户独立运行 TradingAgents，把本地报告导入 harness，生成只读 review packet。
2. `optional local bridge mode`：用户已经在本地安装并配置 TradingAgents 后，显式传入 `--allow-network` 和 `--ack-external-llm`，由 adapter 包装外部分析结果为 review packet。

```bash
# report-only：用户先在 TradingAgents 中生成报告，然后导入本 harness
smcub tradingagents-ingest \
  --report path/to/tradingagents_report.md \
  --ticker 600519.SS \
  --analysis-date 2026-07-06 \
  --output artifacts/tradingagents_review_packet.json

# optional local bridge：仅当用户本地已经安装并配置 TradingAgents 后使用
smcub tradingagents-doctor
smcub tradingagents-run \
  --ticker 600519.SS \
  --analysis-date 2026-07-06 \
  --output artifacts/tradingagents_review_packet.json \
  --allow-network \
  --ack-external-llm
```

TradingAgents 的输出只会进入 reviewer / challenger / evidence / case-review 流程。它不能成为买入、卖出、下单、撤单、自动执行或账户操作的指令；任何 rule candidate 进入 champion 仍然必须由人显式确认。

## 安全边界：你的系统，只属于你

交易逻辑和复盘记忆是私有资产。`smartmoney-cub-harness` 的设计原则是：你的交易系统只在你本地进化。

对市场和执行，它永远是只读的；对你的交易日志，它是可写的。你的成交、笔记和回测记录保存在
本地或你的租户存储里，永远不会提交进这个仓库。

每个 manifest、decision、outcome、evaluation、registry、doctor output 和 loop output 都必须携带：

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

这行声明只断言“不执行交易”，不代表系统不能写入：它写入你自己的日志和报告，
但永远不会下单、撤单或修改券商账户。

项目默认：

- Local-first。
- Offline by default。
- No telemetry。
- No upload。
- No trading execution。
- No broker automation。
- CLI 输出前先 redaction。
- 公开仓库只使用 toy examples；真实交易数据只存在于运行时存储。

它明确不做：

- 不下单。
- 不撤单。
- 不修改账户。
- 不自动化券商。
- 不连接真实交易执行。
- 把真实交易记录、真实 watchlist、账户数据、私有策略 prompt、私有路径、credentials 或 cookies 提交进仓库。

运行：

```bash
smcub privacy-audit
smcub doctor
```

## Privacy

This project does not collect, upload, sell, or learn your trading logic. The core runs offline with no telemetry, no remote database, and no real account connection. Hosted tenant mode is opt-in and drives your own tenant store behind the platform login.

Your private trading logic and your real trades should remain in your local or tenant store. They must not be copied into the public repository. Public examples must stay toy-only.

See [docs/privacy.md](docs/privacy.md) and [docs/public-vs-private-quantkb.md](docs/public-vs-private-quantkb.md).

## 界面入口在哪里

界面由本地工作台服务提供，不能直接从磁盘打开：

```bash
npx smartmoney-cub        # 或：smcub workbench
# 然后打开 http://127.0.0.1:8787
```

直接用浏览器打开 `gui/index.html` 会看到空白页，这是预期行为。那个文件是构建入口，
引用的是尚未编译的源码，也没有本地接口可以调用。服务返回的页面里带着同样的说明，
所以误用 `file://` 打开时会告诉你该怎么做，而不是一片空白。

需要热更新时请启动开发服务器，它会把 `/api` 代理到本地服务：

```bash
cd gui && npm install && npm run dev
```

## CLI Commands

```bash
smcub loop --preset toy --agent-trigger "自进化"
smcub privacy-audit
smcub self-evolve --input-csv path/to/private_cases.csv --max-iterations 20 --time-budget-min 10 --horizon d1
smcub confirm-promotion state/self_evolve/<loop_id>/promotion_packet.json --decision promote --note "manual approval"
smcub inspect-artifacts <run_dir>
smcub collect-case <run_dir>
smcub append-ledger --event EVENT --payload-json FILE
smcub save-memory --case-record FILE
smcub tradingagents-doctor
smcub tradingagents-ingest --report path/to/tradingagents_report.md --ticker 600519.SS --analysis-date 2026-07-06
smcub tradingagents-run --ticker 600519.SS --analysis-date 2026-07-06 --allow-network --ack-external-llm
smcub doctor
smcub validate-manifest examples/sample_run/run_manifest.json
```

## Development Checks

```bash
pip install -e ".[dev]"
pytest -q
python -m smartmoney_cub_harness.cli doctor
python -m smartmoney_cub_harness.cli --help
```

## Public Boundary

The public repo can include schemas, loop runtime, toy examples, redaction, case bank, local Markdown memory format, evolution ledger, challenger/champion governance, integration guidance, and agent runbooks.

The public repo must not include real trades, real watchlists, account data, private QMT paths, private strategy prompts, key stock-picking logic, secret scoring weights, credentials, cookies, or local private workspace paths.

`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` remains the public boundary and runtime safety declaration.

## License

MIT. See [LICENSE](LICENSE).
