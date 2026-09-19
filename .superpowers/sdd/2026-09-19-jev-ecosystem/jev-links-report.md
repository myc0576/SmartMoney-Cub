# Jev Links and README Story Verification Report

## 1. Summary of Changes

This task closes the two content gaps identified in the Jev integration review:
- **Gap 1 (Official Links)**: Added verified links to Jev's official surfaces ([TypeSafe](https://typesafe.ai/) and [OpenRouter Jev Model](https://openrouter.ai/typesafe/jev)) across `docs/jev-ecosystem.md`, `docs/submissions/awesome-jev.md`, `README.md`, and `README.zh-CN.md`. Explicitly noted that links provide reference and configuration access rather than an official endorsement.
- **Gap 2 (Jev Story in READMEs)**: Added dedicated, bilingual sections in the first screen of `README.md` and `README.zh-CN.md` explaining the Jev reasoning layer, pluggable backends (TypeSafe direct and OpenRouter), typed judgment boundaries (`noul` / `choice` / `score`), strict deterministic temporal enforcement (`available_at <= decision_time`), the `finance-jev-v1` 240-case 4-track frozen offline benchmark, reference baseline accuracy (84.26%, 95% CI [81.97%, 86.31%], macro F1 0.7885), and truthful reporting of Jev systems as `not_run` / `live_evaluation_not_wired` without live evaluation in the published reference run.

## 2. Verified URLs & Status Codes

All added URLs were tested with `curl -sI` and verified to resolve with HTTP 200:
- `https://typesafe.ai/` -> HTTP/2 200
- `https://openrouter.ai/typesafe/jev` -> HTTP/2 200

## 3. Metrics Cross-Check against assets/benchmark/run.json

All figures match `assets/benchmark/run.json` exactly:
- Benchmark ID: `finance-jev-v1`
- Sample count: `240`
- Tracks: `trading-review`, `financial-filings`, `industry-events`, `macro-policy`
- Deterministic baseline accuracy: `0.8426` (84.26%)
- 95% Wilson Confidence Interval: `[0.8197, 0.8631]` ([81.97%, 86.31%])
- Macro F1: `0.7885`
- Jev systems status in published run: `not_run` (metrics `None`)
- Safety declaration: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`

## 4. Verification Gates

- `PYTHONPATH=src python3 -m pytest tests/ -q`: 945 passed, 6 skipped
- `./scripts/verify.sh`: ALL GATES PASSED (Doctor audit confirmed `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`, 945 passed, leak/safety sanity passed)
- `python3 tests/test_readme_visuals.py`: All README/asset regression checks passed
- `python3 -m pytest tests/test_readme_commands.py -v`: 9 passed
