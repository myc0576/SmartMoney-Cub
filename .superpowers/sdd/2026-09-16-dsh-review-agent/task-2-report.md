# Task 2 Implementation Report: Provider Route Chain and Failure Classification

## Files Changed and Created
- **Created**:
  - `src/smartmoney_cub_harness/agent/provider_errors.py`: Failure classification, stable `ProviderErrorCode` constants, `FailurePhase` enum, `ClassifiedProviderError` with actionable remediation, portal URL, candidate recovery suggestions, and safe diagnostics with credential redaction.
  - `src/smartmoney_cub_harness/agent/route_chain.py`: `RouteCandidate`, `CooldownTracker` for backoff and failure tracking, `RouteChainPolicy` with bounded retries, and `stream_chat_with_route_chain` supporting multi-candidate fallback and offline candidate routing.
  - `tests/test_provider_route_chain.py`: Comprehensive offline mock HTTP test suite covering 403 quota exhaustion, 429 rate limit vs quota, 5xx server error, timeout, 401 authentication, 400 invalid request, pre-stream vs mid-stream disconnection, bounded same-target retries with cooldowns, fallback to offline candidate, and credential redaction in safe diagnostics.
- **Modified**:
  - `src/smartmoney_cub_harness/agent/providers.py`: Re-exported and integrated error classification in `_open` and `stream_chat`, added offline protocol support to `stream_chat`, and added detection of premature stream termination without completion tokens.
  - `src/smartmoney_cub_harness/agent/__init__.py`: Exported provider error classification and route chain types for downstream runtime use.

## Scope Rulings Honored
- Owned only provider route/error modules and their tests.
- Did not touch review contracts, DSH bridge, Workbench server, or GUI files.
- Maintained write-only credential semantics: secrets are strictly redacted via `smartmoney_cub_harness.safety` before diagnostics/serialization.
- Preserved `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` declaration.

## TDD Verification Evidence

### RED Phase
**Command**:
```bash
python3 -m pytest tests/test_provider_route_chain.py -q
```
**Output**:
```
==================================== ERRORS ====================================
_____________ ERROR collecting tests/test_provider_route_chain.py ______________
ImportError while importing test module '/private/tmp/smartmoney-cub-dsh-review-agent/tests/test_provider_route_chain.py'.
Traceback:
tests/test_provider_route_chain.py:11: in <module>
    from smartmoney_cub_harness.agent.provider_errors import (
E   ModuleNotFoundError: No module named 'smartmoney_cub_harness.agent.provider_errors'
=========================== short test summary info ============================
ERROR tests/test_provider_route_chain.py
1 error in 0.09s
```

### GREEN Phase
**Command**:
```bash
python3 -m pytest tests/test_provider_route_chain.py tests/test_model_providers.py tests/test_agent_tool_rounds.py -v
```
**Output**:
```
============================== 52 passed in 3.77s ==============================
```

### Safety Doctor Check
**Command**:
```bash
python3 -m smartmoney_cub_harness.cli doctor
```
**Output**:
```json
{
  "status": "ok",
  "package": "smartmoney-cub-harness",
  "version": "1.0.0",
  "network_required": false,
  "execution_integrations": "disabled",
  "safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
}
```

## 403 Quota Screenshot Case Resolution
The raw 403 error is now parsed and classified as `ProviderErrorCode.INSUFFICIENT_QUOTA`:
- Instead of an uninformative raw error string, it returns a structured `ClassifiedProviderError` containing:
  - `error_code`: `"insufficient_quota"`
  - `portal_url`: `"https://alphatech.net.cn"` (or configured portal)
  - `action_suggestion`: Actionable guidance to recharge or switch models
  - `recovery_suggestions`: Actions including recharge portal link, model switch, and offline rule fallback
  - `safe_diagnostics`: Sanitized diagnostic payload with credentials safely redacted
  - `retryable_same_target`: `False` (avoids repeated doomed calls)
  - `fallbackable`: `True` (allows automatic or user-guided route chain fallback)

