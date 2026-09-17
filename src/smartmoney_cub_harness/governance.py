"""Local, immutable profile and strategy governance for the review assistant.

The module deliberately uses a small append-only JSON journal instead of adding
another database dependency.  It is local state, never market or execution
state, and every returned object carries the harness safety declaration.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.registry import promotion_blockers
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

PROFILE_STATUSES = ("draft", "current", "superseded")
STRATEGY_STATUSES = (
    "baseline_draft",
    "challenger",
    "evaluating",
    "ready_for_review",
    "champion",
    "retired",
    "stale",
    "rejected",
)
EVALUATION_STATUSES = ("queued", "running", "passed", "failed", "blocked", "cancelled", "stale")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _safe(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    result["safety"] = SAFETY_DECLARATION
    return result


class GovernanceStore:
    """Append-only local profile, strategy, evaluation and promotion store."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "governance.json"
        self._lock = threading.RLock()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema": "smartmoney_cub_governance.v1",
                "profiles": [],
                "strategies": [],
                "evaluations": [],
                "promotions": [],
                "events": [],
            }
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, state: dict[str, Any]) -> None:
        state["safety"] = SAFETY_DECLARATION
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _event(self, state: dict[str, Any], kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = _safe({
            "event_id": _id("EVT"),
            "kind": kind,
            "created_at": _now(),
            "payload": payload,
        })
        state.setdefault("events", []).append(event)
        return event

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return _safe(self._load())

    def profiles(self) -> list[dict[str, Any]]:
        with self._lock:
            return [_safe(item) for item in self._load().get("profiles", [])]

    def current_profile(self) -> dict[str, Any] | None:
        profiles = self.profiles()
        return next((item for item in reversed(profiles) if item.get("status") == "current"), None)

    def create_profile(
        self,
        *,
        facts: dict[str, Any],
        sample_count: int,
        source_snapshot: str,
        generated_by: str = "local_analytics",
        narrative: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            for item in state.get("profiles", []):
                if item.get("status") == "current":
                    item["status"] = "superseded"
            version = len(state.get("profiles", [])) + 1
            profile = {
                "profile_id": _id("PROFILE"),
                "version": version,
                "status": "current",
                "facts": copy.deepcopy(facts),
                "narrative": narrative,
                "sample_count": int(sample_count),
                "source_snapshot": source_snapshot,
                "generated_by": generated_by,
                "created_at": _now(),
            }
            state.setdefault("profiles", []).append(profile)
            self._event(state, "trader_profile_generated", profile)
            self._save(state)
            return _safe(profile)

    def edit_profile(self, profile_id: str, patch: dict[str, Any], *, edited_by: str = "user") -> dict[str, Any]:
        with self._lock:
            state = self._load()
            current = next((p for p in state.get("profiles", []) if p.get("profile_id") == profile_id), None)
            if current is None:
                raise KeyError(profile_id)
            for item in state.get("profiles", []):
                if item.get("status") == "current":
                    item["status"] = "superseded"
            version = len(state.get("profiles", [])) + 1
            edited = copy.deepcopy(current)
            edited.update({"profile_id": _id("PROFILE"), "version": version, "status": "current", "edited_by": edited_by, "created_at": _now()})
            if "facts" in patch:
                edited["facts"] = {**(edited.get("facts") or {}), **copy.deepcopy(patch["facts"])}
            for key in ("narrative", "sample_count", "source_snapshot"):
                if key in patch:
                    edited[key] = patch[key]
            state.setdefault("profiles", []).append(edited)
            stale_ids: list[str] = []
            for strategy in state.get("strategies", []):
                if strategy.get("profile_id") == profile_id and strategy.get("status") not in {"retired", "stale"}:
                    strategy["status"] = "stale"
                    stale_ids.append(strategy["strategy_id"])
            event = self._event(state, "trader_profile_edited", {"profile": edited, "stale_strategy_ids": stale_ids})
            self._save(state)
            return _safe({"profile": edited, "stale_strategy_ids": stale_ids, "event": event})

    def strategies(self) -> list[dict[str, Any]]:
        with self._lock:
            return [_safe(item) for item in self._load().get("strategies", [])]

    def create_strategy(
        self,
        *,
        title: str,
        rules: list[dict[str, Any]],
        profile_id: str | None,
        role: str = "baseline_draft",
        parent_id: str | None = None,
        origin: str = "agent",
        reason: str = "",
        family: str = "general",
    ) -> dict[str, Any]:
        if role not in STRATEGY_STATUSES:
            raise ValueError(f"unsupported strategy status: {role}")
        with self._lock:
            state = self._load()
            strategy = {
                "strategy_id": _id("STRATEGY"),
                "version": len(state.get("strategies", [])) + 1,
                "title": title.strip() or "未命名策略",
                "rules": copy.deepcopy(rules),
                "profile_id": profile_id,
                "parent_id": parent_id,
                "family": family,
                "status": role,
                "origin": origin,
                "reason": reason,
                "created_at": _now(),
            }
            state.setdefault("strategies", []).append(strategy)
            kind = "baseline_strategy_created" if role == "baseline_draft" else "challenger_created"
            self._event(state, kind, strategy)
            self._save(state)
            return _safe(strategy)

    def create_baseline_from_import(
        self,
        *,
        source_snapshot: str,
        sample_count: int,
        facts: dict[str, Any],
        strategy_rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            existing = next((item for item in state.get("strategies", []) if item.get("origin") == "first_import"), None)
            profile = self.current_profile()
            if existing and profile:
                return _safe({"created": False, "profile": profile, "strategy": existing})
        if profile is None:
            profile = self.create_profile(facts=facts, sample_count=sample_count, source_snapshot=source_snapshot)
        strategy = self.create_strategy(
            title="首次导入基线策略",
            rules=strategy_rules or [{"rule": "基于已导入交易提炼可验证的入场、出场和风险约束", "evidence_required": True}],
            profile_id=profile["profile_id"],
            role="baseline_draft",
            origin="first_import",
            reason="首次导入后由本地统计与 Agent 共同初始化；待评估后再决定是否晋级",
        )
        evaluation = self.evaluate(strategy["strategy_id"])
        return _safe({"created": True, "profile": profile, "strategy": strategy, "evaluation": evaluation})

    def evaluate(self, strategy_id: str, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            strategy = next((s for s in state.get("strategies", []) if s.get("strategy_id") == strategy_id), None)
            if strategy is None:
                raise KeyError(strategy_id)
            profile = next((p for p in state.get("profiles", []) if p.get("profile_id") == strategy.get("profile_id")), None)
            resolved = dict(metrics or {})
            if "sample_count" not in resolved:
                resolved["sample_count"] = int((profile or {}).get("sample_count") or 0)
            for key, default in (("false_alert_rate", 0.0), ("missed_opportunity_rate", 0.0), ("future_leakage_count", 0), ("risk_contract_violation_rate", 0.0)):
                resolved.setdefault(key, default)
            blockers = promotion_blockers(resolved)
            evaluation = {
                "evaluation_id": _id("EVAL"),
                "strategy_id": strategy_id,
                "status": "passed" if not blockers else "failed",
                "metrics": resolved,
                "blockers": blockers,
                "dataset_snapshot": (profile or {}).get("source_snapshot"),
                "created_at": _now(),
            }
            # The first-import artifact remains visibly editable as a baseline
            # draft even after its first automatic evaluation. Later Challenger
            # versions move to ready_for_review only when the gates pass.
            if strategy.get("status") != "baseline_draft":
                strategy["status"] = "ready_for_review" if not blockers else "challenger"
            state.setdefault("evaluations", []).append(evaluation)
            self._event(state, "strategy_evaluation_completed", evaluation)
            self._save(state)
            return _safe(evaluation)

    def evaluations(self, strategy_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = self._load().get("evaluations", [])
            if strategy_id:
                items = [item for item in items if item.get("strategy_id") == strategy_id]
            return [_safe(item) for item in items]

    def create_challenger_from_chat(
        self,
        *,
        text: str,
        rules: list[dict[str, Any]],
        family: str = "general",
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not is_explicit_rule_change(text):
            return _safe({"created": False, "reason": "ordinary_discussion"})
        current = next((s for s in self.strategies() if s.get("status") == "champion" and s.get("family") == family), None)
        profile = self.current_profile()
        strategy = self.create_strategy(
            title=f"聊天 Challenger · {family}",
            rules=rules,
            profile_id=(profile or {}).get("profile_id"),
            role="challenger",
            parent_id=(current or {}).get("strategy_id"),
            origin="chat",
            reason=text.strip(),
            family=family,
        )
        evaluation = self.evaluate(strategy["strategy_id"], metrics)
        return _safe({"created": True, "strategy": strategy, "evaluation": evaluation})

    def request_promotion(self, strategy_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._load()
            strategy = next((s for s in state.get("strategies", []) if s.get("strategy_id") == strategy_id), None)
            if strategy is None:
                raise KeyError(strategy_id)
            evaluation = next((e for e in reversed(state.get("evaluations", [])) if e.get("strategy_id") == strategy_id), None)
            if not evaluation or evaluation.get("status") != "passed":
                raise ValueError("strategy is not eligible for promotion")
            request = {
                "promotion_id": _id("PROMO"),
                "strategy_id": strategy_id,
                "status": "pending_confirmation",
                "evaluation_id": evaluation["evaluation_id"],
                "created_at": _now(),
            }
            state.setdefault("promotions", []).append(request)
            self._event(state, "promotion_recommended", request)
            self._save(state)
            return _safe(request)

    def confirm_promotion(self, promotion_id: str, note: str) -> dict[str, Any]:
        if not note.strip():
            raise ValueError("explicit promotion note is required")
        with self._lock:
            state = self._load()
            request = next((r for r in state.get("promotions", []) if r.get("promotion_id") == promotion_id), None)
            if request is None:
                raise KeyError(promotion_id)
            strategy = next(s for s in state.get("strategies", []) if s.get("strategy_id") == request["strategy_id"])
            evaluation = next(e for e in state.get("evaluations", []) if e.get("evaluation_id") == request["evaluation_id"])
            if evaluation.get("status") != "passed":
                raise ValueError("only a passed evaluation can be promoted")
            family = strategy.get("family") or "general"
            for item in state.get("strategies", []):
                if item.get("status") == "champion" and (item.get("family") or "general") == family:
                    item["status"] = "retired"
            strategy["status"] = "champion"
            request.update({"status": "confirmed", "note": note.strip(), "confirmed_at": _now()})
            event = self._event(state, "champion_promoted", {"promotion": request, "strategy": strategy})
            self._save(state)
            return _safe({"promotion": request, "strategy": strategy, "event": event})

    def rollback(self, strategy_id: str, note: str) -> dict[str, Any]:
        if not note.strip():
            raise ValueError("explicit rollback note is required")
        with self._lock:
            state = self._load()
            target = next((s for s in state.get("strategies", []) if s.get("strategy_id") == strategy_id), None)
            if target is None:
                raise KeyError(strategy_id)
            family = target.get("family") or "general"
            for item in state.get("strategies", []):
                if item.get("status") == "champion" and (item.get("family") or "general") == family:
                    item["status"] = "retired"
            target["status"] = "champion"
            event = self._event(state, "champion_rolled_back", {"strategy": target, "note": note.strip()})
            self._save(state)
            return _safe({"strategy": target, "event": event})


def is_explicit_rule_change(text: str) -> bool:
    lowered = text.lower()
    terms = ("生成规则", "新增规则", "修改规则", "采用规则", "形成策略", "创建 challenger", "create challenger", "promote")
    return any(term in lowered for term in terms)


def profile_facts_from_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic cold-start facts; no LLM or market request is involved."""
    symbols = sorted({str(item.get("symbol") or "") for item in trades if item.get("symbol")})
    return {
        "trade_count": len(trades),
        "symbols": symbols[:50],
        "observed_actions": sorted({str(item.get("side") or "") for item in trades if item.get("side")}),
        "data_quality": "partial" if any(not item.get("trade_time") for item in trades) else "ok",
        "facts_only": True,
    }
