# Plugin Development Guide

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

This guide walks through building an out-of-tree plugin that the harness finds and
mounts without any change to the core repository.

## 1. Choose a capability

Pick the narrowest capability that describes your output. Available seams are
`trade_import`, `market_context`, `reviewer`, `challenger`, `evaluator`,
`replay`, `report_renderer`, `memory`, `llm_provider`, and `agent_bridge`.

If your project only produces an analysis narrative, `reviewer` or `challenger`
is correct. Those two are automatically marked review-only in the Evidence
Envelope, which prevents the output from being read as a signal.

## 2. Write the manifest

```json
{
  "schema": "smartmoney_cub_plugin_manifest.v1",
  "plugin_id": "acme.quantstats-report",
  "name": "QuantStats Report Adapter",
  "version": "0.1.0",
  "source_repo": "https://github.com/ranaroussi/quantstats",
  "source_commit": "PUT_THE_RESOLVED_COMMIT_HERE",
  "license": "Apache-2.0",
  "kind": "subprocess",
  "trust_level": "review-only",
  "api_range": ">=1,<2",
  "entrypoint": ["python3", "-m", "acme_quantstats_provider"],
  "capabilities": ["report_renderer"],
  "required_services": [],
  "optional_services": [],
  "required_permissions": [],
  "network_required": false,
  "credential_requirements": [],
  "supported_markets": ["CN-A"],
  "data_time_semantics": "historical_export",
  "provenance_policy": "evidence_envelope_required",
  "safety": "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"
}
```

Record the exact commit or tag you validated against. Doctor output warns when a
plugin omits both, because an unpinned adapter cannot be reproduced later.

## 3. Implement the provider

A subprocess provider reads one JSON request from stdin and writes one JSON object
to stdout. Anything written to stderr is treated as diagnostics and is truncated
into the failure message.

```python
import json
import sys

SAFETY = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"


def main() -> int:
    request = json.loads(sys.stdin.read() or "{}")
    stats = compute_stats(request.get("returns") or [])
    sys.stdout.write(json.dumps({
        "stats": stats,
        "sample_size": len(request.get("returns") or []),
        "statistical_limits": "Self-selected review sample; not a controlled study.",
        "safety": SAFETY,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Return the honest sample size alongside any performance number. A report that omits
its sample size invites a user to over-read a small sample.

## 4. Declare time semantics accurately

| Declaration | Use when |
| --- | --- |
| `point_in_time` | The value was genuinely known at that timestamp |
| `historical_export` | The data is a settled historical record |
| `live_fetch` | The plugin retrieves data at run time; requires network opt-in |
| `derived_static` | The output is computed from bundled or fixed inputs |

The harness refuses an execution whose `available_at` is later than
`decision_time`. If your plugin fetches with a delay, pass the real publication
time as `available_at`; if that lands after the decision, the run is correctly
blocked rather than silently accepted.

## 5. Validate locally

```bash
smcub plugin inspect ./plugin.json
smcub plugin doctor  --plugin-dir . --state-db state/plugins/dev.db
smcub plugin run acme.quantstats-report \
  --capability report_renderer \
  --request request.json \
  --decision-time 2026-09-10T15:00:00+08:00 \
  --available-at  2026-09-10T15:00:00+08:00 \
  --data-source quantstats_report \
  --result-kind statistical_result
```

Confirm the envelope reports the result kind you intended. A statistical result and
a model opinion are displayed differently and carry different trust implications.

## 6. Handle failure honestly

Exit non-zero, or return an object that the harness cannot mistake for success. A
timeout, a missing dependency, a schema mismatch, and partial output must all leave
a visible error. Never return an empty success payload to hide a failure.

The harness records the failure in the envelope with `output_sha256: null` and
moves the plugin to `FAILED`, so a broken plugin cannot quietly produce clean-looking
evidence.

## 7. Declare permissions truthfully

List what your plugin actually needs. If it needs network access, set
`network_required: true`; the plugin will then be `BLOCKED` under offline profiles
until the user opts in. List credential names in `credential_requirements`, and read
values only from the environment at run time. Never write a key into output,
stdout, an artifact, or a fixture.

## 8. Test checklist

Include tests for:

1. a valid run producing a well-formed envelope;
2. a missing hard dependency leading to `PENDING`;
3. network or credentials blocked under an offline profile;
4. `available_at` after `decision_time` being refused;
5. a provider failure staying visible rather than degrading to success;
6. a capability that would imply order or account access being rejected.

## 9. Publishing

An out-of-tree plugin can advertise itself through the
`smartmoney_cub.plugins` entry point group so discovery works after a normal
`pip install`. The harness lists installed entry points during discovery but does
not import, download, or enable them automatically.

An `entry-point` plugin loads in process, so it must declare `trust_level` as
`core` or `review-only`. The entry point target must be a callable or a provider
object, and the capabilities it returns must already be declared in the manifest;
a provider that returns an undeclared capability is ignored and the reason is
recorded. `untrusted-external` plugins must use `subprocess` instead.

Users install, enable, and disable plugins explicitly:

```bash
smcub plugin list
smcub plugin install ./my-plugin          # local path only; remote URLs are refused
smcub plugin enable acme.quantstats-report --profile a-share-review
smcub plugin disable acme.quantstats-report
```

Installation registers the plugin and leaves it disabled, so a newly added plugin
cannot affect a review until the user turns it on.
