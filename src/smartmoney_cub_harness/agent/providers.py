from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

# Model providers for the review assistant.
#
# The company gateway is preconfigured because it is the default internal route.
# A key is read from the environment first and from a local credentials file
# second, and it is never echoed back to the browser or written into a log.

ALPHATECH_PROVIDER_ID = "alphatech"
ALPHATECH_BASE_URL = "https://alphatech.net.cn/v1"

OFFLINE_PROVIDER_ID = "offline"

REQUEST_TIMEOUT_SECONDS = 120
MAX_TOKENS = 2048


class ProviderError(RuntimeError):
    """Raised when a provider request cannot be completed."""


BUILTIN_PROVIDERS: dict[str, dict[str, Any]] = {
    ALPHATECH_PROVIDER_ID: {
        "provider_id": ALPHATECH_PROVIDER_ID,
        "label": "公司中转站 (AlphaTech)",
        "base_url": ALPHATECH_BASE_URL,
        "protocol": "openai-chat",
        "env_key": "ALPHATECH_API_KEY",
        "default_model": "deepseek-v3",
        "requires_key": True,
        "allow_custom_base_url": True,
        "description": "预置的公司中转站，OpenAI 兼容协议。只接收脱敏后的结构化复盘字段。",
    },
    "openai-compatible": {
        "provider_id": "openai-compatible",
        "label": "自定义 OpenAI 兼容端点",
        "base_url": "",
        "protocol": "openai-chat",
        "env_key": "SMCUB_LLM_API_KEY",
        "default_model": "",
        "requires_key": True,
        "allow_custom_base_url": True,
        "description": "任意 OpenAI 兼容服务。地址与密钥只保存在本机。",
    },
    OFFLINE_PROVIDER_ID: {
        "provider_id": OFFLINE_PROVIDER_ID,
        "label": "本地离线复盘（不联网）",
        "base_url": "",
        "protocol": "offline",
        "env_key": "",
        "default_model": "local-template",
        "requires_key": False,
        "allow_custom_base_url": False,
        "description": "使用本地台账与统计生成的模板化复盘，不发出任何网络请求。",
    },
}


