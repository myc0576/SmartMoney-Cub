# Offline Arbitrum transaction evidence

The onchain evidence format freezes one Arbitrum One transaction, its block, an
optional receipt, and structured Agent claims for deterministic offline review.
It is independently versioned from the existing D1/D3 price-outcome Evidence Pack:

- Import snapshot: `smartmoney_cub_onchain_snapshot.v1`.
- Sealed pack manifest: `smartmoney_cub_onchain_evidence_pack.v1`.
- Safety declaration: `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

The existing `replay-evidence-pack` command dispatches by the exact manifest
schema version. Unknown versions fail validation. D1/D3 v1 behavior, the OHLCV
trainer in `trader/replay.py`, and the public four-track benchmark are unchanged.

## Run the toy example

After installing the project in the active Python environment, run from the
repository root:

```bash
python -m smartmoney_cub_harness.cli build-onchain-evidence-pack tmp/onchain-demo --snapshot examples/onchain/toy_snapshot.json
python -m smartmoney_cub_harness.cli replay-evidence-pack tmp/onchain-demo
```

The output directory must not already exist. Use a new directory name when
repeating the build. Replay reads only local frozen evidence and writes the local
replay report; it does not request RPC data, contact the provenance source, access
a wallet, sign messages, place orders, cancel orders, or trade. Credentials and
network access are unnecessary.

Every address, transaction hash and block hash in the example is **synthetic toy
data**. The `toy://synthetic-offline/...` sources name local fixture provenance;
they are not RPC endpoints. The captured `safe` tag is fabricated example data.
The sample is a post-decision review with these expected results:

| Claim ID | Claim | Expected verdict |
|---|---|---|
| `sender_matches` | Transaction sender equals the toy sender | `supported` |
| `recipient_differs` | Transaction recipient equals a different toy address | `contradicted` |
| `execution_succeeded` | Receipt status is success | `supported` |
| `transfer_emitted` | The named contract emitted the specified ERC-20 Transfer layout and arguments | `supported` |
| `profit_not_proven` | The transaction was profitable | `insufficient_evidence` |

## Snapshot contract

[`onchain_snapshot.schema.json`](../schemas/onchain_snapshot.schema.json) describes
the import structure. Its root contains exactly `schema`, `chain_id`,
`decision_time`, `evaluation_mode`, `transaction`, `receipt`, `block`, `claims`,
`finality_observation`, and `safety`. `chain_id` is the integer `42161`, and the
transaction's RPC `chainId` is the canonical quantity `0xa4b1`.

Transaction and block are mandatory evidence envelopes. Receipt and finality
observation may explicitly be `null`. Each non-null envelope contains exactly:

| Field | Meaning |
|---|---|
| `source` | Non-empty, retained provenance label; never fetched during replay |
| `observed_at` | Provider observation/capture timestamp |
| `available_at` | Timestamp when the captured evidence was available |
| `evidence_role` | `pre_decision` or `post_decision` |
| `data` | Frozen RPC-shaped object, or the finality observation object |

All timestamps require the RFC 3339 shape
`YYYY-MM-DDTHH:mm:ss[.fraction](Z|+HH:mm|-HH:mm)` and a valid explicit timezone.
Fractional seconds allow at most six digits. Unknown offset `-00:00`, invalid
offset components (such as `+00:60`), and leap seconds are rejected.
Comparisons use the represented instant, including UTC offsets.
`available_at <= observed_at` is required for every envelope.

`evaluation_mode` specifies the review perspective:

- `pre_decision` uses only envelopes labeled `pre_decision`. Both their
  `available_at` and `observed_at` must be at or before `decision_time`; equality
  is allowed. An envelope falsely labeled as pre-decision while either timestamp
  exceeds the cutoff is invalid, even in a post-decision review.
- `post_decision` can use explicitly labeled post-decision evidence. This is
  retrospective review, not evidence that an Agent possessed the information at
  its original decision. Post-decision envelopes do not support pre-decision
  claims merely because a transaction or block timestamp is older than the cutoff.

Unavailable evidence in the selected perspective yields `insufficient_evidence`.
Changing timestamps, roles, or the review perspective changes sealed input and
requires rebuilding the pack. A seal does not establish that those timestamps
are truthful.

RPC quantities use canonical lowercase hexadecimal strings: `0x0`, or `0x`
followed by a nonzero hexadecimal digit and remaining lowercase hexadecimal
digits. Leading zeros and JSON numeric substitutes are rejected. Hashes are
32 bytes and addresses 20 bytes, with a lowercase `0x` prefix; hexadecimal
letters may use either case and comparisons are case-insensitive.

The runtime additionally checks the relationships that a structural JSON Schema
cannot establish:

- Transaction, receipt and block hashes/numbers agree; the block transaction at
  `transactionIndex` is this transaction's hash.
- Every log belongs to this transaction and block, has a unique `logIndex`, and
  has `removed: false`. Conflicting, transplanted or removed logs invalidate the
  evidence. A failed receipt must not contain emitted logs.
- Claim IDs are unique. Pre-decision provenance meets the cutoff and all
  provenance timestamps have valid ordering.
- A finality observation references the captured block. It contains exactly
  `tag` (`safe` or `finalized`), `blockHash`, and `blockNumber` in its `data`.

Additional RPC fields are retained in transaction, receipt, block and log data;
they do not silently introduce new claim evaluators. Use the runtime validator
for complete validation. The published schemas are self-contained and require
no remote schema lookup; a separate JSON Schema tool must enable date-time
format checking to check calendar validity.

