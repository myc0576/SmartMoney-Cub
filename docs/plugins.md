# Plugin Protocol

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

SmartMoney-Cub is built so that "everything is a plugin" without giving plugins the
ability to trade. The harness publishes a stable protocol, a reference plugin, and a
curated catalog. It does not bundle AKShare, TradingAgents, Qlib, vectorbt,
QuantStats, Backtrader, or ZVT.

## What automatic integration means here

A plugin that a user installs is found, validated, loaded, and injected
automatically. There is no "edit the core to add a data source" step.

| Step | Automatic? | Notes |
| --- | --- | --- |
| Discovery | Yes | Python entry points and explicit `--plugin-dir` paths |
| Validation | Yes | Manifest schema, safety declaration, API range, license field |
| Dependency resolution | Yes | `inject`; missing hard dependencies become `PENDING` |
| Activation | Yes | Gated by profile permissions and health check |
| Execution | Yes | Every result is wrapped in an Evidence Envelope |
| Installation | No | User-initiated; workbench can install into a dedicated venv upon explicit per-item confirmation |
| Downloading | No | Only via verified curated catalog whitelist on explicit confirmation; never silent background fetching |
| Enabling network or a model | No | Requires an explicit profile, credentials confirmation, or flag |

## Layer model

The design follows the same three-layer separation that DeepSeek Harness uses:
definition, provider, consumer.

| Layer | Responsibility | May depend on |
| --- | --- | --- |
| Service definition | Stable request and result types for one capability | Nothing |
| Provider | One implementation of a capability | Its own project only |
| Consumer | Uses a capability by name | The definition only |

Because a consumer never imports a provider, replacing a provider requires no
change to the consumer. That is what makes an external project swappable.

```python
from smartmoney_cub_harness.plugins import BaseConsumer, CapabilityName

class ReviewDashboard(BaseConsumer):
    required_services = (CapabilityName.TRADE_IMPORT,)
    optional_services = (CapabilityName.MARKET_CONTEXT,)

    def render(self, request):
        return self.call(CapabilityName.TRADE_IMPORT, request)
```

## Capabilities

| Capability | Purpose |
| --- | --- |
| `trade_import` | Normalize broker or 同花顺 fills into a position ledger |
| `market_context` | Read-only regime or sentiment context |
| `reviewer` | Produce review observations |
| `challenger` | Produce counter-arguments and rule candidates |
| `evaluator` | Evaluate a candidate against point-in-time samples |
| `replay` | Reconstruct a frozen decision context |
| `report_renderer` | Render local artifacts |
| `memory` | Store portable text memory |
| `llm_provider` | Optional external model access |
| `agent_bridge` | Bridge a local external agent as review evidence |

There is deliberately no `order`, `cancel`, `account`, or `execution`
capability. A manifest that declares one is rejected at load time.

## Manifest

Every plugin ships a `plugin.json`. The reference file is
[examples/toy_plugin/plugin.json](../examples/toy_plugin/plugin.json).
The machine-readable schema is
[schemas/plugin-manifest.schema.json](../schemas/plugin-manifest.schema.json).

| Field | Required | Meaning |
| --- | --- | --- |
| `schema` | Yes | `smartmoney_cub_plugin_manifest.v1` |
| `plugin_id` | Yes | Stable identifier; duplicates are rejected |
| `name`, `version` | Yes | Identity and version recorded in evidence |
| `source_repo` | Yes | Upstream project |
| `source_commit` / `source_tag` | Recommended | Exact provenance |
| `license` | Yes | Upstream license |
| `kind` | Yes | `entry-point`, `local-path`, `subprocess`, or `companion` |
| `trust_level` | Yes | `core`, `review-only`, `data-network`, `untrusted-external` |
| `api_range` | Yes | Compatibility range, for example `>=1,<2` |
| `capabilities` | Yes | Non-empty list of capability names |
| `data_time_semantics` | Yes | `point_in_time`, `historical_export`, `live_fetch`, `derived_static` |
| `required_services` / `optional_services` | No | Dependency seams |
| `network_required` | No | Defaults to false |
| `credential_requirements` | No | Names only; values stay in the user's environment |
| `supported_markets` | No | For example `CN-A` |
| `safety` | Yes | Must be `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` |

