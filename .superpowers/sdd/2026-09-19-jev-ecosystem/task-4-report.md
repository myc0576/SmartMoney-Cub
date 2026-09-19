# Task 4: Frontend Jev / Benchmark / Agent Views Implementation Report

## Summary

Successfully implemented Task 4 according to plan sections 5 & 6 and task-4-brief.md:
1. Backend endpoints in `src/smartmoney_cub_harness/workbench/server.py`:
   - `GET /api/jev/status` -> Returns engine status, provider_id, model_requested, model_resolved, available, safety, and backends diagnostic payload.
   - `GET /api/jev/tracks` -> Returns track definitions with real question counts and case counts.
   - `GET /api/agents` -> Lazy-imports agent integrations, scanning available agents and their status.
   - `POST /api/agents/apply` -> Injects/enables review configuration fragment (supports `dry_run`).
   - `POST /api/agents/disable` -> Disables agent review configuration without destroying the section.
   - `POST /api/agents/restore` -> Restores agent original configuration.
   - `GET /api/benchmark/latest` -> Surfaces the newest benchmark run from `artifacts/benchmark/<run_id>/run.json`.
   - `GET /api/benchmark/images/<run_id>/<filename>` -> Safely serves rendered PNG/SVG score images with appropriate MIME types.
2. Full test coverage in `tests/test_workbench_jev_api.py` validating all endpoints, safety declarations, error handling, and image serving.
3. Frontend views and integration:
   - `gui/src/views/JevView.tsx`: Engine status, honest provider/model reporting, 4 track question packs, and full Agent integration management center.
   - `gui/src/views/BenchmarkView.tsx`: Latest benchmark run metadata, leaderboard table with honest `not_run` display (reasons visible, no fake zeros), track-level metrics, and inline score images viewer.
   - `gui/src/types.ts` and `gui/src/api.ts`: Added typed interfaces and client methods for all endpoints.
   - `gui/src/App.tsx`: Extended `TabKey`, added navigation entries under '系统' (Jev 引擎) and '研究' (基准评测), and hooked up conditional rendering.
   - `scripts/visual-check.cjs`: Registered new views for automated visual regression checking.

## Verification Evidence

1. **Typecheck & Build**:
   - `npm run typecheck`: Passed (`tsc --noEmit` exits 0).
   - `npm run build`: Passed (`vite build` emitted production assets into `src/smartmoney_cub_harness/workbench/web/`).
2. **Backend Unit & Integration Tests**:
   - `tests/test_workbench_jev_api.py`: 4 passed (all endpoints, safety declaration `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` verified).
   - Entire workbench/jev/benchmark/agent test suite: 101 passed.
3. **Visual Regression & Layout Checks**:
   - Executed `./scripts/visual-check.sh`.
   - `Jev 引擎` (jev): `dom=17523`, `panels=11`, `overflow=false`, `errs=0`.
   - `基准评测` (benchmark): `dom=16275`, `panels=10`, `overflow=false`, `errs=0`.
   - Both views rendered with zero horizontal overflow and zero console errors.
   - Screenshots verified in `artifacts/visual/jev.png` and `artifacts/visual/benchmark.png`.

## Constraints & Rules Checked

- No new npm dependencies added (React 19 + Vite + TypeScript only).
- The UI never claims Jev is active when the running engine is unavailable; it displays real provider_id, model_requested, and `missing_credential` reason.
- Empty states are honest; `not_run` systems in the benchmark leaderboard display status, reasons, and `—` rather than fake zero scores.
- Safety declaration `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` is present across all responses and view banners.
- No files modified in `src/smartmoney_cub_harness/jev/`, `src/smartmoney_cub_harness/benchmark/`, `src/smartmoney_cub_harness/agent/integrations.py`, or READMEs.
