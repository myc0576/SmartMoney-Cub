# Settings and review-assistant cleanup (Issue #26)

## Product changes

- The global navigation is for journal/review work. JEV is now under **Settings → JEV connection**, and local coding-Agent integration under **Settings → Agent integration**. The old diagnostic/question-pack page is removed, not merely hidden. CLI/benchmark functionality remains.
- JEV stays a typed-judgment API, not a chat model. Setting its key does not change the assistant's chat provider or enable a new automatic judgment/trading workflow. Credentials are scoped to the local state root. An explicit constructor key wins over the saved local key, which wins over `TYPESAFE_API_KEY`.
- Reading/saving settings is offline. **Test connection** sends one fixed synthetic Noul question with a ten-second request timeout and no automatic retry; it may incur provider charges. No journal context is sent. Stored/configured and remotely verified are different states. The page does not persist verification across reloads.
- Blank key input means keep; deletion is separate and confirmed. The browser receives only credential presence/source, never its value. Credential files are written privately and replaced atomically; other model credentials are preserved. Clearing a local key does not remove an environment variable.
- Agent preview is non-mutating; apply/disable/restore require confirmation. Errors are visible and concurrent actions are blocked.
- Assistant status comes from actual transport/tool/text/terminal events, with elapsed time and collapsed tool details. It does not invent model reasoning or a completion percentage. Stop calls both backend cancellation and browser abort, retains partial output, and warns when cancellation is unconfirmed. Remote cancellation remains cooperative.
- Duplicate sends are blocked before session creation; IME Enter does not send. HTTP/network/parser/early-EOF failures always release the composer. Stale session reads cannot overwrite an active turn. Reading old messages disables forced auto-scroll until **Back to latest** is selected.

## Reference projects and decisions

Reviewed 2026-09-21; patterns were implemented independently, not copied.

| Primary source | Applicable idea | Deliberately not adopted |
|---|---|---|
| [Open WebUI provider connections](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible/) | Put connection configuration in Settings; distinguish save from verification. | No compatibility proxy or new chat-provider entry for JEV's non-chat protocol. |
| [assistant-ui tool fallback](https://www.assistant-ui.com/elements/tool-fallback) | Collapsed tool summaries, actual run states and elapsed duration. | No assistant-ui runtime dependency or migration of the existing assistant state/backend. |
| [TradeNote README](https://github.com/Eleven-Trading/TradeNote/blob/main/README.md) | Preserve a simple private journal-first product rather than foreground infrastructure. | No GPL implementation code, database migration or broker/ordering capabilities. |
| [TypeSafe quick start](https://docs.typesafe.ai/introduction/quickstart) | Existing direct endpoint and Noul schema verified against the official reference. | No unverified community gateway or key forwarding to arbitrary hosts. |

## Verification

Regression entry points:

```sh
python -m pytest tests/test_jev_connection_settings.py tests/test_workbench_jev_api.py -q
npm run test:unit --prefix gui
npm run typecheck --prefix gui
npm run build --prefix gui
npm run test:e2e
PYTHONPATH=src ./scripts/verify.sh
```

The Node tests reproduce HTTP errors, network rejection, split UTF-8/CRLF frames, malformed events and early EOF. Browser tests cover placement, local key handling, preview vs mutation, duplicate sends, IME, stop/partial output, errors and reading while streaming. JEV tests use synthetic keys and injected transports; no real API key or paid-provider success is claimed. The committed frontend is rebuilt from the source. CI runs the existing Python matrix/deployment gates plus these browser/transport checks.

Environment observations: the review container has unrelated preinstalled OCR/data packages and lacks crossplane, which made four pre-existing tests fail (scanned-PDF dependency reporting, two nginx validator checks and the provider-import isolation check). Its Chromium blocks URL navigation, so an in-memory rendering/smoke check was used locally; full URL-based E2E runs in GitHub Actions. These limitations are not concealed by skipping tests or weakening assertions. Final executed results are recorded in the PR.

Safety: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`. No live journal, credential or execution integration belongs in this repository.
