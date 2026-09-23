# Trader API reference

The trader product's HTTP surface. It is mounted on the same process and port as
the local review workbench, under the `/api/trader/*` prefix, so one deployment
serves both products.

Every response body carries the execution ban:

    "safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"

The declaration asserts the execution ban and nothing more. Nothing in this API
places an order, cancels an order, modifies a broker account, or automates
execution.

## Identity

Every handler resolves the request to an identity before it does anything else,
and passes that identity into storage. No endpoint accepts a user id as an
argument, so a request cannot ask for another tenant's data.

- Local mode: one fixed offline user (`local`). The request headers are not read.
- Hosted mode: the alphatech platform identity, resolved from the caller's
  session cookie (forwarded to the platform) or from a signed identity header,
  depending on `ALPHATECH_AUTH_MODE`. Configuration and header names are
  documented in `src/smartmoney_cub_harness/trader/auth/alphatech.py`.

A request with no verifiable identity is refused with `401`:

    {"status": "error", "code": "unauthorized", "error": "...",
     "status_code": 401, "safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"}

## Status codes

| Status | Meaning |
| --- | --- |
| `200` | The request was served. |
| `400` | The request is malformed, or a strategy failed DSL validation. |
| `401` | No verifiable identity. |
| `404` | No such route, or no such record for this tenant. |
| `502` | A market data source did not answer. A quiet market and a broken source are never the same answer. |
| `500` | An unexpected service failure. The body still carries the safety declaration. |

## Endpoints

    GET /api/trader/health
    GET /api/trader/meta
    GET /api/trader/market/providers
    GET /api/trader/market/bars?provider=&symbol=&interval=&start=&end=&limit=
    GET /api/trader/trades?account_id=&symbol=&from=&to=&limit=&offset=
    POST /api/trader/trades/import
    GET /api/trader/trades/{round_trip_id}
    GET /api/trader/accounts
    POST /api/trader/accounts
    GET /api/trader/connections
    GET /api/trader/connections/manifests
    GET /api/trader/connections/accounts
    POST /api/trader/connections/{provider_id}/connect
    POST /api/trader/connections/{provider_id}/sync
    POST /api/trader/connections/{provider_id}/disconnect
    POST /api/trader/connections/snaptrade-personal-mcp/oauth/start
    POST /api/trader/connections/snaptrade-personal-mcp/oauth/complete
    GET /api/trader/connections/snaptrade-personal-mcp/oauth/callback
    GET /api/trader/analytics/summary?from=&to=&account_id=
    GET /api/trader/analytics/breakdown?dimension=&from=&to=
    GET /api/trader/calendar?year=&month=
    GET /api/trader/insight/mistakes?from=&to=&account_id=
    GET /api/trader/insight/edges?from=&to=&account_id=
    GET /api/trader/insight/patterns?from=&to=&account_id=
    POST /api/trader/insight/patterns/decisions
    GET /api/trader/playbooks
    POST /api/trader/playbooks
    POST /api/trader/backtest/run
    GET /api/trader/backtest/runs
    GET /api/trader/backtest/runs/{run_id}
    POST /api/trader/replay/sessions
    GET /api/trader/replay/sessions
    GET /api/trader/replay/sessions/{session_id}
    POST /api/trader/replay/sessions/{session_id}/actions

The method and path of each line above are the route table in
`src/smartmoney_cub_harness/trader/api/routes.py`, and a test asserts the two
agree.

### Liveness and metadata

- GET /api/trader/health - `status`, the resolved `user_id` and `tenant_id`,
  the auth mode, and the safety declaration.
- GET /api/trader/meta - product name, the resolved tenant, the storage engine
  (`sqlite` or `postgres`), the auth mode, and the capability list.

### Market data

- GET /api/trader/market/providers - the built-in keyless sources:
  `provider_id`, `label`, `markets`, `requires_key`, `source_quality`,
  `description`. Listing providers performs no network access.
- GET /api/trader/market/bars?provider=&symbol=&interval=&start=&end=&limit= -
  fetches one normalized OHLCV series on demand. `provider` is one of
  `eastmoney`, `tencent`, `stooq`, `binance`; `interval` is one of `1m`,
  `5m`, `15m`, `30m`, `60m`, `1d`, `1w`, `1M`; `start` and `end` are
  inclusive ISO-8601 dates (or timestamps for intraday); `limit` defaults to 500
  and is capped at 5000. The response is the provider result plus `cached`, and
  the fetched bars are written to the calling tenant's own bar cache with their
  provider and fetch time. A source that will not answer produces `502`.

### Journal

- GET /api/trader/trades?account_id=&symbol=&from=&to=&limit=&offset= - the
  tenant's stored executions and the round trips they close, matched with the
  same FIFO matcher the review workbench uses. `from` and `to` filter on
  `trade_date`. The body carries `trades` (closed round trips), `fills`,
  `open_positions`, `issues`, and `ledger_status`.
- POST /api/trader/trades/import - imports the tenant's own executions. The body
  is JSON (`{"rows": [...]}`, or `{"trades": [...]}` / `{"fills": [...]}`, or
  a bare JSON array) or CSV text (`Content-Type: text/csv`, or any body that does
  not start with `{` or `[`). Each row needs `trade_id`, `symbol`, `side`
  (`BUY` or `SELL`), `price`, `quantity`, and `trade_date`; `trade_time`,
  `name`, `account_id`, `fee`, `thesis`, `invalidation_price`, `regime`,
  and `tags` are optional, and the store also accepts its documented aliases
  (`date`, `qty`, `commission`, `fill_id`). Re-importing the same `trade_id`
  corrects that row instead of duplicating the position.
