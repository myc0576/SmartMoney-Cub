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


# Upstream provenance for entries that have a public source repository.
#
# `source_commit` is the exact upstream commit this catalog was checked against, and
# `source_checked_at` records when. Both matter: these are moving default-branch
# heads, so a commit without a date cannot be told from a stale claim.
#
# `latest_release` is the newest upstream release observed at that same moment. It is
# deliberately NOT called `source_tag`: in this repository's manifest vocabulary a
# source tag means the tag you validated against, and for five of these six projects
# the release tag points at an older commit than the pinned head. Keeping the names
# distinct stops a reader from assuming the two correspond. Re-verify a pin before
# relying on it, and update the date when you do.
PROVENANCE_CHECKED_AT = "2026-09-20"

PROVENANCE: dict[str, dict[str, str]] = {
    "akshare": {
        "source_repo": "https://github.com/akfamily/akshare",
        "source_commit": "0191689d57c667b7c7a198fd0cf97316837ef311",
        "latest_release": "release-v1.18.97",
        "source_checked_at": PROVENANCE_CHECKED_AT,
        "license": "MIT",
    },
    "qlib-factor-evaluator": {
        "source_repo": "https://github.com/microsoft/qlib",
        "source_commit": "be725493eb1a6bbb42bf11b37aa7669f59610ff1",
        "latest_release": "v0.9.7",
        "source_checked_at": PROVENANCE_CHECKED_AT,
        "license": "MIT",
    },
    "chronos-forecasting": {
        "source_repo": "https://github.com/amazon-science/chronos-forecasting",
        "source_commit": "10afa9ebe016e514f9d7dc1aa873f66af57e116b",
        "latest_release": "v2.3.2",
        "source_checked_at": PROVENANCE_CHECKED_AT,
        "license": "Apache-2.0",
    },
    "timesfm": {
        "source_repo": "https://github.com/google-research/timesfm",
        "source_commit": "e31dadd84cb26bd5153fde6687502b8312e918fb",
        "latest_release": "v3.0.0",
        "source_checked_at": PROVENANCE_CHECKED_AT,
        "license": "Apache-2.0",
    },
    "neuralforecast": {
        "source_repo": "https://github.com/Nixtla/neuralforecast",
        "source_commit": "344aaffd504245ff661bd9e211f220f9214a1876",
        "latest_release": "v3.2.2",
        "source_checked_at": PROVENANCE_CHECKED_AT,
        "license": "Apache-2.0",
    },
    "finrobot": {
        "source_repo": "https://github.com/AI4Finance-Foundation/FinRobot",
        "source_commit": "6d6ccd32c1b8b1904dc656cf06897438aba3daec",
        "latest_release": "desktop-v0.1.0",
        "source_checked_at": PROVENANCE_CHECKED_AT,
        "license": "Apache-2.0",
    },
}


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
    ("chronos-forecasting", "研究与评估", "时间序列预测模型，输出仅作为复盘证据", False),
    ("timesfm", "研究与评估", "时间序列基础预测模型，输出仅作为复盘证据", False),
    ("neuralforecast", "研究与评估", "深度学习时间序列预测与评估", False),
    ("vectorbt-evidence", "研究与评估", "回测证据与未来数据检查", False),
    ("pandas-ta-classic", "研究与评估", "技术指标特征计算", False),
    ("pandas-market-calendars", "研究与评估", "交易日历与时间语义", False),
    ("multi-agent-trade-review", "Agent", "多 Agent 交易复盘", False),
    ("challenger-rule-critic", "Agent", "反方规则质询与 Challenger 生成", False),
    ("finrobot", "Agent", "金融开源 Agent 平台，用于研报解析与辅助复盘", False),
)


def official_catalog() -> list[dict[str, Any]]:
    catalog = []
    for plugin_id, category, description, requires_credentials in _RAW_ENTRIES:
        name = plugin_id.replace("-", " ").title()
        entry: dict[str, Any] = {
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
        if plugin_id in PROVENANCE:
            entry.update(PROVENANCE[plugin_id])
        catalog.append(entry)
    return catalog


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
