"""Fail-closed stdio bridge for the optional DeepSeek Harness sidecar.

The Python Workbench remains the source of truth.  This module only transports
versioned, already-redacted review envelopes and lifecycle events to a local
DSH/Cordis process.  It deliberately does not launch, download, or execute a
third-party project.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, TextIO

from smartmoney_cub_harness.review_contracts import RedactedReviewEnvelope
from smartmoney_cub_harness.review_validation import validate_redacted_payload
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

DSH_PROTOCOL = "smartmoney_cub_dsh_stdio.v1"
DSH_PROFILE = "smartmoney-review"

# These are review lifecycle capabilities, not financial operations.  In
# particular, ``review_cancel`` cancels a model turn and never an order.
ALLOWED_CAPABILITIES = frozenset(
    {
        "review_envelope",
        "review_events",
        "review_cancel",
        "review_resume",
        "review_fork",
        "review_close",
        "heartbeat",
    }
)
FORBIDDEN_CAPABILITIES = frozenset(
    {
        "shell",
        "filesystem",
        "network",
        "web",
        "jobs",
        "workflow",
        "subagent",
        "agent-team",
        "broker",
        "order",
        "trade",
        "account",
        "order_cancel",
    }
)


class DshBridgeError(RuntimeError):
    """A safe, stable bridge failure; upstream exception text is not retained."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        self.safety = SAFETY_DECLARATION
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
            "safety": self.safety,
        }


@dataclass(frozen=True)
class DshProfile:
    name: str = DSH_PROFILE
    protocol: str = DSH_PROTOCOL
    capabilities: frozenset[str] = ALLOWED_CAPABILITIES
    allow_network: bool = False
    allow_shell: bool = False
    allow_filesystem: bool = False
    allow_credentials: bool = False
    safety: str = SAFETY_DECLARATION

    def __post_init__(self) -> None:
        if self.safety != SAFETY_DECLARATION:
            raise ValueError("invalid_safety")
        if self.name != DSH_PROFILE or self.protocol != DSH_PROTOCOL:
            raise ValueError("unsupported_dsh_profile")
        if not self.capabilities <= ALLOWED_CAPABILITIES:
            raise ValueError("profile_contains_unsupported_capability")
        if self.capabilities & FORBIDDEN_CAPABILITIES:
            raise ValueError("profile_contains_forbidden_capability")
        if self.allow_network or self.allow_shell or self.allow_filesystem or self.allow_credentials:
            raise ValueError("smartmoney-review profile must remain local and restricted")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "capabilities": sorted(self.capabilities),
            "forbidden_capabilities": sorted(FORBIDDEN_CAPABILITIES),
            "allow_network": self.allow_network,
            "allow_shell": self.allow_shell,
            "allow_filesystem": self.allow_filesystem,
            "allow_credentials": self.allow_credentials,
            "safety": self.safety,
        }


def dsh_source_bootstrap() -> dict[str, Any]:
    """Describe the developer bootstrap without running or fetching anything."""
    return {
        "source": "https://github.com/deepseek-ai/deepseek-harness",
        "clone": "git clone https://github.com/deepseek-ai/deepseek-harness",
        "build": "pnpm install && pnpm build",
        "web": "pnpm dev:web",
        "runtime": "local sidecar only",
        "executed": False,
        "safety": SAFETY_DECLARATION,
    }


def _safe_request(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": None,
        "method": method,
        "params": params,
        "safety": SAFETY_DECLARATION,
    }


