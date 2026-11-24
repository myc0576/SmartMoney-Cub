from __future__ import annotations

import math
import sys
from types import SimpleNamespace
import pytest

from smartmoney_cub_harness.numerical.inverse import (
    InverseValidationError,
    solve_inverse,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

try:
    import numpy as np
    import scipy
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

requires_scipy = pytest.mark.skipif(not _HAS_SCIPY, reason="SciPy is not installed")


# ---------------------------------------------------------------------------
# Analytical recovery & exact linear tests
# ---------------------------------------------------------------------------


@requires_scipy
def test_analytical_recovery_exact_system():
    """Verify exact recovery of known parameters in a 2x2 well-conditioned linear system."""
    request = {
        "operation": "inverse_linear",
        "matrix": [[2.0, 1.0], [1.0, 3.0]],
        "observations": [5.0, 0.0],
        "lower_bounds": [-10.0, -10.0],
        "upper_bounds": [10.0, 10.0],
    }
    result = solve_inverse(request)

    assert result["status"] == "ok"
    assert result["operation"] == "inverse_linear"
    assert result["safety"] == SAFETY_DECLARATION

    # True solution: 2*3 + 1*(-1) = 5; 1*3 + 3*(-1) = 0 -> x = [3.0, -1.0]
    estimates = result["estimates"]
    assert len(estimates) == 2
    assert pytest.approx(3.0, abs=1e-7) == estimates[0]
    assert pytest.approx(-1.0, abs=1e-7) == estimates[1]

    diag = result["diagnostics"]
    assert diag["convergence"] is True
    assert diag["rank"] == 2
    assert diag["identifiability_caveat"] is None
    assert pytest.approx(0.0, abs=1e-7) == diag["residual_norm"]
    assert isinstance(diag["iterations"], int)

    solver = result["solver"]
    assert solver["name"] == "scipy.optimize.lsq_linear"
    assert "version" in solver
    assert len(result["assumptions"]) > 0
    assert len(result["limitations"]) > 0


@requires_scipy
def test_analytical_recovery_overdetermined_system():
    """Verify exact recovery for an overdetermined (m > n) 3x2 system with exact observations."""
    request = {
        "operation": "inverse_linear",
        "matrix": [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        "observations": [2.0, 4.0, 6.0],
    }
    result = solve_inverse(request)

    assert result["status"] == "ok"
    estimates = result["estimates"]
    assert pytest.approx(2.0, abs=1e-7) == estimates[0]
    assert pytest.approx(4.0, abs=1e-7) == estimates[1]
    assert pytest.approx(0.0, abs=1e-7) == result["diagnostics"]["residual_norm"]
    assert result["diagnostics"]["rank"] == 2
    assert result["diagnostics"]["identifiability_caveat"] is None


@requires_scipy
def test_unbounded_and_single_sided_bounds():
    """Verify omitted bounds, lower-only bounds, and upper-only bounds."""
    # Completely unbounded
    res_unbounded = solve_inverse({
        "operation": "inverse_linear",
        "matrix": [[1.0, 0.0], [0.0, 1.0]],
        "observations": [-5.0, 5.0],
    })
    assert pytest.approx(-5.0, abs=1e-7) == res_unbounded["estimates"][0]
    assert pytest.approx(5.0, abs=1e-7) == res_unbounded["estimates"][1]

    # Lower-only bounds
    res_lower_only = solve_inverse({
        "operation": "inverse_linear",
        "matrix": [[1.0, 0.0], [0.0, 1.0]],
        "observations": [-5.0, 5.0],
        "lower_bounds": [0.0, 0.0],
    })
    assert pytest.approx(0.0, abs=1e-7) == res_lower_only["estimates"][0]
    assert pytest.approx(5.0, abs=1e-7) == res_lower_only["estimates"][1]

    # Upper-only bounds
    res_upper_only = solve_inverse({
        "operation": "inverse_linear",
        "matrix": [[1.0, 0.0], [0.0, 1.0]],
        "observations": [-5.0, 5.0],
        "upper_bounds": [0.0, 2.0],
    })
    assert pytest.approx(-5.0, abs=1e-7) == res_upper_only["estimates"][0]
    assert pytest.approx(2.0, abs=1e-7) == res_upper_only["estimates"][1]


# ---------------------------------------------------------------------------
# Active bound constraints
# ---------------------------------------------------------------------------


@requires_scipy
def test_active_bounds_clamping():
    """Verify that parameters are clamped exactly at bounds when unconstrained minimum lies outside."""
    # Unconstrained solution would be x1 = 10, x2 = -5
    request = {
        "operation": "inverse_linear",
        "matrix": [[1.0, 0.0], [0.0, 1.0]],
        "observations": [10.0, -5.0],
        "lower_bounds": [0.0, 0.0],
        "upper_bounds": [4.0, 10.0],
    }
    result = solve_inverse(request)

    assert result["status"] == "ok"
    estimates = result["estimates"]
    # x1 clamped at upper bound 4.0; x2 clamped at lower bound 0.0
    assert pytest.approx(4.0, abs=1e-7) == estimates[0]
    assert pytest.approx(0.0, abs=1e-7) == estimates[1]

    # Residuals: [4 - 10, 0 - (-5)] = [-6, 5] -> norm = sqrt(36 + 25) = sqrt(61)
    expected_residual_norm = math.sqrt(61.0)
    assert pytest.approx(expected_residual_norm, rel=1e-5) == result["diagnostics"]["residual_norm"]


# ---------------------------------------------------------------------------
# Regularization (Tikhonov shrinkage)
# ---------------------------------------------------------------------------


@requires_scipy
def test_regularization_analytical_shrinkage():
    """Verify that L2 regularization shrinks parameter estimates according to closed-form solution.

    For min (x - 10)^2 + reg * x^2:
      d/dx = 2(x - 10) + 2*reg*x = 0  =>  (1 + reg)*x = 10  =>  x = 10 / (1 + reg)
    """
    matrix = [[1.0]]
    obs = [10.0]

    # reg = 0.0 -> x = 10.0
    res_0 = solve_inverse({"operation": "inverse_linear", "matrix": matrix, "observations": obs, "regularization": 0.0})
    assert pytest.approx(10.0, abs=1e-6) == res_0["estimates"][0]

    # reg = 1.0 -> x = 5.0
    res_1 = solve_inverse({"operation": "inverse_linear", "matrix": matrix, "observations": obs, "regularization": 1.0})
    assert pytest.approx(5.0, abs=1e-6) == res_1["estimates"][0]

    # reg = 4.0 -> x = 2.0
    res_4 = solve_inverse({"operation": "inverse_linear", "matrix": matrix, "observations": obs, "regularization": 4.0})
    assert pytest.approx(2.0, abs=1e-6) == res_4["estimates"][0]

    # reg = 9.0 -> x = 1.0
    res_9 = solve_inverse({"operation": "inverse_linear", "matrix": matrix, "observations": obs, "regularization": 9.0})
    assert pytest.approx(1.0, abs=1e-6) == res_9["estimates"][0]


# ---------------------------------------------------------------------------
# Rank deficiency & identifiability diagnostics
# ---------------------------------------------------------------------------


@requires_scipy
def test_rank_deficiency_underdetermined_system():
    """Underdetermined system (m < n) reports rank deficiency and diagnostic caveat."""
    request = {
        "operation": "inverse_linear",
        "matrix": [[1.0, 1.0]],  # 1 row, 2 columns -> m=1, n=2, rank=1
        "observations": [4.0],
    }
    result = solve_inverse(request)

    assert result["status"] == "ok"
    diag = result["diagnostics"]
    assert diag["rank"] == 1
    assert diag["identifiability_caveat"] is not None
    assert "Rank-deficient" in diag["identifiability_caveat"]
    assert "rank (1)" in diag["identifiability_caveat"]
    # Residual should be 0 because 1 equation in 2 unknowns has exact solutions
    assert pytest.approx(0.0, abs=1e-6) == diag["residual_norm"]


@requires_scipy
def test_rank_deficiency_collinear_columns():
    """Collinear columns (m=2, n=2, rank=1) reports rank deficiency and caveat."""
    request = {
        "operation": "inverse_linear",
        "matrix": [[1.0, 2.0], [2.0, 4.0]],
        "observations": [3.0, 6.0],
    }
    result = solve_inverse(request)

    assert result["status"] == "ok"
    diag = result["diagnostics"]
    assert diag["rank"] == 1
    assert diag["identifiability_caveat"] is not None
    assert "Rank-deficient" in diag["identifiability_caveat"]


# ---------------------------------------------------------------------------
# Malformed, nonfinite, and bool input validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_request",
    [
        "not a dict",
        None,
        [],
        123,
    ],
)
def test_reject_non_dict_request(bad_request):
    with pytest.raises((ValueError, TypeError)):
        solve_inverse(bad_request)


@pytest.mark.parametrize(
    "bad_op",
    [
        None,
        "",
        "unknown",
        "inverse_nonlinear",
        123,
    ],
)
def test_reject_invalid_operation(bad_op):
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({"operation": bad_op, "matrix": [[1.0]], "observations": [1.0]})


def test_reject_missing_fields():
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({"operation": "inverse_linear", "observations": [1.0]})
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({"operation": "inverse_linear", "matrix": [[1.0]]})


@pytest.mark.parametrize(
    "bad_matrix",
    [
        [],  # m = 0
        "string",
        [[]],  # n = 0
        [[1.0, 2.0], [3.0]],  # ragged
        [[True, 1.0], [0.0, 2.0]],  # bool as number
        [[False, 0.0]],  # bool as number
        [[float("nan"), 1.0]],  # NaN
        [[float("inf"), 1.0]],  # +Inf
        [[float("-inf"), 1.0]],  # -Inf
        [["1.0", 2.0]],  # string in matrix
    ],
)
def test_reject_malformed_matrix(bad_matrix):
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": bad_matrix,
            "observations": [1.0] * len(bad_matrix) if isinstance(bad_matrix, list) and bad_matrix and isinstance(bad_matrix[0], list) else [1.0],
        })


