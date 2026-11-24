"""Root-bound, local-only storage for shared workbench preferences."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


PREFERENCE_KEYS = (
    "locale",
    "timezone",
    "currency",
    "number_format",
    "color_scheme",
    "theme",
)

DEFAULT_PREFERENCES: dict[str, str] = {
    "locale": "zh-CN",
    "timezone": "local",
    "currency": "original",
    "number_format": "auto",
    "color_scheme": "cn",
    "theme": "dark",
}

SUPPORTED_LOCALES = frozenset(
    {"zh-CN", "en-US", "zh-TW", "ja-JP", "ko-KR", "es-ES", "pt-BR", "de-DE", "fr-FR"}
)
MAX_PREFERENCES_BYTES = 64 * 1024
PREFERENCES_FILENAME = "preferences.json"


class PreferencesError(ValueError):
    """A preference payload or local preference file is unsafe or invalid."""


class PreferencesStore:
    """Persist display preferences below one resolved workbench root.

    read and update return an envelope with preferences and missing_fields. A
    missing field is deliberately different from a stored default: callers can
    migrate an older browser-only preference once, without allowing it to
    overwrite a value already stored by another client.
    """

    def __init__(self, root: str | Path) -> None:
        root_path = Path(root).expanduser()
        root_path.mkdir(parents=True, exist_ok=True)
        self.root = root_path.resolve()
        self.path = self.root / PREFERENCES_FILENAME
        self._lock = threading.RLock()

    def read(self) -> dict[str, Any]:
        with self._lock:
            values, present = self._load_valid_locked()
            return self._snapshot(values, present)

    def update(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise PreferencesError("preferences payload must be a JSON object")
        unknown = sorted(set(payload) - set(PREFERENCE_KEYS))
        if unknown:
            raise PreferencesError("unsupported preference field(s): " + ", ".join(unknown))

        with self._lock:
            values, present = self._load_valid_locked()
            for key, value in payload.items():
                values[key] = self._validate_value(key, value)
                present.add(key)
            if payload:
                self._write_locked({key: values[key] for key in PREFERENCE_KEYS if key in present})
            return self._snapshot(values, present)

    def _load_valid_locked(self) -> tuple[dict[str, str], set[str]]:
        self._assert_safe_path()
        if not self.path.exists():
            return {}, set()
        try:
            raw_bytes = self.path.read_bytes()
        except OSError as error:
            raise PreferencesError(f"could not read preferences: {error}") from error
        if len(raw_bytes) > MAX_PREFERENCES_BYTES:
            raise PreferencesError("preferences file is too large")
        try:
            raw = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}, set()
        if not isinstance(raw, dict):
            return {}, set()

        values: dict[str, str] = {}
        present: set[str] = set()
        for key in PREFERENCE_KEYS:
            if key not in raw:
                continue
            try:
                values[key] = self._validate_value(key, raw[key])
            except PreferencesError:
                # A corrupt field is treated as absent. The safe default remains
                # visible and a later explicit update can repair just that field.
                continue
            present.add(key)
        return values, present

    def _write_locked(self, values: Mapping[str, str]) -> None:
        self._assert_safe_path()
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.root,
                prefix=".preferences.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                os.chmod(temporary_name, 0o600)
                json.dump(dict(values), temporary, ensure_ascii=False, sort_keys=True)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
            temporary_name = None
            try:
                directory_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                # The atomic replace is still safe when directory fsync is not
                # available on the host filesystem.
                pass
        except OSError as error:
            raise PreferencesError(f"could not write preferences: {error}") from error
        finally:
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

    def _assert_safe_path(self) -> None:
        if self.path.parent != self.root:
            raise PreferencesError("preferences path escaped the workbench root")
        try:
            if self.path.is_symlink():
                raise PreferencesError("preferences path must not be a symlink")
        except OSError as error:
            raise PreferencesError(f"could not inspect preferences path: {error}") from error

    @staticmethod
    def _snapshot(values: Mapping[str, str], present: set[str]) -> dict[str, Any]:
        preferences = {key: values.get(key, DEFAULT_PREFERENCES[key]) for key in PREFERENCE_KEYS}
        return {
            "preferences": preferences,
            "missing_fields": [key for key in PREFERENCE_KEYS if key not in present],
        }

    @staticmethod
    def _validate_value(key: str, value: Any) -> str:
        if not isinstance(value, str):
            raise PreferencesError(f"{key} must be a string")
        normalized = value.strip()
        if not normalized or len(normalized) > 128 or any(ord(char) < 0x20 for char in normalized):
            raise PreferencesError(f"{key} must be a non-empty text value")
        if key == "locale" and normalized not in SUPPORTED_LOCALES:
            raise PreferencesError(f"unsupported locale: {normalized}")
        if key == "timezone" and normalized != "local":
            try:
                ZoneInfo(normalized)
            except (KeyError, ValueError):
                raise PreferencesError(f"unsupported timezone: {normalized}") from None
        if key == "color_scheme" and normalized not in {"cn", "intl"}:
            raise PreferencesError(f"unsupported color scheme: {normalized}")
        if key == "theme" and normalized not in {"light", "dark"}:
            raise PreferencesError(f"unsupported theme: {normalized}")
        return normalized
