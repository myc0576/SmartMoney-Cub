from __future__ import annotations

import json
import re
import os
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.agent.provider_errors import (
    ClassifiedProviderError,
    FailurePhase,
    ProviderError,
    ProviderErrorCode,
    classify_provider_error,
)

# Model providers for the review assistant.
#
# The shape follows the harness model-routing convention: a provider catalog you
# install from, one protocol per provider, an explicit model list per provider,
# and a reasoning effort chosen per model. Non-secret configuration lives in
# providers.json and secrets live in credentials.json; the browser only ever
# receives a descriptor, never a key.

ALPHATECH_PROVIDER_ID = "alphatech"
ALPHATECH_BASE_URL = "https://alphatech.net.cn/v1"
COMMANDCODE_PROVIDER_ID = "commandcode-api"
COMMANDCODE_BASE_URL = "http://127.0.0.1:10100/v1"
OFFLINE_PROVIDER_ID = "offline"

REQUEST_TIMEOUT_SECONDS = 120
MAX_TOKENS = 2048
DISCOVERY_TIMEOUT_SECONDS = 30

# The field names an OpenAI-compatible endpoint has been observed to use for the
# private reasoning stream. DeepSeek and the gateways that proxy it send
# ``reasoning_content``; the single-entry list is kept explicit so a new alias is
# an intentional, reviewed addition rather than a wildcard match that could pick
# up unrelated fields. The name that arrived is the name that must be sent back.
REASONING_ALIASES: tuple[str, ...] = ("reasoning_content",)


def iso_now() -> str:
    """UTC timestamp for a model check. UTC because it is compared, not read."""
    return datetime.now(timezone.utc).isoformat()

PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,39}$")


# Every protocol a provider can speak. A provider speaks exactly one, so a
# gateway that answers two protocols is configured twice.
PROVIDER_PROTOCOLS: dict[str, str] = {
    "openai-chat": "OpenAI Chat Completions",
    "openai-responses": "OpenAI Responses",
    "anthropic-messages": "Anthropic Messages",
}

# Reasoning levels, ordered from least to most effort. A model advertises the
# subset it accepts; the selector only offers that subset.
#
# Learning from DSH: the level is a wire value, not a user-facing name. Shipping
# the raw enum ("xhigh") makes the selector unreadable, and shipping a bare name
# with no explanation leaves the user guessing what the extra effort costs, so
# every level carries both a label and a one-line description.
REASONING_LEVELS: tuple[str, ...] = ("off", "low", "medium", "high", "xhigh", "max", "ultra")

EFFORT_DETAILS: dict[str, dict[str, str]] = {
    "off": {"label": "不思考", "description": "直接作答，最快也最省。"},
    "minimal": {"label": "极简", "description": "极少量的内部推理。"},
    "low": {"label": "低", "description": "轻量推理，适合结构化的台账查询。"},
    "medium": {"label": "中", "description": "均衡，日常复盘够用。"},
    "high": {"label": "高", "description": "深入推理，适合多步归因。"},
    "xhigh": {"label": "很高", "description": "更长的推理链，明显更慢。"},
    "max": {"label": "最大", "description": "不计成本的推理，最慢也最容易触发限流。"},
    "ultra": {"label": "极限", "description": "代理路由允许的最高推理强度，速度最慢。"},
}

DEEPSEEK_EFFORTS = ["off", "low", "high", "max"]
OPENAI_EFFORTS = ["off", "low", "medium", "high"]


def effort_details(levels: list[str]) -> list[dict[str, Any]]:
    """Describe each advertised level so the selector never shows a bare enum."""
    rows: list[dict[str, Any]] = []
    for level in levels:
        known = EFFORT_DETAILS.get(level)
        rows.append(
            {
                "level": level,
                "label": (known or {}).get("label") or level,
                "description": (known or {}).get("description") or "",
            }
        )
    return rows


def _model(
    model_id: str,
    label: str = "",
    efforts: list[str] | None = None,
    default_effort: str = "off",
    *,
    context_window: int | None = None,
    max_tokens: int | None = None,
    description: str = "",
    verified: bool = False,
) -> dict[str, Any]:
    levels = list(efforts or [])
    row: dict[str, Any] = {
        "id": model_id,
        "label": label or model_id,
        "reasoning_efforts": levels,
        "default_effort": default_effort,
        "effort_details": effort_details(levels),
    }
    if context_window:
        row["context_window"] = int(context_window)
    if max_tokens:
        row["max_tokens"] = int(max_tokens)
    if description:
        row["description"] = description
    # The verified flag records that this id was confirmed against the live
    # endpoint. An unverified entry is still offered, but the settings page says
    # so rather than presenting a guess as a fact.
    row["verified"] = bool(verified)
    return row


