# hermes-smartmoney-cub

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that exposes
[SmartMoney-Cub](https://github.com/myc0576/SmartMoney-Cub) as six review tools
and a protocol-gated operation bridge, for eight tools total.

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

SmartMoney-Cub is a read-only trading journal and review harness. It records
decisions, imports your own executions, computes analytics, and evolves rules
through challenger to champion governance. This plugin does not reimplement any of
that. It wraps the local `smcub` CLI so an agent can drive the review loop and
present evidence to a human.

## What it does not do

- It never places or cancels an order.
- It never connects to a broker or modifies an account.
- It never fetches market data on its own.
- It never returns financial advice, a price target, a position size, or a signal.
- It does not run arbitrary commands for you; capture-run stays yours to invoke.
- It does not choose `state_dir` or `run_root`; those are human configuration.
- It cannot grant or approve permissions. `permissions.request` can only return a
  proposal for the core PermissionStore or a human to decide.

An `ALERT`, `WATCH`, `AVOID`, or a `grade` value is recorded review context. It is
not an instruction to trade, and neither this plugin nor the harness will treat it
as one.

## Tools

| Tool | Purpose |
| --- | --- |
| `smcub_doctor` | Report harness health, version, and the safety declaration. |
| `smcub_validate_envelope` | Validate a `run_envelope.json` against the schema. |
| `smcub_build_evidence_pack` | Freeze a run plus delayed outcome into a hashed pack under `output_dir`. |
| `smcub_replay_evidence_pack` | Recompute a pack and compare against its hashes. |
| `smcub_evaluate_run` | Grade one run directory and write `eval.json` there. |
| `smcub_inspect_artifacts` | Report promotion readiness and the honest sample count. |
| `smcub_capabilities` | Read and validate `cli.capabilities.v1`, protocol version 1. |
| `smcub_operation` | Invoke one advertised operation with `principal=hermes`, JSON input, and configured roots. |

A bundled skill, `smartmoney-review`, walks the agent through the full loop and
enforces the reporting rules. Load it with `skill_view("smartmoney-cub:smartmoney-review")`.

## Requirements

- Hermes Agent 0.19 or newer.
- The harness CLI on your `PATH`:

  ```bash
  git clone https://github.com/myc0576/SmartMoney-Cub.git
  cd SmartMoney-Cub
  python -m pip install -e ".[dev]"
  smcub doctor
  ```

  The harness is not published on PyPI; install it from source or from the wheel
  attached to its GitHub Releases. Set `smcub_command` in the plugin settings if
  the executable lives somewhere else.

## Install

```bash
hermes plugins install myc0576/hermes-smartmoney-cub --enable
hermes plugins list
```

Or copy the directory into `~/.hermes/plugins/smartmoney-cub/`.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `smcub_command` | `smcub` | Command used to invoke the harness. |
| `timeout_seconds` | `120` | Per-invocation timeout. |
| `run_root` | empty | Required for every path-sensitive tool. Existing inputs and output directories must resolve inside this directory. smcub_doctor does not need it. |
| `state_dir` | empty | Required for `smcub_operation`; the core uses it for PermissionStore and related state. Hermes cannot override it. |

Path-sensitive tools fail closed when run_root is empty or when a resolved
path escapes it. A new output_dir is allowed only when its nearest existing
parent is inside run_root; symlink escapes, missing rule candidates, and
file paths used as directories are rejected. This is an application-level path
boundary, not an operating-system sandbox or protection against other processes
changing paths concurrently.

## Tool arguments

smcub_validate_envelope, smcub_replay_evidence_pack, and smcub_inspect_artifacts
take an existing path below run_root. smcub_evaluate_run requires run_dir and
horizon (d1 or d3) and writes eval.json in that run directory.

smcub_build_evidence_pack requires run_dir, output_dir, rule_candidate, and
horizon (d1 or d3). The rule candidate must be an existing JSON file below
run_root. SmartMoney-Cub writes rule_candidate.json, evidence_pack.json,
evidence_pack.sha256, and samples/<id>/ descendants under output_dir.

`smcub_operation` first calls `smcub capabilities --json` and requires an
exact `schema` of `cli.capabilities.v1` and `protocol_version: 1`. It rejects
operations that are absent, networked, permission granting, or outside the
read-only boundary. It then calls:

`smcub operation NAME --input JSON_FILE --principal hermes --state-dir ROOT --json --run-root RUNROOT`

`ROOT` and `RUNROOT` come from human plugin configuration. The model only
selects the advertised operation and an input file already confined to `run_root`.

## Safety notes

Handlers pass arguments to the CLI as a list with `shell=False`, so a path can
never be interpreted as a command. Every handler returns a JSON string and never
raises; a missing path, a missing CLI, and a timeout all come back as explicit
errors rather than a silent empty success.

The three core commands that write files are `evaluate-run` (`eval.json`),
`build-evidence-pack` (candidate, pack, seal, and sample descendants), and
`replay-evidence-pack` (`replay_report.json`, including unsuccessful reports).
Controlled operations may write core-declared artifacts under the configured
state/run roots. The plugin makes no network calls of its own; database and cache
use are disclosed in every successful response. Python and host runtime caches
may still be written. The plugin SHA does not pin the user-installed `smcub`
binary, so this local copy requires the core capabilities protocol before any new
operation and does not claim an unpinned binary is safe.

All tool responses preserve:

```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

## Development

```bash
python3 -m pytest tests/ -q          # stub CLI plus current-core parity, no network
python3 scripts/check_surface.py     # declared vs registered tools
```

`tests/` uses a stub `smcub` so it proves the contract without the real harness
installed. `scripts/check_surface.py` imports the plugin, calls `register()` against
a recording context, and asserts that `plugin.yaml` matches what actually
registered.

## License

MIT. See [LICENSE](LICENSE).
