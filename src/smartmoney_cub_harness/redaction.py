from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from typing import Any

from smartmoney_cub_harness.safety import looks_sensitive_key, redact_string
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

# Anything that leaves this machine for an external model passes through here.
#
# The redactor is deliberately lossy about identity and exact size, and lossless
# about the review-relevant shape: returns, holding periods, execution
# deviation, and statistical features survive; account numbers, names, exact
# quantities, exact amounts, and exact timestamps do not.

AUDIT_SCHEMA = "smartmoney_cub_outbound_audit.v1"
REDACTION_POLICY_VERSION = "redaction.v1"

# A device-local salt is used so an alias is stable on one machine and
# meaningless anywhere else. It never leaves the local store.
ALIAS_SALT_SETTING = "alias_salt"

QUANTITY_STEPS = (100, 500, 1000, 5000, 10000, 50000, 100000)
AMOUNT_STEPS = (10000, 50000, 100000, 500000, 1000000, 5000000, 10000000)

# Keys that name a person, an account, or any other direct identifier.
IDENTIFIER_KEYS = (
    "account",
    "account_no",
    "account_number",
    "broker_account",
    "client_id",
    "customer",
    "holder",
    "id_card",
    "identity",
    "name",
    "owner",
    "phone",
    "real_name",
    "user",
)

# Aliased keys are checked before the identifier rule, because a portfolio name
# and a holder name must not be treated the same way.
SYMBOL_KEYS = ("symbol", "code", "ticker", "证券代码")
PORTFOLIO_KEYS = ("portfolio", "portfolio_id", "portfolio_name", "portfolio_label")
DATE_KEYS = ("date", "trade_date", "trade_day", "trading_date")

EXACT_TIME_KEYS = (
    "time",
    "timestamp",
    "datetime",
    "executed_at",
    "filled_at",
    "entry_time",
    "exit_time",
    "opened_at",
    "closed_at",
    "created_at",
    "updated_at",
)
EXACT_QUANTITY_KEYS = ("quantity", "volume", "shares", "qty", "position_size", "remaining")
EXACT_AMOUNT_KEYS = ("amount", "notional", "turnover", "value", "cost", "proceeds", "price")

# Base64 blobs, data URLs, and long random strings are how an attachment or a
# credential would sneak into a payload. They are hard failures, not warnings.
ATTACHMENT_PATTERNS = (
    re.compile(r"data:[a-z]+/[a-z0-9.+-]+;base64,", re.IGNORECASE),
    re.compile(r"base64,[A-Za-z0-9+/=]{64,}"),
    re.compile(r'"(?:image|file|attachment|document)_(?:data|bytes|content)"\s*[:=]'),
)


def _round_down(value: float, steps: tuple[int, ...]) -> int:
    magnitude = abs(float(value))
    chosen = 0
    for step in steps:
        if magnitude >= step:
            chosen = step
    return chosen


