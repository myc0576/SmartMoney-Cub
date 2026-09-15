from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from smartmoney_cub_harness.plugin_cli import (
    plugin_disable,
    plugin_doctor,
    plugin_enable,
    plugin_inspect,
    plugin_list,
    plugin_logs,
    plugin_remove,
    plugin_run,
    profile_reload,
    profile_show,
)
from smartmoney_cub_harness.plugins import PluginRuntime, PluginState, PluginStateStore
from smartmoney_cub_harness.plugins.profiles import get_profile
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

TOY_PLUGIN_DIR = Path(__file__).resolve().parents[1] / "examples" / "toy_plugin"
TOY_MANIFEST = TOY_PLUGIN_DIR / "plugin.json"

DECISION_TIME = "2026-09-10T15:00:00+08:00"
AVAILABLE_AT = "2026-09-10T14:00:00+08:00"


def _write_manifest(directory: Path, payload: dict, name: str = "plugin.json") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _toy_manifest(**overrides: object) -> dict:
    payload = json.loads(TOY_MANIFEST.read_text(encoding="utf-8"))
    payload.update(overrides)
    return payload


def _state_db(tmp_path: Path) -> str:
    return str(tmp_path / "plugin_state.db")


def test_reference_plugin_manifest_is_valid_and_declares_review_only() -> None:
    result = plugin_inspect(str(TOY_MANIFEST))
    assert result["status"] == "ok"
    assert result["manifest"]["plugin_id"] == "toy.review-tagger"
    assert result["manifest"]["capabilities"] == ["reviewer"]
    assert result["network_required"] is False
    assert result["requires_credentials"] is False


def test_local_plugin_is_discovered_and_activated_automatically(tmp_path: Path) -> None:
    listing = plugin_list(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=_state_db(tmp_path))
    assert listing["status"] == "ok"
    assert [item["plugin_id"] for item in listing["plugins"]] == ["toy.review-tagger"]
    assert listing["safety"] == SAFETY_DECLARATION

    doctor = plugin_doctor(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=_state_db(tmp_path))
    assert doctor["profile"] == "default-offline"
    assert doctor["sandbox_verified"] is False
    assert doctor["permission_enforcement"] == "declarative"
    reviewer = next(item for item in doctor["capabilities"] if item["capability"] == "reviewer")
    assert reviewer["status"] == "available"
    assert reviewer["provider"]["plugin_id"] == "toy.review-tagger"


def test_run_wraps_output_in_evidence_envelope(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"symbol": "600111", "return_pct": -8.5}), encoding="utf-8")

    result = plugin_run(
        "toy.review-tagger",
        capability="reviewer",
        request_path=str(request),
        decision_time=DECISION_TIME,
        available_at=AVAILABLE_AT,
        data_source="toy_fixture",
        plugin_dirs=[str(TOY_PLUGIN_DIR)],
        state_db=db,
    )
    assert result["status"] == "ok"
    envelope = result["envelope"]
    assert envelope["review_only"] is True
    assert envelope["result_kind"] == "review_observation"
    assert envelope["plugin_id"] == "toy.review-tagger"
    assert envelope["isolation"] == "subprocess"
    assert envelope["network_used"] is False
    assert envelope["champion_mutated"] is False
    assert envelope["permission"]["order"] is False
    assert len(envelope["output_sha256"]) == 64
    # The reference plugin must surface the missing invalidation price as review evidence.
    details = " ".join(item["detail"] for item in envelope["output"]["observations"])
    assert "invalidation" in details


