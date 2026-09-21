# Settings and review assistant: implementation review

Issue: https://github.com/myc0576/SmartMoney-Cub/issues/24

## Scope

JEV is now an optional connection, not a primary workbench destination. The
sidebar no longer exposes its engine/diagnostic/question-pack UI. Research
APIs, the CLI and offline benchmark remain available. Agent configuration
management is in Settings alongside model and JEV configuration.

No brokerage integration, trading authority, or automatic Champion promotion
was added. The default conversation provider and its model catalog are unchanged.

## Review findings addressed

- JEV's previous health check meant a credential existed, not that the endpoint
  had accepted it. Settings distinguishes configured credentials from an explicit
  successful probe. Configuration reads and writes never contact TypeSafe.
- Agent actions were buried in a diagnostic workbench and silently swallowed
  scan failures. Their new settings component has explicit error/retry/pending
  states and independent preview/apply/disable/restore controls.
- Sending a first message could race before session creation completed. A
  synchronous ref lock now covers preparation, streaming and navigation actions.
- HTTP errors and incomplete/malformed SSE streams could leave a busy interface
  or erase the failure at completion. Framing is shared between send/resume,
  recognizes CRLF and chunk boundaries, and requires a terminal `done` event.
- Stopping discarded the visible response and only aborted its transport. It now
  requests the backend cancellation endpoint, retains the partial response and
  prevents stale callbacks from replacing the next turn or selected session.
- IME confirmation could be mistaken for Send. Composing Enter/229 is ignored.
- Streaming forcibly scrolled readers to the end, and assistant bubbles inherited
  the dock's fixed width. Both are corrected; a button returns to latest content.

## Credential boundary

`jev.credentials.json` is scoped to the active local Workbench state directory,
separate from chat-provider configuration. The file is written atomically with
owner-only permissions on POSIX and ignored by git. Its contents are local
plaintext protected by filesystem permissions, **not encrypted at rest**; use
OS disk encryption and protect state-directory backups. The API never returns
secret text, including when a provider rejects a key. Environment fallback uses
`TYPESAFE_API_KEY` without mutating the process environment.

The explicit connection test makes one request to the fixed TypeSafe HTTPS
endpoint using only `{"connection_test": true}` and a synthetic typed question.
It can consume provider credits. It sends no user journal/chat content, follows
no redirects and has no automatic retries. Success is limited to that request:
it does not prove continuous availability or independently attest model identity.
The returned model name is the provider's reported model name.

This configuration supplies the local Workbench's JEV backend and connection
probe. Existing environment-based CLI/benchmark invocations remain compatible;
this change does not turn JEV into a generative chat model or automatically run
JEV for every assistant message. Hosted deployments retain the existing local
Workbench API trust boundary.

Cancellation stops reception and requests cancellation in the harness. It cannot
promise instantaneous termination of an already in-flight provider computation.
A failed cancellation request is shown explicitly instead of claiming success.

## Open-source references (reviewed 2026-09-21)

These are design references, not copied code or added runtime dependencies.
Project descriptions are maintainer claims, not independent efficacy evidence.

| Source | Observed pattern | Applied here |
|---|---|---|
| [Open WebUI](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/) | Provider connections managed under Settings | Optional JEV and Agent connections removed from primary task navigation |
| [assistant-ui tool fallback](https://www.assistant-ui.com/elements/tool-fallback) and [LocalRuntime](https://www.assistant-ui.com/docs/runtimes/custom/local-runtime) | Collapsible tool summaries, explicit running/terminal states and abort signals | Event-driven activity card, folded payloads, retained partial output and backend cancellation |
| [TradeNote](https://tradenote.co/) | Journal, review, tags and screenshots form the daily user workflow | Keep the left navigation focused on review and data; do not add another engine dashboard |
| [LuxAlgo trade-journal](https://github.com/LuxAlgo/trade-journal) | Locally owned journal, optional external connections and inspectable records | Preserve local/private state and deliberate provider opt-in rather than adding execution features |
| [TypeSafe HTTP API](https://docs.typesafe.ai/api) | Typed questions at `/v1/systemone`, not chat completions | Separate JEV configuration, synthetic Noul probe, no entry in the chat model picker |

## Verification

Behavior tests are in `e2e/settings-assistant.spec.ts` (synthetic API fixtures),
stream framing tests in `gui/tests/stream.test.mjs`, and backend coverage in
`tests/test_jev_connection_settings.py` / `tests/test_workbench_jev_api.py`.
Normal CI now runs the added frontend tests and the Playwright suite.

Commands: `npm test --prefix gui`, `npm run typecheck --prefix gui`,
`npm run build --prefix gui`, `npx playwright test`, `./scripts/verify.sh`.
The PR records executed results. No real JEV credential or paid live inference
is needed for automated tests; a user must explicitly test their own key locally.

Safety declaration: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.