- GET /api/trader/trades/{round_trip_id} - one round trip, plus the ledger issues
  touching its symbol. The id is matched inside the calling tenant's own ledger,
  so another tenant's id answers `404`.

### Accounts

- GET /api/trader/accounts - the tenant's accounts.
- POST /api/trader/accounts - creates or updates one account. The body takes
  `account_id` (generated when absent), `name`, `broker`, `currency`, and
  `initial_balance`.

### Analytics

Every number comes from the calling tenant's own stored trades, through
`smartmoney_cub_harness.analytics`, which is the same implementation the
backtester uses for win rate, profit factor, drawdown, and trade counts.

- GET /api/trader/analytics/summary?from=&to=&account_id= - the performance
  summary: net P&L, win rate, profit factor, drawdown, average holding period,
  fee total, open position count, and the sample-size note.
- GET /api/trader/analytics/breakdown?dimension=&from=&to= - performance grouped
  by one dimension (`symbol`, `regime`, `weekday`, `holding`, `tag`). Omit
  `dimension` for all of them. Each row carries `trade_count`, `win_rate`,
  `net_pnl`, `avg_return_pct`, `profit_factor`, and `small_sample`.
- GET /api/trader/calendar?year=&month= - closed round trips aggregated by exit
  day for one month. Defaults to the current month.

### Insight

- GET /api/trader/insight/mistakes?from=&to=&account_id= - deterministic candidate
  mistake clusters identified from journal executions: broken invalidation unstopped,
  early morning exit, one-day holding, and revenge reentry. Every cluster carries the
  non-silent observation envelope: `invalidation`, `time_stop`, `give_up`,
  `data_source`, `available_at`, and `data_quality`.
- GET /api/trader/insight/edges?from=&to=&account_id= - profitable edges extracted
  from journal performance grouped by `tag`, `regime`, and `holding`. Each edge
  carries the non-silent observation envelope and `small_sample` indicator.

### Playbooks

- GET /api/trader/playbooks - the tenant's declared playbooks, each scored against
  the tenant's own journal, plus the playbooks their journal already shows
  (grouped by `tag` and `regime`). Scoring is `analytics.group_performance`
  over the tenant's own ledger, and every row carries `small_sample` so a single
  lucky trade never reads as a pattern.
- POST /api/trader/playbooks - declares or updates one playbook. The body takes
  `name`, `dimension` (`tag` or `regime`), `key`, and optional
  `description` and `rules`. The declaration is written to the tenant's own
  audit trail, and the response returns the scored view of that playbook.

### Backtest

- POST /api/trader/backtest/run - the body carries `strategy` (the JSON rule
  DSL), `data` (`symbol`, `interval`, and one of `bars`, `provider`, or
  `cached: true`), and optionally `initial_cash` (default 100000),
  `fees_bps`, `slippage_bps`, and `save` (default true). The strategy is
  validated against the frozen DSL before anything runs; an unknown key is refused
  with `400` and a message naming the key path. Nothing in the payload is
  executed as code. The response carries the full result, the resolved bar
  provenance, and the `run_id` when the run was saved.
- GET /api/trader/backtest/runs - the tenant's saved runs, newest first, with
  their metrics.
- GET /api/trader/backtest/runs/{run_id} - one saved run, including its spec and
  equity curve.

### Replay

- POST /api/trader/replay/sessions - the body carries `symbol`, `interval`, one
  of `bars`, `provider`, or `cached: true`, and optional `index` (starting
  frame), `mode: review|training`, optional `account_id` and `initial_cash`.
  The response holds only bars and actual markers through the current cursor.
- GET /api/trader/replay/sessions - list persisted session metadata without future bars.
- GET /api/trader/replay/sessions/{session_id}?index= - steps the session to a
  frame index and returns that frame. Sessions survive restarts; another tenant's
  session id answers `404`. Historical availability is explicitly unverified
  unless the source supplies point-in-time provenance; fetched time is not
  presented as historical availability.
- POST /api/trader/replay/sessions/{session_id}/actions - `action` is `step`,
  `seek`, `rewind`, or `simulate`. Seek/rewind use `index`. Simulation accepts
  `side: BUY|SELL` and a positive fractional `quantity` only in training mode.
  The request fills on the next revealed bar's open in a separate, unleveraged
  paper ledger (zero fees/slippage, explicitly labeled). A training rewind
  creates a new session branch and preserves the original experiment. None of
  these records enter imported real executions or call an external trade API.

## Running it

`smcub trader serve` runs the product on the same port as the review workbench:

    smcub trader serve --mode local --state-dir state/trader
    smcub trader serve --mode hosted --database-url postgresql://... --no-browser

Local mode uses SQLite and one fixed offline user. Hosted mode uses Postgres
(install the `hosted` extra) and requires `--database-url`; it refuses to start
without one rather than silently writing a local file. Every tenant-scoped query
filters on the resolved user id, and isolation is proven by test.

Runtime data - real trades, accounts, and backtest runs - lives in the tenant's
store and is never committed to the repository.