@pytest.mark.parametrize(
    "bad_obs",
    [
        "not_list",
        [1.0, 2.0],  # length 2, but matrix has m=1
        [True],  # bool
        [float("nan")],  # NaN
        [float("inf")],  # Inf
        ["string"],
    ],
)
def test_reject_malformed_observations(bad_obs):
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": bad_obs,
        })


@pytest.mark.parametrize(
    "bad_bounds",
    [
        "string",
        [1.0, 2.0],  # length mismatch (n=1)
        [True],  # bool
        [float("nan")],  # NaN
        [float("inf")],  # nonfinite in explicit bound list
        ["string"],
    ],
)
def test_reject_malformed_bounds(bad_bounds):
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
            "lower_bounds": bad_bounds,
        })
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
            "upper_bounds": bad_bounds,
        })


def test_reject_impossible_bounds():
    """Lower bound greater than or equal to upper bound must be rejected."""
    # lower > upper
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
            "lower_bounds": [5.0],
            "upper_bounds": [2.0],
        })
    # lower == upper (SciPy requires lb < ub)
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
            "lower_bounds": [3.0],
            "upper_bounds": [3.0],
        })


@pytest.mark.parametrize(
    "bad_reg",
    [
        True,
        -1.0,
        -0.001,
        float("nan"),
        float("inf"),
        "invalid",
    ],
)
def test_reject_invalid_regularization(bad_reg):
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
            "regularization": bad_reg,
        })


