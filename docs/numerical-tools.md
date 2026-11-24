# Numerical Analysis Plugin Tools (`research.numerical`)

This document details the architecture, safety contracts, scientific boundaries, provenance semantics, and command-line usage for the offline numerical analysis plugin (`research.numerical`).

---

## 1. Architectural Overview

The numerical analysis plugin provides offline scientific computation capabilities through the standard `smartmoney-cub-harness` plugin runtime:

- **Plugin ID:** `research.numerical`
- **Capability:** `numerical_analysis`
- **Plugin Kind:** `subprocess` (isolated process execution via Python interpreter)
- **Trust Level:** `review-only`
- **Result Kind:** `statistical_result` (wrapped inside a provenance record with content hashes)

### Dispatch Architecture

A single subprocess provider (`smartmoney_cub_harness.numerical.provider`) reads a bounded, strict JSON payload from standard input and routes the request based on the top-level `operation` field:

1. `inverse_linear`: Dispatched to `smartmoney_cub_harness.numerical.inverse.solve_inverse`. Solves bounded linear inverse problems using SciPy's bounded least squares (`lsq_linear`).
2. `markov_propagate`: Dispatched to `smartmoney_cub_harness.numerical.markov.propagate_markov`. Propagates finite-state Markov transition dynamics using pure standard-library matrix exponentiation.

### Optional Dependencies & Lazy Loading

Core harness dependencies (`dependencies = []` in `pyproject.toml`) remain untouched.
- **Markov Propagation:** Implemented entirely using the Python standard library. Works without NumPy or SciPy installed.
- **Inverse Solving:** Requires NumPy and SciPy. Imported lazily only when `operation="inverse_linear"` is invoked. If uninstalled, an actionable `RuntimeError` instructs the user to install the optional extra:
  ```bash
  pip install -e '.[numerical]'
  ```

---

## 2. Safety & Process Boundary Contract

### Safety Declaration
Every manifest, log, envelope, and structured error payload carries the mandatory safety declaration:
```text
READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE
```

### Operational Boundaries
- **No Order Execution:** The plugin has no authority to place, modify, or cancel orders, nor can it mutate broker or account state.
- **No Champion Mutation:** Results are review-only statistical outputs; they cannot alter champion models or rule definitions.
- **Declarative Policy:** Declares `network_required: false` and `required_permissions: []`; the child process is an isolated subprocess, not a hard security sandbox.
- **Subprocess Runtime Budget:** When invoked via `PluginRuntime.execute` (or `smcub plugin run`), child process execution is governed by a default 120-second timeout budget (`SubprocessProvider.timeout_seconds = 120`). Runaway processes are terminated and recorded as failures.
- **Input Budget:** Standard input is capped at a strict 2 MiB (2,097,152 bytes) buffer budget. Oversized requests fail immediately.
- **Strict JSON Parsing:** The parser rejects non-standard JSON constants (`NaN`, `Infinity`, `-Infinity`), disallows duplicate object keys, and guards against deep recursion payloads.
- **Encoding & Redaction:** Output is escaped using `ensure_ascii=True` to guarantee standard ASCII/UTF-8 output across all environments without surrogate tracebacks. Exception messages and error details are passed through `smartmoney_cub_harness.safety.redact` before output to stderr.

---

## 3. Scientific Models and Limits

### Linear Inverse Solver (`inverse_linear`)
- **Objective:** Solves $\min_x \frac{1}{2} \|Ax - y\|_2^2 + \frac{\lambda}{2} \|x\|_2^2 \quad \text{s.t.} \quad lb \le x \le ub$.
- **Budgets & Constraints:**
  - Matrix dimensions $1 \le m, n \le 256$.
  - Iteration limit $1 \le \text{max\_iterations} \le 1000$ (default: 1000).
  - Regularization parameter $\lambda \ge 0$ (default: 0.0).
  - Rejects booleans, ragged matrices, non-finite values, and impossible bounds ($lb \ge ub$).
- **Diagnostics:** Returns residual norm, effective matrix rank, solver iteration count, convergence status, and explicit identifiability caveats if $rank(A) < n$.
- **Limitations:** Bounded linear least squares estimates do not imply causal mechanisms. Point estimates do not represent posterior parameter distributions.

### Markov Probability Propagation (`markov_propagate`)
- **Objective:** Propagates state probability distributions under the row-vector convention $p_{k} = p_0 P^k$ using binary matrix exponentiation.
- **Budgets & Constraints:**
  - Dimension $1 \le n \le 128$.
  - Horizon $0 \le \text{steps} \le 10000$.
  - Strict stochastic matrix verification: all row sums and the initial distribution must sum to $1.0 \pm 10^{-9}$ with all entries $p_{ij} \ge 0$.
- **Diagnostics:** Returns step count, matrix exponentiation steps, stationary residual ($L_1$), and labeled state probabilities.
- **Limitations:** Markov propagation models state dynamics under time-homogeneous assumptions; it makes no claim of fitted empirical probabilities or causal action effects.

---

## 4. Provenance and Timestamp Semantics

Every execution via `smcub plugin run` requires explicit timezone-aware ISO 8601 timestamps:

- `--decision-time`: The timestamp when the decision or review context was formed.
- `--available-at`: The timestamp when the input data or observations became known.

### Future Leakage Handling
In the harness plugin pipeline, `PluginRuntime.execute` invokes the provider and then validates timestamps during envelope construction (`build_evidence_envelope`). If `available_at > decision_time`, the harness rejects the evidence with an `EvidenceEnvelopeError` (`future leakage`). The check guarantees that future data cannot be recorded as valid decision evidence (rather than a pre-execution block).

### Provenance Envelope with Hashes
Successful executions output an envelope conforming to `smartmoney_cub_plugin_evidence_envelope.v1`:
- `result_kind`: `"statistical_result"`
- `input_sha256`: SHA-256 digest of the canonical, redacted request JSON.
- `output_sha256`: SHA-256 digest of the canonical, redacted output JSON.
- `output.assumptions` and `output.limitations`: Model assumptions and scientific limitations are recorded under `envelope.output`.
- `source_ref`: When the manifest does not specify a `source_commit` or `source_tag`, `source_ref` falls back to the declared `source_repo` (with a `no_source_commit_or_tag_recorded` doctor warning indicating unpinned local development source).

---

## 5. CLI Usage & Reproducible Commands

### Inspecting the Manifest
```bash
python3 -m smartmoney_cub_harness.cli plugin inspect examples/numerical_plugin/plugin.json
```

### Checking Doctor Status & Enabling the Plugin
Use a workspace-relative state DB (e.g. `state/numerical_plugin_state.db`):
```bash
# Verify plugin tree and capability registration
python3 -m smartmoney_cub_harness.cli plugin doctor \
  --plugin-dir examples/numerical_plugin \
  --state-db state/numerical_plugin_state.db

# Enable the plugin
python3 -m smartmoney_cub_harness.cli plugin enable research.numerical \
  --plugin-dir examples/numerical_plugin \
  --state-db state/numerical_plugin_state.db
```

### Running Markov Probability Propagation
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

### Running Inverse Linear Solver
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

### Disabling the Plugin
```bash
python3 -m smartmoney_cub_harness.cli plugin disable research.numerical \
  --state-db state/numerical_plugin_state.db
```
When disabled, attempting to execute the plugin returns `status: "not_enabled"` and refuses execution until re-enabled.
