from __future__ import annotations

import json
import re
import socket
import urllib.error
from typing import Any

from smartmoney_cub_harness.safety import REDACTED, looks_sensitive_key, redact_string
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


class ProviderErrorCode:
    INSUFFICIENT_QUOTA = "insufficient_quota"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"
    NETWORK_UNREACHABLE = "network_unreachable"
    STREAM_INTERRUPTION = "stream_interruption"
    UNKNOWN = "unknown_error"


class FailurePhase:
    PRE_STREAM = "pre_stream"
    MID_STREAM = "mid_stream"


QUOTA_KEYWORDS = (
    "insufficient_quota",
    "quota",
    "balance",
    "insufficient",
    "arrears",
    "credit",
    "欠费",
    "余额不足",
    "额度不足",
    "额度已耗尽",
    "账户额度",
    "充值",
)

RATE_LIMIT_KEYWORDS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "requests per minute",
    "tokens per minute",
    "rpm",
    "tpm",
    "限流",
    "请求过于频繁",
)

AUTH_KEYWORDS = (
    "unauthorized",
    "invalid api key",
    "incorrect api key",
    "access denied",
    "permission denied",
    "authentication",
    "authorization",
    "forbidden",
    "密钥无效",
    "未授权",
)


class ProviderError(RuntimeError):
    """Base provider runtime error."""


def _collect_provider_secrets(provider: dict[str, Any] | None) -> set[str]:
    secrets: set[str] = set()
    if not provider:
        return secrets
    for k, v in provider.items():
        if isinstance(v, str) and v.strip():
            if looks_sensitive_key(str(k)) or k in ("api_key", "token", "auth_token", "secret", "password"):
                secrets.add(v.strip())
    return secrets