# Providers offered by the catalog. Installing one copies its defaults into the
# local configuration, where every field except the id stays editable.
PROVIDER_CATALOG: dict[str, dict[str, Any]] = {
    ALPHATECH_PROVIDER_ID: {
        "provider_id": ALPHATECH_PROVIDER_ID,
        "label": "AlphaTech API",
        "portal_url": "https://alphatech.net.cn",
        "base_url": ALPHATECH_BASE_URL,
        "protocol": "openai-chat",
        "env_key": "ALPHATECH_API_KEY",
        "requires_key": True,
        "installable": True,
        "removable": False,
        "description": "AlphaTech 商业 API 接口，OpenAI 兼容协议。只接收脱敏后的结构化复盘字段。",
        # These three ids were confirmed against the live /v1/models listing.
        # The previous list named deepseek-v3, deepseek-r1, and deepseek-v4-pro,
        # none of which the endpoint serves: the selector offered three models
        # that could never answer, which is exactly the "not the latest" symptom
        # this list is here to prevent.
        "models": [
            _model(
                "gpt-5.6-luna",
                "GPT-5.6 Luna",
                OPENAI_EFFORTS,
                "medium",
                context_window=922000,
                max_tokens=32768,
                description="快速敏捷的复盘主力模型，支持工具调用与多步反思。",
                verified=True,
            ),
            _model(
                "deepseek-reasoner",
                "DeepSeek Reasoner",
                DEEPSEEK_EFFORTS,
                "high",
                context_window=131072,
                max_tokens=8192,
                description="DeepSeek 推理模型，中转站当前可用的 DeepSeek 主选。",
                verified=True,
            ),
            _model(
                "gpt-5.6-sol",
                "GPT-5.6 Sol",
                OPENAI_EFFORTS,
                "medium",
                context_window=272000,
                max_tokens=32768,
                description="中转站上的通用主力模型，适合多步复盘与长台账。",
                verified=True,
            ),
            _model(
                "claude-opus-5",
                "Claude Opus 5",
                ["off", "low", "medium", "high", "max"],
                "medium",
                context_window=200000,
                max_tokens=32000,
                description="长上下文推理模型，适合跨月归因。",
                verified=True,
            ),
        ],
    },
    "deepseek": {
        "provider_id": "deepseek",
        "label": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com/v1",
        "protocol": "openai-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "requires_key": True,
        "installable": True,
        "removable": True,
        "description": "DeepSeek 官方接口。",
        "models": [
            _model("deepseek-chat", "DeepSeek Chat", DEEPSEEK_EFFORTS, "off"),
            _model("deepseek-reasoner", "DeepSeek Reasoner", DEEPSEEK_EFFORTS, "high"),
        ],
    },
    "openai": {
        "provider_id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "protocol": "openai-responses",
        "env_key": "OPENAI_API_KEY",
        "requires_key": True,
        "installable": True,
        "removable": True,
        "description": "OpenAI 官方接口，使用 Responses 协议。",
        "models": [
            _model("gpt-5.1", "GPT-5.1", OPENAI_EFFORTS, "medium"),
            _model("gpt-5.1-mini", "GPT-5.1 mini", OPENAI_EFFORTS, "low"),
        ],
    },
    "moonshot": {
        "provider_id": "moonshot",
        "label": "Moonshot / Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "protocol": "openai-chat",
        "env_key": "MOONSHOT_API_KEY",
        "requires_key": True,
        "installable": True,
        "removable": True,
        "description": "月之暗面 Kimi 接口。",
        "models": [
            _model("kimi-k2-0905-preview", "Kimi K2"),
            _model("moonshot-v1-128k", "Moonshot 128K"),
        ],
    },
    "zai": {
        "provider_id": "zai",
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "protocol": "openai-chat",
        "env_key": "ZAI_API_KEY",
        "requires_key": True,
        "installable": True,
        "removable": True,
        "description": "智谱 GLM 接口。",
        "models": [_model("glm-4.6", "GLM-4.6"), _model("glm-4.5-air", "GLM-4.5 Air")],
    },
    COMMANDCODE_PROVIDER_ID: {
        "provider_id": COMMANDCODE_PROVIDER_ID,
        "label": "CommandCode API",
        "base_url": COMMANDCODE_BASE_URL,
        "protocol": "openai-chat",
        "env_key": "",
        "requires_key": False,
        "installable": True,
        "removable": True,
        "description": "本机 CommandCode OpenAI 兼容网关。支持 GPT-5.6 Luna 与 DeepSeek V4.1 Flash。",
        "models": [
            _model(
                "gpt-5.6-luna",
                "GPT-5.6 Luna",
                OPENAI_EFFORTS,
                "medium",
                context_window=922000,
                max_tokens=32768,
                description="CommandCode 路由的 GPT-5.6 Luna；敏捷快速，支持多步复盘。",
                verified=True,
            ),
            _model(
                "commandcode/deepseek/deepseek-v4.1-flash",
                "DeepSeek V4.1 Flash",
                ["off", "low", "medium", "high", "xhigh", "max", "ultra"],
                "medium",
                context_window=1000000,
                max_tokens=32768,
                description="CommandCode 路由的 DeepSeek V4.1 Flash；支持长上下文与流式输出。",
                verified=True,
            ),
            _model(
                "gpt-6-astra",
                "GPT-6 Astra",
                OPENAI_EFFORTS,
                "medium",
                context_window=872000,
                max_tokens=32768,
                description="CommandCode 路由的高推理旗舰模型。",
                verified=True,
            ),
            _model(
                "gpt-5.6-sol",
                "GPT-5.6 Sol",
                OPENAI_EFFORTS,
                "low",
                context_window=922000,
                max_tokens=32768,
                description="CommandCode 路由的通用工作马模型。",
                verified=True,
            ),
        ],
    },
    OFFLINE_PROVIDER_ID: {
        "provider_id": OFFLINE_PROVIDER_ID,
        "label": "本地离线复盘（不联网）",
        "base_url": "",
        "protocol": "offline",
        "env_key": "",
        "requires_key": False,
        "installable": False,
        "removable": False,
        "description": "使用本地台账与统计生成的模板化复盘，不发出任何网络请求。",
        "models": [_model("local-template", "本地模板")],
    },
}

