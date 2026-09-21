"""Optional local JEV connection, separate from conversational model providers.

GET/save are offline. Only an explicit test sends a fixed synthetic question.
The key is never returned, logged, or copied into the provider/model catalog.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from smartmoney_cub_harness.jev.direct import TypeSafeDirectJevBackend
from smartmoney_cub_harness.jev.questions import JevQuestion
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


class JevConnectionSettings:
    def __init__(self, root: str | Path, *, backend_factory: Callable[..., Any] = TypeSafeDirectJevBackend):
        self.path = Path(root) / 'jev-credentials.json'
        self._backend_factory = backend_factory
        self._lock = threading.RLock()
        self._probe_lock = threading.Lock()

    def _credential(self) -> tuple[str, str]:
        if self.path.is_symlink():
            raise ValueError('JEV 凭据文件不能是符号链接。')
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                value = data['api_key']
                if not isinstance(value, str) or not value:
                    raise ValueError()
                self._validate_key(value)
                return value, 'local'
            except (ValueError, KeyError, TypeError, UnicodeError) as error:
                raise ValueError('JEV 凭据文件无效，请重新保存密钥。') from error
        value = os.environ.get('TYPESAFE_API_KEY', '')
        return value, 'environment' if value else 'none'

    @staticmethod
    def _validate_key(value: str) -> None:
        if len(value) > 4096 or not re.fullmatch(r'[!-~]+', value):
            raise ValueError('密钥必须是无空格的 ASCII 字符，且不超过 4096 字符。')
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', value):
            raise ValueError('请只粘贴密钥本身，不要粘贴整行环境变量。')

    def view(self) -> dict[str, Any]:
        with self._lock:
            key, source = self._credential()
            return {
                'status': 'ok', 'configured': bool(key), 'key_source': source,
                'connection': 'untested' if key else 'unconfigured',
                'model': 'jev-latest', 'safety': SAFETY_DECLARATION,
            }

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or set(payload) - {'api_key', 'clear_key'}:
            raise ValueError('仅支持密钥和清除密钥选项。')
        value = payload.get('api_key', '')
        clear = payload.get('clear_key', False)
        if not isinstance(value, str) or not isinstance(clear, bool):
            raise ValueError('密钥必须为文本，清除选项必须为布尔值。')
        if clear and value:
            raise ValueError('不能同时保存和清除密钥。')
        if value:
            value = value.strip()
            self._validate_key(value)
        with self._lock:
            if clear:
                self.path.unlink(missing_ok=True)
            elif value:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix='.jev-', dir=self.path.parent)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                        if hasattr(os, 'fchmod'):
                            os.fchmod(handle.fileno(), 0o600)
                        json.dump({'api_key': value}, handle)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(name, self.path)
                finally:
                    Path(name).unlink(missing_ok=True)
            return self.view()

    def backend(self) -> Any:
        """Construct the existing typed backend with the saved key (or environment)."""
        with self._lock:
            key, _ = self._credential()
        if key:
            self._validate_key(key)
        return self._backend_factory(api_key=key, timeout_seconds=15.0)

    def test_connection(self) -> dict[str, Any]:
        if not self._probe_lock.acquire(blocking=False):
            return {'status': 'error', 'connection': 'testing', 'error': '连接测试正在进行。', 'safety': SAFETY_DECLARATION}
        try:
            view = self.view()
            if not view['configured']:
                return {**view, 'status': 'error', 'error': '请先配置 JEV 密钥。'}
            question = JevQuestion(
                question_id='connection-check', kind='choice',
                prompt='For this synthetic connection test, select ready.',
                choices=('ready', 'not_ready'),
            )
            self.backend().evaluate(
                {'connection_test': True}, (question,),
                decision_time=datetime.now(timezone.utc).isoformat(),
            )
            return {
                **view, 'connection': 'connected',
                'checked_at': datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            # Provider exception bodies can include request headers. Never echo them.
            return {
                'status': 'error', 'connection': 'failed',
                'error': '连接测试失败；请检查密钥、余额及网络后重试。',
                'safety': SAFETY_DECLARATION,
            }
        finally:
            self._probe_lock.release()
