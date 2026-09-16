# Task 6 implementation report — GUI lifecycle and plugin marketplace

## Scope

The React Workbench now exposes the existing provider/plugin settings and
Codex-inspired plugin inventory/catalog with safety, isolation, permissions,
network, configuration, health/event detail, and explicit reload actions.
The assistant surface consumes the durable review lifecycle: it previews the
redacted scope, requires confirmation before sending a turn, can request server
cancellation, and has typed API support for replay/resume and fork.

Credentials remain write-only in the settings flow. The GUI displays safety and
status metadata, not raw provider diagnostics or secret values.

The catalog tab also renders the curated SmartMoney Cordis adapters with their
source/commit, license, declared network, permissions, upstream-execution
status, and explicit profile-reload boundary.

## Files

- `gui/src/types.ts`
- `gui/src/api.ts`
- `gui/src/components/AssistantPanel.tsx`
- Existing user-owned settings/plugin UI changes remain intact.

## Verification

- `npm run typecheck` — passed.
- `npm run build` — passed.
- Vite emitted only the existing `__dirname`/native config-loader warning.

## Residual risk

The GUI's resume action is API-ready but the current compact assistant view
still emphasizes the normal send/cancel path. A future UI pass can add a
dedicated resume button for interrupted sessions without changing the backend
contract.
