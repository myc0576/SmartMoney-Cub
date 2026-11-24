"""Tests for the SmartMoney-Cub Hermes plugin."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import schemas  # noqa: E402
import tools  # noqa: E402


def _write_stub(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture()
def stub_ctx(tmp_path: Path):
    """A stub CLI that echoes its argv back as JSON."""
    script = "#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps({\"argv\": sys.argv[1:]}))\n"
    stub = _write_stub(tmp_path, "smcub", script)
    root = tmp_path / "root"
    root.mkdir()
    return {
        "smcub_command": str(stub),
        "timeout_seconds": 30,
        "run_root": str(root),
        "root": root,
    }


def _run_dir(ctx: dict, name: str = "run") -> Path:
    path = ctx["root"] / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _rule(ctx: dict, name: str = "rule.json") -> Path:
    path = ctx["root"] / name
    path.write_text("{}", encoding="utf-8")
    return path


def _payload(output: str) -> dict:
    return json.loads(output)


def test_every_schema_has_a_handler():
    names = {schema["name"] for schema in schemas.ALL_SCHEMAS}
    for name in names:
        assert hasattr(tools, name), f"missing handler for {name}"


def test_manifest_schema_and_handlers_are_aligned():
    manifest = yaml.safe_load((Path(__file__).parents[1] / "plugin.yaml").read_text())
    names = {schema["name"] for schema in schemas.ALL_SCHEMAS}
    assert manifest["version"] == "0.2.0"
    assert manifest["safety"] == tools.SAFETY
    assert manifest["network_required"] is False
    assert manifest["credential_requirements"] == []
    assert manifest["reviewed_snapshot"]["commit"] == "74279466a019d0ff3ccd1615ff660e224fa644d5"
    assert manifest["required_core_protocol"] == {
        "schema": "cli.capabilities.v1",
        "protocol_version": 1,
        "authority": "core_permission_store",
    }
    assert set(manifest["provides_tools"]) == names
    assert manifest["config_schema"]["run_root"]["default"] == ""
    assert manifest["config_schema"]["run_root"]["description"]
    build = next(schema for schema in schemas.ALL_SCHEMAS if schema["name"] == "smcub_build_evidence_pack")
    assert set(build["parameters"]["required"]) == {"run_dir", "output_dir", "rule_candidate"}
    assert build["parameters"]["properties"]["horizon"]["enum"] == ["d1", "d3"]


def test_doctor_does_not_require_run_root(stub_ctx):
    config = {key: value for key, value in stub_ctx.items() if key != "root"}
    config["run_root"] = ""
    payload = _payload(tools.smcub_doctor({}, config=config))
    assert payload["status"] == "ok"
    assert payload["result"]["argv"] == ["doctor"]
    assert payload["safety"] == tools.SAFETY


def test_missing_path_returns_error_not_raise(stub_ctx):
    missing = stub_ctx["root"] / "nope.json"
    payload = _payload(tools.smcub_validate_envelope({"envelope_path": str(missing)}, config=stub_ctx))
    assert payload["status"] == "error"
    assert "does not exist" in payload["error"]


def test_missing_argument_returns_error(stub_ctx):
    payload = _payload(tools.smcub_validate_envelope({}, config=stub_ctx))
    assert payload["status"] == "error"


def test_shell_metacharacters_and_separator_are_literal(stub_ctx):
    marker = stub_ctx["root"] / "owned_by_injection"
    hostile = stub_ctx["root"] / ("env.json; touch " + marker.name)
    hostile.write_text("{}", encoding="utf-8")
    payload = _payload(tools.smcub_validate_envelope({"envelope_path": str(hostile)}, config=stub_ctx))
    assert not marker.exists(), "argument was interpreted by a shell"
    assert payload["result"]["argv"] == ["validate-envelope", "--", str(hostile.resolve())]


def test_evaluate_run_passes_horizon_before_separator(stub_ctx):
    run_dir = _run_dir(stub_ctx)
    payload = _payload(tools.smcub_evaluate_run({"run_dir": str(run_dir), "horizon": "d3"}, config=stub_ctx))
    assert payload["result"]["argv"] == ["evaluate-run", "--horizon", "d3", "--", str(run_dir.resolve())]


def test_evaluate_default_horizon_and_invalid_value(stub_ctx, monkeypatch):
    run_dir = _run_dir(stub_ctx)
    payload = _payload(tools.smcub_evaluate_run({"run_dir": str(run_dir)}, config=stub_ctx))
    assert payload["result"]["argv"][1:3] == ["--horizon", "d1"]

    called = False
    def fail_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess must not start for an invalid horizon")
    monkeypatch.setattr(tools, "_run", fail_run)
    invalid = _payload(tools.smcub_evaluate_run({"run_dir": str(run_dir), "horizon": "m5"}, config=stub_ctx))
    assert invalid["status"] == "error"
    assert "d1, d3" in invalid["error"]
    assert not called


def test_build_evidence_pack_uses_current_cli_contract(stub_ctx):
    run_dir = _run_dir(stub_ctx)
    rule = _rule(stub_ctx)
    output = stub_ctx["root"] / "packs" / "new-pack"
    payload = _payload(tools.smcub_build_evidence_pack({
        "run_dir": str(run_dir),
        "output_dir": str(output),
        "rule_candidate": str(rule),
        "horizon": "d1",
    }, config=stub_ctx))
    assert payload["result"]["argv"] == [
        "build-evidence-pack",
        f"--sample={run_dir.resolve()}",
        f"--rule-candidate={rule.resolve()}",
        "--horizon=d1",
        "--",
        str(output.resolve()),
    ]


def test_build_requires_rule_candidate_and_valid_horizon(stub_ctx):
    run_dir = _run_dir(stub_ctx)
    output = stub_ctx["root"] / "pack"
    missing = _payload(tools.smcub_build_evidence_pack({"run_dir": str(run_dir), "output_dir": str(output)}, config=stub_ctx))
    assert missing["status"] == "error"
    assert "rule_candidate" in missing["error"]

    invalid = _payload(tools.smcub_build_evidence_pack({
        "run_dir": str(run_dir),
        "output_dir": str(output),
        "rule_candidate": str(_rule(stub_ctx)),
        "horizon": "m5",
    }, config=stub_ctx))
    assert invalid["status"] == "error"
    assert "d1, d3" in invalid["error"]


def test_path_sensitive_tools_fail_closed_without_root(stub_ctx):
    run_dir = _run_dir(stub_ctx)
    config = dict(stub_ctx)
    config["run_root"] = ""
    payload = _payload(tools.smcub_inspect_artifacts({"run_dir": str(run_dir)}, config=config))
    assert payload["status"] == "error"
    assert "run_root" in payload["error"]


def test_inputs_outside_root_are_rejected(stub_ctx, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    envelope = outside / "run_envelope.json"
    envelope.write_text("{}", encoding="utf-8")
    payload = _payload(tools.smcub_validate_envelope({"envelope_path": str(envelope)}, config=stub_ctx))
    assert payload["status"] == "error"
    assert "outside" in payload["error"]


def test_symlink_escape_is_rejected(stub_ctx, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "run"
    target.mkdir()
    link = stub_ctx["root"] / "link-run"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    payload = _payload(tools.smcub_inspect_artifacts({"run_dir": str(link)}, config=stub_ctx))
    assert payload["status"] == "error"
    assert "outside" in payload["error"]


def test_output_directory_must_stay_inside_root(stub_ctx, tmp_path):
    run_dir = _run_dir(stub_ctx)
    rule = _rule(stub_ctx)
    outside = tmp_path / "outside-pack"
    payload = _payload(tools.smcub_build_evidence_pack({
        "run_dir": str(run_dir),
        "output_dir": str(outside),
        "rule_candidate": str(rule),
        "horizon": "d1",
    }, config=stub_ctx))
    assert payload["status"] == "error"
    assert "outside" in payload["error"]


def test_output_file_cannot_replace_directory(stub_ctx):
    run_dir = _run_dir(stub_ctx)
    rule = _rule(stub_ctx)
    output = stub_ctx["root"] / "output-file"
    output.write_text("not a directory", encoding="utf-8")
    payload = _payload(tools.smcub_build_evidence_pack({
        "run_dir": str(run_dir),
        "output_dir": str(output),
        "rule_candidate": str(rule),
        "horizon": "d1",
    }, config=stub_ctx))
    assert payload["status"] == "error"
    assert "not a directory" in payload["error"]


def test_leading_dash_paths_are_after_separator(stub_ctx):
    run_dir = _run_dir(stub_ctx, "-run")
    rule = _rule(stub_ctx, "-rule.json")
    output = stub_ctx["root"] / "-pack"
    payload = _payload(tools.smcub_build_evidence_pack({
        "run_dir": str(run_dir),
        "output_dir": str(output),
        "rule_candidate": str(rule),
        "horizon": "d3",
    }, config=stub_ctx))
    argv = payload["result"]["argv"]
    assert argv[0] == "build-evidence-pack"
    assert argv[1].startswith("--sample=/")
    assert argv[-2:] == ["--", str(output.resolve())]


def test_missing_cli_is_reported_not_raised():
    payload = _payload(tools.smcub_doctor({}, config={"smcub_command": "/nonexistent/smcub", "timeout_seconds": 5}))
    assert payload["status"] in {"error", "failed"}


def test_handler_never_raises_on_bad_types(stub_ctx):
    for handler in (
        tools.smcub_validate_envelope,
        tools.smcub_replay_evidence_pack,
        tools.smcub_evaluate_run,
        tools.smcub_inspect_artifacts,
        tools.smcub_build_evidence_pack,
    ):
        output = handler({"run_dir": None, "envelope_path": None, "pack_dir": None}, config=stub_ctx)
        json.loads(output)


def test_safety_declaration_is_preserved(stub_ctx):
    output = tools.smcub_doctor({}, config={"smcub_command": stub_ctx["smcub_command"], "run_root": ""})
    assert tools.SAFETY in output
    output = tools.smcub_inspect_artifacts({"run_dir": str(stub_ctx["root"])}, config=stub_ctx)
    assert tools.SAFETY in output