@pytest.mark.parametrize(
    "bad_max_iter",
    [
        True,
        10.5,
        0,
        -1,
        1001,  # cap is 1000
        "100",
    ],
)
def test_reject_invalid_max_iterations(bad_max_iter):
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
            "max_iterations": bad_max_iter,
        })


# ---------------------------------------------------------------------------
# Overflowing huge Python integers
# ---------------------------------------------------------------------------


def test_reject_huge_overflowing_integers():
    """Huge integers causing float overflow must be gracefully rejected by _is_finite_real."""
    huge_int = 10**500

    # In matrix
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[huge_int]],
            "observations": [1.0],
        })

    # In observations
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [huge_int],
        })

    # In lower bounds
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
            "lower_bounds": [huge_int],
        })

    # In upper bounds
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
            "upper_bounds": [huge_int],
        })

    # In regularization
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
            "regularization": huge_int,
        })


# ---------------------------------------------------------------------------
# Budget bounds (m, n <= 256)
# ---------------------------------------------------------------------------


def test_budget_bounds_dimension_caps():
    # m > 256
    large_m_matrix = [[1.0]] * 257
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": large_m_matrix,
            "observations": [1.0] * 257,
        })

    # n > 256
    large_n_matrix = [[1.0] * 257]
    with pytest.raises((ValueError, TypeError)):
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": large_n_matrix,
            "observations": [1.0],
        })


