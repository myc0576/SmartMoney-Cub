from __future__ import annotations

import copy
import hashlib
import json
import socket
from pathlib import Path

import pytest

from onchain_helpers import BLOCK_HASH, RECIPIENT, SENDER, TOKEN, TX_HASH, toy_snapshot
from smartmoney_cub_harness.onchain_evidence import (
    build_onchain_evidence_pack,
    read_snapshot,
    replay_onchain_evidence_pack,
    safe_pack_path,
    strict_json_loads,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def _build(tmp_path: Path, snapshot: dict | None = None) -> Path:
    root = tmp_path / "pack"
    build_onchain_evidence_pack(root, snapshot or toy_snapshot())
    return root


def _reseal(root: Path, mutate=None) -> None:
    manifest = json.loads((root / "evidence_pack.json").read_text())
    for name in manifest["hashes"]:
        manifest["hashes"][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    if mutate:
        mutate(manifest)
    raw = json.dumps(manifest).encode()
    (root / "evidence_pack.json").write_bytes(raw)
    (root / "evidence_pack.sha256").write_text(hashlib.sha256(raw).hexdigest())


def test_offline_deterministic_claim_replay_and_seal(tmp_path, monkeypatch):
    def deny_network(*args, **kwargs):
        raise AssertionError("offline replay used network")

    monkeypatch.setattr(socket, "socket", deny_network)
    root = _build(tmp_path)
    first = replay_onchain_evidence_pack(root)
    assert first == replay_onchain_evidence_pack(root)
    assert first == json.loads((root / "replay_report.json").read_text())
    assert first["schema"] == "smartmoney_cub_onchain_evidence_replay.v1"
    assert first["evidence_status"] == "verified"
    assert [c["verdict"] for c in first["claims"]] == [
        "supported", "contradicted", "supported", "supported", "insufficient_evidence"]
    assert all(c["reason"] and c["evidence_locations"] for c in first["claims"])
    assert first["safety"] == SAFETY_DECLARATION
    assert "internal consistency" in " ".join(first["limitations"])
    assert "current" in " ".join(first["limitations"])


def test_null_receipt_is_valid_but_missing_receipt_file_is_invalid(tmp_path):
    snapshot = toy_snapshot()
    snapshot["receipt"] = None
    root = _build(tmp_path, snapshot)
    report = replay_onchain_evidence_pack(root)
    assert report["evidence_status"] == "verified"
    assert report["claims"][2]["verdict"] == "insufficient_evidence"
    assert report["claims"][3]["verdict"] == "insufficient_evidence"
    (root / "receipt.json").unlink()
    report = replay_onchain_evidence_pack(root)
    assert report["evidence_status"] == "invalid" and not report["claims"]


@pytest.mark.parametrize("change", [
    lambda s: s.update(chain_id=True),
    lambda s: s.update(chain_id=1),
    lambda s: s.update(chain_id=42161.0),
    lambda s: s.update(schema="smartmoney_cub_onchain_snapshot.v2"),
    lambda s: s.update(safety="unsafe"),
    lambda s: s.update(extra="unsealed"),
    lambda s: s["transaction"]["data"].update(chainId="0x1"),
    lambda s: s["transaction"]["data"].update(blockNumber="0x010"),
    lambda s: s["transaction"]["data"].update(transactionIndex="0x1"),
    lambda s: s["transaction"]["data"].update(hash="0x123"),
    lambda s: s["receipt"]["data"].update(transactionHash=BLOCK_HASH),
    lambda s: s["receipt"]["data"].update(blockHash=TX_HASH),
    lambda s: s["receipt"]["data"].update(blockNumber="0x11"),
    lambda s: s["receipt"]["data"].update(transactionIndex="0x1"),
    lambda s: s["receipt"]["data"].update(status="0x2"),
    lambda s: s["receipt"]["data"].update(status="0x0"),
    lambda s: s["block"]["data"].update(transactions=[BLOCK_HASH]),
    lambda s: s["block"]["data"].update(number="0x11"),
    lambda s: s["block"]["data"].update(hash=TX_HASH),
    lambda s: s["receipt"]["data"]["logs"][0].update(blockHash=TX_HASH),
    lambda s: s["receipt"]["data"]["logs"][0].update(transactionHash=BLOCK_HASH),
    lambda s: s["receipt"]["data"]["logs"][0].update(blockNumber="0x11"),
    lambda s: s["receipt"]["data"]["logs"][0].update(transactionIndex="0x1"),
    lambda s: s["receipt"]["data"]["logs"][0].update(removed=True),
    lambda s: s["receipt"]["data"]["logs"].append(copy.deepcopy(s["receipt"]["data"]["logs"][0])),
    lambda s: s["claims"].append(copy.deepcopy(s["claims"][0])),
    lambda s: s["claims"][0].update(value="not-an-address"),
    lambda s: s["claims"][0].update(extra=True),
    lambda s: s["claims"][2].update(value=True),
    lambda s: s["claims"][3].update(value="0x" + "f" * 65),
    lambda s: s["claims"][3].pop("contract"),
    lambda s: s["claims"][4].update(value=float("nan")),
    lambda s: s["claims"][4].update(value=(1, 2)),
    lambda s: s["finality_observation"]["data"].update(blockHash=TX_HASH),
    lambda s: s["finality_observation"]["data"].update(tag="latest"),
])
def test_import_rejects_invalid_snapshot_before_writing(tmp_path, change):
    snapshot = toy_snapshot()
    change(snapshot)
    root = tmp_path / "pack"
    with pytest.raises(ValueError):
        build_onchain_evidence_pack(root, snapshot)
    assert not root.exists()


@pytest.mark.parametrize("field,value", [
    ("observed_at", "2026-01-02T12:00:00"),
    ("available_at", "2026-01-03T00:00:00Z"),
    ("observed_at", "nonsense"),
    ("available_at", "20260101"),
])
def test_envelopes_require_ordered_timezone_aware_timestamps(tmp_path, field, value):
    snapshot = toy_snapshot()
    snapshot["transaction"][field] = value
    with pytest.raises(ValueError):
        build_onchain_evidence_pack(tmp_path / "pack", snapshot)


def test_pre_decision_role_rejects_future_even_in_post_decision_mode(tmp_path):
    snapshot = toy_snapshot()
    snapshot["receipt"]["evidence_role"] = "pre_decision"
    with pytest.raises(ValueError, match="decision_time"):
        build_onchain_evidence_pack(tmp_path / "pack", snapshot)


def test_pre_decision_evaluation_excludes_post_decision_envelopes(tmp_path):
    snapshot = toy_snapshot()
    snapshot["evaluation_mode"] = "pre_decision"
    root = _build(tmp_path, snapshot)
    report = replay_onchain_evidence_pack(root)
    assert report["evidence_status"] == "verified"
    assert all(c["verdict"] == "insufficient_evidence" for c in report["claims"])


def test_pre_decision_eval_uses_only_eligible_envelope(tmp_path):
    snapshot = toy_snapshot()
    snapshot["evaluation_mode"] = "pre_decision"
    snapshot["transaction"].update(evidence_role="pre_decision", observed_at="2025-12-31T23:00:00Z",
                                   available_at="2025-12-31T23:00:00+00:00")
    report = replay_onchain_evidence_pack(_build(tmp_path, snapshot))
    assert report["claims"][0]["verdict"] == "supported"
    assert report["claims"][2]["verdict"] == "insufficient_evidence"


@pytest.mark.parametrize("change", [
    lambda log: log.update(address=SENDER),
    lambda log: log["topics"].__setitem__(1, "0x" + "00" * 12 + RECIPIENT[2:]),
    lambda log: log["topics"].__setitem__(2, "0x" + "00" * 12 + SENDER[2:]),
    lambda log: log.update(data="0x" + f"{43:064x}"),
])
def test_event_requires_all_specified_parameters(tmp_path, change):
    snapshot = toy_snapshot()
    change(snapshot["receipt"]["data"]["logs"][0])
    report = replay_onchain_evidence_pack(_build(tmp_path, snapshot))
    assert report["claims"][3]["verdict"] == "contradicted"


@pytest.mark.parametrize("topics,data", [
    (None, "0x"),  # ERC721 has four topics and zero data bytes.
    ([], "0x"),
    (["0x" + "ff" * 32], "0x" + "00" * 32),
])
def test_topic_signature_alone_never_proves_erc20_transfer(tmp_path, topics, data):
    snapshot = toy_snapshot()
    log = snapshot["receipt"]["data"]["logs"][0]
    log["topics"] = log["topics"] + ["0x" + "00" * 32] if topics is None else log["topics"][:1] + topics
    log["data"] = data
    report = replay_onchain_evidence_pack(_build(tmp_path, snapshot))
    assert report["claims"][3]["verdict"] != "supported"


def test_nonzero_erc20_address_padding_cannot_support_claim(tmp_path):
    snapshot = toy_snapshot()
    snapshot["receipt"]["data"]["logs"][0]["topics"][1] = "0x" + "ff" * 12 + SENDER[2:]
    report = replay_onchain_evidence_pack(_build(tmp_path, snapshot))
    assert report["claims"][3]["verdict"] != "supported"


def test_contract_creation_recipient_is_null_not_contract_address(tmp_path):
    snapshot = toy_snapshot()
    snapshot["transaction"]["data"]["to"] = None
    snapshot["receipt"]["data"]["contractAddress"] = TOKEN
    snapshot["claims"] = [{"id": "creation", "type": "recipient", "value": None},
                          {"id": "not-token", "type": "recipient", "value": TOKEN}]
    report = replay_onchain_evidence_pack(_build(tmp_path, snapshot))
    assert [c["verdict"] for c in report["claims"]] == ["supported", "contradicted"]


def test_failed_receipt_without_logs_is_valid(tmp_path):
    snapshot = toy_snapshot()
    snapshot["receipt"]["data"].update(status="0x0", logs=[])
    report = replay_onchain_evidence_pack(_build(tmp_path, snapshot))
    assert report["claims"][2]["verdict"] == "contradicted"
    assert report["claims"][3]["verdict"] == "contradicted"


@pytest.mark.parametrize("kind", ["profit", "strategy_correctness", "balance", "intent", "new_unknown"])
def test_unsupported_semantics_are_insufficient(tmp_path, kind):
    snapshot = toy_snapshot()
    snapshot["claims"] = [{"id": "unknown", "type": kind, "arbitrary": {"value": 1}}]
    assert replay_onchain_evidence_pack(_build(tmp_path, snapshot))["claims"][0]["verdict"] == "insufficient_evidence"


@pytest.mark.parametrize("name", ["transaction.json", "receipt.json", "block.json", "claims.json",
                                   "evidence_pack.json", "evidence_pack.sha256"])
def test_missing_files_fail_closed(tmp_path, name):
    root = _build(tmp_path)
    (root / name).unlink()
    report = replay_onchain_evidence_pack(root)
    assert report["evidence_status"] == "invalid" and report["errors"] and not report["claims"]


def test_tamper_and_even_resealed_invalid_associations_fail_closed(tmp_path):
    root = _build(tmp_path)
    file = root / "receipt.json"
    receipt = json.loads(file.read_text())
    receipt["evidence"]["data"]["blockHash"] = TX_HASH
    file.write_text(json.dumps(receipt))
    assert replay_onchain_evidence_pack(root)["evidence_status"] == "invalid"
    _reseal(root)
    report = replay_onchain_evidence_pack(root)
    assert report["evidence_status"] == "invalid" and not report["claims"]


@pytest.mark.parametrize("bad_path", ["../escape", "C:/escape", "receipt.json:evil", "sub/receipt.json", "\\\\host\\share", "receipt.json\\evil"])
def test_manifest_paths_are_fixed_and_cannot_escape(tmp_path, bad_path):
    root = _build(tmp_path)
    _reseal(root, lambda m: m["files"].update(receipt=bad_path))
    assert replay_onchain_evidence_pack(root)["evidence_status"] == "invalid"
    with pytest.raises(ValueError):
        safe_pack_path(root, bad_path)


def test_hash_inventory_is_exact(tmp_path):
    root = _build(tmp_path)
    _reseal(root, lambda m: m["hashes"].update({"extra.json": "0" * 64}))
    assert replay_onchain_evidence_pack(root)["evidence_status"] == "invalid"


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":-Infinity}', '{"a":1e999}'])
def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(raw):
    with pytest.raises(ValueError):
        strict_json_loads(raw)


def test_resealed_duplicate_json_key_is_invalid(tmp_path):
    root = _build(tmp_path)
    file = root / "transaction.json"
    raw = file.read_text()
    file.write_text(raw.replace('"evidence":', '"evidence":null,"evidence":', 1))
    _reseal(root)
    assert replay_onchain_evidence_pack(root)["evidence_status"] == "invalid"


def test_existing_output_is_never_overwritten(tmp_path):
    root = _build(tmp_path)
    before = (root / "evidence_pack.json").read_bytes()
    with pytest.raises(ValueError):
        build_onchain_evidence_pack(root, toy_snapshot())
    assert (root / "evidence_pack.json").read_bytes() == before


@pytest.mark.parametrize("link_name", ["receipt.json", "evidence_pack.json", "evidence_pack.sha256", "replay_report.json"])
def test_linked_files_never_read_or_written(tmp_path, link_name):
    root = _build(tmp_path)
    target = tmp_path / "target"
    target.write_text("untouched")
    link = root / link_name
    link.unlink(missing_ok=True)
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink privilege unavailable: {exc}")
    report = replay_onchain_evidence_pack(root)
    assert report["evidence_status"] == "invalid" and not report["claims"]
    assert target.read_text() == "untouched"


def test_root_and_parent_directory_links_are_rejected(tmp_path):
    root = _build(tmp_path)
    link = tmp_path / "linked"
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink privilege unavailable: {exc}")
    assert replay_onchain_evidence_pack(link)["evidence_status"] == "invalid"
    with pytest.raises(ValueError):
        build_onchain_evidence_pack(link / "new", toy_snapshot())
    with pytest.raises(ValueError):
        read_snapshot(link / "claims.json")


def test_read_snapshot_requires_json_object_and_rejects_duplicate_keys(tmp_path):
    file = tmp_path / "snapshot.json"
    for raw in ('[]', '{"schema":1,"schema":2}'):
        file.write_text(raw)
        with pytest.raises(ValueError):
            read_snapshot(file)


@pytest.mark.parametrize("value", ["2026-01-02T12:00:00+00:60", "2026-01-02T12:00:00-01:99",
                                 "2026-01-02T12:00:00.000000001Z", "2026-01-02T12:00:00-00:00"])
def test_timestamp_offset_and_precision_cannot_be_normalized_into_acceptance(tmp_path, value):
    snapshot = toy_snapshot()
    snapshot["transaction"]["observed_at"] = value
    with pytest.raises(ValueError):
        build_onchain_evidence_pack(tmp_path / "pack", snapshot)


def test_rpc_block_nonce_is_fixed_bytes_while_transaction_nonce_is_quantity(tmp_path):
    snapshot = toy_snapshot()
    snapshot["block"]["data"]["nonce"] = "0x0000000000000000"
    snapshot["transaction"]["data"]["nonce"] = "0x0"
    report = replay_onchain_evidence_pack(_build(tmp_path, snapshot))
    assert report["evidence_status"] == "verified"


@pytest.mark.parametrize("key", ["transaction", "receipt", "block"])
def test_optional_chain_id_never_allows_another_chain(tmp_path, key):
    snapshot = toy_snapshot()
    snapshot[key]["data"]["chainId"] = "0x1"
    with pytest.raises(ValueError):
        build_onchain_evidence_pack(tmp_path / "pack", snapshot)


@pytest.mark.parametrize("field,value", [("from", RECIPIENT), ("to", SENDER), ("to", None)])
def test_optional_receipt_addresses_must_match_transaction(tmp_path, field, value):
    snapshot = toy_snapshot()
    snapshot["receipt"]["data"][field] = value
    with pytest.raises(ValueError):
        build_onchain_evidence_pack(tmp_path / "pack", snapshot)


def test_repeated_block_transaction_hash_is_invalid_even_with_different_case(tmp_path):
    snapshot = toy_snapshot()
    snapshot["block"]["data"]["transactions"].append(TX_HASH.upper().replace("0X", "0x"))
    with pytest.raises(ValueError):
        build_onchain_evidence_pack(tmp_path / "pack", snapshot)


def test_unknown_event_is_insufficient_and_keeps_unrecognized_parameters(tmp_path):
    snapshot = toy_snapshot()
    snapshot["claims"] = [{"id": "new-event", "type": "event", "event_type": "unknown", "parameters": [1, 2]}]
    root = _build(tmp_path, snapshot)
    assert json.loads((root / "claims.json").read_text())["claims"] == snapshot["claims"]
    assert replay_onchain_evidence_pack(root)["claims"][0]["verdict"] == "insufficient_evidence"


@pytest.mark.parametrize("value", [None, [], True, "42161", {}, 0])
def test_malformed_snapshot_types_fail_with_value_error_without_writes(tmp_path, value):
    snapshot = toy_snapshot()
    snapshot["transaction"] = value
    with pytest.raises(ValueError):
        build_onchain_evidence_pack(tmp_path / "pack", snapshot)


def test_linked_report_hardlink_does_not_overwrite_external_target(tmp_path):
    root = _build(tmp_path)
    target = tmp_path / "target"
    target.write_text("untouched")
    try:
        (root / "replay_report.json").hardlink_to(target)
    except OSError as exc:
        pytest.skip(f"hardlink unavailable: {exc}")
    report = replay_onchain_evidence_pack(root)
    assert report["evidence_status"] == "verified"
    assert target.read_text() == "untouched"


@pytest.mark.parametrize("network_path", ["\\\\server\\share\\snapshot.json", "//server/share/snapshot.json"])
def test_unc_paths_are_rejected_before_any_filesystem_access(monkeypatch, network_path):
    def deny_stat(*args, **kwargs):
        raise AssertionError("UNC path must not trigger network filesystem access")

    monkeypatch.setattr(Path, "lstat", deny_stat)
    with pytest.raises(ValueError):
        read_snapshot(network_path)


def test_status_and_events_can_be_proven_before_decision_with_explicit_eligible_evidence(tmp_path):
    snapshot = toy_snapshot()
    snapshot["evaluation_mode"] = "pre_decision"
    for key in ("transaction", "receipt", "block", "finality_observation"):
        snapshot[key].update(evidence_role="pre_decision", observed_at="2025-12-31T20:00:00-03:00",
                             available_at="2025-12-31T21:00:00-02:00")
    report = replay_onchain_evidence_pack(_build(tmp_path, snapshot))
    assert report["claims"][2]["verdict"] == "supported"
    assert report["claims"][3]["verdict"] == "supported"


def test_actual_positive_timezone_future_is_rejected(tmp_path):
    snapshot = toy_snapshot()
    snapshot["transaction"].update(evidence_role="pre_decision", observed_at="2026-01-01T02:00:00+01:00",
                                   available_at="2026-01-01T01:00:00Z")
    with pytest.raises(ValueError, match="decision_time"):
        build_onchain_evidence_pack(tmp_path / "pack", snapshot)


def test_report_location_is_relative_and_finality_is_only_original_observation(tmp_path):
    snapshot = toy_snapshot()
    report = replay_onchain_evidence_pack(_build(tmp_path, snapshot))
    assert report["finality_observation"] == snapshot["finality_observation"]
    assert "finalized" not in report and "safe" not in report
    assert all(not Path(loc.split("#", 1)[0]).is_absolute()
               for claim in report["claims"] for loc in claim["evidence_locations"])
