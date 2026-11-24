from __future__ import annotations

import math
import sys
import time
import pytest

from smartmoney_cub_harness.numerical.markov import (
    MAX_DIMENSION,
    MAX_STEPS,
    PROBABILITY_TOLERANCE,
    MarkovValidationError,
    _is_finite_real,
    propagate_markov,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


# ---------------------------------------------------------------------------
# 1. Zero-step Identity Tests
# ---------------------------------------------------------------------------


def test_zero_step_identity_preserves_initial_distribution() -> None:
    request = {
        "operation": "markov_propagate",
        "transition_matrix": [
            [0.7, 0.3],
            [0.2, 0.8],
        ],
        "initial_distribution": [0.4, 0.6],
        "steps": 0,
    }
    result = propagate_markov(request)
    assert result["status"] == "ok"
    assert result["operation"] == "markov_propagate"
    assert len(result["distribution"]) == 2
    assert math.isclose(result["distribution"][0], 0.4, abs_tol=1e-12)
    assert math.isclose(result["distribution"][1], 0.6, abs_tol=1e-12)
    assert result["diagnostics"]["steps"] == 0
    assert result["diagnostics"]["squaring_steps"] == 0
    assert result["diagnostics"]["vector_multiplications"] == 0


def test_zero_step_with_labels_and_time_step() -> None:
    request = {
        "operation": "markov_propagate",
        "transition_matrix": [
            [1.0, 0.0, 0.0],
            [0.2, 0.5, 0.3],
            [0.1, 0.1, 0.8],
        ],
        "initial_distribution": [0.2, 0.5, 0.3],
        "steps": 0,
        "state_labels": ["low", "medium", "high"],
        "time_step": "1_day",
    }
    result = propagate_markov(request)
    assert result["status"] == "ok"
    assert result["diagnostics"]["state_labels"] == ["low", "medium", "high"]
    labeled = result["diagnostics"]["labeled_distribution"]
    assert math.isclose(labeled["low"], 0.2, abs_tol=1e-12)
    assert math.isclose(labeled["medium"], 0.5, abs_tol=1e-12)
    assert math.isclose(labeled["high"], 0.3, abs_tol=1e-12)
    assert result["diagnostics"]["time_step"] == "1_day"


# ---------------------------------------------------------------------------
# 2. Analytical 1-step and Multi-step Transitions
# ---------------------------------------------------------------------------


def test_analytical_one_step_transition() -> None:
    # 2-state Markov chain: p_1 = p_0 * P
    # p_0 = [0.5, 0.5]
    # P = [[0.8, 0.2], [0.1, 0.9]]
    # p_1[0] = 0.5*0.8 + 0.5*0.1 = 0.45
    # p_1[1] = 0.5*0.2 + 0.5*0.9 = 0.55
    request = {
        "operation": "markov_propagate",
        "transition_matrix": [
            [0.8, 0.2],
            [0.1, 0.9],
        ],
        "initial_distribution": [0.5, 0.5],
        "steps": 1,
    }
    result = propagate_markov(request)
    assert result["status"] == "ok"
    assert math.isclose(result["distribution"][0], 0.45, abs_tol=1e-12)
    assert math.isclose(result["distribution"][1], 0.55, abs_tol=1e-12)
    assert result["diagnostics"]["vector_multiplications"] == 1
    assert result["diagnostics"]["squaring_steps"] == 0


def test_analytical_two_step_transition() -> None:
    # Continuing from step 1:
    # p_1 = [0.45, 0.55]
    # p_2[0] = 0.45*0.8 + 0.55*0.1 = 0.36 + 0.055 = 0.415
    # p_2[1] = 0.45*0.2 + 0.55*0.9 = 0.09 + 0.495 = 0.585
    request = {
        "operation": "markov_propagate",
        "transition_matrix": [
            [0.8, 0.2],
            [0.1, 0.9],
        ],
        "initial_distribution": [0.5, 0.5],
        "steps": 2,
    }
    result = propagate_markov(request)
    assert result["status"] == "ok"
    assert math.isclose(result["distribution"][0], 0.415, abs_tol=1e-12)
    assert math.isclose(result["distribution"][1], 0.585, abs_tol=1e-12)


def test_analytical_stationary_distribution_convergence() -> None:
    # 2-state ergodic chain:
    # P = [[1-a, a], [b, 1-b]] where a=0.3, b=0.2
    # Stationary distribution pi = [b/(a+b), a/(a+b)] = [0.2/0.5, 0.3/0.5] = [0.4, 0.6]
    request = {
        "operation": "markov_propagate",
        "transition_matrix": [
            [0.7, 0.3],
            [0.2, 0.8],
        ],
        "initial_distribution": [1.0, 0.0],
        "steps": 100,
    }
    result = propagate_markov(request)
    assert result["status"] == "ok"
    assert math.isclose(result["distribution"][0], 0.4, abs_tol=1e-7)
    assert math.isclose(result["distribution"][1], 0.6, abs_tol=1e-7)
    assert result["diagnostics"]["stationary_residual_l1"] < 1e-7


def test_absorbing_state_convergence() -> None:
    # State 0 is absorbing: P[0][0] = 1.0, P[1][0] = 0.4, P[1][1] = 0.6
    # Starting from state 1: prob of staying in state 1 after k steps is 0.6^k
    # For k=50, 0.6^50 ≈ 8e-12, so prob of absorbing state 0 is essentially 1.0.
    request = {
        "operation": "markov_propagate",
        "transition_matrix": [
            [1.0, 0.0],
            [0.4, 0.6],
        ],
        "initial_distribution": [0.0, 1.0],
        "steps": 50,
    }
    result = propagate_markov(request)
    assert result["status"] == "ok"
    assert math.isclose(result["distribution"][0], 1.0, abs_tol=1e-10)
    assert math.isclose(result["distribution"][1], 0.0, abs_tol=1e-10)


def test_cyclic_permutation_chain() -> None:
    # 3-state deterministic cycle: 0 -> 1 -> 2 -> 0
    request = {
        "operation": "markov_propagate",
        "transition_matrix": [
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 0.0],
        ],
        "initial_distribution": [1.0, 0.0, 0.0],
        "steps": 10000,
    }
    result = propagate_markov(request)
    # 10000 mod 3 = 1, so distribution should be [0.0, 1.0, 0.0]
    assert result["status"] == "ok"
    assert math.isclose(result["distribution"][0], 0.0, abs_tol=1e-12)
    assert math.isclose(result["distribution"][1], 1.0, abs_tol=1e-12)
    assert math.isclose(result["distribution"][2], 0.0, abs_tol=1e-12)


