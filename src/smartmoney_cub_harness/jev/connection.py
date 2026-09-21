"""Optional, local JEV connection. Reading/saving settings never contacts TypeSafe."""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend
from smartmoney_cub_harness.jev.errors import JevProtocolError
from smartmoney_cub_harness.jev.questions import JevQuestion
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

CREDENTIALS_NAME = "jev.credentials.json"
MODEL = "jev-latest"


def _validate_key(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("密钥必须是文本。")
    key = value.strip()
    if not key or len(key) > 4096 or not re.fullmatch(r"[!-~]+", key):
        raise ValueError("请输入有效密钥；不能包含空白、换行或非 ASCII 字符。")
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", key):
        raise ValueError("请只填写密钥，不要粘贴 NAME=value 环境变量。")
    return key


def _keys(root: str | Path) -> tuple[str, str]:
    path = Path(root) / CREDENTIALS_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError):
        raise ValueError("无法读取本机 JEV 凭据文件，请检查文件权限或内容。") from None
    if not isinstance(data, dict):
        raise ValueError("本机 JEV 凭据格式无效。")
    local = _validate_key(data["api_key"]) if data.get("api_key") else ""
    environment = os.environ.get("TYPESAFE_API_KEY", "").strip()
    return local, environment


def connection_settings(root: str | Path) -> dict[str, Any]:
    local, environment = _keys(root)
    return {
        "has_key": bool(local or environment), "has_local_key": bool(local),
        "key_source": "local" if local else "environment" if environment else "none",
        "model_requested": MODEL, "safety": SAFETY_DECLARATION,
    }


def save_connection(root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) - {"api_key", "clear_key"}:
        raise ValueError("JEV 连接只接受 api_key 和 clear_key。")
    clear = payload.get("clear_key", False)
    if not isinstance(clear, bool):
        raise ValueError("clear_key 必须是布尔值。")
    raw = payload.get("api_key", "")
    if not isinstance(raw, str):
        raise ValueError("密钥必须是文本。")
    if clear and raw:
        raise ValueError("不能同时清除和替换密钥。")
    path = Path(root) / CREDENTIALS_NAME
    if clear:
        path.unlink(missing_ok=True)
    elif raw != "":
        key = _validate_key(raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Separate from chat credentials: no read-modify-write race with model
        # settings. mkstemp creates mode 0600 before any secret bytes are written.
        fd, name = tempfile.mkstemp(prefix=".jev-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"api_key": key}, handle)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
    return connection_settings(root)


def configured_backend(root: str | Path, **kwargs: Any) -> TypeSafeDirectJevBackend:
    local, environment = _keys(root)
    key = _validate_key(local or environment) if local or environment else ""
    return TypeSafeDirectJevBackend(api_key=key, model_requested=MODEL, **kwargs)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward an Authorization header to a redirected host.
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


def _probe_request(req: urllib.request.Request) -> dict[str, Any]:
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(req, timeout=12) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise JevProtocolError("oversized probe response")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise JevProtocolError("invalid probe response")
    model = data.get("model")
    answer = (data.get("answers") or {}).get("connection_test", {})
    value = answer.get("noul")
    if (not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,100}", model)
            or answer.get("type") != "noul" or isinstance(value, bool)
            or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1):
        raise JevProtocolError("invalid typed probe response")
    return data


def probe_connection(root: str | Path) -> dict[str, Any]:
    """Explicit, potentially billable probe using no journal or chat content."""
    checked_at = datetime.now(timezone.utc).isoformat()
    result = {"connected": False, "checked_at": checked_at, "safety": SAFETY_DECLARATION}
    try:
        backend = configured_backend(root, http_client=_probe_request, timeout_seconds=12)
        if not backend.api_key:
            return {**result, "error": "请先保存 JEV 密钥。"}
        decision = backend.evaluate(
            {"connection_test": True},
            (JevQuestion("connection_test", "noul", "Is connection_test true?"),),
            decision_time=checked_at,
        )
        resolved = decision.model_resolved
        if backend.api_key in str(resolved):
            raise JevProtocolError("unexpected probe model")
        return {**result, "connected": True, "model_resolved": resolved}
    except Exception as error:
        # Upstream error text/response bodies can echo credentials. Return only
        # bounded status information, never exception text or request headers.
        cause = error.__cause__ or error
        code = cause.code if isinstance(cause, urllib.error.HTTPError) else None
        message = {
            401: "JEV 鉴权失败，请检查密钥。", 403: "JEV 拒绝访问，请检查密钥权限。",
            429: "JEV 请求频率受限，请稍后重试。",
        }.get(code, "JEV 连接测试未通过，请检查网络、密钥或服务状态。")
        return {**result, "error": message}
