# Trader Product v1 — Implementation Plan

Spec authority: this plan argues from `docs/trader-product-spec.md` (Global Constraints below).
Base commit: 9453e30 (branch `codex/trader-product-v1`).

## Global Constraints

Every task must satisfy all of these. They are not restated per task.

1. **Execution ban is absolute.** No order placement, cancellation, broker account
   mutation, or execution automation anywhere in the codebase. `doctor()` keeps
   `execution_integrations == "disabled"` and `broker_api_required is False`.
2. **The safety declaration string `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` is kept
   verbatim** on every manifest, decision, outcome, doctor output, plugin envelope,
   and generated report.
3. **`pyproject.toml` core `dependencies = []` stays empty.** Anything that needs a
   third-party package goes in `[project.optional-dependencies]` and must be imported
   lazily inside the code path that needs it. `tests/test_packaged_assets.py`
   enforces this.
4. **In-repo fixtures are toy data only.** No real trades, real accounts, private
   watchlists, local absolute paths, credentials, cookies, or account identifiers
   are committed. Runtime user data lives in the local/tenant store, never in git.
5. **Anti-future-leakage stays enforced.** Any data source with
   `available_at > decision_time` fails validation, including online market data.
6. **The existing 443 tests must still pass.** Where a test asserts a claim this plan
   changes, the test is *amended with a stated reason*, never deleted or weakened
   silently.
7. **Python >= 3.10.** No `match` on complex patterns, no 3.11+ only stdlib APIs.
8. **`./scripts/verify.sh` is the gate.** It must pass at the end of every task.

---

## Task 1: Rewrite the contract documents and doctor fields

**Deliverable:** The published contract says what the product now is, and `doctor`
reports the new fields, without weakening the execution ban.

**Files (write set):**
- `docs/harness-contract.md` — rewrite the framing paragraph and the "Seven
  Principles" that speak of read-only/no-real-data. New framing: *read-only with
  respect to markets and execution; writable with respect to the user's own local
  and tenant-scoped journal.* Keep all seven principle *names* and reword 3 and 7,
  which are about provenance and portable memory, not about read-only-ness.
- `AGENTS.md` and `CLAUDE.md` — safety rules 1-7 rewritten per the new framing.
  Rule "Do not add live trading execution..." stays. Rule "Do not add real personal
  trading records..." becomes "Do not commit real personal trading records..." with
  the runtime-store exception stated.
- `README.md` and `README.zh-CN.md` — the safety section and the "what it is not"
  section. Keep the `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` block present in both.
- `docs/safety.md`, `docs/privacy.md`, `docs/philosophy.md` — data policy and
  network policy paragraphs.
- `src/smartmoney_cub_harness/cli.py` — `doctor()` gains two fields:
  `market_data_mode` (default `"offline"`) and `tenant_mode` (default
  `"local_single_user"`). `network_required` keeps its key and changes meaning to
  "the core is usable with no network" and stays `False` by default. Add
  `external_api_required` stays `False` (the built-in market sources are opt-in at
  call time, not required to import or run the core).
- `tests/test_doctor.py` — add assertions for the two new fields; keep every
  existing assertion and add a comment above the file explaining the semantic.

**DoD:**
- [ ] `docs/harness-contract.md` contains the string `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` (verify: `grep`)
- [ ] `smcub doctor` stdout contains `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` (verify: run it)
- [ ] `smcub doctor` JSON has `market_data_mode` and `tenant_mode` keys (verify: run it, assert)
- [ ] `doctor()["execution_integrations"] == "disabled"` and `doctor()["broker_api_required"] is False` still hold (verify: `pytest tests/test_doctor.py -q`)
- [ ] `README.md` and `README.zh-CN.md` still contain the declaration (verify: `pytest tests/test_readme_commands.py -q`)
- [ ] `pytest -q` fully green (verify: command output)

---

## Task 2: Market data provider layer

**Deliverable:** A provider interface plus four built-in no-key sources, each behind a
lazy import, returning normalized bars with provenance metadata.

**Files (write set):**
- `src/smartmoney_cub_harness/trader/__init__.py` — package marker, version constant.
- `src/smartmoney_cub_harness/trader/market/__init__.py` — exports `Bar`,
  `ProviderResult`, `PROVIDERS`, `fetch_bars`, `list_providers`.