# ---------------------------------------------------------------------------
# Missing dependency handling
# ---------------------------------------------------------------------------


def test_missing_scipy_dependency_raises_actionable_runtime_error(monkeypatch):
    """When SciPy cannot be imported, solve_inverse must raise an actionable RuntimeError."""
    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "scipy.optimize", None)

    with pytest.raises(RuntimeError) as excinfo:
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
        })

    msg = str(excinfo.value)
    assert "SciPy and NumPy are required" in msg
    assert "smartmoney-cub-harness[numerical]" in msg


# ---------------------------------------------------------------------------
# Optimizer non-convergence & non-finite output rejection
# ---------------------------------------------------------------------------


@requires_scipy
def test_optimizer_non_convergence_raises():
    """When optimization fails to converge within iteration budget, a RuntimeError is raised."""
    # Deterministic problem where max_iter=1 cannot converge:
    # 20x20 problem with strictly active bounds requiring multiple search iterations
    m, n = 20, 20
    matrix = []
    for r in range(m):
        row = [(r * n + c + 1) / 100.0 + (2.0 if r == c else 0.0) for c in range(n)]
        matrix.append(row)

    observations = [10.0] * m
    lower_bounds = [0.0] * n
    upper_bounds = [0.5] * n

    with pytest.raises(RuntimeError) as excinfo:
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": matrix,
            "observations": observations,
            "lower_bounds": lower_bounds,
            "upper_bounds": upper_bounds,
            "max_iterations": 1,
        })

    assert "did not converge" in str(excinfo.value) or "failed" in str(excinfo.value)


@requires_scipy
def test_optimizer_nonfinite_estimates_rejected(monkeypatch):
    """Adversarial check: even if solver reports success, nonfinite x must raise RuntimeError."""
    import scipy.optimize

    # Monkeypatch lsq_linear to return success=True with NaN x
    def fake_lsq_linear(*args, **kwargs):
        return SimpleNamespace(
            success=True,
            status=1,
            message="Optimization converged",
            x=np.array([float("nan")]),
            nit=1,
        )

    monkeypatch.setattr(scipy.optimize, "lsq_linear", fake_lsq_linear)

    with pytest.raises(RuntimeError) as excinfo:
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
        })

    assert "non-finite parameter estimates" in str(excinfo.value)


@requires_scipy
def test_optimizer_inf_estimates_rejected(monkeypatch):
    """Adversarial check: even if solver reports success, infinite x must raise RuntimeError."""
    import scipy.optimize

    def fake_lsq_linear(*args, **kwargs):
        return SimpleNamespace(
            success=True,
            status=1,
            message="Optimization converged",
            x=np.array([float("inf")]),
            nit=1,
        )

    monkeypatch.setattr(scipy.optimize, "lsq_linear", fake_lsq_linear)

    with pytest.raises(RuntimeError) as excinfo:
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1.0]],
            "observations": [1.0],
        })

    assert "non-finite parameter estimates" in str(excinfo.value)


@requires_scipy
def test_optimizer_nonfinite_residual_norm_rejected(monkeypatch):
    """Adversarial check: nonfinite residual norm must raise RuntimeError instead of status ok."""
    import scipy.optimize

    # Return valid x, but when matrix multiplication happens with huge numbers it overflows
    def fake_lsq_linear(*args, **kwargs):
        return SimpleNamespace(
            success=True,
            status=1,
            message="Optimization converged",
            x=np.array([1e308]),
            nit=1,
        )

    monkeypatch.setattr(scipy.optimize, "lsq_linear", fake_lsq_linear)

    with pytest.raises(RuntimeError) as excinfo:
        solve_inverse({
            "operation": "inverse_linear",
            "matrix": [[1e308]],
            "observations": [-1e308],
        })

    assert "non-finite" in str(excinfo.value)