## Lifecycle and Status Vocabulary

```text
AVAILABLE -> [PERMISSIONS_CONFIRMED] -> INSTALLED (in dedicated venv/sources) -> ENABLED/DISABLED -> HEALTH_CHECKED
   -> ACTIVE -> EXECUTED -> EVIDENCE_WRAPPED -> REVIEWED
   -> UNINSTALLED / REVOKED
PENDING  (a required service is missing)
FAILED / ERROR (a health probe, installation, or execution raised)
BLOCKED  (high execution risk or the active profile does not permit permissions)
```

### Market States

The workbench and catalog contract define five explicit market states:

| State | Meaning |
| --- | --- |
| `AVAILABLE` | The plugin is cataloged and available for installation, but not yet downloaded or installed. |
| `INSTALLED` | The plugin package has been fetched into the dedicated venv (or cloned into `sources/`), passes health check, but is currently inactive. |
| `ENABLED` | The plugin is active and available for invocation in workflows. |
| `DISABLED` | The plugin is installed but intentionally disabled by the user or profile. |
| `ERROR` | A health probe, installation step, or execution failed, or the entry is in an invalid state. |

Activation registers providers as reversible effects. Deactivation runs those
disposers in reverse order, so no consumer keeps a reference to a provider that is
no longer loaded. Removing a plugin revokes the entry while keeping its audit trail.

## Isolation and permission honesty

Third-party projects default to a report-only subprocess provider. A subprocess
plugin receives one JSON request on stdin and returns one JSON object on stdout.

Declared permissions are a statement, not a sandbox attestation. Doctor output and
every envelope therefore report `enforcement: declarative` and `verified: false`.
Place untrusted code in an operating-system or container sandbox before running it.

## Evidence Envelope

Every execution returns a wrapped envelope rather than a bare result:

- plugin id, version, and source reference;
- input and output SHA-256;
- decision time and available time;
- data source and data quality;
- whether network or a model was used;
- declared permission state;
- the normalized `result_kind`, which separates facts, statistics, model opinions,
  and user records;
- `champion_mutated: false` and `core_rules_mutated: false`.

An output whose `available_at` is after `decision_time` raises instead of being
recorded. That single check prevents most look-ahead mistakes.

## Command line

```bash
smcub plugin list   --plugin-dir examples/toy_plugin
smcub plugin inspect examples/toy_plugin/plugin.json
smcub plugin doctor  --plugin-dir examples/toy_plugin
smcub plugin install ./my-plugin          # registers a local path, never downloads
smcub plugin enable  toy.review-tagger --plugin-dir examples/toy_plugin
smcub plugin run     toy.review-tagger \
  --request request.json \
  --decision-time 2026-09-10T15:00:00+08:00 \
  --available-at  2026-09-10T14:00:00+08:00 \
  --workspace-db state/workspace/review.db --case-id CASE-1
smcub plugin logs    toy.review-tagger
smcub plugin disable toy.review-tagger
smcub plugin remove  toy.review-tagger
smcub plugin catalog

smcub profile show default-offline
smcub profile dump --output profiles.json
smcub profile reload --plugin-dir examples/toy_plugin
```

### Installation Channels and Workbench Wizard

The harness provides two installation avenues:

