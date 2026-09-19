"""Agent integration center for local developer harnesses and CLI agents.

Provides safe discovery, configuration fragment management, and status inspection
for external coding agents without taking execution authority.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

AGENT_STATUS = (
    "not_found",
    "detected",
    "configured",
    "healthy",
    "unavailable",
    "unsupported",
)

SUPPORTED_AGENTS = (
    "codex",
    "claude-code",
    "deepseek-harness",
    "opencode",
    "gemini-cli",
    "pi",
)

OTHER_KNOWN_AGENTS = (
    ("aider", "Aider AI Pair Programmer"),
    ("cline", "Cline (Autonomous Coding Agent)"),
    ("cursor", "Cursor IDE Agent"),
    ("windsurf", "Windsurf / Codeium Cascade"),
)


@dataclass
class AgentIntegration:
    """Status record for an external agent harness integration."""

    agent_id: str
    label: str
    status: str
    config_path: str | None = None
    detected_version: str | None = None
    detail: str = ""
    owned_keys: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in AGENT_STATUS:
            raise ValueError(f"Invalid status {self.status!r}, must be one of {AGENT_STATUS}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _resolve_home(home: Path | str | None = None) -> Path:
    if home is not None:
        return Path(home).expanduser().resolve()
    return Path.home()


def _get_agent_spec(agent_id: str) -> dict[str, Any]:
    specs: dict[str, dict[str, Any]] = {
        "codex": {
            "label": "OpenAI Codex CLI / Harness",
            "dir": ".codex",
            "file": ".codex/config.toml",
            "format": "toml",
        },
        "claude-code": {
            "label": "Anthropic Claude Code",
            "dir": ".claude",
            "file": ".claude/settings.json",
            "format": "json",
        },
        "deepseek-harness": {
            "label": "DeepSeek Harness (DSH)",
            "dir": ".dsh",
            "file": ".dsh/settings.yaml",
            "format": "yaml",
        },
        "opencode": {
            "label": "OpenCode Agent CLI",
            "dir": ".config/opencode",
            "file": ".config/opencode/opencode.jsonc",
            "format": "json",
        },
        "gemini-cli": {
            "label": "Google Gemini CLI",
            "dir": ".gemini",
            "alt_dir": ".gemini/config",
            "file": ".gemini/config/config.json",
            "format": "json",
        },
        "pi": {
            "label": "Pi AI Coding Assistant",
            "dir": ".config/pi",
            "file": ".config/pi/config.json",
            "format": "json",
        },
    }
    if agent_id not in specs:
        raise ValueError(f"Unsupported agent: {agent_id}")
    return specs[agent_id]


def _read_owned_state(config_path: Path, fmt: str) -> tuple[bool, bool]:
    """Inspect if smartmoney_cub key exists and if it is enabled.

    Returns (present, enabled).
    """
    if not config_path.is_file():
        return False, False

    content = config_path.read_text(encoding="utf-8")
    if fmt == "json":
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "smartmoney_cub" in data:
                smc = data["smartmoney_cub"]
                enabled = smc.get("enabled", False) if isinstance(smc, dict) else False
                return True, enabled
        except Exception:
            return False, False
    elif fmt == "toml":
        try:
            import tomllib

            data = tomllib.loads(content)
            if "smartmoney_cub" in data:
                smc = data["smartmoney_cub"]
                enabled = smc.get("enabled", False) if isinstance(smc, dict) else False
                return True, enabled
        except Exception:
            if "[smartmoney_cub]" in content:
                enabled = "enabled = true" in content
                return True, enabled
    elif fmt == "yaml":
        try:
            import yaml

            data = yaml.safe_load(content)
            if isinstance(data, dict) and "smartmoney_cub" in data:
                smc = data["smartmoney_cub"]
                enabled = smc.get("enabled", False) if isinstance(smc, dict) else False
                return True, enabled
        except Exception:
            if "smartmoney_cub:" in content:
                enabled = "enabled: true" in content
                return True, enabled

    return False, False


def scan_agents(home: Path | str | None = None) -> list[AgentIntegration]:
    """Scan the environment for known agents in a strictly read-only manner.

    Never creates, writes, or modifies any files or directories.
    """
    root = _resolve_home(home)
    results: list[AgentIntegration] = []

    for agent_id in SUPPORTED_AGENTS:
        spec = _get_agent_spec(agent_id)
        label = spec["label"]
        primary_dir = root / spec["dir"]
        alt_dir = root / spec.get("alt_dir", "") if "alt_dir" in spec else None
        target_file = root / spec["file"]

        exists = primary_dir.exists() or (alt_dir is not None and alt_dir.exists())

        if not exists:
            results.append(
                AgentIntegration(
                    agent_id=agent_id,
                    label=label,
                    status="not_found",
                    config_path=None,
                    detected_version=None,
                    detail=f"Configuration directory {spec['dir']} not found.",
                    owned_keys=[],
                )
            )
            continue

        config_path_str = str(target_file) if target_file.exists() else str(primary_dir)
        present, enabled = _read_owned_state(target_file, spec["format"])

        if present and enabled:
            status = "configured"
            detail = "SmartMoney-Cub review integration active."
            owned_keys = ["smartmoney_cub"]
        elif present and not enabled:
            status = "configured"
            detail = "SmartMoney-Cub integration present but disabled."
            owned_keys = ["smartmoney_cub"]
        else:
            status = "detected"
            detail = "Agent installed and detected; integration not configured."
            owned_keys = []

        results.append(
            AgentIntegration(
                agent_id=agent_id,
                label=label,
                status=status,
                config_path=config_path_str,
                detected_version="detected",
                detail=detail,
                owned_keys=owned_keys,
            )
        )

    for agent_id, label in OTHER_KNOWN_AGENTS:
        results.append(
            AgentIntegration(
                agent_id=agent_id,
                label=label,
                status="unsupported",
                config_path=None,
                detected_version=None,
                detail="Manual review envelope invocation supported; automated config injection not supported.",
                owned_keys=[],
            )
        )

    return results


def apply_agent(
    agent_id: str,
    *,
    home: Path | str | None = None,
    dry_run: bool = False,
) -> AgentIntegration:
    """Inject or enable the SmartMoney-Cub review configuration fragment for an agent."""
    root = _resolve_home(home)
    spec = _get_agent_spec(agent_id)
    target_file = root / spec["file"]
    fmt = spec["format"]

    fragment = {
        "enabled": True,
        "endpoint": "http://localhost:8765",
        "profile": "smartmoney-review",
        "safety": SAFETY_DECLARATION,
    }

    if dry_run:
        return AgentIntegration(
            agent_id=agent_id,
            label=spec["label"],
            status="configured",
            config_path=str(target_file),
            detected_version="dry_run",
            detail="Dry run: configuration would be applied.",
            owned_keys=["smartmoney_cub"],
        )

    target_file.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        data: dict[str, Any] = {}
        if target_file.is_file():
            try:
                loaded = json.loads(target_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}
        data["smartmoney_cub"] = fragment
        target_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    elif fmt == "toml":
        current_text = target_file.read_text(encoding="utf-8") if target_file.is_file() else ""
        cleaned = _remove_toml_section(current_text, "smartmoney_cub")
        toml_block = (
            "\n[smartmoney_cub]\n"
            "enabled = true\n"
            'endpoint = "http://localhost:8765"\n'
            'profile = "smartmoney-review"\n'
            f'safety = "{SAFETY_DECLARATION}"\n'
        )
        new_text = cleaned.rstrip() + "\n" + toml_block.lstrip()
        target_file.write_text(new_text, encoding="utf-8")

    elif fmt == "yaml":
        current_text = target_file.read_text(encoding="utf-8") if target_file.is_file() else ""
        cleaned = _remove_yaml_key(current_text, "smartmoney_cub")
        yaml_block = (
            "\nsmartmoney_cub:\n"
            "  enabled: true\n"
            '  endpoint: "http://localhost:8765"\n'
            '  profile: "smartmoney-review"\n'
            f'  safety: "{SAFETY_DECLARATION}"\n'
        )
        new_text = cleaned.rstrip() + "\n" + yaml_block.lstrip()
        target_file.write_text(new_text, encoding="utf-8")

    return AgentIntegration(
        agent_id=agent_id,
        label=spec["label"],
        status="configured",
        config_path=str(target_file),
        detected_version="configured",
        detail="SmartMoney-Cub configuration applied successfully.",
        owned_keys=["smartmoney_cub"],
    )


def disable_agent(
    agent_id: str,
    *,
    home: Path | str | None = None,
) -> AgentIntegration:
    """Disable the SmartMoney-Cub review configuration without deleting the section."""
    root = _resolve_home(home)
    spec = _get_agent_spec(agent_id)
    target_file = root / spec["file"]
    fmt = spec["format"]

    if not target_file.is_file():
        return AgentIntegration(
            agent_id=agent_id,
            label=spec["label"],
            status="detected" if (root / spec["dir"]).exists() else "not_found",
            config_path=str(target_file) if target_file.exists() else None,
            detected_version=None,
            detail="Configuration file does not exist.",
            owned_keys=[],
        )

    if fmt == "json":
        try:
            data = json.loads(target_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "smartmoney_cub" in data:
                if isinstance(data["smartmoney_cub"], dict):
                    data["smartmoney_cub"]["enabled"] = False
                else:
                    data["smartmoney_cub"] = {"enabled": False}
                target_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass

    elif fmt == "toml":
        current_text = target_file.read_text(encoding="utf-8")
        if "[smartmoney_cub]" in current_text:
            cleaned = _remove_toml_section(current_text, "smartmoney_cub")
            toml_block = (
                "\n[smartmoney_cub]\n"
                "enabled = false\n"
                'endpoint = "http://localhost:8765"\n'
                'profile = "smartmoney-review"\n'
                f'safety = "{SAFETY_DECLARATION}"\n'
            )
            new_text = cleaned.rstrip() + "\n" + toml_block.lstrip()
            target_file.write_text(new_text, encoding="utf-8")

    elif fmt == "yaml":
        current_text = target_file.read_text(encoding="utf-8")
        if "smartmoney_cub:" in current_text:
            cleaned = _remove_yaml_key(current_text, "smartmoney_cub")
            yaml_block = (
                "\nsmartmoney_cub:\n"
                "  enabled: false\n"
                '  endpoint: "http://localhost:8765"\n'
                '  profile: "smartmoney-review"\n'
                f'  safety: "{SAFETY_DECLARATION}"\n'
            )
            new_text = cleaned.rstrip() + "\n" + yaml_block.lstrip()
            target_file.write_text(new_text, encoding="utf-8")

    return AgentIntegration(
        agent_id=agent_id,
        label=spec["label"],
        status="configured",
        config_path=str(target_file),
        detected_version="configured",
        detail="SmartMoney-Cub configuration disabled.",
        owned_keys=["smartmoney_cub"],
    )


def restore_agent(
    agent_id: str,
    *,
    home: Path | str | None = None,
) -> AgentIntegration:
    """Remove the SmartMoney-Cub owned configuration fragment entirely, leaving other user config intact."""
    root = _resolve_home(home)
    spec = _get_agent_spec(agent_id)
    target_file = root / spec["file"]
    fmt = spec["format"]

    if not target_file.is_file():
        return AgentIntegration(
            agent_id=agent_id,
            label=spec["label"],
            status="detected" if (root / spec["dir"]).exists() else "not_found",
            config_path=None,
            detected_version=None,
            detail="Configuration file does not exist.",
            owned_keys=[],
        )

    if fmt == "json":
        try:
            data = json.loads(target_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "smartmoney_cub" in data:
                del data["smartmoney_cub"]
                target_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:
            pass

    elif fmt == "toml":
        current_text = target_file.read_text(encoding="utf-8")
        cleaned = _remove_toml_section(current_text, "smartmoney_cub")
        target_file.write_text(cleaned, encoding="utf-8")

    elif fmt == "yaml":
        current_text = target_file.read_text(encoding="utf-8")
        cleaned = _remove_yaml_key(current_text, "smartmoney_cub")
        target_file.write_text(cleaned, encoding="utf-8")

    return AgentIntegration(
        agent_id=agent_id,
        label=spec["label"],
        status="detected" if (root / spec["dir"]).exists() else "not_found",
        config_path=str(target_file),
        detected_version="detected",
        detail="SmartMoney-Cub configuration removed; user configuration restored.",
        owned_keys=[],
    )


def _remove_toml_section(text: str, section_name: str) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            cur_sec = stripped[1:-1].strip()
            if cur_sec == section_name or cur_sec.startswith(section_name + "."):
                in_section = True
                continue
            else:
                in_section = False
        if not in_section:
            out.append(line)
    result = "".join(out).rstrip()
    return (result + "\n") if result else ""


def _remove_yaml_key(text: str, key_name: str) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if not line.startswith(" ") and not line.startswith("\t") and stripped.startswith(key_name + ":"):
            in_block = True
            continue
        if in_block:
            if not line.startswith(" ") and not line.startswith("\t") and stripped and not stripped.startswith("#"):
                in_block = False
                out.append(line)
            continue
        out.append(line)
    result = "".join(out).rstrip()
    return (result + "\n") if result else ""
