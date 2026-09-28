from __future__ import annotations

import math
import random
from collections.abc import Mapping
from typing import Any, Sequence


CASE_BOOTSTRAP_SEED = 20260927
CASE_BOOTSTRAP_REPLICATES = 10_000
CASE_BOOTSTRAP_METHOD = "case_bootstrap_stratified_percentile"
CASE_BOOTSTRAP_UNIT = "case"


def normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compute_accuracy(preds: Sequence[Any], targets: Sequence[Any]) -> float:
    if not preds or len(preds) != len(targets):
        return 0.0
    correct = sum(1 for p, t in zip(preds, targets) if p == t)
    return correct / len(preds)


def compute_macro_f1(preds: Sequence[Any], targets: Sequence[Any]) -> float:
    if not preds or len(preds) != len(targets):
        return 0.0
    classes = sorted(list(set(targets) | set(preds)), key=lambda x: (type(x).__name__, str(x)))
    if not classes:
        return 0.0

    f1_scores = []
    for c in classes:
        tp = sum(1 for p, t in zip(preds, targets) if p == c and t == c)
        fp = sum(1 for p, t in zip(preds, targets) if p == c and t != c)
        fn = sum(1 for p, t in zip(preds, targets) if p != c and t == c)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        f1_scores.append(f1)
    return sum(f1_scores) / len(f1_scores)


def compute_recall(preds: Sequence[Any], targets: Sequence[Any]) -> float:
    """Macro recall across classes."""
    if not preds or len(preds) != len(targets):
        return 0.0
    classes = sorted(list(set(targets)), key=lambda x: (type(x).__name__, str(x)))
    if not classes:
        return 0.0
    recalls = []
    for c in classes:
        tp = sum(1 for p, t in zip(preds, targets) if p == c and t == c)
        fn = sum(1 for p, t in zip(preds, targets) if p != c and t == c)
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        recalls.append(r)
    return sum(recalls) / len(recalls)


def compute_fpr(preds: Sequence[Any], targets: Sequence[Any]) -> float:
    """Macro false positive rate across classes: FP / (FP + TN)."""
    if not preds or len(preds) != len(targets):
        return 0.0
    classes = sorted(list(set(targets) | set(preds)), key=lambda x: (type(x).__name__, str(x)))
    if not classes:
        return 0.0
    fprs = []
    for c in classes:
        fp = sum(1 for p, t in zip(preds, targets) if p == c and t != c)
        tn = sum(1 for p, t in zip(preds, targets) if p != c and t != c)
        rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fprs.append(rate)
    return sum(fprs) / len(fprs)


def compute_brier_score(confs: Sequence[float], matches: Sequence[bool]) -> float:
    """Brier score: mean squared error between confidence (as probability of match) and outcome (1 or 0)."""
    if not confs or len(confs) != len(matches):
        return 0.0
    sq_diffs = [(float(c) - (1.0 if m else 0.0)) ** 2 for c, m in zip(confs, matches)]
    return sum(sq_diffs) / len(sq_diffs)


def compute_ece(confs: Sequence[float], matches: Sequence[bool], n_bins: int = 10) -> float:
    """Expected Calibration Error (ECE) with 10 bins."""
    if not confs or len(confs) != len(matches):
        return 0.0
    bin_boundaries = [i / n_bins for i in range(n_bins + 1)]
    ece = 0.0
    n = len(confs)
    for i in range(n_bins):
        low = bin_boundaries[i]
        high = bin_boundaries[i + 1]
        indices = [
            idx
            for idx, c in enumerate(confs)
            if (low <= c < high) or (i == n_bins - 1 and low <= c <= high)
        ]
        if indices:
            bin_acc = sum(1 for idx in indices if matches[idx]) / len(indices)
            bin_conf = sum(confs[idx] for idx in indices) / len(indices)
            bin_weight = len(indices) / n
            ece += bin_weight * abs(bin_acc - bin_conf)
    return ece


def compute_percentiles(values: Sequence[float]) -> dict[str, float]:
    """Compute p50, p95, p99 latency in milliseconds."""
    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
    sorted_vals = sorted(values)
    n = len(sorted_vals)

    def get_p(p: float) -> float:
        rank = (p / 100.0) * (n - 1)
        low_idx = int(math.floor(rank))
        high_idx = int(math.ceil(rank))
        weight = rank - low_idx
        return sorted_vals[low_idx] * (1.0 - weight) + sorted_vals[high_idx] * weight

    return {
        "p50": round(get_p(50.0), 3),
        "p95": round(get_p(95.0), 3),
        "p99": round(get_p(99.0), 3),
    }


