# Offline Arbitrum evidence implementation plan

Goal: extend the existing evidence replay CLI with a separately versioned, fully offline Arbitrum One single-transaction evidence pack and deterministic claim evaluation.

Non-goals: RPC collection, wallets, signatures, orders, UI, trading advice, profit/strategy/balance/intent proof, current chain finality, OHLCV trainer changes, public benchmark changes, publication or deployment.

## Frozen Definition of Done

- [ ] Independent `smartmoney_cub_onchain_evidence_pack.v1` format; existing D1/D3 v1 remains compatible (existing tests).
- [ ] Frozen transaction, optional receipt, block, structured claims, provenance and timezone-aware observed/available times are sealed; offline replay is deterministic (unit/CLI tests).
- [ ] Chain ID 42161, hash/number/index associations, block membership, log uniqueness and explicit event layouts are validated (negative tests).
- [ ] sender, recipient, execution status and explicit contract event claims return supported/contradicted/insufficient_evidence with reasons and evidence locations; unsupported semantics remain insufficient (unit tests).
- [ ] Pre-decision evidence cannot use future information; post-decision evidence is explicitly distinguished (boundary tests).
- [ ] Corruption, omitted files, duplicate JSON keys, malformed versions, traversal and links fail closed; unavailable receipt differs from missing file (security tests).
- [ ] Safe/finalized are capture-time provider observations only; seal asserts internal consistency only (reports/docs/tests).
- [ ] A toy example imports and replays without network and without credentials (CLI smoke).
- [ ] `./scripts/dev-env.sh test`, `./scripts/dev-env.sh verify` and doctor run, with exact outcomes reported; doctor includes READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE.
- [ ] Independent review addresses correctness/security/regressions; original working directory stays unchanged; deliver local branch/commit and verification evidence.

Max repair iterations: 5; never weaken these criteria to manufacture completion.

## Interfaces and work order

1. Core module `src/smartmoney_cub_harness/onchain_evidence.py` and `tests/test_onchain_evidence.py`: tests first, demonstrate expected failures, then implement `build_onchain_evidence_pack(output_dir, snapshot)` and `replay_onchain_evidence_pack(pack_dir)`. Constants live in this module, keeping the original schema constants unchanged. Invalid inputs raise ValueError at import; invalid replay returns an invalid report, no claim verdicts. Valid replay uses evidence_status=verified (internal consistency), includes claims and explicit limitations. Standard library only.
2. Frozen import snapshot schema `smartmoney_cub_onchain_snapshot.v1`: integer chain_id, decision_time, evaluation_mode (`pre_decision`/`post_decision`), transaction/receipt/block provenance envelopes, claims, optional capture-time finality observation, safety. Envelope has source, observed_at, available_at, evidence_role, data. receipt may explicitly be null. Known claim types sender/recipient/execution_status/event; event initial layout is erc20_transfer. Unsupported types are preserved and evaluated insufficient_evidence. Core owner specifies exact final details before documentation/schema authoring.
3. Existing `evidence_pack.replay_evidence_pack` dispatches only exact known schema versions after safe manifest/seal handling; retain v1 implementation and report behavior. CLI adds `build-onchain-evidence-pack OUTPUT --snapshot FILE` and reuses `replay-evidence-pack PACK`. Focused CLI tests cover errors, all verdicts, determinism, and network denial.
4. `schemas/onchain*.schema.json`, toy input, and focused documentation describe actual contract and commands. Existing public benchmark corpus and trader replay remain untouched.
5. Run existing/new tests and mandatory scripts; record evidence in ignored `ledger.md` and artifacts. Independent whole-change review; repair findings with regression tests before local commit.

## Review focus

Receipt omission versus referenced-file deletion; ERC-721/20 shared Transfer signature; pre-decision availability and observation cutoffs; rooted path/ADS/symlink/junction escapes; downgrade or unknown-version dispatch; report write links; contradictory failed receipts with emitted logs; stable no-network evaluation.
