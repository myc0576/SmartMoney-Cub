"""Entirely invented, frozen chain data for offline tests."""
from __future__ import annotations

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

TX_HASH = "0x" + "11" * 32
BLOCK_HASH = "0x" + "22" * 32
SENDER = "0x" + "33" * 20
RECIPIENT = "0x" + "44" * 20
TOKEN = "0x" + "55" * 20
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def toy_snapshot() -> dict:
    def envelope(data: dict) -> dict:
        return {
            "source": "toy-offline-provider",
            "observed_at": "2026-01-02T12:00:00Z",
            "available_at": "2026-01-02T11:59:00+00:00",
            "evidence_role": "post_decision",
            "data": data,
        }

    log = {
        "address": TOKEN, "topics": [TRANSFER_TOPIC, "0x" + "00" * 12 + SENDER[2:],
                                      "0x" + "00" * 12 + RECIPIENT[2:]],
        "data": "0x" + f"{42:064x}", "blockHash": BLOCK_HASH, "blockNumber": "0x10",
        "transactionHash": TX_HASH, "transactionIndex": "0x0", "logIndex": "0x2", "removed": False,
    }
    return {
        "schema": "smartmoney_cub_onchain_snapshot.v1", "chain_id": 42161,
        "decision_time": "2026-01-01T00:00:00Z", "evaluation_mode": "post_decision",
        "transaction": envelope({"hash": TX_HASH, "chainId": "0xa4b1", "from": SENDER,
                                 "to": RECIPIENT, "blockHash": BLOCK_HASH, "blockNumber": "0x10",
                                 "transactionIndex": "0x0"}),
        "receipt": envelope({"transactionHash": TX_HASH, "transactionIndex": "0x0",
                             "blockHash": BLOCK_HASH, "blockNumber": "0x10", "status": "0x1",
                             "logs": [log]}),
        "block": envelope({"hash": BLOCK_HASH, "number": "0x10", "transactions": [TX_HASH]}),
        "claims": [
            {"id": "sender-ok", "type": "sender", "value": SENDER},
            {"id": "recipient-no", "type": "recipient", "value": SENDER},
            {"id": "status-ok", "type": "execution_status", "value": "success"},
            {"id": "transfer-ok", "type": "event", "event_type": "erc20_transfer",
             "contract": TOKEN, "from": SENDER, "to": RECIPIENT, "value": "0x2a"},
            {"id": "profit-unknown", "type": "profit", "value": 100},
        ],
        "finality_observation": envelope({"tag": "safe", "blockHash": BLOCK_HASH, "blockNumber": "0x10"}),
        "safety": SAFETY_DECLARATION,
    }
