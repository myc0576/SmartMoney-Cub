from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from smartmoney_cub_harness.plugin_cli import (
    plugin_disable,
    plugin_doctor,
    plugin_enable,
    plugin_inspect,
    plugin_list,
    plugin_run,
)
from smartmoney_cub_harness.plugins import PluginRuntime, PluginState, PluginStateStore
from smartmoney_cub_harness.plugins.manifest import parse_manifest
from smartmoney_cub_harness.plugins.profiles import get_profile
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

NUMERICAL_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "examples" / "numerical_plugin"
NUMERICAL_MANIFEST = NUMERICAL_PLUGIN_DIR / "plugin.json"
MARKOV_REQUEST = NUMERICAL_PLUGIN_DIR / "markov_request.json"
INVERSE_REQUEST = NUMERICAL_PLUGIN_DIR / "inverse_request.json"

DECISION_TIME = "2026-10-31T15:00:00+08:00"
AVAILABLE_AT = "2026-10-31T14:30:00+08:00"


def _state_db(tmp_path: Path) -> str:
    return str(tmp_path / "test_numerical_state.db")


def test_numerical_plugin_manifest_is_valid_and_declares_review_only() -> None:
    result = plugin_inspect(str(NUMERICAL_MANIFEST))
    assert result["status"] == "ok"
    manifest = result["manifest"]
    assert manifest["plugin_id"] == "research.numerical"
    assert manifest["kind"] == "subprocess"
    assert manifest["trust_level"] == "review-only"
    assert manifest["capabilities"] == ["numerical_analysis"]
    assert manifest["network_required"] is False
    assert manifest["credential_requirements"] == []
    assert manifest["safety"] == SAFETY_DECLARATION
    assert result["safety"] == SAFETY_DECLARATION
    assert "no_source_commit_or_tag_recorded" in result["validation"]["warnings"]


def test_numerical_plugin_is_discovered_and_activated_via_doctor(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    listing = plugin_list(plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)], state_db=db)
    assert listing["status"] == "ok"
    assert any(item["plugin_id"] == "research.numerical" for item in listing["plugins"])

    doctor = plugin_doctor(plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)], state_db=db)
    assert doctor["status"] == "ok"
    plugin_entry = next(
        item for item in doctor["plugins"] if item["plugin_id"] == "research.numerical"
    )
    assert plugin_entry["state"] == "ACTIVE"
    assert plugin_entry["capabilities"] == ["numerical_analysis"]
    assert plugin_entry["health"]["status"] == "ok"
    assert plugin_entry["health"]["capability"] == "numerical_analysis"


def test_plugin_run_markov_propagation_real_subprocess(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    result = plugin_run(
        "research.numerical",
        capability="numerical_analysis",
        request_path=str(MARKOV_REQUEST),
        decision_time=DECISION_TIME,
        available_at=AVAILABLE_AT,
        data_source="toy_state_model",
        result_kind="statistical_result",
        plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)],
        state_db=db,
    )
    assert result["status"] == "ok"
    envelope = result["envelope"]
    assert envelope["plugin_id"] == "research.numerical"
    assert envelope["capability"] == "numerical_analysis"
    assert envelope["result_kind"] == "statistical_result"
    assert envelope["isolation"] == "subprocess"
    assert envelope["network_used"] is False
    assert envelope["champion_mutated"] is False
    assert envelope["core_rules_mutated"] is False
    assert envelope["safety"] == SAFETY_DECLARATION
    assert len(envelope["input_sha256"]) == 64
    assert len(envelope["output_sha256"]) == 64

    output = envelope["output"]
    assert output["status"] == "ok"
    assert output["operation"] == "markov_propagate"
    assert output["safety"] == SAFETY_DECLARATION
    assert output["result_kind"] == "statistical_result"
    assert len(output["distribution"]) == 2
    assert abs(sum(output["distribution"]) - 1.0) < 1e-9
    assert output["diagnostics"]["steps"] == 5
    assert output["diagnostics"]["dimension"] == 2
    assert output["diagnostics"]["labeled_distribution"]["stable"] == pytest.approx(
        output["distribution"][0]
    )
    assert output["assumptions"]
    assert output["limitations"]


