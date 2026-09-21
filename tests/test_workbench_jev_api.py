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


def test_benchmark_latest_bundled_run_discovery(tmp_path: Path):
    root = tmp_path / "app_root"
    assets_dir = root / "assets" / "benchmark"
    assets_dir.mkdir(parents=True)
    sample_run = {
        "schema": "smartmoney_cub_benchmark_run.v1",
        "run_id": "run_bundled_test",
        "benchmark_id": "finance-jev-v1",
        "sample_count": 240,
        "tracks": ["trading-review"],
        "systems": [{"system_id": "deterministic_baseline", "status": "completed"}],
        "safety": SAFETY_DECLARATION,
    }
    (assets_dir / "run.json").write_text(json.dumps(sample_run), encoding="utf-8")
    (assets_dir / "benchmark-leaderboard.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-image-bytes")

    service = _service(root)
    try:
        latest = service.benchmark_latest()
        assert latest["run_id"] == "run_bundled_test"
        assert latest["source"] == "bundled"
        assert latest["safety"] == SAFETY_DECLARATION
        assert len(latest["images"]) == 1
        assert latest["images"][0]["name"] == "benchmark-leaderboard.png"

        # Verify image serving from bundled directory
        res = service.benchmark_image("run_bundled_test", "benchmark-leaderboard.png")
        assert res is not None
        img_bytes, mime = res
        assert img_bytes == b"\x89PNG\r\n\x1a\nfake-image-bytes"
        assert mime == "image/png"

        # Also serves via 'latest' run_id
        res_latest = service.benchmark_image("latest", "benchmark-leaderboard.png")
        assert res_latest is not None
        img_bytes_latest, _ = res_latest
        assert img_bytes_latest == b"\x89PNG\r\n\x1a\nfake-image-bytes"
    finally:
        service.close()


def test_benchmark_latest_local_artifacts_priority(tmp_path: Path):
    root = tmp_path / "app_root_local"
    # Bundled run
    assets_dir = root / "assets" / "benchmark"
    assets_dir.mkdir(parents=True)
    (assets_dir / "run.json").write_text(
        json.dumps({"run_id": "run_bundled", "systems": [], "safety": SAFETY_DECLARATION}),
        encoding="utf-8",
    )
    # Local run
    local_run_dir = root / "artifacts" / "benchmark" / "run_local_001"
    local_run_dir.mkdir(parents=True)
    (local_run_dir / "run.json").write_text(
        json.dumps({"run_id": "run_local_001", "systems": [], "safety": SAFETY_DECLARATION}),
        encoding="utf-8",
    )
    (local_run_dir / "test.png").write_bytes(b"local-image-data")

    service = _service(root)
    try:
        latest = service.benchmark_latest()
        assert latest["run_id"] == "run_local_001"
        assert latest["source"] == "local"

        res = service.benchmark_image("run_local_001", "test.png")
        assert res is not None
        img_bytes, mime = res
        assert img_bytes == b"local-image-data"
        assert mime == "image/png"
    finally:
        service.close()


def test_benchmark_image_path_traversal_defence(tmp_path: Path):
    root = tmp_path / "app_traversal"
    assets_dir = root / "assets" / "benchmark"
    assets_dir.mkdir(parents=True)
    (assets_dir / "run.json").write_text(
        json.dumps({"run_id": "run_safe", "safety": SAFETY_DECLARATION}),
        encoding="utf-8",
    )
    (assets_dir / "valid.png").write_bytes(b"png-data")
    secret_file = root / "secret.txt"
    secret_file.write_text("sensitive-content", encoding="utf-8")

    service = _service(root)
    try:
        # Invalid run_id with dot-dot
        assert service.benchmark_image("..", "valid.png") is None
        assert service.benchmark_image("../etc", "valid.png") is None
        # Invalid filename with dot-dot
        assert service.benchmark_image("run_safe", "../secret.txt") is None
        assert service.benchmark_image("run_safe", "sub/../../secret.txt") is None
        # Illegal characters
        assert service.benchmark_image("run_safe;rm", "valid.png") is None
        assert service.benchmark_image("run_safe", "valid*.png") is None
    finally:
        service.close()


def test_jev_connection_settings_http_contract(http_server, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    base, _ = http_server
    status, body = _post(f"{base}/api/settings/jev", {"api_key": "fixture-only-key"})
    assert status == 200 and body["has_key"]
    assert "fixture-only-key" not in json.dumps(body)
    status, body = _get(f"{base}/api/settings/jev")
    assert status == 200 and body["key_source"] == "local"
    status, body = _post(f"{base}/api/settings/jev", {"api_key": "bad key"})
    assert status == 400 and body["safety"] == SAFETY_DECLARATION
    status, body = _post(f"{base}/api/settings/jev", {"clear_key": True})
    assert status == 200 and not body["has_key"]
    status, body = _post(f"{base}/api/settings/jev/test", {})
    assert status == 200 and body["connected"] is False


def test_jev_connection_test_http_uses_saved_key(http_server, monkeypatch):
    from smartmoney_cub_harness.jev import connection
    base, _ = http_server
    seen = []
    def respond(req):
        seen.append(req.get_header("Authorization"))
        return {"model": "jev-test", "answers": {"connection_test": {"type": "noul", "noul": 0.8}}}
    monkeypatch.setattr(connection, "_probe_request", respond)
    _post(f"{base}/api/settings/jev", {"api_key": "fixture-only-key"})
    status, body = _post(f"{base}/api/settings/jev/test", {})
    assert status == 200 and body["connected"]
    assert seen == ["Bearer fixture-only-key"]
    assert "fixture-only-key" not in json.dumps(body)
