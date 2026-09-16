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