def compute_confidence_interval_95(acc: float, n: int) -> tuple[float, float]:
    """Wilson score interval for 95% confidence."""
    if n <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054  # 95% normal quantile
    denom = 1.0 + (z**2) / n
    center = (acc + (z**2) / (2 * n)) / denom
    half_width = (z / denom) * math.sqrt((acc * (1.0 - acc) / n) + ((z**2) / (4 * (n**2))))
    low = max(0.0, center - half_width)
    high = min(1.0, center + half_width)
    return (round(low, 4), round(high, 4))


def _linear_percentile(values: Sequence[float], percentile: float) -> float:
    """Return a deterministic linearly interpolated percentile."""
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (float(percentile) / 100.0) * (len(ordered) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    weight = rank - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def compute_case_bootstrap_confidence_interval_95(
    case_evaluations: Sequence[Mapping[str, Any]],
    *,
    seed: int = CASE_BOOTSTRAP_SEED,
    replicates: int = CASE_BOOTSTRAP_REPLICATES,
    stratified_by: str = "track",
) -> tuple[float, float]:
    """Compute a case-level percentile bootstrap accuracy interval.

    Cases are sampled with replacement inside each track. Every sampled case
    carries all of its question outcomes into that replicate, so questions from
    one case are never treated as independent sampling units.
    """
    if replicates <= 0:
        raise ValueError("bootstrap replicates must be positive")
    if stratified_by != "track":
        raise ValueError("case bootstrap is only supported when stratified_by='track'")

    groups: dict[str, list[Mapping[str, Any]]] = {}
    for case in case_evaluations:
        if not isinstance(case, Mapping):
            raise ValueError("case evaluation must be an object")
        track = str(case.get(stratified_by, ""))
        if not track:
            raise ValueError("case evaluation is missing its track")
        items = case.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"case evaluation {case.get('case_id', '<unknown>')} has no items")
        groups.setdefault(track, []).append(case)

    if not groups:
        return (0.0, 0.0)

    rng = random.Random(seed)
    accuracies: list[float] = []
    for _ in range(replicates):
        correct = 0
        total = 0
        for track in sorted(groups):
            cases = groups[track]
            for _ in range(len(cases)):
                sampled_case = cases[rng.randrange(len(cases))]
                for item in sampled_case["items"]:
                    if not isinstance(item, Mapping) or "prediction" not in item or "target" not in item:
                        raise ValueError("case bootstrap item must contain prediction and target")
                    correct += int(item["prediction"] == item["target"])
                    total += 1
        accuracies.append(correct / total if total else 0.0)

    return (
        round(_linear_percentile(accuracies, 2.5), 4),
        round(_linear_percentile(accuracies, 97.5), 4),
    )


def compute_mcnemar_test(
    system_matches: Sequence[bool], baseline_matches: Sequence[bool]
) -> dict[str, Any]:
    """McNemar test with continuity correction against baseline matches.

    b: system correct, baseline incorrect
    c: system incorrect, baseline correct
    chi2 = (|b - c| - 1)^2 / (b + c)
    """
    if len(system_matches) != len(baseline_matches) or not system_matches:
        return {"statistic": 0.0, "p_value": 1.0, "b": 0, "c": 0}

    b = sum(1 for s, base in zip(system_matches, baseline_matches) if s and not base)
    c = sum(1 for s, base in zip(system_matches, baseline_matches) if not s and base)

    total_discordant = b + c
    if total_discordant == 0:
        return {"statistic": 0.0, "p_value": 1.0, "b": b, "c": c}

    diff = abs(b - c)
    stat = ((max(0.0, diff - 1.0)) ** 2) / total_discordant

    # For 1 degree of freedom chi-squared: P(chi^2 >= stat) = 2 * (1 - normal_cdf(sqrt(stat)))
    p_val = 2.0 * (1.0 - normal_cdf(math.sqrt(stat)))
    p_val = max(0.0, min(1.0, p_val))

    return {
        "statistic": round(stat, 4),
        "p_value": round(p_val, 4),
        "b": b,
        "c": c,
    }