- `src/smartmoney_cub_harness/trader/market/base.py` — `Bar` dataclass
  (`symbol, interval, open_time, open, high, low, close, volume`), `ProviderResult`
  (`bars, provider_id, symbol, interval, fetched_at, source_quality, warnings`),
  the `MarketDataProvider` protocol, and `MarketDataError`.
- `src/smartmoney_cub_harness/trader/market/eastmoney.py` — A-share daily and
  minute bars via `push2his.eastmoney.com/api/qt/stock/kline/get`. `secid`
  mapping: Shanghai `1.`, Shenzhen `0.`. Klt: 101 daily, 102 weekly, 103 monthly,
  1/5/15/30/60 minutes.
- `src/smartmoney_cub_harness/trader/market/tencent.py` — A-share/HK/US via
  `web.ifzq.gtimg.cn/appstock/app/fqkline/get`, prefix `sh`/`sz`/`hk`/`us`.
- `src/smartmoney_cub_harness/trader/market/stooq.py` — daily CSV for US and EU
  symbols via `stooq.com/q/d/l/`.
- `src/smartmoney_cub_harness/trader/market/binance.py` — spot klines via
  `api.binance.com/api/v3/klines`.
- `tests/test_trader_market.py` — contract tests using recorded response fixtures
  (no live network), plus one opt-in live smoke test gated on
  `SMARTMONEY_LIVE_MARKET=1`.

**Interfaces this task produces (later tasks consume):**
- `fetch_bars(provider_id: str, symbol: str, interval: str, *, start: str | None = None,
  end: str | None = None, limit: int = 500) -> ProviderResult`
- `list_providers() -> list[dict]` with keys `provider_id, label, markets, requires_key,
  source_quality, description`.
- `MarketDataProvider.protocol` method: `bars(...) -> ProviderResult`.

**Notes:** Use `urllib.request` only. Every provider must set a real
`User-Agent`. `fetched_at` is an ISO-8601 UTC string. `source_quality` is one of
`exchange`, `aggregator`, or `delayed`. Providers raise `MarketDataError` with a
readable message; they never return partial data silently (a truncated page is
reported in `warnings`).

**DoD:**
- [ ] `fetch_bars("eastmoney", "600111", "1d")` returns bars parsed from the fixture with correct OHLC ordering (verify: `pytest tests/test_trader_market.py -q`)
- [ ] Every provider normalizes to the same `Bar` shape (verify: parametrized test over all four provider ids)
- [ ] A malformed/empty upstream payload raises `MarketDataError`, never returns `[]` silently (verify: test)
- [ ] `python -c "from smartmoney_cub_harness.trader.market import list_providers; print(len(list_providers()))"` prints `4` (verify: run it)
- [ ] Importing the package pulls in no third-party module (verify: `python -c "import sys, smartmoney_cub_harness.trader.market as m; assert not any(x in sys.modules for x in ('pandas','numpy','requests'))"`)
- [ ] `pytest -q` fully green

---

## Task 3: Backtest engine with a JSON rule DSL

**Deliverable:** A deterministic event-driven backtester that executes strategies
described in JSON, with no code-execution surface.

**Files (write set):**
- `src/smartmoney_cub_harness/trader/backtest/__init__.py` — exports `run_backtest`,
  `StrategySpec`, `BacktestResult`, `load_strategy`, `validate_strategy`.
- `src/smartmoney_cub_harness/trader/backtest/dsl.py` — the DSL: `StrategySpec`
  dataclass and `validate_strategy(payload: dict) -> StrategySpec` which raises
  `StrategyError` with a path-qualified message on any unknown key.
- `src/smartmoney_cub_harness/trader/backtest/engine.py` — `run_backtest(spec, bars,
  *, initial_cash, fees_bps, slippage_bps) -> BacktestResult`. Fills at next-bar open
  by default (`fill: "next_open"`), or same-bar close when `fill: "same_close"`.
- `src/smartmoney_cub_harness/trader/backtest/metrics.py` — reuses
  `smartmoney_cub_harness.analytics` for win rate, profit factor, expectancy, and
  drawdown so the two code paths cannot drift. Adds CAGR and equity-curve output.
