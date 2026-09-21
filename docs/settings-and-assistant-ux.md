# Settings and assistant UX (Issue #27)

## Product boundary

The journal remains the primary workflow. The standalone JEV page is removed;
JEV connections and external Agent configuration live under Settings. The
question-pack and engine-diagnostics panels are no longer part of the GUI.
Existing CLI, benchmark and JSON diagnostic APIs remain available.

`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`

## JEV connection

Settings → JEV connection saves an optional TypeSafe credential in
`<state-root>/jev-credentials.json`. The file is ignored by Git, written atomically
with owner-only permissions on POSIX, and never returned by the settings API.
This is a local plaintext credential file, not an encrypted operating-system
keychain; protect the local account and state directory accordingly.

A saved local key takes precedence over `TYPESAFE_API_KEY`. Clearing the local
key falls back to that environment variable, when present. Blank input retains
the saved key. Settings load/save do not contact any provider.

The explicit connection test sends one fixed synthetic question to the existing
TypeSafe backend. It does not send journal data and may incur provider charges.
A successful test means that particular typed request succeeded, not permanent
availability or independently verified model identity. Reloading shows untested
again. The workbench doctor reads the same configured credential; CLI callers
without a state root retain their environment-based behavior.

JEV remains a structured-judgment service, not a replacement chat model. This
change does not silently reroute the conversational assistant or auto-enable
paid evaluations. `JevConnectionSettings(root).backend()` provides the configured
existing typed backend for workbench consumers.

## Assistant feedback

The run card presents transport/tool activity and elapsed time, not a fabricated
reasoning trace or percentage. Tool JSON is collapsed by default. Scrolling up
suspends automatic following until the user returns to the bottom or chooses
“回到最新”. Sending locks before asynchronous session creation. Chinese IME
confirmation does not submit. Stop aborts reception, requests server cancellation,
and retains partial output; an unconfirmed server cancellation is disclosed.
