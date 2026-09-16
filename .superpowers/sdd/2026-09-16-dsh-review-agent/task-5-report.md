# Task 5 implementation report — finance catalog and Cordis adapters

## Scope

Added a metadata-only SmartMoney curated finance catalog and a typed Cordis
adapter boundary. The catalog records source/version/commit/license, declared
network and permissions, lifecycle state, health, and explicit profile reload
events. It never fetches, imports, or executes upstream repositories.

Two deterministic toy adapters are included:

- TradingAgents-style multi-role evidence (fundamental, technical, risk).
- Evaluator/memory/challenger evidence.

Both accept only a validated Task 1 redacted envelope, emit point-in-time toy
evidence, and validate challenger proposals before returning. Champion mutation
is never performed by an adapter; explicit human confirmation returns an
authorization handoff only.

## Files

- `src/smartmoney_cub_harness/plugins/curated_catalog.py`
- `src/smartmoney_cub_harness/plugins/cordis_adapters.py`
- `src/smartmoney_cub_harness/plugins/__init__.py`
- `tests/test_curated_finance_plugins.py`

## Verification

Focused/related tests: `78 passed` across curated finance plugins, plugin
foundation/CLI, and Workbench service tests. The adapters run with toy offline
fixtures only. All responses preserve
`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

## Residual risk

The curated in-memory state machine is not yet persisted in the Workbench's
SQLite session event stream. Task 4 must connect catalog profile-reload events
and plugin results to the durable lifecycle without passing raw journal data or
credentials.
