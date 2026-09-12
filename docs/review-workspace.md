# Review Workspace

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

The review workspace is a local SQLite database holding review cases, outcomes,
plugin evidence, and rule state. It answers questions in seconds and keeps
immutable evidence in the Evidence Pack and plugin envelopes.

## Division of responsibility

| Store | Owns |
| --- | --- |
| SQLite workspace | Cases, outcomes, evidence index, rule state, filtering, counts |
| Evidence Pack and envelopes | Immutable, hashed, replayable proof |
| Plugin state store | Plugin identity, lifecycle state, and audit history |

SQLite is a convenience index. A number that appears in the workspace can always be
traced back to a hashed artifact.

## Review cases

A case is keyed to a decision, not to a trade. Supported actions are
`BUY`, `SELL`, `HOLD`, `FLAT`, `AVOID`, and `NO_DECISION`, plus the
harness labels `ALERT`, `WATCH`, `EMPTY_POSITION`, `ERROR`, and `SILENT`.

Flat and avoidance positions are first-class. Staying out of the market is a
decision worth reviewing, and it gets the same evidence treatment as an entry.

## The risk contract

Every observation that is not `SILENT`, and not a recovered historical fact, must
carry:

| Field | Meaning |
| --- | --- |
| `invalidation_price` | The level at which the thesis is wrong |
| `time_stop` | When the observation expires |
| `give_up_conditions` | What makes you abandon the idea |
| `data_source` | Where the input came from |
| `available_at` | When that input became available |
| `data_quality_flag` | `ok`, `stale`, `partial`, `missing`, or `error` |

If any field is missing, the case is refused with the exact missing field names. If
`available_at` is later than `decision_time`, the case is refused as future
leakage.

## Command line

```bash
smcub workspace add-case case.json
smcub workspace list-cases --action AVOID
smcub workspace show-case RT-600111-1
smcub workspace record-outcome RT-600111-1 --horizon d1 --return-pct 3.5
smcub workspace import-csv exports/fills.csv
smcub workspace summary
```

The database defaults to `state/workspace/review.db`; override it with `--db`.

## Outcomes never rewrite history

Recording an outcome writes a separate row keyed by `(case_id, horizon)`. It does
not modify the case. The decision context stays exactly as it was frozen, which is
what makes a later replay meaningful.

## CSV import

`import-csv` runs the fill ledger and imports each closed round trip as an
`IMPORTED` case. Imported rows are historical facts, not forward-looking
observations, so they carry no fabricated risk contract.

Ambiguity is never silently converted into a trade. A same-day sell is flagged as a
T+1 violation, a sell without a prior position is flagged as unknown cost basis,
and an oversell is flagged as blocking. The import response reports the ledger
status and every issue so the user can correct the export.

## Rule state

`rule_state` tracks challenger, recommendation, champion, rejected, and deferred
status. A champion row cannot be written without an explicit human confirmation
note. That constraint is enforced in the workspace layer, so a dashboard, a plugin,
or a model cannot bypass it by writing to the database directly.

## Statistics and their limits

`workspace summary` reports counts, the sample size behind any mean, and a written
statement that the sample is self-selected review history rather than a controlled
study. Small samples are shown as small samples.
