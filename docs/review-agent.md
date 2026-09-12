```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

The review assistant is the right-hand panel of the workbench. It is a local
session runtime with an optional model provider. It is read-only over your review
data, and there is exactly one write it can perform: proposing a challenger rule.

## Interaction model

- Sessions are stored locally with a title, context, provider, model, and status.
- Every turn is written to a local event log before it is streamed to the browser,
  so a refresh, a crashed tab, or a restarted server resumes the same conversation.
- The transcript shows user messages, assistant messages, and expandable tool-call
  cards with their arguments and results.
- A running turn can be stopped. Stopping does not delete what was already stored.
- A session can be forked, which copies the transcript into a new conversation.

## Providers

| Provider | Purpose |
| --- | --- |
| `alphatech` | The preconfigured company gateway at `https://alphatech.net.cn/v1` |
| `openai-compatible` | Any OpenAI-compatible endpoint you configure |
| `offline` | Local template review with no network request at all |

API keys are read from the environment first (`ALPHATECH_API_KEY`, `SMCUB_LLM_API_KEY`) and from a local
credentials file second. The credentials file is written with owner-only
permissions, and no response ever returns the key. The settings page reports only
whether a key exists and where it came from.

When no usable key is configured, the turn is answered from local data. The harness
never sends an unauthenticated request to a provider.

## What leaves the machine

Only a redacted, structured payload. Before any request:

| Item | Treatment |
| --- | --- |
| Account, holder, and customer values | Removed entirely |
| Names and direct identifiers | Replaced with a device-stable pseudonym |
| Security codes | Replaced with a device-stable pseudonym, including codes embedded in generated ids |
| Portfolio names | Replaced with a device-stable pseudonym |
| Exact quantities and amounts | Reduced to a range band |
| Prices | Reduced to a range band |
| Exact timestamps | Reduced to a 15-minute session bucket |
| Exact dates | Reduced to a month |
| Returns, holding periods, scores, and statistics | Kept, because the review depends on them |
| Credentials, secrets, emails, phone numbers, and local paths inside free text | Removed |

Pseudonyms are produced with HMAC-SHA256 over a per-device salt stored in the local
store. An alias is therefore stable on one machine, so history stays comparable,
and meaningless anywhere else.

Screenshots, PDFs, and CSV originals never enter a request. Two mechanisms enforce
that:

1. A payload containing a data URL, base64 blob, or attachment field is blocked
   outright.
2. The outbound path takes an explicit `attachments_present` flag, and a blocked request carries
   no payload at all instead of a partial one.

There is no override switch in the interface.

## Audit trail

Every attempt is recorded locally in `outbound_audit`:

- provider and model
- SHA-256 of the redacted payload
- the list of field paths that were sent
- a redaction summary counting how many values were replaced, by reason
- whether the request was blocked, and why

The audit records which fields were sent and never their values. The settings page
shows the most recent entries.

## Tools the assistant may call

`list_trades`, `get_trade`, `analytics_summary`, `calendar_month`, `open_positions`, `list_rules`, `list_review_cases`, `data_quality_report`, and `propose_challenger_rule`.

There is deliberately no shell, no arbitrary file write, no arbitrary network
access, and no broker or order tool. Tool results are redacted by the same policy
before they are sent back to the provider.

## Rule promotion

The assistant can create a challenger rule and nothing more. Promotion to champion
still requires the existing gate: minimum sample size, risk-condition checks, and
an explicit written human confirmation. A model cannot bypass that by writing to
the database, because the workspace layer refuses a champion row without a
confirmation note.
