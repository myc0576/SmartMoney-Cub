# Jev 生态接入、四轨架构与金融评测基准指南 (Jev Ecosystem & Benchmark Guide)

`smartmoney-cub-harness` 深度对齐并集成了 Jev 生态规范，旨在为量化与交易复盘场景提供类型化 AI 审查与确定性规则校验；市场与执行只读，用户的本地评测、日志和复盘产物可写。

`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`

---

## 官方资源 / Official Resources

- **Jev / TypeSafe 官方网站**: [https://typesafe.ai/](https://typesafe.ai/) — Jev 推理引擎开发方 TypeSafe 官方主页。
- **OpenRouter Jev 模型页面**: [https://openrouter.ai/typesafe/jev](https://openrouter.ai/typesafe/jev) — OpenRouter 模型中心对 Jev 模型的官方托管与分发页面。

*注：本项目作为独立的只读复盘与评测工具，链接至上述官方资源仅供用户配置后端与查阅模型规范，并不代表 Jev 或 TypeSafe 对本项目的官方背书。*

---

## 1. 架构总览与核心设计原则

Jev 生态集成严格遵循系统的只读安全铁律：
- **只读市场与执行**：Jev 仅作为事后审查与决策评估引擎，绝不接触券商连接、实时行情交易或资金账户。
- **严格时间序列防偷窥 (Anti-Lookahead)**：所有送审状态必须满足 `available_at <= decision_time`。任何包含未来时间戳的数据源均被立即拦截并标记校验失败。
- **脱敏边界**：出站审查包仅包含经过严格脱敏的结构化字段，绝不传输账户标识符、个人凭证、原始截图或本地私有绝对路径。
- **确定性与可复现性**：每次审查与评测均生成确定性的 SHA-256 签名，支持完整回放与审计。

---

## 2. Jev 四轨标准化审查包 (Four Evaluation Tracks)

在 `src/smartmoney_cub_harness/jev/` 中，系统将复杂的金融逻辑分解为四个确定性审查轨道：

1. **交易复盘轨 (`trading-review`)**
   - **核心关注**：执行纪律、盈亏比合规性、滑点影响、时间止损与失效条件逻辑闭环。
   - **关键问题**：审查计划与实际执行的偏离度，验证是否遵守既定的交易规则系统。

2. **财报财务轨 (`financial-filings`)**
   - **核心关注**：定期报告、营收质量、现金流偏离、资产负债结构异常及附注重大变动。
   - **关键问题**：非经常性损益占比、应收账款与存货周转匹配度、审计意见类型及受限资产比例。

3. **行业产业事件轨 (`industry-events`)**
   - **核心关注**：供需格局突变、技术替代、政策规制、产业链上下游传导及重大产能投产。
   - **关键问题**：事件真实影响范围、受益/受损环节识别、预期差兑现节奏及传导时滞。

4. **宏观政策轨 (`macro-policy`)**
   - **核心关注**：货币政策、财政刺激、流动性拐点、利率汇率联动及系统性监管周期。
   - **关键问题**：政策口径与市场共识预期的偏离度、信贷脉冲持续性及系统性风险溢价变化。

---

## 3. 后端驱动与协议契约 (`JevBackend`)

系统通过 `JevBackend` 协议抽象实现了多后端无缝热插拔：
```python
@runtime_checkable
class JevBackend(Protocol):
    backend_id: str
    provider_id: str
    model_requested: str

    def health(self) -> dict[str, Any]: ...

    def evaluate(
        self,
        state: Mapping[str, Any] | Any,
        questions: tuple[JevQuestion, ...],
        *,
        decision_time: str,
    ) -> JevReviewDecision: ...
```

- **`TypeSafeDirectJevBackend`**：原生直连驱动，用于本地或受信任私有 Jev 服务端，严格实施 schema 校验与格式兜底。
- **`OpenRouterJevBackend`**：面向云端 OpenRouter 路由生态，自动映射模型参数并支持多模型并行对比。
- **Fail-Closed 故障安全**：在无网络、凭证缺失或响应不符合 schema 时，引擎自动降级为不作为或安全退出，绝不捏造评审结果。

---

## 4. 金融 Jev 基准评测 (`finance-jev-v1`)

为了客观衡量 AI 智能体在金融审查中的实际表现，项目内置了 `finance-jev-v1` 基准评测套件：

- **基准规格**：4 个专业赛轨，每个赛轨 60 个确定性案例（30 个开发集 + 30 个保留测试集），全套共计 240 个冻结案例。
- **纯离线合成测试集**：所有测试案例位于 `benchmarks/finance-jev-v1/`，均采用纯离线合成数据，保证不依赖网络、无真实个人信息。
- **评估指标体系**：
  - `schema_valid_rate`：结构合规率
  - `accuracy` & `macro_f1`：分类准确率与宏观 F1
  - `fpr` (假阳性率) & `recall` (召回率)
  - `brier` & `ece` (校准误差)
  - `coverage` & `abstention_rate` (弃权/防胡言乱语率)
  - accuracy 使用按四个 track 分层的 case-level bootstrap percentile 95% CI（seed `20260927`, 10,000 replicates）；旧 v1 产物的 Wilson 区间仅作为 legacy 方法保留。
- **评测执行与图像生成**：
  ```bash
  # 运行完整离线基准评测 (默认评测全量 4 赛道 240 例，产物保存至 artifacts/benchmark/)
  smcub benchmark run --out-dir artifacts/benchmark
  # 渲染标准评测卡片与图表 (纯 Pillow 栅格与矢量 SVG，指定 run 目录)
  smcub benchmark render artifacts/benchmark/<run_id>
  ```

---

## 5. Agent 集成与 DSH 插件双向桥接

- **Agent 集成中心**：支持本地六大主流开发者 Agent（Codex, Claude Code, DeepSeek Harness, OpenCode, Gemini CLI, Pi）的非侵入式配置探测与 Apply/Disable/Restore。
- **DeepSeek Harness (DSH) 插件**：
  - 位于 `npm/dsh-plugin/`，基于 `smartmoney_cub_dsh_stdio.v1` 协议与 `smartmoney-review` 限制性 profile。
  - 仅开放审查生命周期能力 (`review_envelope`, `review_events`, `review_cancel`, `review_resume`, `review_fork`, `review_close`, `heartbeat`, `teardown`)。
  - 彻底封禁 `shell`、`filesystem`、`network`、`broker`、`trade` 等一切执行与网络权限。

---

## 6. 生态项目投稿指南 (Ecosystem Submission)

如需将基于 SmartMoney-Cub 或 Jev 扩展的应用提交至官方生态索引（如 `awesome-jev`），请遵循以下流程：

1. **环境与契约检查**：
   - 运行 `smcub doctor`，确保通过全部诊断项且安全声明存在。
   - 运行基准套件 `smcub benchmark run`，生成真实有效的 `run.json`。严禁虚报或夸大评测分值。
2. **准备 PR 申请材料**：
   - 参考 `docs/submissions/awesome-jev.md` 标准模板编写介绍。
   - 准备 1200x630 的标准基准 Hero 图或 Leaderboard 图（引用自 tracked `assets/benchmark/`）。
3. **提交规范**：
   - 提交 Issue 或 Pull Request 至 `awesome-jev` 仓库，分类归属至 **Trading & Financial Review Systems**。
   - 在 PR 说明中附上本地测试用例复现命令与只读安全声明。


## 7. 2026-09-27 生态维护记录

- **已合并收录**：[`leoncuhk/awesome-quant-ai#63`](https://github.com/leoncuhk/awesome-quant-ai/pull/63)，于 2026-09-27 合并，merge SHA `ac89cce6148322db6cbca6587aad00faabce6a4a`。
- **上游最终条目**：上游 README 将 SmartMoney-Cub 描述为 synthetic、early-stage 项目，并保留 canonical repository 链接；维护者合并时删除了 hosted relay 链接。
- **评测反馈**：维护者指出公开规模应表述为 240 cases / 1,020 evaluated items，accuracy 区间应按 case-level bootstrap 计算，而不能把同一 case 内的问题当作独立样本。
- **本地落地（2026-09-29 待人工审查）**：v2 benchmark 支持逐 case/question 记录与按 track 分层 bootstrap；[assets/benchmark/run.json](../assets/benchmark/run.json) 的 run hash 为 `7a40b49e57d594da8b45e835417e6f7880d7fa48583349da4559ff1b15f8be45`。基线 83.33%，95% CI [81.57%, 85.10%]；TypeSafe 78.43%，95% CI [76.08%, 80.69%]。
- **TypeSafe 状态**：从原 62-case checkpoint 续跑到 240/240 cases、1,020 items，原 62 条记录保持不变；`jev-latest` 全程解析为 `jev-1.13.0`。记录 218,438 输入、43,836 输出 token，成功响应 usage 计价为 $0.009175，预算上限 $4.00。历史中断请求的账单不能由成功响应反推；不将此数值称为服务商最终账单。
- **严格验证**：`./scripts/dev-env.sh benchmark verify assets/benchmark --require-typesafe-public`。现在开发入口会保留此标志，拷贝到 tracked assets 的脚本也在写入前执行严格门禁。
- **远端差异**：以上为本地待审结果，尚未推送。2026-09-29 检查时远端 main 仍提供 2026-09-20 v1 产物；不能用远端旧链接证明本地 v2 数据已经发布。
- **意见清单**：[2026-09-29 远端意见与本地审查记录](maintenance-review-2026-09-29.md) 逐项记录 Quant AI、Hermes、Awesome-Evals 及其他已发现投稿的意见、SHA、检查结果和后续事项。

`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`
