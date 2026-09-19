"""Tests for DSH plugin stdio integration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from smartmoney_cub_harness.agent.dsh_bridge import DSH_PROFILE, DSH_PROTOCOL
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


def test_dsh_plugin_stdio():
    plugin_bin = Path("npm/dsh-plugin/bin/dsh-plugin.js").resolve()
    proc = subprocess.Popen(
        ["node", str(plugin_bin)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # 1. Heartbeat
    req_hb = {"jsonrpc": "2.0", "id": 1, "method": "heartbeat"}
    proc.stdin.write(json.dumps(req_hb) + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    resp_hb = json.loads(line)
    assert resp_hb["id"] == 1
    assert resp_hb["result"]["alive"] is True
    assert resp_hb["safety"] == SAFETY_DECLARATION

    # 2. Handshake
    req_hs = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "handshake",
        "params": {
            "protocol": DSH_PROTOCOL,
            "profile": {
                "name": DSH_PROFILE,
                "protocol": DSH_PROTOCOL,
                "safety": SAFETY_DECLARATION,
                "allow_network": False,
                "allow_shell": False,
                "allow_filesystem": False,
                "allow_credentials": False,
            },
            "envelope": {
                "review_id": "rev-test-01",
                "payload": {"status": "ok"},
            },
        },
    }
    proc.stdin.write(json.dumps(req_hs) + "\n")
    proc.stdin.flush()
    resp_hs = json.loads(proc.stdout.readline())
    assert resp_hs["id"] == 2
    assert resp_hs["result"]["accepted"] is True
    assert resp_hs["result"]["protocol"] == DSH_PROTOCOL
    assert "review_envelope" in resp_hs["result"]["capabilities"]

    # 3. Teardown
    req_td = {"jsonrpc": "2.0", "id": 3, "method": "teardown"}
    proc.stdin.write(json.dumps(req_td) + "\n")
    proc.stdin.flush()
    resp_td = json.loads(proc.stdout.readline())
    assert resp_td["id"] == 3
    assert resp_td["result"]["teardown"] is True
    assert resp_td["safety"] == SAFETY_DECLARATION

    proc.wait(timeout=5)
    assert proc.returncode == 0

