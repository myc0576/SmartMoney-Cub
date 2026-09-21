# Integrations

`smartmoney-cub-harness` can reference and learn from strong open-source projects, but every integration stays inside the read-only review contract.

The goal is not to create stronger execution signals. The goal is to turn external analysis, reports, skills, and data shapes into better local review artifacts.

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

## Integration Contract

Every integration must preserve these rules:

- Inputs are read-only.
- Public examples use toy offline data only.
- External reports are evidence for review, not trading instructions.
- Agent outputs may create challenger rule candidates only.
- Champion mutation requires explicit human confirmation.
- No integration may place orders, cancel orders, modify accounts, automate brokers, or handle credentials.
- No integration may publish real trades, real watchlists, account data, private strategy prompts, or local private paths.

## Status Vocabulary

| Status | Meaning |
| --- | --- |
| `recommended-companion` | Useful alongside the harness, but not imported or executed by the harness runtime. |
| `reserved-slot` | A category intentionally left open for future open-source integrations. |
| `documented-adapter` | A documented local pattern exists, but it remains read-only and optional. |
| `optional-bridge` | A local bridge exists, but users must explicitly install and configure the upstream tool before use. |
| `runtime-integrated` | Code, tests, and docs prove the integration is part of the harness runtime. |

Do not label a project `runtime-integrated` until the repository contains the code path, tests, and safety documentation that prove it.

## Plugin Protocol

External projects are now integrated through the plugin protocol in
[plugins.md](plugins.md) rather than by editing the core. The runtime discovers,
validates, loads, and injects plugins automatically; installation, network access,
and model access stay user-initiated.

The curated catalog is available offline:

```bash
smcub plugin catalog
```

It records three integration levels — `companion`, `adapter`, and
`runtime-plugin` — and the boundary each project must respect. A catalog entry
grades the project; it never ships as a bundled dependency. The core release keeps
`dependencies = []` in `pyproject.toml`.

## Current Matrix

### 数据

