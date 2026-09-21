from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from smartmoney_cub_harness.plugins.types import CapabilityName
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

PLUGIN_CATALOG_SCHEMA = "smartmoney_cub_plugin_catalog.v1"

# Integration levels. A project is never promoted to a higher level just by
# appearing in this catalog.
LEVEL_COMPANION = "companion"
LEVEL_ADAPTER = "adapter"
LEVEL_RUNTIME_PLUGIN = "runtime-plugin"

LEVELS = (LEVEL_COMPANION, LEVEL_ADAPTER, LEVEL_RUNTIME_PLUGIN)


@dataclass
class CatalogEntry:
    """One curated external project and the boundary it must stay inside."""

    project: str
    repo: str
    level: str
    capabilities: list[str] = field(default_factory=list)
    license: str = "unverified"
    maintained: str = "unverified"
    boundary: str = ""
    network_required: bool = False
    execution_risk: str = "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "repo": self.repo,
            "level": self.level,
            "capabilities": list(self.capabilities),
            "license": self.license,
            "maintained": self.maintained,
            "boundary": self.boundary,
            "network_required": self.network_required,
            "execution_risk": self.execution_risk,
            "safety": SAFETY_DECLARATION,
        }


def _entry(
    project: str,
    repo: str,
    level: str,
    capabilities: list[str],
    *,
    license_name: str = "unverified",
    maintained: str = "unverified",
    boundary: str = "",
    network_required: bool = False,
    execution_risk: str = "low",
) -> CatalogEntry:
    return CatalogEntry(
        project=project,
        repo=repo,
        level=level,
        capabilities=capabilities,
        license=license_name,
        maintained=maintained,
        boundary=boundary,
        network_required=network_required,
        execution_risk=execution_risk,
    )