## Pre-Stream vs Mid-Stream Behavior
- **Pre-stream failure**: Request failed before producing deltas. Evaluated for bounded same-target retry (if transient 5xx/429/timeout) or route chain fallback.
- **Mid-stream failure**: Partial chunks were already delivered to the caller. Classified as `ProviderErrorCode.STREAM_INTERRUPTION` with `FailurePhase.MID_STREAM`. Does not silently replay duplicate tokens from scratch to prevent transcript corruption.

## Unresolved Issues
None. All tests pass with zero regressions across provider and agent suites, and all frozen DoD criteria are verified with fresh execution evidence.



---

## Task 2 Review Fix Report

### Issues Addressed
1. **Opaque Credential Redaction & RouteCandidate Representation**:
   - Implemented `_collect_provider_secrets()` and `_redact_all()` in `provider_errors.py` to identify any arbitrary or opaque secret string passed in provider configurations and redact it from raw messages, sanitized details, and `safe_diagnostics` / `to_dict()`.
   - Set `repr=False` on `RouteCandidate.api_key` in `route_chain.py` so credentials are not representable.
   - Added test `test_opaque_token_redacted_from_diagnostics_and_candidate_repr`.

2. **Preserve `portal_url` & Emit Structured Error in Runtime**:
   - Updated `resolve_provider()` in `providers.py` to preserve `portal_url` from the catalog/entry through resolution.
   - Updated `ReviewAgentRuntime.run_turn()` in `runtime.py` to recognize `ClassifiedProviderError`, emit `classified` structured data in the streamed error event, and record the structured error payload in the store.
   - Added tests `test_resolve_provider_preserves_portal_url` and `test_runtime_emits_structured_classified_error`.

3. **Opening Timeout Classification**:
   - Extended `_open()` in `providers.py` to catch `socket.timeout` and `TimeoutError`, and wrapped `_open()` call within `stream_chat()` to classify opening connection timeouts as pre-stream `ClassifiedProviderError`.
   - Added test `test_open_socket_timeout_classified_through_stream_chat`.

4. **HTTP 408/504 Classified as Timeout Before 5xx**:
   - Reordered classification checks in `provider_errors.py` so that HTTP 408 / 504 are classified as `ProviderErrorCode.TIMEOUT` rather than generic 5xx server errors.
   - Added test `test_http_504_and_408_classified_as_timeout`.

5. **Cooldown Candidate Exclusion and Stable Retry-After**:
   - Updated `stream_chat_with_route_chain()` in `route_chain.py` to exclude candidates in active cooldown. When all candidates are cooling down, it raises a stable 429 `rate_limited` error with `retry_after` seconds calculated from the minimum remaining cooldown time, bypassing network calls completely.
   - Added test `test_cooldown_excludes_candidate_and_returns_retry_after`.

6. **Authentication and Invalid Request Fallbackability**:
   - Configured `fallbackable = True` for both `AUTHENTICATION` and `INVALID_REQUEST` in `provider_errors.py` while keeping `retryable_same_target = False`, allowing routes to fall back to alternative candidates or offline review.
   - Added test `test_auth_and_invalid_request_fallback_to_next_candidate`.

7. **HTTP Status Parser Regex Fix**:
   - Fixed regex in `_extract_http_status_and_body()` from `HTTPs+(\d{3})` to `r"HTTP\s+(\d{3})"`.
   - Added test `test_http_status_parsed_from_provider_error_message`.

### Fresh TDD Verification Evidence

#### RED Output (Covering All 8 Review Tests)
```
tests/test_provider_route_chain.py::test_opaque_token_redacted_from_diagnostics_and_candidate_repr FAILED [ 12%]
tests/test_provider_route_chain.py::test_resolve_provider_preserves_portal_url FAILED [ 25%]
tests/test_provider_route_chain.py::test_runtime_emits_structured_classified_error FAILED [ 37%]
tests/test_provider_route_chain.py::test_open_socket_timeout_classified_through_stream_chat FAILED [ 50%]
tests/test_provider_route_chain.py::test_http_504_and_408_classified_as_timeout FAILED [ 62%]
tests/test_provider_route_chain.py::test_cooldown_excludes_candidate_and_returns_retry_after FAILED [ 75%]
tests/test_provider_route_chain.py::test_auth_and_invalid_request_fallback_to_next_candidate FAILED [ 87%]
tests/test_provider_route_chain.py::test_http_status_parsed_from_provider_error_message FAILED [100%]
======================= 8 failed, 10 deselected in 1.26s =======================
```

