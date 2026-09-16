# DSH Review Agent Integration

## Global Constraints

- SQLite and the existing Python Workbench remain the authoritative journal store; DSH is a local runtime and event projection, not a storage migration.
- Every manifest, decision, outcome, doctor result, review envelope, and plugin result carries `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.
- No order placement, cancellation, account modification, broker automation, stock-picking claim, or financial-advice behavior may be added.
- Real personal records, credentials, cookies, account identifiers, screenshots, CSV originals, and local absolute paths must not leave the Python boundary or enter fixtures.
- Any observation with `available_at > decision_time` is rejected; every non-silent observation carries invalidation, time stop, give-up, source, available time, and data quality.
- Rule promotion remains challenger -> champion with explicit human confirmation; no plugin or model may mutate champion directly.
- External finance projects are mounted as Cordis packages inside the DSH sidecar; the sidecar receives only the redacted review envelope and no store handle or credential.
- DSH review profile does not load shell, arbitrary filesystem, web, jobs, workflow, subagent, agent-team, broker, or order capabilities.
- The implementation must preserve existing session/event compatibility and the current hosted Python mode.

## Task 1: Review contracts and validation

Create typed Python contracts for review scope, redacted envelope, evidence, structured review package, plugin result, and stable safety/error metadata. Add validators for redaction, required observation fields, source/time semantics, and challenger-only mutation. Keep legacy payloads readable through explicit schema versions. Write tests first and cover toy offline fixtures only.

Write the implementation report to `.superpowers/sdd/2026-09-16-dsh-review-agent/task-1-report.md`.

## Task 2: Provider route chain and failure classification

Implement a provider/model route-chain policy with bounded same-target retries, cooldowns, explicit fallback candidates, offline candidates, stable error codes, and pre-stream versus mid-stream behavior. Preserve write-only credentials and safe diagnostics. Add tests for insufficient quota, 429, 5xx, timeout, authentication, invalid request, and stream interruption. The screenshot’s 403 quota case must produce an actionable classified result rather than a raw error bubble.

Write the implementation report to `.superpowers/sdd/2026-09-16-dsh-review-agent/task-2-report.md`.

## Task 3: DSH sidecar bridge and restricted profile

Add a versioned JSON-RPC/stdio sidecar bridge with handshake, profile declaration, event subscription, cancel/resume/fork/close, heartbeat and crash classification. Provide a deterministic local test sidecar or protocol stub so tests do not require remote credentials. Define the `smartmoney-review` capability allowlist and a developer/source bootstrap path compatible with DSH’s clone/pnpm/build/web flow. Do not add model-facing shell, filesystem, network, workflow, or subagent tools.

Write the implementation report to `.superpowers/sdd/2026-09-16-dsh-review-agent/task-3-report.md`.

## Task 4: Durable review runtime and Workbench lifecycle

Integrate typed turn/step/attempt/plugin/terminal events into the existing SQLite session model without losing old sessions. Add server-side cancel, resume, replay cursor, and crash recovery. Implement guided review phases, scope confirmation, envelope persistence, structured result validation, and challenger proposal persistence. Keep hosted mode on the existing Python path unless the DSH sidecar is explicitly enabled locally.

Write the implementation report to `.superpowers/sdd/2026-09-16-dsh-review-agent/task-4-report.md`.

## Task 5: Finance plugin catalog and Cordis adapters

Implement the SmartMoney curated finance plugin catalog, manifest validation, source/version/commit metadata, network declaration, install/enable/disable/update/health state, and profile reload boundary. Add an adapter contract and two toy-backed validation adapters: TradingAgents-style multi-role evidence and evaluator/memory/challenger evidence. Upstream code must never receive raw journal data or credentials. Preserve existing plugin registry behavior and safety declarations.

Write the implementation report to `.superpowers/sdd/2026-09-16-dsh-review-agent/task-5-report.md`.

## Task 6: GUI settings, assistant states, and plugin marketplace

Update the React GUI to expose scope preview, guided phases, typed events, route-chain recovery actions, cancel/resume/fork, structured review package, and a Codex-inspired finance plugin marketplace with installed/detail/update/permission/network states. Keep credentials write-only and raw provider diagnostics local. Add frontend type/build coverage and compact smoke fixtures without changing unrelated existing views.

Write the implementation report to `.superpowers/sdd/2026-09-16-dsh-review-agent/task-6-report.md`.

## Verification

Run `./scripts/verify.sh` (or the repository-equivalent doctor plus full pytest and frontend build) after integration. Independent review must check the complete diff against the global constraints and all frozen DoD items.
