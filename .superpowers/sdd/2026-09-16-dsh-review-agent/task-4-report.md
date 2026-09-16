# Task 4 implementation report — durable review lifecycle

## Scope

Extended the existing SQLite-backed Workbench lifecycle without changing the
legacy session/event schema. Running or cancel-requested sessions are marked
`interrupted` on a new service process and receive a durable recovery event;
the existing `after_seq` cursor remains the replay mechanism.

The runtime now records typed lifecycle events for turn start, provider attempt,
review scope preview/confirmation, sidecar connection, synthesis completion,
terminal state, cancellation, resume, and challenger proposal. It can build a
versioned `RedactedReviewEnvelope` from the local context and validates the
redacted payload before it is eligible for a DSH handshake. A supplied sidecar
is opt-in; the default Workbench path remains the Python/offline-compatible
runtime.

Server routes added:

- `GET /api/assistant/sessions/{id}/review/scope`
- `POST /api/assistant/sessions/{id}/review/scope`
- `POST /api/assistant/sessions/{id}/review/confirm`
- `POST /api/assistant/sessions/{id}/cancel`
- `POST /api/assistant/sessions/{id}/resume` (SSE)
- `POST /api/assistant/sessions/{id}/review/challenger`

## Files

- `src/smartmoney_cub_harness/store.py`
- `src/smartmoney_cub_harness/agent/runtime.py`
- `src/smartmoney_cub_harness/workbench/server.py`
- `tests/test_workbench_service.py`

## Verification

Focused lifecycle/bridge/agent tests: `34 passed`.

Scope preview and confirmation use a toy local context, cancellation is
review-turn-only, resume reads the durable transcript, and restart recovery is
asserted against SQLite. All lifecycle payloads carry
`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

## Residual risk

The DSH bridge is injectable but not automatically spawned; deployment wiring
must explicitly supply a local sidecar transport. A real provider stream cannot
be force-killed mid-socket read, so cancellation is cooperative and persists a
recoverable state at the next event boundary.
