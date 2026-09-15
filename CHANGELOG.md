# Changelog

## 1.0.0 — Trader Product v1

The 1.0 release. It converges two products into one package and one process:

- The **hosted trader product**: a multi-tenant trading journal and review
  surface, delivered as a peer entry on the alphatech platform at
  `alphatech.net.cn/trader`, beside Alpha Canvas and the Commerce Workbench.
  It imports the trader's own executions, computes performance analytics,
  scores playbooks, backtests a JSON strategy DSL, and replays historical bars.
  Local mode is a single offline user on SQLite; hosted mode is one tenant per
  platform identity in Postgres.
- The **local-first review workbench**: a three-region interface whose import
  pipeline parses broker files on the machine and whose review assistant
  redacts identity and exact size before any provider request.

`smcub trader serve` mounts both on one socket and one port. The safety
contract is unchanged and the execution ban is absolute.

The plugin protocol, the review workspace, the share pack, and the Run
Envelope / Evidence Pack governance predate this release. They were written up
under an unreleased `0.2.0` heading that never became a tag, so they ship
here and are recorded under this version.

### Added — the hosted trader product

- `smcub trader serve --mode {local,hosted}` with `--host`, `--port`,
  `--database-url`, `--state-dir`, `--token`, and `--no-browser`. It mounts
  the trader API at `/api/trader/*` and the review workbench on the same socket.
- Tenant-scoped storage behind one `TenantStore` interface with two engines:
  SQLite for a local single user and Postgres for hosted tenants. Every
  tenant-scoped row carries a user identifier and every tenant-scoped query
  filters on it.
- alphatech platform identity for hosted requests: the caller's session cookie
  forwarded to `{ALPHATECH_BASE_URL}/api/user/self` (`session` mode, the
  default), or an HMAC-signed identity header (`hmac` mode, selected by
  `ALPHATECH_AUTH_MODE` and keyed by `ALPHATECH_SSO_SECRET`). Both modes fail
  closed; a platform user id maps to a stable tenant `alphatech:<id>`.
- Four built-in keyless market data sources behind a provider interface, each
  returning normalized bars with provenance (provider, fetch time, quality
  flag). Importing the package performs no network access, and a fetched series
  is subject to the same anti-future-leakage validation as any other input.
- Deterministic backtest engine driven by a JSON strategy DSL, with saved runs.
- Trader HTTP surface under `/api/trader/*`: health, meta, market providers and
  bars, trade import and lookup, accounts, performance summary and breakdown,
  calendar, playbooks, backtests, and historical-bar replay. Every response
  carries the safety declaration. See `docs/trader-api.md`.
- Frontend rebuilt into the package for the full product surface: trade log,
  analytics, calendar, playbooks, backtest, replay, reports, prop-firm view, and
  settings, served by the same process and carrying no CDN or remote asset.
- `[hosted]` install extra (`psycopg[binary]>=3.2`) for the Postgres store. The
  driver is imported lazily; without it, opening a hosted store raises a
  `StoreError` naming the exact install command. Core `dependencies` stays
  empty.
- Deployment artifacts: `deploy/Dockerfile` (Python 3.12 slim, non-root,
  `.[hosted]`, no baked secrets), `deploy/docker-compose.yml` (app plus
  Postgres 16, healthcheck on both, named volumes, secrets from the
  environment), `deploy/nginx.conf` (TLS placeholders, `/trader` prefix,
  streaming-friendly proxy), `deploy/trader.service` (systemd, non-root,
  `Restart=on-failure`), and `deploy/README.md`.
- `docs/trader-product.md`, the product README: what v1 does, the explicit
  non-goals, and the features deferred past v1.

### Added — the local-first review workbench

- Review workbench served from the package at `workbench`: a three-region
  interface with navigation and portfolio switch, a working page, and a docked review
  assistant. Pages cover overview, trade log, review calendar, performance analytics,
  rule library, import, plugins, and settings.
- `npx smartmoney-cub` launcher. It provisions a private Python environment
  under `~/.smartmoney-cub` on first run, so a user needs no manual Python
  setup.
- Local import pipeline for CSV, TSV, PDF, and screenshots. Source bytes are hashed
  and stored once, parsing runs locally, and every field carries confidence.
- Immutable documents and fill revisions. A correction appends a revision and marks
  the previous one superseded, so an edit stays auditable.
- Review assistant with local session storage, streamed turns, expandable tool cards,
  stop, and fork. Turns are persisted before they are streamed, so a reload resumes
  the same conversation.
- Preconfigured company gateway provider (`https://alphatech.net.cn/v1`), a
  generic OpenAI-compatible provider, and an offline provider for local review.
- Outbound redaction with a device-stable salt: account and identity values are
  removed or pseudonymized, security codes and portfolio names become aliases, exact
  quantities and amounts become bands, and timestamps become 15-minute buckets.
  Returns and statistics survive.
