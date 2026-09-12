from __future__ import annotations

import base64
import json
import threading
from http.server import ThreadingHTTPServer

from smartmoney_cub_harness.agent.providers import (
    ALPHATECH_BASE_URL,
    ALPHATECH_PROVIDER_ID,
    OFFLINE_PROVIDER_ID,
    credentials_path,
    load_credentials,
    public_provider_view,
    resolve_provider,
    save_credentials,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workbench.server import WorkbenchHandler, WorkbenchService


def _fill(**overrides):
    fill = {
        "trade_date": "2026-09-01",
        "trade_time": "09:40:00",
        "symbol": "600111",
        "name": "北方稀土",
        "side": "BUY",
        "price": 10.0,
        "quantity": 1000,
        "fee": 5.0,
    }
    fill.update(overrides)
    return fill


def _service(tmp_path) -> WorkbenchService:
    return WorkbenchService(tmp_path)


def test_meta_exposes_the_company_gateway_without_a_key(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        meta = service.meta()
        alphatech = next(p for p in meta["providers"] if p["provider_id"] == ALPHATECH_PROVIDER_ID)
        assert alphatech["base_url"] == ALPHATECH_BASE_URL
        assert alphatech["has_key"] is False
        # A key never appears in a browser-facing payload.
        assert "api_key" not in json.dumps(meta)
        assert meta["safety"] == SAFETY_DECLARATION
    finally:
        service.close()


def test_a_stored_key_is_reported_as_present_but_never_returned(tmp_path) -> None:
    save_credentials(tmp_path, {"providers": {ALPHATECH_PROVIDER_ID: {"api_key": "sk-secret-value"}}})
    view = public_provider_view(ALPHATECH_PROVIDER_ID, credentials=load_credentials(tmp_path))
    assert view["has_key"] is True
    assert view["key_source"] == "local_store"
    assert "sk-secret-value" not in json.dumps(view)

    service = _service(tmp_path)
    try:
        assert "sk-secret-value" not in json.dumps(service.settings())
    finally:
        service.close()

    mode = credentials_path(tmp_path).stat().st_mode & 0o777
    assert mode == 0o600


def test_the_offline_provider_needs_no_key(tmp_path) -> None:
    provider = resolve_provider(OFFLINE_PROVIDER_ID, credentials={"providers": {}})
    assert provider["protocol"] == "offline"
    assert provider["requires_key"] is False


def test_a_provider_without_a_key_falls_back_to_local_review(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        service.store.add_fills([_fill()])
        session = service.create_session({"title": "复盘"})
        events = list(
            service.stream_turn(session["session"]["session_id"], {"text": "帮我复盘这几笔"})
        )
        text = "".join(event.get("text", "") for event in events if event["kind"] == "delta")
        # Without a configured key the turn still completes, using local numbers.
        assert "本地离线复盘" in text
        assert events[-1]["kind"] == "done"
        # Nothing left the machine, so there is no outbound audit row.
        assert service.store.list_audits() == []
    finally:
        service.close()


def test_a_turn_is_persisted_so_a_reload_resumes_it(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        session = service.create_session({"title": "复盘"})
        session_id = session["session"]["session_id"]
        list(service.stream_turn(session_id, {"text": "第一轮"}))
        events = service.session_detail(session_id, {})["events"]
        kinds = [event["kind"] for event in events]
        assert "user_message" in kinds
        assert "assistant_message" in kinds
        seqs = [event["seq"] for event in events]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)
    finally:
        service.close()


def test_upload_stores_the_file_locally_and_does_not_commit(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        content = (
            "成交日期,证券代码,操作,成交均价,成交数量\n"
            "2026-09-01,600111,买入,10.00,1000\n"
            "2026-09-03,600111,卖出,11.00,1000\n"
        ).encode("utf-8")
        result = service.upload(
            {
                "file_name": "fills.csv",
                "media_type": "text/csv",
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        )
        assert result["extraction"]["row_count"] == 2
        assert result["raw_file_stays_local"] is True
        # Parsing writes nothing to the ledger until the user commits.
        assert service.store.list_fills() == []
        assert service.store.counts()["source_document"] == 1
    finally:
        service.close()


def test_commit_rejects_the_whole_batch_when_one_row_is_invalid(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        result = service.commit_import(
            {
                "rows": [
                    {"trade_date": "2026-09-01", "symbol": "600111", "side": "BUY", "price": 10.0, "quantity": 1000},
                    {"trade_date": "2026-09-01", "symbol": "600111", "side": "SIDEWAYS", "price": "abc", "quantity": None},
                ]
            }
        )
        assert result["status"] == "rejected"
        assert result["committed"] == 0
        # A partial import is worse than no import, so nothing is written.
        assert service.store.list_fills() == []
        assert len(result["rejected"]) == 1
    finally:
        service.close()


def test_committing_a_reviewed_extraction_writes_the_rows(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        content = (
            "成交日期,证券代码,操作,成交均价,成交数量\n"
            "2026-09-01,600111,买入,10.00,1000\n"
            "2026-09-03,600111,卖出,11.00,1000\n"
        ).encode("utf-8")
        uploaded = service.upload(
            {
                "file_name": "fills.csv",
                "media_type": "text/csv",
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        )
        extraction_id = uploaded["extraction"]["extraction_id"]
        result = service.commit_import(
            {"extraction_id": extraction_id, "document_id": uploaded["document"]["document_id"]}
        )
        assert result["status"] == "ok"
        assert result["inserted_count"] == 2
        assert result["ledger_status"] == "ok"

        overview = service.overview({})
        assert overview["summary"]["trade_count"] == 1
        assert overview["summary"]["total_net_pnl"] == 1000.0
        assert overview["recent_documents"][0]["file_name"] == "fills.csv"
    finally:
        service.close()


def test_recommitting_the_same_extraction_does_not_duplicate_positions(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        content = (
            "成交日期,证券代码,操作,成交均价,成交数量\n"
            "2026-09-01,600111,买入,10.00,1000\n"
            "2026-09-03,600111,卖出,11.00,1000\n"
        ).encode("utf-8")
        uploaded = service.upload(
            {
                "file_name": "fills.csv",
                "media_type": "text/csv",
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        )
        extraction_id = uploaded["extraction"]["extraction_id"]
        service.commit_import({"extraction_id": extraction_id})
        second = service.commit_import({"extraction_id": extraction_id})
        assert second["inserted_count"] == 0
        assert len(second["skipped"]) == 2
        assert service.overview({})["summary"]["trade_count"] == 1
    finally:
        service.close()


def test_upload_rejects_a_file_larger_than_the_limit(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        oversized = b"a" * (33 * 1024 * 1024)
        try:
            service.upload(
                {
                    "file_name": "huge.csv",
                    "media_type": "text/csv",
                    "content_base64": base64.b64encode(oversized).decode("ascii"),
                }
            )
        except Exception as error:
            assert "32 MB" in str(error)
        else:
            raise AssertionError("an oversized upload must be refused")
    finally:
        service.close()


def test_overview_reports_blocking_issues_for_an_unpaired_sell(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        service.add_manual_fill(
            {"trade_date": "2026-09-03", "symbol": "600519", "side": "SELL", "price": 1500.0, "quantity": 100}
        )
        overview = service.overview({})
        assert overview["ledger_status"] == "needs_review"
        assert any(issue["code"] == "sell_without_position" for issue in overview["blocking_issues"])
        assert overview["summary"]["trade_count"] == 0
    finally:
        service.close()


def test_trade_detail_returns_the_revision_history(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        service.store.add_fills([_fill()])
        service.store.add_fills([_fill(price=10.5)], edited_by="manual")
        service.store.add_fills(
            [_fill(trade_date="2026-09-03", side="SELL", price=11.0)]
        )
        detail = service.trade_detail("RT-600111-1")
        assert detail["trade"]["round_trip_id"] == "RT-600111-1"
        revisions = detail["fill_revisions"]
        assert len(revisions) == 3
        # The corrected buy keeps its earlier revision, marked as superseded.
        superseded = [row for row in revisions if row["superseded"]]
        assert any(row["price"] == 10.0 for row in superseded)
    finally:
        service.close()


def test_doctor_reports_local_state(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        doctor = service.doctor()
        assert doctor["status"] == "ok"
        names = {check["name"] for check in doctor["checks"]}
        assert {"store", "local_ocr", "outbound_redaction"} <= names
    finally:
        service.close()


def test_http_get_endpoints_and_unknown_routes(tmp_path) -> None:
    service = _service(tmp_path)
    handler = type(
        "TestHandler",
        (WorkbenchHandler,),
        {"service": service, "asset_dir": None, "access_token": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    import urllib.error
    import urllib.request

    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base + "/api/meta", timeout=10) as response:
            meta = json.loads(response.read().decode("utf-8"))
        assert meta["app"] == "smartmoney-cub"

        request = urllib.request.Request(
            base + "/api/import/manual",
            data=json.dumps(
                {"trade_date": "2026-09-01", "symbol": "600111", "side": "BUY", "price": 10.0, "quantity": 1000}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        assert result["inserted_count"] == 1

        with urllib.request.urlopen(base + "/api/overview", timeout=10) as response:
            overview = json.loads(response.read().decode("utf-8"))
        assert overview["summary"]["open_position_count"] == 1

        try:
            urllib.request.urlopen(base + "/api/does-not-exist", timeout=10)
        except urllib.error.HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("an unknown route must return 404")
    finally:
        server.shutdown()
        server.server_close()
        service.close()


def test_http_requires_the_token_when_one_is_configured(tmp_path) -> None:
    service = _service(tmp_path)
    handler = type(
        "TokenHandler",
        (WorkbenchHandler,),
        {"service": service, "asset_dir": None, "access_token": "expected-token"},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    import urllib.error
    import urllib.request

    base = f"http://127.0.0.1:{server.server_port}"
    try:
        try:
            urllib.request.urlopen(base + "/api/meta", timeout=10)
        except urllib.error.HTTPError as error:
            assert error.code == 401
        else:
            raise AssertionError("a missing token must be rejected")

        request = urllib.request.Request(base + "/api/meta", headers={"X-SMCUB-Token": "expected-token"})
        with urllib.request.urlopen(request, timeout=10) as response:
            assert json.loads(response.read().decode("utf-8"))["app"] == "smartmoney-cub"
    finally:
        server.shutdown()
        server.server_close()
        service.close()
