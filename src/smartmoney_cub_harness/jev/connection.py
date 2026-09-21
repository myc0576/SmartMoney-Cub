"""Local-only JEV credentials, kept separate from selectable chat providers.

Reading and saving configuration never contacts TypeSafe. The explicit probe
uses a fixed synthetic state, not the trader's journal.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.agent.providers import credentials_path, load_credentials, save_credentials
from smartmoney_cub_harness.local_state import local_state_root
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

CREDENTIAL_ID = "typesafe-jev"
MODEL = "jev-latest"


def credential(root: str | Path | None = None) -> tuple[str, str, bool]:
    entry = (load_credentials(local_state_root(root)).get("providers") or {}).get(CREDENTIAL_ID) or {}
    local_key = entry.get("api_key") if isinstance(entry, dict) else None
    if isinstance(local_key, str) and local_key:
        return local_key, "local", True
    env_key = os.environ.get("TYPESAFE_API_KEY", "")
    return env_key, "environment" if env_key else "none", False


def describe(root: str | Path) -> dict[str, Any]:
    key, source, local = credential(root)
    return {
        "has_key": bool(key), "has_local_key": local, "key_source": source,
        "model": MODEL, "connection_verified": False,
        "safety": SAFETY_DECLARATION,
    }


def save(root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("api_key", "")
    clear = payload.get("clear_key", False)
    if not isinstance(raw, str) or not isinstance(clear, bool):
        raise ValueError("密钥必须是文本，清除选项必须是布尔值。")
    if clear and raw:
        raise ValueError("请分别执行保存密钥和清除本地密钥。")
    if raw:
        key = raw.strip()
        if not key or not re.fullmatch(r"[!-~]+", key) or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", key):
            raise ValueError("密钥格式无效：请只粘贴密钥本身，不要包含空白、非 ASCII 字符或环境变量赋值。")
    elif not clear:
        return describe(root)  # Blank is keep, never delete.
    else:
        key = ""
    # Do not overwrite a corrupt credential file and silently lose other keys.
    path = credentials_path(root)
    if path.exists():
        import json
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as error:
            raise ValueError("本地凭据文件无法读取；未修改任何密钥。") from error
        if not isinstance(existing, dict) or not isinstance(existing.get("providers", {}), dict):
            raise ValueError("本地凭据文件格式无效；未修改任何密钥。")
    values = load_credentials(root)
    providers = values.setdefault("providers", {})
    if clear:
        providers.pop(CREDENTIAL_ID, None)
    else:
        providers[CREDENTIAL_ID] = {"api_key": key}
    save_credentials(root, values)
    return describe(root)


def probe(root: str | Path) -> dict[str, Any]:
    from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend
    from smartmoney_cub_harness.jev.questions import JevQuestion

    view = describe(root)
    if not view["has_key"]:
        return {**view, "error": "请先保存 JEV 密钥，或配置启动环境凭据。"}
    try:
        result = TypeSafeDirectJevBackend(credentials_root=root, timeout_seconds=10, max_attempts=1).evaluate(
            {"connection_test": True},
            (JevQuestion("connection_test", "noul", "Does the state indicate a connection test?"),),
            decision_time=datetime.now(timezone.utc).isoformat(),
        )
    except Exception:
        # Provider exception text can contain headers or echoed secrets. Neither
        # it nor the raw upstream response belongs in the browser or logs.
        return {**view, "error": "连接测试失败：请检查密钥、额度和网络后重试。"}
    return {**view, "connection_verified": True, "model_resolved": result.model_resolved}