def quantity_band(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if number <= 0:
        return "0"
    step = _round_down(number, QUANTITY_STEPS)
    if step == 0:
        return "0-100"
    return f"{step}-{step * 5}"


def amount_band(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if number <= 0:
        return "0"
    step = _round_down(number, AMOUNT_STEPS)
    if step == 0:
        return "0-10000"
    return f"{step}-{step * 5}"


def time_bucket(value: Any) -> str:
    """Reduce an exact timestamp to a 15-minute session bucket."""
    text = str(value or "")
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return "unknown"
    hour = int(match.group(1))
    minute = int(match.group(2))
    bucket = (minute // 15) * 15
    end_minute = bucket + 15
    end_hour = hour + (1 if end_minute >= 60 else 0)
    return f"{hour:02d}:{bucket:02d}-{end_hour:02d}:{end_minute % 60:02d}"


def date_bucket(value: Any) -> str:
    """Reduce an exact date to its month."""
    text = str(value or "")
    match = re.search(r"(\d{4})[-/]?(\d{2})[-/]?(\d{2})", text)
    if not match:
        return "unknown"
    return f"{match.group(1)}-{match.group(2)}"


def alias_for(value: Any, *, salt: str, kind: str) -> str:
    """Return a device-stable pseudonym for an identifier."""
    digest = hmac.new(
        key=salt.encode("utf-8"),
        msg=f"{kind}:{value}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"{kind}-{digest[:8]}"


# A six-digit code is an A-share symbol in this domain. It also hides inside
# generated identifiers such as POS-600111 or RT-600111-1, so every remaining
# string gets one final pass.
SYMBOL_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")


def scrub_symbol_codes(text: str, *, salt: str) -> str:
    return SYMBOL_CODE_RE.sub(lambda match: alias_for(match.group(1), salt=salt, kind="symbol"), text)


def _is_key(key: str, candidates: tuple[str, ...]) -> bool:
    lowered = key.lower()
    return any(candidate == lowered or lowered.endswith(f"_{candidate}") for candidate in candidates)


def redact_payload(payload: Any, *, salt: str, path: str = "") -> tuple[Any, dict[str, int]]:
    """Redact every value whose key marks it as identity or exact size.

    This is value-level redaction. It does not rely on the key name alone for
    strings, so a personal identifier sitting inside a note is still removed.
    """
    summary: dict[str, int] = {}

    def note(reason: str) -> None:
        summary[reason] = summary.get(reason, 0) + 1

    def walk(node: Any, key_path: str) -> Any:
        if isinstance(node, dict):
            result: dict[str, Any] = {}
            for key, value in node.items():
                key_text = str(key)
                child_path = f"{key_path}.{key_text}" if key_path else key_text
                lowered = key_text.lower()
                if looks_sensitive_key(key_text):
                    note("credential_or_account_key")
                    result[key_text] = "[REDACTED]"
                    continue
                if lowered in PORTFOLIO_KEYS and isinstance(value, str):
                    note("portfolio_alias")
                    result[key_text] = alias_for(value, salt=salt, kind="portfolio")
                    continue
                if lowered in SYMBOL_KEYS and isinstance(value, str):
                    note("symbol_alias")
                    result[key_text] = alias_for(value, salt=salt, kind="symbol")
                    continue
                if lowered in DATE_KEYS:
                    note("date_coarsened")
                    result[key_text] = date_bucket(value)
                    continue
                if _is_key(key_text, EXACT_QUANTITY_KEYS):
                    note("exact_quantity")
                    result[key_text] = quantity_band(value)
                    continue
                if _is_key(key_text, EXACT_AMOUNT_KEYS):
                    note("exact_amount")
                    result[key_text] = amount_band(value)
                    continue
                if _is_key(key_text, EXACT_TIME_KEYS):
                    note("exact_time")
                    result[key_text] = time_bucket(value)
                    continue
                if _is_key(key_text, IDENTIFIER_KEYS) and isinstance(value, str):
                    note("identifier_value")
                    result[key_text] = alias_for(value, salt=salt, kind="subject")
                    continue
                result[key_text] = walk(value, child_path)
            return result
        if isinstance(node, (list, tuple)):
            return [walk(item, f"{key_path}[{index}]") for index, item in enumerate(node)]
        if isinstance(node, str):
            # Structured values have already been handled by their key. A code
            # embedded in free text or in a generated id is replaced here.
            cleaned = scrub_symbol_codes(redact_string(node), salt=salt)
            if cleaned != node:
                note("free_text_reference")
            return cleaned
        return node

    return walk(payload, path), summary


def scan_for_attachments(payload: Any, *, path: str = "") -> list[str]:
    """Return the paths of embedded attachment or credential material."""
    findings: list[str] = []

    def walk(node: Any, key_path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{key_path}.{key}" if key_path else str(key))
            return
        if isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                walk(item, f"{key_path}[{index}]")
            return
        if isinstance(node, str):
            for pattern in ATTACHMENT_PATTERNS:
                if pattern.search(node):
                    findings.append(key_path or "payload")
                    return
            # A long, decodable blob is treated as file content even without a
            # data URL prefix.
            if len(node) > 512:
                try:
                    base64.b64decode(node[:512], validate=True)
                except Exception:
                    return
                findings.append(key_path or "payload")
            return

    walk(payload, path)
    return findings


def prepare_outbound(
    payload: dict[str, Any],
    *,
    salt: str,
    attachments_present: bool = False,
) -> dict[str, Any]:
    """Build the outbound request body, or refuse it.

    There is no override switch: when attachment material is detected the request
    is blocked and the caller is told why.
    """
    if attachments_present:
        return {
            "status": "blocked",
            "blocked": True,
            "reason": "attachments_never_leave_this_machine",
            "safety": SAFETY_DECLARATION,
        }

    findings = scan_for_attachments(payload)
    if findings:
        return {
            "status": "blocked",
            "blocked": True,
            "reason": "embedded_attachment_material",
            "paths": findings,
            "safety": SAFETY_DECLARATION,
        }

    redacted, summary = redact_payload(payload, salt=salt)
    serialized = json.dumps(redacted, ensure_ascii=False, sort_keys=True)
    return {
        "status": "ok",
        "blocked": False,
        "payload": redacted,
        "payload_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "sent_keys": sorted(_collect_keys(redacted)),
        "redaction_summary": {
            "policy": REDACTION_POLICY_VERSION,
            "counts": summary,
            "total": sum(summary.values()),
        },
        "safety": SAFETY_DECLARATION,
    }


def _collect_keys(node: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.add(path)
            keys |= _collect_keys(value, path)
    elif isinstance(node, (list, tuple)):
        for index, item in enumerate(node):
            keys |= _collect_keys(item, f"{prefix}[{index}]")
    return keys
