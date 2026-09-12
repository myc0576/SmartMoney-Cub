```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

The review workbench is the local-first interface of `smartmoney-cub-harness`. It turns broker
screenshots, PDFs, and CSV exports into a reviewable ledger, then gives you a
review assistant that works on reviewed evidence.

## Start it

```bash
npx smartmoney-cub
```

or, from a Python environment:

```bash
python -m pip install -e ".[dev]"
smcub workbench
```

`smcub workbench` binds `127.0.0.1:8787` and opens a browser. Binding anything other than
loopback requires an explicit `--token`, because a review journal must not become
reachable on a shared network by accident.

## Layout

| Region | Contents |
| --- | --- |
| Left | Navigation and the local portfolio switch |
| Middle | The working page: overview, trades, calendar, analytics, rules, import, plugins, settings |
| Right | The review assistant, docked and collapsible |

The right panel collapses on a narrow window and becomes a drawer on a phone.

## Pages

| Page | Answers |
| --- | --- |
| Overview | Net PnL, win rate, profit factor, drawdown, equity curve, open positions, and the items waiting for review |
| Trade log | Every confirmed round trip, with a detail drawer showing matched lots and every fill revision |
| Review calendar | Daily profit and loss for a month, with the trades behind each day |
| Analytics | Breakdowns by symbol, market state, weekday, holding period, and tag, each with its sample size |
| Rule library | Challenger and champion rules with their evidence |
| Import | Local parsing, per-field confidence, correction, and commit |
| Plugins | Discovered read-only data sources and their capabilities |
| Settings | Providers, redaction policy, outbound audit, and local diagnostics |

## Import contract

1. A file is hashed with SHA-256 and stored once under that hash. Re-importing the
   same bytes returns the same document instead of a duplicate.
2. Parsing runs on this machine. CSV, TSV, and text use the built-in reader; PDFs
   use a local text layer first; scanned PDFs and images need the local OCR extra.
3. Every extracted row carries per-field confidence. Nothing is written to the
   ledger until the user confirms the row.
4. If any row in a confirmed batch fails validation, the whole batch is refused. A
   partial import is worse than no import.
5. A correction appends a revision. The earlier revision stays readable and is
   marked as superseded, so an edit remains auditable.

Local OCR is optional and stays local:

```bash
python -m pip install "smartmoney-cub-harness[ocr]"
# or
npx smartmoney-cub install --with-ocr
```

Without it, screenshots and scanned PDFs return a structured explanation naming
the missing engine rather than an error or a fabricated result.

## Metrics and their limits

Profit factor is fixed as gross profit divided by the absolute gross loss. When a
sample has no losing trade it is reported as undefined, not as a large number.

Every aggregate carries its sample size. A breakdown group under five trades is
flagged `small_sample` in the API and marked with an asterisk in the interface, so one
lucky trade never reads as a pattern. The summary states that the sample is
self-selected review history rather than a controlled study.

## Safety boundaries

- The workbench never places, modifies, or cancels an order and never connects to a
  broker.
- The assistant is a separate concern: it reads review data and can propose a
  challenger rule. It cannot promote a rule.
- Raw attachments stay on disk. See docs/review-agent.md for what may leave the
  machine.
