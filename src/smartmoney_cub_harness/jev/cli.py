from __future__ import annotations

import argparse
from typing import Any

from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend
from smartmoney_cub_harness.jev.openrouter import OpenRouterJevBackend
from smartmoney_cub_harness.jev.questions import available_tracks
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def run_jev_doctor() -> dict[str, Any]:
    """Inspect Jev backend availability, supported tracks, and safety declarations."""
    direct_backend = TypeSafeDirectJevBackend()
    openrouter_backend = OpenRouterJevBackend()

    return {
        "status": "ok",
        "engine": "jev",
        "package": "smartmoney-cub-harness",
        "safety": SAFETY_DECLARATION,
        "tracks": list(available_tracks()),
        "backends": {
            "typesafe-direct": direct_backend.health(),
            "openrouter-jev": openrouter_backend.health(),
        },
        "network_required": False,
        "execution_integrations": "disabled",
    }


def register_jev_commands(sub: Any) -> argparse.ArgumentParser:
    """Register Jev subcommands under 'smcub jev'."""
    jev_parser = sub.add_parser(
        "jev",
        help="Jev reasoning engine diagnostic and review tools",
    )
    jev_sub = jev_parser.add_subparsers(dest="jev_command", required=True)

    doctor_cmd = jev_sub.add_parser(
        "doctor",
        help="Check Jev engine availability, tracks, and safety declaration",
    )
    doctor_cmd.set_defaults(jev_command="doctor")

    return jev_parser