def _redact_all(value: Any, extra_secrets: set[str] | None = None) -> Any:
    """Copy diagnostic data, scrubbing keys and values without retaining objects."""
    if isinstance(value, dict):
        return {
            _redact_all(str(key), extra_secrets): (
                REDACTED if looks_sensitive_key(str(key)) else _redact_all(nested, extra_secrets)
            )
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [_redact_all(item, extra_secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_all(item, extra_secrets) for item in value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    redacted = redact_string(str(value))
    for secret in sorted(extra_secrets or (), key=len, reverse=True):
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    return redacted


class ClassifiedProviderError(ProviderError):
    """Structured provider error with stable code, actionable remediation, and safe diagnostics."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        raw_message: str = "",
        http_status: int | None = None,
        phase: str = FailurePhase.PRE_STREAM,
        provider_id: str = "",
        model: str = "",
        retryable_same_target: bool = False,
        fallbackable: bool = False,
        portal_url: str = "",
        action_suggestion: str = "",
        recovery_suggestions: list[dict[str, str]] | None = None,
        safe_diagnostics: dict[str, Any] | None = None,
        extra_secrets: set[str] | None = None,
    ) -> None:
        # This is the only storage boundary: sanitize the complete payload before
        # assigning any attributes (including RuntimeError.args). The secret set
        # is construction-only and must never become part of the exception state.
        fields = {
            "code": code,
            "message": message,
            "raw_message": raw_message or message,
            "http_status": http_status,
            "phase": phase,
            "provider_id": provider_id,
            "model": model,
            "retryable_same_target": retryable_same_target,
            "fallbackable": fallbackable,
            "portal_url": portal_url,
            "action_suggestion": action_suggestion,
            "recovery_suggestions": recovery_suggestions or [],
            "safe_diagnostics": safe_diagnostics or {},
            "safety": SAFETY_DECLARATION,
        }
        # Attribute names belong to our schema, not the upstream payload. Only
        # nested diagnostic keys are untrusted and should themselves be scrubbed.
        safe_fields = {name: _redact_all(value, extra_secrets) for name, value in fields.items()}
        super().__init__(safe_fields["message"])
        self.__dict__.update(safe_fields)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.code,
            "message": self.message,
            "raw_message": self.raw_message,
            "http_status": self.http_status,
            "phase": self.phase,
            "provider_id": self.provider_id,
            "model": self.model,
            "retryable_same_target": self.retryable_same_target,
            "fallbackable": self.fallbackable,
            "portal_url": self.portal_url,
            "action_suggestion": self.action_suggestion,
            "recovery_suggestions": self.recovery_suggestions,
            "safe_diagnostics": self.safe_diagnostics,
            "safety": self.safety,
        }


def _extract_http_status_and_body(error: Exception, detail: str = "") -> tuple[int | None, str]:
    http_status: int | None = getattr(error, "code", None)
    body = detail or ""
    if isinstance(error, urllib.error.HTTPError):
        http_status = error.code
        if not body:
            try:
                body = error.read().decode("utf-8", errors="replace")[:600]
            except Exception:
                body = ""
    elif isinstance(error, ProviderError):
        msg = str(error)
        match = re.search(r"HTTP\s+(\d{3})", msg)
        if match:
            http_status = int(match.group(1))
        if not body and ":" in msg:
            body = msg.split(":", 1)[1].strip()
    return http_status, body


def classify_provider_error(
    error: Exception,
    *,
    provider: dict[str, Any] | None = None,
    model: str = "",
    phase: str = FailurePhase.PRE_STREAM,
    detail: str = "",
) -> ClassifiedProviderError:
    provider = provider or {}
    provider_id = str(provider.get("provider_id") or "")
    portal_url = str(provider.get("portal_url") or "")
    extra_secrets = _collect_provider_secrets(provider)

    http_status, body = _extract_http_status_and_body(error, detail=detail)

    combined_text = f"{error} {body}".lower()
    sanitized_body = _redact_all(redact_string(body), extra_secrets)
    raw_message = _redact_all(redact_string(str(error)), extra_secrets)

    # Base diagnostic information
    safe_diagnostics: dict[str, Any] = {
        "provider_id": provider_id,
        "model": model,
        "phase": phase,
        "http_status": http_status,
        "error_type": type(error).__name__,
        "detail": sanitized_body[:300] if sanitized_body else "",
    }

    # Mid-stream failures
    if phase == FailurePhase.MID_STREAM:
        code = ProviderErrorCode.STREAM_INTERRUPTION
        msg = f"模型服务流式传输中断 ({model or provider_id})，连接已断开。"
        suggestion = "传输在输出中途中断。建议检查网络稳定性或重新发起复盘。"
        return ClassifiedProviderError(
            code=code,
            message=msg,
            raw_message=raw_message,
            http_status=http_status,
            phase=phase,
            provider_id=provider_id,
            model=model,
            retryable_same_target=False,
            fallbackable=False,
            portal_url=portal_url,
            action_suggestion=suggestion,
            recovery_suggestions=[
                {"action": "retry_turn", "label": "重新发起当前复盘轮次"},
            ],
            safe_diagnostics=safe_diagnostics,
            extra_secrets=extra_secrets,
        )

    # 1. Quota exhaustion (403, 429 with insufficient_quota, 400 with quota message)
    is_quota_code = http_status in (403, 429, 400)
    has_quota_kw = any(kw in combined_text for kw in QUOTA_KEYWORDS)
    if is_quota_code and has_quota_kw:
        code = ProviderErrorCode.INSUFFICIENT_QUOTA
        msg = f"模型服务额度不足 (HTTP {http_status}: insufficient_quota)。"
        if portal_url:
            msg += f" 请前往服务商控制台充值: {portal_url}"
        suggestion = "账户额度已耗尽。请前往服务商平台充值，或切换备用模型/离线模式。"
        recovery_suggestions: list[dict[str, str]] = []
        if portal_url:
            recovery_suggestions.append({
                "action": "recharge",
                "label": "前往服务商充值",
                "url": portal_url,
            })
        recovery_suggestions.extend([
            {"action": "switch_model", "label": "切换备用模型"},
            {"action": "offline_mode", "label": "使用离线规则"},
        ])
        return ClassifiedProviderError(
            code=code,
            message=msg,
            raw_message=raw_message,
            http_status=http_status,
            phase=phase,
            provider_id=provider_id,
            model=model,
            retryable_same_target=False,
            fallbackable=True,
            portal_url=portal_url,
            action_suggestion=suggestion,
            recovery_suggestions=recovery_suggestions,
            safe_diagnostics=safe_diagnostics,
            extra_secrets=extra_secrets,
        )

    # 2. Rate limited (429 not quota)
    if http_status == 429 or any(kw in combined_text for kw in RATE_LIMIT_KEYWORDS):
        code = ProviderErrorCode.RATE_LIMITED
        msg = f"模型服务请求频次超限 (HTTP {http_status or 429}: rate_limited)。"
        suggestion = "服务商暂时限流，建议稍后重试或配置候选降级模型。"
        return ClassifiedProviderError(
            code=code,
            message=msg,
            raw_message=raw_message,
            http_status=http_status or 429,
            phase=phase,
            provider_id=provider_id,
            model=model,
            retryable_same_target=True,
            fallbackable=True,
            portal_url=portal_url,
            action_suggestion=suggestion,
            recovery_suggestions=[
                {"action": "wait_retry", "label": "稍后自动重试"},
                {"action": "fallback", "label": "切换备用路线"},
            ],
            safe_diagnostics=safe_diagnostics,
            extra_secrets=extra_secrets,
        )

    # 3. Authentication failure (401, or 403 not quota)
    if http_status == 401 or (http_status == 403 and any(kw in combined_text for kw in AUTH_KEYWORDS)):
        code = ProviderErrorCode.AUTHENTICATION
        msg = f"模型服务鉴权失败 (HTTP {http_status})，API Key 无效或未授权。"
        suggestion = "请在设置中核对 API Key 是否正确，或重新输入。"
        return ClassifiedProviderError(
            code=code,
            message=msg,
            raw_message=raw_message,
            http_status=http_status,
            phase=phase,
            provider_id=provider_id,
            model=model,
            retryable_same_target=False,
            fallbackable=True,
            portal_url=portal_url,
            action_suggestion=suggestion,
            recovery_suggestions=[
                {"action": "check_key", "label": "检查并更新 API Key"},
            ],
            safe_diagnostics=safe_diagnostics,
            extra_secrets=extra_secrets,
        )

    # 4. Timeout (checked before generic 5xx so 504 and 408 classify as TIMEOUT)
    is_timeout = (
        isinstance(error, (socket.timeout, TimeoutError))
        or http_status in (408, 504)
        or "timed out" in combined_text
        or "timeout" in combined_text
    )
    if is_timeout:
        code = ProviderErrorCode.TIMEOUT
        msg = f"模型服务响应超时 (HTTP {http_status or 'timeout'}: {model or provider_id})。"
        suggestion = "请求超时未返回。可稍后重试或切换较快的小模型。"
        return ClassifiedProviderError(
            code=code,
            message=msg,
            raw_message=raw_message,
            http_status=http_status,
            phase=phase,
            provider_id=provider_id,
            model=model,
            retryable_same_target=True,
            fallbackable=True,
            portal_url=portal_url,
            action_suggestion=suggestion,
            recovery_suggestions=[
                {"action": "retry", "label": "重试请求"},
                {"action": "fallback", "label": "切换备用路线"},
            ],
            safe_diagnostics=safe_diagnostics,
            extra_secrets=extra_secrets,
        )

    # 5. Server error (5xx, excluding 504)
    if http_status and 500 <= http_status <= 599:
        code = ProviderErrorCode.SERVER_ERROR
        msg = f"模型服务上游异常 (HTTP {http_status})。"
        suggestion = "服务商服务端临时故障，可重试或自动降级至备用模型。"
        return ClassifiedProviderError(
            code=code,
            message=msg,
            raw_message=raw_message,
            http_status=http_status,
            phase=phase,
            provider_id=provider_id,
            model=model,
            retryable_same_target=True,
            fallbackable=True,
            portal_url=portal_url,
            action_suggestion=suggestion,
            recovery_suggestions=[
                {"action": "retry", "label": "重试请求"},
                {"action": "fallback", "label": "切换候选路线"},
            ],
            safe_diagnostics=safe_diagnostics,
            extra_secrets=extra_secrets,
        )

    # 6. Invalid request (400, 404, 422)
    if http_status in (400, 404, 422):
        code = ProviderErrorCode.INVALID_REQUEST
        msg = f"模型服务请求无效 (HTTP {http_status})。"
        suggestion = "请求格式、上下文长度或模型标识不支持，请核对模型参数。"
        return ClassifiedProviderError(
            code=code,
            message=msg,
            raw_message=raw_message,
            http_status=http_status,
            phase=phase,
            provider_id=provider_id,
            model=model,
            retryable_same_target=False,
            fallbackable=True,
            portal_url=portal_url,
            action_suggestion=suggestion,
            recovery_suggestions=[
                {"action": "check_settings", "label": "检查模型名称与参数"},
            ],
            safe_diagnostics=safe_diagnostics,
            extra_secrets=extra_secrets,
        )

    # 7. Network unreachable
    is_network = isinstance(error, urllib.error.URLError) or any(
        kw in combined_text
        for kw in ("connection refused", "unreachable", "name or service not known", "nodename")
    )
    if is_network:
        code = ProviderErrorCode.NETWORK_UNREACHABLE
        msg = f"无法连接到模型服务网关 ({provider_id})。"
        suggestion = "网络不通或服务端不可达。请检查网络或切换离线规则。"
        return ClassifiedProviderError(
            code=code,
            message=msg,
            raw_message=raw_message,
            http_status=http_status,
            phase=phase,
            provider_id=provider_id,
            model=model,
            retryable_same_target=True,
            fallbackable=True,
            portal_url=portal_url,
            action_suggestion=suggestion,
            recovery_suggestions=[
                {"action": "check_network", "label": "检查网络连接"},
                {"action": "offline_mode", "label": "切换离线模式"},
            ],
            safe_diagnostics=safe_diagnostics,
            extra_secrets=extra_secrets,
        )

    # 8. Fallback unknown error
    code = ProviderErrorCode.UNKNOWN
    msg = f"模型服务调用失败: {sanitized_body or raw_message}"
    return ClassifiedProviderError(
        code=code,
        message=msg,
        raw_message=raw_message,
        http_status=http_status,
        phase=phase,
        provider_id=provider_id,
        model=model,
        retryable_same_target=False,
        fallbackable=True,
        portal_url=portal_url,
        action_suggestion="调用异常，请查看日志或切换其他模型。",
        recovery_suggestions=[
            {"action": "switch_model", "label": "切换其他模型"},
        ],
        safe_diagnostics=safe_diagnostics,
        extra_secrets=extra_secrets,
    )
