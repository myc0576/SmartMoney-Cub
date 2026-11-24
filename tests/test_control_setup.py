from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from smartmoney_cub_harness import cli
from smartmoney_cub_harness.control_exports import render_result
from smartmoney_cub_harness.control_setup import configure, setup_info
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_provider_setup_uses_plural_alias_and_never_returns_key(tmp_path: Path) -> None:
    result = setup_info("providers", "alphatech", tmp_path)
    assert result["status"] == "not_configured"
    assert result["required_fields"][0]["secret"] is True
    assert result["provider"]["has_key"] is False
    assert "toy-secret-value" not in str(result)
    assert result["safety"] == SAFETY_DECLARATION


def test_provider_setup_reports_configured_unverified_without_secret_value(tmp_path: Path) -> None:
    from smartmoney_cub_harness.agent.providers import install_provider

    install_provider(tmp_path, "deepseek", from_catalog=True, api_key="toy-secret-value")
    result = setup_info("provider", "deepseek", tmp_path)
    assert result["status"] == "configured_unverified"
    assert "toy-secret-value" not in str(result)


def test_connection_setup_reuses_manifest_and_https_links(tmp_path: Path) -> None:
    result = setup_info("connections", "ibkr-flex", tmp_path)
    assert result["status"] == "not_configured"
    assert {field["name"] for field in result["required_fields"]} == {"flex_token", "query_id"}
    assert all(link["url"].startswith("https://") for link in result["official_links"])


def test_missing_or_unknown_identifier_returns_actionable_directory(tmp_path: Path) -> None:
    missing = setup_info("plugins", "", tmp_path)
    unknown = setup_info("plugins", "does-not-exist", tmp_path)
    assert missing["status"] == "action_required"
    assert unknown["status"] == "unknown_identifier"
    assert "available_identifiers" in unknown


def test_plugin_companion_is_not_claimed_callable(tmp_path: Path) -> None:
    result = setup_info("plugin", "qlib-factor-evaluator", tmp_path)
    assert result["installed"] is False
    assert result["active"] is False
    assert result["callable"] is False
    assert result["callable_reason"] == "not_installed"


def test_existing_market_bars_and_equity_curve_render_as_charts() -> None:
    bars = {"bars": [{"open_time": "2026-01-01", "close": 10}, {"open_time": "2026-01-02", "close": 11}]}
    backtest = {"equity_curve": [{"open_time": "2026-01-01", "equity": 100}, {"open_time": "2026-01-02", "equity": 102}]}
    assert "<polyline" in render_result(bars)
    assert "<polyline" in render_result(backtest)


def test_csv_escapes_formula_cells_and_renders_nested_metrics() -> None:
    rendered = render_result({"status": "=SUM(A1:A2)", "summary": {"win_rate": 50, "equity_curve": [{"exit_time": "d1", "cumulative_pnl": 3}] }}, "csv")
    assert "'=SUM(A1:A2)" in rendered
    assert "win_rate" in rendered
    assert "d1" in rendered


def test_configure_provider_delegates_and_redacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called = {}

    def fake_install(root, identifier, **kwargs):
        called.update(root=root, identifier=identifier, kwargs=kwargs)
        return {"status": "ok", "api_key": "toy-secret-value", "safety": SAFETY_DECLARATION}

    monkeypatch.setattr("smartmoney_cub_harness.control_setup.install_provider", fake_install)
    result = configure("providers", "deepseek", tmp_path, {"api_key": "toy-secret-value", "from_catalog": True})
    assert called["identifier"] == "deepseek"
    assert result["api_key"] == "[REDACTED]"
    assert "toy-secret-value" not in str(result)


def test_render_html_escapes_values_and_includes_chart() -> None:
    rendered = render_result({"title": "<script>alert(1)</script>", "timeseries": [{"time": "a", "value": 1}, {"time": "b", "value": 2}]})
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<svg" in rendered
    assert "polyline" in rendered


def test_render_csv_has_scalar_and_series_rows() -> None:
    rendered = render_result({"status": "ok", "curve": [{"x": 0, "y": 1.5}, {"x": 1, "y": 2.5}]}, "csv")
    rows = list(csv.reader(io.StringIO(rendered)))
    assert ["field", "value"] in rows
    assert ["label", "value"] in rows
    assert ["0", "1.5"] in rows


def test_render_data_series_without_writing_files(tmp_path: Path) -> None:
    before = sorted(path.name for path in tmp_path.iterdir())
    rendered = render_result({"data": [["a", 1], ["b", 2]]})
    assert "<svg" in rendered
    assert sorted(path.name for path in tmp_path.iterdir()) == before


def test_render_rejects_unknown_format_and_redacts_credentials() -> None:
    with pytest.raises(ValueError):
        render_result({"status": "ok"}, "json")
    rendered = render_result({"access_token": "secret", "status": "ok"}, "csv")
    assert "secret" not in rendered


def test_cli_doctor_keeps_credentials_optional(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["doctor"]) == 0
    output = capsys.readouterr().out
    assert '"credentials_required": false' in output
    assert SAFETY_DECLARATION in output
