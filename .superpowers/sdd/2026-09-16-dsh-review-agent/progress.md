# SDD ledger — plan: docs/superpowers/plans/2026-09-16-dsh-review-agent.md

## Preflight conflict scan

| Pair/task | Shared input/output or write surface | Finding | Ruling |
|---|---|---|---|
| Task 1 ↔ Task 2 | Both define stable metadata consumed by runtime | Contracts and provider errors are conceptually adjacent but can use separate modules | Task 1 owns generic review/safety contracts; Task 2 owns provider route/error types and may import Task 1 safety constants only. |
| Task 1 ↔ Task 3 | Task 3 bridge carries review envelopes and events | Task 3 depends on envelope/event shapes | Task 1 publishes versioned Python contracts first; Task 3 consumes them without redefining fields. |
| Task 1 ↔ Task 4 | Task 4 persists and validates Task 1 result types | Direct dependency, no same-file requirement | Task 4 imports Task 1 contracts and owns persistence integration. |
| Task 2 ↔ Task 4 | Route policy controls runtime attempts | Direct dependency, runtime needs classified errors | Task 2 owns route policy/classifier; Task 4 owns orchestration and persistence of attempts. |
| Task 3 ↔ Task 4 | Sidecar lifecycle events feed Workbench lifecycle | Bridge transport and server orchestration could overlap | Task 3 owns `agent/dsh_bridge.py` and sidecar protocol; Task 4 owns server/store calls and projections. |
| Task 3 ↔ Task 5 | Both mention DSH profile/plugin loading | Plugin catalog must produce profile input | Task 3 owns the fixed profile allowlist; Task 5 produces validated plugin descriptors and reload requests, never broadens forbidden capabilities. |
| Task 4 ↔ Task 5 | Both may touch Workbench/plugin API routes | Potential server.py collision | Task 4 owns assistant/session routes; Task 5 owns plugin service/module and only adds isolated plugin route hooks through an interface; Task 6 consumes both. If registration requires `server.py`, it is a small integration commit after both tasks, not parallel edits. |
| Task 4 ↔ Task 6 | GUI consumes assistant lifecycle APIs | Backend contracts must precede UI wiring | Task 4 defines stable JSON response/event shapes; Task 6 only consumes them and does not change backend behavior. |
| Task 5 ↔ Task 6 | Marketplace data/status shapes cross backend/frontend | Frontend types must mirror plugin catalog | Task 5 publishes JSON shapes and fixtures; Task 6 owns TypeScript rendering and API client. |
| Task 1 | Tests vs implementation | TDD required | Write focused failing tests first, verify RED, then implement minimal code. |
| Task 2 | Tests vs implementation | TDD required | Same red-green-refactor cycle, including screenshot quota regression. |
| Task 3 | Tests vs implementation | Sidecar cannot require live DSH credentials | Use deterministic protocol stub and assert fail-closed profile capabilities. |
| Task 4 | Tests vs implementation | Existing session compatibility is mandatory | Add migration/replay tests before modifying persistence paths. |
| Task 5 | Tests vs implementation | Upstream projects must not be fetched or executed in tests | Use toy adapters and static manifest fixtures only. |
| Task 6 | Tests vs implementation | Existing dirty GUI changes are in scope input, not disposable | Preserve current user changes; add type/build/smoke coverage around them. |

## Rulings

- Ruling: “同进程” means same DSH sidecar/Cordis process, never the Python Workbench process — DSH is a Node runtime and the sidecar must remain the only plugin host; cost if wrong: plugins may need a later RPC boundary redesign.
- Ruling: The current dirty worktree snapshot is user-owned baseline and must remain intact in `/Users/myc/Smartmoney-Cub`; implementation happens only in this worktree — cost if wrong: user changes could be lost or mixed into the feature branch.
- Ruling: Task 1 must land before Tasks 3 and 4 because bridge and persistence depend on its contract names — cost if wrong: parallel agents could invent incompatible payloads.