def resolve_provider(
    provider_id: str,
    *,
    base_url: str | None = None,
    credentials: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = BUILTIN_PROVIDERS.get(provider_id)
    if spec is None:
        raise ProviderError(f"unknown provider: {provider_id}")
    resolved = dict(spec)
    credentials = credentials or {}
    stored = (credentials.get("providers") or {}).get(provider_id) or {}

    if spec["allow_custom_base_url"] and (base_url or stored.get("base_url")):
        resolved["base_url"] = str(base_url or stored["base_url"]).rstrip("/")
    if not resolved["base_url"] and spec["requires_key"]:
        raise ProviderError(f"provider {provider_id} needs a base_url")

    # Environment first so CI and shell users can supply a key without writing a file.
    env_key = os.environ.get(spec["env_key"] or "", "").strip()
    api_key = env_key or str(stored.get("api_key") or "").strip()
    resolved["api_key"] = api_key
    resolved["has_key"] = bool(api_key)
    resolved["key_source"] = "environment" if env_key else ("local_store" if api_key else "none")
    resolved["default_model"] = stored.get("default_model") or resolved["default_model"]
    resolved["safety"] = SAFETY_DECLARATION
    return resolved


def public_provider_view(
    provider_id: str,
    *,
    credentials: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe a provider without ever returning the key itself."""
    resolved = resolve_provider(provider_id, credentials=credentials)
    return {
        "provider_id": resolved["provider_id"],
        "label": resolved["label"],
        "base_url": resolved["base_url"],
        "protocol": resolved["protocol"],
        "default_model": resolved["default_model"],
        "requires_key": resolved["requires_key"],
        "has_key": resolved["has_key"],
        "key_source": resolved["key_source"],
        "description": resolved["description"],
        "safety": SAFETY_DECLARATION,
    }


# ---- credential file ----------------------------------------------------

CREDENTIALS_NAME = "credentials.json"


def credentials_path(root: str | Path) -> Path:
    return Path(root) / CREDENTIALS_NAME


def load_credentials(root: str | Path) -> dict[str, Any]:
    path = credentials_path(root)
    if not path.is_file():
        return {"providers": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"providers": {}}
    if not isinstance(payload, dict):
        return {"providers": {}}
    payload.setdefault("providers", {})
    return payload


def save_credentials(root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = credentials_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - some filesystems reject chmod
        pass
    providers = {
        key: {
            "base_url": value.get("base_url", ""),
            "default_model": value.get("default_model", ""),
            "has_key": bool(value.get("api_key")),
        }
        for key, value in (payload.get("providers") or {}).items()
    }
    return {
        "status": "ok",
        "providers": providers,
        "note": "secrets stay in the local credentials file and are never returned",
        "safety": SAFETY_DECLARATION,
    }


# ---- transport ----------------------------------------------------------


def build_request_body(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    stream: bool,
) -> bytes:
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "stream": stream,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def _open(
    provider: dict[str, Any],
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    stream: bool,
) -> Any:
    url = provider["base_url"].rstrip("/") + "/chat/completions"
    request = urllib.request.Request(
        url,
        data=build_request_body(model=model, messages=messages, tools=tools, stream=stream),
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "Authorization": "Bearer " + str(provider["api_key"]),
            "User-Agent": "smartmoney-cub-convergence/1.0",
        },
        method="POST",
    )
    try:
        return urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS)
    except urllib.error.HTTPError as error:
        detail = ""
        try:
            detail = error.read().decode("utf-8", errors="replace")[:400]
        except Exception:  # pragma: no cover - the body may already be consumed
            detail = ""
        raise ProviderError(f"provider returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise ProviderError(f"provider is unreachable: {error.reason}") from error


def list_models(provider: dict[str, Any]) -> dict[str, Any]:
    url = provider["base_url"].rstrip("/") + "/models"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + str(provider["api_key"]),
            "User-Agent": "smartmoney-cub-convergence/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise ProviderError(f"could not list models: {error}") from error
    models = [
        entry.get("id")
        for entry in payload.get("data") or []
        if isinstance(entry, dict) and entry.get("id")
    ]
    return {"status": "ok", "models": models, "safety": SAFETY_DECLARATION}


def parse_stream_line(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped or not stripped.startswith("data:"):
        return None
    data = stripped[5:].strip()
    if data == "[DONE]":
        return {"kind": "end"}
    try:
        return {"kind": "chunk", "chunk": json.loads(data)}
    except json.JSONDecodeError:
        return None


def stream_chat(
    provider: dict[str, Any],
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield provider events as dictionaries.

    Event kinds: delta (text), tool_call (a complete call), done.
    """
    response = _open(provider, model=model, messages=messages, tools=tools, stream=True)
    pending: dict[int, dict[str, Any]] = {}
    with response:
        for raw_line in response:
            parsed = parse_stream_line(raw_line.decode("utf-8", errors="replace"))
            if parsed is None:
                continue
            if parsed["kind"] == "end":
                break
            chunk = parsed["chunk"]
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                content = delta.get("content")
                if content:
                    yield {"kind": "delta", "text": content}
                for call in delta.get("tool_calls") or []:
                    index = int(call.get("index") or 0)
                    slot = pending.setdefault(index, {"call_id": "", "name": "", "arguments": ""})
                    if call.get("id"):
                        slot["call_id"] = call["id"]
                    function = call.get("function") or {}
                    if function.get("name"):
                        slot["name"] = function["name"]
                    if function.get("arguments"):
                        slot["arguments"] += function["arguments"]
                finish = choice.get("finish_reason")
                if finish in {"tool_calls", "stop", "length"}:
                    for index in sorted(pending):
                        yield {"kind": "tool_call", "call": dict(pending[index])}
                    pending.clear()
                    yield {"kind": "done", "finish_reason": finish}
                    return
    for index in sorted(pending):
        yield {"kind": "tool_call", "call": dict(pending[index])}
    yield {"kind": "done", "finish_reason": "stop"}

