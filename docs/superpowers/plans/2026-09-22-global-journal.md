# Global journal and completeness implementation plan

## Goal and constraints

Implement the approved global, multilingual journal update on top of the existing uncommitted GUI/review changes, with independent review, real service E2E, visual checks, GitHub issue and PR. Preserve `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`, offline core, tenant isolation, user-owned records, and explicit challenger promotion. No live execution, paid vendor enrollment, or real account authorization during development. Fixtures are synthetic only. Maximum verification repair cycles: 5.

## Frozen acceptance checklist

- [ ] Preserve and include prior uncommitted changes after diff/privacy review.
- [ ] Fix replay/backtest/playbook/report contracts, duplicate edges, chart markers, import identity, and false empty states.
- [ ] Global execution model supports account/instrument isolation, fractional quantities, shorts, multipliers, currencies, market policies, source precision and provenance; missing facts stay unknown.
- [ ] Read-only connections include CCXT Binance/OKX, IBKR Flex, MetaTrader investor terminal bridge, local statement directory, optional SnapTrade Personal MCP, optional user-owned Vezgo. No vendor credentials are bundled or required for core. External live authorization acceptance is explicitly separate.
- [ ] Insight provides observed account profiles and per-trade evidence-backed candidates, uncertain/mixed states, confirm/reject/rename persistence and playbook links. No psychological claims from timestamps.
- [ ] Persistent actual-trade replay and separate simulated training with cursor-bounded data, markers, deterministic next-bar fills and independent journal.
- [ ] Credential setup has official obtain links and correct fields/modes; vn.py absent from official marketplace.
- [ ] Remove prop-firm evaluation without deleting accounts. Consolidate duplicate legacy views.
- [ ] Nine locales (zh-CN/en-US/zh-TW/ja-JP/ko-KR/es-ES/pt-BR/de-DE/fr-FR), locale-aware formatting, compact header, account scope, preferences and complete async states.
- [ ] Independent review; full verify, E2E and visual report with no failed checks; issue + commit + pushed PR.

## Task ownership and contracts

1. Domain backend: fills/analytics/storage/insight; global metadata, deterministic imports, account and currency scope; pattern candidates and decisions. Own existing storage and service integration for domain methods, coordinate edits to service/routes with connection/replay work.
2. Frontend: gui/src only, i18n, compact header/preferences/account scope, plugin setup, API normalization, four-state views, insight and replay UI, connections UI. Existing backend envelopes remain; use an explicit boundary adapter, not casts. Coordinate new endpoint DTOs before consuming.
3. Connection backend: new trader/connections package and tests; read-only adapter manifest, sync engine, credentials, watches and persistence; communicate endpoint integration patch to coordinator. Never modify shared service/routes/storage until assigned.
4. Coordinator: plan/ledger/docs, plugin catalog and installer, replay/backtest/playbook API integration (coordinate shared edits), migration integration, final tests, independent reviews, GitHub delivery.

## Connection boundary

Connector methods: metadata, validate_read_access, list_accounts, read_events(cursor), read_positions, disconnect. Manifests provide official links, auth fields, supported assets, capabilities, history/time precision and validation status. Pagination, durable cursors, idempotent external IDs and revisions, partial failures, bounded retries, scope verification, secret redaction and disconnect must be tested. SnapTrade uses the official read-only MCP endpoint with DCR + PKCE and structural calls, never LLM parsing or consumer keys. Vezgo uses user-owned developer credentials and explains the cost. Credentials remain local/server-side. Unknown permission = no automatic sync. Local statement watch never automates broker login/export.

## Data and feature behavior

Use decimal quantities/money and preserve source metadata, timestamp precision, timezone, market, asset, currency, multiplier and fee components. No 09:30 fabrication, cross-account FIFO, global CN-A fee/T+1 assumption, or mixed-currency sum without rates. Keep legacy imports compatible; unknown mapping requires review. Reimports and same-second fills must not duplicate or overwrite distinct fills.

Patterns are multi-axis (holding horizon, entry shape, sizing/exit behavior), observed/inferred/confirmed, with sample/evidence/quality/version. Rules use only pre-entry market context. Users confirm before stable playbooks/tags. Stable edge claims need evidence beyond positive PnL; show losing groups separately.

Replay supports review and training. Persistent sessions hold source/quality/as-of and cursor. Only revealed bars/markers reach the client. Training is simulated only, next-bar execution, separate records, rewind starts a branch. Historical availability differs from fetched_at; unproven point-in-time inputs are not accepted as historical decision evidence.

## Verification

Test real service envelopes and browser consumption, save/reload, import-to-reports-to-insight, cursor leakage, training isolation, global lots and currencies/timezones/DST, same-second/repeated imports, pagination >1000, revisions, auth expiry/revoke/403, tenant isolation, missing time and prices, translation switching and long labels, responsive assistant open/closed. Run `./scripts/dev-env.sh verify`, `./scripts/dev-env.sh test e2e`, `./scripts/visual-check.sh`; inspect screenshots and `artifacts/visual/report.json` with `summary.failed.length === 0`. Never make mock-only E2E stand in for actual service contracts. External account tests require the user's own authorization and are reported separately from fixture/sandbox evidence.

## Research references

- https://docs.snaptrade.com/docs/mcp-server
- https://docs.snaptrade.com/docs/oauth-apps
- https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getAccountActivities
- https://github.com/ccxt/ccxt
- https://www.metatrader5.com/en/terminal/help/startworking/authorization
- https://vezgo.com/docs/get-started/
- https://github.com/rotki/rotki
- https://edgewonk.com/features
- https://www.tradervue.com/help/reports/reports_advanced
