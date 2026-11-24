"""Parity and boundary tests for the local Hermes plugin copy."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "integrations" / "hermes-smartmoney-cub"
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(PLUGIN_ROOT))

import tools  # noqa: E402
from smartmoney_cub_harness.run_envelope import build_run_envelope  # noqa: E402


def _write_executable(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _config(tmp_path: Path, script: str) -> dict[str, object]:
    root = tmp_path / "run-root"
    root.mkdir()
    state = tmp_path / "state-root"
    state.mkdir()
    command = _write_executable(tmp_path / "smcub", script)
    return {
        "smcub_command": str(command),
        "timeout_seconds": 10,
        "run_root": str(root),
        "state_dir": str(state),
        "root": root,
        "state": state,
    }


def _json(value: str) -> dict:
    return json.loads(value)


def _protocol_stub(*, operation_result: dict | None = None, capabilities: dict | None = None) -> str:
    payload = capabilities or {
        "schema": "cli.capabilities.v1",
        "protocol_version": 1,
        "operations": [
            {
                "name": "review.inspect",
                "description": "Read a toy review input",
                "permission": "read_review",
                "writes": [],
                "network": False,
                "database": "none",
                "cache": "none",
                "read_only": True,
            },
            {
                "name": "permissions.request",
                "description": "Propose a permission request",
                "permission": "request",
                "proposal_only": True,
                "approval_required": True,
                "writes": ["permission proposal in core state"],
                "network": False,
            },
        ],
    }
    encoded = json.dumps(payload)
    result = json.dumps(operation_result or {"status": "proposal", "proposal_only": True})
    return f"""#!/usr/bin/env python3
import json, sys
argv = sys.argv[1:]
if argv[:2] == ["capabilities", "--json"]:
    print({encoded!r})
    raise SystemExit(0)
if argv and argv[0] == "operation":
    operation_result = json.loads({result!r})
    operation_result.setdefault("argv", argv)
    print(json.dumps(operation_result))
    raise SystemExit(0)
print(json.dumps({{"argv": argv, "safety": {tools.SAFETY!r}}}))
"""


def _real_core_wrapper(tmp_path: Path) -> Path:
    return _write_executable(
        tmp_path / "smcub-real-core",
        f"""#!/usr/bin/env python3
