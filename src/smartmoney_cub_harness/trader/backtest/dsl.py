"""The JSON strategy DSL.

A strategy is data. This module walks a payload against a frozen key whitelist
and returns a typed spec. It never turns the payload into Python and never
resolves anything the payload does not name. The engine downstream is a fixed
dispatch over the same closed vocabulary, so a strategy this file cannot
describe cannot run at all.

Two readings of the task brief are deliberate, because both are the stricter of
the available options:

* An operand is a declared indicator id and nothing else. A raw price series is
  named by declaring an identity indicator, for example
  {"id": "px", "kind": "sma", "source": "close", "period": 1}. Every operand is
  therefore resolvable when the strategy is validated, not when it runs.
* "all" is the only group key. The brief freezes {"all": [...]} and requires
  unknown keys to be rejected rather than ignored, so an unlisted group key such
  as "any" or "not" is rejected exactly as "leverage" is.

The top level also accepts "fill", with the two values the engine section of the
brief names, because the engine has to know when it may trade. It defaults to
"next_open", so a payload written to the frozen shape alone is valid.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, NoReturn

DSL_VERSION = 1

INDICATOR_KINDS = ("sma", "ema", "rsi", "atr", "highest", "lowest", "volume_sma")
INDICATOR_SOURCES = ("open", "high", "low", "close", "volume")
COMPARISON_OPERATORS = ("gt", "lt", "gte", "lte", "crosses_above", "crosses_below", "is_true")
SIZING_KINDS = ("fixed_fraction", "fixed_quantity", "risk_percent")
STOP_KINDS = ("percent", "atr_multiple", "none")
TARGET_KINDS = ("r_multiple", "percent", "none")
FILL_MODES = ("next_open", "same_close")

TOP_LEVEL_KEYS = (
    "version",
    "name",
    "universe",
    "indicators",
    "entry",
    "exit",
    "stop",
    "target",
    "sizing",
    "filters",
    "fill",
)
REQUIRED_TOP_LEVEL_KEYS = (
    "version",
    "name",
    "universe",
    "indicators",
    "entry",
    "exit",
    "stop",
    "target",
    "sizing",
    "filters",
)
UNIVERSE_KEYS = ("symbol", "interval")
INDICATOR_KEYS = ("id", "kind", "source", "period")
RULE_KEYS = ("all",)
STOP_KEYS = ("kind", "value")
TARGET_KEYS = ("kind", "value")
SIZING_KEYS = ("kind", "value")
FILTER_KEYS = ("session", "min_bars")

# A cross reads the current and the previous value on both series, so it takes
# exactly two operands, like a level comparison does.
OPERATOR_ARITY = {
    "gt": 2,
    "lt": 2,
    "gte": 2,
    "lte": 2,
    "crosses_above": 2,
    "crosses_below": 2,
    "is_true": 1,
}


class StrategyError(ValueError):
    """A payload is not describable by the frozen DSL.

    The message always carries the key path that failed, so a caller can point
    at the offending line of a strategy file without re-deriving the walk.
    """

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}" if path else message)


def _fail(path: str, message: str) -> NoReturn:
    raise StrategyError(path, message)


def _reject_unknown(value: Mapping[str, Any], allowed: tuple[str, ...], path: str) -> None:
    """Reject every key the DSL does not name.

    These are visited in sorted order, so the first failure a caller sees is the
    same on every run.
    """
    for key in sorted(str(item) for item in value):
        if key not in allowed:
            child = f"{path}.{key}" if path else key
            _fail(child, f"unknown key {key!r}")


def _require_keys(value: Mapping[str, Any], required: tuple[str, ...], path: str) -> None:
    for key in required:
        if key not in value:
            _fail(path, f"missing required key {key!r}")


def _as_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(path, f"expected an object, got {type(value).__name__}")
    return value


def _as_text(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _fail(path, f"expected a string, got {type(value).__name__}")
    text = value.strip()
    if not text:
        _fail(path, "expected a non-empty string")
    return text


def _as_int(value: Any, path: str, *, minimum: int) -> int:
    # bool is an int in Python, and true is never a period.
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, f"expected an integer, got {value!r}")
    if value < minimum:
        _fail(path, f"expected an integer >= {minimum}, got {value!r}")
    return value


def _as_whole_number(value: Any, path: str, *, minimum: int) -> int:
    """A count, accepted as an integer or as an integral float.

    JSON writes 100 and 100.0 into the same field, and a spec that round-trips
    through to_dict and back has to survive both, so "100.0 shares" is read as
    one hundred rather than refused. A fraction is still an error.
    """
    if isinstance(value, bool):
        _fail(path, f"expected a whole number, got {value!r}")
    if isinstance(value, int):
        number = value
    elif isinstance(value, float) and math.isfinite(value) and float(value).is_integer():
        number = int(value)
    else:
        _fail(path, f"expected a whole number, got {value!r}")
    if number < minimum:
        _fail(path, f"expected a whole number >= {minimum}, got {value!r}")
    return number


def _as_number(value: Any, path: str, *, minimum: float, exclusive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, f"expected a number, got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        _fail(path, f"expected a finite number, got {value!r}")
    if exclusive and number <= minimum:
        _fail(path, f"expected a number greater than {minimum}, got {value!r}")
    if not exclusive and number < minimum:
        _fail(path, f"expected a number >= {minimum}, got {value!r}")
    return number


def _as_fraction(value: Any, path: str) -> float:
    """A share of equity, in (0, 1].

    Fixed fraction and risk percent share this scale, so the two sizing kinds
    read the same way: 0.01 commits or risks one percent.
    """
    number = _as_number(value, path, minimum=0.0, exclusive=True)
    if number > 1.0:
        _fail(path, f"expected a fraction of equity in (0, 1], got {value!r}")
    return number


def _as_choice(value: Any, path: str, allowed: tuple[str, ...]) -> str:
    text = _as_text(value, path)
    if text not in allowed:
        _fail(path, f"unknown value {text!r}; expected one of {', '.join(allowed)}")
    return text


@dataclass(frozen=True)
class Operand:
    """A reference to one declared indicator series."""

    indicator_id: str


@dataclass(frozen=True)
class ConditionSpec:
    operator: str
    operands: tuple[Operand, ...]


@dataclass(frozen=True)
class RuleSpec:
    """A conjunction of comparisons.

    The brief freezes "all" as the only group form, so a rule is exactly that:
    every condition listed must hold.
    """

    conditions: tuple[ConditionSpec, ...]


@dataclass(frozen=True)
class IndicatorSpec:
    id: str
    kind: str
    source: str
    period: int


@dataclass(frozen=True)
class StopSpec:
    kind: str
    value: float | None


@dataclass(frozen=True)
class TargetSpec:
    kind: str
    value: float | None


@dataclass(frozen=True)
class SizingSpec:
    kind: str
    value: float


@dataclass(frozen=True)
class FilterSpec:
    session: None
    min_bars: int


@dataclass(frozen=True)
class UniverseSpec:
    symbol: str
    interval: str


@dataclass(frozen=True)
class StrategySpec:
    version: int
    name: str
    universe: UniverseSpec
    indicators: tuple[IndicatorSpec, ...]
    entry: RuleSpec
    exit: RuleSpec
    stop: StopSpec
    target: TargetSpec
    sizing: SizingSpec
    filters: FilterSpec
    fill: str = "next_open"

    @property
    def indicator_ids(self) -> tuple[str, ...]:
        return tuple(indicator.id for indicator in self.indicators)

    @property
    def atr_indicator_id(self) -> str | None:
        """The ATR series an atr_multiple stop measures from.

        The frozen shape carries no key for naming a series inside "stop", so
        the first declared atr indicator is the one that measures the distance.
        Validation refuses an atr_multiple stop when no such indicator exists,
        which keeps that choice explicit in the payload rather than an implicit
        default here.
        """
        for indicator in self.indicators:
            if indicator.kind == "atr":
                return indicator.id
        return None

    def to_dict(self) -> dict[str, Any]:
        """The canonical payload for this spec, for run artifacts and hashing."""
        return {
            "version": self.version,
            "name": self.name,
            "universe": {"symbol": self.universe.symbol, "interval": self.universe.interval},
            "indicators": [
                {
                    "id": indicator.id,
                    "kind": indicator.kind,
                    "source": indicator.source,
                    "period": indicator.period,
                }
                for indicator in self.indicators
            ],
            "entry": _rule_to_dict(self.entry),
            "exit": _rule_to_dict(self.exit),
            "stop": _limit_to_dict(self.stop),
            "target": _limit_to_dict(self.target),
            "sizing": {"kind": self.sizing.kind, "value": self.sizing.value},
            "filters": {"session": None, "min_bars": self.filters.min_bars},
            "fill": self.fill,
        }


def _rule_to_dict(rule: RuleSpec) -> dict[str, Any]:
    return {
        "all": [
            {condition.operator: [operand.indicator_id for operand in condition.operands]}
            for condition in rule.conditions
        ]
    }


def _limit_to_dict(limit: StopSpec | TargetSpec) -> dict[str, Any]:
    if limit.kind == "none":
        return {"kind": "none"}
    return {"kind": limit.kind, "value": limit.value}


def validate_strategy(payload: Mapping[str, Any]) -> StrategySpec:
    """Validate a strategy payload and return the typed spec.

    Every failure is a StrategyError naming the key path that failed, for
    example: entry.all[0].crosses_above: unknown indicator id 'x'. Unknown keys
    are an error, never a silently ignored extra.
    """
    root = _as_mapping(payload, "strategy")
    _reject_unknown(root, TOP_LEVEL_KEYS, "")
    _require_keys(root, REQUIRED_TOP_LEVEL_KEYS, "strategy")

    version = root["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != DSL_VERSION:
        _fail("version", f"unsupported DSL version {version!r}; expected {DSL_VERSION}")

    universe_raw = _as_mapping(root["universe"], "universe")
    _reject_unknown(universe_raw, UNIVERSE_KEYS, "universe")
    _require_keys(universe_raw, UNIVERSE_KEYS, "universe")
    universe = UniverseSpec(
        symbol=_as_text(universe_raw["symbol"], "universe.symbol"),
        interval=_as_text(universe_raw["interval"], "universe.interval"),
    )

    indicators_raw = root["indicators"]
    if not isinstance(indicators_raw, (list, tuple)) or not indicators_raw:
        _fail("indicators", "expected a non-empty list of indicators")
    indicators: list[IndicatorSpec] = []
    for index, item in enumerate(indicators_raw):
        path = f"indicators[{index}]"
        entry = _as_mapping(item, path)
        _reject_unknown(entry, INDICATOR_KEYS, path)
        _require_keys(entry, INDICATOR_KEYS, path)
        kind = _as_choice(entry["kind"], f"{path}.kind", INDICATOR_KINDS)
        source = _as_choice(entry["source"], f"{path}.source", INDICATOR_SOURCES)
        indicator_id = _as_text(entry["id"], f"{path}.id")
        if any(existing.id == indicator_id for existing in indicators):
            _fail(f"{path}.id", f"duplicate indicator id {indicator_id!r}")
        if kind == "volume_sma" and source != "volume":
            _fail(f"{path}.source", "volume_sma reads the volume field; expected 'volume'")
        indicators.append(
            IndicatorSpec(
                id=indicator_id,
                kind=kind,
                source=source,
                period=_as_int(entry["period"], f"{path}.period", minimum=1),
            )
        )

    known_ids = tuple(indicator.id for indicator in indicators)
    entry_rule = _parse_rule(root["entry"], "entry", known_ids)
    exit_rule = _parse_rule(root["exit"], "exit", known_ids)

    stop = _parse_stop(root["stop"], indicators)
    target = _parse_target(root["target"])
    sizing = _parse_sizing(root["sizing"])
    filters = _parse_filters(root["filters"])
    fill = _as_choice(root.get("fill", "next_open"), "fill", FILL_MODES)

    if target.kind == "r_multiple" and stop.kind == "none":
        _fail("target.kind", "r_multiple measures from the stop distance; stop.kind 'none' has none")
    if sizing.kind == "risk_percent" and stop.kind == "none":
        _fail("sizing.kind", "risk_percent sizes from the stop distance; stop.kind 'none' has none")

    return StrategySpec(
        version=version,
        name=_as_text(root["name"], "name"),
        universe=universe,
        indicators=tuple(indicators),
        entry=entry_rule,
        exit=exit_rule,
        stop=stop,
        target=target,
        sizing=sizing,
        filters=filters,
        fill=fill,
    )


def _parse_rule(value: Any, path: str, known_ids: tuple[str, ...]) -> RuleSpec:
    rule = _as_mapping(value, path)
    _require_keys(rule, RULE_KEYS, path)
    _reject_unknown(rule, RULE_KEYS, path)
    items = rule["all"]
    if not isinstance(items, (list, tuple)) or not items:
        _fail(f"{path}.all", "expected a non-empty list of conditions")
    return RuleSpec(
        conditions=tuple(
            _parse_condition(item, f"{path}.all[{index}]", known_ids)
            for index, item in enumerate(items)
        )
    )


def _parse_condition(value: Any, path: str, known_ids: tuple[str, ...]) -> ConditionSpec:
    condition = _as_mapping(value, path)
    unlisted = sorted(key for key in condition if key not in COMPARISON_OPERATORS)
    if unlisted:
        _fail(f"{path}.{unlisted[0]}", f"unknown key {unlisted[0]!r}")
    operators = [key for key in condition if key in COMPARISON_OPERATORS]
    if len(operators) != 1:
        _fail(path, "expected exactly one comparison operator")
    operator = operators[0]
    raw_operands = condition[operator]
    if not isinstance(raw_operands, (list, tuple)):
        _fail(f"{path}.{operator}", "expected a list of operands")
    arity = OPERATOR_ARITY[operator]
    if len(raw_operands) != arity:
        _fail(
            f"{path}.{operator}",
            f"operator {operator!r} takes {arity} operand(s), got {len(raw_operands)}",
        )
    operands = tuple(
        _parse_operand(item, f"{path}.{operator}", known_ids, position=index + 1)
        for index, item in enumerate(raw_operands)
    )
    return ConditionSpec(operator=operator, operands=operands)


def _parse_operand(value: Any, path: str, known_ids: tuple[str, ...], *, position: int) -> Operand:
    """One operand of a comparison.

    The key path in a failure is the operator itself, matching the documented
    shape of entry.all[0].crosses_above: unknown indicator id 'x'. Which
    operand was at fault is carried in the message, not appended to the path.
    """
    if not isinstance(value, str):
        _fail(path, f"operand {position} expected an indicator id, got {type(value).__name__}")
    indicator_id = value.strip()
    if indicator_id not in known_ids:
        _fail(path, f"unknown indicator id {indicator_id!r} (operand {position})")
    return Operand(indicator_id=indicator_id)


def _parse_stop(value: Any, indicators: list[IndicatorSpec]) -> StopSpec:
    stop = _as_mapping(value, "stop")
    _reject_unknown(stop, STOP_KEYS, "stop")
    _require_keys(stop, ("kind",), "stop")
    kind = _as_choice(stop["kind"], "stop.kind", STOP_KINDS)
    if kind == "none":
        if "value" in stop:
            _fail("stop.value", "stop.kind 'none' takes no value")
        return StopSpec(kind=kind, value=None)
    if "value" not in stop:
        _fail("stop", f"missing required key 'value' for stop.kind {kind!r}")
    number = _as_number(stop["value"], "stop.value", minimum=0.0, exclusive=True)
    if kind == "percent" and number >= 100.0:
        _fail("stop.value", f"a percent stop must be below 100.0, got {number!r}")
    if kind == "atr_multiple" and not any(indicator.kind == "atr" for indicator in indicators):
        _fail("stop.kind", "atr_multiple needs a declared 'atr' indicator to measure the distance")
    return StopSpec(kind=kind, value=number)


def _parse_target(value: Any) -> TargetSpec:
    target = _as_mapping(value, "target")
    _reject_unknown(target, TARGET_KEYS, "target")
    _require_keys(target, ("kind",), "target")
    kind = _as_choice(target["kind"], "target.kind", TARGET_KINDS)
    if kind == "none":
        if "value" in target:
            _fail("target.value", "target.kind 'none' takes no value")
        return TargetSpec(kind=kind, value=None)
    if "value" not in target:
        _fail("target", f"missing required key 'value' for target.kind {kind!r}")
    number = _as_number(target["value"], "target.value", minimum=0.0, exclusive=True)
    if kind == "percent" and number >= 100.0:
        _fail("target.value", f"a percent target must be below 100.0, got {number!r}")
    return TargetSpec(kind=kind, value=number)


def _parse_sizing(value: Any) -> SizingSpec:
    sizing = _as_mapping(value, "sizing")
    _reject_unknown(sizing, SIZING_KEYS, "sizing")
    _require_keys(sizing, SIZING_KEYS, "sizing")
    kind = _as_choice(sizing["kind"], "sizing.kind", SIZING_KINDS)
    if kind == "fixed_quantity":
        # Quantities are whole shares, and keeping the int is what lets
        # to_dict round-trip back through validate_strategy unchanged.
        return SizingSpec(kind=kind, value=_as_whole_number(sizing["value"], "sizing.value", minimum=1))
    return SizingSpec(kind=kind, value=_as_fraction(sizing["value"], "sizing.value"))


def _parse_filters(value: Any) -> FilterSpec:
    filters = _as_mapping(value, "filters")
    _reject_unknown(filters, FILTER_KEYS, "filters")
    _require_keys(filters, FILTER_KEYS, "filters")
    if filters["session"] is not None:
        _fail("filters.session", "session filters are not part of the frozen DSL; expected null")
    min_bars = filters["min_bars"]
    if min_bars is None:
        return FilterSpec(session=None, min_bars=0)
    return FilterSpec(session=None, min_bars=_as_int(min_bars, "filters.min_bars", minimum=0))


def load_strategy(payload: Mapping[str, Any] | str | bytes) -> StrategySpec:
    """Validate a strategy from a mapping, a JSON string, or JSON bytes.

    Text is decoded as JSON and nothing else. There is no second language here:
    a payload that is not JSON data is a StrategyError, never something that
    gets run. Duplicate keys are refused rather than letting the last one win,
    because a strategy whose meaning depends on key order is a strategy nobody
    can review.
    """
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            loaded = json.loads(
                text,
                parse_constant=_reject_json_constant,
                object_pairs_hook=_object_without_duplicates,
            )
        except StrategyError:
            raise
        except UnicodeDecodeError as exc:
            _fail("strategy", f"payload is not UTF-8: {exc}")
        except ValueError as exc:
            _fail("strategy", f"invalid JSON: {exc}")
        payload = loaded
    return validate_strategy(payload)


def _reject_json_constant(name: str) -> NoReturn:
    raise StrategyError("strategy", f"{name} is not valid JSON")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise StrategyError("strategy", f"duplicate key {key!r}")
        result[key] = item
    return result


__all__ = [
    "COMPARISON_OPERATORS",
    "ConditionSpec",
    "DSL_VERSION",
    "FILL_MODES",
    "FilterSpec",
    "INDICATOR_KINDS",
    "INDICATOR_SOURCES",
    "IndicatorSpec",
    "OPERATOR_ARITY",
    "Operand",
    "RuleSpec",
    "SIZING_KINDS",
    "STOP_KINDS",
    "SizingSpec",
    "StopSpec",
    "StrategyError",
    "StrategySpec",
    "TARGET_KINDS",
    "TargetSpec",
    "UniverseSpec",
    "load_strategy",
    "validate_strategy",
]
