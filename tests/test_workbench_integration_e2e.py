"""End-to-end integration tests for Workbench server and its ecosystem APIs.

Validates:
1. Starts the workbench server on an ephemeral loopback port
2. Queries /api/jev/status, /api/jev/tracks, /api/agents, /api/benchmark/latest
3. Asserts payload response shapes, fields, and HTTP 200 status
4. Asserts presence of SAFETY_DECLARATION in every response
5. Cleanly tears down the server and workbench services
"""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workbench.server import WorkbenchHandler, WorkbenchService


@pytest.fixture
def workbench_server(tmp_path: Path):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    service = WorkbenchService(state_dir)
    handler = type(
        "WorkbenchE2EHandler",
        (WorkbenchHandler,),
        {"service": service, "asset_dir": None, "access_token": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"
    try:
        yield base_url, service
    finally:
        server.shutdown()
        server.server_close()
        service.close()


def _fetch_json(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_workbench_integration_e2e(workbench_server):
    base_url, _ = workbench_server

    # 1. /api/jev/status
    status, jev_status = _fetch_json(f"{base_url}/api/jev/status")
    assert status == 200
    assert jev_status["safety"] == SAFETY_DECLARATION
    assert jev_status["engine"] == "jev"
    assert "provider_id" in jev_status
    assert "model_requested" in jev_status
    assert "model_resolved" in jev_status
    assert "available" in jev_status
    assert "backends" in jev_status
    assert isinstance(jev_status["backends"], dict)

    # 2. /api/jev/tracks
    status, jev_tracks = _fetch_json(f"{base_url}/api/jev/tracks")
    assert status == 200
    assert jev_tracks["safety"] == SAFETY_DECLARATION
    tracks = jev_tracks.get("tracks", [])
    assert len(tracks) == 4
    track_ids = {t["track"] for t in tracks}
    assert track_ids == {"trading-review", "financial-filings", "industry-events", "macro-policy"}
    for t in tracks:
        assert t["question_count"] > 0
        assert t["case_count"] > 0
        assert "questions" in t
        assert len(t["questions"]) == t["question_count"]

    # 3. /api/agents
    status, agents_resp = _fetch_json(f"{base_url}/api/agents")
    assert status == 200
    assert agents_resp["safety"] == SAFETY_DECLARATION
    agents = agents_resp.get("agents", [])
    assert isinstance(agents, list)
    assert len(agents) >= 6
    agent_ids = {a["agent_id"] for a in agents}
    for expected_agent in ("codex", "claude-code", "deepseek-harness", "opencode", "gemini-cli", "pi"):
        assert expected_agent in agent_ids

    # 4. /api/benchmark/latest
    status, bench_resp = _fetch_json(f"{base_url}/api/benchmark/latest")
    assert status == 200
    assert bench_resp["safety"] == SAFETY_DECLARATION
    assert "run_id" in bench_resp
    assert "systems" in bench_resp
    assert "tracks" in bench_resp
    assert "images" in bench_resp
    if bench_resp["run_id"] is not None:
        assert isinstance(bench_resp["systems"], list)
        assert isinstance(bench_resp["images"], list)
