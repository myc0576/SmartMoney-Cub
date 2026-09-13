# CLAUDE.md

This file mirrors `AGENTS.md` for agent compatibility. The canonical contract is `docs/harness-contract.md`.

## Project Shape

`smartmoney-cub-harness` is a trading journal and review package. The core stays a
small, offline Python package; hosted tenant mode is opt-in:

- `src/smartmoney_cub_harness/manifest.py` validates provenance and anti-future-leakage rules.
- `src/smartmoney_cub_harness/run_capture.py` captures stdout, stderr, metadata, manifests, and decisions from offline commands.
- `src/smartmoney_cub_harness/outcome.py` builds D1/D3 toy outcomes from JSON fixtures.
- `src/smartmoney_cub_harness/evaluator.py` scores decisions against outcomes and risk contracts.
- `src/smartmoney_cub_harness/registry.py` keeps challenger/champion rule state.
- `src/smartmoney_cub_harness/safety.py` redacts sensitive strings and local paths.

## Non-Negotiables

- No trading execution, no order placement or cancellation, no account mutation, no broker automation.
- No real account data committed. Real trades live in the git-ignored runtime store, never in the repository.
- No private local paths.
- No live data source as a default dependency.
- No financial advice language.
- Repository examples, fixtures, and tests use toy offline data only.

## Commands

```bash
pip install -e ".[dev]"
smcub doctor
pytest -q
```

## Mandatory Agent Loops

Any AI agent operating in this repository MUST strictly follow these two skills (configured in `.codex/skills/`):

1. **`goal-loop`**:
   - Freeze Goal, Non-Goals, and Definition of Done (DoD) checklist before writing code.
   - Disallow goal drift, scope reduction, or self-serving completion claims.

2. **`verification-loop`**:
   - Mandatory gate: Run `./scripts/verify.sh` (or `python -m smartmoney_cub_harness.cli doctor` and `python -m pytest tests/ -q`).
   - No completion claims without fresh, passing execution logs.