- `outbound_audit` table recording which fields were sent and how many values
  were replaced, without recording values or keys.
- `smcub import file|commit|list`, `smcub store status|backup`,
  `smcub skill install|show`, and `smcub workbench`.
- Agent skill that drives only the stable JSON CLI and cannot read the database,
  credentials, or attachments directly.
- Local OCR as an optional extra (`smartmoney-cub-harness[ocr]`), so
  screenshots and scanned PDFs can be read without a network call.

### Added — plugins, workspace, and evidence governance

- Plugin protocol for read-only external integrations: manifest schema and validator, service definition / provider / consumer seams, `inject` dependency resolution, profile-bundle-patch composition, lifecycle states, reversible effects with disposers, subprocess isolation, capability catalog, and Evidence Envelopes.
- `smcub plugin list|inspect|enable|disable|remove|doctor|run|logs|catalog` and `smcub profile show|dump|reload`.
- SQLite review workspace with the non-silent observation contract, D1/D3 outcomes that never rewrite a frozen case, validated plugin evidence, and human-gated champion rule state via `smcub workspace ...`.
- Position ledger for broker and 同花顺 CSV exports with batched fills, partial closes, cross-day positions, T+1, fees, oversell, duplicate rows, limit-board, and suspension flags. Ambiguity is reported as `needs_review` instead of becoming a silent trade.
- Static, privacy-reduced share pack with identifier, path, and credential auditing plus a SHA-256 seal via `smcub share-pack`.
- Reference subprocess plugin at `examples/toy_plugin`, plus `docs/plugins.md`, `docs/plugin-development.md`, `docs/review-workspace.md`, and `docs/share-pack.md`.

- Run Envelope v1 for external-Agent provenance, reconciled offline tool results, output evidence paths, fixed permissions, and failure status.
- Evidence Pack v1 for frozen D1/D3 samples, artifact hashes, review metrics, and deterministic replay.
- `validate-envelope`, Agent metadata options on `capture-run`, `build-evidence-pack`, and `replay-evidence-pack` CLI support.
- Challenger evidence states and an explicit human confirmation gate before champion registry mutation.
- Machine-readable schemas at `schemas/run-envelope.schema.json` and `schemas/evidence-pack.schema.json`.
- Explicit `declarative` / unverified Run Envelope permission semantics so provenance is not mistaken for subprocess sandbox enforcement.
- `evidence_pack.sha256`, fail-closed manifest validation, complete hash-inventory checks, and safe `pending_review` reports for invalid packs.

### Changed

- `docs/harness-contract.md` and the safety framing now read as read-only with
  respect to markets and execution and writable with respect to the user's own
  local and tenant-scoped journal.
- `doctor()` reports `market_data_mode` (`offline`) and `tenant_mode`
  (`local_single_user`); `network_required` keeps its key and means the core
  is usable with no network.
- The documented contract now covers the trader product alongside the existing
  control plane.

- The interface ships inside the wheel and uses no CDN, no remote font, and no
  external asset.
- A combined broker fee column is now read as a declared fee instead of being ignored
  and replaced by an estimate.
- A model provider without a usable key falls back to local review instead of sending
  an unauthenticated request.
- Profit factor is documented and reported as gross profit over absolute gross loss,
  and reads as undefined when a sample has no losing trade.

- Dashboard CSV import now uses the position ledger and surfaces blocking issues instead of pairing fills with naive FIFO.
- Dashboard promotion is a two-step request plus explicit confirmation with a written note; sample-size gates apply and no performance numbers are fabricated on promotion.
- Dashboard labels demo fixture data as DEMO and refuses to execute a disabled plugin.
- Fixed the documented toy control-plane sequence: build-outcome now resolves the packaged price-source reference the toy loop records, instead of the stale examples path.

### Fixed

Fixes found while preparing the product to ship, each verified by executing the
path rather than reading it. An independent adversarial pass over the shipping
claims produced most of them.

- **The workbench API was reachable by every visitor the proxy served.** The
  tenant-scoped `/api/trader/*` surface resolved an identity per request and was
  isolated, but `/api/overview`, `/api/settings`, and `/api/assistant/*` read
  the container's own state directory and carry no tenant identity, so a second
  platform identity could list the first user's private assistant sessions.
  `deploy/nginx.conf` closed this only in a commented-out block, so the shipped
  default was fail-open on a shared host. Those blocks are now active, and
  `scripts/preflight.py` asserts the boundary instead of trusting it.
  The access token does not close this on its own: nginx injects it for every
  visitor, because a browser cannot attach a custom header to a page load.