#### GREEN Output (All 18 Tests in Route Chain Suite Passing)
**Command**:
```bash
python3 -m pytest tests/test_provider_route_chain.py -v
```
**Output**:
```
tests/test_provider_route_chain.py::test_error_classification_quota_403 PASSED [  5%]
tests/test_provider_route_chain.py::test_error_classification_rate_limit_429 PASSED [ 11%]
tests/test_provider_route_chain.py::test_error_classification_server_error_5xx PASSED [ 16%]
tests/test_provider_route_chain.py::test_error_classification_timeout PASSED [ 22%]
tests/test_provider_route_chain.py::test_error_classification_auth_401 PASSED [ 27%]
tests/test_provider_route_chain.py::test_error_classification_invalid_request_400 PASSED [ 33%]
tests/test_provider_route_chain.py::test_403_quota_actionable_result PASSED [ 38%]
tests/test_provider_route_chain.py::test_pre_stream_vs_mid_stream PASSED [ 44%]
tests/test_provider_route_chain.py::test_route_chain_retries_cooldown_and_fallback PASSED [ 50%]
tests/test_provider_route_chain.py::test_safe_diagnostics_redacts_credentials PASSED [ 55%]
tests/test_provider_route_chain.py::test_opaque_token_redacted_from_diagnostics_and_candidate_repr PASSED [ 61%]
tests/test_provider_route_chain.py::test_resolve_provider_preserves_portal_url PASSED [ 66%]
tests/test_provider_route_chain.py::test_runtime_emits_structured_classified_error PASSED [ 72%]
tests/test_provider_route_chain.py::test_open_socket_timeout_classified_through_stream_chat PASSED [ 77%]
tests/test_provider_route_chain.py::test_http_504_and_408_classified_as_timeout PASSED [ 83%]
tests/test_provider_route_chain.py::test_cooldown_excludes_candidate_and_returns_retry_after PASSED [ 88%]
tests/test_provider_route_chain.py::test_auth_and_invalid_request_fallback_to_next_candidate PASSED [ 94%]
tests/test_provider_route_chain.py::test_http_status_parsed_from_provider_error_message PASSED [100%]
============================== 18 passed in 2.75s ==============================
```

#### Full Regressions Suite Check
**Command**:
```bash
python3 -m pytest tests/test_provider_route_chain.py tests/test_model_providers.py tests/test_agent_tool_rounds.py tests/test_workbench_service.py -q
```
**Output**:
```
82 passed in 7.06s
```

#### Doctor Verification
**Command**:
```bash
python3 -m smartmoney_cub_harness.cli doctor
```
**Output**:
```json
{
  "status": "ok",
  "package": "smartmoney-cub-harness",
  "version": "1.0.0",
  "safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
}
```



---

## Task 2 Re-Review Fix Report (Round 2)

### Critical Finding Resolved
- **Full Serialization Boundary Scrub in `ClassifiedProviderError.to_dict()`**:
  - Previously, `portal_url`, `recovery_suggestions`, and `action_suggestion` were stored directly without scrubbing against `extra_secrets`, and `to_dict()` did not apply a final scrub across all dictionary fields.
  - Updated `ClassifiedProviderError.__init__()` in `provider_errors.py` to retain `self.extra_secrets` and scrub `portal_url`, `action_suggestion`, and `recovery_suggestions` using `_redact_all()`.
  - Updated `ClassifiedProviderError.to_dict()` to apply `_redact_all()` over the entire serialized dictionary, guaranteeing that every string in every serialized field (including URLs, query strings, action descriptions, recovery targets, and nested diagnostic payloads) is scrubbed against the complete known provider secret set.
  - Added regression test `test_opaque_token_scrubbed_from_all_serialized_fields_including_portal_and_recovery` in `tests/test_provider_route_chain.py`.

### Fresh TDD Verification Evidence

