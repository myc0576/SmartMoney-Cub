# Privacy

`smartmoney-cub-harness` is local-first and offline by default.

The project does not collect, upload, sell, or learn a user's trading logic. The public core has no server, no telemetry, no remote database, and no real account connection.

## Defaults

- `network_required`: `false`
- `telemetry`: `false`
- `upload`: `false`
- `default_data_mode`: `offline_json_fixtures`
- `execution_integrations`: `disabled`
- `redaction`: `enabled`
- `safety`: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`

Run:

```bash
smcub privacy-audit
```

## What Stays Local

Private trading plans, journals, screenshots, exports, rule notes, and review memories should stay in local artifacts. They should not be committed to this public repository.

The CLI redacts common sensitive strings before printing JSON output, including email, phone, token, cookie, account-like keys, Windows paths, and Unix home paths.

The TradingAgents adapter is optional and user-configured. External LLM/API credentials remain outside this repository and must never be committed or captured in artifacts.

## What Public Examples May Contain

Public examples must use toy offline data only. They may demonstrate schemas, case records, memory files, and ledger events, but not real trades, private watchlists, credentials, cookies, account identifiers, or local private paths.

## Default Redaction for Review Sessions

The review workbench is redaction-first. When the review assistant talks to an
external model provider, the request carries only redacted structured fields.

- Screenshots, PDFs, and CSV originals never leave the machine. They are parsed
  locally and stored locally.
- Account numbers, names, and direct identifiers are removed or replaced with a
  device-stable pseudonym.
- Security codes, portfolio names, exact quantities, exact amounts, and exact
  timestamps are replaced with pseudonyms, range bands, or time buckets.
- Returns, holding periods, execution deviation, and statistical features are kept,
  because the review is meaningless without them.
- Every outbound request is recorded locally in an audit table listing which fields
  were sent and how many values were replaced. There is no override switch.

This policy applies to the preconfigured company gateway and to every provider
added later. See [docs/review-agent.md](review-agent.md) for the full table.

When no provider key is configured, the assistant answers from local data and
sends nothing.