import os, sys
os.environ['PYTHONPATH'] = {str(REPO_ROOT / 'src')!r} + os.pathsep + os.environ.get('PYTHONPATH', '')
os.execv({sys.executable!r}, [{sys.executable!r}, '-m', 'smartmoney_cub_harness.cli', *sys.argv[1:]])
""",
    )


def test_real_current_core_doctor_preserves_safety() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    completed = subprocess.run(
        [sys.executable, "-m", "smartmoney_cub_harness.cli", "doctor"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["safety"] == tools.SAFETY


def test_real_current_core_capabilities_are_live_and_fail_closed_for_old_protocol(tmp_path: Path) -> None:
    wrapper = _real_core_wrapper(tmp_path)
    result = _json(
        tools.smcub_capabilities(
            {},
            config={"smcub_command": str(wrapper)},
        )
    )
    if result["status"] != "ok":
        pytest.fail(result)
    assert result["result"]["schema"] == "cli.capabilities.v1"
    assert result["result"]["protocol_version"] == 1
    assert result["result"]["operations"]
    assert result["result"].get("status", "ok") == "ok"
    assert len(result["result"]["operations"]) >= 118
    live = {item["name"]: item for item in result["result"]["operations"]}
    for name in ("providers.add", "providers.update", "providers.remove", "settings.update", "settings.open"):
        assert live[name]["human_only"] is True
    assert result["safety"] == tools.SAFETY

    old_root = tmp_path / "old"
    old_root.mkdir()
    old = _config(old_root, _protocol_stub(capabilities={"schema": "cli.capabilities.v0", "protocol_version": 1, "operations": []}))
    mismatch = _json(tools.smcub_capabilities({}, config=old))
    assert mismatch["status"] == "error"
    assert mismatch["error_code"] == "capabilities_protocol_mismatch"


def test_real_current_core_validate_envelope_uses_legacy_argv(tmp_path: Path) -> None:
    wrapper = _real_core_wrapper(tmp_path)
    root = tmp_path / "run-root"
    root.mkdir()
    envelope_path = root / "run_envelope.json"
    envelope_path.write_text(
        json.dumps(
            build_run_envelope(
                run_id="toy-hermes",
                decision_time="2026-09-29T09:30:00+08:00",
                mode="after-close",
                commands=[],
                command_results=[],
            )
        ),
        encoding="utf-8",
    )
    result = _json(
        tools.smcub_validate_envelope(
            {"envelope_path": str(envelope_path)},
            config={"smcub_command": str(wrapper), "run_root": str(root)},
        )
    )
    assert result["status"] == "ok"
    assert result["result"]["valid"] is True
    assert result["result"]["safety"] == tools.SAFETY


@pytest.mark.parametrize("horizon", ["d1", "d3"])
def test_real_current_core_legacy_d1_d3_evaluate_build_replay(tmp_path: Path, horizon: str) -> None:
    wrapper = _real_core_wrapper(tmp_path)
    root = tmp_path / "run-root"
    root.mkdir()
    run_dir = root / f"toy-{horizon}"
    run_dir.mkdir()
    manifest = {
        "schema": "smartmoney_cub_run_manifest.v1",
        "run_id": f"toy-{horizon}",
        "decision_time": "2026-09-29T09:30:00+08:00",
        "mode": "offline",
        "data_sources": [{"name": "toy", "fetch_time": "2026-09-29T09:00:00+08:00", "available_at": "2026-09-29T09:00:00+08:00", "data_quality_flag": "ok"}],
        "safety": tools.SAFETY,
    }
    decision = {"action_label": "ALERT", "symbol": "TOY", "decision_time": manifest["decision_time"], "invalidation_price": 9.5, "time_stop": horizon, "give_up_conditions": ["pattern_failed"], "data_source": "toy", "available_at": "2026-09-29T09:00:00+08:00", "data_quality_flag": "ok", "safety": tools.SAFETY}
    outcome = {"schema": "smartmoney_cub_outcome.v1", "symbol": "TOY", "horizon": horizon, "decision_time": manifest["decision_time"], "decision_path": "decision.json", "entry_date": "20260929", "entry_close": 10.0, "exit_date": "20260930", "exit_close": 10.5, f"{horizon}_return_pct": 5.0, "max_adverse_excursion_pct": -1.0, "met_user_pattern": False, "price_source": "toy", "price_source_type": "json_fixture", "safety": tools.SAFETY}
    for name, payload in (("run_manifest.json", manifest), ("decision.json", decision), (f"outcome_{horizon}.json", outcome)):
        (run_dir / name).write_text(json.dumps(payload), encoding="utf-8")
    rule = root / "rule_candidate.json"
    rule.write_text(json.dumps({"rule_id": "toy-rule", "family": "toy"}), encoding="utf-8")
    config = {"smcub_command": str(wrapper), "run_root": str(root), "timeout_seconds": 30}

    evaluated = _json(tools.smcub_evaluate_run({"run_dir": str(run_dir), "horizon": horizon}, config=config))
    assert evaluated["status"] == "ok", evaluated
    assert (run_dir / "eval.json").is_file()
    output_dir = root / f"pack-{horizon}"
    built = _json(tools.smcub_build_evidence_pack({"run_dir": str(run_dir), "output_dir": str(output_dir), "rule_candidate": str(rule), "horizon": horizon}, config=config))
    assert built["status"] == "ok", built
    assert (output_dir / "evidence_pack.json").is_file()
    replayed = _json(tools.smcub_replay_evidence_pack({"pack_dir": str(output_dir)}, config=config))
    assert replayed["status"] == "ok", replayed
    assert (output_dir / "replay_report.json").is_file()
    assert any("replay_report.json" in item for item in replayed["disclosures"]["writes"])


def test_capabilities_accepts_only_exact_protocol_and_redacts_secrets(tmp_path: Path) -> None:
    capabilities = {
        "schema": "cli.capabilities.v1",
        "protocol_version": 1,
        "operations": [
            {
                "name": "review.inspect",
                "description": "api_key=toy-secret",
                "permission": "read_review",
                "network": False,
            }
        ],
    }
    config = _config(tmp_path, _protocol_stub(capabilities=capabilities))
    result = _json(tools.smcub_capabilities({}, config=config))
    assert result["status"] == "ok"
    assert result["result"]["schema"] == "cli.capabilities.v1"
    assert result["result"]["protocol_version"] == 1
    assert [item["name"] for item in result["result"]["operations"]] == ["review.inspect"]
    assert "toy-secret" not in json.dumps(result)


@pytest.mark.parametrize(
    "capabilities",
    [
        {"schema": "cli.capabilities.v1", "protocol_version": 2, "operations": []},
        {"schema": "cli.capabilities.v1", "protocol_version": 1, "operations": [{"name": "permissions.grant", "permission": "grant"}]},
        {"schema": "cli.capabilities.v1", "protocol_version": 1, "operations": [{"name": "review.place_order", "network": False}]},
        {"schema": "cli.capabilities.v1", "protocol_version": 1, "operations": [{"name": "trade.execute", "network": False}]},
        {"schema": "cli.capabilities.v1", "protocol_version": 1, "operations": [{"name": "cancel.order", "network": False}]},
    ],
)
def test_capabilities_mismatch_or_unsafe_authority_is_rejected(tmp_path: Path, capabilities: dict) -> None:
    config = _config(tmp_path, _protocol_stub(capabilities=capabilities))
    result = _json(tools.smcub_capabilities({}, config=config))
    if capabilities["protocol_version"] != 1:
        assert result["status"] == "error"
        assert result["error_code"] == "capabilities_protocol_mismatch"
    else:
        assert result["status"] == "ok"
        names = {item["name"] for item in result["result"]["operations"]}
        assert not names.intersection({capabilities["operations"][0]["name"]})


def test_capabilities_allow_network_account_and_scoped_sync_metadata(tmp_path: Path) -> None:
    capabilities = {
        "schema": "cli.capabilities.v1",
        "protocol_version": 1,
        "operations": [
            {"name": "market.public_bars", "network": True, "network_required": True, "market_data": True, "scope": "public"},
            {"name": "account.positions", "network": True, "account": True, "scope": "tenant_read_only"},
            {"name": "journal.scoped_sync", "network": True, "sync": True, "scope": "tenant_scoped"},
        ],
    }
    result = _json(tools.smcub_capabilities({}, config=_config(tmp_path, _protocol_stub(capabilities=capabilities))))
    assert result["status"] == "ok"
    operations = {item["name"]: item for item in result["result"]["operations"]}
    assert operations["market.public_bars"]["network"] is True
    assert operations["account.positions"]["account"] is True
    assert operations["journal.scoped_sync"]["scope"] == "tenant_scoped"


def test_human_only_secret_operation_is_cataloged_but_not_invokable(tmp_path: Path) -> None:
    capabilities = {
        "schema": "cli.capabilities.v1", "protocol_version": 1,
        "operations": [{"name": "credentials.rotate", "network": True, "human_only": True, "secret_input": True}],
    }
    config = _config(tmp_path, _protocol_stub(capabilities=capabilities))
    input_path = config["root"] / "input.json"
    input_path.write_text("{}", encoding="utf-8")
    result = _json(tools.smcub_operation({"operation": "credentials.rotate", "input_path": str(input_path)}, config=config))
    assert result["error_code"] == "human_only_operation"


def test_operation_checks_capabilities_then_passes_fixed_argv_and_roots(tmp_path: Path) -> None:
    config = _config(tmp_path, _protocol_stub(operation_result={"status": "ok", "safety": tools.SAFETY}))
    input_path = config["root"] / "input.json"
    input_path.write_text(json.dumps({"toy": True}), encoding="utf-8")
    result = _json(
        tools.smcub_operation(
            {"operation": "review.inspect", "input_path": str(input_path)},
            config=config,
        )
    )
    assert result["status"] == "ok"
    assert result["result"]["safety"] == tools.SAFETY
    assert result["result"]["argv"] == [
        "operation",
        "review.inspect",
        "--input",
        str(input_path.resolve()),
        "--principal",
        "hermes",
        "--state-dir",
        str(config["state"].resolve()),
        "--json",
        "--run-root",
        str(config["root"].resolve()),
    ]
    assert result["disclosures"]["network"] is False


def test_operation_forwards_opaque_approval_id_as_top_level_flag(tmp_path: Path) -> None:
    capabilities = {
        "schema": "cli.capabilities.v1", "protocol_version": 1,
        "operations": [{"name": "connections.sync", "network": True, "confirmation": True}],
    }
    config = _config(tmp_path, _protocol_stub(capabilities=capabilities, operation_result={"status": "ok", "safety": tools.SAFETY}))
    input_path = config["root"] / "input.json"
    input_path.write_text(json.dumps({"provider_id": "toy"}), encoding="utf-8")
    result = _json(tools.smcub_operation({"operation": "connections.sync", "input_path": str(input_path), "approval_id": "req-opaque-123"}, config=config))
    assert result["status"] == "ok"
    assert result["result"]["argv"][-2:] == ["--approval-id", "req-opaque-123"]
    assert "approval_id" not in json.dumps(result["result"])


def test_operation_rejects_non_opaque_approval_id(tmp_path: Path) -> None:
    config = _config(tmp_path, _protocol_stub())
    input_path = config["root"] / "input.json"
    input_path.write_text("{}", encoding="utf-8")
    result = _json(tools.smcub_operation({"operation": "review.inspect", "input_path": str(input_path), "approval_id": "request with spaces"}, config=config))
    assert result["error_code"] == "invalid_approval_id"


def test_operation_requires_human_state_dir_and_rejects_model_root_args(tmp_path: Path) -> None:
    config = _config(tmp_path, _protocol_stub())
    input_path = config["root"] / "input.json"
    input_path.write_text("{}", encoding="utf-8")
    missing_state = dict(config)
    missing_state["state_dir"] = ""
    result = _json(
        tools.smcub_operation(
            {
                "operation": "review.inspect",
                "input_path": str(input_path),
                "state_dir": str(tmp_path / "model-state"),
                "run_root": str(tmp_path / "model-run"),
            },
            config=missing_state,
        )
    )
    assert result["status"] == "error"
    assert "state_dir" in result["error"]


def test_permissions_request_is_proposal_only_and_cannot_return_grant(tmp_path: Path) -> None:
    config = _config(tmp_path, _protocol_stub(operation_result={"status": "proposal", "proposal_only": True}))
    input_path = config["root"] / "request.json"
    input_path.write_text("{}", encoding="utf-8")
    result = _json(
        tools.smcub_operation(
            {"operation": "permissions.request", "input_path": str(input_path)},
            config=config,
        )
    )
    assert result["proposal_only"] is True
    assert result["approval_authority"] == "human_or_core_permission_store"


def test_permission_grant_result_is_rejected_even_from_stub(tmp_path: Path) -> None:
    config = _config(tmp_path, _protocol_stub(operation_result={"status": "approved", "approval_granted": True}))
    input_path = config["root"] / "request.json"
    input_path.write_text("{}", encoding="utf-8")
    result = _json(
        tools.smcub_operation(
            {"operation": "permissions.request", "input_path": str(input_path)},
            config=config,
        )
    )
    assert result["status"] == "error"
    assert result["error_code"] == "approval_grant_rejected"


def test_legacy_tools_preserve_separator_and_disclose_replay_write(tmp_path: Path) -> None:
    config = _config(tmp_path, _protocol_stub())
    pack_dir = config["root"] / "-pack"
    pack_dir.mkdir()
    result = _json(tools.smcub_replay_evidence_pack({"pack_dir": str(pack_dir)}, config=config))
    assert result["result"]["argv"][-2:] == ["--", str(pack_dir.resolve())]
    assert any("replay_report.json" in item for item in result["disclosures"]["writes"])


def test_paths_outside_run_root_fail_closed_before_cli(tmp_path: Path) -> None:
    config = _config(tmp_path, _protocol_stub())
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    result = _json(tools.smcub_validate_envelope({"envelope_path": str(outside)}, config=config))
    assert result["status"] == "error"
    assert "outside" in result["error"]
