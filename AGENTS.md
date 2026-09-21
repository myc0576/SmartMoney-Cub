# AGENTS.md

This repository is the public core of `smartmoney-cub-harness`, a trading journal
and review product. The core installs and runs offline; hosted mode is opt-in.

## Contract

Read `docs/harness-contract.md` first. The project is read-only with respect to
markets and execution, and writable with respect to the user's own local and
tenant-scoped journal. It is not a stock picker, broker connector, or financial
advice system.

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

Additionally, the repository vendors the official TypeSafe agent skill ([typesafe-ai/skills](https://github.com/typesafe-ai/skills)) at `.codex/skills/typesafe-ai/`, hash-pinned to upstream commit `65a39f393687675ce170e6094757de20370365b9`. Its output is review evidence only.

@RTK.md
