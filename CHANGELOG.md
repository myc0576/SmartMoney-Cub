# Changelog

## 1.0.0

The convergence release: a local-first review workbench with a review assistant, an
import pipeline that parses broker files on the machine, and an outbound policy that
redacts identity and exact size before any provider request.

### Added

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

### Changed

- The interface ships inside the wheel and uses no CDN, no remote font, and no
  external asset.
- A combined broker fee column is now read as a declared fee instead of being ignored
  and replaced by an estimate.
- A model provider without a usable key falls back to local review instead of sending
  an unauthenticated request.
- Profit factor is documented and reported as gross profit over absolute gross loss,
  and reads as undefined when a sample has no losing trade.

### Notes

- Screenshots, PDFs, and CSV originals never leave the machine. A payload carrying
  attachment material is refused, and there is no override switch in the interface.
- `smcub workbench` binds loopback by default; a non-loopback bind requires an
  explicit `--token`.

Safety remains `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

## Unreleased

### Added

- Plugin protocol for read-only external integrations: manifest schema and validator, service definition / provider / consumer seams, `inject` dependency resolution, profile-bundle-patch composition, lifecycle states, reversible effects with disposers, subprocess isolation, capability catalog, and Evidence Envelopes.
- `smcub plugin list|inspect|enable|disable|remove|doctor|run|logs|catalog` and `smcub profile show|dump|reload`.
- SQLite review workspace with the non-silent observation contract, D1/D3 outcomes that never rewrite a frozen case, validated plugin evidence, and human-gated champion rule state via `smcub workspace ...`.
- Position ledger for broker and 同花顺 CSV exports with batched fills, partial closes, cross-day positions, T+1, fees, oversell, duplicate rows, limit-board, and suspension flags. Ambiguity is reported as `needs_review` instead of becoming a silent trade.
- Static, privacy-reduced share pack with identifier, path, and credential auditing plus a SHA-256 seal via `smcub share-pack`.
- Reference subprocess plugin at `examples/toy_plugin`, plus `docs/plugins.md`, `docs/plugin-development.md`, `docs/review-workspace.md`, and `docs/share-pack.md`.

### Changed

- Dashboard CSV import now uses the position ledger and surfaces blocking issues instead of pairing fills with naive FIFO.
- Dashboard promotion is a two-step request plus explicit confirmation with a written note; sample-size gates apply and no performance numbers are fabricated on promotion.
- Dashboard labels demo fixture data as DEMO and refuses to execute a disabled plugin.
- Fixed the documented toy control-plane sequence: build-outcome now resolves the packaged price-source reference the toy loop records, instead of the stale examples path.

### Compatibility

- Existing v1 manifest, decision, outcome, evaluation, registry, case, ledger, memory, and mentor-fit artifacts remain supported.
- New commands are additive. The core distribution still declares no runtime dependencies.

Safety remains `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

## Unreleased (continued)

### Added

- Run Envelope v1 for external-Agent provenance, reconciled offline tool results, output evidence paths, fixed permissions, and failure status.
- Evidence Pack v1 for frozen D1/D3 samples, artifact hashes, review metrics, and deterministic replay.
- `validate-envelope`, Agent metadata options on `capture-run`, `build-evidence-pack`, and `replay-evidence-pack` CLI support.
- Challenger evidence states and an explicit human confirmation gate before champion registry mutation.
- Machine-readable schemas at `schemas/run-envelope.schema.json` and `schemas/evidence-pack.schema.json`.
- Explicit `declarative` / unverified Run Envelope permission semantics so provenance is not mistaken for subprocess sandbox enforcement.
- `evidence_pack.sha256`, fail-closed manifest validation, complete hash-inventory checks, and safe `pending_review` reports for invalid packs.

### Compatibility

- Existing v1 manifest, decision, outcome, evaluation, registry, case, ledger, memory, and mentor-fit artifacts remain supported.
- Existing commands remain supported; the new control-plane commands and `capture-run` metadata options are additive.

Safety remains `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.