1. **CLI Local Registration**: `smcub plugin install <local-dir>` registers an existing local directory or manifest path.
2. **Workbench Installation Wizard (Dedicated venv & Whitelist)**:
   The review workbench provides an interactive, human-gated installation flow for curated catalog plugins:
   - **Catalog Whitelist Enforcement**: Only entries present in the curated catalog whitelist (`catalog_index()`) can be installed. Arbitrary URLs or unauthorized packages are strictly rejected.
   - **Absolute Execution Ban on High Risk**: Catalog entries marked with `execution_risk: "high"` (such as vn.py, which contains order placement and account manipulation capabilities) are **never installed** under any circumstance. The installer immediately refuses them.
   - **Explicit Permission Confirmation**: Installation cannot proceed without explicit human consent to the `READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` boundary.
   - **Dedicated Virtual Environment (`.plugins/venv`)**: PyPI-based plugins are installed into an isolated dedicated virtual environment, avoiding pollution of the core runtime.
   - **Dedicated Sources Directory (`.plugins/sources`)**: Git-based plugins are cloned into an isolated sources directory with health probes verified.
   - **Health Checks & Probes**: Immediately following download/install, a non-mutating health check (`probe`) verifies that the declared module can be imported cleanly. If the probe fails, the installer reports `ERROR`, rolls back changes, and surfaces the failure.
   - **Clean Uninstallation**: Uninstallation cleanly removes packages from the dedicated venv or deletes cloned directories while preserving audit logs.

Pass `--workspace-db` to `plugin run` to persist the wrapped envelope into the review
workspace, optionally linked to a case with `--case-id`.

## Profiles

| Profile | Network | External model | Contents |
| --- | --- | --- | --- |
| `default-offline` | No | No | Offline core only |
| `a-share-review` | No | No | Offline core plus A-share review helpers |
| `research` | No | No | Adds disabled evaluation and replay slots |
| `ai-optional` | Yes | Yes | Adds disabled LLM and agent bridge slots |

Composition is ordered bundles plus user patches. Because entries have stable ids,
a patch keeps applying to the same logical slot even when providers change.

## Curated catalog

`smcub plugin catalog` lists external projects with three integration levels:

- `companion` — documentation only; nothing is executed.
- `adapter` — wraps external output into an Evidence Envelope, preferably as a
  report-only subprocess.
- `runtime-plugin` — a manifest, tests, permission declarations, safety docs,
  and a health check exist.

Execution frameworks such as vn.py are not listed in the official marketplace.
A catalog entry is never a bundled dependency. The installer still refuses any
entry with high execution risk as a defense in depth.

Credential fields come from catalog metadata, never an invented generic API key.
TuShare and FRED link to their official key pages. TradingAgents is configured
externally using its upstream instructions; this journal neither requests nor
stores its provider keys. Local managed credentials are saved only after an
installation passes its health check.

## Schemas

| Schema | Purpose |
| --- | --- |
| [plugin-manifest.schema.json](../schemas/plugin-manifest.schema.json) | Plugin declaration and the capability names it may not use |
| [plugin-evidence-envelope.schema.json](../schemas/plugin-evidence-envelope.schema.json) | Wire shape of wrapped plugin output |

## Writing a plugin

1. Copy [examples/toy_plugin](../examples/toy_plugin) as a starting point.
2. Describe the plugin in `plugin.json`. Keep `network_required` false unless the
   plugin genuinely must reach the network.
3. Implement the provider. For a subprocess plugin, read JSON from stdin and write
   JSON to stdout.
4. Validate with `smcub plugin inspect plugin.json`.
5. Run it with `smcub plugin run` and confirm the envelope has no error and reports
   the expected `result_kind`.
6. Add tests covering success, a missing dependency, a future-data refusal, and a
   failure that must stay visible.

## What plugins must not do

- Place, cancel, or simulate orders; modify accounts; automate a broker.
- Present a model opinion as a fact, a statistic, or a signal.
- Write champion rules. A plugin may only propose a candidate.
- Read credentials, cookies, or account identifiers, or write them into artifacts.
- Require network access or an external model without an explicit user opt-in.
- Claim sandbox verification that the harness has not performed.
