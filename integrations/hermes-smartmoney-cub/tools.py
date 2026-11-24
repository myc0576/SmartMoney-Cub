"""Tool handlers: shell out to the local `smcub` CLI and return JSON strings.

Design rules enforced here:
- arguments are passed as a list, never through a shell, so a path can never
  be interpreted as a command;
- every handler returns a JSON string and never raises;
- no handler places or cancels an order, executes a trade, or produces
  financial advice. Registered public-market, account-query, and scoped-sync
  operations may use the network only after the core PermissionStore checks
  authorization; the plugin discloses that metadata and does not authorize it.
- path-sensitive tools fail closed unless run_root is configured. Every input
  and output path is checked after filesystem resolution so symlinks and parent
  traversal cannot escape that root.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

SAFETY = "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"

DEFAULT_TIMEOUT = 120
CAPABILITIES_SCHEMA = "cli.capabilities.v1"
PROTOCOL_VERSION = 1
HERMES_PRINCIPAL = "hermes"

_OPERATION_NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SECRET_KEY_PARTS = (
    "secret",
    "token",
    "password",
    "credential",
    "cookie",
    "authorization",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
)
_SECRET_VALUE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)\s*[:=]\s*)[^\s,;]+"
)
_FORBIDDEN_OPERATION_PREFIXES = (
    "order.",
    "orders.",
    "cancel.",
    "trade.",
    "trades.",
    "execution.",
    "permissions.grant",
    "permissions.approve",
    "permission.grant",
    "permission.approve",
)
_FORBIDDEN_OPERATION_TOKENS = frozenset(
    {
        "order",
        "orders",
        "cancel",
        "cancels",
        "trade",
        "trades",
        "trading",
        "execution",
        "execute",
        "place",
        "submit",
        "approve",
        "approved",
        "grant",
        "granted",
    }
)
_SAFE_OPERATION_FIELDS = {
    "name",
    "description",
    "permission",
    "permissions",
    "writes",
    "network",
    "network_required",
    "database",
    "cache",
    "proposal_only",
    "approval_required",
    "read_only",
    "scope",
    "data_class",
    "human_only",
    "secret_input",
    "secret_output",
    "setup",
    "sync",
    "account",
    "market_data",
    "network_disclosure",
    "human_approval_required",
    "confirmation",
}

_DISCLOSURES: dict[str, dict[str, Any]] = {
    "doctor": {
        "writes": [],
        "database": "none initiated by this plugin",
        "cache": "none initiated by this plugin",
        "network": False,
    },
    "validate": {
        "writes": [],
        "database": "none initiated by this plugin",
        "cache": "none initiated by this plugin",
        "network": False,
    },
    "inspect": {
        "writes": [],
        "database": "none initiated by this plugin",
        "cache": "none initiated by this plugin",
        "network": False,
    },
    "evaluate": {
        "writes": ["<run_dir>/eval.json; the core may create or replace it"],
        "database": "none initiated by this plugin",
        "cache": "host runtime caches may be written",
        "network": False,
    },
    "build": {
        "writes": [
            "<output_dir>/rule_candidate.json",
            "<output_dir>/evidence_pack.json",
            "<output_dir>/evidence_pack.sha256",
            "<output_dir>/samples/<run_id>/*",
        ],
        "database": "none initiated by this plugin",
        "cache": "host runtime caches may be written",
        "network": False,
    },
    "replay": {
        "writes": [
            "<pack_dir>/replay_report.json; the core may create or replace it, including on pending or failed replay"
        ],
        "database": "none initiated by this plugin",
        "cache": "host runtime caches may be written",
        "network": False,
    },
    "capabilities": {
        "writes": [],
        "database": "none initiated by this plugin",
        "cache": "host runtime caches may be written",
        "network": False,
    },
    "operation": {
        "writes": [
            "core-controlled outputs under the human-configured state_dir and run_root, as advertised by the capability"
        ],
        "database": "the core PermissionStore and other state may use the human-configured state_dir",
        "cache": "the core may use caches under its configured state boundary",
        "network": "declared per operation; core PermissionStore authorization is required",
        "authorization": "enforced by core PermissionStore",
    },
}


def _redact(value: Any, key: str = "") -> Any:
    """Remove credential-like values before a payload reaches Hermes."""
    lowered = key.lower()
    if any(part in lowered for part in _SECRET_KEY_PARTS):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(item_key): _redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        value = _SECRET_VALUE.sub(r"\1<redacted>", value)
        return _SECRET_ASSIGNMENT.sub(r"\1<redacted>", value)
    return value


def _error(message: str, *, code: str = "plugin_error", **extra: Any) -> str:
    payload: dict[str, Any] = {
        "status": "error",
        "error_code": code,
        "error": message,
        "safety": SAFETY,
    }
    payload.update(extra)
    return json.dumps(_redact(payload), ensure_ascii=False)


def _resolve_command(ctx_config: dict[str, Any]) -> str:
    configured = str(ctx_config.get("smcub_command") or "smcub").strip() or "smcub"
    resolved = shutil.which(configured)
    return resolved or configured


def _resolve_configured_directory(
    ctx_config: dict[str, Any], key: str
) -> tuple[Path | None, str | None]:
    """Resolve a human-configured directory; model arguments never reach here."""
    raw = str(ctx_config.get(key) or "").strip()
    if not raw:
        return None, f"{key} must be configured by the human operator"
    try:
        resolved = Path(raw).expanduser().resolve(strict=True)
    except OSError as exc:
        return None, f"{key} cannot be resolved: {exc}"
    if not resolved.is_dir():
        return None, f"{key} is not a directory: {resolved}"
    return resolved, None


def _timeout(ctx_config: dict[str, Any]) -> int:
    try:
        value = int(ctx_config.get("timeout_seconds") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        value = DEFAULT_TIMEOUT
    return max(5, min(value, 3600))


def _resolve_root(ctx_config: dict[str, Any]) -> tuple[Path | None, str | None]:
    """Resolve the human-configured run root, refusing an absent root."""
    return _resolve_configured_directory(ctx_config, "run_root")


def _relative_to_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_existing_under_root(
    ctx_config: dict[str, Any], path: Path, *, kind: str
) -> tuple[Path | None, str | None]:
    """Validate an existing file or directory, including symlink containment."""
    root, failure = _resolve_root(ctx_config)
    if failure:
        return None, failure
    assert root is not None
    try:
        resolved = path.expanduser().resolve(strict=True)
    except FileNotFoundError:
        return None, f"path does not exist: {path}"
    except OSError as exc:
        return None, f"could not resolve path: {exc}"
    if not _relative_to_root(resolved, root):
        return None, f"path is outside the configured run_root: {path}"
    if kind == "directory" and not resolved.is_dir():
        return None, f"path is not a directory: {path}"
    if kind == "file" and not resolved.is_file():
        return None, f"path is not a file: {path}"
    return resolved, None


def _resolve_output_under_root(
    ctx_config: dict[str, Any], path: Path
) -> tuple[Path | None, str | None]:
    """Validate an output directory, allowing a new directory below root."""
    root, failure = _resolve_root(ctx_config)
    if failure:
        return None, failure
    assert root is not None
    candidate = path.expanduser()
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        return None, f"could not resolve output directory: {exc}"
    if not _relative_to_root(resolved, root):
        return None, f"output directory is outside the configured run_root: {path}"

    existing = candidate
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    try:
        existing_resolved = existing.resolve(strict=True)
    except OSError as exc:
        return None, f"could not resolve output parent: {exc}"
    if not existing_resolved.is_dir():
        return None, f"output parent is not a directory: {existing}"
    if not _relative_to_root(existing_resolved, root):
        return None, f"output directory is outside the configured run_root: {path}"
    if candidate.exists() and not resolved.is_dir():
        return None, f"output path is not a directory: {path}"
    return resolved, None


def _run(ctx_config: dict[str, Any], argv: list[str]) -> tuple[int, str, str]:
    command = [ _resolve_command(ctx_config), *argv ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_timeout(ctx_config),
            shell=False,
            check=False,
        )
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except FileNotFoundError:
        return 127, "", f"smcub CLI not found: {_resolve_command(ctx_config)}"
    except subprocess.TimeoutExpired:
        return 124, "", f"smcub timed out after {_timeout(ctx_config)}s"
    except OSError as exc:
        return 126, "", f"could not start smcub: {exc}"


def _payload(
    returncode: int,
    stdout: str,
    stderr: str,
    command: list[str],
    *,
    disclosure_key: str | None = None,
) -> str:
    parsed: Any = None
    text_out = stdout.strip()
    if text_out:
        try:
            parsed = json.loads(text_out)
        except json.JSONDecodeError:
            parsed = None
    result: dict[str, Any] = {
        "status": "ok" if returncode == 0 else "failed",
        "returncode": returncode,
        "command": " ".join(command),
        "safety": SAFETY,
    }
    if parsed is not None:
        result["result"] = parsed
    elif text_out:
        result["stdout"] = text_out
    if stderr.strip():
        result["stderr"] = stderr.strip()[:4000]
    if disclosure_key:
        result["disclosures"] = _DISCLOSURES[disclosure_key]
    return json.dumps(_redact(result), ensure_ascii=False)


def _require_path(args: Any, key: str) -> tuple[Path | None, str | None]:
    if not isinstance(args, dict):
        return None, "arguments must be an object"
    raw = str(args.get(key) or "").strip()
    if not raw:
        return None, f"missing required argument: {key}"
    path = Path(raw).expanduser()
    return path, None


def smcub_doctor(args: dict[str, Any], **kwargs: Any) -> str:
    ctx_config = kwargs.get("config") or {}
    argv = ["doctor"]
    returncode, stdout, stderr = _run(ctx_config, argv)
    return _payload(returncode, stdout, stderr, argv, disclosure_key="doctor")


def _path_tool(args, kwargs, key, argv_for, *, kind: str, disclosure_key: str):
    ctx_config = kwargs.get("config") or {}
    path, failure = _require_path(args, key)
    if failure:
        return _error(failure)
    assert path is not None
    checked, failure = _resolve_existing_under_root(ctx_config, path, kind=kind)
    if failure:
        return _error(failure)
    assert checked is not None
    argv = argv_for(str(checked))
    returncode, stdout, stderr = _run(ctx_config, argv)
    return _payload(returncode, stdout, stderr, argv, disclosure_key=disclosure_key)


def smcub_validate_envelope(args: dict[str, Any], **kwargs: Any) -> str:
    return _path_tool(
        args,
        kwargs,
        "envelope_path",
        lambda p: ["validate-envelope", "--", p],
        kind="file",
        disclosure_key="validate",
    )


def smcub_replay_evidence_pack(args: dict[str, Any], **kwargs: Any) -> str:
    return _path_tool(
        args,
        kwargs,
        "pack_dir",
        lambda p: ["replay-evidence-pack", "--", p],
        kind="directory",
        disclosure_key="replay",
    )


def smcub_inspect_artifacts(args: dict[str, Any], **kwargs: Any) -> str:
    return _path_tool(
        args,
        kwargs,
        "run_dir",
        lambda p: ["inspect-artifacts", "--", p],
        kind="directory",
        disclosure_key="inspect",
    )


def smcub_evaluate_run(args: dict[str, Any], **kwargs: Any) -> str:
    values = _as_args(args)
    if values is None:
        return _error("arguments must be an object")
    horizon = str(values.get("horizon") or "d1").strip()
    if horizon not in {"d1", "d3"}:
        return _error("horizon must be one of: d1, d3")
    return _path_tool(
        values,
        kwargs,
        "run_dir",
        lambda p: ["evaluate-run", "--horizon", horizon, "--", p],
        kind="directory",
        disclosure_key="evaluate",
    )


def smcub_build_evidence_pack(args: dict[str, Any], **kwargs: Any) -> str:
    ctx_config = kwargs.get("config") or {}
    run_dir, failure = _require_path(args, "run_dir")
    if failure:
        return _error(failure)
    output_raw = str(args.get("output_dir") or "").strip()
    if not output_raw:
        return _error("missing required argument: output_dir")
    rule_raw = str(args.get("rule_candidate") or "").strip()
    if not rule_raw:
        return _error("missing required argument: rule_candidate")
    horizon = str(args.get("horizon") or "d1").strip()
    if horizon not in {"d1", "d3"}:
        return _error("horizon must be one of: d1, d3")

    assert run_dir is not None
    checked_run, failure = _resolve_existing_under_root(
        ctx_config, run_dir, kind="directory"
    )
    if failure:
        return _error(failure)
    rule_candidate = Path(rule_raw).expanduser()
    checked_rule, failure = _resolve_existing_under_root(
        ctx_config, rule_candidate, kind="file"
    )
    if failure:
        return _error(failure)
    assert checked_rule is not None
    if checked_rule.suffix.lower() != ".json":
        return _error("rule_candidate must be a JSON file")
    checked_output, failure = _resolve_output_under_root(
        ctx_config, Path(output_raw)
    )
    if failure:
        return _error(failure)
    assert checked_run is not None and checked_output is not None
    argv = [
        "build-evidence-pack",
        f"--sample={checked_run}",
        f"--rule-candidate={checked_rule}",
        f"--horizon={horizon}",
        "--",
        str(checked_output),
    ]
    returncode, stdout, stderr = _run(ctx_config, argv)
    return _payload(returncode, stdout, stderr, argv, disclosure_key="build")


def _as_args(args: Any) -> dict[str, Any] | None:
    return args if isinstance(args, dict) else None


def _forbidden_operation(name: str) -> bool:
    lowered = name.lower()
    if any(lowered.startswith(prefix) for prefix in _FORBIDDEN_OPERATION_PREFIXES):
        return True
    return bool(set(re.split(r"[._-]+", lowered)) & _FORBIDDEN_OPERATION_TOKENS)


def _operation_name(args: Any) -> tuple[str | None, str | None]:
    values = _as_args(args)
    if values is None:
        return None, "arguments must be an object"
    raw = str(values.get("operation") or "").strip()
    if not raw:
        return None, "missing required argument: operation"
    if not _OPERATION_NAME.fullmatch(raw):
        return None, "operation must be a capability name"
    if _forbidden_operation(raw):
        return None, "operation is outside the read-only Hermes boundary"
    return raw, None


def _safe_operation_descriptor(entry: dict[str, Any]) -> dict[str, Any] | None:
    name = entry.get("name")
    if not isinstance(name, str) or not _OPERATION_NAME.fullmatch(name):
        return None
    if _forbidden_operation(name):
        return None
    if any(entry.get(field) is True for field in ("can_grant_approval", "grant_approval", "approval_grant")):
        return None
    permission = entry.get("permission")
    if isinstance(permission, str) and permission.lower() in {"grant", "approve"}:
        return None
    safe = {key: _redact(entry[key], key) for key in _SAFE_OPERATION_FIELDS if key in entry}
    safe["name"] = name
    if entry.get("network") is True or entry.get("network_required") is True:
        safe["network"] = True
        safe["network_disclosure"] = "core-authorized network access; no plugin authorization"
    if entry.get("human_only") is True or entry.get("secret_input") is True or entry.get("secret_output") is True or entry.get("setup") is True:
        safe["proposal_only"] = True
        safe["human_only"] = True
    if entry.get("human_only") is True:
        safe["human_only"] = True
    if entry.get("confirmation") is True:
        safe["human_approval_required"] = True
    if name == "permissions.request":
        safe["proposal_only"] = True
    return safe


def _descriptor_has_forbidden_authority(value: Any, key: str = "") -> bool:
    if isinstance(value, dict):
        for item_key, item in value.items():
            lowered = str(item_key).lower()
            if any(token in lowered for token in ("grant", "approve")) and item is True:
                return True
            if _descriptor_has_forbidden_authority(item, lowered):
                return True
    elif isinstance(value, list):
        return any(_descriptor_has_forbidden_authority(item, key) for item in value)
    elif isinstance(value, str) and key in {"permission", "permissions"}:
        return value.lower() in {"grant", "approve", "revoke"}
    return False


def _validate_capabilities(stdout: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(stdout.strip())
    except (TypeError, json.JSONDecodeError):
        return None, "capabilities output is not one JSON object"
    if not isinstance(payload, dict):
        return None, "capabilities output must be a JSON object"
    if payload.get("schema") != CAPABILITIES_SCHEMA:
        return None, f"unsupported capabilities schema: {payload.get('schema')!r}"
    if type(payload.get("protocol_version")) is not int or payload.get("protocol_version") != PROTOCOL_VERSION:
        return None, f"unsupported capabilities protocol version: {payload.get('protocol_version')!r}"
    operations = payload.get("operations")
    if not isinstance(operations, list):
        return None, "capabilities operations must be a list"
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in operations:
        if not isinstance(entry, dict):
            return None, "capabilities operation entries must be objects"
        safe = _safe_operation_descriptor(entry)
        if safe is None:
            if isinstance(entry.get("name"), str) and _forbidden_operation(entry["name"]):
                continue
            if _descriptor_has_forbidden_authority(entry):
                continue
            return None, "capabilities contain an unsafe or malformed operation"
        name = safe["name"]
        if name in seen:
            return None, f"duplicate capability operation: {name}"
        seen.add(name)
        normalized.append(safe)
    return {
        "schema": CAPABILITIES_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "operations": normalized,
    }, None


def _probe_capabilities(ctx_config: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    argv = ["capabilities", "--json"]
    returncode, stdout, stderr = _run(ctx_config, argv)
    if returncode != 0:
        return None, _error(
            "core CLI does not provide the required capabilities protocol",
            code="capabilities_command_failed",
            returncode=returncode,
            stderr=stderr.strip()[:4000],
        )
    capabilities, failure = _validate_capabilities(stdout)
    if failure:
        return None, _error(failure, code="capabilities_protocol_mismatch")
    assert capabilities is not None
    return capabilities, None


def smcub_capabilities(args: dict[str, Any], **kwargs: Any) -> str:
    ctx_config = kwargs.get("config") or {}
    capabilities, failure = _probe_capabilities(ctx_config)
    if failure:
        return failure
    assert capabilities is not None
    return json.dumps(
        _redact(
            {
                "status": "ok",
                "returncode": 0,
                "result": capabilities,
                "safety": SAFETY,
                "disclosures": _DISCLOSURES["capabilities"],
            }
        ),
        ensure_ascii=False,
    )


def _claims_approval(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"approval_granted", "permission_granted", "approved", "granted"} and item is True:
                return True
            if lowered == "status" and isinstance(item, str) and item.lower() in {"approved", "granted"}:
                return True
            if _claims_approval(item):
                return True
    elif isinstance(value, list):
        return any(_claims_approval(item) for item in value)
    return False


def smcub_operation(args: dict[str, Any], **kwargs: Any) -> str:
    values = _as_args(args)
    if values is None:
        return _error("arguments must be an object")
    operation, failure = _operation_name(values)
    if failure:
        return _error(failure)
    assert operation is not None

    ctx_config = kwargs.get("config") or {}
    capabilities, failure = _probe_capabilities(ctx_config)
    if failure:
        return failure
    assert capabilities is not None
    operation_entry = next(
        (entry for entry in capabilities["operations"] if entry["name"] == operation),
        None,
    )
    if operation_entry is None:
        return _error(
            f"operation is not advertised by the core capabilities response: {operation}",
            code="unsupported_operation",
        )

    if operation_entry.get("human_only") is True or operation_entry.get("secret_input") is True or operation_entry.get("secret_output") is True or operation_entry.get("setup") is True:
        return _error(
            "setup or secret-changing operations require a human-controlled proposal path",
            code="human_only_operation",
        )

    approval_id = str(values.get("approval_id") or "").strip()
    if approval_id and any(character.isspace() for character in approval_id):
        return _error("approval_id must be an opaque request identifier", code="invalid_approval_id")

    input_path, failure = _require_path(values, "input_path")
    if failure:
        return _error(failure)
    assert input_path is not None
    checked_input, failure = _resolve_existing_under_root(ctx_config, input_path, kind="file")
    if failure:
        return _error(failure)
    assert checked_input is not None
    if checked_input.suffix.lower() != ".json":
        return _error("input_path must be a JSON file")

    state_dir, failure = _resolve_configured_directory(ctx_config, "state_dir")
    if failure:
        return _error(failure)
    run_root, failure = _resolve_root(ctx_config)
    if failure:
        return _error(failure)
    assert state_dir is not None and run_root is not None

    argv = [
        "operation",
        operation,
        "--input",
        str(checked_input),
        "--principal",
        HERMES_PRINCIPAL,
        "--state-dir",
        str(state_dir),
        "--json",
        "--run-root",
        str(run_root),
    ]
    if approval_id:
        argv.extend(["--approval-id", approval_id])
    returncode, stdout, stderr = _run(ctx_config, argv)
    output = json.loads(_payload(returncode, stdout, stderr, argv, disclosure_key="operation"))
    operation_disclosure = dict(output.get("disclosures") or {})
    operation_disclosure["network"] = bool(operation_entry.get("network") or operation_entry.get("network_required"))
    operation_disclosure["authorization"] = "enforced by core PermissionStore"
    if operation_entry.get("account") is True:
        operation_disclosure["account"] = "authorized account query; no account mutation"
    if operation_entry.get("scope") is not None:
        operation_disclosure["scope"] = operation_entry["scope"]
    output["disclosures"] = operation_disclosure
    if operation == "permissions.request":
        if _claims_approval(output.get("result")):
            return _error(
                "Hermes cannot grant or approve permissions; only a proposal may be returned",
                code="approval_grant_rejected",
            )
        output["proposal_only"] = True
        output["approval_authority"] = "human_or_core_permission_store"
    return json.dumps(_redact(output), ensure_ascii=False)
