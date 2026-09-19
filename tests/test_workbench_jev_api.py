from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workbench.server import WorkbenchHandler, WorkbenchService


def _service(root: Path) -> WorkbenchService:
    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return WorkbenchService(state_dir)


@pytest.fixture
def http_server(tmp_path: Path):
    service = _service(tmp_path)
    handler = type(
        "TestHandler",
        (WorkbenchHandler,),
        {"service": service, "asset_dir": None, "access_token": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        yield base, service
    finally:
        server.shutdown()
        server.server_close()
        service.close()


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


def _post(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


def test_jev_status_endpoint(http_server):
    base, _ = http_server
    status, body = _get(f"{base}/api/jev/status")
    assert status == 200
    assert body["safety"] == SAFETY_DECLARATION
    assert body["engine"] == "jev"
    assert "provider_id" in body
    assert "model_requested" in body
    assert "available" in body
    assert "backends" in body


def test_jev_tracks_endpoint(http_server):
    base, _ = http_server
    status, body = _get(f"{base}/api/jev/tracks")
    assert status == 200
    assert body["safety"] == SAFETY_DECLARATION
    tracks = body["tracks"]
    assert len(tracks) == 4
    track_names = {t["track"] for t in tracks}
    assert "trading-review" in track_names
    assert "financial-filings" in track_names
    assert "industry-events" in track_names
    assert "macro-policy" in track_names
    for t in tracks:
        assert t["question_count"] > 0
        assert t["case_count"] > 0
        assert "questions" in t
        assert len(t["questions"]) == t["question_count"]


def test_agents_endpoints_lifecycle(http_server, tmp_path):
    base, _ = http_server
    # 1. GET /api/agents
    status, body = _get(f"{base}/api/agents")
    assert status == 200
    assert body["safety"] == SAFETY_DECLARATION
    agents = body["agents"]
    assert isinstance(agents, list)
    assert len(agents) >= 6
    agent_ids = {a["agent_id"] for a in agents}
    assert "codex" in agent_ids
    assert "claude-code" in agent_ids

    # 2. POST /api/agents/apply (dry run)
    status, body = _post(f"{base}/api/agents/apply", {"agent_id": "codex", "dry_run": True})
    assert status == 200
    assert body["safety"] == SAFETY_DECLARATION
    assert body["agent"]["agent_id"] == "codex"
    assert body["agent"]["status"] == "configured"

    # 3. POST with missing agent_id
    status, body = _post(f"{base}/api/agents/apply", {})
    assert status == 400
    assert body["safety"] == SAFETY_DECLARATION

    # 4. POST with unknown agent_id
    status, body = _post(f"{base}/api/agents/apply", {"agent_id": "unknown-nonexistent"})
    assert status == 404
    assert body["safety"] == SAFETY_DECLARATION

    # 5. POST /api/agents/disable
    status, body = _post(f"{base}/api/agents/disable", {"agent_id": "codex"})
    assert status == 200
    assert body["safety"] == SAFETY_DECLARATION

    # 6. POST /api/agents/restore
    status, body = _post(f"{base}/api/agents/restore", {"agent_id": "codex"})
    assert status == 200
    assert body["safety"] == SAFETY_DECLARATION


def test_benchmark_latest_and_images_endpoints(http_server):
    base, _ = http_server
    status, body = _get(f"{base}/api/benchmark/latest")
    assert status == 200
    assert body["safety"] == SAFETY_DECLARATION
    if body["run_id"] is not None:
        assert "generated_at" in body
        assert "tracks" in body
        assert "systems" in body
        assert "images" in body
        # Image serving check
        images = body["images"]
        if images:
            first_img = images[0]
            img_url = first_img["url"] if isinstance(first_img, dict) else first_img
            with urllib.request.urlopen(f"{base}{img_url}") as img_resp:
                assert img_resp.status == 200
                assert img_resp.headers.get("Content-Type") in ("image/png", "image/svg+xml")
                assert len(img_resp.read()) > 0

    # 404 for invalid image
    status, err_body = _get(f"{base}/api/benchmark/images/latest/nonexistent.png")
    assert status == 404
    assert err_body["safety"] == SAFETY_DECLARATION