CATALOG_ENTRIES: tuple[CatalogEntry, ...] = (
    _entry(
        "TauricResearch/TradingAgents",
        "https://github.com/TauricResearch/TradingAgents",
        LEVEL_ADAPTER,
        [CapabilityName.REVIEWER, CapabilityName.CHALLENGER, CapabilityName.AGENT_BRIDGE],
        license_name="Apache-2.0 (verify upstream)",
        maintained="active",
        boundary=(
            "External LLM multi-agent analysis. Output may only become review evidence or a "
            "challenger candidate; never order intent, broker action, or automatic promotion."
        ),
        network_required=True,
        execution_risk="medium",
    ),
    _entry(
        "akfamily/akshare",
        "https://github.com/akfamily/akshare",
        LEVEL_ADAPTER,
        [CapabilityName.MARKET_CONTEXT, CapabilityName.TRADE_IMPORT],
        license_name="MIT",
        maintained="active",
        boundary=(
            "Network data source. Must record source, fetch_at, available_at, and quality, and "
            "must stay disabled until the user opts in. Evidence layer only."
        ),
        network_required=True,
        execution_risk="low",
    ),
    _entry(
        "ranaroussi/quantstats",
        "https://github.com/ranaroussi/quantstats",
        LEVEL_ADAPTER,
        [CapabilityName.REPORT_RENDERER, CapabilityName.EVALUATOR],
        license_name="Apache-2.0 (verify upstream)",
        maintained="active",
        boundary=(
            "Performance statistics and report rendering. Must show sample size, filters, "
            "missing data, and statistical limits. Never produces a strategy conclusion."
        ),
        execution_risk="low",
    ),
    _entry(
        "polakowo/vectorbt",
        "https://github.com/polakowo/vectorbt",
        LEVEL_ADAPTER,
        [CapabilityName.EVALUATOR, CapabilityName.REPLAY],
        license_name="Apache-2.0 (verify upstream)",
        maintained="active",
        boundary=(
            "Backtest evaluation. Requires point-in-time data and complete provenance, and a "
            "future-data check. Must never expose an execution interface."
        ),
        execution_risk="medium",
    ),
    _entry(
        "kernc/backtesting.py",
        "https://github.com/kernc/backtesting.py",
        LEVEL_ADAPTER,
        [CapabilityName.EVALUATOR, CapabilityName.REPLAY],
        license_name="AGPL-3.0 (verify upstream)",
        maintained="active",
        boundary=(
            "Lightweight replay and evaluation. Report-only import; must not become a trading "
            "execution surface. AGPL obligations must be reviewed before runtime integration."
        ),
        execution_risk="medium",
    ),
    _entry(
        "microsoft/qlib",
        "https://github.com/microsoft/qlib",
        LEVEL_COMPANION,
        [CapabilityName.EVALUATOR],
        license_name="MIT",
        maintained="active",
        boundary=(
            "Offline research and model evaluation. Must run isolated with its own data "
            "directory; model leakage and future data must be checked before any adapter."
        ),
        execution_risk="medium",
    ),
    _entry(
        "mementum/backtrader",
        "https://github.com/mementum/backtrader",
        LEVEL_COMPANION,
        [CapabilityName.EVALUATOR],
        license_name="GPL-3.0 (verify upstream)",
        maintained="maintenance",
        boundary=(
            "Isolated offline backtest only. Results must be imported as a report. GPL "
            "obligations require review before any bundled runtime integration."
        ),
        execution_risk="medium",
    ),
    _entry(
        "vnpy/vnpy",
        "https://github.com/vnpy/vnpy",
        LEVEL_COMPANION,
        [],
        license_name="MIT",
        maintained="active",
        boundary=(
            "Contains gateway and execution capabilities. Only external reports or backtest "
            "outputs may be imported. Gateway, account, and order modules must never be wired in."
        ),
        execution_risk="high",
    ),
    _entry(
        "zvtvz/zvt",
        "https://github.com/zvtvz/zvt",
        LEVEL_COMPANION,
        [CapabilityName.MARKET_CONTEXT],
        license_name="MIT (verify upstream)",
        maintained="unverified",
        boundary=(
            "Data, factor, and analysis candidates. License, maintenance status, and data time "
            "semantics must be verified before any adapter is published."
        ),
        execution_risk="medium",
    ),
    _entry(
        "shy3130/tick-stock-panel",
        "https://github.com/shy3130/tick-stock-panel",
        LEVEL_COMPANION,
        [CapabilityName.MARKET_CONTEXT],
        license_name="unverified",
        maintained="unverified",
        boundary=(
            "A-share self-hosted screening and monitoring. Report import only; its screening "
            "output must never be presented as a buy signal inside the harness."
        ),
        execution_risk="medium",
    ),
    _entry(
        "wbh604/UZI-Skill",
        "https://github.com/wbh604/UZI-Skill",
        LEVEL_COMPANION,
        [CapabilityName.REVIEWER],
        license_name="unverified",
        maintained="unverified",
        boundary=(
            "External analysis skill and narrative inspiration. Must be described as a "
            "recommended companion, never as an embedded dependency."
        ),
        execution_risk="low",
    ),
    _entry(
        "typesafe-ai/skills",
        "https://github.com/typesafe-ai/skills",
        LEVEL_COMPANION,
        [CapabilityName.REVIEWER, CapabilityName.CHALLENGER],
        license_name="MIT",
        maintained="active",
        boundary=(
            "Read-only prompt and skill asset. Output may only become review evidence or a "
            "challenger candidate; never order intent, broker action, or automatic champion promotion. "
            "TYPESAFE_API_KEY is name-declared with the value staying in the user environment."
        ),
        network_required=True,
        execution_risk="low",
    ),
)


def catalog_payload() -> dict[str, Any]:
    """Return the curated catalog, grouped by integration level."""
    by_level: dict[str, list[dict[str, Any]]] = {level: [] for level in LEVELS}
    for entry in CATALOG_ENTRIES:
        by_level.setdefault(entry.level, []).append(entry.to_dict())
    return {
        "schema": PLUGIN_CATALOG_SCHEMA,
        "levels": list(LEVELS),
        "entries": [entry.to_dict() for entry in CATALOG_ENTRIES],
        "by_level": by_level,
        "counts": {level: len(items) for level, items in by_level.items()},
        "policy": (
            "Catalog listing is documentation only. Nothing here is installed, downloaded, or "
            "executed automatically. Installation is always a user-initiated action."
        ),
        "safety": SAFETY_DECLARATION,
    }
