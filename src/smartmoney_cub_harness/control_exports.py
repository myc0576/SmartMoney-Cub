"""Dependency-free renderers for control results."""

from __future__ import annotations

import csv
import html
import io
import math
from collections.abc import Mapping
from typing import Any


def _safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in value.items() if not any(word in str(k).lower() for word in ("key", "token", "secret", "password", "credential", "auth"))}
    if isinstance(value, list):
        return [_safe(v) for v in value]
    return value


def _series_source(result: Mapping[str, Any]) -> Any:
    """Select the result shapes emitted by market, analytics, and backtest APIs."""
    for key in ("timeseries", "curve", "series", "data", "bars", "equity_curve"):
        if result.get(key):
            return result[key]
    for parent in ("summary", "result", "backtest"):
        nested = result.get(parent)
        if isinstance(nested, Mapping):
            for key in ("equity_curve", "timeseries", "curve", "series", "data", "bars"):
                if nested.get(key):
                    return nested[key]
    return None


def _points(result: Mapping[str, Any]) -> list[tuple[str, float]]:
    raw = _series_source(result)
    if isinstance(raw, Mapping):
        raw = next(iter(raw.values()), [])
    points: list[tuple[str, float]] = []
    for item in raw or []:
        if isinstance(item, Mapping):
            label = item.get("time", item.get("open_time", item.get("exit_time", item.get("x", item.get("label", len(points))))))
            value = item.get("value", item.get("y", item.get("equity", item.get("cumulative_pnl", item.get("close")))))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            label, value = item[0], item[1]
        else:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            points.append((str(label), number))
    return points


def _svg(points: list[tuple[str, float]]) -> str:
    if not points:
        return ""
    width, height, pad = 520, 180, 20
    values = [value for _, value in points]
    low, high = min(values), max(values)
    span = high - low or 1.0
    coords = []
    for index, (_, value) in enumerate(points):
        x = pad + (width - 2 * pad) * index / max(len(points) - 1, 1)
        y = height - pad - (height - 2 * pad) * (value - low) / span
        coords.append(f"{x:.1f},{y:.1f}")
    return f'<svg class="result-chart" viewBox="0 0 {width} {height}" role="img" aria-label="Result chart"><polyline fill="none" stroke="#2563eb" stroke-width="2" points="{html.escape(" ".join(coords), quote=True)}" /></svg>'


def render_result(result: Mapping[str, Any], format: str = "html") -> str:
    if not isinstance(result, Mapping):
        raise TypeError("result must be a mapping")
    if format not in {"html", "csv"}:
        raise ValueError("format must be html or csv")
    clean = _safe(result)
    points = _points(clean)
    if format == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["field", "value"])
        for key, value in clean.items():
            if key in {"timeseries", "curve", "series", "data", "bars", "result", "backtest"} and _series_source({key: value}):
                continue
            writer.writerow([_csv_cell(key), _csv_cell(value if not isinstance(value, (dict, list)) else str(value))])
            if key == "summary" and isinstance(value, Mapping):
                for metric, metric_value in value.items():
                    if metric not in {"equity_curve", "timeseries", "curve", "series", "data", "bars"} and not isinstance(metric_value, (dict, list)):
                        writer.writerow([_csv_cell(metric), _csv_cell(metric_value)])
        if points:
            writer.writerow([])
            writer.writerow(["label", "value"])
            writer.writerows([[_csv_cell(label), _csv_cell(value)] for label, value in points])
        return output.getvalue()
    rows = "".join(f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>" for key, value in clean.items() if key not in {"timeseries", "curve", "series", "data", "bars", "summary", "result", "backtest"})
    nested = clean.get("summary") if isinstance(clean.get("summary"), Mapping) else clean.get("backtest") if isinstance(clean.get("backtest"), Mapping) else {}
    metrics = "".join(f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>" for key, value in nested.items() if key not in {"equity_curve", "timeseries", "curve", "series", "data", "bars"} and not isinstance(value, (dict, list)))
    table = rows + metrics
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Control result</title></head><body><section><table><tbody>{table}</tbody></table>{_svg(points)}</section></body></html>'''


def _csv_cell(value: Any) -> Any:
    text = str(value)
    if text[:1] in {"=", "+", "-", "@"}:
        return "'" + text
    return value