#### RED Output
```
tests/test_provider_route_chain.py::test_opaque_token_scrubbed_from_all_serialized_fields_including_portal_and_recovery FAILED [100%]

=================================== FAILURES ===================================
_ test_opaque_token_scrubbed_from_all_serialized_fields_including_portal_and_recovery _
AssertionError: assert 'opaque_secret_in_portal_and_recovery_887766' not in 'https://portal.example.com/login?token=opaque_secret_in_portal_and_recovery_887766'
======================= 1 failed, 18 deselected in 0.07s =======================
```

#### GREEN Output (Route Chain Suite: 19 Tests Passing)
**Command**:
```bash
python3 -m pytest tests/test_provider_route_chain.py -v
```
**Output**:
```
tests/test_provider_route_chain.py::test_error_classification_quota_403 PASSED [  5%]
tests/test_provider_route_chain.py::test_error_classification_rate_limit_429 PASSED [ 10%]
tests/test_provider_route_chain.py::test_error_classification_server_error_5xx PASSED [ 15%]
tests/test_provider_route_chain.py::test_error_classification_timeout PASSED [ 21%]
tests/test_provider_route_chain.py::test_error_classification_auth_401 PASSED [ 26%]
tests/test_provider_route_chain.py::test_error_classification_invalid_request_400 PASSED [ 31%]
tests/test_provider_route_chain.py::test_403_quota_actionable_result PASSED [ 36%]
tests/test_provider_route_chain.py::test_pre_stream_vs_mid_stream PASSED [ 42%]
tests/test_provider_route_chain.py::test_route_chain_retries_cooldown_and_fallback PASSED [ 47%]
tests/test_provider_route_chain.py::test_safe_diagnostics_redacts_credentials PASSED [ 52%]
tests/test_provider_route_chain.py::test_opaque_token_redacted_from_diagnostics_and_candidate_repr PASSED [ 57%]
tests/test_provider_route_chain.py::test_resolve_provider_preserves_portal_url PASSED [ 63%]
tests/test_provider_route_chain.py::test_runtime_emits_structured_classified_error PASSED [ 68%]
tests/test_provider_route_chain.py::test_open_socket_timeout_classified_through_stream_chat PASSED [ 73%]
tests/test_provider_route_chain.py::test_http_504_and_408_classified_as_timeout PASSED [ 78%]
tests/test_provider_route_chain.py::test_cooldown_excludes_candidate_and_returns_retry_after PASSED [ 84%]
tests/test_provider_route_chain.py::test_auth_and_invalid_request_fallback_to_next_candidate PASSED [ 89%]
tests/test_provider_route_chain.py::test_http_status_parsed_from_provider_error_message PASSED [ 94%]
tests/test_provider_route_chain.py::test_opaque_token_scrubbed_from_all_serialized_fields_including_portal_and_recovery PASSED [100%]
============================== 19 passed in 2.60s ==============================
```

#### Regressions Suite Check (83 Tests Passing)
**Command**:
```bash
python3 -m pytest tests/test_provider_route_chain.py tests/test_model_providers.py tests/test_agent_tool_rounds.py tests/test_workbench_service.py -q
```
**Output**:
```
83 passed in 7.08s
```

#### Doctor Verification
**Command**:
```bash
python3 -m smartmoney_cub_harness.cli doctor
```
**Output**:
```json
{
  "status": "ok",
  "package": "smartmoney-cub-harness",
  "version": "1.0.0",
  "safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
}
```



---

## Task 2 Re-Review Fix Report (Round 3)

### Critical Finding Resolved
- **Zero Plaintext Secret Retention on Exception Instance**:
  - Identified that storing `self.extra_secrets` on `ClassifiedProviderError` exposed raw plaintext credentials to ordinary inspection via `vars(error)`.
  - Removed `self.extra_secrets` from `ClassifiedProviderError` completely.
  - In `ClassifiedProviderError.__init__()`, all instance attributes (`self.message`, `self.raw_message`, `self.portal_url`, `self.action_suggestion`, `self.recovery_suggestions`, `self.safe_diagnostics`) are immutably sanitized with `_redact_all(..., secrets)` during initialization, and the secret collection is discarded without being attached to `self`.
  - Verified `to_dict()` returns the pre-sanitized attributes directly with zero raw secrets accessible.
  - Added regression test `test_exception_instance_does_not_store_plaintext_secrets_in_vars_or_repr` asserting that `vars(error)`, `repr(error)`, and `str(error)` never contain the opaque secret while `portal_url`, `recovery_suggestions`, and `safe_diagnostics` remain sanitized.