def test_run_refuses_future_data_and_missing_provenance(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    leak = plugin_run(
        "toy.review-tagger",
        capability="reviewer",
        decision_time=DECISION_TIME,
        available_at="2026-09-11T15:00:00+08:00",
        plugin_dirs=[str(TOY_PLUGIN_DIR)],
        state_db=db,
    )
    assert leak["status"] == "error"
    assert leak["error"]["code"] == "EvidenceEnvelopeError"
    assert "future leakage" in leak["error"]["message"]

    no_decision_time = plugin_run(
        "toy.review-tagger",
        capability="reviewer",
        decision_time=None,
        available_at=AVAILABLE_AT,
        plugin_dirs=[str(TOY_PLUGIN_DIR)],
        state_db=db,
    )
    assert no_decision_time["status"] == "error"
    assert no_decision_time["error"]["code"] == "decision_time_required"

    no_available_at = plugin_run(
        "toy.review-tagger",
        capability="reviewer",
        decision_time=DECISION_TIME,
        available_at=None,
        plugin_dirs=[str(TOY_PLUGIN_DIR)],
        state_db=db,
    )
    assert no_available_at["error"]["code"] == "available_at_required"


def test_plugin_failure_stays_visible_and_never_becomes_success(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "broken"
    failing = tmp_path / "failing_provider.py"
    failing.write_text(
        "import sys\n"
        "sys.stdout.write('not json at all')\n",
        encoding="utf-8",
    )
    _write_manifest(
        plugin_dir,
        _toy_manifest(
            plugin_id="demo.broken",
            name="Broken Provider",
            entrypoint=[sys.executable, str(failing)],
        ),
    )

    result = plugin_run(
        "demo.broken",
        capability="reviewer",
        decision_time=DECISION_TIME,
        available_at=AVAILABLE_AT,
        plugin_dirs=[str(plugin_dir)],
        state_db=_state_db(tmp_path),
    )
    assert result["status"] == "failed"
    envelope = result["envelope"]
    assert envelope["error"] is not None
    assert envelope["output"] is None
    assert envelope["output_sha256"] is None


def test_missing_hard_dependency_moves_plugin_to_pending(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "needs-evaluator"
    _write_manifest(
        plugin_dir,
        _toy_manifest(
            plugin_id="demo.needs-evaluator",
            name="Needs Evaluator",
            required_services=["evaluator"],
        ),
    )
    runtime = PluginRuntime(profile=get_profile("default-offline"), state_store=PluginStateStore(_state_db(tmp_path)))
    runtime.discover([str(plugin_dir)])
    instance = runtime.activate("demo.needs-evaluator", enabled=True)
    assert instance.state == PluginState.PENDING
    assert instance.missing_services == ["evaluator"]


def test_network_plugin_is_blocked_under_offline_profile(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "networked"
    _write_manifest(
        plugin_dir,
        _toy_manifest(
            plugin_id="demo.networked",
            name="Networked Data",
            network_required=True,
            credential_requirements=["DEMO_API_KEY"],
        ),
    )
    runtime = PluginRuntime(profile=get_profile("default-offline"), state_store=PluginStateStore(_state_db(tmp_path)))
    runtime.discover([str(plugin_dir)])
    instance = runtime.activate("demo.networked", enabled=True)
    assert instance.state == PluginState.BLOCKED
    assert "network_required_but_profile_disallows_network" in instance.blockers
    assert "credentials_required_but_profile_disallows_credentials" in instance.blockers


def test_plugin_timeout_is_recorded_as_failure_not_success(tmp_path: Path) -> None:
    from smartmoney_cub_harness.plugins.runtime import SubprocessProvider

    plugin_dir = tmp_path / "slow"
    slow = tmp_path / "slow_provider.py"
    slow.write_text("import time" + chr(10) + "time.sleep(30)" + chr(10), encoding="utf-8")
    _write_manifest(
        plugin_dir,
        _toy_manifest(
            plugin_id="demo.slow",
            name="Slow Provider",
            entrypoint=[sys.executable, str(slow)],
        ),
    )

    runtime = PluginRuntime(
        profile=get_profile("default-offline"), state_store=PluginStateStore(_state_db(tmp_path))
    )
    runtime.discover([str(plugin_dir)])
    runtime.register_provider(
        "demo.slow",
        SubprocessProvider(
            capability="reviewer",
            plugin_id="demo.slow",
            command=[sys.executable, str(slow)],
            timeout_seconds=1,
        ),
    )
    runtime.activate("demo.slow", enabled=True)

    envelope = runtime.execute(
        plugin_id="demo.slow",
        capability="reviewer",
        request={},
        decision_time="2026-09-10T15:00:00+08:00",
        available_at="2026-09-10T14:00:00+08:00",
    )
    assert envelope["error"] is not None
    assert "timed out" in envelope["error"]
    assert envelope["output"] is None
    assert envelope["output_sha256"] is None
    assert runtime.registry.get("demo.slow").state == PluginState.FAILED


def test_execute_requires_an_active_plugin(tmp_path: Path) -> None:
    from smartmoney_cub_harness.plugins.runtime import PluginPermissionError

    plugin_dir = tmp_path / "inactive"
    _write_manifest(plugin_dir, _toy_manifest(plugin_id="demo.inactive", name="Inactive"))
    runtime = PluginRuntime(
        profile=get_profile("default-offline"), state_store=PluginStateStore(_state_db(tmp_path))
    )
    runtime.discover([str(plugin_dir)])
    runtime.activate("demo.inactive", enabled=False)
    with pytest.raises(PluginPermissionError):
        runtime.execute(
            plugin_id="demo.inactive",
            capability="reviewer",
            request={},
            decision_time=None,
            available_at="2026-09-10T14:00:00+08:00",
        )


def test_disabled_plugin_refuses_to_run_until_reenabled(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    plugin_doctor(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=db)
    disabled = plugin_disable("toy.review-tagger", state_db=db)
    assert disabled["status"] == "ok"
    assert disabled["plugin"]["state"] == PluginState.DISABLED

    refused = plugin_run(
        "toy.review-tagger",
        capability="reviewer",
        decision_time=DECISION_TIME,
        available_at=AVAILABLE_AT,
        state_db=db,
    )
    assert refused["status"] == "not_enabled"

    enabled = plugin_enable("toy.review-tagger", plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=db)
    assert enabled["plugin"]["state"] == PluginState.ACTIVE


def test_deactivate_rolls_back_registered_capability(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    plugin_doctor(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=db)
    plugin_disable("toy.review-tagger", state_db=db)

    doctor = plugin_doctor(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=db)
    reviewer = next(item for item in doctor["capabilities"] if item["capability"] == "reviewer")
    # The rollback must remove the provider so no consumer holds a stale reference.
    assert reviewer["status"] == "unavailable"


def test_duplicate_plugin_id_is_rejected(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_manifest(first, _toy_manifest())
    _write_manifest(second, _toy_manifest())
    listing = plugin_list(
        plugin_dirs=[str(first), str(second)], state_db=_state_db(tmp_path)
    )
    reasons = [item["reason"] for item in listing["rejected"]]
    assert "duplicate_plugin_id" in reasons


def test_invalid_manifest_is_rejected_with_reasons(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "unsafe"
    _write_manifest(plugin_dir, _toy_manifest(capabilities=["order_execution"]))
    listing = plugin_list(plugin_dirs=[str(plugin_dir)], state_db=_state_db(tmp_path))
    assert listing["plugins"] == []
    assert any(
        "forbidden_capability:order_execution" in item["errors"]
        for item in listing["rejected"]
    )


def test_plugin_lifecycle_events_are_recorded(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    plugin_doctor(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=db)
    logs = plugin_logs("toy.review-tagger", state_db=db)
    assert logs["state"]["plugin_id"] == "toy.review-tagger"
    assert logs["state"]["safety"] == SAFETY_DECLARATION
    states = [event["to_state"] for event in logs["events"]]
    assert PluginState.ACTIVE in states


def test_remove_revokes_entry_but_keeps_audit_trail(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    plugin_doctor(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=db)
    removed = plugin_remove("toy.review-tagger", state_db=db)
    assert removed["status"] == "ok"
    assert removed["state"] == PluginState.REVOKED
    logs = plugin_logs("toy.review-tagger", state_db=db)
    assert logs["state"]["state"] == PluginState.REVOKED
    assert logs["events"]


def test_state_survives_process_boundaries_via_state_store(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    plugin_doctor(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=db)
    store = PluginStateStore(db)
    record = store.get("toy.review-tagger")
    assert record is not None
    # Provenance must be recoverable without re-reading the manifest file.
    assert record["manifest"]["license"] == "MIT"
    assert record["manifest"]["source_repo"]
    store.close()


def test_profile_show_and_reload_keep_disabled_plugins_disabled(tmp_path: Path) -> None:
    db = _state_db(tmp_path)
    shown = profile_show("a-share-review")
    assert shown["status"] == "ok"
    assert shown["allow_network"] is False
    assert shown["safety"] == SAFETY_DECLARATION

    plugin_doctor(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=db)
    plugin_disable("toy.review-tagger", state_db=db)
    reloaded = profile_reload(plugin_dirs=[str(TOY_PLUGIN_DIR)], state_db=db)
    assert reloaded["reloaded"] is True
    assert reloaded["hot_reload"] is False
    states = {item["plugin_id"]: item["state"] for item in reloaded["activation"]}
    assert states["toy.review-tagger"] == PluginState.DISABLED


def test_runtime_does_not_hard_depend_on_external_trading_projects() -> None:
    # The shipped core must run with no third-party trading libraries installed.
    import importlib.util

    for module_name in ("akshare", "vectorbt", "quantstats", "backtesting", "qlib", "vnpy"):
        assert importlib.util.find_spec(module_name) is None
