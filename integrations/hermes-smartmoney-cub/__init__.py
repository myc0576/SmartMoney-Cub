"""SmartMoney-Cub plugin for Hermes Agent.

Exposes the local, read-only smcub harness as six review tools plus a
capability-gated operation surface. Nothing here
places or cancels an order, connects to a broker, or produces financial advice:
every tool shells out to the user's own copy of the harness and passes its
output through unchanged.
"""

from __future__ import annotations

import logging
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from . import schemas, tools

logger = logging.getLogger(__name__)

PLUGIN_ID = "smartmoney-cub"


def _read_config(ctx: Any) -> dict[str, Any]:
    """Read this plugin's settings at call time so edits take effect live."""
    defaults = {
        "smcub_command": "smcub",
        "timeout_seconds": tools.DEFAULT_TIMEOUT,
        "run_root": "",
        "state_dir": "",
    }
    config: dict[str, Any] = {}
    for key, default in defaults.items():
        try:
            config[key] = ctx.get_config(key, default=default)
        except Exception:  # a settings backend must never break a tool call
            config[key] = default
    return config


def _bind(fn: Callable[..., str], ctx: Any) -> Callable[..., str]:
    """Inject the live plugin config into every handler call."""

    @wraps(fn)
    def wrapper(args: dict[str, Any], **kwargs: Any) -> str:
        kwargs["config"] = _read_config(ctx)
        return fn(args, **kwargs)

    return wrapper


def _register_tools(ctx: Any) -> list[str]:
    """Register the harness tools and return the names that landed."""
    registered: list[str] = []
    tools_by_name = {
        "smcub_doctor": tools.smcub_doctor,
        "smcub_validate_envelope": tools.smcub_validate_envelope,
        "smcub_build_evidence_pack": tools.smcub_build_evidence_pack,
        "smcub_replay_evidence_pack": tools.smcub_replay_evidence_pack,
        "smcub_evaluate_run": tools.smcub_evaluate_run,
        "smcub_inspect_artifacts": tools.smcub_inspect_artifacts,
        "smcub_capabilities": tools.smcub_capabilities,
        "smcub_operation": tools.smcub_operation,
    }
    for schema in schemas.ALL_SCHEMAS:
        name = schema["name"]
        handler = tools_by_name.get(name)
        if handler is None:
            logger.warning("no handler for schema %s", name)
            continue
        try:
            ctx.register_tool(
                name=name,
                toolset=PLUGIN_ID,
                schema=schema,
                handler=_bind(handler, ctx),
            )
            registered.append(name)
        except Exception as exc:  # one bad tool must not disable the rest
            logger.warning("could not register %s: %s", name, exc)
    return registered


def _register_skills(ctx: Any) -> None:
    skills_dir = Path(__file__).parent / "skills"
    if not skills_dir.is_dir():
        return
    for child in sorted(skills_dir.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            try:
                ctx.register_skill(child.name, skill_md)
            except Exception as exc:
                logger.warning("could not register skill %s: %s", child.name, exc)


def register(ctx: Any) -> None:
    """Called once at startup by Hermes."""
    registered = _register_tools(ctx)
    logger.info("smartmoney-cub registered %d tools: %s", len(registered), ", ".join(registered))
    _register_skills(ctx)