def test_plugin_run_inverse_linear_real_subprocess(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    result = plugin_run(
        "research.numerical",
        capability="numerical_analysis",
        request_path=str(INVERSE_REQUEST),
        decision_time=DECISION_TIME,
        available_at=AVAILABLE_AT,
        data_source="toy_linear_model",
        result_kind="statistical_result",
        plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)],
        state_db=db,
    )
    assert result["status"] == "ok"
    envelope = result["envelope"]
    assert envelope["plugin_id"] == "research.numerical"
    assert envelope["capability"] == "numerical_analysis"
    assert envelope["result_kind"] == "statistical_result"
    assert envelope["isolation"] == "subprocess"
    assert envelope["safety"] == SAFETY_DECLARATION
    assert len(envelope["input_sha256"]) == 64
    assert len(envelope["output_sha256"]) == 64

    output = envelope["output"]
    assert output["status"] == "ok"
    assert output["operation"] == "inverse_linear"
    assert output["safety"] == SAFETY_DECLARATION
    assert len(output["estimates"]) == 2
    assert output["estimates"][0] == pytest.approx(1.0, rel=1e-2)
    assert output["estimates"][1] == pytest.approx(1.0, rel=1e-2)
    assert output["diagnostics"]["rank"] == 2
    assert output["diagnostics"]["convergence"] is True
    assert output["assumptions"]
    assert output["limitations"]


def test_future_data_leakage_is_rejected(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    leak = plugin_run(
        "research.numerical",
        capability="numerical_analysis",
        request_path=str(MARKOV_REQUEST),
        decision_time=DECISION_TIME,
        available_at="2026-10-31T16:00:00+08:00",  # After decision_time
        data_source="toy_state_model",
        result_kind="statistical_result",
        plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)],
        state_db=db,
    )
    assert leak["status"] == "error"
    assert leak["error"]["code"] == "EvidenceEnvelopeError"
    assert "future leakage" in leak["error"]["message"]


def test_missing_provenance_timestamps_refused(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    res_no_avail = plugin_run(
        "research.numerical",
        capability="numerical_analysis",
        request_path=str(MARKOV_REQUEST),
        decision_time=DECISION_TIME,
        available_at=None,
        plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)],
        state_db=db,
    )
    assert res_no_avail["status"] == "error"
    assert res_no_avail["error"]["code"] == "available_at_required"

    res_no_dec = plugin_run(
        "research.numerical",
        capability="numerical_analysis",
        request_path=str(MARKOV_REQUEST),
        decision_time=None,
        available_at=AVAILABLE_AT,
        plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)],
        state_db=db,
    )
    assert res_no_dec["status"] == "error"
    assert res_no_dec["error"]["code"] == "decision_time_required"


def test_disabled_plugin_refuses_to_run_until_reenabled(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    plugin_doctor(plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)], state_db=db)

    disabled = plugin_disable("research.numerical", state_db=db)
    assert disabled["status"] == "ok"
    assert disabled["plugin"]["state"] == PluginState.DISABLED

    refused = plugin_run(
        "research.numerical",
        capability="numerical_analysis",
        request_path=str(MARKOV_REQUEST),
        decision_time=DECISION_TIME,
        available_at=AVAILABLE_AT,
        state_db=db,
    )
    assert refused["status"] == "not_enabled"
    assert refused["error"]["code"] == "plugin_not_enabled"

    enabled = plugin_enable(
        "research.numerical", plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)], state_db=db
    )
    assert enabled["status"] == "ok"
    assert enabled["plugin"]["state"] == PluginState.ACTIVE