# The catalog is also the compatibility surface for callers that predate the
# installable catalog.
BUILTIN_PROVIDERS = PROVIDER_CATALOG

SETTINGS_NAME = "providers.json"
CREDENTIALS_NAME = "credentials.json"

DEFAULT_INSTALLED = (ALPHATECH_PROVIDER_ID, OFFLINE_PROVIDER_ID)


# ---- local configuration ------------------------------------------------


def settings_path(root: str | Path) -> Path:
    return Path(root) / SETTINGS_NAME


def credentials_path(root: str | Path) -> Path:
    return Path(root) / CREDENTIALS_NAME


def default_settings() -> dict[str, Any]:
    return {
        "order": list(DEFAULT_INSTALLED),
        "providers": {
            provider_id: _installed_default(PROVIDER_CATALOG[provider_id])
            for provider_id in DEFAULT_INSTALLED
        },
    }


def _installed_default(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_id": entry["provider_id"],
        "label": entry["label"],
        "portal_url": entry.get("portal_url", ""),
        "base_url": entry["base_url"],
        "protocol": entry["protocol"],
        "env_key": entry["env_key"],
        "description": entry["description"],
        "requires_key": entry["requires_key"],
        "removable": entry.get("removable", True),
        "models": [dict(model) for model in entry["models"]],
        "default_model": entry["models"][0]["id"] if entry["models"] else "",
    }


def load_settings(root: str | Path) -> dict[str, Any]:
    """Read the local provider configuration, falling back to the defaults."""
    path = settings_path(root)
    if not path.is_file():
        return default_settings()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_settings()
    if not isinstance(payload, dict) or not isinstance(payload.get("providers"), dict):
        return default_settings()
    settings = default_settings()
    settings.update({key: value for key, value in payload.items() if key != "providers"})
    order = [pid for pid in payload.get("order", []) if pid in payload["providers"]]
    for provider_id, entry in payload["providers"].items():
        if provider_id not in order:
            order.append(provider_id)
    settings["order"] = order
    settings["providers"] = payload["providers"]
    return settings


def save_settings(root: str | Path, settings: dict[str, Any]) -> dict[str, Any]:
    path = settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "providers_path": path.name, "safety": SAFETY_DECLARATION}


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


# ---- resolution ---------------------------------------------------------


def normalize_provider_id(value: str) -> str:
    candidate = (value or "").strip().lower()
    if not PROVIDER_ID_RE.match(candidate):
        raise ProviderError(
            "provider id must be lowercase letters, digits, or dashes, and must start with a letter"
        )
    return candidate


