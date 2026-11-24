# WebUI CLI Operation Inventory

This inventory compares the current WebUI calls with the control operation registry and shared runtime. It is based on `gui/src/api.ts`, GUI call sites, the trader route table, and workbench service methods. Every operation response is required to carry `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

## Mapped operation groups

| WebUI capability | CLI operation(s) | Handler/source | Notes |
| --- | --- | --- | --- |
| Overview, documents, rules, rule timeline | `overview.show`, `documents.list`, `rules.list`, `rules.timeline` | `WorkbenchService` | Read paths are local and executable. |
| Import upload, reviewed commit, manual fill | `import.upload`, `import.commit-reviewed`, `import.manual`; trader `journal.import` | `WorkbenchService` / `TraderService` | Upload persists the document and extraction; trader import is the journal source read by trader views. |
| Governance profile, challenger, evaluation, promotion request and confirmation | `governance.profile-create`, `governance.profile-edit`, `governance.challenger`, `governance.evaluate`, `governance.request-promotion`, `governance.confirm-promotion`, `governance.rollback` | `GovernanceStore` through `WorkbenchService` | Champion mutation remains confirmation gated. |
| Rule promotion | `rules.promote` | `WorkbenchService.promote_rule` | Requires a non-empty human note. |
| Plugin registry, market, detail, probe, install, uninstall, configure, update, reload, enable, disable | `plugin.list`, `plugin.market`, `plugin.catalog`, `plugin.detail`, `plugin.probe`, `plugin.install-catalog`, `plugin.uninstall`, `plugin.configure`, `plugin.update`, `plugin.reload`, `plugin.enable`, `plugin.disable` | `WorkbenchService` and plugin stores | Companion plugins may be installed but remain non-callable; configuration and mutations need human confirmation. |
| Assistant sessions, create/update/fork, scope confirmation, challenger artifact, review package | `assistant.list`, `assistant.create`, `assistant.show`, `assistant.update`, `assistant.fork`, `assistant.scope`, `assistant.confirm-scope`, `assistant.challenger`, `assistant.package`, `assistant.preview` | `WorkbenchService` / review runtime | Structured package validation enforces provenance and challenger-only mutation. |
| Assistant streaming/cancel/resume | `assistant.send`, `assistant.cancel`, `assistant.resume` | `WorkbenchService` review runtime | Streaming operations are provider gated and re-check integration grants between events. |
| Review agents and presets | `assistant.agents`, `assistant.agent-detail`, `assistant.agent-probe`, `assistant.agent-enable`, `assistant.agent-disable`, `assistant.presets`, `assistant.preset-create`, `assistant.preset-save`, `assistant.preset-delete`, `assistant.default`, `assistant.set-default`, `assistant.from-trade` | `WorkbenchService` | Agent/provider configuration remains human-only where credentials or defaults are mutated. |
| Preferences | `preferences.show`, `preferences.update` | Shared preferences store | Local persistent read/write. |
| Audit, JEV, benchmark, agent administration | `audit.list`, `jev.status`, `jev.tracks`, `benchmark.latest`, `benchmark.image`, `agents.list`, `agents.apply`, `agents.disable`, `agents.restore` | `WorkbenchService` | Benchmark image is binary and requires `--output`; agent mutation is confirmation gated. |
| Trader journal, analytics, market, accounts, connections | `health.show`, `meta.show`, `market.providers`, `market.bars`, `journal.list`, `journal.import`, `journal.show`, `accounts.list`, `accounts.save`, `connections.*`, `analytics.*`, `calendar.show`, `insight.*`, `playbook.*` | Trader route table and `TraderService` | Route paths are kept in sync by the registry assertion. Account ingestion remains read-only with respect to the account. |
| Backtest and replay | `backtest.run`, `backtest.list`, `backtest.show`, `backtest.validate`, `replay.create`, `replay.list`, `replay.show`, `replay.action`, `replay.step`, `replay.seek`, `replay.rewind`, `replay.play`, `replay.pause` | Trader service plus local replay adapters | Offline bars bypass network permission; replay writes only the local training/review session. |

## Browser-derived actions

Report KPI calculations (`expectancy`, `feeShare`, best/worst day), report tab selection, breakdown table formatting and small-sample markers, replay chart markers and visible-bar change percentage, and export rendering through `control_exports.render_result` (`json`, `html`, `csv`) are computed after API responses. They have no independent server operation and should be documented as derived views.

The import screen converts a browser `File` to base64 before calling `import.upload`; the CLI equivalent is a protected JSON input or stdin payload. It does not expose a second file-upload transport.

## Gaps and handler risks found

- `gui/src/api.ts` exposes `decidePattern`, `createPlaybook`, `runBacktest`, replay actions, and several trader reads. The registry maps these through `insight.decide`, `playbook.save`, `backtest.*`, and `replay.*`, but workbench and trader namespaces use different stores. Cross-view parity requires a shared state directory, not only matching JSON shapes.
- `plugin.configure` maps to `/api/plugins/market/{plugin_id}/configure`, while `plugin.install-catalog` maps to `/api/plugins/install`; these are distinct from the local plugin CLI registry and must retain separate lifecycle semantics.
- `settings.open` launches a native editor and is desktop-only. The CLI handler returns the path and safety declaration but cannot reproduce a browser click or guarantee an editor in headless environments.
- `connections.authorize` and OAuth start/complete/callback require an active PKCE wizard or configured HTTP service. They are intentionally excluded from offline tests because invoking them requires a real authorization boundary.
- `assistant.send`, `assistant.resume`, provider discovery/test/model checks, market bars, and account sync are network/provider operations. Offline coverage should assert refusal without `--allow-network` or an integration grant and must not use paid endpoints.
- `assistant.cancel` is only exercised after an interrupted stream in the CLI path. A deterministic standalone cancellation test needs a controllable provider stream and is not included in this toy offline inventory.
- `benchmark.image` is binary and requires an explicit output path; ordinary JSON operation tests do not cover artifact writing.
- Local helpers such as `providers.setup`, `plugin.setup`, `permissions.*`, `connections.watch`, and `backtest.validate` are companion CLI capabilities rather than direct WebUI routes.

## Coverage added

`tests/test_cli_operation_coverage.py` invokes real local handlers for import upload/commit, governance challenger/evaluation/promotion confirmation, assistant create/update/fork/scope/package, plugin registry/configuration, and offline backtest/replay. It also checks registry safety declarations and uses only invented temporary state. OAuth, paid/provider network calls, binary benchmark export, and live assistant streaming remain explicitly untested for the reasons above.

## External-service verification boundary

Registry presence and a matching HTTP path establish interface mapping only.
They do not establish that AlphaTech paid completion, account authorization,
market provenance, or another external service has succeeded. In the
2026-09-29 bounded probe, AlphaTech model discovery returned HTTP 200, while a
paid completion remains pending usage/cost verification; seven connection
manifests yielded zero live authorized accounts; Eastmoney and Stooq failed;
Tencent returned bars without provenance timestamps and remains pending; Binance
was restricted with HTTP 451. Redacted evidence is under
artifacts/maintenance/2026-09-29/.

The table above is a map of advertised operations, not proof of complete CLI,
HTTP, or WebUI behavioral equivalence. The 2026-09-30 probe found AlphaTech
model discovery but no verified paid completion, seven account providers in
not_configured, Eastmoney/Stooq/Binance failed, and Tencent pending because
availability provenance is incomplete. Live service actions, OAuth, provider
specific recovery, browser-only interactions, and full visual behavior remain
uncovered until independently exercised with fresh evidence.