# ---------------------------------------------------------------------------
# 3. Near-Tolerance Stochastic Matrices & Normalization Drift at Large Steps
# ---------------------------------------------------------------------------


def test_near_tolerance_drift_reported_and_strictly_normalized() -> None:
    # Row sum is within tolerance (1e-9), e.g. 1.0 + 8e-10
    drift_eps = 8e-10
    assert drift_eps <= PROBABILITY_TOLERANCE
    request = {
        "operation": "markov_propagate",
        "transition_matrix": [
            [0.5 + drift_eps, 0.5],
            [0.5, 0.5 + drift_eps],
        ],
        "initial_distribution": [0.5, 0.5],
        "steps": 5000,
    }
    result = propagate_markov(request)
    assert result["status"] == "ok"
    dist = result["distribution"]
    # Output must be finite, non-negative, and strictly sum to 1.0
    for p in dist:
        assert math.isfinite(p)
        assert p >= 0.0
        assert p <= 1.0
    assert math.isclose(sum(dist), 1.0, abs_tol=1e-12)

    # Drift before renormalization must be tracked and recorded
    assert "drift_before_renormalization" in result["diagnostics"]
    assert result["diagnostics"]["drift_before_renormalization"] > 0.0


# ---------------------------------------------------------------------------
# 4. Input Validation & Error Handling (Malformed, Non-finite, Bool, Types)
# ---------------------------------------------------------------------------