@dataclass
class DshSidecarBridge:
    """Synchronous line-oriented JSON-RPC client with a fixed method allowlist."""

    reader: TextIO
    writer: TextIO
    profile: DshProfile = field(default_factory=DshProfile)
    request_id: int = 0
    connected: bool = False
    _envelope: RedactedReviewEnvelope | None = field(default=None, repr=False)

    def _write(self, method: str, params: dict[str, Any]) -> None:
        self.request_id += 1
        request = _safe_request(method, params)
        request["id"] = self.request_id
        try:
            self.writer.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.writer.flush()
        except (BrokenPipeError, OSError) as exc:
            raise DshBridgeError("sidecar_crashed", "DSH sidecar transport closed.", retryable=True) from None

    def _read(self) -> dict[str, Any]:
        try:
            line = self.reader.readline()
        except (BrokenPipeError, OSError):
            raise DshBridgeError("sidecar_crashed", "DSH sidecar transport closed.", retryable=True) from None
        if not line:
            raise DshBridgeError("sidecar_crashed", "DSH sidecar exited before responding.", retryable=True)
        try:
            response = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            raise DshBridgeError("invalid_sidecar_response", "DSH sidecar returned invalid JSON.", retryable=True) from None
        if not isinstance(response, dict):
            raise DshBridgeError("invalid_sidecar_response", "DSH sidecar response must be an object.", retryable=True)
        if response.get("safety") != SAFETY_DECLARATION:
            raise DshBridgeError("invalid_sidecar_safety", "DSH sidecar safety declaration is invalid.")
        if response.get("error"):
            error = response["error"]
            code = error.get("code") if isinstance(error, dict) else "sidecar_error"
            raise DshBridgeError(str(code), "DSH sidecar rejected the review request.", retryable=False)
        return response

    def _call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if method not in {
            "handshake",
            "subscribe",
            "cancel",
            "resume",
            "fork",
            "close",
            "heartbeat",
        }:
            raise DshBridgeError("method_not_allowed", "DSH review profile does not allow this method.")
        self._write(method, params or {})
        return self._read()

    def handshake(self, envelope: RedactedReviewEnvelope | dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = (
                envelope
                if isinstance(envelope, RedactedReviewEnvelope)
                else RedactedReviewEnvelope.from_dict(envelope)
            )
        except Exception:
            raise DshBridgeError("invalid_review_envelope", "Only a versioned redacted review envelope is accepted.") from None
        validation = validate_redacted_payload(normalized.payload)
        if not validation.ok:
            raise DshBridgeError("invalid_review_envelope", "Review envelope failed the redaction boundary.")
        digest = hashlib.sha256(
            json.dumps(normalized.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if normalized.payload_sha256 != digest:
            raise DshBridgeError("invalid_review_envelope", "Review envelope integrity check failed.")
        response = self._call(
            "handshake",
            {"protocol": DSH_PROTOCOL, "profile": self.profile.to_dict(), "envelope": normalized.to_dict()},
        )
        self.connected = True
        self._envelope = normalized
        return response

    def subscribe(self, topics: Iterable[str] = ("turn", "step", "attempt", "plugin", "terminal")) -> dict[str, Any]:
        self._require_connected()
        return self._call("subscribe", {"topics": sorted(set(topics))})

    def cancel(self, review_id: str) -> dict[str, Any]:
        self._require_connected()
        return self._call("cancel", {"review_id": review_id})

    def resume(self, review_id: str, *, after_seq: int = 0) -> dict[str, Any]:
        self._require_connected()
        return self._call("resume", {"review_id": review_id, "after_seq": max(0, int(after_seq))})

    def fork(self, review_id: str, *, title: str = "") -> dict[str, Any]:
        self._require_connected()
        return self._call("fork", {"review_id": review_id, "title": title})

    def close(self, review_id: str) -> dict[str, Any]:
        self._require_connected()
        response = self._call("close", {"review_id": review_id})
        self.connected = False
        return response

    def heartbeat(self) -> dict[str, Any]:
        self._require_connected()
        return self._call("heartbeat", {})

    def _require_connected(self) -> None:
        if not self.connected:
            raise DshBridgeError("not_connected", "DSH sidecar handshake is required first.")


class InMemoryDshTransport:
    """Deterministic protocol stub used by tests and offline development."""

    def __init__(self) -> None:
        self.inbox: list[str] = []
        self.outbox: list[str] = []
        self.closed = False

    def write(self, line: str) -> None:
        self.inbox.append(line)
        request = json.loads(line)
        method = request.get("method")
        if self.closed:
            return
        result: dict[str, Any] = {"accepted": True, "method": method}
        if method == "handshake":
            profile = request.get("params", {}).get("profile", {})
            if profile.get("name") != DSH_PROFILE or profile.get("allow_network") is not False:
                self._respond(request, error={"code": "profile_rejected"})
                return
            result["profile"] = DSH_PROFILE
        if method == "heartbeat":
            result["alive"] = True
        self._respond(request, result=result)

    def flush(self) -> None:
        return

    def _respond(self, request: dict[str, Any], *, result: dict[str, Any] | None = None, error: dict[str, Any] | None = None) -> None:
        self.outbox.append(
            json.dumps(
                {"jsonrpc": "2.0", "id": request.get("id"), "result": result, "error": error, "safety": SAFETY_DECLARATION},
                ensure_ascii=False,
            )
            + "\n"
        )

    def readline(self) -> str:
        if not self.outbox:
            return ""
        return self.outbox.pop(0)

    def close(self) -> None:
        self.closed = True
