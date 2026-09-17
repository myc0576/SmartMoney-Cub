# Privacy

`smartmoney-cub-harness` is local-first. The core installs and runs with no
network, and hosted tenant mode is opt-in.

The project does not collect, upload, sell, or learn a user's trading logic. The
core has no server, no telemetry, and no real account connection. Hosted mode
stores the user's own journal in that tenant's store; it does not publish it.

Read-only applies to markets and execution. The user's own journal is writable:
imported trades, notes, playbooks, and backtest runs are written to the local or
tenant store and are never committed to this repository.

## Defaults

- `network_required`: `false`
- `telemetry`: `false`
- `upload`: `false`
- `default_data_mode`: `offline_json_fixtures`
- `execution_integrations`: `disabled`
- `redaction`: `enabled`
- `safety`: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`

### `smcub doctor` defaults

`smcub privacy-audit` does not print these two keys; `smcub doctor` does:

- `market_data_mode`: `offline`
- `tenant_mode`: `local_single_user`

`network_required: false` means the core is usable with no network. Built-in
market sources are free and keyless, and are called only when the user asks for
data; importing the package performs no network access.

## Network Policy

- Importing the package performs no network access and requires no credential.
- Built-in market sources are opt-in at call time, keyless, and never contacted on
  import or during a default offline run.
- Every fetched series records its provenance: provider, fetch time, and a quality
  flag. Anti-future-leakage validation applies to fetched market data exactly as it
  applies to any other input.
- Redaction and review-assistant rules below still govern anything that leaves the
  machine.

Run:

```bash
smcub privacy-audit
```

## What Stays Local

Private trading plans, journals, screenshots, exports, rule notes, and review
memories stay in the local or tenant store. They are not committed to this public
repository.

The CLI redacts common sensitive strings before printing JSON output, including email, phone, token, cookie, account-like keys, Windows paths, and Unix home paths.

The TradingAgents adapter is optional and user-configured. External LLM/API credentials remain outside this repository and must never be committed or captured in artifacts.

## What Public Examples May Contain

Public examples must use toy offline data only. They may demonstrate schemas, case
records, memory files, and ledger events, but not real trades, real backtest runs,
private watchlists, credentials, cookies, account identifiers, or local private
paths.

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

When a key-required provider has no configured key, the assistant shows setup
guidance and sends nothing. Local gateways that explicitly declare
`requires_key = false` can still be used through their own authentication
boundary.