### Fresh TDD Verification Evidence

#### RED Output
```
tests/test_provider_route_chain.py::test_exception_instance_does_not_store_plaintext_secrets_in_vars_or_repr FAILED [100%]

=================================== FAILURES ===================================
___ test_exception_instance_does_not_store_plaintext_secrets_in_vars_or_repr ___
AssertionError: assert 'opaque_token_never_in_vars_77665544' not in '{"extra_secrets": "{'opaque_token_never_in_vars_77665544'}", ...}'
======================= 1 failed, 19 deselected in 0.06s =======================
```

#### GREEN Output (Route Chain Suite: 20 Tests Passing)
**Command**:
```bash
python3 -m pytest tests/test_provider_route_chain.py -v
```
**Output**:
```
tests/test_provider_route_chain.py::test_error_classification_quota_403 PASSED [  5%]
tests/test_provider_route_chain.py::test_error_classification_rate_limit_429 PASSED [ 10%]
tests/test_provider_route_chain.py::test_error_classification_server_error_5xx PASSED [ 15%]
tests/test_provider_route_chain.py::test_error_classification_timeout PASSED [ 20%]
tests/test_provider_route_chain.py::test_error_classification_auth_401 PASSED [ 25%]
tests/test_provider_route_chain.py::test_error_classification_invalid_request_400 PASSED [ 30%]
tests/test_provider_route_chain.py::test_403_quota_actionable_result PASSED [ 35%]
tests/test_provider_route_chain.py::test_pre_stream_vs_mid_stream PASSED [ 40%]
tests/test_provider_route_chain.py::test_route_chain_retries_cooldown_and_fallback PASSED [ 45%]
tests/test_provider_route_chain.py::test_safe_diagnostics_redacts_credentials PASSED [ 50%]
tests/test_provider_route_chain.py::test_opaque_token_redacted_from_diagnostics_and_candidate_repr PASSED [ 55%]
tests/test_provider_route_chain.py::test_resolve_provider_preserves_portal_url PASSED [ 60%]
tests/test_provider_route_chain.py::test_runtime_emits_structured_classified_error PASSED [ 65%]
tests/test_provider_route_chain.py::test_open_socket_timeout_classified_through_stream_chat PASSED [ 70%]
tests/test_provider_route_chain.py::test_http_504_and_408_classified_as_timeout PASSED [ 75%]
tests/test_provider_route_chain.py::test_cooldown_excludes_candidate_and_returns_retry_after PASSED [ 80%]
tests/test_provider_route_chain.py::test_auth_and_invalid_request_fallback_to_next_candidate PASSED [ 85%]
tests/test_provider_route_chain.py::test_http_status_parsed_from_provider_error_message PASSED [ 90%]
tests/test_provider_route_chain.py::test_opaque_token_scrubbed_from_all_serialized_fields_including_portal_and_recovery PASSED [ 95%]
tests/test_provider_route_chain.py::test_exception_instance_does_not_store_plaintext_secrets_in_vars_or_repr PASSED [100%]
============================== 20 passed in 2.70s ==============================
```

#### Regressions Suite Check (84 Tests Passing)
**Command**:
```bash
python3 -m pytest tests/test_provider_route_chain.py tests/test_model_providers.py tests/test_agent_tool_rounds.py tests/test_workbench_service.py -q
```
**Output**:
```
84 passed in 7.02s
```

#### Doctor Verification
**Command**:
```bash
python3 -m smartmoney_cub_harness.cli doctor
```
**Output**:
```json
{
  "status": "ok",
  "package": "smartmoney-cub-harness",
  "version": "1.0.0",
  "safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
}
```



---

## Task 2 Re-Review Fix Report (Round 4)

### Scope and frozen acceptance criteria

Goal: remove plaintext provider credentials from retained classified-error data at construction, including duplicated identifiers, while preserving useful diagnostics and route behavior. Maximum: five implementation/verification iterations; this round used two.

