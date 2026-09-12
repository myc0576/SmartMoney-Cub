# Changelog

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