| Project / Category | Status | Harness Role | Required Boundary |
| --- | --- | --- | --- |
| [akfamily/akshare](https://github.com/akfamily/akshare) | `documented-adapter` | A 股公开数据适配器：行情、财务与宏观公开接口。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |
| [TuShare Pro](https://tushare.pro) | `documented-adapter` | TuShare Pro 历史行情与财务数据，需要官方 token。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |
| [BaoStock](http://www.baostock.com) | `documented-adapter` | BaoStock 证券历史行情，免注册。上游以官网分发，无 GitHub 仓库。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |
| [Micro-sheep/efinance](https://github.com/Micro-sheep/efinance) | `documented-adapter` | 东方财富公开行情接口的 Python 封装（efinance）。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |
| [ranaroussi/yfinance](https://github.com/ranaroussi/yfinance) | `documented-adapter` | Yahoo Finance 历史行情与基本面（yfinance）。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |
| [pydata/pandas-datareader](https://github.com/pydata/pandas-datareader) | `documented-adapter` | Stooq 历史行情，通过 pandas-datareader 读取。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |
| [mortada/fredapi](https://github.com/mortada/fredapi) | `documented-adapter` | 圣路易斯联储 FRED 宏观时间序列，需要免费 API key。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |
| [腾讯行情快照](https://gu.qq.com/) | `documented-adapter` | 腾讯证券公开行情接口没有独立维护的 Python 发行版，由 harness 内置的只读抓取适配器提供，不安装第三方代码。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |

### 绩效与风险

| Project / Category | Status | Harness Role | Required Boundary |
| --- | --- | --- | --- |
| [ranaroussi/quantstats](https://github.com/ranaroussi/quantstats) | `documented-adapter` | 绩效报告与风险统计：收益、回撤、夏普等指标。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [stefan-jansen/empyrical-reloaded](https://github.com/stefan-jansen/empyrical-reloaded) | `documented-adapter` | 收益、回撤与风险指标计算（Quantopian empyrical 维护分支）。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [stefan-jansen/pyfolio-reloaded](https://github.com/stefan-jansen/pyfolio-reloaded) | `documented-adapter` | 组合归因与事件分析报告。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [dcajasn/Riskfolio-Lib](https://github.com/dcajasn/Riskfolio-Lib) | `documented-adapter` | 组合风险与约束分析。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [pyportfolio/pyportfolioopt](https://github.com/pyportfolio/pyportfolioopt) | `documented-adapter` | 组合优化结果评估：有效前沿与风险模型。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [skfolio/skfolio](https://github.com/skfolio/skfolio) | `documented-adapter` | 基于 scikit-learn 的样本外组合风险评估。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |

### 研究与评估

| Project / Category | Status | Harness Role | Required Boundary |
| --- | --- | --- | --- |
| [xgboosted/pandas-ta-classic](https://github.com/xgboosted/pandas-ta-classic) | `documented-adapter` | 技术指标特征计算（pandas-ta 的持续维护分支）。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [rsheftel/pandas_market_calendars](https://github.com/rsheftel/pandas_market_calendars) | `documented-adapter` | 交易日历与时间语义，用于 available_at 与决策时间的对齐校对。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [microsoft/qlib](https://github.com/microsoft/qlib) | `recommended-companion` | 微软 Qlib（PyPI: pyqlib）的因子研究与 point-in-time 评估。仓库分发为主，安装后由 harness 以只读方式调用。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | `documented-adapter` | 回测证据与未来数据检查。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [kernc/backtesting.py](https://github.com/kernc/backtesting.py) | `recommended-companion` | 轻量回测框架，用于策略原型的样本外检查。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [mementum/backtrader](https://github.com/mementum/backtrader) | `recommended-companion` | 经典回测框架，用于历史策略复盘。 | 只读计算结果与报表；不产生买卖指令，不写入账户与订单。 |
| [zvtvz/zvt](https://github.com/zvtvz/zvt) | `recommended-companion` | 本地量化数据与选股框架，仅作为只读数据与因子来源。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |

### Agent

| Project / Category | Status | Harness Role | Required Boundary |
| --- | --- | --- | --- |
| 多 Agent 复盘 (`multi-agent-trade-review`) | `documented-adapter` | 由 harness 内置的 reviewer/challenger 协作链提供，无需安装第三方包。 | 只生成 challenger 候选与复盘观察；champion 变更必须人工确认。 |
| 反方规则质询 (`challenger-rule-critic`) | `documented-adapter` | 由 harness 内置的 challenger 规则质询能力提供。 | 只提出候选与反例；不自动晋级 champion，不改写规则库。 |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | `documented-adapter` / `optional-bridge` | 多智能体交易分析框架。用户自行运行生成报告后导入为只读复盘材料；harness 不代管其 LLM 密钥。 | 用户自备 LLM/API key 并在本仓库之外配置；harness 不保存、不收集、不上传密钥；其输出只能作为复盘证据，不得转成订单意图或执行计划。 |
| [wbh604/UZI-Skill](https://github.com/wbh604/UZI-Skill) | `recommended-companion` | 外部分析技能与叙述灵感，输出可本地保存后进入 reviewer/challenger 流程。 | 只能描述为推荐搭配与生态接入位；不得称为内置依赖，不得把结论变成买卖指令。 |
| [shy3130/tick-stock-panel](https://github.com/shy3130/tick-stock-panel) | `recommended-companion` | Tick 级行情面板项目，作为只读行情可视化参考实现。 | 只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。 |
| [vnpy/vnpy](https://github.com/vnpy/vnpy) | `recommended-companion` | 交易框架。因其自身包含下单与账户能力，harness 只把它作为 companion 记录，永不挂载为运行时插件。 | 本项目自带下单与账户能力，因此 harness 绝不安装、挂载或调用它；仅作为对照参考记录在册。执行禁令绝对不变。 |

## UZI-Skill Positioning

UZI-Skill is a strong example of agent-facing financial analysis packaging and a useful companion project for users who already run it in their own agent environment.

In this harness, UZI-Skill should be described carefully:

- Good: "recommended companion", "ecosystem slot", "external analysis that can be reviewed locally".
- Good: "its output can become read-only evidence inside a review packet".
- Not allowed: "built-in integration", unless runtime code and tests are added.
- Not allowed: "use this analysis to trade", "auto-trade from UZI output", or any equivalent execution framing.

## TradingAgents Positioning

TradingAgents is a powerful external LLM multi-agent financial analysis framework. In this project, it is only an external optional analysis engine.

Allowed contributions:

- Candidate reports.
- Debate summaries.
- Risk notes.
- Watchlist rationale.
- Decision evidence.

Not allowed contributions:

- Order intent.
- Broker action.
- Execution plan.
- Account operation.
- Automatic champion mutation.

Current status is `documented-adapter` / `optional-bridge`. It may only be called `runtime-integrated` after this repository contains code, tests, and safety documentation proving the integration remains read-only, local-first, and human-gated.

## Future Integration Checklist

Before adding any new project to the README matrix:

1. Identify the integration status.
2. State the read-only input or artifact it contributes.
3. State what the harness must never do with it.
4. Confirm public examples remain toy-only.
5. Confirm the safety declaration appears in any new manifest, decision, outcome, evaluation, registry, doctor, or loop output touched by the integration.
6. Add tests when the integration becomes runtime behavior.
7. For any LLM-based integration, declare that users configure their own keys outside this repository.
8. Confirm keys never enter artifacts, git, stdout plaintext, or test fixtures.
9. Confirm network calls default to disabled unless the user explicitly provides `--allow-network` and `--ack-external-llm` or an equivalent local consent gate.

## Human Gate

Integrations may improve review quality, evidence organization, and challenger suggestions. They must not turn the harness into an execution system.

Champion rule changes remain human-gated:

```bash
smcub confirm-promotion state/self_evolve/<loop_id>/promotion_packet.json --decision promote --note "manual approval"
```
