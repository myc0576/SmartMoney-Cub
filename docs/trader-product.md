# Trader Product v1

The trader product is the hosted half of `smartmoney-cub-harness`. It is a
trading journal and review tool: it imports a trader's own executions, computes
performance analytics, lets the trader declare and score playbooks, runs
backtests against a JSON strategy DSL, and replays historical bars. It is
multi-tenant and runs on the alphatech platform behind the platform's login.

It is **read-only with respect to markets and execution** and **writable with
respect to the user's own journal**. Every response carries
`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`, which asserts the execution ban and
nothing more. The binder for this document is `docs/trader-product-spec.md`;
where the two disagree, the spec wins. The HTTP surface is listed in
`docs/trader-api.md`, and the deployment routes in `deploy/README.md`.

## Where it lives

The product is a peer entry on the alphatech platform, at
`alphatech.net.cn/trader`, alongside Alpha Canvas and the Commerce Workbench.
Requests arrive carrying the caller's platform session cookie; the product
resolves that cookie to a tenant and implements no registration and no password
storage of its own. Identity is a platform user id mapped to a stable tenant
`alphatech:<id>`.

## What v1 does

### Serve both products from one process

`smcub trader serve` mounts the trader API at `/api/trader/*` and the review
workbench interface on the same socket and the same port. A local run is a
single offline user on SQLite in `--state-dir`; a hosted run is one tenant per
platform identity, in Postgres.

`smcub workbench` is a different command and does not mount `/api/trader/*`.
Only `smcub trader serve` serves both.

### Keep the journal in a tenant store

One `TenantStore` interface, two engines. Local mode writes SQLite under the
state directory; hosted mode writes Postgres, and refuses to start without a
`postgresql://` URL rather than falling back to a local file. Every
tenant-scoped row carries a user identifier and every tenant-scoped query
filters on it, so one tenant cannot read another's trades.

Fetched bars are stored so a review can be reproduced. A user's real trades,
accounts, notes, and backtest runs live in that store and are never committed
to the repository.

### Import the trader's own executions

An import turns the trader's own fills into round trips with a position ledger:
batched fills, partial closes, cross-day positions, T+1, fees, oversell,
duplicate rows, limit-board, and suspension flags. Ambiguity is reported as
`needs_review` instead of silently becoming a trade.

### Compute performance analytics once

The performance summary, the breakdown by dimension, and the calendar all read
the same metric implementation as the backtest. The journal and the backtest
cannot disagree about what a metric means. Profit factor is gross profit over
absolute gross loss, and reads as undefined for a sample with no losing trade.

### Declare and score playbooks

A playbook is the trader's own stated pattern. The product scores the journal
against it, so the trader can see where their execution matched their stated
rule and where it did not, without the product inventing a rule or a label.

### Backtest a JSON strategy DSL

`POST /api/trader/backtest/run` takes a strategy in the JSON rule DSL and
returns the run; saved runs are listed and re-readable. Backtests are
deterministic: identical inputs produce identical outputs. A strategy that
fails DSL validation is a `400`, not a silent partial run.

### Replay historical bars

A replay session steps the trader through historical bars so a past decision
can be reviewed with the information that was actually available at the time.

### Fetch market data with provenance

The built-in market sources are free and keyless, and are called only when the
trader asks for data. Importing the package performs no network access. Every
fetched series records its provider, fetch time, and a quality flag, and
anti-future-leakage validation applies to market data exactly as it applies to
any other input: a source whose `available_at` is later than the decision time
fails validation. A source that does not answer is a `502`, because a quiet
market and a broken source are never the same answer.

## Non-goals

These are not gaps to be closed later. They are the permanent boundary of the
product, and the execution ban among them is absolute.

- **No orders.** The product does not place an order, in any mode, for any
  reason. No endpoint has one.
- **No cancellation.** It does not cancel an order either, placed by it or by
  anyone else.
- **No broker account mutation.** It does not modify a broker account, a
  position, a balance, or a setting at a broker.
- **No execution automation.** There is no background process that acts on the
  market. Every artifact the product produces is for the trader to read.
- **No broker trading channel.** It does not open a broker's trading session or
  connect to a broker's order gateway.
- **No advice.** It does not give investment advice, produce buy or sell
  recommendations, or tell the trader what to do next.
- **No stock picking.** It is not a screener, a signal service, or a prediction
  engine. It records and reviews what the trader did.

The prohibitions are enforced by tests, not only by intent: `doctor()` keeps
`execution_integrations == "disabled"` and `broker_api_required is False`,
and the safety declaration string is asserted on every generated artifact.

## Deferred past v1

These features are planned for after v1. They are recorded here so they are not
forgotten. None of them is a v1 deliverable, none of them is implemented, and
listing them does not change the non-goals above; in particular, nothing in
this list authorizes order placement or execution automation.

- **Broker direct-connect and read-only key sync.** Reading a broker account
  through a read-only API key instead of an export file. Read-only is the whole
  point of the item: a write-scoped key is out of scope permanently, not
  deferred. The spec records the same item as "broker direct-connect and
  key-based sync".
- **Multi-user billing and quotas.** Plans, per-tenant storage and backtest
  quotas, and payment. v1 runs tenants without metering them.
- **Spaces and mentor-student mode.** A shared surface where a mentor reviews a
  student's journal, with roles and visibility rules. The spec records the same
  item as "Spaces and mentor-student mode".
- **Community features and leaderboards.** Cross-tenant sharing, ranking, and
  comparison. Note that this is the item most likely to collide with the data
  policy: a leaderboard is a decision about publishing a user's records, so it
  needs an explicit consent design, not only a feature.
- **Realtime notification push.** Out-of-band alerts, for example when a
  review lands or a rule changes state. It needs a device or channel registry
  that v1 does not have.
- **A mobile client.** A phone client. The interface is served from the
  package and is usable in a mobile browser today; a native client is the
  deferred part, and it is what would make realtime notification push useful.

## Where the rest of it is written down

| Topic | Document |
| --- | --- |
| Binding spec, goal, and out-of-scope list | `docs/trader-product-spec.md` |
| HTTP endpoints, status codes, and identity | `docs/trader-api.md` |
| Deployment routes (compose, image, systemd + nginx) | `deploy/README.md` |
| Execution ban and the safety declaration | `docs/harness-contract.md`, `docs/safety.md` |
| Data and privacy policy | `docs/privacy.md` |
| The local review workbench | `docs/review-workspace.md`, `docs/review-agent.md` |
| Market data providers and provenance | `docs/trader-api.md` |

Safety remains `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.
