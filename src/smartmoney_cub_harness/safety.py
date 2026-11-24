from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

REDACTED = "[REDACTED]"

SENSITIVE_KEY_FRAGMENTS = (
    "account",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "passwd",
    "secret",
    "session",
    "token",
)

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
WINDOWS_PATH_RE = re.compile(r"(?i)\b[A-Z]:\\[^\s\"'<>|]+")
HOME_PATH_RE = re.compile(r"(?i)(?:/Users|/home)/[^\s\"'<>|]+")
POSIX_LOCAL_PATH_RE = re.compile(
    r"(?i)(?<![:/])/(?:usr|opt|tmp|var|private|mnt|workspace|workspaces|runner)(?:/[^\s\"'<>|,;]*)?"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|api_key|apikey|password|passwd|cookie|secret|account|session)\s*=\s*([^\s,;]+)"
)
SECRET_VALUE_RE = re.compile(
    r"(?i)\b("
    r"sk-[A-Za-z0-9_-]{8,}|"
    r"ghp_[A-Za-z0-9_]{8,}|"
    r"AIza[A-Za-z0-9_-]{8,}|"
    r"AKIA[A-Z0-9]{8,}"
    r")\b"
)


def looks_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_string(value: str) -> str:
    text = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", value)
    text = SECRET_VALUE_RE.sub(REDACTED, text)
    text = EMAIL_RE.sub(REDACTED, text)
    text = PHONE_RE.sub(REDACTED, text)
    text = WINDOWS_PATH_RE.sub(REDACTED, text)
    text = HOME_PATH_RE.sub(REDACTED, text)
    text = POSIX_LOCAL_PATH_RE.sub(REDACTED, text)
    return text


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            redacted[key] = REDACTED if looks_sensitive_key(key_text) else redact(nested)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, Path):
        return redact_string(str(value))
    if isinstance(value, str):
        return redact_string(value)
    return value


def is_relative_artifact_path(value: object) -> bool:
    """Return whether a portable artifact reference stays below its pack root."""
    if not isinstance(value, str) or not value.strip():
        return False
    windows_path = PureWindowsPath(value)
    posix_path = PurePosixPath(value)
    if windows_path.drive or windows_path.root or posix_path.root:
        return False
    return ".." not in re.split(r"[\\/]", value)


def safety_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    wrapped = dict(payload)
    wrapped.setdefault("safety", SAFETY_DECLARATION)
    return redact(wrapped)


def confined_artifact_path(root: Path, relative: str) -> Path:
    """Resolve an artifact destination, refusing existing symlink escapes.

    This checks the filesystem at call time; it is not an OS sandbox against
    another process concurrently replacing directories.
    """
    if not is_relative_artifact_path(relative):
        raise ValueError("artifact destination is outside its output directory")
    resolved_root = root.resolve(strict=True)
    destination = (resolved_root / relative).resolve(strict=False)
    if not destination.is_relative_to(resolved_root):
        raise ValueError("artifact destination is outside its output directory")
    return destination
