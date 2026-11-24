from __future__ import annotations

import math
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

MAX_DIMENSION = 128
MAX_STEPS = 10000
PROBABILITY_TOLERANCE = 1e-9


class MarkovValidationError(ValueError, TypeError):
    """Raised when a Markov propagation request is malformed, out of budget, or stochastic-invalid."""


def _is_finite_real(val: Any) -> bool:
    """Return True if val is a finite real number (excluding bool).

    Gracefully handles arbitrarily large integers (e.g. 10**400) without
    raising OverflowError.
    """
    if isinstance(val, bool):
        return False
    if not isinstance(val, (int, float)):
        return False
    try:
        f = float(val)
    except (OverflowError, ValueError):
        return False
    return not (math.isnan(f) or math.isinf(f))


def propagate_markov(request: dict[str, Any]) -> dict[str, Any]:
    """Propagate a finite-state Markov chain using matrix exponentiation.

    Row-vector convention: p_{t+1} = p_t * P.
    For k steps: p_k = p_0 * P^k.

    Parameters
    ----------
    request : dict
        A dictionary containing:
        - operation: "markov_propagate"
        - transition_matrix: n x n stochastic matrix (1 <= n <= 128)
        - initial_distribution: n-element probability distribution vector
        - steps: int in range [0, 10000]
        - state_labels: optional list of n distinct nonempty strings
        - time_step: optional nonempty description string

    Returns
    -------
    dict
        - status: "ok"
        - operation: "markov_propagate"
        - distribution: list of n float probabilities summing to 1.0
        - diagnostics: dict with steps, dimension, stationary residual, operation counts
        - solver: metadata about the standard library matrix exponentiation algorithm
        - assumptions: explicit list of model assumptions
        - limitations: explicit list of domain-neutral model limitations
        - safety: SAFETY_DECLARATION ("READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE")
    """
    if not isinstance(request, dict):
        raise MarkovValidationError(f"request must be a dict, got {type(request).__name__}")

    operation = request.get("operation")
    if operation != "markov_propagate":
        raise MarkovValidationError(
            f"unsupported operation {operation!r}, expected 'markov_propagate'"
        )

    # 1. Validate transition_matrix
    if "transition_matrix" not in request:
        raise MarkovValidationError("missing required field 'transition_matrix'")
    raw_matrix = request["transition_matrix"]
    if isinstance(raw_matrix, (str, bytes)) or not isinstance(raw_matrix, (list, tuple)):
        raise MarkovValidationError("'transition_matrix' must be a list or tuple of rows")

    n = len(raw_matrix)
    if n < 1 or n > MAX_DIMENSION:
        raise MarkovValidationError(
            f"transition_matrix dimension {n} out of allowed bounds [1, {MAX_DIMENSION}]"
        )

    transition_matrix: list[list[float]] = []
    for row_idx, raw_row in enumerate(raw_matrix):
        if isinstance(raw_row, (str, bytes)) or not isinstance(raw_row, (list, tuple)):
            raise MarkovValidationError(f"transition_matrix row {row_idx} must be a list or tuple")
        if len(raw_row) != n:
            raise MarkovValidationError(
                f"transition_matrix must be square: row {row_idx} has length {len(raw_row)}, expected {n}"
            )
        parsed_row: list[float] = []
        for col_idx, val in enumerate(raw_row):
            if isinstance(val, bool):
                raise MarkovValidationError(
                    f"bool value {val!r} at transition_matrix[{row_idx}][{col_idx}] is not a valid numeric probability"
                )
            if not _is_finite_real(val):
                raise MarkovValidationError(
                    f"transition_matrix[{row_idx}][{col_idx}] must be a finite number, got {val!r}"
                )
            f_val = float(val)
            if f_val < 0.0:
                raise MarkovValidationError(
                    f"transition_matrix[{row_idx}][{col_idx}] must be non-negative, got {f_val}"
                )
            parsed_row.append(f_val)

        row_sum = sum(parsed_row)
        if abs(row_sum - 1.0) > PROBABILITY_TOLERANCE:
            raise MarkovValidationError(
                f"Row {row_idx} of transition_matrix does not sum to 1.0 (sum={row_sum:.12f}, tolerance={PROBABILITY_TOLERANCE})"
            )
        transition_matrix.append(parsed_row)

    # 2. Validate initial_distribution
    if "initial_distribution" not in request:
        raise MarkovValidationError("missing required field 'initial_distribution'")
    raw_init = request["initial_distribution"]
    if isinstance(raw_init, (str, bytes)) or not isinstance(raw_init, (list, tuple)):
        raise MarkovValidationError("'initial_distribution' must be a list or tuple")
    if len(raw_init) != n:
        raise MarkovValidationError(
            f"initial_distribution length ({len(raw_init)}) does not match transition_matrix dimension ({n})"
        )

    initial_distribution: list[float] = []
    for idx, val in enumerate(raw_init):
        if isinstance(val, bool):
            raise MarkovValidationError(
                f"bool value {val!r} at initial_distribution[{idx}] is not a valid numeric probability"
            )
        if not _is_finite_real(val):
            raise MarkovValidationError(
                f"initial_distribution[{idx}] must be a finite number, got {val!r}"
            )
        f_val = float(val)
        if f_val < 0.0:
            raise MarkovValidationError(
                f"initial_distribution[{idx}] must be non-negative, got {f_val}"
            )
        initial_distribution.append(f_val)

    init_sum = sum(initial_distribution)
    if abs(init_sum - 1.0) > PROBABILITY_TOLERANCE:
        raise MarkovValidationError(
            f"initial_distribution does not sum to 1.0 (sum={init_sum:.12f}, tolerance={PROBABILITY_TOLERANCE})"
        )

    # 3. Validate steps
    if "steps" not in request:
        raise MarkovValidationError("missing required field 'steps'")
    steps = request["steps"]
    if isinstance(steps, bool):
        raise MarkovValidationError("steps cannot be a boolean")
    if not isinstance(steps, int):
        raise MarkovValidationError(f"steps must be an integer, got {type(steps).__name__}")
    if steps < 0 or steps > MAX_STEPS:
        raise MarkovValidationError(f"steps {steps} out of bounds [0, {MAX_STEPS}]")

    # 4. Validate optional state_labels
    state_labels = request.get("state_labels")
    parsed_labels: list[str] | None = None
    if state_labels is not None:
        if isinstance(state_labels, (str, bytes)) or not isinstance(state_labels, (list, tuple)):
            raise MarkovValidationError("'state_labels' must be a list or tuple of strings")
        if len(state_labels) != n:
            raise MarkovValidationError(
                f"state_labels length ({len(state_labels)}) does not match dimension ({n})"
            )
        parsed_labels = []
        seen_labels: set[str] = set()
        for idx, label in enumerate(state_labels):
            if not isinstance(label, str):
                raise MarkovValidationError(
                    f"state_labels[{idx}] must be a string, got {type(label).__name__}"
                )
            if not label.strip():
                raise MarkovValidationError(
                    f"state_labels[{idx}] cannot be empty or whitespace-only"
                )
            if label in seen_labels:
                raise MarkovValidationError(
                    f"state_labels must contain distinct strings, found duplicate: {label!r}"
                )
            seen_labels.add(label)
            parsed_labels.append(label)

    # 5. Validate optional time_step
    time_step = request.get("time_step")
    parsed_time_step: str | None = None
    if time_step is not None:
        if not isinstance(time_step, str):
            raise MarkovValidationError(
                f"'time_step' must be a string, got {type(time_step).__name__}"
            )
        if not time_step.strip():
            raise MarkovValidationError("'time_step' cannot be empty or whitespace-only")
        parsed_time_step = time_step

    # 6. Propagation via binary exponentiation
    # Row-vector convention: p_{t+1} = p_t * P
    # Binary exponentiation avoids storing full trajectory and bounds runtime at O(n^3 log k)
    v = [float(x) for x in initial_distribution]
    squaring_steps = 0
    vector_multiplications = 0

    if steps > 0:
        p = steps
        M = [row[:] for row in transition_matrix]
        while p > 0:
            if p & 1:
                # v = v * M (row-vector by matrix)
                # v[j] = sum(v[i] * M[i][j])
                v = [sum(v[i] * M[i][j] for i in range(n)) for j in range(n)]
                vector_multiplications += 1
            if p > 1:
                # M = M * M
                # Transpose M for cache-locality and fast row dot products
                M_t = [[M[r][c] for r in range(n)] for c in range(n)]
                M = [
                    [sum(row_m[k] * col_m[k] for k in range(n)) for col_m in M_t]
                    for row_m in M
                ]
                squaring_steps += 1
            p >>= 1

    # Post-propagation drift inspection and strict normalization
    raw_sum = sum(v)
    drift_before_renorm = float(abs(raw_sum - 1.0))
    clamped = [max(0.0, float(x)) for x in v]
    total = sum(clamped)
    if total <= 0.0 or not math.isfinite(total):
        raise RuntimeError("Markov propagation failed: degenerate state distribution")
    distribution = [x / total for x in clamped]

    # Calculate stationary residual L1 norm: ||p * P - p||_1
    p_next = [sum(distribution[i] * transition_matrix[i][j] for i in range(n)) for j in range(n)]
    stationary_residual_l1 = float(sum(abs(p_next[j] - distribution[j]) for j in range(n)))

    diagnostics: dict[str, Any] = {
        "steps": steps,
        "dimension": n,
        "matrix_exponentiation": True,
        "squaring_steps": squaring_steps,
        "vector_multiplications": vector_multiplications,
        "drift_before_renormalization": drift_before_renorm,
        "stationary_residual_l1": stationary_residual_l1,
    }
    if parsed_labels is not None:
        diagnostics["state_labels"] = parsed_labels
        diagnostics["labeled_distribution"] = {
            label: prob for label, prob in zip(parsed_labels, distribution)
        }
    if parsed_time_step is not None:
        diagnostics["time_step"] = parsed_time_step

    solver = {
        "name": "markov_matrix_exponentiation",
        "version": "1.0.0",
        "algorithm": "binary_exponentiation",
        "framework": "standard_library",
    }

    assumptions = [
        "First-order finite-state Markov property: transition probabilities depend only on current state",
        "Time-homogeneous transition probabilities across all propagation steps",
        "Discrete state space and discrete time steps",
        "Transition matrix and initial distribution are user-specified assumptions, not fitted empirical estimates or ground truth",
    ]

    limitations = [
        "Does not claim fitted probabilities, causal effects, or predictive accuracy",
        "Does not model exogenous shocks, structural regime breaks, or time-varying transition dynamics",
        "Finite-precision floating-point arithmetic may accumulate rounding drift over large step horizons",
    ]

    return {
        "status": "ok",
        "operation": "markov_propagate",
        "distribution": distribution,
        "diagnostics": diagnostics,
        "solver": solver,
        "assumptions": assumptions,
        "limitations": limitations,
        "safety": SAFETY_DECLARATION,
    }
