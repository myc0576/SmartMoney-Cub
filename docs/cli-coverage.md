# CLI and WebUI parity coverage

This table records tested parity between ControlRuntime local execution and
the Workbench HTTP surface. Fixtures use a temporary state root and invented
journal values. Successful responses are expected to carry
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE.

| WebUI operation | Registered operation | Local | HTTP with X-SMCUB-Token | Evidence | Current gap |
|---|---|---:|---:|---|---|
| Read and update shared preferences | preferences.show, preferences.update | yes | yes | test_registered_workbench_reads_and_mutations_match_local_and_http | none identified for these calls |
| Add a manual journal fill | import.manual | yes | yes | same test | no parity gap observed |
| List, create, and inspect assistant sessions | assistant.list, assistant.create, assistant.show | yes | list/show over HTTP; create locally | same test | HTTP create is registered but not repeated in this fixture |
| List and save a local account | accounts.list, accounts.save | yes | yes | same test | trader mount has its own local identity path |
| Reject an invalid access token | HTTP auth boundary | n/a | yes, 401 | test_http_auth_denial_does_not_fall_back_to_local | none identified in this check |

These focused tests do not claim full CLI/WebUI parity. Uncovered browser
operations include assistant message and resume streaming, settings file
opening, binary benchmark image delivery, provider discovery and probing,
plugin installation and lifecycle, governance promotion, review package
actions, import upload/commit, and the full trader market, connection, replay,
backtest, analytics, and insight surfaces.

The current tested slice is evidence for representative paths only. Missing
business actions to report to the integration owner are:

- Workbench import upload and reviewed commit, documents, overview, settings,
  audit, rules, governance, plugins, agents, JEV, and benchmark reads/actions.
- Assistant review scope confirmation, challenger/package recording, forks,
  cancellation/resume streaming, agent and preset administration, and
  review-from-trade.
- Trader market bars, trade import/detail, analytics, calendar, insights,
  playbooks, backtests, connections and OAuth, and replay session creation,
  stepping, and cross-process concurrent mutation.
- Local-only setup and foreground stream operations represented by registry
  entries with an empty path.

The replay service now has a root-scoped advisory lock for its persisted
read-modify-write paths. The focused cross-process test is
test_replay_rmw_uses_one_root_lock_across_processes; this does not imply the
full replay surface is covered.

The registry also contains local-only setup and foreground stream operations
with an empty path. They are not counted as HTTP parity. The browser-only
transports above should be reported to the integration owner before claiming
complete coverage.

## 2026-09-29 real-service boundary

Bounded network probes are recorded under
artifacts/maintenance/2026-09-29/. They are service evidence, not fixture or
catalog evidence, and every result preserves
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE.

| Service path | Fresh result | Acceptance state | Evidence boundary |
|---|---|---|---|
| AlphaTech model route | 2026-09-30T15:14:15Z: HTTP 200, live model IDs include gpt-6-astra and gpt-6.1-sol; official pricing API returned 120 records | route/model discovery verified; user-approved $0.05 paid completion pending and unverified | Gateway tier expression has no documented USD conversion; no completion, usage, cost, balance, or quota verification was performed |
| Account connections | Seven providers, all not_configured: ccxt-binance, ccxt-okx, ibkr-flex, metatrader-investor, local-statement-directory, snaptrade-personal-mcp, vezgo | pending; zero live authorized connections | No sync, paging, cursor recovery, restart recovery, or disconnect test was run without verified read-only authorization |
| Eastmoney | remote connection closed without a response | failed | No catalog or local fixture was promoted to success |
| Tencent | two live bars returned, but provenance timestamps were absent | pending | Missing available_at and decision_time prevents historical acceptance |
| Stooq | TLS connection failed | failed | No substitute source was used |
| Binance | HTTP 451 regional restriction | failed | Regional denial remains a provider failure |

A real market result is accepted only when it includes source, symbol,
interval, available_at, decision_time, data quality, response timing, and a
check that available_at <= decision_time. A network response without those
fields remains pending; unavailable, unauthorized, rate-limited, or parse
failed providers remain failed. Catalog metadata, fixtures, cached bars, and
operation registration are never real-service success evidence. Toy-state tests
and registry/interface mappings do not establish live-service success or
complete WebUI equivalence; browser-only, OAuth, streaming, and external
account flows remain separate coverage items.