- `tests/test_trader_backtest.py` — determinism, hand-computed PnL, DSL validation,
  and a golden-file run.

**DSL shape (frozen by this task):**
```json
{
  "version": 1,
  "name": "sma-cross-toy",
  "universe": {"symbol": "600111", "interval": "1d"},
  "indicators": [
    {"id": "fast", "kind": "sma", "source": "close", "period": 5},
    {"id": "slow", "kind": "sma", "source": "close", "period": 20}
  ],
  "entry": {"all": [{"crosses_above": ["fast", "slow"]}]},
  "exit": {"all": [{"crosses_below": ["fast", "slow"]}]},
  "stop": {"kind": "percent", "value": 2.0},
  "target": {"kind": "r_multiple", "value": 2.0},
  "sizing": {"kind": "fixed_fraction", "value": 0.1},
  "filters": {"session": null, "min_bars": 25}
}
```
Allowed `indicators[].kind`: `sma`, `ema`, `rsi`, `atr`, `highest`, `lowest`,
`volume_sma`. Allowed comparison operators: `gt`, `lt`, `gte`, `lte`,
`crosses_above`, `crosses_below`, `is_true`. Allowed `sizing.kind`:
`fixed_fraction`, `fixed_quantity`, `risk_percent`. Allowed `stop.kind`:
`percent`, `atr_multiple`, `none`. Allowed `target.kind`: `r_multiple`,
`percent`, `none`.

**DoD:**
- [ ] Same spec + same bars produce byte-identical results across two runs (verify: test asserts `run_backtest(...) == run_backtest(...)`)
- [ ] A two-trade hand-computed scenario yields exactly the expected net PnL to the cent (verify: test with literal expected values, arithmetic shown in a comment)
- [ ] `validate_strategy` rejects an unknown key with a message naming the key path (verify: test asserts the key appears in `str(exc)`)
- [ ] Loading a strategy never imports or executes user Python (verify: test asserts no `eval`/`exec`/`compile` in the module source, and `compile` is absent from `backtest/engine.py`)
- [ ] Backtest metrics for a scenario equal `analytics.summarize` on the same synthetic fills (verify: cross-check test)
- [ ] `pytest -q` fully green

---

## Task 4: Storage layer with tenant isolation

**Deliverable:** One storage interface with a SQLite implementation (default, local,
no dependencies) and a Postgres implementation (hosted, optional extra), both
enforcing per-tenant row isolation.

**Files (write set):**
- `src/smartmoney_cub_harness/trader/storage/__init__.py` — exports
  `open_store`, `StoreError`, `TenantStore`.
- `src/smartmoney_cub_harness/trader/storage/base.py` — the `TenantStore` protocol
  and shared dataclasses. Methods: `migrate()`, `create_user`, `get_user`,
  `list_trades(user_id)`, `insert_trades(user_id, rows)`, `list_accounts(user_id)`,
  `upsert_account`, `save_backtest_run`, `list_backtest_runs`, `save_bars`,
  `load_bars`, `audit`.
- `src/smartmoney_cub_harness/trader/storage/sqlite_store.py` — default
  implementation on `sqlite3`, WAL mode, one database per tenant directory.
- `src/smartmoney_cub_harness/trader/storage/postgres_store.py` — hosted
  implementation. Imports `psycopg` lazily inside `connect()` and raises
  `StoreError` with an install hint (`pip install "smartmoney-cub-harness[hosted]"`)
  when absent. Every table carries `user_id`; every query filters on it.
- `src/smartmoney_cub_harness/trader/storage/schema.sql` — the shared DDL, written
  in the SQL subset both engines accept.
- `tests/test_trader_storage.py` — SQLite behavior tests, isolation tests,
  and Postgres tests skipped unless `SMARTMONEY_TEST_DATABASE_URL` is set.
- `pyproject.toml` — add `hosted = ["psycopg[binary]>=3.2"]` under
  `[project.optional-dependencies]`. Do not touch `dependencies`.

