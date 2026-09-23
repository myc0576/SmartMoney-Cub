# AGENTS.md

This repository is the public core of `smartmoney-cub-harness`, a trading journal
and review product. The core installs and runs offline; hosted mode is opt-in.

## Contract

Read `docs/harness-contract.md` first. The project is read-only with respect to
markets and execution, and writable with respect to the user's own local and
tenant-scoped journal. Optional user-authorized account ingestion is read-only.
It is not a stock picker, execution system, or financial advice system.

## Safety Rules

1. Keep the safety declaration on every manifest, decision, outcome, and doctor output:
   `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`
2. Do not add live trading execution, order placement, order cancellation, account modification, or broker automation. The execution ban is absolute.
3. Do not commit real personal trading records, private watchlists, local absolute paths, credentials, cookies, or account identifiers. A user's real trades belong in the runtime store, which is git-ignored and never published.
4. Repository examples, fixtures, and tests must use toy offline data only.
5. Non-silent observations must carry invalidation, time stop, give-up conditions, data source, available time, and data quality, whether the entry is journal data or fetched market data.
6. Any data source with `available_at > decision_time` must fail validation, including online market data.
7. Rule promotion must go through challenger -> champion, with explicit confirmation before champion mutation.

## Build and Test

```bash
pip install -e ".[dev]"
./scripts/dev-env.sh test
./scripts/dev-env.sh verify
```

## Mandatory Agent Loops

Any AI agent operating in this repository MUST strictly follow the skills configured in `.codex/skills/`:

1. **`goal-loop` (端到端目标闭环)**:
   - Before modifying code, freeze Goal, Non-Goals, and a clear Definition of Done (DoD) checklist.
   - Do NOT reduce, drop, or self-relax DoD items during implementation.
   - Task completion requires external, objective verification evidence for each DoD item.

2. **`verification-loop` (确定性门禁循环)**:
   - Iron Law: **NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE**.
   - Before claiming task complete or creating a PR, you MUST execute:
     `./scripts/verify.sh` (or `./scripts/dev-env.sh verify`).
   - All tests must pass, doctor safety output must confirm `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.
   - Never tamper with tests or assertions to fake passes.

3. **`workflow-cost-optimizer` (研发成本与上下文优化闭环)**:
   - **Scale Triage (S/M/L)**: Small tasks (≤ 3 files) execute in single-agent mode without spawning sub-agents; M/L tasks use phased wave execution with role whitelists.
   - **Code Graph First**: Never blind-grep the whole repo. Query `./scripts/dev-env.sh graph query '<symbol>'` to locate exact files and AST call sites first.
   - **Deterministic CLI**: Use `./scripts/dev-env.sh [test|build|verify|graph|rtk]` for predictable execution without hallucinating parameter trial-and-error.
   - **Progressive Disclosure**: Consult `docs/INDEX.md` before reading documentation; only load top-matched design specs into context.
   - **RTK Compression**: Prefix shell commands with `rtk` to strip 60%-90% terminal noise and save tokens.
   - **State Externalization**: Maintain persistent discoveries and task state in `ledger.md` rather than repeating huge progress boards across conversation turns.

## Open-Source Upstream Contribution Workflow

For any task that forks a repository, publishes this project, opens or updates an
upstream pull request, or changes an existing ecosystem listing, read
`docs/open-source-maintenance.md` before changing Git state or remote state.

- Add the applicable Fork, PR, post-merge sync, and ongoing-maintenance checks from
  that document to the task's Definition of Done.
- Verify the Fork's GitHub `parent`, the PR's base/head repositories and branches,
  and the final content on the upstream default branch with fresh external evidence.
- A merged PR is not the end of the loop: inspect the maintainer's final wording,
  synchronize the personal Fork, and record the PR URL, merge date, upstream
  location, and ahead/behind status.
- Before releases or material README/API/integration changes, check whether existing
  upstream listings remain accurate; update them only when the public description
  is stale, broken, or materially misleading.
- Remote mutations such as pushing, opening a PR, or deleting a branch must stay
  within the user's requested scope. Never publish credentials, personal trading
  data, private watchlists, account identifiers, local absolute paths, or non-toy
  fixtures.
- Every public description of execution authority must preserve
  `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` and must not imply stock picking,
  financial advice, broker automation, order placement, or cancellation.

## Frontend & Review Agent Development Workflow

When modifying or refactoring frontend views (`gui/src/`), styling (`tokens.css`, `styles.css`), or the right-side review assistant (`AssistantPanel.tsx`), agents MUST follow the 4 dedicated skills:

4. **`frontend-design` (视觉审美闭环)**:
   - 必须遵循 TradingView 级语义化沉浸设计，杜绝劣质 AI 模板感与未收敛的内联样式。
   - 严格使用 `gui/src/tokens.css` 语义设计令牌；红涨绿跌/绿涨红跌使用 `--pos` / `--neg` 动态映射解耦。
   - 核心数值、盈亏与价格列强制使用等宽对齐字体 (`tnum` / Geist Mono)。
   - 杜绝暗色下控件反白、无描边融底等视觉降级问题。

5. **`ui-ux-pro-max` (设计规范与交互契约)**:
   - **四态完备**：所有异步数据视图必须严密实现 Loading、Empty、Error、Populated 四态。
   - **自适应挤压保护**：在右侧复盘助手（AssistantPanel 400px）常驻展开时，主体网格自适应收敛（如 2 列），严禁横向溢出（Horizontal Scroll）。
   - **防呆与安全防御**：破坏性操作必须二次确认；封闭信任边界（403）下输入框禁用并清晰诊断，杜绝谎称「暂无数据」。

6. **`ai-elements-json-render` (右侧复盘 Agent 重构)**:
   - 专用指导 `AssistantPanel.tsx` 架构重构，全面采用 `UIMessage.parts` 分片协议。
   - 分离常规文本、深度思考链（折叠手风琴）、工具调用卡片（生命周期状态机）与结构化业务产物（挑战者规则、交易证据卡）。
   - 流式增量更新优化防卡顿，会话事件本地持久化（本地 SQLite/SSE 断点续传与重试）。

7. **`agent-browser-verify` (终局视觉 QA 门禁)**:
   - 前端代码提交或声称完成前，必须执行客观无头浏览器自动化巡检：
     `./scripts/visual-check.sh`（或 `./scripts/dev-env.sh test e2e`）。
   - 自动化核查：15 个核心视图无报错、无横向溢出、控制台 0 错误、复盘助手深度交互、403 信任边界防御全通过。
   - 必须产出并验证 `artifacts/visual/report.json` 中 `summary.failed.length === 0`。

@RTK.md
