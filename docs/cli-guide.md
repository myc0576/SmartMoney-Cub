# CLI Guide

The guaranteed manual entry point for registered control operations is:

`smcub operation <operation-name> [options]`

Use `smcub capabilities` to list operation names. Grouped commands generated
from the same registry remain legacy-compatible where present, including
provider/provider**s**, connection/connection**s**, and plugin setup names.

Setup inspection accepts both singular and plural kinds:

`smcub operation providers.setup --provider-id deepseek --json`

`smcub operation connections.setup --provider-id ibkr-flex --json`

`smcub operation plugin.setup --plugin-id qlib-factor-evaluator --json`

Setup results contain status, required fields, next steps, and verified HTTPS
links. Secret fields use logical names such as `api_key`; values are never
returned. An environment reference is a separate non-secret descriptor, for
example `env_key=DEEPSEEK_API_KEY`. A default `base_url` is included as a
reusable descriptor when catalog metadata provides one.

Use `--configure --confirm` for the local human setup wizard. Hidden fields
are prompted interactively. Non-interactive setup accepts protected JSON from
`--input PATH` or `--input -` and supports environment references such as
`api_key_env`. Credential values must not be placed in argv or `--set`.
The wizard delegates provider and plugin changes to existing service APIs and
sends connection credentials through the read-only connection service.

Network operations require `--allow-network`. External verification remains
pending until the configured service verifies it. Catalog metadata, local files,
or an installed companion do not by themselves imply a usable adapter.
The safety contract is `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE`.

Use `--format html` or `--format csv` for dependency-free result exports.
HTML is a standalone escaped document with inline charts for existing market
bars, analytics equity curves, backtest equity curves, and equivalent series.
CSV includes scalar and nested metric rows, protects formula-like cells, and
includes a label/value series table. Rendering does not write files; use the
explicit output option when a saved artifact is required.

For a paid model call, setup status or a successful model-list probe proves only
that the route and key can be reached. It does not prove completion, usage,
billing, quota, balance, or a verified price. A real assistant.send call must
set --budget-usd, --pricing-file, and --max-provider-calls 1. The pricing JSON
maps the exact model ID to input_usd_per_million and output_usd_per_million;
use prices verified for the configured gateway account, because upstream vendor
prices do not prove a reseller charge. Without prices, usage, or cost evidence,
record the corresponding field as pending or unverified.

Connections manifests and setup metadata describe integration capability only.
Entries marked fixture-only or local-bridge-only do not establish a live
read-only authorization. Do not sync, paginate, resume cursors, or test
revocation until an actual authorized connection and read-only scope are
verified.

Live market bars with absent source timestamps or data-quality fields remain
pending even when a provider returned rows. Accept historical evidence only
with source, available_at, decision_time, quality, and available_at <=
decision_time.
