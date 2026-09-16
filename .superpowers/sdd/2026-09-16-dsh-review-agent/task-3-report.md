# Task 3 implementation report — DSH sidecar bridge and restricted profile

## Scope

Implemented a versioned, synchronous JSON-RPC/stdio bridge for the optional
DeepSeek Harness sidecar. The Python Workbench remains authoritative; the
bridge accepts only a validated Task 1 `RedactedReviewEnvelope` and exposes
review lifecycle methods.

## Safety boundary

- Profile: `smartmoney-review`, protocol `smartmoney_cub_dsh_stdio.v1`.
- Allowed capabilities are limited to review envelope/events, review
  cancel/resume/fork/close, and heartbeat.
- Shell, arbitrary filesystem, network/web, jobs/workflow, subagent/agent-team,
  broker, order, trade, account, and order-cancel capabilities are rejected.
- The bootstrap helper returns clone/build/web metadata only; it never fetches,
  imports, or executes DSH or an upstream finance project.
- Handshake fails closed for malformed or unredacted envelopes and every
  request/response/error carries `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

## Files

- `src/smartmoney_cub_harness/agent/dsh_bridge.py`
- `src/smartmoney_cub_harness/agent/__init__.py`
- `tests/test_dsh_bridge.py`

## Verification

Focused tests: `4 passed`.

The deterministic `InMemoryDshTransport` covers handshake, profile allowlist,
subscription, heartbeat, cancel/resume/fork/close, envelope rejection, and
crash classification without credentials or network access.

## Residual risk

The production Node/Cordis sidecar process is intentionally not bundled or
launched by this task. Task 4 must connect this transport to Workbench lifecycle
events and persist the sidecar event projection while keeping the Python store
authoritative.

Safety: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`