- [x] Reproduce the leak across exception attributes and serialization using an opaque offline fixture (focused RED below).
- [x] Sanitize the complete exception payload before storage without retaining the secret set; preserve safe diagnostics and routing semantics (focused assertions and related suite below).
- [x] Pass the focused regression, related provider tests, full test suite, and safety doctor (fresh command outputs below).
- [x] Append fresh RED/GREEN evidence to this report; limit the change set to Task 2 provider modules, tests, and this report.

Excluded: review contracts, DSH bridge, Workbench server, GUI, and unrelated existing worktree edits. All new credentials are toy offline fixtures. Safety contract: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

### Root cause and final design

The round-3 constructor scrubbed selected fields individually but retained `provider_id`, `model`, `code`, and `phase` verbatim. Removing the retained secret set also removed the serialization fallback. Thus an opaque credential copied into metadata survived both object inspection and `to_dict()`. Nested diagnostic keys and tuples also bypassed known-secret scrubbing, and arbitrary diagnostic objects could retain raw upstream errors.

The constructor now assembles the complete declared payload, sanitizes every value before assigning any instance state, and initializes `RuntimeError.args` from the sanitized message. Known secrets remain construction-only inputs. Fixed attribute names remain intact; untrusted nested keys are scrubbed. Redaction copies dictionaries/lists/tuples, sanitizes unknown diagnostic objects to text, and retains safe scalar diagnostics. `to_dict()` uses this sanitized state without a stored secret set.

Provider opening and stream-read handlers also previously chained the raw upstream exception through `__cause__` and `__context__`. They now construct the classified error inside the handler and raise it after leaving the handler, retaining sanitized diagnostic text without attaching the raw exception. The new opening-error tests exposed a missing `socket` import, which is restored so timeout classification works.

### Files changed

- `src/smartmoney_cub_harness/agent/provider_errors.py`: complete construction-time sanitization, nested key/tuple coverage, safe diagnostic-object normalization.
- `src/smartmoney_cub_harness/agent/providers.py`: prevent retention of raw upstream exception chains; restore the socket import.
- `tests/test_provider_route_chain.py`: eight focused cases covering direct construction, classification, every public non-callable attribute (including `args`), `vars`, `repr`, `str`, dictionary/JSON serialization, nested diagnostics, input aliasing, and upstream exception chains.
- This Task 2 report.

### RED — before production changes

Command:
```bash
PYTHONPATH=src python3 -m pytest tests/test_provider_route_chain.py -q -k opaque_credential --tb=short
```

