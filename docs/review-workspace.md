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
smcub workspace rules                 # the rule library, with promotion blockers
smcub workspace rules --status champion
smcub workspace promote-rule RULE-1 --note "reviewed the gates"
smcub workspace reject-rule RULE-1 --note "superseded by RULE-2"
```

The database defaults to `state/workspace/review.db`; override it with `--db`.
`register-candidate`, `self-evolve`, and `confirm-promotion` accept `--workspace-db`
so the JSON rule registry they write stays mirrored into this one library.

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

Two gates are deliberately separate. The threshold gate -- `sample_count >= 20`,
`false_alert_rate <= 0.2`, `missed_opportunity_rate <= 0.25`, zero future leakage,
zero risk-contract violations -- decides whether the evidence may produce a
promotion *recommendation*. It does not authorize the mutation. The human gate is
the written note, and it is the only thing that writes a champion row. So
`promote-rule` reports the outstanding blockers and then proceeds only when a note
is supplied; a blank or missing note is refused, and nothing is written.

Every rule carries its blockers wherever it is read, from the one frozen threshold
check the rest of the product uses, so the interface and the CLI cannot disagree
about what a rule is still missing.

The review assistant can only ever propose a challenger. A proposal records its
blockers, appends an entry to `evolution_ledger.jsonl` beside the workspace
database, and appends a readable fragment to `memory.md` in the same directory. It
cannot promote, and no tool it can call reaches a champion row.

## Statistics and their limits

`workspace summary` reports counts, the sample size behind any mean, and a written
statement that the sample is self-selected review history rather than a controlled
study. Small samples are shown as small samples.
