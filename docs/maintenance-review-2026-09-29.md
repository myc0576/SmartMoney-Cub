# 2026-09-29 Benchmark 与生态反馈人工审查记录

状态：本地维护已完成；真实服务与远端的最新复核部分受当前网络失败限制，历史远端 receipt 不作为本轮 fresh check 通过证据。远端此前仅发生本轮授权范围内的 Hermes #123396 与 Awesome-Evals #112 分支/body 更新，没有合并、发布、删除分支或 Fork 同步操作。
安全声明：`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`。

## 1. 实际 240-case 结果

从同一 `artifacts/benchmark/typesafe_checkpoint.json` 续跑，未重新评测原 62 cases。
开始前 `GET /v1/models` 返回 HTTP 200；只运行一次 `--resume-typesafe`，后端每次请求最多 3 次尝试。
本轮起止：2026-09-29 02:13:31–02:16:22 UTC（北京时间 10:13:31–10:16:22）。
完成 checkpoint：240 cases，1,020 items，四轨各 60 cases；原 62 条记录逐条相等。
运行 ID：`run_20260929_021332_240`。
运行 hash：`7a40b49e57d594da8b45e835417e6f7880d7fa48583349da4559ff1b15f8be45`。

| 系统 | 完成度 | Accuracy | Case-level 95% CI | Macro F1 | 记录费用 |
|---|---|---|---|---|---|
| Deterministic baseline | 240 / 240 | 83.33% | [81.57%, 85.10%] | 0.7792 | $0 |
| TypeSafe `jev-1.13.0` | 240 / 240 | 78.43% | [76.08%, 80.69%] | 0.7350 | $0.009175 |

