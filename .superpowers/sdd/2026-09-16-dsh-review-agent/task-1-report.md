# Task 1 Implementation Report

## Scope delivered

Added typed, versioned Python contracts for review scope, redacted review
envelopes, evidence, structured review packages, plugin review results, safety
metadata, and stable error metadata. Added pure validation functions for
redaction, non-silent observation completeness, source/time semantics,
future-leakage prevention, and challenger-only mutation.

Current wire contracts use explicit `v2` schema identifiers. Explicit `v1`
readers normalize legacy scope, envelope, evidence, package, and plugin-result
field names into the current typed objects; unknown schema versions fail closed.

## Files changed

- `src/smartmoney_cub_harness/review_contracts.py`
- `src/smartmoney_cub_harness/review_validation.py`
- `tests/test_review_contracts.py`
- `.superpowers/sdd/2026-09-16-dsh-review-agent/task-1-report.md`

No provider, DSH bridge, Workbench server, GUI, or existing dirty-baseline file
was edited for Task 1.

## TDD evidence

### RED 1 — contract and validator API

Command:

```text
python -m pytest tests/test_review_contracts.py -q
```

Observed output and exit status:

```text
24 failed in 0.17s
ModuleNotFoundError: No module named 'smartmoney_cub_harness.review_contracts'
ModuleNotFoundError: No module named 'smartmoney_cub_harness.review_validation'
exit code 1
```

The failures were caused by the missing Task 1 production modules, not test
syntax or fixture errors.

### GREEN 1 — minimal contracts and validators

Command:

```text
python -m pytest tests/test_review_contracts.py -q
```

Observed output and exit status:

```text
24 passed in 0.03s
exit code 0
```

### RED 2 — attachment fields and exact-value leakage

Command:

```text
python -m pytest tests/test_review_contracts.py::test_redaction_validator_rejects_attachment_fields_and_uncoarsened_values -q
```

Observed output and exit status:

```text
5 failed in 0.06s
AssertionError: assert True is False
exit code 1
```

The validator incorrectly accepted a plain screenshot field and exact quantity,
amount, timestamp, and date values.

### GREEN 2 — tightened redaction contract

Command:

```text
python -m pytest tests/test_review_contracts.py::test_redaction_validator_rejects_attachment_fields_and_uncoarsened_values -q
```

Observed output and exit status:

```text
5 passed in 0.03s
exit code 0
```

### Focused regression gate

Command:

```text
python -m pytest tests/test_review_contracts.py tests/test_redaction.py tests/test_manifest.py tests/test_plugin_foundation.py tests/test_plugin_schemas.py -q
```

Observed output and exit status:

```text
83 passed in 0.09s
exit code 0
```

### Initial repository verification script

Command:

```text
./scripts/verify.sh
```

Observed output and exit status:

```text
Doctor contract check passed.
751 passed, 6 skipped in 25.70s
Safety sanity check passed.
Verification Loop: ALL GATES PASSED
exit code 0
```

Doctor output included `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

### Final repository-equivalent gate

After the final fixture privacy cleanup and report write, the repository-wide
script was run again. Its doctor gate passed and its full test gate reported
`751 passed, 6 skipped in 25.52s`, but its unscoped leak grep then matched the
pre-existing/generated GUI bundle's HTML credential input and exited 1. Task 1
does not own that file, so it was not edited.

The contract-authorized equivalent commands were then run against the final
Task 1 tree:

```text
python -m smartmoney_cub_harness.cli doctor
python -m pytest tests/ -q --tb=short
git diff --cached --check
Task 1 scoped secret/live-order/local-path scan
```

Observed output and exit status:

```text
doctor status: ok
safety: READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
751 passed, 6 skipped in 25.55s
Task 1 scoped safety and whitespace checks passed.
all commands exited 0
```

## Safety review

- Every review contract and validation result carries
  `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.
- No order, cancel, trade, broker, account-mutation, network, filesystem, or
  execution capability was added.
- Fixtures contain toy/offline review data only; no personal trading records,
  credentials, account identifiers, or real local paths were added.
- Redaction validation rejects sensitive keyed values, raw aliases, embedded or
  declared attachment material, local-path/credential patterns, and exact
  quantities, amounts, timestamps, and dates.
- Every non-silent observation requires invalidation, time stop, give-up
  conditions, source, available time, and data quality.
- `available_at > decision_time` fails with stable `future_leakage` metadata.
- Rule proposals must remain challengers and cannot claim champion or core-rule
  mutation.

## Unresolved issues

No Task 1 issue remains. Two pre-existing dirty GUI findings are outside Task 1
ownership and were not edited or staged: trailing whitespace in
`gui/src/views/PluginsView.tsx`, and an HTML credential input in the generated web
bundle that makes the final unscoped `./scripts/verify.sh` safety grep exit 1.
Doctor, all tests, and the Task 1-scoped safety/whitespace gate pass on the final
tree.
