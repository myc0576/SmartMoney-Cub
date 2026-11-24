# Numerical Analysis Plugin (`research.numerical`)

Reference offline plugin demonstrating bounded linear inverse problem solving and finite-state Markov probability propagation within `smartmoney-cub-harness`.

## Safety & Isolation Contract

All operations strictly declare and enforce:
```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

This plugin operates strictly in offline review mode:
- **No trading execution:** Never orders, cancels, trades, or mutates trading accounts.
- **No model mutation:** Never promotes or mutates champion rules or core rule libraries.
- **Declarative permissions:** Declares `network_required: false` and `required_permissions: []`; subprocess isolation separates process memory rather than acting as a security sandbox.
- **Runtime budget:** When invoked through the harness runtime, a 120-second subprocess timeout budget is enforced (`SubprocessProvider.timeout_seconds = 120`), and standard input is constrained to a 2 MiB byte budget.
- **Provenance envelope:** All capability executions return a provenance envelope with hashes wrapping a `statistical_result` with SHA-256 content hashes, with mathematical assumptions and limitations under `envelope.output`.

## Installation of Optional Dependencies

Markov propagation requires only the Python standard library.
The bounded linear inverse solver utilizes SciPy and NumPy via the optional `numerical` extra:

```bash
# In the repository root:
pip install -e '.[numerical]'
```

## CLI Usage

### 1. Inspect Manifest

```bash
python3 -m smartmoney_cub_harness.cli plugin inspect examples/numerical_plugin/plugin.json
```
*(Note: Manifest inspection reports a `no_source_commit_or_tag_recorded` warning for unversioned local directory manifests, indicating an unpinned local development source.)*

### 2. Check Plugin Doctor & Enable Plugin

```bash
# Doctor check using a workspace-relative state store:
python3 -m smartmoney_cub_harness.cli plugin doctor \
  --plugin-dir examples/numerical_plugin \
  --state-db state/numerical_plugin_state.db

# Enable the plugin:
python3 -m smartmoney_cub_harness.cli plugin enable research.numerical \
  --plugin-dir examples/numerical_plugin \
  --state-db state/numerical_plugin_state.db
```

### 3. Run Markov Probability Propagation

```bash
python3 -m smartmoney_cub_harness.cli plugin run research.numerical \
  --capability numerical_analysis \
  --request examples/numerical_plugin/markov_request.json \
  --decision-time "2026-10-31T15:00:00+08:00" \
  --available-at "2026-10-31T14:30:00+08:00" \
  --data-source "toy_state_model" \
  --result-kind statistical_result \
  --plugin-dir examples/numerical_plugin \
  --state-db state/numerical_plugin_state.db
```

### 4. Run Inverse Linear Solver (Requires `numerical` extra)

```bash
python3 -m smartmoney_cub_harness.cli plugin run research.numerical \
  --capability numerical_analysis \
  --request examples/numerical_plugin/inverse_request.json \
  --decision-time "2026-10-31T15:00:00+08:00" \
  --available-at "2026-10-31T14:30:00+08:00" \
  --data-source "toy_linear_model" \
  --result-kind statistical_result \
  --plugin-dir examples/numerical_plugin \
  --state-db state/numerical_plugin_state.db
```
