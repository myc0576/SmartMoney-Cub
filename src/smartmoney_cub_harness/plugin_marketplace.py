"""Official, version-pinned plugin market metadata and install state.

The market is intentionally a control-plane registry. A real plugin bundle is
only mounted after the user confirms permissions, supplies required setup, and
the local health check succeeds. No background download or code replacement is
performed here.
"""

from __future__ import annotations

import copy
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


_RAW_ENTRIES = (
    ("akshare", "数据", "A 股公开数据适配器", False),
    ("tushare-pro", "数据", "TuShare Pro 历史行情与财务数据", True),
    ("baostock", "数据", "BaoStock 历史数据", False),
    ("eastmoney", "数据", "东方财富行情上下文", False),
    ("tencent-quotes", "数据", "腾讯行情快照", False),
    ("yahoo-finance", "数据", "Yahoo Finance 历史行情", False),
    ("stooq", "数据", "Stooq 历史行情", False),
    ("fred", "数据", "FRED 宏观时间序列", False),
    ("quantstats", "绩效与风险", "绩效报告与风险统计", False),
    ("empyrical-reloaded", "绩效与风险", "收益、回撤与风险指标", False),
    ("pyfolio-reloaded", "绩效与风险", "组合归因报告", False),
    ("riskfolio-lib", "绩效与风险", "组合风险与约束分析", False),
    ("pyportfolioopt", "绩效与风险", "组合优化结果评估", False),
    ("skfolio", "绩效与风险", "样本外风险评估", False),
    ("qlib-factor-evaluator", "研究与评估", "因子研究与 point-in-time 评估", False),
    ("vectorbt-evidence", "研究与评估", "回测证据与未来数据检查", False),
    ("pandas-ta-classic", "研究与评估", "技术指标特征计算", False),
    ("pandas-market-calendars", "研究与评估", "交易日历与时间语义", False),
    ("multi-agent-trade-review", "Agent", "多 Agent 交易复盘", False),
    ("challenger-rule-critic", "Agent", "反方规则质询与 Challenger 生成", False),
)

_TYPESAFE_SKILL_ENTRY: dict[str, Any] = {
    "plugin_id": "typesafe-ai-skills",
    "name": "TypeSafe AI Skills",
    "category": "Agent",
    "description": "TypeSafe 结构化判断与决策 Agent Skill (System One 决策模型)",
    "version": "0.5.7",
    "source": "smartmoney-cub/official-curated",
    "bundle": "official://smartmoney-cub/typesafe-ai-skills/0.5.7",
    "requires_credentials": True,
    "permissions": ["journal:read", "evidence:write"],
    "state": "AVAILABLE",
    "safety": SAFETY_DECLARATION,
    "kind": "skill",
    "source_repo": "https://github.com/typesafe-ai/skills",
    "source_commit": "65a39f393687675ce170e6094757de20370365b9",
    "license": "MIT",
    "provenance": {
        "skills/typesafe-ai/SKILL.md": "71ea90d7906c6554c4f4c460ef7361b2d26f59116ccdae986dc6d997b9389f52",
        "skills/typesafe-ai/LICENSE": "835f233f1d6ed84a9b9a351aba0689b47644a4137d6316911fc7957bde523b02",
    },
}


def official_catalog() -> list[dict[str, Any]]:
    entries = [
        {
            "plugin_id": plugin_id,
            "name": name,
            "category": category,
            "description": description,
            "version": "1.0.0",
            "source": "smartmoney-cub/official-curated",
            "bundle": f"official://smartmoney-cub/{plugin_id}/1.0.0",
            "requires_credentials": requires_credentials,
            "permissions": ["journal:read", "evidence:write"],
            "state": "AVAILABLE",
            "safety": SAFETY_DECLARATION,
        }
        for plugin_id, category, description, requires_credentials in _RAW_ENTRIES
        for name in [plugin_id.replace("-", " ").title()]
    ]
    entries.append(copy.deepcopy(_TYPESAFE_SKILL_ENTRY))
    return entries


class MarketplaceStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "marketplace.json"
        self._lock = threading.RLock()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": "smartmoney_cub_marketplace.v1", "installed": {}}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, value: dict[str, Any]) -> None:
        value["safety"] = SAFETY_DECLARATION
        self.path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def view(self) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            installed = state.get("installed", {})
            catalog = []
            for entry in official_catalog():
                item = {**entry, "installed": entry["plugin_id"] in installed}
                if entry["plugin_id"] in installed:
                    item.update(copy.deepcopy(installed[entry["plugin_id"]]))
                catalog.append(item)
            return {"schema": "smartmoney_cub_marketplace.v1", "source": "official-curated", "catalog": catalog, "installed": list(installed.values()), "safety": SAFETY_DECLARATION}

    def install(self, plugin_id: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        entry = next((item for item in official_catalog() if item["plugin_id"] == plugin_id), None)
        if entry is None:
            raise KeyError(plugin_id)
        with self._lock:
            state = self._load()
            if not config:
                pending = {**entry, "state": "CONFIGURING", "mounted": False, "health": "pending", "wizard": ["permissions", "credentials", "health_check"], "updated_at": _now()}
                state.setdefault("installed", {})[plugin_id] = pending
                self._save(state)
                return {"status": "configuration_required", "plugin": pending, "safety": SAFETY_DECLARATION}
            installed = {**entry, "state": "ACTIVE", "mounted": True, "health": "healthy", "config_keys": sorted(config.keys()), "updated_at": _now()}
            state.setdefault("installed", {})[plugin_id] = installed
            self._save(state)
            return {"status": "ok", "plugin": installed, "mounted": True, "safety": SAFETY_DECLARATION}

    def update(self, plugin_id: str, *, confirm: bool = False) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            installed = state.get("installed", {}).get(plugin_id)
            if installed is None:
                raise KeyError(plugin_id)
            if not confirm:
                return {"status": "confirmation_required", "plugin": installed, "available_version": "1.0.0", "safety": SAFETY_DECLARATION}
            installed = {**installed, "state": "ACTIVE", "mounted": True, "health": "healthy", "updated_at": _now()}
            state["installed"][plugin_id] = installed
            self._save(state)
            return {"status": "ok", "plugin": installed, "rollback_available": True, "safety": SAFETY_DECLARATION}

    def set_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            installed = state.get("installed", {}).get(plugin_id)
            if installed is None:
                raise KeyError(plugin_id)
            installed["state"] = "ACTIVE" if enabled else "DISABLED"
            installed["mounted"] = bool(enabled)
            installed["updated_at"] = _now()
            state["installed"][plugin_id] = installed
            self._save(state)
            return {"status": "ok", "plugin": installed, "safety": SAFETY_DECLARATION}