Exit code: 1. Captured output below, with trailing terminal whitespace omitted:
```text
FFFFFFFF                                                                 [100%]
=================================== FAILURES ===================================
____ test_opaque_credential_absent_from_all_exception_surfaces[classifier] _____
tests/test_provider_route_chain.py:666: in test_opaque_credential_absent_from_all_exception_surfaces
    _assert_no_credential_on_error(error, secret)
tests/test_provider_route_chain.py:629: in _assert_no_credential_on_error
    assert leaked_surfaces == []
E   AssertionError: assert ['model', 'pr... 'serialized'] == []
E
E     Left contains 4 more items, first extra item: 'model'
E     Use -v to get more diff
____ test_opaque_credential_absent_from_all_exception_surfaces[constructor] ____
tests/test_provider_route_chain.py:666: in test_opaque_credential_absent_from_all_exception_surfaces
    _assert_no_credential_on_error(error, secret)
tests/test_provider_route_chain.py:629: in _assert_no_credential_on_error
    assert leaked_surfaces == []
E   AssertionError: assert ['model', 'pr... 'serialized'] == []
E
E     Left contains 4 more items, first extra item: 'model'
E     Use -v to get more diff
______ test_opaque_credential_scrubbed_from_complete_constructor_payload _______
tests/test_provider_route_chain.py:699: in test_opaque_credential_scrubbed_from_complete_constructor_payload
    _assert_no_credential_on_error(error, secret)
tests/test_provider_route_chain.py:629: in _assert_no_credential_on_error
    assert leaked_surfaces == []
E   AssertionError: assert ['code', 'pha... 'serialized'] == []
E
E     Left contains 6 more items, first extra item: 'code'
E     Use -v to get more diff
_ test_opaque_credential_not_retained_in_upstream_exception_chain[http_open-insufficient_quota] _
tests/test_provider_route_chain.py:763: in test_opaque_credential_not_retained_in_upstream_exception_chain
    _assert_no_credential_on_error(error, secret)
tests/test_provider_route_chain.py:629: in _assert_no_credential_on_error
    assert leaked_surfaces == []
E   AssertionError: assert ['cause', 'context'] == []
E
E     Left contains 2 more items, first extra item: 'cause'
E     Use -v to get more diff
_ test_opaque_credential_not_retained_in_upstream_exception_chain[url_open-network_unreachable] _
tests/test_provider_route_chain.py:763: in test_opaque_credential_not_retained_in_upstream_exception_chain
    _assert_no_credential_on_error(error, secret)
tests/test_provider_route_chain.py:629: in _assert_no_credential_on_error
    assert leaked_surfaces == []
E   AssertionError: assert ['cause', 'context'] == []
E
E     Left contains 2 more items, first extra item: 'cause'
E     Use -v to get more diff
_ test_opaque_credential_not_retained_in_upstream_exception_chain[timeout_open-timeout] _
tests/test_provider_route_chain.py:764: in test_opaque_credential_not_retained_in_upstream_exception_chain
    assert error.__cause__ is None
E   assert NameError("name 'socket' is not defined") is None
E    +  where NameError("name 'socket' is not defined") = ClassifiedProviderError("模型服务调用失败: name 'socket' is not defined").__cause__
_ test_opaque_credential_not_retained_in_upstream_exception_chain[unexpected_open-unknown_error] _
tests/test_provider_route_chain.py:764: in test_opaque_credential_not_retained_in_upstream_exception_chain
    assert error.__cause__ is None
E   assert NameError("name 'socket' is not defined") is None
E    +  where NameError("name 'socket' is not defined") = ClassifiedProviderError("模型服务调用失败: name 'socket' is not defined").__cause__
_ test_opaque_credential_not_retained_in_upstream_exception_chain[stream_read-stream_interruption] _
tests/test_provider_route_chain.py:763: in test_opaque_credential_not_retained_in_upstream_exception_chain
    _assert_no_credential_on_error(error, secret)
tests/test_provider_route_chain.py:629: in _assert_no_credential_on_error
    assert leaked_surfaces == []
E   AssertionError: assert ['cause', 'context'] == []
E
E     Left contains 2 more items, first extra item: 'cause'
E     Use -v to get more diff
=========================== short test summary info ============================
FAILED tests/test_provider_route_chain.py::test_opaque_credential_absent_from_all_exception_surfaces[classifier]
FAILED tests/test_provider_route_chain.py::test_opaque_credential_absent_from_all_exception_surfaces[constructor]
FAILED tests/test_provider_route_chain.py::test_opaque_credential_scrubbed_from_complete_constructor_payload
FAILED tests/test_provider_route_chain.py::test_opaque_credential_not_retained_in_upstream_exception_chain[http_open-insufficient_quota]
FAILED tests/test_provider_route_chain.py::test_opaque_credential_not_retained_in_upstream_exception_chain[url_open-network_unreachable]
FAILED tests/test_provider_route_chain.py::test_opaque_credential_not_retained_in_upstream_exception_chain[timeout_open-timeout]
FAILED tests/test_provider_route_chain.py::test_opaque_credential_not_retained_in_upstream_exception_chain[unexpected_open-unknown_error]
FAILED tests/test_provider_route_chain.py::test_opaque_credential_not_retained_in_upstream_exception_chain[stream_read-stream_interruption]
8 failed, 20 deselected in 0.13s
```

The identifier cases fail on leaked metadata, the complete-payload case fails on other retained strings/nested diagnostics, and the upstream cases expose raw exception chaining. Timeout and unexpected opening failures also expose the missing socket import.

### Intermediate verification finding and correction

After the first implementation, all eight focused cases passed, but the related suite caught an additional route regression. Passing the entire attribute dictionary through key redaction allowed the existing one-character toy credential to alter the fixed `fallbackable` attribute name. The correction preserves trusted schema names and sanitizes every attribute value, while continuing to scrub upstream diagnostic keys. No existing tests or assertions were relaxed.