TypeSafe model_requested 为 `jev-latest`，model_resolved 为 `jev-1.13.0`；runner 拒绝续跑中模型改变。
记录 218,438 input tokens、43,836 output tokens；P50/P95/P99 分别为 815.315 / 4480.416 / 22143.683 ms。
费用来自成功响应 usage 与[官方模型单价](https://docs.typesafe.ai/models)（输入 $0.042/Mtok，输出免费），含 checkpoint 的舍入。
预算上限一直为 $4.00；历史超时/重试请求是否计费没有账单证据，因此此数值不是最终账单或全部网络尝试的计费证明。
按当前模型最大上下文和最多三次尝试，本轮 178 cases 的保守请求预留上界约 $1.47，未接近 $4。
原始 case/question 预测、标签、置信度、延迟、usage、费用保存在 run.json；模型元数据为全系统共享且受一致性验证。

统计方法为四轨分别按 case 有放回抽样，保留每个 case 的所有问题，seed `20260927`、10,000 replicates、2.5/97.5 percentile。
这只是 early-stage synthetic/toy offline benchmark。保留的 item-level McNemar 字段不能当作处理了 case 内相关性的显著性检验；retry_rate 字段也不能用于证明历史网络请求从未重试。

本地 [run.json](../assets/benchmark/run.json) 及 18 张 PNG/SVG 已经严格门禁后同步，**尚未在远端发布**。
远端 `myc0576/SmartMoney-Cub:main` 核验 SHA 为 `7395e4b6d42d59820c890d8aecd5752b2def7a54`，仍是 2026-09-20 v1 run，hash `00e9ef2f5a9c919ca35697d16d30af3faca099c0ff1cbefd69d9eb3804c223ec`。
本次 run 的 git_sha 指向运行时 HEAD；运行使用已有未提交实现，不能把该提交本身称为完整可复现的新源码版本。人工审查后若授权发布，应同时发布代码、测试和产物。

## 2. Awesome Quant AI #63

来源：[PR #63](https://github.com/leoncuhk/awesome-quant-ai/pull/63)、[维护者原始评论](https://github.com/leoncuhk/awesome-quant-ai/pull/63#issuecomment-5851516826)、[上游 main README](https://github.com/leoncuhk/awesome-quant-ai/blob/main/README.md)。

最新状态 **MERGED**，2026-09-27 01:10:08 UTC 合并，merge SHA `ac89cce6148322db6cbca6587aad00faabce6a4a`。
上游最终条目明确 evidence packs、deterministic replay、D1/D3、240-case synthetic、early-stage，并只链接 canonical repository，未保留 relay 链接。

| 原意（转述） | 当前处理状态 | 仍需处理 |
|---|---|---|
| 维护者实测 doctor、capture、outcome、pack build/replay 均可用，认可 MIT 与执行禁令 | 保留；本轮另有真实 CLI 联调 | 不是金融性能或生产成熟度背书 |
| 描述应具体说明冻结、回放和 D1/D3 评分 | 上游最终条目已采用 | 无需再改已合并 PR |
| 数据是模板化 synthetic/toy | 本地中英文 README、图表明确；上游已采用 | 后续所有投稿保持同一口径 |
| 项目 early-stage，用户基础扩大后再申请删去 | 本地与上游保留 | 不提前移除 |
| hosted LLM relay 不应作为 harness 官网收录 | 上游已去掉 relay 链接 | 本地投稿草稿仅使用 canonical repo |
| 1,020 是 items，只有 240 个独立 case；逐 item Wilson 低估不确定性，建议 case bootstrap（非合并阻塞） | 两系统 v2 均已按 track 分层 case bootstrap，准确区分 240 cases / 1,020 items | 远端 main 仍旧 v1，需人工授权后才可同步 |
| 上游条目写着 no broker connection | 属于维护者最终文本，已核对 | core 允许用户授权的只读账户导入，此表述对整个 core 过宽；未来可提最小措辞修正，本轮不操作上游 |

Fork `myc0576/awesome-quant-ai` 的 GitHub parent 正确；相对上游 main 为 ahead 0 / behind 0，无需同步。

## 3. Hermes #123396

真实来源：[NousResearch/hermes-agent #123396](https://github.com/NousResearch/hermes-agent/pull/123396)、[维护者评审](https://github.com/NousResearch/hermes-agent/pull/123396#issuecomment-5848715418)。
**OPEN，未合并**。`kraayenjon/hermes` 的 API 404 是错误仓库地址，不能据此推断 Hermes PR 消失。
当前 catalog diff 只有 `plugin-catalog/smartmoney-cub.yaml`，当前 PR head/catalog commit 为 `799e7b94278d2e72c346716f5521e3fba2ae6de8`，插件 pin 为 `67e5a73d32fde4d0b68d3562a930064bf8b0d103`。
[固定插件源码](https://github.com/myc0576/hermes-smartmoney-cub/tree/74279466a019d0ff3ccd1615ff660e224fa644d5) 已下载到 ignored artifacts 做只读审查。
PR 正文已更新为插件版本 `0.2.0`、当前插件 pin 与 catalog commit，并披露 replay 写入、用户安装的 `smcub` binary 未被插件 SHA 固定以及路径边界不是 OS sandbox。

| 原意（转述） | 实测/源码状态 | 仍需处理 |
|---|---|---|
| 原 build argv 无法调用 v1.1.0 CLI；需要 output_dir positional、重复 --sample、必需 --rule-candidate、--horizon | 当前插件使用 `build-evidence-pack --sample=... --rule-candidate=... --horizon=... -- output_dir`；真实 D1/D3 构建与回放通过 | 单插件调用只传一个 sample 合法；core 支持重复 --sample |
| run_root 必须 fail-closed，未配置、外部输入和外部输出不能只警告 | 当前插件默认空 root 且路径工具拒绝；doctor 可不配 root；已有回归通过 | core CLI 是本机用户命令，root 配置由插件负责，不能声称所有 core 命令都被插件 sandbox |
| output_parent、symlink、file-as-directory 需验证 | 插件已解析现存输入、输出以及最近现存父目录；测试通过 | 本轮发现 core 内部文件链接逃逸，已在本仓库修复；旧安装版尚未包含修复 |
| manifest 必须声明 config_schema/run_root，README 描述一致 | 当前 pin 已声明并说明默认 fail-closed | 保留此声明 |
| horizon 限 d1/d3，rule candidate 必需并存在 | 当前 pin 与 CLI 已限制；D1/D3 真实联调通过 | 插件仅验证 JSON 后缀，JSON 解析由 CLI 负责；不能描述成插件已做完整 schema 验证 |
| positional 路径前加 --，shell=False | 当前 pin 已实现；leading-dash 路径测试通过 | PR 正文“拒绝 option-like paths”不准确，实际是解析为绝对路径后安全传递 |
| 安装说明统一；不是 PyPI 包 | README 指向 source/GitHub wheel，catalog 亦明确 | bundled skill 仍泛称安装且 `capture-run <offline-command>` 非完整 CLI 用法；需在独立插件仓库修正文档，本轮仅给建议 |
| 不能把 no-trading 写成文件系统只读；必须披露所有写入和本地未固定 smcub 二进制 | manifest/README/catalog 披露了 evaluate 和 build；保留 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` | **仍不完整：replay 也写 replay_report.json**；且插件 SHA 不固定用户 PATH/config 指向的 harness 版本 |
| 修复后重 pin 供维护者复审 | 当前 pin、正文和 catalog 已对齐；19 tests 与 surface check 通过 | 当前 PR checks 为空，等待上游维护者复核 |

真实 CLI 联调发现的全部业务写入：

| 命令 | 写入 |
|---|---|
| evaluate-run | `<run_dir>/eval.json`，可能覆盖既有评分；D1/D3 共用文件名 |
| build-evidence-pack | `<output_dir>/rule_candidate.json`、`evidence_pack.json`、`evidence_pack.sha256`、`samples/<id>/{run_manifest.json,decision.json,outcome_d1或d3.json,evaluation.json}`；会创建所需目录并可能覆盖同名文件 |
| replay-evidence-pack | `<pack_dir>/replay_report.json`，包括 pending/失败报告路径；可能覆盖 |
| doctor / validate-envelope / inspect-artifacts | 此次源码与 toy 联调未观察到业务文件写入 |

Python/宿主运行时可能产生字节码或缓存；toy 联调关闭了 child bytecode 写入。这不是“任何环境下没有其他 filesystem writes”的承诺。
新增 `confined_artifact_path` 检查 eval、pack 子文件和 replay report 的真实目标，拒绝现存 symlink 逃逸；这是调用时路径检查，不是抵御其他进程并发替换目录的 OS sandbox。
更改仅在本仓库；独立插件远端和用户已安装 CLI 均未更新，因此不能声称 Hermes 反馈已全部关闭。

Fork `myc0576/hermes-agent` parent 正确；main ahead 0 / behind 2063。本轮没有同步远端。

## 4. Awesome-Evals #112

来源：[PR #112](https://github.com/benchflow-ai/awesome-evals/pull/112)、[当前 diff](https://github.com/benchflow-ai/awesome-evals/pull/112/files)、[历史 responder run](https://github.com/benchflow-ai/awesome-evals/actions/runs/36216218695)。
当前 **OPEN**，只改 README 一行（+1/-0），位置是第 9 节 Agent-specific evaluation；无维护者评论、正式 review 或行内评论，当前 checks 为空。
因此 dated/source-verifiable/self-submission 是本次核查的投稿要求与现有正文内容，不能捏造为维护者已发出的评论。

| 要求/发现 | 当前状态 | 仍需处理 |
|---|---|---|
| 明确 self-submission 与 author affiliation | 正文已写作者自荐 | 保留 |
| dated、source-verifiable | 正文已改为公开 v1 artifact 的可核查事实，明确不声称本地 v2 已公开 | 继续等待上游维护者 review；不把空 checks 写成通过 |
| synthetic/early-stage 与能力边界 | 正文已明确 early-stage、synthetic/offline、只读账户导入和执行禁令 | 无需本地补充 |
| 最新 base/head/diff/check | 已重新读取当前 PR 元数据；见下表和 `remote-pr-status-current.json` | 两个 head 的 check runs/statuses 均为空，不等于 CI 通过 |
| responder 失败的性质 | 2026-09-26 workflow 对 actor 得到 read 权限，报没有 write permission；日志明确 PR_NUMBER 112 | 这是上游 Actions 权限问题，不是本项目内容测试失败；不能把历史失败附会为当前 head 检查 |

Fork `myc0576/awesome-evals` parent 正确；main ahead 0 / behind 0。

## 5. 最新 PR identity 与检查证据

所有查询均为 GET/只读。原始响应位于本地 `artifacts/maintenance/2026-09-29/` 的 `quant-*`、`hermes-*`、`evals-*` 文件。

| PR | Base repo / branch / SHA | Head repo / branch / SHA |
|---|---|---|
| Quant #63 | leoncuhk/awesome-quant-ai / main / `2959a2cc47d5bb9cc6087f5ddd88c0faf4c5d839` | myc0576/awesome-quant-ai / codex/add-smartmoney-cub-quant-ai / `e91745e6d5dc3216d1fc3ef548460824c56decb3` |
| Hermes #123396 | NousResearch/hermes-agent / main / `11e22f25823cdb0bec7d86e8591f6415eb0b58e6` | myc0576/hermes-agent / codex/add-smartmoney-cub-catalog / `799e7b94278d2e72c346716f5521e3fba2ae6de8` |
| Evals #112 | benchflow-ai/awesome-evals / main / `1b8928b60a9d41cbab371610d741d39a3fd50860` | myc0576/awesome-evals / codex/add-smartmoney-cub-evals / `b5e14f10fc4ff5f812d47075b41ca169c5fc066c` |

三个 head 的 check-runs total_count = 0，commit statuses total_count = 0；当前两项开放 PR 的 checks 为空，不得写成绿色 CI。
合并后无需改写 Quant #63。Hermes/Evals 的本轮授权更新已完成，后续仍只在再次授权后更新外部内容。

## 6. 扩展检索到的其他投稿

检索范围：GitHub 搜索 `SmartMoney-Cub author:myc0576`，排除自身仓库，得到 13 个外部 PR；逐个读取 issue comments、reviews、review comments。以下“无评论”仅指本次可访问的这些 API，不能保证所有私下或已删除反馈均被覆盖。

| 来源 | 最新状态 | 意见原意与处理 |
|---|---|---|
| [thuquant/awesome-quant#73](https://github.com/thuquant/awesome-quant/pull/73) | OPEN | 本次未发现评论/review；没有可据此新增的修复要求。 |
| [georgezouq/awesome-ai-in-finance#272](https://github.com/georgezouq/awesome-ai-in-finance/pull/272) | OPEN | 本次未发现评论/review；没有可据此新增的修复要求。 |
| [wilsonfreitas/awesome-quant#725](https://github.com/wilsonfreitas/awesome-quant/pull/725) | OPEN | 本次未发现评论/review；没有可据此新增的修复要求。 |
| [wangzhe3224/awesome-systematic-trading#182](https://github.com/wangzhe3224/awesome-systematic-trading/pull/182) | OPEN | 本次未发现评论/review；没有可据此新增的修复要求。 |
| [ai-boost/awesome-harness-engineering#286](https://github.com/ai-boost/awesome-harness-engineering/pull/286) | OPEN | 本次未发现评论/review；没有可据此新增的修复要求。 |
| [NousResearch/hermes-agent#123419](https://github.com/NousResearch/hermes-agent/pull/123419) | CLOSED | 本次未发现评论/review；没有可据此新增的修复要求。 |
| [wilsonfreitas/awesome-quant#726](https://github.com/wilsonfreitas/awesome-quant/pull/726) | CLOSED | 本次未发现评论/review；没有可据此新增的修复要求。 |
| [laplace0x/awesome-agent-trading#20](https://github.com/laplace0x/awesome-agent-trading/pull/20) | MERGED | 本次未发现评论/review；没有可据此新增的修复要求。 |
| [NousResearch/hermes-agent#123427](https://github.com/NousResearch/hermes-agent/pull/123427) | CLOSED | AI triage 明确判定与 #123396 重复；该 PR 已关闭，#123396 是开放的 canonical 投稿。[原评论](https://github.com/NousResearch/hermes-agent/pull/123427#issuecomment-5842952272)。不再创建重复投稿。 |
| [kraayenjon/awesome-jev#9](https://github.com/kraayenjon/awesome-jev/pull/9) | MERGED | 本次未发现评论/review；没有可据此新增的修复要求。 |

## 7. 本地修改与验收入口

- 保留此前的 benchmark v2、JEV 定价与重试、测试及全部未跟踪工作；本轮有原始文件 SHA 和内容备份。
- `scripts/dev-env.sh` 转发严格校验标志；`scripts/publish_benchmark_images.py` 在触碰 assets 前强制 run integrity 和适用的 TypeSafe 240-case gate。
- `safety.py`、`cli.py`、`evidence_pack.py` 补齐 eval / pack descendants / replay report 实际写入目标边界；新增六项 toy symlink 回归。
- `benchmark/render.py` 明确 synthetic/early-stage、case/items 数量与统计方法、小额费用六位小数，修正 calibration SVG 中未展开的模板和标题中的 XML 转义错误，新增全套 SVG 解析断言；本轮不修改前端。
- 中英文 README、Jev 文档、文档索引与本记录同步；更新本地 run.json 和 18 张图表。
- 新增四项 publication 回归，验证部分 TypeSafe / 篡改产物不会覆盖现有 public 目录，严格标志实际被转发，baseline-only 路径可用。

本地验收命令：

```bash
./scripts/verify.sh
./scripts/dev-env.sh benchmark verify assets/benchmark --require-typesafe-public
python3 -m pytest tests/test_review_write_boundaries.py tests/test_benchmark_publication.py -q
```

完整门禁：`./scripts/verify.sh` 退出 0，`1244 passed, 8 skipped, 2 xfailed`，doctor 安全声明通过。插件 19 tests 与 surface check 通过；前端 typecheck/build/visual report 也通过（25 views、0 failed、0 overflow、0 console errors）。证据保存在 `artifacts/maintenance/2026-09-29/`；最终收据见 `final-verification.json`，远端状态见 `remote-pr-status-current.json`。

## 8. 留给人工审查的外部事项

1. 审查本地完整 diff 与 TypeSafe 数据；公开 v2 实现和产物仍未发布。
2. Hermes 独立插件的三类写入、准确安装/capture 说明、当前源码 pin 与 CLI 版本边界已写入插件、catalog 和 PR body；当前 head 无 checks，等待维护者复核。
3. Awesome-Evals 已改为公开 v1 的 source-verifiable 文案，当前 head 无 checks；历史 responder 权限失败仍是上游事项。
4. Quant 上游最终 synthetic/early-stage 描述已确认，未来最小修正 no broker connection 的过宽表述；不重开已合并 PR。
5. Hermes Fork 落后 2063 提交，需在另获授权后同步；本轮不改变任何远端 Git 状态。

这是一份包含本地门禁和有限远端更新证据的维护交付，不是生产金融效果验证或全系统安全审计。

## 9. CLI 覆盖、AlphaTech、账户与行情的最新真实探测

本节记录本轮 CLI parity 维护后的最新状态，不能由 catalog、fixture 或本地缓存替代。
所有探测均保留 READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE。

### AlphaTech

最新观测时间为 `2026-09-30T15:14:15Z`。调用 `providers.check-models --allow-network` 成功返回 HTTP 200，`verified: true`、`persisted: true`，发现包含 `gpt-6-astra` 的实时模型列表；历史配置中的 `claude-opus-5` 被标记为 stale。官方价格 API 同时返回 HTTP 200 和 120 条记录。模型探测成功，但 $0.05 paid completion 未执行且保持 pending；cost、usage、balance、quota 均保持 pending/unverified。

本机默认运行时的 providers.setup 仍返回 configured_unverified，说明受保护的本地配置存在；不会在输出、参数或 artifact 中暴露 key。结果见
[alphatech-model-probe.json](../artifacts/maintenance/2026-09-29/alphatech-model-probe.json)。
这证明当前路由和模型发现可达，但不能证明一次 completion 的 usage、AlphaTech 账户计费、余额或配额。

用户已确认单次预算上限为 $0.05，并提供了官方价格页 https://alphatech.net.cn/pricing。当前公开接口返回 120 条记录；其中 gpt-6-astra 仅给出 tier billing expression、quota ratio 和 tier 字段，没有定义 p/c/cr/cc 的单位或到 USD 的换算，因此仍无法生成可重算的 input_usd_per_million / output_usd_per_million 价格文件。没有猜测价格或发起不可重算的付费请求。

### 账户连接

截至 `2026-09-30T15:14:15Z`，当前运行时报告 0 个已授权 live connection、0 个 live account；逐一执行 setup metadata 检查后七个 provider 全部为 `not_configured`（ccxt-binance、ccxt-okx、ibkr-flex、metatrader-investor、local-statement-directory、snaptrade-personal-mcp、vezgo）。都保留 pending；没有在未证明只读授权前执行 sync、分页、游标恢复、重启恢复或 disconnect。证据见
[account-connection-probe.json](../artifacts/maintenance/2026-09-29/account-connection-probe.json)。

### 行情

截至 `2026-09-30T15:14:15Z`，行情探测状态为：Eastmoney failed、Tencent pending、Stooq failed、Binance failed。Tencent 收到真实 bars 但缺少 available_at、decision_time 和可验证质量；Eastmoney 远端连接关闭，Stooq TLS 握手失败，Binance 受区域限制。没有任何 provider 被提升为成功，并且所有来源都仍须满足 available_at <= decision_time。证据见
[market-provider-probe-2026-09-29.json](../artifacts/maintenance/2026-09-29/market-provider-probe-2026-09-29.json)。

### 覆盖边界

smcub capabilities --json 已确认 CLI registry 的实际 operation 名称；registry 映射、toy/offline 测试和 HTTP/local parity 不等同于真实服务覆盖，也不等同于完整 WebUI 覆盖。未完成项仍包括 AlphaTech usage/cost/billing 验收、live 账户授权和同步恢复、带完整时间溯源的行情成功证据，以及完整前端视觉门禁。

本节最新事实来源为四个 probe artifact 与 `remote-pr-status-current.json`；远端状态为 Hermes catalog/head `799e7b94278d2e72c346716f5521e3fba2ae6de8`、Awesome-Evals head `b5e14f10fc4ff5f812d47075b41ca169c5fc066c`，两项 checks 均为空。所有探测和维护记录继续保留 `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`。
