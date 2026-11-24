---
name: smartmoney-review
description: Guide an agent through a read-only SmartMoney-Cub review - configure human-owned roots, check the core capabilities protocol, validate artifacts, build and replay an evidence pack, and present the result to a human without turning it into a trading instruction.
---

# SmartMoney-Cub review workflow

Use this when the user asks to review a trade, journal a decision, or build a
reproducible record of a review run.

## The one rule

Every status this workflow produces is a **review** status. ALERT, WATCH,
AVOID, and any grade are descriptions of recorded context. None of them is an
instruction to buy or sell. Never convert one into an order, a size, or a
recommendation, and never tell the user what to trade.

## Steps

1. **Check the harness.** Call smcub_doctor, then smcub_capabilities. Require
   schema=cli.capabilities.v1 and protocol_version=1; if either is absent,
   stop and report the core protocol mismatch. If the CLI is missing, tell the
   user to install smartmoney-cub-harness rather than substituting your own
   numbers.
2. **Configure the boundary.** Set a non-empty run_root to the directory
   containing the offline run artifacts. Every path-sensitive tool fails closed
   without it and rejects paths that resolve outside it.
3. **Capture a run.** Ask the user to run the actual offline CLI themselves,
   for example: smcub capture-run --mode after-close --preset toy
   --agent-name hermes-user. The plugin does not run arbitrary commands on
   their behalf.
4. **Validate.** Call smcub_validate_envelope with the existing
   envelope_path below run_root. Stop and surface the error if validation fails.
5. **Build the pack.** Once delayed D1/D3 outcome data exists, call
   smcub_build_evidence_pack with existing run_dir and JSON rule_candidate,
   a confined output_dir, and horizon d1 or d3. SmartMoney-Cub creates the
   pack in that output directory.
6. **Replay.** Call smcub_replay_evidence_pack. Only a verified report means
   the pack is intact. A pending_review or blocked report is a stop sign.
7. **Inspect before presenting.** Call smcub_inspect_artifacts and report the
   sample count honestly. Never present a performance number without it.

For a capability-listed operation, call smcub_operation with only the operation
name and a confined JSON input file. The plugin supplies principal=hermes,
state_dir, run_root, and --json. permissions.request is proposal-only; Hermes
cannot approve it, and an approval must come from the core PermissionStore or a
human-controlled flow.

## Reporting

Always state the sample size next to any performance figure, name the horizon
(d1/d3), and say plainly that a small self-selected sample is not a
controlled study. If a promotion threshold is not met, say so instead of
softening it.

Preserve this declaration on anything you output:

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```
smcub_evaluate_run accepts only horizon d1 or d3 and writes eval.json in the
run directory. Build and replay also write their documented artifacts, including
replay_report.json on unsuccessful replay. The harness remains no-trading and
only updates the user's local review record.
