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

## Task 1 review-fix addendum

### Review findings resolved

- Review-package scope is now the authoritative decision time. Plugin-result
  validation rejects disagreement from the caller or redacted-envelope scope
  and uses the authoritative time for observation/evidence leakage checks.
- Redaction rejects numeric or malformed symbol/portfolio aliases and original
  CSV/file field variants.
- Direct construction of review scope, envelope, evidence, package, or plugin
  result now enforces the safety declaration through the same invariant as
  deserialization.
- Challenger proposals reject extra promotion/champion/mutation-shaped fields
  while retaining extensible ordinary review metadata.
- A v1 plugin-result fixture now proves alias normalization into the unchanged
  current v2 wire contract.

### Fresh RED evidence

Command:

```text
python -m pytest tests/test_review_contracts.py -q
```

Observed output and exit status before production changes:

```text
16 failed, 30 passed in 0.12s
exit code 1
```

The 16 failures reproduced the two decision-time trust errors, four invalid
alias cases, four original-file cases, five direct-construction safety bypasses,
and one hidden promotion field. The v1 plugin-result compatibility
characterization was already readable and remained green.

### Incremental GREEN evidence

Authoritative decision time:

```text
python -m pytest tests/test_review_contracts.py::test_plugin_result_uses_package_scope_time_and_rejects_caller_disagreement tests/test_review_contracts.py::test_plugin_result_rejects_envelope_scope_time_disagreement -q
2 passed in 0.03s
exit code 0
```

Redaction aliases and original files:

```text
python -m pytest tests/test_review_contracts.py::test_redaction_validator_requires_valid_aliases_regardless_of_value_type tests/test_review_contracts.py::test_redaction_validator_rejects_original_file_fields -q
8 passed in 0.03s
exit code 0
```

Typed safety invariants:

```text
python -m pytest tests/test_review_contracts.py::test_typed_contract_construction_rejects_tampered_safety -q
5 passed in 0.02s
exit code 0
```

Challenger-only mutation:

```text
python -m pytest tests/test_review_contracts.py::test_challenger_validation_rejects_hidden_promotion_field -q
1 passed in 0.03s
exit code 0
```

V1 plugin-result normalization:

```text
python -m pytest tests/test_review_contracts.py::test_v1_plugin_result_normalizes_aliases_to_current_contract -q
1 passed in 0.02s
exit code 0
```

Final focused suite:

```text
python -m pytest tests/test_review_contracts.py -q
46 passed in 0.04s
exit code 0
```

Adjacent contract regression suite:

```text
python -m pytest tests/test_review_contracts.py tests/test_redaction.py tests/test_manifest.py tests/test_plugin_foundation.py tests/test_plugin_schemas.py -q
100 passed in 0.10s
exit code 0
```

### Fresh full verification

Command:

```text
./scripts/verify.sh
```

Observed output and exit status:

```text
Doctor contract check passed.
777 passed, 6 skipped in 26.65s
Safety sanity check passed.
Verification Loop: ALL GATES PASSED
exit code 0
```

Doctor output retained `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`. No provider,
DSH bridge, Workbench server, or GUI file was changed for these fixes.

### Post-report verification refresh

After updating this report, `./scripts/verify.sh` was run again. Its doctor and
test gates passed (`777 passed, 6 skipped in 26.63s`), but its repository-wide
safety scan returned exit code 1 after an unrelated dirty generated GUI bundle
acquired a credential-form marker. That file is outside Task 1 ownership and was
not edited or staged by this task.

The permitted equivalent verification gate was then run against the final code:

```text
python -m smartmoney_cub_harness.cli doctor
status: ok
safety: READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
exit code 0

python -m pytest tests/ -q --tb=short
777 passed, 6 skipped in 26.72s
exit code 0

Task 1 cached-diff safety scan plus git diff --cached --check
Task 1 scoped safety and whitespace checks passed.
exit code 0
```

The scoped gate covers exactly the four authorized Task 1 files and confirms
that no secrets, live-execution terms, or local absolute paths were introduced.

### Unresolved shared-worktree verification issue

A final full-suite rerun after staging this addendum produced a different result
from the two earlier green full-suite runs:

```text
python -m smartmoney_cub_harness.cli doctor
status: ok
safety: READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
exit code 0

python -m pytest tests/ -q --tb=short
FAILED tests/test_provider_route_chain.py::test_exception_instance_does_not_store_plaintext_secrets_in_vars_or_repr
1 failed, 777 passed, 6 skipped in 26.20s
exit code 1
```

The failing provider-route test and its implementation are outside Task 1's
write scope and are part of the pre-existing/concurrent dirty baseline. Task 1
did not modify or stage either file. The final Task 1 suite remained green at
`46 passed in 0.04s`, and the exact staged-diff safety and whitespace checks
passed. This external provider-route failure is the only unresolved issue.

The shared branch then received the concurrent provider fix without any Task 1
edits to provider code. Verification against that updated HEAD was refreshed:

```text
python -m pytest tests/test_review_contracts.py -q
46 passed in 0.04s
exit code 0

python -m smartmoney_cub_harness.cli doctor
status: ok
safety: READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
exit code 0

python -m pytest tests/ -q --tb=short
778 passed, 6 skipped in 25.90s
exit code 0
```

Accordingly, the transient out-of-scope provider failure is resolved by its
own concurrent change. Task 1 has no unresolved issue.

## Task 1 review-fix round 2 addendum

### Review findings addressed

The challenger validator now recursively inspects retained mapping keys and
sequence values for promotion or mutation indicators. Guard exemptions require
the exact raw top-level guard field and the exact value already accepted by the
direct guard validation. Normalized spellings such as `champion-mutated` and
nested metadata are therefore not exempted.

### Fresh RED evidence

Tests were added first and run before the validator change:

```text
python -m pytest tests/test_review_contracts.py::test_plugin_result_rejects_nested_challenger_promotion_metadata tests/test_review_contracts.py::test_plugin_result_rejects_hyphenated_champion_mutation_key -q
2 failed in 0.05s
exit code 1
```

Both failures were the expected `assert checked.ok is False` failures: the
existing shallow validator incorrectly returned `ok=True` for both bypasses.

### Fresh GREEN evidence

After the minimal recursive validator change:

```text
python -m pytest tests/test_review_contracts.py::test_plugin_result_rejects_nested_challenger_promotion_metadata tests/test_review_contracts.py::test_plugin_result_rejects_hyphenated_champion_mutation_key -q
2 passed in 0.02s
exit code 0

python -m pytest tests/test_review_contracts.py -q
48 passed in 0.04s
exit code 0

python -m compileall -q src/smartmoney_cub_harness/review_contracts.py src/smartmoney_cub_harness/review_validation.py
exit code 0

./scripts/verify.sh
Doctor contract check passed.
780 passed, 6 skipped in 25.84s
Safety sanity check passed.
Verification Loop: ALL GATES PASSED
exit code 0
```

The doctor output retained `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.
