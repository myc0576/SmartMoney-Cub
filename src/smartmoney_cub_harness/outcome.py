from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.safety import redact
from smartmoney_cub_harness.schemas import OUTCOME_SCHEMA, SAFETY_DECLARATION, VALID_HORIZONS


def _parse_decision_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


PACKAGE_RESOURCE_PREFIX = "smartmoney_cub_harness:"


def resolve_price_source(price_source: str | Path) -> Path:
    """Resolve a price source path, including packaged resource references.

    The toy loop records its price source as a package resource reference so an
    installed copy stays independent of any source checkout. Read commands must
    resolve the same reference form.
    """
    text = str(price_source)
    if text.startswith(PACKAGE_RESOURCE_PREFIX):
        from importlib.resources import files

        relative = text[len(PACKAGE_RESOURCE_PREFIX) :]
        _, _, resource = relative.partition("/")
        target = files("smartmoney_cub_harness").joinpath("data", resource or relative)
        return Path(str(target))
    return Path(text)


def _load_prices(price_source: str | Path) -> dict[str, Any]:
    return json.loads(resolve_price_source(price_source).read_text(encoding="utf-8"))


def _collect_codes(value: Any) -> list[str]:
    codes: list[str] = []
    if isinstance(value, dict):
        code = value.get("code") or value.get("symbol")
        if isinstance(code, str) and code:
            codes.append(code)
        for nested in value.values():
            codes.extend(_collect_codes(nested))
    elif isinstance(value, list):
        for item in value:
            codes.extend(_collect_codes(item))
    return codes


def _candidate_codes(value: Any) -> list[str]:
    codes: list[str] = []
    if not isinstance(value, dict):
        return codes

    for key in ("selected_candidate", "decision_candidate", "signal_candidate", "observation_candidate"):
        candidate = value.get(key)
        if isinstance(candidate, dict):
            code = candidate.get("code") or candidate.get("symbol")
            if isinstance(code, str) and code:
                codes.append(code)

    for key in ("signal_candidates", "top_pool_candidates", "candidates", "observation_candidates"):
        candidates = value.get(key)
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if isinstance(candidate, dict):
                code = candidate.get("code") or candidate.get("symbol")
                if isinstance(code, str) and code:
                    codes.append(code)
    return codes


def _derive_symbol(run_path: Path, decision: dict[str, Any], prices: dict[str, Any]) -> str:
    explicit = decision.get("symbol") or decision.get("code")
    if isinstance(explicit, str) and explicit:
        return explicit

    artifact_dir = run_path / "artifacts"
    all_codes: list[str] = []
    if artifact_dir.exists():
        for artifact in sorted(artifact_dir.glob("*.stdout.txt")):
            try:
                payload = json.loads(artifact.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            all_codes.extend(_collect_codes(payload))
            for code in _candidate_codes(payload):
                if code in prices:
                    return code

    matched_codes = sorted({code for code in all_codes if code in prices})
    if len(matched_codes) > 1:
        raise ValueError(f"ambiguous decision symbol candidates: {', '.join(matched_codes)}")
    if len(matched_codes) == 1 and len(set(all_codes)) == 1:
        return matched_codes[0]

    if not all_codes and len(prices) == 1:
        return next(iter(prices))
    raise ValueError("decision.json requires symbol/code, or artifacts must contain an unambiguous candidate code")


def _select_exit_date(available_dates: list[str], decision_day: str, horizon: str) -> str:
    target = datetime.strptime(decision_day, "%Y%m%d") + timedelta(days=VALID_HORIZONS[horizon])
    target_key = target.strftime("%Y%m%d")
    later_dates = [date for date in available_dates if date > decision_day]
    if not later_dates:
        raise ValueError(f"no prices after decision date {decision_day}")
    for date in later_dates:
        if date >= target_key:
            return date
    return later_dates[-1]


def _price_value(day_data: dict[str, Any], field: str) -> float:
    if field not in day_data:
        raise ValueError(f"missing price field: {field}")
    return float(day_data[field])


def build_outcome(
    run_dir: str | Path,
    horizon: str,
    price_source: str | Path,
    *,
    price_source_label: str | None = None,
) -> Path:
    if horizon not in VALID_HORIZONS:
        raise ValueError("horizon must be one of: d1, d3")

    run_path = Path(run_dir)
    decision_path = run_path / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision_time = decision.get("decision_time")
    if not decision_time:
        raise ValueError("decision.json requires decision_time")

    prices = _load_prices(price_source)
    symbol = _derive_symbol(run_path, decision, prices)
    symbol_prices = prices.get(symbol)
    if not isinstance(symbol_prices, dict):
        raise ValueError(f"price source missing symbol: {symbol}")

    decision_day = _parse_decision_date(str(decision_time)).strftime("%Y%m%d")
    available_dates = sorted(symbol_prices)
    if decision_day not in symbol_prices:
        raise ValueError(f"price source missing decision date: {decision_day}")
    exit_date = _select_exit_date(available_dates, decision_day, horizon)

    entry_close = _price_value(symbol_prices[decision_day], "close")
    exit_close = _price_value(symbol_prices[exit_date], "close")
    lows = [
        float(symbol_prices[date].get("low", symbol_prices[date].get("close")))
        for date in available_dates
        if decision_day < date <= exit_date
    ]
    min_low = min(lows) if lows else exit_close
    return_pct = round((exit_close / entry_close - 1) * 100, 2)
    adverse_pct = round((min_low / entry_close - 1) * 100, 2)

    outcome = {
        "schema": OUTCOME_SCHEMA,
        "symbol": symbol,
        "horizon": horizon,
        "decision_time": decision_time,
        "decision_path": str(redact(str(decision_path))),
        "entry_date": decision_day,
        "entry_close": entry_close,
        "exit_date": exit_date,
        "exit_close": exit_close,
        f"{horizon}_return_pct": return_pct,
        "max_adverse_excursion_pct": adverse_pct,
        "met_user_pattern": bool(symbol_prices[exit_date].get("met_user_pattern", False)),
        "price_source": str(redact(price_source_label or str(price_source))),
        "price_source_type": "json_fixture",
        "safety": SAFETY_DECLARATION,
    }
    output_path = run_path / f"outcome_{horizon}.json"
    output_path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path
