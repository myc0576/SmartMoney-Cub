# Safety

`smartmoney-cub-harness` is a trading journal, review, and rule-evolution tool. It does not provide securities investment advice and does not connect to real trading execution.

Read-only applies to markets and execution. The harness is writable with respect
to the user's own journal: it stores trades, notes, playbooks, and backtest runs
in the local or tenant store named by the user. Nothing in that store is committed
to this repository.

## Hard Boundary

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

This declaration is required on core artifacts and in doctor output.

## Redaction

The package redacts:

- credential-like fields;
- session and authorization fields;
- account-like fields;
- emails;
- phone numbers;
- local absolute paths.

Redaction happens before command metadata and CLI output are written.

## Data Policy

Real trades, accounts, notes, and backtest runs are runtime data. They belong in
the user's local or tenant store and must not be committed to this repository.
Repository fixtures, examples, and tests use toy data only.

Do not commit:

- real trades;
- real watchlists;
- real account identifiers;
- private local paths;
- credentials;
- cookies;
- private notes;
- backtest runs produced from real data.

Repository examples must remain toy-only. The core runs offline; online market
sources are opt-in at call time and record their provenance when used.

The TradingAgents adapter is optional and user-configured. External LLM/API credentials remain outside this repository and must never be committed or captured in artifacts.
