"""Pure, cursor-bounded replay and an isolated paper-training ledger.

No broker objects or execution adapters are imported here. A simulated request
is filled only when the next recorded bar is revealed. Rewinding training makes
a new branch; the original experiment remains available for comparison.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence
from uuid import uuid4

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _number(value: Any, name: str, *, positive: bool = False) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be finite numeric data") from None
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError(f"{name} must be finite" + (" and positive" if positive else ""))
    return number


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _bar_end(bar: Mapping[str, Any]) -> datetime:
    start = _time(str(bar["open_time"]))
    interval = str(bar["interval"])
    if interval == "1M":
        return start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1, day=1)
    minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}
    if interval in minutes:
        return start + timedelta(minutes=minutes[interval])
    if interval in ("1d", "1w"):
        return start + timedelta(days=7 if interval == "1w" else 1)
    raise ValueError("unsupported replay interval")


def _marker_index(fill: Mapping[str, Any], bars: list[dict[str, Any]]) -> int | None:
    raw = str(fill.get("timestamp") or fill.get("executed_at") or "")
    if not raw:
        day = str(fill.get("trade_date") or fill.get("date") or "")
        clock = str(fill.get("trade_time") or fill.get("time") or "")
        raw = day + ("T" + clock if clock else "")
    if not raw:
        return None
    for i, bar in enumerate(bars):
        # A daily candle is a session date, not a fabricated midnight execution.
        if bar["interval"] == "1d" and raw[:10] == str(bar["open_time"])[:10]:
            return i
        if len(raw) <= 10 and bar["interval"] not in ("1w", "1M"):
            continue  # Date-only fills cannot be assigned to an intraday candle.
        try:
            stamp, start, end = _time(raw), _time(str(bar["open_time"])), _bar_end(bar)
            if (stamp.tzinfo is None) != (start.tzinfo is None):
                continue  # Unknown source timezone: don't invent an alignment.
            if start <= stamp < end:
                return i
        except (ValueError, TypeError):
            continue
    return None


def create_record(*, symbol: str, interval: str, bars: Sequence[Mapping[str, Any]],
                  provenance: Mapping[str, Any], mode: str, initial_cash: Any,
                  account_id: str | None, fills: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if mode not in ("review", "training"):
        raise ValueError("mode must be review or training")
    initial = _number(initial_cash, "initial_cash", positive=True)
    series = [dict(bar) for bar in bars]
    if not series:
        raise ValueError("no bars to replay")
    previous = None
    for bar in series:
        if bar.get("symbol") != symbol or bar.get("interval") != interval:
            raise ValueError("replay bars must match symbol and interval")
        stamp = _time(str(bar["open_time"]))
        if previous is not None and stamp <= previous:
            raise ValueError("bars must be strictly chronological without duplicates")
        previous = stamp
        values = {key: _number(bar[key], key) for key in ("open", "high", "low", "close", "volume")}
        if values["volume"] < 0 or values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]) or values["low"] > values["high"]:
            raise ValueError("inconsistent OHLCV values")
        _bar_end(bar)
    markers = []
    unmatched = 0
    for fill in fills:
        if fill.get("symbol") != symbol or (account_id and fill.get("account_id") != account_id):
            continue
        index = _marker_index(fill, series)
        if index is None:
            unmatched += 1
            continue
        markers.append({"index": index, "time": series[index]["open_time"],
                        "trade_id": fill.get("trade_id") or fill.get("fill_id"),
                        "side": fill.get("side"), "price": fill.get("price"),
                        "quantity": fill.get("quantity"), "account_id": fill.get("account_id"),
                        "time_precision": fill.get("time_precision") or ("time" if fill.get("trade_time") else "date")})
    session_id = "RPL-" + uuid4().hex
    return {"session_id": session_id, "mode": mode, "symbol": symbol, "interval": interval,
            "account_id": account_id, "created_at": datetime.now(timezone.utc).isoformat(),
            "index": 0, "bars": series, "all_markers": markers,
            "unmatched_marker_count": unmatched, "provenance": dict(provenance),
            "training": {"branch_id": session_id, "initial_cash": float(initial),
                         "cash": float(initial), "position": 0.0, "orders": [], "fills": [],
                         "currency": "simulation_units", "fill_policy": "next_bar_open",
                         "cost_model": "zero_fees_zero_slippage", "simulated_only": True},
            "safety": SAFETY_DECLARATION}


def public_view(record: Mapping[str, Any]) -> dict[str, Any]:
    index = int(record["index"])
    provenance = dict(record.get("provenance") or {})
    training = deepcopy(record["training"])
    training["positions"] = [{"symbol": record["symbol"], "quantity": training["position"]}]
    return {"session_id": record["session_id"], "mode": record["mode"],
            "parent_session_id": record.get("parent_session_id"),
            "symbol": record["symbol"], "interval": record["interval"],
            "account_id": record.get("account_id"), "created_at": record["created_at"],
            "index": index, "cursor": index, "frame_count": len(record["bars"]),
            "bar_count": len(record["bars"]), "bars": deepcopy(record["bars"][:index + 1]),
            "markers": [dict(m) for m in record["all_markers"] if m["index"] <= index] if record["mode"] == "review" else [],
            "training": training if record["mode"] == "training" else None,
            "provenance": provenance, "source": provenance.get("source", "unknown"),
            "provider_id": provenance.get("provider_id", ""),
            "source_quality": provenance.get("source_quality", "unknown"),
            "fetched_at": provenance.get("fetched_at", ""),
            "warnings": list(provenance.get("warnings") or []),
            "historical_evidence": provenance.get("historical_evidence", "unverified"),
            "ephemeral": False, "safety": SAFETY_DECLARATION}


def _settle(record: dict[str, Any], next_index: int) -> None:
    training = record["training"]
    for order in training["orders"]:
        if order["status"] != "pending" or order["submitted_index"] + 1 > next_index:
            continue
        index = order["submitted_index"] + 1
        price = _number(record["bars"][index]["open"], "price")
        quantity = _number(order["quantity"], "quantity")
        signed = quantity if order["side"] == "BUY" else -quantity
        cash = _number(training["cash"], "cash") - signed * price
        position = _number(training["position"], "position") + signed
        # Unleveraged paper model. Short exposure is capped by initial capital.
        if cash < 0 or abs(min(position, Decimal(0)) * price) > _number(training["initial_cash"], "initial_cash"):
            order.update(status="rejected", reason="simulation_buying_power")
            continue
        training.update(cash=float(cash), position=float(position))
        order["status"] = "filled"
        training["fills"].append({"order_id": order["order_id"], "index": index,
                                  "time": record["bars"][index]["open_time"],
                                  "side": order["side"], "quantity": float(quantity),
                                  "price": float(price), "simulated_only": True})


def apply_action(record: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(record))
    action = str(payload.get("action") or "")
    current = int(result["index"])
    if action == "simulate":
        if result["mode"] != "training":
            raise ValueError("simulated requests require training mode")
        if current >= len(result["bars"]) - 1:
            raise ValueError("end of series; no next bar available")
        side = str(payload.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        quantity = _number(payload.get("quantity"), "quantity", positive=True)
        result["training"]["orders"].append({"order_id": "SIM-" + uuid4().hex,
                                              "submitted_index": current, "side": side,
                                              "quantity": float(quantity), "status": "pending"})
        return result
    if action not in ("step", "seek", "rewind"):
        raise ValueError("unknown replay action")
    raw_index = payload.get("index", current + 1 if action == "step" else None)
    if isinstance(raw_index, bool) or not isinstance(raw_index, int):
        raise ValueError("index must be an integer")
    index = raw_index
    if not 0 <= index < len(result["bars"]):
        raise ValueError("index outside replay series")
    if result["mode"] == "training" and index < current:
        # An experiment after a rewind cannot be confused with its predecessor.
        result["parent_session_id"] = result["session_id"]
        result["session_id"] = "RPL-" + uuid4().hex
        training = result["training"]
        training["branch_id"] = result["session_id"]
        training["fills"] = [f for f in training["fills"] if f["index"] <= index]
        retained = {f["order_id"] for f in training["fills"]}
        training["orders"] = [o for o in training["orders"] if o["order_id"] in retained]
        cash, position = _number(training["initial_cash"], "initial_cash"), Decimal(0)
        for fill in training["fills"]:
            qty = _number(fill["quantity"], "quantity") * (1 if fill["side"] == "BUY" else -1)
            cash -= qty * _number(fill["price"], "price")
            position += qty
        training.update(cash=float(cash), position=float(position))
    elif result["mode"] == "training":
        _settle(result, index)
    result["index"] = index
    return result