**DoD:**
- [ ] Two users in one store cannot read each other's trades (verify: test creating user A and B, asserting B sees zero of A's rows)
- [ ] Every tenant-scoped query in `postgres_store.py` contains a `user_id` predicate (verify: test that greps the module source for each public method's SQL)
- [ ] `import smartmoney_cub_harness.trader.storage` succeeds with `psycopg` uninstalled (verify: test monkeypatching the import to fail, asserting `StoreError` with the install hint)
- [ ] `pyproject.toml` core `dependencies` is still exactly `[]` (verify: `pytest tests/test_packaged_assets.py -q`)
- [ ] `migrate()` is idempotent (verify: test calling it twice)
- [ ] `pytest -q` fully green

---

## Task 5: Tenant authentication against the alphatech platform

**Deliverable:** Request authentication that accepts an alphatech identity and maps
it to a tenant, with a local no-auth mode for offline use and CI.

**Files (write set):**
- `src/smartmoney_cub_harness/trader/auth/__init__.py` — exports
  `AuthContext`, `resolve_identity`, `AuthError`.
- `src/smartmoney_cub_harness/trader/auth/identity.py` — `AuthContext` dataclass
  (`user_id, tenant_id, display_name, mode, platform_user_id`) and
  `resolve_identity(headers: Mapping[str,str], *, mode: str) -> AuthContext`.
- `src/smartmoney_cub_harness/trader/auth/alphatech.py` — the platform adapter.
  Reads a shared-secret-signed identity header (`X-AlphaTech-User`,
  `X-AlphaTech-Signature`) and verifies an HMAC-SHA256 over
  `user_id` + timestamp using `ALPHATECH_SSO_SECRET`. Rejects a timestamp older
  than 300 seconds. Every assumption about the platform protocol is collected in
  one module-level docstring table so a wrong guess is a one-file change.
- `tests/test_trader_auth.py` — HMAC accept/reject, replay window, local mode,
  and missing-secret behavior.

**Interfaces this task produces (later tasks consume):**
- `resolve_identity(headers, mode="hosted"|"local") -> AuthContext`
- Header names and the HMAC construction above.

**DoD:**
- [ ] A correctly signed identity resolves to the matching `tenant_id` (verify: test)
- [ ] A tampered signature raises `AuthError` (verify: test)
- [ ] A correct signature with a timestamp older than 300s raises `AuthError` (verify: test)
- [ ] `mode="local"` returns a fixed single-user context and never reads headers (verify: test)
- [ ] Hosted mode with `ALPHATECH_SSO_SECRET` unset fails closed (verify: test asserts `AuthError`, never an anonymous context)
- [ ] `pytest -q` fully green

---

## Task 6: Trader HTTP API

**Deliverable:** The product's HTTP surface, mounted alongside the existing workbench
server, exposing journal, analytics, market data, backtest, and replay endpoints.

**Files (write set):**
- `src/smartmoney_cub_harness/trader/api/__init__.py` — exports `TraderService`.
- `src/smartmoney_cub_harness/trader/api/service.py` — `TraderService` with one
  method per endpoint, all taking an `AuthContext` first.
- `src/smartmoney_cub_harness/trader/api/routes.py` — the route table and the
  dispatch function the workbench server calls.
- `src/smartmoney_cub_harness/workbench/server.py` — mount the trader routes under
  `/api/trader/*` by delegating to `routes.dispatch`. Keep the existing routes and
  their behavior unchanged.
- `src/smartmoney_cub_harness/cli.py` — add `smcub trader serve` with
  `--host`, `--port`, `--mode {local,hosted}`, `--database-url`, `--no-browser`.
- `tests/test_trader_api.py` — end-to-end over a real bound socket, like the
  existing `test_workbench_service.py`.
- `docs/trader-api.md` — the endpoint reference this task produces.

**Endpoints (frozen by this task):**
```
GET    /api/trader/health
GET    /api/trader/meta
GET    /api/trader/market/providers
GET    /api/trader/market/bars?provider=&symbol=&interval=&start=&end=&limit=
GET    /api/trader/trades?account_id=&symbol=&from=&to=&limit=&offset=
POST   /api/trader/trades/import           (CSV/JSON body)
GET    /api/trader/trades/{round_trip_id}
GET    /api/trader/accounts
POST   /api/trader/accounts
GET    /api/trader/analytics/summary?from=&to=&account_id=
GET    /api/trader/analytics/breakdown?dimension=&from=&to=
GET    /api/trader/calendar?year=&month=
GET    /api/trader/playbooks
POST   /api/trader/playbooks
POST   /api/trader/backtest/run            (strategy JSON + data ref)
GET    /api/trader/backtest/runs
GET    /api/trader/backtest/runs/{run_id}
POST   /api/trader/replay/sessions
GET    /api/trader/replay/sessions/{session_id}
```

Every response body includes `"safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"`.
Every handler resolves identity via Task 5 and passes `AuthContext` into storage.

**DoD:**
- [ ] Each endpoint returns 200 with a well-formed JSON body for a valid tenant (verify: `pytest tests/test_trader_api.py -q`)
- [ ] Every response body contains the safety declaration (verify: test iterating every route)
- [ ] A request with no valid identity is refused with 401 (verify: test)
- [ ] Tenant A's `/trades` response never contains tenant B's `round_trip_id` (verify: test importing distinct trades for two tenants)
- [ ] Existing workbench routes still behave identically (verify: `pytest tests/test_workbench_service.py -q`)
- [ ] `docs/trader-api.md` lists every route above (verify: test asserting each path string appears in the doc)
- [ ] `pytest -q` fully green

---

## Task 7: Frontend expansion

**Deliverable:** `gui/` grows from 8 views into the product's full navigation, styled
with TradingView semantic tokens and Tradezalla's button system.

**Files (write set):**
- `gui/src/tokens.css` — the design tokens. TradingView semantic naming
  (`--color-*`) and values: accent `#2962FF`, text `#0F0F0F`, borders, surfaces,
  plus positive/negative from the Tradezalla palette (`--pos: #38d39f`,
  `--neg: #f04f68`). Light and dark blocks.
- `gui/src/views/TradeLogView.tsx` — the sortable, filterable trade table.
- `gui/src/views/ReportsView.tsx` — the report tabs (performance, risk, symbols,
  day-time).
- `gui/src/views/PlaybookView.tsx` — playbook CRUD and per-playbook P&L.
- `gui/src/views/BacktestView.tsx` — strategy editor (JSON), run, results, equity curve.
- `gui/src/views/ReplayView.tsx` — candle replay with trade markers.
- `gui/src/views/PropFirmView.tsx` — accounts and multi-stage evaluation rules.
- `gui/src/components/CandleChart.tsx` — the chart component. Hand-rolled canvas or
  SVG; no new npm dependency, matching the repo's zero-dependency stance.
- `gui/src/api.ts` — add the trader endpoints from Task 6.
- `gui/src/types.ts` — the trader response types.
- `gui/src/App.tsx` — the expanded navigation.
- `gui/src/styles.css` — extend, do not rewrite: keep the existing layout and classes.
- `gui/package.json` — keep dependencies to React only; add a `typecheck` script if
  missing.

**DoD:**
- [ ] `npm run typecheck` in `gui/` exits 0 (verify: run it)
- [ ] `npm run build` in `gui/` exits 0 and writes
  `src/smartmoney_cub_harness/workbench/web/index.html` (verify: run it, then check the file exists)
- [ ] Every view listed above is reachable from the navigation (verify: the App tab array contains each, checked by a grep in the test)
- [ ] `gui/package.json` `dependencies` contains only `react` and `react-dom` (verify: `python -c` assertion or node check)
- [ ] `--color-*` token names appear in `tokens.css` and `#2962FF` is the accent (verify: grep)
- [ ] `pytest tests/test_packaged_assets.py -q` still green after the build
- [ ] `pytest -q` fully green

---

## Task 8: Bundle contract oracle

**Deliverable:** The private TradeZella bundle, running offline against the real
Trader API instead of the mock, proving the backend contract is compatible with a
shipping product's shape.

**Files (write set):**
- `work/trader-oracle/adapter.cjs` — a Node script that translates the bundle's
  expected request/response shapes onto `/api/trader/*`.
- `work/trader-oracle/run.cjs` — serves the bundle with the adapter injected,
  drives Playwright across the route list, and writes
  `work/trader-oracle/report.json`.
- `scripts/trader-oracle.sh` — one command that starts the API, runs the oracle,
  and exits non-zero if any route errored.
- `docs/trader-oracle.md` — what the oracle proves and what it deliberately does not.

**Notes:** `work/` is git-ignored, so this task's artifacts stay private. The
committed parts are `scripts/trader-oracle.sh` and the doc. Report `dom` length,
row count, and console errors per route, matching the existing
`work/tradezella-ui/offline-app/routes-verify.json` shape so the numbers are
comparable to the earlier baseline.

**DoD:**
- [ ] `bash scripts/trader-oracle.sh` exits 0 (verify: run it)
- [ ] Its report shows zero console errors on at least the five routes that
  previously rendered cleanly: `/tracking`, `/tracking/trade-log`,
  `/tracking/day-view`, `/reports/performance`, `/backtesting` (verify: inspect `report.json`)
- [ ] No file under `work/` is tracked by git (verify: `git status --porcelain` shows none)
- [ ] Nothing from the bundle is copied into `src/` (verify: `git ls-files src | xargs grep -l "lightweight-charts" || true` returns nothing)

---

## Task 9: Browser and visual verification

**Deliverable:** An automated visual pass over the product's own frontend, plus a
recorded manual pass using computer use.

**Files (write set):**
- `scripts/visual-check.cjs` — serves the built workbench, drives Playwright over
  every view, asserts no console errors, no horizontal overflow at 390px, and
  captures screenshots to `artifacts/visual/`.
- `scripts/visual-check.sh` — wrapper that starts `smcub trader serve` on a free
  port, runs the checks, and tears down.
- `artifacts/visual/README.md` — how to read the output.
- `.gitignore` — ignore `artifacts/visual/*.png` but keep the README.

**DoD:**
- [ ] `bash scripts/visual-check.sh` exits 0 (verify: run it)
- [ ] The run reports zero console errors across every view (verify: script output)
- [ ] Every view produces a non-blank screenshot wider than 300px (verify: script asserts PNG dimensions)
- [ ] A screenshot of each view is visually confirmed to render the expected
  content (verify: computer-use inspection, recorded in the task report)
- [ ] `pytest -q` fully green

---

## Task 10: Deployment artifacts and the product README

**Deliverable:** Everything needed to run the hosted product, plus documentation
that names the v1 scope and the deferred features.

**Files (write set):**
- `deploy/Dockerfile` — Python 3.12 slim, installs `.[hosted]`, runs `smcub trader serve --mode hosted`.
- `deploy/docker-compose.yml` — app plus Postgres 16, with a healthcheck.
- `deploy/nginx.conf` — reverse proxy with TLS placeholders and a `/trader` prefix.
- `deploy/trader.service` — systemd unit.
- `deploy/README.md` — the three deployment routes, step by step.
- `docs/trader-product.md` — the product README: what v1 does, the explicit
  non-goals, and the **deferred feature list** (broker direct-connect, multi-user
  billing, Spaces/mentor mode, notification push, mobile) with a note that these are
  planned for after v1.
- `CHANGELOG.md` — a new entry describing the product addition.

**DoD:**
- [ ] `docker build -f deploy/Dockerfile .` succeeds (verify: run it; if Docker is
  unavailable in this environment, verify by `python -m py_compile` on every
  referenced script plus a documented manual check, and say so in the report)
- [ ] `deploy/docker-compose.yml` is valid YAML (verify: `python -c "import yaml, sys; yaml.safe_load(open('deploy/docker-compose.yml'))"` or a JSON-parse fallback)
- [ ] `docs/trader-product.md` names every deferred feature listed above (verify: test asserting each phrase appears)
- [ ] `README.md` links to `docs/trader-product.md` (verify: grep)
- [ ] `pytest -q` fully green
- [ ] `./scripts/verify.sh` passes all three gates (verify: run it)

---

## Deferred (explicitly out of v1)

Broker direct-connect and read-only key sync, multi-user billing and quotas,
Spaces / mentor-student mode, community and leaderboards, realtime notification
push, and a mobile client. These are recorded in `docs/trader-product.md` so they
are not forgotten; none of them is a v1 deliverable.