def test_reject_non_dict_request() -> None:
    with pytest.raises(MarkovValidationError):
        propagate_markov(["not", "a", "dict"])  # type: ignore[arg-type]


def test_reject_unsupported_operation() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({"operation": "markov_simulate"})
    assert "unsupported operation" in str(exc.value)


def test_reject_missing_transition_matrix() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
        })
    assert "missing required field 'transition_matrix'" in str(exc.value)


def test_reject_missing_initial_distribution() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [[0.5, 0.5], [0.5, 0.5]],
            "steps": 1,
        })
    assert "missing required field 'initial_distribution'" in str(exc.value)


def test_reject_missing_steps() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [[0.5, 0.5], [0.5, 0.5]],
            "initial_distribution": [0.5, 0.5],
        })
    assert "missing required field 'steps'" in str(exc.value)


def test_reject_empty_matrix() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [],
            "initial_distribution": [],
            "steps": 1,
        })
    assert "dimension 0 out of allowed bounds" in str(exc.value)


def test_reject_matrix_exceeding_max_dimension() -> None:
    dim = MAX_DIMENSION + 1
    # Create oversized matrix
    row = [1.0 / dim] * dim
    matrix = [row[:] for _ in range(dim)]
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": matrix,
            "initial_distribution": [1.0 / dim] * dim,
            "steps": 1,
        })
    assert f"dimension {dim} out of allowed bounds" in str(exc.value)


def test_reject_ragged_transition_matrix() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.3, 0.3, 0.4],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
        })
    assert "square" in str(exc.value)


def test_reject_non_square_transition_matrix() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5, 0.0],
                [0.5, 0.5, 0.0],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
        })
    assert "square" in str(exc.value)


def test_reject_dimension_mismatch_with_initial_distribution() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.33, 0.33, 0.34],
            "steps": 1,
        })
    assert "does not match transition_matrix dimension" in str(exc.value)


def test_reject_bool_in_transition_matrix() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [True, False],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
        })
    assert "bool value" in str(exc.value)


def test_reject_bool_in_initial_distribution() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [True, False],
            "steps": 1,
        })
    assert "bool value" in str(exc.value)


def test_reject_bool_as_steps() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": True,
        })
    assert "cannot be a boolean" in str(exc.value)


def test_reject_float_steps() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 2.5,
        })
    assert "steps must be an integer" in str(exc.value)


def test_reject_negative_steps() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": -1,
        })
    assert "out of bounds" in str(exc.value)


def test_reject_steps_exceeding_max() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": MAX_STEPS + 1,
        })
    assert f"steps {MAX_STEPS + 1} out of bounds" in str(exc.value)


def test_reject_negative_probability_in_matrix() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [-0.1, 1.1],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
        })
    assert "non-negative" in str(exc.value)


def test_reject_negative_probability_in_initial_distribution() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [-0.2, 1.2],
            "steps": 1,
        })
    assert "non-negative" in str(exc.value)


def test_reject_nan_in_matrix() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [float("nan"), 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
        })
    assert "finite number" in str(exc.value)


def test_reject_inf_in_initial_distribution() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [float("inf"), 0.5],
            "steps": 1,
        })
    assert "finite number" in str(exc.value)


def test_reject_huge_integer_gracefully_without_overflow_error() -> None:
    # A huge int like 10**400 raises OverflowError if converted naively via float() or math.isinf()
    huge_int = 10**400
    assert not _is_finite_real(huge_int)

    with pytest.raises(MarkovValidationError) as exc_matrix:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [huge_int, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
        })
    assert "must be a finite number" in str(exc_matrix.value)

    with pytest.raises(MarkovValidationError) as exc_init:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [huge_int, 0.5],
            "steps": 1,
        })
    assert "must be a finite number" in str(exc_init.value)


def test_reject_row_sum_not_equal_to_one() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.4, 0.4],  # sum is 0.8
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
        })
    assert "does not sum to 1.0" in str(exc.value)


