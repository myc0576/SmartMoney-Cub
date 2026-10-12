"""Versioned, offline Arbitrum transaction evidence; no provider or wallet access.

The unkeyed seal establishes internal consistency, never source authenticity or
current chain finality. Only explicitly supported, narrowly scoped claims are
evaluated; arbitrary Agent text is preserved without granting it authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

ONCHAIN_SNAPSHOT_SCHEMA = "smartmoney_cub_onchain_snapshot.v1"
ONCHAIN_EVIDENCE_PACK_SCHEMA = "smartmoney_cub_onchain_evidence_pack.v1"
ONCHAIN_EVIDENCE_REPLAY_SCHEMA = "smartmoney_cub_onchain_evidence_replay.v1"
CHAIN_ID = 42161
PACK_MANIFEST_NAME = "evidence_pack.json"
PACK_SEAL_NAME = "evidence_pack.sha256"
REPORT_NAME = "replay_report.json"
FILES = {"transaction": "transaction.json", "receipt": "receipt.json", "block": "block.json", "claims": "claims.json"}
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_ROLES = {"pre_decision", "post_decision"}
_SNAPSHOT_FIELDS = {"schema", "chain_id", "decision_time", "evaluation_mode", "transaction", "receipt", "block", "claims", "finality_observation", "safety"}
_MANIFEST_FIELDS = {"schema", "snapshot_schema", "chain_id", "decision_time", "evaluation_mode", "files", "hashes", "finality_observation", "safety"}
LIMITATIONS = [
    "The evidence seal verifies internal consistency only; it does not authenticate the source or prove that the frozen data occurred on-chain.",
    "Safe/finalized tags are provider observations at capture time, not proof of current chain finality; neither receipt success nor a snapshot hash proves finality.",
    "Receipt status describes recorded execution only. Events describe recorded log fields only, not profit, strategy correctness, actual asset balances, intent, or token-contract authenticity.",
    "Post-decision evidence supports retrospective review only. Pre-decision evaluation excludes every post-decision envelope.",
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _json_value(value: Any) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        _require(math.isfinite(value), "non-finite JSON number")
    elif type(value) is list:
        for item in value:
            _json_value(item)
    elif type(value) is dict:
        for key, item in value.items():
            _require(type(key) is str, "JSON object keys must be strings")
            _json_value(item)
    else:
        raise ValueError("input must contain only JSON values")


def strict_json_loads(content: str | bytes) -> Any:
    """Reject ambiguous duplicate keys and non-standard/non-finite JSON numbers."""
    def pairs(items: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in items:
            _require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON number: {value}")

    try:
        result = json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
        _json_value(result)
        return result
    except (TypeError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid JSON") from exc


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _checked_path(path: str | Path) -> Path:
    """Check lexical components before resolution; reject links/reparse points.

    Checking every existing ancestor catches both symlinks and Windows junctions,
    including a linked pack root. A Windows reparse point is conservatively unsafe.
    """
    _require(not str(path).startswith(("\\\\", "//")), "network or device paths are not allowed in offline evidence")
    candidate = Path(path)
    for component in candidate.parts:
        if component == candidate.anchor:
            continue
        _require(component not in {"..", "."} and not any(c in component for c in ':<>|?*'), "unsafe path component")
        _require(not component.endswith((" ", ".")), "unsafe path component")
    candidate = candidate.absolute()
    for item in [*reversed(candidate.parents), candidate]:
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        _require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, "st_file_attributes", 0) & 0x400), "symbolic link or reparse point is not allowed")
        if item != candidate:
            _require(stat.S_ISDIR(info.st_mode), "path parent must be a directory")
    return candidate


def safe_pack_path(root: Path, filename: str) -> Path:
    """Return only one of the fixed v1 pack paths, after checking its ancestors."""
    _require(filename in {*FILES.values(), PACK_MANIFEST_NAME, PACK_SEAL_NAME, REPORT_NAME}, "unsafe or unknown pack filename")
    return _checked_path(Path(root) / filename)


def read_snapshot(path: str | Path) -> dict:
    """Read a local input JSON object without following links or junctions."""
    try:
        checked = _checked_path(path)
        _require(checked.is_file(), "snapshot must be a regular file")
        value = strict_json_loads(checked.read_bytes())
        _require(isinstance(value, dict), "snapshot must be a JSON object")
        return value
    except OSError as exc:
        raise ValueError("snapshot could not be read") from exc


def _object(value: Any, location: str, required: set[str], *, exact: bool = False) -> dict:
    _require(isinstance(value, dict), f"{location}: expected object")
    _require(set(value) == required if exact else required <= set(value), f"{location}: invalid fields")
    return value


def _hex(value: Any, size: int, location: str) -> str:
    _require(isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{" + str(size * 2) + "}", value) is not None, f"{location}: expected {size}-byte hex")
    return value.lower()


def _quantity(value: Any, location: str, max_value: int | None = None) -> int:
    _require(isinstance(value, str) and re.fullmatch(r"0x(?:0|[1-9a-f][0-9a-f]*)", value) is not None, f"{location}: expected canonical hex quantity")
    number = int(value[2:], 16)
    _require(max_value is None or number <= max_value, f"{location}: quantity exceeds maximum")
    return number


def _time(value: Any, location: str) -> datetime:
    _require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value) is not None, f"{location}: expected timezone-aware RFC3339 timestamp with at most microsecond precision")
    if not value.endswith("Z"):
        _require(int(value[-5:-3]) <= 23 and int(value[-2:]) <= 59, f"{location}: invalid timezone offset")
        _require(not value.endswith("-00:00"), f"{location}: unknown local offset -00:00 is not an explicit timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(result.utcoffset() is not None, f"{location}: timezone required")
        return result
    except ValueError as exc:
        raise ValueError(f"{location}: invalid timestamp") from exc


def _envelope(value: Any, location: str, decision_time: datetime) -> dict:
    env = _object(value, location, {"source", "observed_at", "available_at", "evidence_role", "data"}, exact=True)
    _require(isinstance(env["source"], str) and bool(env["source"].strip()), f"{location}: source required")
    _require(env["evidence_role"] in _ROLES if isinstance(env["evidence_role"], str) else False, f"{location}: invalid evidence_role")
    observed = _time(env["observed_at"], f"{location}.observed_at")
    available = _time(env["available_at"], f"{location}.available_at")
    _require(available <= observed, f"{location}: available_at exceeds observed_at")
    if env["evidence_role"] == "pre_decision":
        _require(observed <= decision_time and available <= decision_time, f"{location}: pre_decision evidence exceeds decision_time")
    _require(isinstance(env["data"], dict), f"{location}.data: expected object")
    return env["data"]


def _optional_rpc_fields(data: dict, location: str) -> None:
    """Validate retained standard RPC fields even when not used by claim logic."""
    for key in ("gas", "gasPrice", "value", "type", "maxFeePerGas", "maxPriorityFeePerGas", "gasUsed", "cumulativeGasUsed", "effectiveGasPrice", "timestamp", "baseFeePerGas", "gasLimit", "size", "difficulty", "totalDifficulty", "blobGasUsed", "excessBlobGas"):
        if key in data:
            _quantity(data[key], f"{location}.{key}")
    if "nonce" in data:
        if location == "block":
            _hex(data["nonce"], 8, "block.nonce")
        else:
            _quantity(data["nonce"], f"{location}.nonce")
    for key in ("from", "to", "contractAddress"):
        if key in data and not (key in {"to", "contractAddress"} and data[key] is None):
            _hex(data[key], 20, f"{location}.{key}")
    if "chainId" in data:
        _require(_quantity(data["chainId"], f"{location}.chainId") == CHAIN_ID, f"{location}: wrong chainId")


def _claims(value: Any) -> list[dict]:
    _require(isinstance(value, list), "claims: expected array")
    ids = set()
    for claim in value:
        _object(claim, "claim", {"id", "type"})
        _require(isinstance(claim["id"], str) and bool(claim["id"].strip()), "claim.id: nonempty string required")
        _require(claim["id"] not in ids, "claim.id: duplicate")
        ids.add(claim["id"])
        kind = claim["type"]
        _require(isinstance(kind, str) and bool(kind.strip()), "claim.type: nonempty string required")
        if kind in {"sender", "recipient", "execution_status"}:
            _object(claim, "claim", {"id", "type", "value"}, exact=True)
            if kind == "execution_status":
                _require(isinstance(claim["value"], str) and claim["value"] in {"success", "failure"}, "claim.value: expected success/failure")
            elif not (kind == "recipient" and claim["value"] is None):
                _hex(claim["value"], 20, "claim.value")
        elif kind == "event":
            _require(isinstance(claim.get("event_type"), str) and bool(claim["event_type"].strip()), "claim.event_type: required")
            if claim["event_type"] == "erc20_transfer":
                _object(claim, "claim", {"id", "type", "event_type", "contract", "from", "to", "value"}, exact=True)
                for key in ("contract", "from", "to"):
                    _hex(claim[key], 20, f"claim.{key}")
                _quantity(claim["value"], "claim.value", (1 << 256) - 1)
    return value


def _validate_snapshot(snapshot: dict) -> None:
    try:
        _json_value(snapshot)
    except RecursionError as exc:
        raise ValueError("snapshot must be acyclic JSON") from exc
    _object(snapshot, "snapshot", _SNAPSHOT_FIELDS, exact=True)
    _require(snapshot["schema"] == ONCHAIN_SNAPSHOT_SCHEMA, "snapshot: unsupported schema")
    _require(type(snapshot["chain_id"]) is int and snapshot["chain_id"] == CHAIN_ID, "snapshot: chain_id must be integer 42161")
    _require(snapshot["safety"] == SAFETY_DECLARATION, "snapshot: invalid safety declaration")
    _require(isinstance(snapshot["evaluation_mode"], str) and snapshot["evaluation_mode"] in _ROLES, "snapshot: invalid evaluation_mode")
    decision = _time(snapshot["decision_time"], "decision_time")
    tx = _envelope(snapshot["transaction"], "transaction", decision)
    _object(tx, "transaction.data", {"hash", "chainId", "from", "to", "blockHash", "blockNumber", "transactionIndex"})
    tx_hash = _hex(tx["hash"], 32, "transaction.hash")
    block_hash = _hex(tx["blockHash"], 32, "transaction.blockHash")
    block_number = _quantity(tx["blockNumber"], "transaction.blockNumber")
    tx_index = _quantity(tx["transactionIndex"], "transaction.transactionIndex")
    _optional_rpc_fields(tx, "transaction")
    block = _envelope(snapshot["block"], "block", decision)
    _object(block, "block.data", {"hash", "number", "transactions"})
    _require(_hex(block["hash"], 32, "block.hash") == block_hash, "block: blockHash mismatch")
    _require(_quantity(block["number"], "block.number") == block_number, "block: blockNumber mismatch")
    _require(isinstance(block["transactions"], list), "block.transactions: expected hash array")
    block_txs = [_hex(item, 32, "block.transactions") for item in block["transactions"]]
    _require(len(set(block_txs)) == len(block_txs), "block.transactions: duplicate transaction")
    _require(tx_index < len(block_txs) and block_txs[tx_index] == tx_hash, "block.transactions: transaction index membership mismatch")
    _optional_rpc_fields(block, "block")
    if snapshot["receipt"] is not None:
        receipt = _envelope(snapshot["receipt"], "receipt", decision)
        _object(receipt, "receipt.data", {"transactionHash", "transactionIndex", "blockHash", "blockNumber", "status", "logs"})
        _association(receipt, "receipt", tx_hash, block_hash, block_number, tx_index)
        _optional_rpc_fields(receipt, "receipt")
        for key in ("from", "to"):
            if key in receipt:
                _require(_same_hex(receipt[key], tx[key]), f"receipt.{key}: transaction mismatch")
        status = _quantity(receipt["status"], "receipt.status", 1)
        _require(isinstance(receipt["logs"], list), "receipt.logs: expected array")
        _require(status != 0 or not receipt["logs"], "receipt: failed execution conflicts with emitted logs")
        seen = set()
        for log in receipt["logs"]:
            _object(log, "log", {"address", "topics", "data", "blockHash", "blockNumber", "transactionHash", "transactionIndex", "logIndex", "removed"})
            _association(log, "log", tx_hash, block_hash, block_number, tx_index)
            _hex(log["address"], 20, "log.address")
            _require(log["removed"] is False, "log.removed must be false")
            index = _quantity(log["logIndex"], "log.logIndex")
            _require(index not in seen, "log.logIndex: duplicate or conflicting log")
            seen.add(index)
            _require(isinstance(log["topics"], list) and len(log["topics"]) <= 4, "log.topics: expected up to four topics")
            for topic in log["topics"]:
                _hex(topic, 32, "log.topic")
            _require(isinstance(log["data"], str) and re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", log["data"]) is not None, "log.data: expected hex bytes")
            _optional_rpc_fields(log, "log")
    finality = snapshot["finality_observation"]
    if finality is not None:
        observation = _envelope(finality, "finality_observation", decision)
        _object(observation, "finality_observation.data", {"tag", "blockHash", "blockNumber"}, exact=True)
        _require(isinstance(observation["tag"], str) and observation["tag"] in {"safe", "finalized"}, "finality_observation.tag: expected safe/finalized")
        _require(_hex(observation["blockHash"], 32, "finality_observation.blockHash") == block_hash, "finality_observation: blockHash mismatch")
        _require(_quantity(observation["blockNumber"], "finality_observation.blockNumber") == block_number, "finality_observation: blockNumber mismatch")
    _claims(snapshot["claims"])


def _association(data: dict, location: str, tx_hash: str, block_hash: str, block_number: int, tx_index: int) -> None:
    for key, wanted in (("transactionHash", tx_hash), ("blockHash", block_hash)):
        _require(_hex(data[key], 32, f"{location}.{key}") == wanted, f"{location}.{key}: mismatch")
    for key, wanted in (("blockNumber", block_number), ("transactionIndex", tx_index)):
        _require(_quantity(data[key], f"{location}.{key}") == wanted, f"{location}.{key}: mismatch")


def _same_hex(left: str | None, right: str | None) -> bool:
    return (left.lower() if left is not None else None) == (right.lower() if right is not None else None)


def build_onchain_evidence_pack(output_dir: str | Path, snapshot: dict) -> dict:
    """Validate and freeze one snapshot; never overwrite an existing directory."""
    _validate_snapshot(snapshot)
    try:
        root = _checked_path(output_dir)
        _require(not root.exists(), "output directory already exists")
        artifacts = {
            FILES[key]: {"evidence": snapshot[key], "safety": SAFETY_DECLARATION}
            for key in ("transaction", "receipt", "block")
        }
        artifacts[FILES["claims"]] = {"claims": snapshot["claims"], "safety": SAFETY_DECLARATION}
        content = {name: _canonical(value) for name, value in artifacts.items()}
        manifest = {
            "schema": ONCHAIN_EVIDENCE_PACK_SCHEMA, "snapshot_schema": ONCHAIN_SNAPSHOT_SCHEMA,
            "chain_id": snapshot["chain_id"], "decision_time": snapshot["decision_time"],
            "evaluation_mode": snapshot["evaluation_mode"], "files": dict(FILES),
            "hashes": {name: hashlib.sha256(raw).hexdigest() for name, raw in content.items()},
            "finality_observation": snapshot["finality_observation"], "safety": SAFETY_DECLARATION,
        }
        content[PACK_MANIFEST_NAME] = _canonical(manifest)
        content[PACK_SEAL_NAME] = (hashlib.sha256(content[PACK_MANIFEST_NAME]).hexdigest() + "\n").encode("ascii")
        root.mkdir(parents=True, exist_ok=False)
        for name, raw in content.items():
            with safe_pack_path(root, name).open("xb") as stream:
                stream.write(raw)
        return manifest
    except OSError as exc:
        raise ValueError("evidence pack could not be written") from exc


def _read_pack(root: Path) -> dict:
    _require(_checked_path(root).is_dir(), "pack root must be a directory")
    paths = {name: safe_pack_path(root, name) for name in [*FILES.values(), PACK_MANIFEST_NAME, PACK_SEAL_NAME, REPORT_NAME]}
    for name, path in paths.items():
        if name != REPORT_NAME:
            _require(path.is_file(), f"missing or non-regular pack file: {name}")
    raw = paths[PACK_MANIFEST_NAME].read_bytes()
    seal = paths[PACK_SEAL_NAME].read_text(encoding="ascii").strip()
    _require(re.fullmatch(r"[0-9a-f]{64}", seal) is not None, "invalid manifest seal")
    _require(hashlib.sha256(raw).hexdigest() == seal, "manifest seal mismatch")
    manifest = strict_json_loads(raw)
    _object(manifest, "manifest", _MANIFEST_FIELDS, exact=True)
    _require(manifest["schema"] == ONCHAIN_EVIDENCE_PACK_SCHEMA, "unsupported pack schema")
    _require(manifest["snapshot_schema"] == ONCHAIN_SNAPSHOT_SCHEMA, "unsupported snapshot schema")
    _require(manifest["files"] == FILES, "manifest: file inventory mismatch")
    _object(manifest["hashes"], "manifest.hashes", set(FILES.values()), exact=True)
    artifacts = {}
    for key, name in FILES.items():
        digest = manifest["hashes"][name]
        _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "invalid artifact hash")
        content = paths[name].read_bytes()
        _require(hashlib.sha256(content).hexdigest() == digest, f"artifact hash mismatch: {name}")
        artifact = strict_json_loads(content)
        field = "claims" if key == "claims" else "evidence"
        _object(artifact, name, {field, "safety"}, exact=True)
        _require(artifact["safety"] == SAFETY_DECLARATION, f"{name}: invalid safety declaration")
        artifacts[key] = artifact[field]
    snapshot = {key: manifest[key] for key in ("chain_id", "decision_time", "evaluation_mode", "finality_observation", "safety")}
    snapshot.update(schema=manifest["snapshot_schema"], **artifacts)
    _validate_snapshot(snapshot)
    return snapshot


def _eligible(snapshot: dict, key: str) -> bool:
    env = snapshot[key]
    return env is not None and (snapshot["evaluation_mode"] == "post_decision" or env["evidence_role"] == "pre_decision")


def _evaluate_claim(snapshot: dict, claim: dict, index: int) -> dict:
    result = {"id": claim["id"], "type": claim["type"], "verdict": "insufficient_evidence",
              "reason": "Unsupported claim semantics; these frozen records cannot establish this claim.",
              "evidence_locations": [f"claims.json#/claims/{index}"]}
    kind = claim["type"]
    if kind not in {"sender", "recipient", "execution_status", "event"} or (kind == "event" and claim["event_type"] != "erc20_transfer"):
        return result
    key = "transaction" if kind in {"sender", "recipient"} else "receipt"
    location = FILES[key] + "#/evidence"
    result["evidence_locations"].append(location)
    if not _eligible(snapshot, key):
        result["reason"] = "Required evidence is explicitly unavailable or excluded by the pre-decision evidence cutoff."
        return result
    data = snapshot[key]["data"]
    if kind in {"sender", "recipient"}:
        field = "from" if kind == "sender" else "to"
        matches = _same_hex(data[field], claim["value"])
        result.update(verdict="supported" if matches else "contradicted",
                      reason=f"Frozen transaction {field} {'matches' if matches else 'does not match'} the asserted address (null recipient means contract creation).")
        result["evidence_locations"].append(location + "/data/" + field)
    elif kind == "execution_status":
        actual = "success" if data["status"] == "0x1" else "failure"
        result.update(verdict="supported" if actual == claim["value"] else "contradicted",
                      reason=f"Frozen receipt records execution {actual}; this does not establish economic success or finality.")
        result["evidence_locations"].append(location + "/data/status")
    else:
        return _event_verdict(result, data["logs"], claim, location + "/data/logs")
    return result


def _event_verdict(result: dict, logs: list[dict], claim: dict, location: str) -> dict:
    ambiguous = False
    for index, log in enumerate(logs):
        topics = log["topics"]
        if not _same_hex(log["address"], claim["contract"]) or not topics or topics[0].lower() != TRANSFER_TOPIC:
            continue
        pointer = location + f"/{index}"
        result["evidence_locations"].append(pointer)
        if len(topics) != 3 or len(log["data"]) != 66 or any(topic[2:26] != "0" * 24 for topic in topics[1:]):
            ambiguous = True
            continue
        matches = (_same_hex("0x" + topics[1][26:], claim["from"])
                   and _same_hex("0x" + topics[2][26:], claim["to"])
                   and int(log["data"][2:], 16) == int(claim["value"][2:], 16))
        if matches:
            result.update(verdict="supported", reason="Frozen log matches the specified contract, exact ERC20 Transfer layout, sender, recipient and raw uint256 value; no balance or profit is inferred.")
            return result
    if ambiguous:
        result.update(verdict="insufficient_evidence", reason="Matching contract/signature has an incompatible or ambiguous event layout; a Transfer signature alone cannot establish an ERC20 Transfer (including ERC721 logs).")
    else:
        result.update(verdict="contradicted", reason="The complete frozen receipt contains no ERC20 Transfer log matching every specified parameter.")
        result["evidence_locations"].append(location)
    return result


def _write_report(root: Path, report: dict) -> None:
    target = safe_pack_path(root, REPORT_NAME)
    _require(root.is_dir(), "pack root must be a directory")
    if target.exists():
        _require(target.is_file(), "report must be a regular file")
    # Atomic replacement avoids writing through pre-existing hard links, too.
    descriptor, temporary = tempfile.mkstemp(prefix=".replay-report-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(report))
        safe_pack_path(root, REPORT_NAME)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def replay_onchain_evidence_pack(pack_dir: str | Path) -> dict:
    """Verify sealed content and replay supported claims deterministically offline."""
    report = {"schema": ONCHAIN_EVIDENCE_REPLAY_SCHEMA, "evidence_status": "invalid",
              "chain_id": CHAIN_ID, "errors": [], "claims": [], "limitations": list(LIMITATIONS),
              "finality_observation": None, "safety": SAFETY_DECLARATION}
    root = Path(pack_dir)
    try:
        snapshot = _read_pack(root)
        report.update(evidence_status="verified", evaluation_mode=snapshot["evaluation_mode"],
                      decision_time=snapshot["decision_time"], finality_observation=snapshot["finality_observation"],
                      claims=[_evaluate_claim(snapshot, claim, index) for index, claim in enumerate(snapshot["claims"])])
        _write_report(root, report)
    except (ValueError, OSError, UnicodeError, RecursionError) as exc:
        report.update(evidence_status="invalid", claims=[], errors=[str(exc)])
        try:
            _write_report(root, report)
        except (ValueError, OSError):
            pass  # Unsafe or inaccessible paths must never receive a report write.
    return report
