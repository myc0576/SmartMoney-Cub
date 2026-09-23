# Harness Contract

`smartmoney-cub-harness` is a trading journal and review harness. It records decisions, imports a trader's own executions, computes performance analytics, validates provenance, reviews D1/D3 outcomes, and evolves rules through challenger -> champion governance.

It is **read-only with respect to markets and execution** and **writable with
respect to the user's own journal**. The journal, notes, and backtest runs it
produces are the user's own data, stored locally or in the user's tenant store,
and never committed to this repository.

It is not a stock picker, financial adviser, or execution system. Optional,
user-authorized read-only account ingestion can import a user's own history,
balances and positions. It cannot place or cancel orders, modify an account,
withdraw funds, or automate broker login/export. Core journal use stays offline.

## Safety Declaration

Every manifest, decision, outcome, evaluation, registry, and doctor output must carry:

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

This declaration asserts the execution ban, and nothing more. It does not mean the
harness cannot write: the journal, review, and backtest artifacts it owns are
writable, while market and execution authority stay permanently out of reach.

## Seven Principles

1. **Read-only safety is non-negotiable.** Read-only applies to markets and execution: no order placement, cancellation, account modification, or execution automation. The user's own journal remains writable.
2. **No future leakage.** A data source with `available_at > decision_time` fails manifest validation.
3. **No non-silent observation without invalidation.** ALERT/WATCH style observations must include invalidation price, time stop, give-up conditions, data source, available time, and data quality. This provenance requirement applies to the harness's own journal entries and to any online market data it is asked to fetch.
4. **Public cases are learning material only.** Published examples may inform review and rule proposals, not direct live instructions. A user's own journal entries are private records and are never published.
5. **Shadow first, explicit promotion later.** Challenger rules become champion only after metrics pass and confirmation is explicit.
6. **Provenance first.** Data sources carry fetch time, available time, and quality flag.
7. **Memory is portable text.** Journals and memories are written as plain, portable files or store rows the user can read and move. Public examples and docs are plain files, never a private shared database.

## Decision Labels

| Label | Meaning |
|---|---|
| `SILENT` | No command produced usable stdout. |
| `ALERT` | Context was recorded for review. It is not an instruction. |
| `ERROR` | One or more sources failed. |
| `WATCH` | Observation only. |
| `AVOID` | Avoidance rationale. |
| `EMPTY_POSITION` | No active exposure context. |

## Promotion Thresholds

| Metric | Threshold |
|---|---:|
| `sample_count` | `>= 20` |
| `false_alert_rate` | `<= 0.2` |
| `missed_opportunity_rate` | `<= 0.25` |
| `future_leakage_count` | `= 0` |
| `risk_contract_violation_rate` | `= 0` |

Passing thresholds may create a promotion recommendation. Champion mutation still requires explicit confirmation.
