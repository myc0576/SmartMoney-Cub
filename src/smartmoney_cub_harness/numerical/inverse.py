from __future__ import annotations

import math
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

MAX_DIMENSION = 256
MAX_ITERATIONS = 1000


class InverseValidationError(ValueError, TypeError):
    """Raised when an inverse solver request is malformed, out of budget, or invalid."""


def _is_finite_real(val: Any) -> bool:
    """Return True if val is a finite real number (excluding bool and overflowing ints)."""
    if isinstance(val, bool):
        return False
    if not isinstance(val, (int, float)):
        return False
    try:
        fval = float(val)
    except (OverflowError, ValueError):
        return False
    return not (math.isnan(fval) or math.isinf(fval))


def solve_inverse(request: dict[str, Any]) -> dict[str, Any]:
    """Solve bounded linear inverse problem: min ||Ax - y||^2 + reg*||x||^2 s.t. lb <= x <= ub.

    Parameters
    ----------
    request : dict
        A dictionary containing:
        - operation: "inverse_linear"
        - matrix: m x n finite numeric list (1 <= m, n <= 256)
        - observations: m finite numeric list
        - lower_bounds: optional n finite numeric list
        - upper_bounds: optional n finite numeric list
        - regularization: optional nonnegative float (default 0.0)
        - max_iterations: optional positive int <= 1000 (default 1000)

    Returns
    -------
    dict
        - status: "ok"
        - operation: "inverse_linear"
        - estimates: list of n finite floats
        - diagnostics: dict with residual_norm, rank, identifiability_caveat, convergence, iterations
        - solver: dict with name, version, method
        - assumptions: list of assumption statements
        - limitations: list of limitation statements
        - safety: SAFETY_DECLARATION
    """
    if not isinstance(request, dict):
        raise InverseValidationError(f"request must be a dict, got {type(request).__name__}")

    operation = request.get("operation")
    if operation != "inverse_linear":
        raise InverseValidationError(
            f"unsupported operation {operation!r}, expected 'inverse_linear'"
        )

    if "matrix" not in request:
        raise InverseValidationError("missing required field 'matrix'")
    matrix = request["matrix"]
    if isinstance(matrix, (str, bytes)) or not isinstance(matrix, (list, tuple)):
        raise InverseValidationError("'matrix' must be a list of lists")

    m = len(matrix)
    if m < 1 or m > MAX_DIMENSION:
        raise InverseValidationError(f"matrix row count {m} out of bounds [1, {MAX_DIMENSION}]")

    n: int | None = None
    for row_idx, row in enumerate(matrix):
        if isinstance(row, (str, bytes)) or not isinstance(row, (list, tuple)):
            raise InverseValidationError(f"matrix row {row_idx} must be a list or tuple")
        if n is None:
            n = len(row)
            if n < 1 or n > MAX_DIMENSION:
                raise InverseValidationError(f"matrix column count {n} out of bounds [1, {MAX_DIMENSION}]")
        elif len(row) != n:
            raise InverseValidationError(
                f"matrix is ragged: row {row_idx} has length {len(row)}, expected {n}"
            )
        for col_idx, val in enumerate(row):
            if not _is_finite_real(val):
                raise InverseValidationError(
                    f"matrix element at [{row_idx}, {col_idx}] is not a finite number: {val!r}"
                )

    assert n is not None

    if "observations" not in request:
        raise InverseValidationError("missing required field 'observations'")
    observations = request["observations"]
    if isinstance(observations, (str, bytes)) or not isinstance(observations, (list, tuple)):
        raise InverseValidationError("'observations' must be a list or tuple")

    if len(observations) != m:
        raise InverseValidationError(
            f"observations length ({len(observations)}) does not match matrix rows ({m})"
        )

    for idx, val in enumerate(observations):
        if not _is_finite_real(val):
            raise InverseValidationError(
                f"observation at index {idx} is not a finite number: {val!r}"
            )

    # Optional bounds
    lower_bounds = request.get("lower_bounds")
    if lower_bounds is not None:
        if isinstance(lower_bounds, (str, bytes)) or not isinstance(lower_bounds, (list, tuple)):
            raise InverseValidationError("'lower_bounds' must be a list or tuple")
        if len(lower_bounds) != n:
            raise InverseValidationError(
                f"lower_bounds length ({len(lower_bounds)}) does not match matrix cols ({n})"
            )
        for idx, val in enumerate(lower_bounds):
            if not _is_finite_real(val):
                raise InverseValidationError(
                    f"lower_bounds element at index {idx} is not a finite number: {val!r}"
                )

    upper_bounds = request.get("upper_bounds")
    if upper_bounds is not None:
        if isinstance(upper_bounds, (str, bytes)) or not isinstance(upper_bounds, (list, tuple)):
            raise InverseValidationError("'upper_bounds' must be a list or tuple")
        if len(upper_bounds) != n:
            raise InverseValidationError(
                f"upper_bounds length ({len(upper_bounds)}) does not match matrix cols ({n})"
            )
        for idx, val in enumerate(upper_bounds):
            if not _is_finite_real(val):
                raise InverseValidationError(
                    f"upper_bounds element at index {idx} is not a finite number: {val!r}"
                )

    # Impossible bounds check
    for idx in range(n):
        lb = lower_bounds[idx] if lower_bounds is not None else -math.inf
        ub = upper_bounds[idx] if upper_bounds is not None else math.inf
        if lb >= ub:
            raise InverseValidationError(
                f"impossible bounds at index {idx}: lower_bound ({lb}) must be strictly less than upper_bound ({ub})"
            )

    # Regularization
    regularization_raw = request.get("regularization", 0.0)
    if regularization_raw is None:
        regularization_raw = 0.0
    if not _is_finite_real(regularization_raw):
        raise InverseValidationError(
            f"regularization must be a finite number: {regularization_raw!r}"
        )
    regularization = float(regularization_raw)
    if regularization < 0.0:
        raise InverseValidationError(f"regularization must be nonnegative, got {regularization}")

    # Max iterations
    max_iter_raw = request.get("max_iterations", MAX_ITERATIONS)
    if max_iter_raw is None:
        max_iter_raw = MAX_ITERATIONS
    if isinstance(max_iter_raw, bool) or not isinstance(max_iter_raw, int):
        raise InverseValidationError(f"max_iterations must be an integer, got {max_iter_raw!r}")
    if max_iter_raw < 1 or max_iter_raw > MAX_ITERATIONS:
        raise InverseValidationError(
            f"max_iterations must be between 1 and {MAX_ITERATIONS}, got {max_iter_raw}"
        )
    max_iterations = int(max_iter_raw)

    # Lazy scientific dependency imports
    try:
        import numpy as np
        import scipy
        from scipy.optimize import lsq_linear
    except ImportError as err:
        raise RuntimeError(
            "SciPy and NumPy are required for the inverse solver. "
            "Install the optional numerical extra via 'pip install smartmoney-cub-harness[numerical]'."
        ) from err

    A = np.asarray(matrix, dtype=np.float64)
    y = np.asarray(observations, dtype=np.float64)

    # Rank and identifiability diagnostics on observation matrix A
    rank = int(np.linalg.matrix_rank(A))
    if rank < n:
        identifiability_caveat: str | None = (
            f"Rank-deficient system: matrix rank ({rank}) is less than parameter count ({n}). "
            "The inverse solution is not uniquely identifiable from observations alone without "
            "regularization or active boundary constraints."
        )
    else:
        identifiability_caveat = None

    # Formulate bounded least squares with optional Tikhonov regularization:
    # min ||Ax - y||^2 + reg * ||x||^2  s.t.  lb <= x <= ub
    if regularization > 0.0:
        reg_factor = math.sqrt(regularization)
        A_solve = np.vstack([A, reg_factor * np.eye(n, dtype=np.float64)])
        y_solve = np.concatenate([y, np.zeros(n, dtype=np.float64)])
    else:
        A_solve = A
        y_solve = y

    lb_vec = (
        np.full(n, -np.inf, dtype=np.float64)
        if lower_bounds is None
        else np.asarray(lower_bounds, dtype=np.float64)
    )
    ub_vec = (
        np.full(n, np.inf, dtype=np.float64)
        if upper_bounds is None
        else np.asarray(upper_bounds, dtype=np.float64)
    )

    result = lsq_linear(
        A_solve,
        y_solve,
        bounds=(lb_vec, ub_vec),
        max_iter=max_iterations,
        method="trf",
    )

    if not getattr(result, "success", False):
        msg = getattr(result, "message", "unknown failure")
        status = getattr(result, "status", -1)
        raise RuntimeError(
            f"Inverse solver optimization did not converge: {msg} (status={status})"
        )

    # Strict finiteness validation on optimizer outputs before declaring ok
    raw_x = getattr(result, "x", None)
    if raw_x is None:
        raise RuntimeError("Inverse solver returned no parameter estimates")

    x_arr = np.asarray(raw_x, dtype=np.float64)
    if not np.all(np.isfinite(x_arr)):
        raise RuntimeError(
            "Inverse solver produced non-finite parameter estimates (overflow or numerical divergence)"
        )

    estimates = [0.0 if abs(val) == 0.0 else float(val) for val in x_arr]
    for est in estimates:
        if not math.isfinite(est):
            raise RuntimeError("Inverse solver produced non-finite estimate value")

    residuals = A @ x_arr - y
    residual_norm = float(np.linalg.norm(residuals))
    if not math.isfinite(residual_norm):
        raise RuntimeError(
            "Inverse solver produced non-finite residual norm (overflow or numerical divergence)"
        )

    nit = int(getattr(result, "nit", 0))

    solver_meta = {
        "name": "scipy.optimize.lsq_linear",
        "version": str(scipy.__version__),
        "method": "trf",
    }

    assumptions = [
        "Linear observation model y = A*x + epsilon",
        "Additive independent observation noise",
        "Known deterministic parameter boundary constraints",
        "L2 (Tikhonov) shrinkage prior when regularization > 0",
    ]

    limitations = [
        "Bounded linear least squares estimates do not imply causal mechanisms",
        "Point estimates do not capture full posterior parameter uncertainty",
        "Rank-deficient or ill-conditioned systems have non-unique or sensitive solutions",
        "Model assumes exact knowledge of the linear operator matrix A",
    ]

    return {
        "status": "ok",
        "operation": "inverse_linear",
        "estimates": estimates,
        "diagnostics": {
            "residual_norm": residual_norm,
            "rank": rank,
            "identifiability_caveat": identifiability_caveat,
            "convergence": True,
            "iterations": nit,
        },
        "solver": solver_meta,
        "assumptions": assumptions,
        "limitations": limitations,
        "safety": SAFETY_DECLARATION,
    }
