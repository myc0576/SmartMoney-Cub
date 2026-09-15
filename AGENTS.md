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
pytest -q
python -m smartmoney_cub_harness.cli doctor
```

## Mandatory Agent Loops

Any AI agent operating in this repository MUST strictly follow these two skills (configured in `.codex/skills/`):

1. **`goal-loop` (端到端目标闭环)**:
   - Before modifying code, freeze Goal, Non-Goals, and a clear Definition of Done (DoD) checklist.
   - Do NOT reduce, drop, or self-relax DoD items during implementation.
   - Task completion requires external, objective verification evidence for each DoD item.

2. **`verification-loop` (确定性门禁循环)**:
   - Iron Law: **NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE**.
   - Before claiming task complete or creating a PR, you MUST execute:
     `./scripts/verify.sh` (or `python -m smartmoney_cub_harness.cli doctor` + `python -m pytest tests/ -q`).
   - All tests must pass, doctor safety output must confirm `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.
   - Never tamper with tests or assertions to fake passes.
