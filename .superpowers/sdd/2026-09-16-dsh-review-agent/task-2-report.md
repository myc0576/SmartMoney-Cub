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