Command:
```bash
PYTHONPATH=src python3 -m pytest tests/test_provider_route_chain.py tests/test_model_providers.py tests/test_agent_tool_rounds.py tests/test_workbench_service.py -q
```

Exit code: 1. Exact failure excerpt and result:
```text
E               AttributeError: 'ClassifiedProviderError' object has no attribute 'fallbackable'

src/smartmoney_cub_harness/agent/route_chain.py:235: AttributeError
=========================== short test summary info ============================
FAILED tests/test_provider_route_chain.py::test_cooldown_excludes_candidate_and_returns_retry_after
1 failed, 91 passed in 7.13s
```

### GREEN — final focused regression

Command:
```bash
PYTHONPATH=src python3 -m pytest tests/test_provider_route_chain.py -q -k opaque_credential --tb=short
```

Exit code: 0. Exact output:
```text
........                                                                 [100%]
8 passed, 20 deselected in 0.03s
```

### GREEN — related providers, route chain, runtime, and Workbench regression tests

Command:
```bash
PYTHONPATH=src python3 -m pytest tests/test_provider_route_chain.py tests/test_model_providers.py tests/test_agent_tool_rounds.py tests/test_workbench_service.py -q --tb=short
```

Exit code: 0. Exact output:
```text
........................................................................ [ 78%]
....................                                                     [100%]
92 passed in 7.12s
```

The tests retain actionable quota recovery and portal redaction, stable classification, bounded retries, cooldown exclusion, offline fallback, and pre-stream versus mid-stream behavior. The new interrupted-stream case verifies partial output is delivered once and the classified interruption remains non-retryable and non-fallbackable.

### Full verification gate

Used the repository-authorized doctor plus full pytest alternative to `scripts/verify.sh`. `PYTHONPATH=src` ensures this checkout's code is tested.

Syntax/compilation:
```bash
PYTHONPATH=src python3 -m compileall -q src/smartmoney_cub_harness/agent/provider_errors.py src/smartmoney_cub_harness/agent/providers.py tests/test_provider_route_chain.py
```
Exit code: 0; no output.

Doctor:
```bash
PYTHONPATH=src python3 -m smartmoney_cub_harness.cli doctor
```
Exit code: 0. Exact output:
```json
{
  "status": "ok",
  "package": "smartmoney-cub-harness",
  "version": "1.0.0",
  "python": "3.12.14",
  "platform": "macOS-26.6.2-arm64-arm-64bit",
  "cwd": "[REDACTED]",
  "network_required": false,
  "telemetry": false,
  "upload": false,
  "credentials_required": false,
  "github_auth_required": false,
  "external_api_required": false,
  "broker_api_required": false,
  "execution_integrations": "disabled",
  "default_data_mode": "offline_json_fixtures",
  "market_data_mode": "offline",
  "tenant_mode": "local_single_user",
  "launcher": {
    "launcher_found": false,
    "launcher_count": 0,
    "multiple_launchers": false,
    "resolved_to_current_environment": false
  },
  "safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
}
```

Full test suite:
```bash
PYTHONPATH=src python3 -m pytest tests/ -q --tb=short
```
Exit code: 0. Exact output:
```text
........................................................................ [  9%]
........................................................................ [ 18%]
........................................................................ [ 27%]
........................................................................ [ 36%]
........................................................................ [ 45%]
........................................................................ [ 54%]
........................................................................ [ 63%]
........................................................................ [ 72%]
........................................................................ [ 81%]
............................................ssss........................ [ 90%]
...........ss........................................................... [ 99%]
..                                                                       [100%]
788 passed, 6 skipped in 25.94s
```

The six skipped tests are reported explicitly; there were no test failures or errors. The full suite ran against the shared checkout, including its pre-existing unrelated edits.

Task-scoped whitespace check:
```bash
git diff --check -- src/smartmoney_cub_harness/agent/provider_errors.py src/smartmoney_cub_harness/agent/providers.py tests/test_provider_route_chain.py .superpowers/sdd/2026-09-16-dsh-review-agent/task-2-report.md
```
Exit code: 0; no output.