def provider_entry(provider_id: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve one provider from the local configuration or the catalog."""
    settings = settings or default_settings()
    configured = settings.get("providers", {}).get(provider_id)
    if configured is not None:
        return dict(configured)
    catalog = PROVIDER_CATALOG.get(provider_id)
    if catalog is not None:
        return _installed_default(catalog)
    raise ProviderError("unknown provider: " + provider_id)


def list_provider_ids(settings: dict[str, Any] | None = None) -> list[str]:
    settings = settings or default_settings()
    order = [pid for pid in settings.get("order", []) if pid in settings.get("providers", {})]
    for provider_id in settings.get("providers", {}):
        if provider_id not in order:
            order.append(provider_id)
    return order


def resolve_provider(
    provider_id: str,
    *,
    base_url: str | None = None,
    credentials: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = provider_entry(provider_id, settings)
    credentials = credentials or {}
    stored = (credentials.get("providers") or {}).get(provider_id) or {}
    # Precedence: an explicit argument, then an endpoint the user set for this
    # provider, then the configured default. The stored value is honoured because
    # an earlier layout kept the endpoint beside the key, and a user who set one
    # expects the next request to use it.
    effective_base_url = base_url or stored.get("base_url") or entry.get("base_url") or ""
    resolved = {
        "provider_id": provider_id,
        "label": entry.get("label", provider_id),
        "portal_url": entry.get("portal_url", "") or PROVIDER_CATALOG.get(provider_id, {}).get("portal_url", ""),
        "base_url": effective_base_url.rstrip("/"),
        "protocol": entry.get("protocol", "openai-chat"),
        "env_key": entry.get("env_key", ""),
        "default_model": entry.get("default_model") or "",
        "requires_key": bool(entry.get("requires_key", True)),
        "description": entry.get("description", ""),
        "models": [dict(model) for model in (entry.get("models") or [])],
    }
    if resolved["protocol"] != "offline" and not resolved["base_url"]:
        raise ProviderError("provider " + provider_id + " needs a base_url")

    # Environment first so CI and shell users can supply a key without a file.
    env_key = os.environ.get(resolved["env_key"] or "", "").strip()
    api_key = env_key or str(stored.get("api_key") or "").strip()
    resolved["api_key"] = api_key
    resolved["has_key"] = bool(api_key)
    resolved["key_source"] = "environment" if env_key else ("local_store" if api_key else "none")
    resolved["safety"] = SAFETY_DECLARATION
    return resolved


def public_provider_view(
    provider_id: str,
    *,
    credentials: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe a provider without ever returning the key itself."""
    resolved = resolve_provider(provider_id, credentials=credentials, settings=settings)
    entry = provider_entry(provider_id, settings)

    # The three-state key rule, borrowed from DSH. A green dot claims a key IS
    # configured and a red dot claims a named reference IS missing; anything we
    # cannot decide gets no dot at all. Collapsing "no key" into a red dot would
    # accuse a provider that is merely unconfigured, and collapsing "unknown"
    # into green would promise a working route we have not confirmed.
    if not resolved["requires_key"] or resolved["protocol"] == "offline":
        key_status = "unknown"
    elif resolved["has_key"]:
        key_status = "configured"
    else:
        key_status = "missing"

    # A provider is routable when the assistant could actually send a turn
    # through it: an endpoint (unless offline) plus a usable key.
    routable = (
        resolved["protocol"] == "offline"
        or bool(resolved["base_url"] and (resolved["has_key"] or not resolved["requires_key"]))
    )

    return {
        "provider_id": resolved["provider_id"],
        "label": resolved["label"],
        "portal_url": entry.get("portal_url", "") or PROVIDER_CATALOG.get(provider_id, {}).get("portal_url", ""),
        "base_url": resolved["base_url"],
        "protocol": resolved["protocol"],
        "protocol_label": PROVIDER_PROTOCOLS.get(resolved["protocol"], resolved["protocol"]),
        "default_model": resolved["default_model"],
        "models": resolved["models"],
        "reasoning_efforts": sorted(
            {
                effort
                for model in resolved["models"]
                for effort in (model.get("reasoning_efforts") or [])
            },
            key=REASONING_LEVELS.index,
        ),
        "requires_key": resolved["requires_key"],
        "removable": bool(entry.get("removable", True)),
        "installable": provider_id in PROVIDER_CATALOG and provider_id not in DEFAULT_INSTALLED,
        "has_key": resolved["has_key"],
        "key_source": resolved["key_source"],
        "key_status": key_status,
        "routable": routable,
        # A route we did not ship in the catalog was declared by hand, which is
        # what the 自定义 tag reports.
        "is_custom": provider_id not in PROVIDER_CATALOG,
        "description": resolved["description"],
        "safety": SAFETY_DECLARATION,
    }


def catalog_view(settings: dict[str, Any] | None = None, *, credentials: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """List catalog entries, marking the ones already installed."""
    installed = set(list_provider_ids(settings))
    entries: list[dict[str, Any]] = []
    for provider_id, entry in PROVIDER_CATALOG.items():
        if not entry.get("installable"):
            continue
        entries.append(
            {
                "provider_id": provider_id,
                "label": entry["label"],
                "portal_url": entry.get("portal_url", ""),
                "base_url": entry["base_url"],
                "protocol": entry["protocol"],
                "protocol_label": PROVIDER_PROTOCOLS.get(entry["protocol"], entry["protocol"]),
                "description": entry["description"],
                "installed": provider_id in installed,
                "has_env_key": bool(os.environ.get(entry.get("env_key") or "", "").strip()),
                "models": [dict(model) for model in entry["models"]],
                "safety": SAFETY_DECLARATION,
            }
        )
    return entries


# ---- configuration mutation --------------------------------------------


def install_provider(
    root: str | Path,
    provider_id: str,
    *,
    from_catalog: bool = False,
    label: str = "",
    base_url: str = "",
    protocol: str = "openai-chat",
    api_key: str = "",
    models: list[Any] | None = None,
    display_name: str = "",
) -> dict[str, Any]:
    """Add a provider from the catalog or from an explicit description."""
    provider_id = normalize_provider_id(provider_id)
    settings = load_settings(root)

    if from_catalog:
        entry = PROVIDER_CATALOG.get(provider_id)
        if entry is None:
            raise ProviderError("no catalog entry for " + provider_id)
        configured = _installed_default(entry)
        configured["removable"] = True
    else:
        if protocol not in PROVIDER_PROTOCOLS:
            raise ProviderError(
                "unsupported protocol " + protocol + "; choose one of "
                + ", ".join(sorted(PROVIDER_PROTOCOLS))
            )
        configured = {
            "provider_id": provider_id,
            "label": display_name or label or provider_id,
            "base_url": (base_url or "").strip(),
            "protocol": protocol,
            "env_key": "",
            "description": "自定义 Provider。地址与密钥只保存在本机。",
            "requires_key": True,
            "removable": True,
            "models": [],
            "default_model": "",
        }
        if not configured["base_url"]:
            raise ProviderError("a custom provider needs a base URL")

    existing = settings["providers"].get(provider_id)
    if existing is not None:
        # Re-installing an existing provider refreshes its protocol and endpoint
        # but keeps the models and key the user already added.
        merged = dict(existing)
        for key in ("label", "base_url", "protocol", "description", "requires_key", "removable"):
            merged[key] = configured[key]
        if models is None:
            merged["models"] = existing.get("models") or []
        configured = merged

    if models is not None:
        configured["models"] = _normalize_models(models)
    if not configured.get("default_model") and configured.get("models"):
        configured["default_model"] = configured["models"][0]["id"]

    settings["providers"][provider_id] = configured
    if provider_id not in settings["order"]:
        # A newly added provider joins the other remote providers. The offline
        # entry stays last so a local fallback is always at the end of the list.
        settings["order"] = _move_before_offline(settings["order"], provider_id)
    save_settings(root, settings)

    if api_key.strip():
        _store_key(root, provider_id, api_key.strip())

    return {
        "status": "ok",
        "provider": public_provider_view(
            provider_id, credentials=load_credentials(root), settings=settings
        ),
        "safety": SAFETY_DECLARATION,
    }


def _move_before_offline(order: list[str], provider_id: str) -> list[str]:
    remaining = [pid for pid in order if pid != provider_id]
    if OFFLINE_PROVIDER_ID in remaining:
        index = remaining.index(OFFLINE_PROVIDER_ID)
        remaining.insert(index, provider_id)
        return remaining
    remaining.append(provider_id)
    return remaining


def _normalize_models(models: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in models:
        if isinstance(raw, str):
            model = _model(raw.strip())
        elif isinstance(raw, dict):
            model_id = str(raw.get("id") or "").strip()
            if not model_id:
                continue
            efforts = raw.get("reasoning_efforts")
            if efforts is None:
                efforts = []
            if not isinstance(efforts, list):
                raise ProviderError("reasoning_efforts must be a list for " + model_id)
            unknown = [str(item) for item in efforts if str(item) not in REASONING_LEVELS]
            if unknown:
                raise ProviderError(
                    "unsupported reasoning effort " + ", ".join(unknown)
                    + " for " + model_id + "; choose from " + ", ".join(REASONING_LEVELS)
                )
            default_effort = str(raw.get("default_effort") or (efforts[0] if efforts else "off"))
            if efforts and default_effort not in efforts:
                raise ProviderError(
                    "default_effort " + default_effort + " is not offered by " + model_id
                )
            model = {
                "id": model_id,
                "label": str(raw.get("label") or model_id),
                "reasoning_efforts": [str(item) for item in efforts],
                "default_effort": default_effort,
                "effort_details": effort_details([str(item) for item in efforts]),
            }
            # The richer optional fields are carried through rather than
            # discarded. Dropping them made the settings page a write-only
            # surface: the form sent a context window and the store rebuilt the
            # row without it, so the number silently vanished on every save.
            for key in ("context_window", "max_tokens"):
                value = raw.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if value > 0:
                    model[key] = int(value)
            for key in ("description", "input_modalities"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    model[key] = value.strip()
                elif isinstance(value, list) and value:
                    model[key] = [str(item) for item in value]
            # Staleness is decided by reconciliation, not by the client. A form
            # submission must not be able to claim a model is current, so these
            # two flags survive a round trip but are only ever set from a check.
            if raw.get("stale"):
                model["stale"] = True
            if raw.get("verified"):
                model["verified"] = True
        else:
            continue
        if not model["id"] or model["id"] in seen:
            continue
        seen.add(model["id"])
        normalized.append(model)
    return normalized


def remove_provider(root: str | Path, provider_id: str) -> dict[str, Any]:
    settings = load_settings(root)
    entry = settings["providers"].get(provider_id)
    if entry is None:
        raise ProviderError("provider is not installed: " + provider_id)
    if not entry.get("removable", True):
        raise ProviderError("provider " + provider_id + " cannot be removed")
    settings["providers"].pop(provider_id, None)
    settings["order"] = [pid for pid in settings["order"] if pid != provider_id]
    save_settings(root, settings)

    credentials = load_credentials(root)
    if (credentials.get("providers") or {}).pop(provider_id, None) is not None:
        save_credentials(root, credentials)
    return {"status": "ok", "removed": provider_id, "safety": SAFETY_DECLARATION}


def update_provider(
    root: str | Path,
    provider_id: str,
    *,
    display_name: str | None = None,
    base_url: str | None = None,
    protocol: str | None = None,
    models: list[Any] | None = None,
    default_model: str | None = None,
    api_key: str | None = None,
    clear_key: bool = False,
) -> dict[str, Any]:
    settings = load_settings(root)
    entry = settings["providers"].get(provider_id)
    if entry is None:
        raise ProviderError("provider is not installed: " + provider_id)

    if protocol is not None and protocol != entry.get("protocol"):
        if protocol not in PROVIDER_PROTOCOLS:
            raise ProviderError(
                "unsupported protocol " + protocol + "; choose one of "
                + ", ".join(sorted(PROVIDER_PROTOCOLS))
            )
        entry["protocol"] = protocol
    if display_name is not None and display_name.strip():
        entry["label"] = display_name.strip()
    if base_url is not None:
        entry["base_url"] = base_url.strip()
    if models is not None:
        entry["models"] = _normalize_models(models)
    if default_model is not None:
        known = {model["id"] for model in entry.get("models") or []}
        if default_model and default_model not in known:
            raise ProviderError("default model " + default_model + " is not in the model list")
        entry["default_model"] = default_model
    if not entry.get("default_model") and entry.get("models"):
        entry["default_model"] = entry["models"][0]["id"]

    settings["providers"][provider_id] = entry
    save_settings(root, settings)

    if clear_key or (api_key is not None and api_key.strip()):
        credentials = load_credentials(root)
        providers = credentials.setdefault("providers", {})
        if clear_key:
            providers.pop(provider_id, None)
        else:
            providers.setdefault(provider_id, {})["api_key"] = api_key.strip()
        save_credentials(root, credentials)

    return {
        "status": "ok",
        "provider": public_provider_view(
            provider_id, credentials=load_credentials(root), settings=settings
        ),
        "safety": SAFETY_DECLARATION,
    }


def _store_key(root: str | Path, provider_id: str, api_key: str) -> None:
    credentials = load_credentials(root)
    credentials.setdefault("providers", {}).setdefault(provider_id, {})["api_key"] = api_key
    save_credentials(root, credentials)


# ---- requests -----------------------------------------------------------


def _auth_headers(provider: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "smartmoney-cub-convergence/1.0",
    }
    key = str(provider.get("api_key") or "")
    protocol = provider.get("protocol", "openai-chat")
    if protocol == "anthropic-messages":
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = "Bearer " + key
    return headers


def effort_parameter(model: str, effort: str, provider: dict[str, Any]) -> dict[str, Any]:
    """Translate a named effort into the field this provider understands."""
    if not effort or effort == "off":
        return {}
    if provider.get("protocol") == "anthropic-messages":
        return {"thinking": {"type": "enabled", "budget_tokens": 4096}}
    return {"reasoning_effort": effort}


def build_request_body(
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    stream: bool,
    effort: str = "off",
    provider: dict[str, Any] | None = None,
) -> bytes:
    provider = provider or {"protocol": "openai-chat"}
    body: dict[str, Any] = {
        "model": canonical_model_id(model, provider),
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "stream": stream,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    body.update(effort_parameter(model, effort, provider))
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def canonical_model_id(model: str, provider: dict[str, Any] | None = None) -> str:
    """Normalize the shorthand used in settings to the gateway model id.

    The CommandCode catalog exposes ``commandcode/deepseek/deepseek-v4.1-flash``
    through its OpenAI-compatible proxy. Users often paste the shorter
    ``deepseekv4.1flash`` or ``deepseek-v4.1-flash`` spelling; sending either
    verbatim produces a gateway 404. The alias is scoped to the local
    CommandCode route so another provider's model with the same display name is
    never rewritten.
    """
    raw = str(model or "").strip()
    if not raw:
        return raw
    provider = provider or {}
    is_commandcode = (
        provider.get("provider_id") == COMMANDCODE_PROVIDER_ID
        or provider.get("provider_id") == "commandcode"
        or str(provider.get("base_url") or "").rstrip("/") == COMMANDCODE_BASE_URL
    )
    if not is_commandcode:
        return raw
    aliases = {
        "deepseekv4.1flash": "commandcode/deepseek/deepseek-v4.1-flash",
        "deepseek-v4.1-flash": "commandcode/deepseek/deepseek-v4.1-flash",
        "deepseek/deepseek-v4.1-flash": "commandcode/deepseek/deepseek-v4.1-flash",
        "/deepseekv4.1flash": "commandcode/deepseek/deepseek-v4.1-flash",
        "gpt5.6luna": "gpt-5.6-luna",
        "gpt-5.6luna": "gpt-5.6-luna",
        "gpt56luna": "gpt-5.6-luna",
    }
    return aliases.get(raw.lower(), raw)


def _open(
    provider: dict[str, Any],
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    stream: bool,
    effort: str = "off",
) -> Any:
    url = provider["base_url"].rstrip("/") + "/chat/completions"
    request = urllib.request.Request(
        url,
        data=build_request_body(
            model=model,
            messages=messages,
            tools=tools,
            stream=stream,
            effort=effort,
            provider=provider,
        ),
        headers={
            **_auth_headers(provider),
            "Accept": "text/event-stream" if stream else "application/json",
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
        classified = classify_provider_error(
            error, provider=provider, model=model, phase=FailurePhase.PRE_STREAM, detail=detail
        )
    except urllib.error.URLError as error:
        classified = classify_provider_error(
            error, provider=provider, model=model, phase=FailurePhase.PRE_STREAM
        )
    except (socket.timeout, TimeoutError) as error:
        classified = classify_provider_error(
            error, provider=provider, model=model, phase=FailurePhase.PRE_STREAM
        )
    # Raise after leaving the handler so neither __cause__ nor __context__ keeps
    # the upstream exception, which may contain an echoed credential.
    raise classified


def list_models(provider: dict[str, Any]) -> dict[str, Any]:
    """Ask the endpoint which models it serves.

    Discovery reads the listing shapes common gateways publish. It is a
    convenience: when an endpoint answers in another shape the caller adds the
    model ids by hand and they work the same way.
    """
    url = provider["base_url"].rstrip("/") + "/models"
    request = urllib.request.Request(url, headers=_auth_headers(provider), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=DISCOVERY_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise ProviderError("could not list models: " + str(error)) from error

    identifiers: list[str] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict) and entry.get("id"):
                    identifiers.append(str(entry["id"]))
        models = payload.get("models")
        if isinstance(models, list):
            for entry in models:
                if isinstance(entry, str):
                    identifiers.append(entry)
                elif isinstance(entry, dict):
                    name = entry.get("id") or entry.get("name") or entry.get("model")
                    if name:
                        identifiers.append(str(name))
    if not identifiers:
        raise ProviderError(
            "the endpoint returned neither a data array nor a models list; add model ids by hand"
        )
    if not provider.get("base_url"):
        raise ProviderError("provider needs a base_url before discovery")
    return {
        "status": "ok",
        "models": sorted(dict.fromkeys(identifiers)),
        "safety": SAFETY_DECLARATION,
    }


# Markers that identify a listing the assistant cannot hold a conversation with.
#
# A gateway's /v1/models endpoint is the whole catalog, not the chat subset: the
# company relay answers with 108 ids, of which image, video, music, speech, and
# upscaling models are the majority. Appending those to the selector would bury
# the three usable chat models under sixty unusable ones, which is a worse
# failure than a short list. This filter is deliberately the conservative half
# of the problem: it only drops ids that name an obviously non-conversational
# modality, and anything ambiguous is kept so a real chat model is never hidden.
NON_CHAT_MODEL_MARKERS: tuple[str, ...] = (
    "tts", "whisper", "suno", "music", "audio", "speech", "voice",
    "image", "sd2", "sd-", "sdvip", "sdquan", "quanneng", "by-image",
    "cf-image", "gz-sd", "gz-sd2", "rd2", "sp2", "bh2", "tj-sp", "tj-wan",
    "video", "veo", "sora", "wan3", "hailuo", "minimax-h", "seedance",
    "grok-imagine", "upscale", "去字幕", "embedding", "rerank", "moderation",
)


def is_conversational_model(model_id: str) -> bool:
    """Report whether a discovered id looks like a chat model.

    Used only to decide what a reconciliation may APPEND. A model the user
    declared by hand is never filtered out, because they named it on purpose.
    """
    lowered = str(model_id or "").lower()
    return not any(marker in lowered for marker in NON_CHAT_MODEL_MARKERS)


def reconcile_models(
    provider: dict[str, Any],
    *,
    live_ids: list[str] | None = None,
    error: str = "",
) -> dict[str, Any]:
    """Reconcile a provider's declared model list against what the endpoint serves.

    Why this exists: the catalog is a snapshot of an endpoint that keeps moving,
    so a hardcoded list silently rots and the selector ends up offering models
    that can never answer. Reconciling instead of overwriting is the important
    part - a model that is no longer published is MARKED stale and stays
    selectable, because it may still be a valid alias or a temporary outage, and
    deleting the user's working choice is worse than flagging it.

    Discovered models the catalog never heard of are appended, so a new release
    shows up without a code change. Brand-new rows are marked unverified until a
    later check confirms them, and their effort list is left empty rather than
    guessed: an invented effort level would fail at the endpoint.

    This function performs no I/O. The caller supplies live_ids from
    list_models(), or an error string when discovery failed, and it stays pure
    so the merge rule is testable without a network.
    """
    declared = [dict(model) for model in (provider.get("models") or [])]
    result: dict[str, Any] = {
        "provider_id": provider.get("provider_id", ""),
        "models": declared,
        "checked_at": iso_now(),
        "verified": False,
        "stale_count": 0,
        "added_count": 0,
        "error": error,
    }

    # A failed lookup must not be presented as "these models are gone": we
    # learned nothing, so every row keeps the state it already had.
    if not live_ids:
        result["models"] = [
            {**model, "stale": bool(model.get("stale"))} for model in declared
        ]
        return result

    known = set(live_ids)
    merged: list[dict[str, Any]] = []
    for model in declared:
        model_id = str(model.get("id") or "")
        if model_id in known:
            merged.append({**model, "stale": False, "verified": True})
        else:
            # Kept, but flagged. The picker draws this as 已下架 while leaving it
            # selectable.
            merged.append({**model, "stale": True, "verified": False})

    declared_ids = {str(model.get("id") or "") for model in declared}
    added = 0
    skipped = 0
    for model_id in live_ids:
        if model_id in declared_ids:
            continue
        # A declared model is never filtered: the user named it. A discovered one
        # is appended only when it looks conversational, so the selector does not
        # fill up with image and speech endpoints from the same gateway.
        if not is_conversational_model(model_id):
            skipped += 1
            continue
        merged.append(
            {
                **_model(
                    model_id,
                    model_id,
                    [],
                    "off",
                    description="从端点自动发现，尚未在本机校验其对工具调用的支持。",
                    verified=False,
                ),
                # A freshly discovered id is by definition still published, so
                # it is not stale; it is merely unverified.
                "stale": False,
            }
        )
        added += 1

    result["models"] = merged
    result["verified"] = True
    result["stale_count"] = sum(1 for model in merged if model.get("stale"))
    result["added_count"] = added
    result["skipped_count"] = skipped
    return result


def check_provider_models(
    provider_id: str,
    *,
    credentials: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    live_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Reconcile one provider, looking its models up unless ids were supplied."""
    resolved = resolve_provider(provider_id, credentials=credentials, settings=settings)
    if resolved["protocol"] == "offline":
        return {
            "status": "ok",
            "provider_id": provider_id,
            "models": [dict(model) for model in resolved["models"]],
            "checked_at": iso_now(),
            "verified": True,
            "stale_count": 0,
            "added_count": 0,
            "error": "",
            "safety": SAFETY_DECLARATION,
        }
    discovered: list[str] = list(live_ids or [])
    error = ""
    if not discovered:
        try:
            discovered = list(list_models(resolved)["models"])
        except ProviderError as failure:
            error = str(failure)
    reconciled = reconcile_models(resolved, live_ids=discovered, error=error)
    return {**reconciled, "status": "ok", "safety": SAFETY_DECLARATION}


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
    effort: str = "off",
) -> Iterator[dict[str, Any]]:
    """Yield provider events as dictionaries.

    Event kinds: delta (visible text), reasoning (private thinking text),
    tool_call (a complete call), done.

    A thinking model streams its private reasoning beside the answer, and the
    provider rejects the NEXT round with HTTP 400 when that text is dropped:
    "The reasoning_content in the thinking mode must be passed back to the API".
    So the field is forwarded verbatim under the event's ``text``. Only field
    names the provider actually used are read, and the event is emitted only
    when the field was present: inventing an empty reasoning field would make
    the request shape wrong for the models that never emit one.
    """
    if provider.get("protocol") == "offline" or provider.get("provider_id") == OFFLINE_PROVIDER_ID:
        yield {"kind": "delta", "text": "【本地离线复盘】使用本地确定性启发式规则评估交易执行偏差与风控表现。"}
        yield {"kind": "done", "finish_reason": "stop"}
        return

    opening_failure: ClassifiedProviderError | None = None
    try:
        response = _open(
            provider, model=model, messages=messages, tools=tools, stream=True, effort=effort
        )
    except ClassifiedProviderError:
        raise
    except Exception as error:
        opening_failure = classify_provider_error(
            error, provider=provider, model=model, phase=FailurePhase.PRE_STREAM
        )
    if opening_failure is not None:
        raise opening_failure
    pending: dict[int, dict[str, Any]] = {}
    emitted_any = False
    completed = False
    stream_failure: ClassifiedProviderError | None = None
    try:
        with response:
            for raw_line in response:
                parsed = parse_stream_line(raw_line.decode("utf-8", errors="replace"))
                if parsed is None:
                    continue
                if parsed["kind"] == "end":
                    completed = True
                    break
                chunk = parsed["chunk"]
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    # Reasoning travels under the alias names seen in the wild; the
                    # alias determines the key the transcript uses on the way back,
                    # so it is carried with the event rather than flattened.
                    for alias in REASONING_ALIASES:
                        if isinstance(delta.get(alias), str) and delta[alias]:
                            emitted_any = True
                            yield {"kind": "reasoning", "field": alias, "text": delta[alias]}
                            break
                    content = delta.get("content")
                    if content:
                        emitted_any = True
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
                    finish = choice.get("finish_reason") or delta.get("finish_reason")
                    if finish in {"tool_calls", "stop", "length"}:
                        for index in sorted(pending):
                            emitted_any = True
                            yield {"kind": "tool_call", "call": dict(pending[index])}
                        pending.clear()
                        yield {"kind": "done", "finish_reason": finish}
                        return
        if not completed:
            phase = FailurePhase.MID_STREAM if emitted_any else FailurePhase.PRE_STREAM
            raise classify_provider_error(
                RuntimeError("stream ended prematurely without [DONE] or finish_reason"),
                provider=provider,
                model=model,
                phase=phase,
            )
    except ClassifiedProviderError:
        raise
    except Exception as error:
        phase = FailurePhase.MID_STREAM if emitted_any else FailurePhase.PRE_STREAM
        stream_failure = classify_provider_error(
            error, provider=provider, model=model, phase=phase
        )
    if stream_failure is not None:
        raise stream_failure
    for index in sorted(pending):
        yield {"kind": "tool_call", "call": dict(pending[index])}
    yield {"kind": "done", "finish_reason": "stop"}
