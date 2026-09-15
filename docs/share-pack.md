# Share Pack

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

A share pack is a static, offline HTML summary of a review session that a user can
read locally and then choose to post in a GitHub issue, a discussion, or an article.
The harness audits it, seals it with a checksum, and never uploads it.

## Command

```bash
# Labelled demo data, safe to share as a workflow example
smcub share-pack --output tmp/share-pack --write

# Your own broker or 同花顺 CSV
smcub share-pack --csv exports/fills.csv --output tmp/share-pack --write
```

The command writes three files:

| File | Purpose |
| --- | --- |
| `share_pack.html` | The review summary; no external assets and no network calls |
| `share_audit.json` | The privacy audit result |
| `share_pack.sha256` | A local tamper check |

## What is reduced

| Field | Default policy | Effect |
| --- | --- | --- |
| Security code | `hash` | Replaced with a stable opaque id |
| Security name | `replace` | Replaced with `REDACTED` |
| Amounts | `coarsen` | Rounded to the nearest thousand |
| Timestamps | `date_only` | Intraday timing removed |

The policy is printed inside the pack so a reader can see exactly what was reduced.

## Privacy audit

Before writing, the pack content is scanned for emails, phone numbers, local
absolute paths, credential assignments, cookies, tokens, and account identifiers.
Any hit sets the audit status to `needs_review` and records the matched kind. The
audit never echoes a full secret back into the report.

## Demo versus real data

When no CSV is supplied, the pack uses the bundled toy case and embeds a visible
`DEMO` notice. That label is deliberate: demo figures must never be mistaken for a
user's real performance.

## Boundaries

- The pack contains no order, cancel, or account capability.
- The pack is a review artifact, not investment advice.
- The harness does not upload, post, or sync the pack anywhere.
- A `needs_review` audit is a warning to inspect the file, not an automatic
  blocker, because the user makes the final sharing decision.