- **The proxy validator reported success without parsing.** `scripts/nginx-check.py`
  passed crossplane the config text where it expects a filename, and crossplane
  reports that failure in its returned status rather than by raising, so the
  guard never fired and the script printed "PASS: parses cleanly" with the config
  unread. It now parses a real file and checks the returned status.
- **Two deployment-pipeline defects blocked any release.** `release.yml` uploaded
  the npm tarball from a malformed path expression, which would have failed the
  `npm-package` job; `ci.yml` carried a stray `+` inside the grep asserting the
  safety declaration survives the interface build.
- **Every JSON error response now carries the safety declaration.** Five error
  paths omitted it, so a refusal was the one reply that did not state the
  product's safety contract.
- **An unreachable hosted database reported a raw traceback.** The first real
  connection happens when the store migrates its schema, which sat outside the
  startup guard, so a database that was down reached the operator as a Python
  stack instead of the one clean line every other refusal prints.
- **The model catalog named models the endpoint does not serve.** The built-in
  gateway catalog hardcoded three DeepSeek ids that `/v1/models` does not
  return, so the selector offered models that could never answer. The catalog is
  now correct and reconciled against the endpoint: a withdrawn id is marked
  stale rather than hidden, discovered chat models are appended, and the effort
  selector shows a human label and a description instead of a bare wire enum.
- **Saving a model dropped its context window and description**, which made the
  settings page write-only for those fields.
- **The visual harness hardcoded an absolute path** to one developer's checkout,
  so it could only run on that machine. A test now guards the shipping files
  against committed local paths.
- **The loop tests filled the checkout until they failed.** They ran the CLI
  with the repository as the working directory and the loop writes its run
  directories relative to that, so enough local runs exhausted the
  `unique_run_dir` cap and six tests began failing for an unrelated reason.
  `smcub loop` now takes `--root` and the tests isolate their runs.
- **A flaky redaction assertion** searched a whole ledger file for a short
  secret, so it failed whenever those letters fell inside the entry's random
  `ledger_id` -- about one run in fifty, and it looked like a privacy failure.
+- **`smcub workbench` served an interface that could not boot.** The documented
  front door for the local product did not mount `/api/trader/*`, the surface the
  interface reads every number through. The shell loaded, each request for its own
  data came back as the HTML page with status 200, and the user was told the local
  review service was unreachable while it was running. It now mounts the surface
  for one offline user under `--state-dir`; `smcub trader serve --mode hosted`
  remains the only entry point that resolves a platform identity per request.
  Found by driving the shipped command in a browser rather than by reading it.
- **The favicon was not in the wheel.** `workbench/web/assets/*` does not match a
  file at the web root, so an installed copy would have served a missing icon.
- **An assistant proposal could be promoted into a row the interface misread.** A
  promotion returned `rule_status` where a listed rule carries `status`, so the
  page had to special-case the response; it now returns the same shape as a list row.
+- **An assistant proposal could be promoted into a row the interface misread.** A
  promotion returned `rule_status` where a listed rule carries `status`, so the
  page had to special-case the response; it now returns the same shape as a list row.
- **The readable memory fragment kept secrets the ledger had removed.** An evidence
  note is free text a person or a model wrote, so it can carry a token, a phone
  number, or a local path. The JSON ledger entry was redacted by its helper, but
  the Markdown fragment was written from the raw argument -- so the copy a human
  reads and shares was the one that leaked. It now goes through the same redaction
  layer that docs/memory-loop.md requires, with a test asserting a token, a phone
  number, and a home path never survive into either file.


### Compatibility

- Existing v1 manifest, decision, outcome, evaluation, registry, case, ledger, memory, and mentor-fit artifacts remain supported.
- Existing commands remain supported; the control-plane commands and `capture-run` metadata options are additive.
- The core distribution still declares no runtime dependencies.

### Notes

- Hosted mode requires a `postgresql://` `--database-url` and refuses to fall
  back to a local file; `--database-url` in local mode is refused; a
  non-loopback bind requires `--token`; `smcub workbench` does not mount
  `/api/trader/*`. These refusals are deliberate.
- Broker direct-connect and read-only key sync, multi-user billing and quotas,
  Spaces and mentor-student mode, community features and leaderboards, realtime
  notification push, and a mobile client are deferred past v1 and recorded in
  `docs/trader-product.md` so they are not forgotten.
- A user's real trades, accounts, notes, and backtest runs live in the tenant
  store and are never committed to the repository. Repository fixtures, examples,
  and tests use toy offline data only.

The execution ban is absolute: the product does not place or cancel orders, modify a
broker account, or automate execution, and it is not financial advice.

- Screenshots, PDFs, and CSV originals never leave the machine. A payload carrying
  attachment material is refused, and there is no override switch in the interface.
- `smcub workbench` binds loopback by default; a non-loopback bind requires an
  explicit `--token`.

Safety remains `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.
