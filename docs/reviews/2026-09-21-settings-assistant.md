# Settings and assistant review — 2026-09-21

Implemented on `codex/settings-jev-assistant-27` for Issue #27 / PR #28.
This is a focused settings and assistant review, not a whole-repository security audit.

## Findings and changes

| Finding | Change | Verification |
| --- | --- | --- |
| Infrastructure configuration occupied the primary trading navigation | Remove standalone JEV page; put optional JEV connection and Agent integrations in Settings | Navigation contracts, frontend build |
| A JEV input alone would not configure the backend | Add local credential storage, environment fallback and explicit synthetic probe | Unit and actual HTTP tests with a fake backend |
| Sending was locked only after asynchronous session creation | Lock before the first await; retain selected provider and model | Browser duplicate-submit test |
| Stop discarded partial output | Abort reception, request server cancellation, preserve partial text/tools and disclose unconfirmed cancellation | Browser streaming/stop test |
| Pending tools still looked active after stopping | Terminal '未返回结果' labels | Regression observed failing, then passing |
| Panel CSS also matched assistant message bubbles | Scope panel selectors away from `.bubble` | Browser horizontal-overflow assertion |
| Streaming always forced the reader to the bottom | Follow only near the bottom; provide '回到最新' | Helper unit test and focused code inspection |
| Chinese IME Enter could submit early | Check composition state and key code 229 | Unit and browser tests |
| Agent API failure resembled an empty list | Visible errors, retry and operation outcome feedback | Browser failure/recovery test |

## Open-source references

- [assistant-ui Reasoning](https://www.assistant-ui.com/elements/reasoning): collapsible details, timing and respect for manual scrolling. Borrowed interaction principles, not upstream implementation or fabricated reasoning text.
- [Open WebUI connection setup](https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible/): keep connection configuration in Settings and distinguish saving from testing.
- [TraderMemos](https://github.com/sinhong2011/TraderMemos): self-hosted trading journal used for product-scope comparison. No profitability, adoption or code-quality claim; no upstream code copied.
- [TypeSafe introduction](https://docs.typesafe.ai/introduction): JEV produces structured judgments and is kept separate from the conversational model list.

No new runtime package dependencies are introduced. Existing CLI, diagnostic and benchmark APIs remain compatible; removed panels are no longer rendered in the GUI.

## Verification and limits

[Full verification and terminal-state review](https://github.com/myc0576/SmartMoney-Cub/actions/runs/35605526133): **979 passed, 9 skipped**, doctor/safety sanity checks passed; frontend helper tests **3 passed**; Chromium scenarios **3 passed**.

[Final layout verification](https://github.com/myc0576/SmartMoney-Cub/actions/runs/35606400079): reproduced the overflow regression, corrected the panel selector, then passed typecheck, helper tests, build and all three focused browser cases with containment checks. The earlier layout attempt failed safely in its edit-script assertion before source changes; the corrected selector targets standalone panel rules only.

The shipped Python-package frontend is rebuilt alongside every UI correction. Temporary branch-only editing workflows remove themselves and are not included in the final product tree.

Real paid JEV requests were not made. Tests use synthetic data and backend substitutes; screenshots are real browser captures of fixtures, not proof of live provider connectivity. The local credential file is atomic and permission-protected on POSIX but plaintext, not an encrypted OS keychain. Browser coverage is Chromium only, not an exhaustive device/browser matrix. Existing Vite native-loader compatibility warnings remain outside this scope.

`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`
