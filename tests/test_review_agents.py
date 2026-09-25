from __future__ import annotations

import json
import subprocess

import pytest

from smartmoney_cub_harness.agent import review_agents
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


ENVELOPE = {"schema": "smartmoney_cub_redacted_review_envelope.v2", "payload": {"summary": {}}, "safety": SAFETY_DECLARATION}


def _enable_fake_agent(monkeypatch: pytest.MonkeyPatch, agent_id: str = "codex") -> None:
    monkeypatch.setattr(review_agents, "_PROTOCOL_COMPATIBLE", frozenset({agent_id}))
    monkeypatch.setattr(review_agents.shutil, "which", lambda executable: "/opt/fake-agent")


def _result(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["/opt/fake-agent", *review_agents._REVIEW_ARGV["codex"]], returncode, stdout, "diagnostic")


def test_probe_distinguishes_detection_from_protocol_compatibility(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(review_agents.shutil, "which", lambda executable: "/opt/codex")
    monkeypatch.setattr(review_agents, "_version", lambda executable: "codex 1.0")
    item = review_agents.probe_agent("codex")
    assert item["detected"] is True
    assert item["status"] == "runnable"
    assert item["enabled"] is True
    assert item["protocol"]["compatible"] is True
    assert item["safety"] == SAFETY_DECLARATION


def test_run_sends_fixed_json_request_and_validates_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_fake_agent(monkeypatch)
    calls: list[dict] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        assert review_agents.REVIEW_PROTOCOL in kwargs["input"]
        assert SAFETY_DECLARATION in kwargs["input"]
        assert "token=secret" not in kwargs["input"]
        message = json.dumps({"protocol": review_agents.REVIEW_PROTOCOL, "status": "ok", "text": "复盘完成", "safety": SAFETY_DECLARATION})
        event = json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": message}})
        return _result(event)

    monkeypatch.setattr(review_agents.subprocess, "run", fake_run)
    result = review_agents.run_local_review("codex", ENVELOPE, "检查入场纪律")
    assert result["text"] == "复盘完成"
    assert calls[0]["command"] == ["/opt/fake-agent", *review_agents._REVIEW_ARGV["codex"]]
    assert calls[0]["shell"] is False
    assert calls[0]["cwd"] == "/"
    assert calls[0]["env"] == {"PATH": "/opt", "LANG": "C", "LC_ALL": "C"}


def test_rejects_disabled_and_incompatible_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(review_agents.LocalAgentError, match="未启用") as disabled:
        review_agents.run_local_review("codex", ENVELOPE, enabled=False)
    assert disabled.value.code == "agent_disabled"
    monkeypatch.setattr(review_agents, "_PROTOCOL_COMPATIBLE", frozenset())
    with pytest.raises(review_agents.LocalAgentError) as incompatible:
        review_agents.run_local_review("codex", ENVELOPE)
    assert incompatible.value.code == "protocol_incompatible"


@pytest.mark.parametrize(
    ("returncode", "stdout", "code"),
    [
        (1, "", "nonzero_exit"),
        (0, "not json", "invalid_stdout"),
        (0, json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps({"protocol": "wrong", "status": "ok", "text": "x", "safety": SAFETY_DECLARATION})}}), "protocol_mismatch"),
        (0, json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps({"protocol": review_agents.REVIEW_PROTOCOL, "status": "ok", "text": "x", "safety": "wrong"})}}), "invalid_safety"),
    ],
)
def test_rejects_process_failures_and_untrusted_stdout(monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str, code: str) -> None:
    _enable_fake_agent(monkeypatch)
    monkeypatch.setattr(review_agents.subprocess, "run", lambda *args, **kwargs: _result(stdout, returncode))
    with pytest.raises(review_agents.LocalAgentError) as error:
        review_agents.run_local_review("codex", ENVELOPE)
    assert error.value.code == code


def test_maps_timeout_and_does_not_accept_caller_command_or_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_fake_agent(monkeypatch)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(kwargs.get("args", args[0]), kwargs["timeout"])

    monkeypatch.setattr(review_agents.subprocess, "run", timeout)
    with pytest.raises(review_agents.LocalAgentError) as error:
        review_agents.run_local_review("codex", ENVELOPE, timeout_seconds=2)
    assert error.value.code == "timeout"
    with pytest.raises(review_agents.LocalAgentError) as invalid:
        review_agents.run_local_review("codex", {"safety": "wrong"})
    assert invalid.value.code == "invalid_safety"