Recognized optional RPC quantity and address fields are also validated when
present. Block `nonce` is an eight-byte hexadecimal value; transaction, receipt
and log `nonce`, when supplied, use the canonical quantity format. Block
transaction hashes must be unique, including case-insensitive duplicates.

## Claims and verdicts

Each claim requires a unique non-empty `id` and non-empty `type`. Supported claim
forms are:

```json
{"id":"sender","type":"sender","value":"0x1111111111111111111111111111111111111111"}
{"id":"recipient","type":"recipient","value":null}
{"id":"status","type":"execution_status","value":"success"}
{"id":"transfer","type":"event","event_type":"erc20_transfer","contract":"0x3333333333333333333333333333333333333333","from":"0x1111111111111111111111111111111111111111","to":"0x2222222222222222222222222222222222222222","value":"0x2a"}
```

`recipient: null` means the transaction's `to` is null, as in contract creation;
it does not substitute `receipt.contractAddress`. Execution status accepts
`success` or `failure`, corresponding to receipt `0x1` or `0x0`. Success records
only the receipt's execution status, not business success or profitability.

An `erc20_transfer` claim binds the emitting contract and the full explicit
`Transfer(address,address,uint256)` layout: signature topic, exactly three
topics, zero-padded indexed `from` and `to` addresses, and exactly one 32-byte
unsigned value in `data`. Claim `value` is an unscaled uint256 hexadecimal
quantity; token decimals, symbols, balances and economic meaning are not inferred.
ERC-721 uses the same signature but a different indexed layout, so signature
matching alone is insufficient.

| Verdict | Meaning |
|---|---|
| `supported` | Eligible evidence directly matches the supported claim |
| `contradicted` | Eligible evidence directly disagrees, or a complete receipt has no matching supported event |
| `insufficient_evidence` | Required evidence is unavailable for this perspective, the claim/type is unsupported, or the relevant event layout cannot be safely interpreted |

If a relevant contract/signature log has an unsupported layout and no complete
ERC-20 match exists, the event result is insufficient evidence. A complete
receipt with no relevant contract/signature log contradicts that event claim.
Unknown claim types and unknown `event_type` values remain visible with an
insufficient-evidence result. They are not silently dropped. Known claim forms
reject unexpected fields rather than ignoring constraints the caller intended.

Every valid-pack claim result includes `verdict`, `reason`, and
`evidence_locations`, so the reader can trace the conclusion into the frozen
files. Once dispatched to the onchain validator, invalid evidence produces
`evidence_status: "invalid"` and no claim verdicts. Failures before a sealed
format can be recognized (such as a missing/bad manifest seal or unknown version)
retain the shared dispatcher's `pending_review` failure report. Both fail the CLI
with exit code 2; corruption is never interpreted as a contradicted claim.

A valid replay exits 0 even if individual claims are contradicted or have
insufficient evidence: that exit code confirms a valid replay, not that every
Agent claim is true. Import also exits 2 on invalid input and refuses to overwrite
an existing output directory.

## Pack layout and integrity

[`onchain_evidence_pack.schema.json`](../schemas/onchain_evidence_pack.schema.json)
describes the manifest. A built pack contains:

```text
evidence_pack.json      manifest, source times via file hashes, finality observation
evidence_pack.sha256    SHA-256 seal of the manifest bytes
transaction.json       {"evidence": <transaction envelope>, "safety": <declaration>}
receipt.json           {"evidence": <receipt envelope or null>, "safety": <declaration>}
block.json             {"evidence": <block envelope>, "safety": <declaration>}
claims.json            {"claims": [...], "safety": <declaration>}
replay_report.json     generated by replay; not an evidence input
```

The manifest has an exact fixed `files` mapping and four lowercase SHA-256
digests in `hashes`. The seal covers the exact manifest bytes, which bind the
file digests and all other evaluation inputs. The receipt artifact is required
even when its evidence is `null`: an intentionally unavailable receipt is valid,
while a missing file is invalid.

Replay rejects missing or altered files, duplicate JSON keys, nonstandard JSON
numbers, unknown versions, invalid associations, unsafe paths, and symbolic
links. UNC/network/device paths are rejected before filesystem access so replay
does not trigger a network file lookup. It does not follow arbitrary paths
supplied in a manifest. Repeated
replay of unchanged input is deterministic and does not update observations
from the network.

`evidence_status: "verified"` means the pack passed structural, association and
seal checks. The seal proves internal consistency, **not** provider authenticity,
transaction signature validity, recomputation of real transaction/block hashes,
or current chain inclusion/finality. A party able to change the whole pack can
also recompute its hashes; there is no trusted signature or external trust anchor.

A `safe` or `finalized` value is only a provider's claim at the captured
observation time. Neither a successful receipt, a frozen hash, nor an internally
consistent pack establishes the current canonical chain or current finality.
This evaluator cannot prove profit, strategy correctness, actual asset balances,
or transaction intent. It makes no trading recommendation.

## Validation workflow

```bash
./scripts/dev-env.sh test
./scripts/dev-env.sh verify
python -m smartmoney_cub_harness.cli doctor
```

Doctor and generated safety-bearing artifacts must retain
`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`. The example is an offline fixture only;
real trading records, account identifiers and private evidence must stay out of
repository fixtures and public commits.