## Task status

- Task 1: complete (scoped fix-round-3 re-review approved)
- Task 2: complete by controller adjudication (fix-round-5 `123b20d`; fresh full pytest and deterministic privacy probes pass; model re-review was blocked by repeated no-response/OAuth failures; final whole-branch review remains mandatory)
- Task 3: pending
- Task 4: pending
- Task 5: pending
- Task 6: pending

## Task 2 review

- Task 2: review failed — Critical: known opaque credentials can leak through provider diagnostics; Important: production quota remediation is flattened into a string, opening timeout classification is incomplete, 504 is classified as generic server error, cooldown candidates are still attempted, and authentication/invalid-request errors block explicit fallback candidates. Reviewer also noted the HTTP status regex minor issue. Fix round 1 dispatched to the original implementer; no controller-side fix.

## Task 1 review

- Task 1: review failed — Important: plugin-result validation trusts caller decision time, redaction misses CSV originals and non-string identifiers, typed nested objects bypass safety validation, and challenger dictionaries allow extra champion-mutation fields. Fix round 1 dispatched to the original implementer; no controller-side fix.

- Task 2: fix round 1 re-review — 6 findings addressed, 1 Critical remains open: `ClassifiedProviderError.to_dict()` still serializes `portal_url` and `recovery_suggestions` without final known-secret redaction. Fix round 2 dispatched to the original implementer.
- Task 2: fix round 2 commit `f909f32` scrubs all serialized ClassifiedProviderError fields; scoped re-review pending.
- Task 2: fix round 2 re-review — original finding addressed, but a new Critical was introduced: plaintext credentials are retained in public `ClassifiedProviderError.extra_secrets` and visible via `vars(error)`. Fix round 3 dispatched.
- Task 2: fix round 3 — eliminated extra_secrets attribute from ClassifiedProviderError instance; immutable attribute scrubbing on initialization; regression verified with fresh TDD evidence.
- Task 2: fix round 3 scoped re-review pending.
- Task 1: fix round 1 re-review — authoritative time, original-file/numeric identifier redaction, typed safety, and v1 compatibility addressed; Important challenger bypass remains because nested metadata and `champion-mutated` fields evade the shallow guard. Fix round 2 dispatched after resuming the original implementer.
- Task 1: fix round 2 commits `272ad6a`, `a502e42` recursively reject nested/hyphenated champion mutation fields; scoped re-review pending. Concurrent Task 2 changes remain outside this task.
- Task 2: fix round 3 re-review — `extra_secrets` was removed, but the fix exposed credentials duplicated into public `provider_id`/`model`; because three resume rounds were exhausted, a fresh gpt-6-astra implementer was dispatched for fix round 4.
- Task 1: fix round 3 commit `9378344d5cf62b805d968b87e007dd532971aca3` restores exact dangerous-value matching while retaining normalized nested-key protection; scoped re-review approved with 56 focused tests passing and doctor safety confirmed.
- Task 2: fix round 4 commit `6018f4f` removes raw upstream causes and sanitizes retained fields, but scoped re-review found a Critical URL-query credential leak and an Important schema-corrupting blanket substring replacement; a fresh `commandcode/deepseek-deepseek-v4.1-flash` implementer is handling fix round 5.
- Task 2: the DeepSeek and Astra fix-round-5 attempts produced no submission; the requested Gemini attempt failed with OAuth 401. The controller then completed the scoped fix as `123b20d`, adding URL query/fragment removal and preserving trusted protocol/recovery schema. Final independent review is pending.
- Task 2: scoped model re-review attempts after `123b20d` repeatedly timed out; controller adjudication ran 70 focused and 134 related tests, then the full suite at 838 passed / 6 skipped with doctor safety confirmed. Treat the missing model review as an environment limitation, not as evidence of approval; the final whole-branch reviewer must re-check this boundary.
