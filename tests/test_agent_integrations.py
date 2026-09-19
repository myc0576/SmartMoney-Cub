"""Tests for Agent Integration Center."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from smartmoney_cub_harness.agent.integrations import (
    AGENT_STATUS,
    SUPPORTED_AGENTS,
    AgentIntegration,
    apply_agent,
    disable_agent,
    restore_agent,
    scan_agents,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_agent_status_constants():
    assert "not_found" in AGENT_STATUS
    assert "detected" in AGENT_STATUS
    assert "configured" in AGENT_STATUS
    assert "healthy" in AGENT_STATUS
    assert "unavailable" in AGENT_STATUS
    assert "unsupported" in AGENT_STATUS
    assert set(SUPPORTED_AGENTS) == {
        "codex",
        "claude-code",
        "deepseek-harness",
        "opencode",
        "gemini-cli",
        "pi",
    }


def test_scan_agents_empty_home(tmp_path: Path):
    # Completely empty home directory: everything should be not_found
    integrations = scan_agents(home=tmp_path)
    assert len(integrations) >= 6
    by_id = {item.agent_id: item for item in integrations}
    for agent_id in SUPPORTED_AGENTS:
        assert agent_id in by_id
        assert by_id[agent_id].status == "not_found"
        assert by_id[agent_id].config_path is None

    # scan_agents must be strictly read-only: tmp_path remains empty
    assert list(tmp_path.iterdir()) == []


def test_scan_agents_detected_when_dir_present(tmp_path: Path):
    # Setup directories for agents
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".dsh").mkdir()
    (tmp_path / ".config" / "opencode").mkdir(parents=True)
    (tmp_path / ".gemini" / "config").mkdir(parents=True)
    (tmp_path / ".config" / "pi").mkdir(parents=True)

    integrations = scan_agents(home=tmp_path)
    by_id = {item.agent_id: item for item in integrations}

    for agent_id in SUPPORTED_AGENTS:
        assert by_id[agent_id].status == "detected"
        assert by_id[agent_id].config_path is not None


def test_apply_disable_restore_preserves_unrelated_json(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    settings_file = claude_dir / "settings.json"
    initial_content = {
        "theme": "dark",
        "env": {"FOO": "BAR"},
        "user_custom": 123,
    }
    settings_file.write_text(json.dumps(initial_content, indent=2))

    # 1. Apply dry_run
    dry = apply_agent("claude-code", home=tmp_path, dry_run=True)
    assert dry.status == "configured"
    # Content must NOT change on dry-run
    assert json.loads(settings_file.read_text()) == initial_content

    # 2. Apply real
    real = apply_agent("claude-code", home=tmp_path, dry_run=False)
    assert real.status in ("configured", "healthy")
    after_apply = json.loads(settings_file.read_text())
    assert after_apply["theme"] == "dark"
    assert after_apply["env"] == {"FOO": "BAR"}
    assert after_apply["user_custom"] == 123
    assert "smartmoney_cub" in after_apply
    assert after_apply["smartmoney_cub"]["enabled"] is True
    assert after_apply["smartmoney_cub"]["safety"] == SAFETY_DECLARATION

    # 3. Disable
    disabled = disable_agent("claude-code", home=tmp_path)
    assert disabled.status == "configured"
    after_disable = json.loads(settings_file.read_text())
    assert after_disable["theme"] == "dark"
    assert after_disable["user_custom"] == 123
    assert after_disable["smartmoney_cub"]["enabled"] is False

    # 4. Restore
    restored = restore_agent("claude-code", home=tmp_path)
    assert restored.status == "detected"
    after_restore = json.loads(settings_file.read_text())
    assert after_restore == initial_content
    assert "smartmoney_cub" not in after_restore


def test_apply_disable_restore_preserves_unrelated_toml(tmp_path: Path):
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir(parents=True)
    config_file = codex_dir / "config.toml"
    initial_text = 'model = "gpt-5.6-sol"\nmodel_reasoning_effort = "xhigh"\n'
    config_file.write_text(initial_text)

    # 1. Apply dry_run
    dry = apply_agent("codex", home=tmp_path, dry_run=True)
    assert dry.status == "configured"
    assert config_file.read_text() == initial_text

    # 2. Apply real
    real = apply_agent("codex", home=tmp_path, dry_run=False)
    assert real.status in ("configured", "healthy")
    applied_text = config_file.read_text()
    assert 'model = "gpt-5.6-sol"' in applied_text
    assert 'model_reasoning_effort = "xhigh"' in applied_text
    assert "[smartmoney_cub]" in applied_text
    assert "enabled = true" in applied_text

    # 3. Disable
    disabled = disable_agent("codex", home=tmp_path)
    assert disabled.status == "configured"
    disabled_text = config_file.read_text()
    assert 'model = "gpt-5.6-sol"' in disabled_text
    assert "enabled = false" in disabled_text

    # 4. Restore
    restored = restore_agent("codex", home=tmp_path)
    assert restored.status == "detected"
    restored_text = config_file.read_text()
    assert "[smartmoney_cub]" not in restored_text
    assert 'model = "gpt-5.6-sol"' in restored_text
    assert 'model_reasoning_effort = "xhigh"' in restored_text


def test_apply_disable_restore_preserves_unrelated_yaml(tmp_path: Path):
    dsh_dir = tmp_path / ".dsh"
    dsh_dir.mkdir(parents=True)
    settings_file = dsh_dir / "settings.yaml"
    initial_text = "permission:\n  defaultPreset: danger-full-access\n"
    settings_file.write_text(initial_text)

    # Apply
    apply_agent("deepseek-harness", home=tmp_path)
    applied_text = settings_file.read_text()
    assert "defaultPreset: danger-full-access" in applied_text
    assert "smartmoney_cub:" in applied_text
    assert "enabled: true" in applied_text

    # Disable
    disable_agent("deepseek-harness", home=tmp_path)
    disabled_text = settings_file.read_text()
    assert "defaultPreset: danger-full-access" in disabled_text
    assert "enabled: false" in disabled_text

    # Restore
    restore_agent("deepseek-harness", home=tmp_path)
    restored_text = settings_file.read_text()
    assert "defaultPreset: danger-full-access" in restored_text
    assert "smartmoney_cub:" not in restored_text


def test_unsupported_agent_handling(tmp_path: Path):
    integrations = scan_agents(home=tmp_path)
    unsupported = [item for item in integrations if item.status == "unsupported"]
    assert len(unsupported) > 0

    with pytest.raises(ValueError, match="Unsupported agent"):
        apply_agent(unsupported[0].agent_id, home=tmp_path)
