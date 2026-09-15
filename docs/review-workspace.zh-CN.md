# 复盘工作区（Review Workspace）

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

复盘工作区是一个本地 SQLite 数据库，存放复盘用例、D1/D3 结果、插件证据与规则状态。
它在数秒内回答问题，而不可变的证据保留在 Evidence Pack 与插件信封里。

## 职责划分

| 存储 | 负责什么 |
| --- | --- |
| SQLite 工作区 | 用例、结果、证据索引、规则状态、筛选、计数 |
| Evidence Pack 与信封 | 不可变、带哈希、可回放的凭证 |
| 插件状态库 | 插件身份、生命周期状态与审计历史 |

SQLite 只是便利索引。**工作区里出现的任何一个数字，都必须能追溯到带哈希的产物。**

## 复盘用例（Review cases）

用例锚定的是**一次决策**，不是一笔成交。支持的 action 有
`BUY`、`SELL`、`HOLD`、`FLAT`、`AVOID`、`NO_DECISION`，以及 harness 语义标签
`ALERT`、`WATCH`、`EMPTY_POSITION`、`ERROR`、`SILENT`。

空仓与回避（FLAT / AVOID）是一等公民。**空仓离场也是一次值得复盘的决策**，
它和一次买入享有同样的证据待遇。

## 风险契约（The risk contract）

每一条**非静默**的观察（不是 `SILENT`，也不是从历史成交里还原出来的事实），都必须携带：

| 字段 | 含义 |
| --- | --- |
| `invalidation_price` | 逻辑被证伪的价格位 |
| `time_stop` | 这条观察的失效时间 |
| `give_up_conditions` | 什么情况下放弃这个想法 |
| `data_source` | 输入来自哪里 |
| `available_at` | 这个输入何时变得可用 |
| `data_quality_flag` | `ok`、`stale`、`partial`、`missing` 或 `error` |

任何字段缺失，用例会被拒绝，并明确列出缺了哪几个字段名。
如果 `available_at` 晚于 `decision_time`，用例会被判定为**未来数据泄漏**并拒绝。

## 命令行

```bash
smcub workspace add-case case.json
smcub workspace list-cases --action AVOID
smcub workspace show-case RT-600111-1
smcub workspace record-outcome RT-600111-1 --horizon d1 --return-pct 3.5
smcub workspace import-csv exports/fills.csv
smcub workspace summary
smcub workspace rules                 # 规则库，并附带晋升门禁缺口
smcub workspace rules --status champion
smcub workspace promote-rule RULE-1 --note "reviewed the gates"
smcub workspace reject-rule RULE-1 --note "superseded by RULE-2"
```

数据库默认位于 `state/workspace/review.db`，可用 `--db` 覆盖。
`register-candidate`、`self-evolve` 与 `confirm-promotion` 都接受 `--workspace-db`，
它们写入的 JSON 规则注册表会同步映射到这一个规则库里。

## 结果永不改写历史

记录一次结果会写入独立的一行，以 `(case_id, horizon)` 为主键，**不会修改用例本身**。
决策上下文保持冻结时的原样，这正是后续回放有意义的前提。

## CSV 导入

`import-csv` 会跑一遍持仓台账，把每一个已平仓的完整回合导入为一条 `IMPORTED` 用例。
导入行是历史事实，不是前瞻性观察，所以**不会为它们编造风险契约**。

歧义永远不会被悄悄当成一笔成交。当日卖出会被标记为 T+1 违规；
没有前置持仓的卖出会被标记为成本基准未知；超卖会被标记为阻断性问题。
导入结果会报告台账状态与每一条问题，让用户能回去修正导出文件。

## 规则状态（Rule state）

`rule_state` 跟踪 challenger、recommendation、champion、rejected、deferred 五种状态。
**没有人工写下的确认说明，就写不进 champion 行。** 这条约束在 workspace 层强制，
所以无论是面板、插件，还是模型直接写数据库，都绕不过它。

两道门禁是**刻意分开**的。阈值门禁——`sample_count >= 20`、`false_alert_rate <= 0.2`、
`missed_opportunity_rate <= 0.25`、未来数据泄漏为零、风险契约违规为零——决定的是
证据**有没有资格产生一条晋升"建议"**。它并不授权真正的变更。
真正的门禁是人写下的那条说明，**只有它能写出 champion 行**。
所以 `promote-rule` 会先报告尚未满足的门禁项，然后只在你提供了说明时才继续；
说明为空或缺失一律拒绝，且不写入任何东西。

每一条规则在被读取的地方都会带上它的门禁缺口，取自整个产品共用的那一份冻结阈值检查，
因此界面与命令行不可能对"这条规则还缺什么"给出不一致的答案。

复盘助手永远只能提出 challenger。提一条候选时，它会记录自己的门禁缺口、
在 workspace 数据库旁追加一条 `evolution_ledger.jsonl` 记录，
并在同一目录追加一段可读的 `memory.md` 片段。
**它无法晋升**，它能调用的任何工具都碰不到 champion 行。

## 统计口径与它的局限

`workspace summary` 会报告各项计数、任何均值背后的样本量，
并明确写出一句声明：这个样本是**自选的复盘历史，不是受控实验**。
小样本就按小样本呈现。

