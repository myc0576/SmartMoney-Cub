# Contract oracle

The trader product's API must be able to back a real, shipping trading-journal
interface without that interface changing its own data contract. This oracle
demonstrates that rather than asserting it.

```bash
bash scripts/trader-oracle.sh            # defaults: API on 8791, bundle on 8799
```

It exits 0 when every required route renders with zero console errors and at
least one route is backed by the real backend.

## What it actually does

1. Starts the product's own server — `smcub trader serve --mode local` — on a
   temporary store. This is the backend under test; nothing about it is stubbed.
2. Seeds it with one account and four toy fills (two closed round trips).
3. Serves an archived third-party trading-journal bundle whose data contract was
   reverse-engineered in an earlier phase, with a translation adapter injected
   ahead of it.
4. Drives five routes in Chromium and writes `work/trader-oracle/report.json`.

## The design, and why the split matters

The bundle reads roughly forty endpoints with shapes that took the earlier recon
phase many iterations to satisfy. Re-deriving all of them inside the adapter would
be a second implementation of someone else's wire format, and every mistake would
surface as a rendering error rather than as evidence about our API.

So the oracle inverts the problem. The validated fixture library answers every
endpoint by default, and the adapter **overrides only the endpoints our backend
owns**, merging our values into the fixture's already-correct shape. Each override
is a real call to `/api/trader/*` and is recorded as `REAL`; everything else is
recorded as `FALLBACK`. The report prints both counts per route.

That split is the entire point. A route that renders from fixtures proves nothing
about our backend, and the report never lets one be mistaken for the other. The
current run: **5 routes clean, 0 console errors, 5 backed by real backend calls**
(30 real vs 20 fallback).

## The endpoints under test

| Bundle endpoint | Our endpoint | What it proves |
|---|---|---|
| `auth/validate_token` | `/api/trader/meta` | the session contract resolves |
| `user/get_onboarding` | `/api/trader/meta` | the onboarding gate clears |
| `user/profile` | `/api/trader/meta` | account profile shape holds |
| `account/index` | `/api/trader/accounts` | accounts render |
| `trades/all_trades` | `/api/trader/trades` | the trade ledger renders |
| `trades/all_symbols` | `/api/trader/trades` | the symbol universe derives |
| `strategy/playbooks` | `/api/trader/playbooks` | playbooks render |
| `filters/dashboard_stats`, `filters/winrate` | `/api/trader/analytics/summary` | headline stats come from our analytics |

## What it deliberately does not prove

- **Not a compatibility guarantee for every endpoint.** Only the rows above are
  exercised against our backend. The rest of the bundle's surface is answered by
  fixtures and proves nothing.
- **Not a full table render on every route.** The trade-log route renders its
  toolbar, filters, and column configuration from our data, but the row count
  depends on the bundle's own account/paginator interaction, which the adapter
  does not fully model. The report states the observed row count rather than
  implying more.
- **Not a performance or load test.** This is a single-user functional pass.
- **Not a legal clearance.** The archived bundle is third-party copyrighted build
  output. It lives under `work/`, is git-ignored, and is never published. Nothing
  from it is copied into `src/`.

## Reproducing

The bundle is git-ignored local material and is not shipped. To restore it, re-run
the recon scripts described in `work/tradezella-ui/README.md`; the oracle needs
`work/tradezella-ui/assets/` and `scripts/mock-api.js` to be present. If either is
missing the script exits 3 with that message rather than reporting a false pass.

Playwright is already a root dependency (`node_modules/playwright`).

## Reading a report

```
/tracking/trade-log   ok=True  dom=32259  rows=0  REAL=8  FALLBACK=3  errs=0
```

`REAL` counts requests answered from our backend; `FALLBACK` counts those the
fixture had to answer. A route with `REAL=0` rendered without exercising our API
at all. `errs` is the count of non-noise console errors after filtering
third-party analytics noise, which the archived page emits regardless of backend.

The script refuses to start if either port is already in use, because a stale
server would answer the browser and make the whole report meaningless.

