# Hermes CLI Integration

Local review material for the standalone copy at integrations/hermes-smartmoney-cub/. Nothing in this document has been published to Hermes, and it does not change the core CLI.

READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE

## Scope

The local plugin snapshot corresponds to the reviewed Hermes plugin pin 67e5a73d32fde4d0b68d3562a930064bf8b0d103 and catalog commit 799e7b94278d2e72c346716f5521e3fba2ae6de8. It exposes eight tools: six legacy review tools that invoke the real smcub CLI with argv lists, plus two protocol-gated tools:

- smcub_capabilities requires smcub capabilities --json to return schema=cli.capabilities.v1 and protocol_version=1.
- smcub_operation runs only an operation advertised by that response with --input JSON_FILE --principal hermes --state-dir ROOT --json --run-root RUNROOT.

The core owns operation authorization and PermissionStore enforcement. The plugin supplies principal=hermes as a fixed integration identity. state_dir and run_root are human configuration; they are not model arguments. The permissions.request operation is proposal-only. Hermes cannot grant or approve permissions, and an approval result from a provider is rejected.

The plugin rejects capability schema/version mismatches, duplicate or malformed operation names, networked operations, execution/account/order operations, and capability declarations that advertise permission-grant authority. It filters operation descriptors to non-secret, disclosed fields before returning them.

## Legacy CLI contract

The six existing tools remain real CLI calls:

| Tool | CLI argv and write disclosure |
| --- | --- |
| smcub_doctor | doctor; no plugin initiated database, cache, or network write |
| smcub_validate_envelope | validate-envelope -- PATH; no plugin initiated database, cache, or network write |
| smcub_build_evidence_pack | build-evidence-pack --sample=... --rule-candidate=... --horizon=d1 or d3 -- OUTPUT; writes rule_candidate.json, evidence_pack.json, evidence_pack.sha256, and samples/<id> descendants under output_dir |
| smcub_replay_evidence_pack | replay-evidence-pack -- PATH; may create or replace replay_report.json, including unsuccessful replay reports |
| smcub_evaluate_run | evaluate-run --horizon d1 or d3 -- PATH; may create or replace eval.json |
| smcub_inspect_artifacts | inspect-artifacts -- PATH; no plugin initiated database, cache, or network write |

All path-sensitive legacy inputs and outputs fail closed unless the human configures run_root. Resolution follows symlinks and checks existing parents; the positional path is placed after --. The plugin uses shell=False, accepts only d1 or d3, and reports database, cache, and network disclosures in every successful response. Host and Python runtime caches remain possible and are disclosed as such. run_root is an application-level path boundary, not an operating-system sandbox or protection against other processes changing paths concurrently.

The plugin SHA does not pin the user-installed smcub executable found on PATH or configured as smcub_command. The plugin therefore requires the capabilities protocol before any new operation and does not claim that an unpinned binary is safe. Current core parity is expected to fail closed until the core implements that protocol.

## Local verification

The focused test surface is:

    python3 -m pytest integrations/hermes-smartmoney-cub/tests/test_plugin.py tests/test_hermes_parity.py -q
    python3 integrations/hermes-smartmoney-cub/scripts/check_surface.py

The parity tests invoke the current working-tree core doctor, assert its safety declaration, verify the current core rejects the not-yet-present capabilities command, and exercise protocol and boundary behavior with an isolated executable stub. No network calls or real account data are used.

## Pending publishing draft

PENDING HUMAN REVIEW AND PUBLISHING: do not send or apply remotely.

### Catalog entry draft

    name: smartmoney-cub
    repo: https://github.com/myc0576/hermes-smartmoney-cub
    sha: PENDING_NEW_PLUGIN_PIN_AFTER_REVIEW
    description: >-
      Local-first SmartMoney-Cub review harness with six real smcub CLI tools and a
      cli.capabilities.v1, protocol_version 1 controlled operation bridge. Preserves
      READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE; no orders, cancels, account mutation,
      broker automation, or financial advice. State and run roots are human-configured;
      permissions.request is proposal-only. evaluate-run, build-evidence-pack, and
      replay-evidence-pack write their documented local review artifacts. The plugin
      makes no network requests of its own and does not claim an unpinned smcub binary
      is safe.
    maintainer: myc0576
    tier: community
    category: tools
    docs_url: https://github.com/myc0576/hermes-smartmoney-cub#readme
    requires_hermes: ">=0.19"
    version: "0.2.0"
    capabilities:
      provides_tools:
        - smcub_doctor
        - smcub_validate_envelope
        - smcub_build_evidence_pack
        - smcub_replay_evidence_pack
        - smcub_evaluate_run
        - smcub_inspect_artifacts
        - smcub_capabilities
        - smcub_operation
      provides_hooks: []
      provides_middleware: []
    requires_core_protocol:
      schema: cli.capabilities.v1
      protocol_version: 1
    requires_env: []

### Published PR state

Public read-only verification: Hermes PR #123396 is OPEN. Its current head/catalog commit is 799e7b94278d2e72c346716f5521e3fba2ae6de8, and the catalog pins plugin source 67e5a73d32fde4d0b68d3562a930064bf8b0d103. The PR body discloses evaluate-run, build-evidence-pack, and replay-evidence-pack writes, the unpinned user smcub binary, and the path boundary limitation. Current PR checks are empty; no passing CI claim is made. This public verification made no new remote writes.

This follow-up updates the standalone SmartMoney-Cub Hermes plugin after local parity review. It preserves the six legacy tools and adds a controlled operation bridge that requires cli.capabilities.v1 with protocol_version: 1 before each new operation. The bridge passes a fixed principal=hermes; the human-configured state_dir and run_root are never supplied by the model. permissions.request returns a proposal only, and Hermes cannot grant approval.

The plugin keeps real argv invocation, d1/d3 validation, -- path separation, fail-closed root checks, shell=False, and explicit disclosures for database, cache, network, and all three core file-writing commands, including replay_report.json. The local test slice covers the current core doctor and protocol mismatch plus isolated protocol, argv, secret-redaction, root-boundary, and permission-proposal guards. No core code, remote catalog, branch, or release is mutated by this local change.

The plugin SHA cannot pin the user-installed smcub executable, so the catalog retains the required core protocol statement and does not describe an unpinned binary as safe.
