"""Reference subprocess provider for the harness plugin contract.

Reads one JSON request from stdin and writes one JSON response to stdout. It is a
report-only reviewer: it produces observations and never places, cancels, or
advises a trade.
"""

from __future__ import annotations

import json
import sys

SAFETY = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"


def review(request: dict) -> dict:
    symbol = str(request.get("symbol") or "UNKNOWN")
    return_pct = float(request.get("return_pct") or 0.0)
    invalidation = request.get("invalidation_price")

    observations: list[dict] = []
    if return_pct < -5.0:
        observations.append(
            {
                "kind": "review_observation",
                "severity": "high",
                "symbol": symbol,
                "detail": f"loss of {return_pct}% exceeded the -5% review threshold",
            }
        )
        if invalidation is None:
            observations.append(
                {
                    "kind": "review_observation",
                    "severity": "high",
                    "symbol": symbol,
                    "detail": "position was opened without a recorded invalidation price",
                }
            )
    elif return_pct > 0:
        observations.append(
            {
                "kind": "review_observation",
                "severity": "info",
                "symbol": symbol,
                "detail": f"closed with {return_pct}%; record whether the process was repeatable",
            }
        )
    else:
        observations.append(
            {
                "kind": "review_observation",
                "severity": "info",
                "symbol": symbol,
                "detail": "flat or untagged result; no rule signal inferred",
            }
        )

    return {
        "observations": observations,
        "result_kind": "review_observation",
        "safety": SAFETY,
    }


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        request = json.loads(raw)
    except json.JSONDecodeError:
        request = {}
    if not isinstance(request, dict):
        request = {}
    sys.stdout.write(json.dumps(review(request), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