def test_reject_initial_distribution_sum_not_equal_to_one() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.3, 0.3],  # sum is 0.6
            "steps": 1,
        })
    assert "initial_distribution does not sum to 1.0" in str(exc.value)


# ---------------------------------------------------------------------------
# 5. State Labels & Time Step Validations
# ---------------------------------------------------------------------------


def test_reject_invalid_state_labels_length() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
            "state_labels": ["only_one"],
        })
    assert "does not match dimension" in str(exc.value)


def test_reject_duplicate_state_labels() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
            "state_labels": ["state_a", "state_a"],
        })
    assert "must contain distinct strings" in str(exc.value)


def test_reject_empty_string_state_label() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
            "state_labels": ["valid", "   "],
        })
    assert "cannot be empty" in str(exc.value)


def test_reject_empty_time_step() -> None:
    with pytest.raises(MarkovValidationError) as exc:
        propagate_markov({
            "operation": "markov_propagate",
            "transition_matrix": [
                [0.5, 0.5],
                [0.5, 0.5],
            ],
            "initial_distribution": [0.5, 0.5],
            "steps": 1,
            "time_step": "   ",
        })
    assert "'time_step' cannot be empty" in str(exc.value)


# ---------------------------------------------------------------------------
# 6. Safety, Metadata, and Domain-Neutral Declarations
# ---------------------------------------------------------------------------


def test_contract_metadata_and_domain_neutral_declarations() -> None:
    request = {
        "operation": "markov_propagate",
        "transition_matrix": [
            [0.6, 0.4],
            [0.3, 0.7],
        ],
        "initial_distribution": [0.5, 0.5],
        "steps": 5,
    }
    result = propagate_markov(request)

    # Status and safety
    assert result["status"] == "ok"
    assert result["operation"] == "markov_propagate"
    assert result["safety"] == SAFETY_DECLARATION
    assert result["safety"] == "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"

    # Solver
    assert result["solver"]["name"] == "markov_matrix_exponentiation"
    assert result["solver"]["algorithm"] == "binary_exponentiation"
    assert result["solver"]["framework"] == "standard_library"

    # Assumptions & Limitations (must be domain-neutral)
    limitations_text = " ".join(result["limitations"])
    assert "causal effects" in limitations_text
    assert "predictive accuracy" in limitations_text
    # Ensure domain-neutral phrasing
    assert "exogenous shocks" in limitations_text


# ---------------------------------------------------------------------------
# 7. Standard Library Purity and Performance Budget (n=128, steps=10000)
# ---------------------------------------------------------------------------


def test_no_scientific_dependencies_imported() -> None:
    # Ensure numpy and scipy are not imported by markov module
    assert "smartmoney_cub_harness.numerical.markov" in sys.modules
    # markov module itself should not have imported numpy or scipy
    import smartmoney_cub_harness.numerical.markov as markov_mod
    assert not hasattr(markov_mod, "np")
    assert not hasattr(markov_mod, "scipy")


def test_performance_budget_at_max_dimensions_and_steps() -> None:
    # Max dimension n = 128, max steps = 10000
    n = 128
    prob = 1.0 / n
    matrix = [[prob] * n for _ in range(n)]
    init_dist = [prob] * n

    request = {
        "operation": "markov_propagate",
        "transition_matrix": matrix,
        "initial_distribution": init_dist,
        "steps": MAX_STEPS,
    }

    t0 = time.perf_counter()
    result = propagate_markov(request)
    elapsed = time.perf_counter() - t0

    assert result["status"] == "ok"
    assert result["diagnostics"]["steps"] == MAX_STEPS
    assert result["diagnostics"]["dimension"] == n
    assert len(result["distribution"]) == n
    assert math.isclose(sum(result["distribution"]), 1.0, abs_tol=1e-12)
    # Binary exponentiation for 10000 steps should easily complete in under 2 seconds in pure Python
    assert elapsed < 2.0, f"Propagation took too long: {elapsed:.2f}s (budget: 2.0s)"