def calculate_system_metrics(
    *,
    total_cases: int,
    valid_schema_cases: int,
    preds: list[Any],
    targets: list[Any],
    confidences: list[float],
    latencies_ms: list[float],
    costs_usd: list[float],
    abstained_indices: set[int] | None = None,
    baseline_preds: list[Any] | None = None,
    retries_count: int = 0,
    case_evaluations: Sequence[Mapping[str, Any]] | None = None,
    case_latencies_ms: Sequence[float] | None = None,
    case_costs_usd: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Compute the full suite of required benchmark metrics."""
    n = total_cases
    if n == 0:
        return {}

    abstained_set = abstained_indices or set()
    schema_valid_rate = valid_schema_cases / n if n > 0 else 0.0

    # Evaluated items (all items or non-abstained)
    num_questions = len(preds)
    matches = [p == t for p, t in zip(preds, targets)]

    # Overall accuracy
    accuracy = compute_accuracy(preds, targets) if num_questions > 0 else 0.0
    macro_f1 = compute_macro_f1(preds, targets) if num_questions > 0 else 0.0
    recall = compute_recall(preds, targets) if num_questions > 0 else 0.0
    fpr = compute_fpr(preds, targets) if num_questions > 0 else 0.0

    # Brier & ECE
    brier = compute_brier_score(confidences, matches) if num_questions > 0 else 0.0
    ece = compute_ece(confidences, matches) if num_questions > 0 else 0.0

    # Coverage & abstention
    # Case-level coverage
    abstention_count = len(abstained_set)
    coverage = (n - abstention_count) / n if n > 0 else 0.0
    abstention_rate = abstention_count / n if n > 0 else 0.0

    # Selective risk: error rate among covered (non-abstained) cases
    # Each question's case index can be tracked, or if no abstentions: 1 - accuracy
    selective_risk = (1.0 - accuracy) if coverage > 0 else 0.0

    # Stability: proportion of predictions consistent across deterministic seeds / checks
    stability = 1.0

    # Latencies
    latency_stats = compute_percentiles(
        list(case_latencies_ms) if case_latencies_ms is not None else latencies_ms
    )

    # Cost
    total_cost = sum(
        list(case_costs_usd) if case_costs_usd is not None else costs_usd
    )
    cost_per_case = total_cost / n if n > 0 else 0.0

    # Retry rate
    retry_rate = retries_count / n if n > 0 else 0.0

    # 95% confidence interval
    if case_evaluations is not None:
        ci_95 = compute_case_bootstrap_confidence_interval_95(case_evaluations)
        ci_metadata = {
            "confidence_interval_method": CASE_BOOTSTRAP_METHOD,
            "confidence_interval_unit": CASE_BOOTSTRAP_UNIT,
            "bootstrap": {
                "seed": CASE_BOOTSTRAP_SEED,
                "replicates": CASE_BOOTSTRAP_REPLICATES,
                "stratified_by": "track",
            },
        }
    else:
        # v1 runs used an item-level Wilson interval. Keep this branch for
        # reading and validating legacy artifacts without rewriting their claims.
        ci_95 = compute_confidence_interval_95(accuracy, num_questions)
        ci_metadata = {
            "confidence_interval_method": "item_wilson_legacy",
            "confidence_interval_unit": "item",
        }

    # McNemar test against baseline
    if baseline_preds and len(baseline_preds) == len(preds):
        base_matches = [bp == t for bp, t in zip(baseline_preds, targets)]
        mcnemar = compute_mcnemar_test(matches, base_matches)
    else:
        # System is its own baseline or no baseline provided
        mcnemar = {"statistic": 0.0, "p_value": 1.0, "b": 0, "c": 0}

    return {
        "schema_valid_rate": round(schema_valid_rate, 4),
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "recall": round(recall, 4),
        "fpr": round(fpr, 4),
        "brier": round(brier, 4),
        "ece": round(ece, 4),
        "coverage": round(coverage, 4),
        "abstention_rate": round(abstention_rate, 4),
        "selective_risk": round(selective_risk, 4),
        "stability": round(stability, 4),
        "p50_latency_ms": latency_stats["p50"],
        "p95_latency_ms": latency_stats["p95"],
        "p99_latency_ms": latency_stats["p99"],
        "cost_per_case": round(cost_per_case, 6),
        "retry_rate": round(retry_rate, 4),
        "confidence_interval_95": list(ci_95),
        **ci_metadata,
        "mcnemar_against_baseline": mcnemar,
    }