def test_unsupported_operation_records_failure_in_envelope(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    req = tmp_path / "bad_op.json"
    req.write_text(json.dumps({"operation": "arbitrary_calc", "data": [1, 2]}), encoding="utf-8")

    result = plugin_run(
        "research.numerical",
        capability="numerical_analysis",
        request_path=str(req),
        decision_time=DECISION_TIME,
        available_at=AVAILABLE_AT,
        plugin_dirs=[str(NUMERICAL_PLUGIN_DIR)],
        state_db=db,
    )
    assert result["status"] == "failed"
    envelope = result["envelope"]
    assert envelope["error"] is not None
    assert "unsupported_operation" in envelope["error"]
    assert envelope["output"] is None
    assert envelope["output_sha256"] is None
    assert envelope["safety"] == SAFETY_DECLARATION


def test_malformed_json_records_failure_in_envelope_and_provider() -> None:
    # 1. Provider subprocess directly rejects malformed JSON
    completed = subprocess.run(
        ["python3", "-m", "smartmoney_cub_harness.numerical.provider"],
        input="not json at all",
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 2
    err_payload = json.loads(completed.stderr.strip())
    assert err_payload["status"] == "error"
    assert err_payload["error_code"] == "json_decode_error"
    assert err_payload["safety"] == SAFETY_DECLARATION


def test_strict_json_rejection_of_nan_constants() -> None:
    from smartmoney_cub_harness.numerical.provider import main

    nan_json = '{"operation": "markov_propagate", "value": NaN}'
    captured_stderr: list[str] = []

    def mock_write(s: str) -> int:
        captured_stderr.append(s)
        return len(s)

    with patch("sys.stdin.buffer.read", return_value=nan_json.encode("utf-8")):
        with patch("sys.stderr.write", side_effect=mock_write):
            exit_code = main([])

    assert exit_code == 2
    err_text = "".join(captured_stderr)
    parsed = json.loads(err_text.strip())
    assert parsed["status"] == "error"
    assert parsed["error_code"] == "json_decode_error"
    assert "disallowed JSON constant: NaN" in parsed["message"]
    assert parsed["safety"] == SAFETY_DECLARATION


def test_strict_json_rejection_of_duplicate_keys() -> None:
    from smartmoney_cub_harness.numerical.provider import main

    dup_json = '{"operation": "markov_propagate", "operation": "inverse_linear"}'
    captured_stderr: list[str] = []

    def mock_write(s: str) -> int:
        captured_stderr.append(s)
        return len(s)

    with patch("sys.stdin.buffer.read", return_value=dup_json.encode("utf-8")):
        with patch("sys.stderr.write", side_effect=mock_write):
            exit_code = main([])

    assert exit_code == 2
    err_text = "".join(captured_stderr)
    parsed = json.loads(err_text.strip())
    assert parsed["status"] == "error"
    assert parsed["error_code"] == "json_decode_error"
    assert "duplicate key in JSON object" in parsed["message"]
    assert parsed["safety"] == SAFETY_DECLARATION


def test_oversized_input_rejection() -> None:
    from smartmoney_cub_harness.numerical.provider import MAX_INPUT_BYTES, main

    oversized_bytes = b" " * (MAX_INPUT_BYTES + 10)
    captured_stderr: list[str] = []

    def mock_write(s: str) -> int:
        captured_stderr.append(s)
        return len(s)

    with patch("sys.stdin.buffer.read", return_value=oversized_bytes):
        with patch("sys.stderr.write", side_effect=mock_write):
            exit_code = main([])

    assert exit_code == 2
    err_text = "".join(captured_stderr)
    parsed = json.loads(err_text.strip())
    assert parsed["status"] == "error"
    assert parsed["error_code"] == "input_too_large"
    assert parsed["safety"] == SAFETY_DECLARATION


def test_provider_rejects_unrecognized_cli_arguments() -> None:
    from smartmoney_cub_harness.numerical.provider import main

    captured_stderr: list[str] = []

    def mock_write(s: str) -> int:
        captured_stderr.append(s)
        return len(s)

    with patch("sys.stderr.write", side_effect=mock_write):
        exit_code = main(["--unrecognized", "arg"])

    assert exit_code == 2
    err_text = "".join(captured_stderr)
    parsed = json.loads(err_text.strip())
    assert parsed["status"] == "error"
    assert parsed["error_code"] == "invalid_arguments"
    assert parsed["safety"] == SAFETY_DECLARATION


def test_provider_help_flag_displays_usage_and_safety() -> None:
    from smartmoney_cub_harness.numerical.provider import main

    captured_stdout: list[str] = []

    def mock_write(s: str) -> int:
        captured_stdout.append(s)
        return len(s)

    with patch("sys.stdout.write", side_effect=mock_write):
        exit_code = main(["--help"])

    assert exit_code == 0
    help_text = "".join(captured_stdout)
    assert "Numerical analysis subprocess provider" in help_text
    assert SAFETY_DECLARATION in help_text


def test_missing_scipy_dependency_surfaces_actionable_error(tmp_path: Path) -> None:
    """When SciPy is missing, inverse solver raises actionable error preserved in envelope."""
    db = _state_db(tmp_path)
    plugin_dir = tmp_path / "simulated_missing_scipy"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest_payload = json.loads(NUMERICAL_MANIFEST.read_text(encoding="utf-8"))
    manifest_payload["plugin_id"] = "test.missing-scipy"
    manifest_payload["entrypoint"] = [
        sys.executable,
        "-c",
        (
            "import sys; "
            "sys.modules['scipy'] = None; "
            "sys.modules['scipy.optimize'] = None; "
            "from smartmoney_cub_harness.numerical.provider import main; "
            "sys.exit(main())"
        ),
    ]
    manifest_file = plugin_dir / "plugin.json"
    manifest_file.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    result = plugin_run(
        "test.missing-scipy",
        capability="numerical_analysis",
        request_path=str(INVERSE_REQUEST),
        decision_time=DECISION_TIME,
        available_at=AVAILABLE_AT,
        plugin_dirs=[str(plugin_dir)],
        state_db=db,
    )

    assert result["status"] == "failed"
    envelope = result["envelope"]
    assert envelope["error"] is not None
    assert "smartmoney-cub-harness[numerical]" in envelope["error"]
    assert "SciPy and NumPy are required" in envelope["error"]
    assert envelope["output"] is None
    assert envelope["output_sha256"] is None
    assert envelope["safety"] == SAFETY_DECLARATION


def test_surrogate_and_unicode_labels_roundtrip_safely() -> None:
    """Ensure labels with unpaired surrogates (chr(0xD800)) serialize via ensure_ascii=True without stdout crash."""
    from smartmoney_cub_harness.numerical.provider import main

    # json.dumps default escapes unpaired surrogates into ASCII "\ud800"
    raw_ascii_input = json.dumps({
        "operation": "markov_propagate",
        "transition_matrix": [[1.0]],
        "initial_distribution": [1.0],
        "steps": 1,
        "state_labels": [f"state_{chr(0xD800)}"],
    })

    captured_stdout: list[str] = []

    def mock_write(s: str) -> int:
        captured_stdout.append(s)
        return len(s)

    with patch("sys.stdin.buffer.read", return_value=raw_ascii_input.encode("utf-8")):
        with patch("sys.stdout.write", side_effect=mock_write):
            exit_code = main([])

    assert exit_code == 0
    raw_out = "".join(captured_stdout)
    # Output must be pure ASCII (due to ensure_ascii=True) and round-trip to UTF-8 bytes cleanly
    raw_out.encode("utf-8")
    parsed = json.loads(raw_out)
    assert parsed["status"] == "ok"
    assert parsed["diagnostics"]["state_labels"][0] == f"state_{chr(0xD800)}"


def test_invalid_utf8_input_rejection() -> None:
    from smartmoney_cub_harness.numerical.provider import main

    invalid_utf8_bytes = b"\x80\x81\xff\xfe"
    captured_stderr: list[str] = []

    def mock_write(s: str) -> int:
        captured_stderr.append(s)
        return len(s)

    with patch("sys.stdin.buffer.read", return_value=invalid_utf8_bytes):
        with patch("sys.stderr.write", side_effect=mock_write):
            exit_code = main([])

    assert exit_code == 2
    err_text = "".join(captured_stderr)
    parsed = json.loads(err_text.strip())
    assert parsed["status"] == "error"
    assert parsed["error_code"] == "encoding_error"
    assert parsed["safety"] == SAFETY_DECLARATION


