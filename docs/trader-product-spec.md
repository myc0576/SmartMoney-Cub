# Trader Product v1 — Spec

This is the binding authority for the plan in
`docs/superpowers/plans/2026-09-13-trader-product-v1.md`. Where the plan and this
spec disagree, this spec wins.

## Goal

Extend `smartmoney-cub-harness` from a read-only review control plane into a
hosted trading-journal and review product, delivered as a peer entry on the
alphatech platform beside Alpha Canvas and the Commerce Workbench.

## What the product is

A trading journal and review tool. It imports a trader's own executions, computes
performance analytics, lets the trader define and score playbooks, runs backtests
against a JSON strategy DSL, and replays historical bars. It is multi-tenant and
runs on the alphatech platform behind the platform's login.

## What the product is not

It does not place orders, cancel orders, modify a broker account, or automate
execution. It does not give investment advice, produce buy/sell recommendations,
or connect to a broker's trading channel. Those prohibitions are permanent and are
enforced by tests.

## Tenancy and identity

- Hosted mode authenticates via an alphatech platform identity. The product does
  not implement registration or password storage of its own.
- Local mode runs as a single local user with no authentication, for offline use
  and CI.
- Every tenant-scoped row carries a user identifier and every tenant-scoped query
  filters on it. Isolation is proven by test.

## Data policy

- Runtime data — a user's real trades, accounts, notes, and backtest runs — is
  stored in the tenant's store. It is never committed to the repository.
- Repository fixtures, examples, and tests use toy data only.
- No credentials, cookies, local absolute paths, or account identifiers appear in
  any committed artifact.

## Market data policy

- Built-in market sources are free and keyless, and are called only when the user
  asks for data. Importing the package performs no network access.
- Every fetched series records its provenance: provider, fetch time, and a
  quality flag. Anti-future-leakage validation applies to market data exactly as it
  applies to any other input.

## Provenance and determinism

- Any input whose `available_at` is later than the decision time fails validation.
- Backtests are deterministic: identical inputs produce identical outputs.
- Report metrics come from one shared implementation, so the backtest and the
  journal cannot disagree about what a metric means.

## Interfaces

- The product's HTTP surface lives under `/api/trader/*` on the existing local
  service, so one process serves both the review workbench and the trader product.
- Every response carries the safety declaration
  `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`, which asserts the execution ban and
  nothing more.
- The core package continues to install with no third-party runtime dependency.
  Hosted-mode extras are opt-in.

## Compatibility

The product's API must be able to back a real, shipping trading-journal UI without
that UI changing its own data contract. Compliance is demonstrated against the
archived TradeZella bundle as an external oracle, not asserted.

## Out of scope for v1

Broker direct-connect and key-based sync, billing and quota enforcement, Spaces and
mentor-student mode, community features and leaderboards, realtime notification
push, and mobile clients. These are listed in the product documentation as
deferred so they are not forgotten.

## Success

The product ships when: the contract documents describe the product accurately;
every v1 capability is implemented and covered by passing tests; the full suite and
`./scripts/verify.sh` pass; the frontend builds into the packaged interface and
passes a browser-based visual check; the bundle oracle renders cleanly against the
real backend; and deployment artifacts let someone run the hosted product.

