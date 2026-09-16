from __future__ import annotations

import base64
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from smartmoney_cub_harness.agent.providers import (
    ALPHATECH_BASE_URL,
    ALPHATECH_PROVIDER_ID,
    OFFLINE_PROVIDER_ID,
    credentials_path,
    install_provider,
    load_credentials,
    load_settings,
    public_provider_view,
    resolve_provider,
    save_credentials,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.workbench.server import ApiError, WorkbenchHandler, WorkbenchService
from smartmoney_cub_harness.store import Store
from smartmoney_cub_harness.workspace import Workspace

# ---- the rule library: where it lives, and the one write it accepts -------


def test_the_rule_library_lives_under_the_state_root_not_the_process_cwd(tmp_path) -> None:
    """A rule proposed in a session must land in the store the session reads.

    The service used to keep the literal "state/workspace/review.db", resolved
    against the process working directory, and then hand that value down to the
    assistant runtime. A workbench started with --state-dir elsewhere therefore
    wrote a proposed rule outside its own review data, and the rule library page
    read a different store than the assistant had written to.
    """
    root = tmp_path / "state-dir"
    outside = tmp_path / "cwd"
    root.mkdir()
    outside.mkdir()
    previous = os.getcwd()
    os.chdir(outside)
    try:
        service = WorkbenchService(root)
        try:
            # The path is anchored to the state root, and it is absolute, so it
            # cannot be reinterpreted by whatever directory the process is in.
            assert Path(service.workspace_db).is_absolute()
            assert Path(service.workspace_db) == root / "workspace" / "review.db"
            # The assistant writes where the library reads. Both halves agreeing
            # is the property that makes a proposed rule visible on the page.
            assert service.runtime.workspace_db == service.workspace_db
            result = service.runtime.toolbox.call(
                "propose_challenger_rule",
                {"rule_id": "CWD-1", "title": "t", "family": "f", "sample_count": 3},
            )
            assert result["status"] == "ok"
            assert (root / "workspace" / "review.db").is_file()
            assert not (outside / "state").exists(), "a rule was written under the process CWD"
            listed = service.rules()["rules"]
            assert [rule["rule_id"] for rule in listed] == ["CWD-1"]
        finally:
            service.close()
    finally:
        os.chdir(previous)


def test_an_explicit_workspace_db_still_wins(tmp_path) -> None:
    explicit = tmp_path / "custom" / "rules.db"
    service = WorkbenchService(tmp_path / "root", workspace_db=str(explicit))
    try:
        assert service.workspace_db == str(explicit)
        assert service.runtime.workspace_db == str(explicit)
    finally:
        service.close()


def test_http_promotion_requires_a_written_note(tmp_path) -> None:
    """Promotion is the one rule-library write, and the note is the gate.

    Driven over HTTP rather than by calling the service, because the route is
    what the rule-library page actually uses and the gate has to hold there.
    """
    service = WorkbenchService(tmp_path)
    try:
        service.runtime.toolbox.call(
            "propose_challenger_rule",
            {"rule_id": "HTTP-1", "title": "t", "family": "f", "sample_count": 25},
        )
        handler = type(
            "PromotionHandler",
            (WorkbenchHandler,),
            {"service": service, "asset_dir": None, "access_token": None},
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"

        def post(path: str, payload: dict) -> tuple[int, dict]:
            request = urllib.request.Request(
                base + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read().decode("utf-8"))

        try:
            # A blank note is refused, and the refusal carries the declaration
            # like every other response does.
            status, body = post("/api/rules/HTTP-1/promote", {"note": "   "})
            assert status == 400, body
            assert body["safety"] == SAFETY_DECLARATION
            # The rule is still a challenger: a refused promotion writes nothing.
            assert Workspace(service.workspace_db).get_rule("HTTP-1")["status"] == "challenger"

            status, body = post("/api/rules/NOPE/promote", {"note": "x"})
            assert status == 404, body
            assert body["safety"] == SAFETY_DECLARATION

            status, body = post("/api/rules/HTTP-1/promote", {"note": "reviewed the gates"})
            assert status == 200, body
            assert body["safety"] == SAFETY_DECLARATION
            assert body["rule"]["status"] == "champion"
            assert Workspace(service.workspace_db).get_rule("HTTP-1")["promotion_note"] == "reviewed the gates"

            # A promoted rule leaves the challenger list and joins the champions.
            listed = service.rules()["rules"]
            assert [r["rule_id"] for r in listed if r["status"] == "champion"] == ["HTTP-1"]
        finally:
            server.shutdown()
            server.server_close()
    finally:
        service.close()



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
    view = public_provider_view(
        ALPHATECH_PROVIDER_ID,
        credentials=load_credentials(tmp_path),
        settings=load_settings(tmp_path),
    )
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
    provider = resolve_provider(
        OFFLINE_PROVIDER_ID, credentials={"providers": {}}, settings=load_settings(tmp_path)
    )
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


def test_http_resume_stream_uses_the_resume_generator(tmp_path) -> None:
    service = _service(tmp_path)
    session_id = service.create_session({"title": "HTTP 恢复"})["session"]["session_id"]
    service.store.append_event(session_id, kind="user_message", role="user", payload={"text": "继续本地复盘"})
    service.store.update_session(session_id, status="interrupted")
    handler = type(
        "TestHandler",
        (WorkbenchHandler,),
        {"service": service, "asset_dir": None, "access_token": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    import urllib.request

    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/assistant/sessions/{session_id}/resume",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8")
        assert response.status == 200
        assert "本地离线复盘" in body
        assert '"kind": "done"' in body
        assert service.store.get_session(session_id)["status"] == "idle"
    finally:
        server.shutdown()
        server.server_close()
        service.close()


def test_workbench_service_integrates_trader_service(tmp_path: Path) -> None:
    from smartmoney_cub_harness.trader.storage import open_store
    from smartmoney_cub_harness.trader.auth import MODE_LOCAL
    from smartmoney_cub_harness.trader.auth.identity import LOCAL_CONTEXT
    from smartmoney_cub_harness.trader.api import TraderService

    trader_store = open_store(tmp_path / "journal", mode=MODE_LOCAL)
    trader_svc = TraderService(trader_store, auth_mode=MODE_LOCAL)
    trader_svc.import_trades(
        LOCAL_CONTEXT,
        rows=[
            {
                "trade_id": "T-BUY",
                "symbol": "600519",
                "side": "BUY",
                "trade_date": "2026-09-01",
                "price": 100.0,
                "quantity": 10,
            },
            {
                "trade_id": "T-SELL",
                "symbol": "600519",
                "side": "SELL",
                "trade_date": "2026-09-02",
                "price": 110.0,
                "quantity": 10,
            },
        ],
    )

    service = WorkbenchService(tmp_path, trader_service=trader_svc)
    try:
        overview = service.overview({})
        assert overview["summary"]["trade_count"] == 1
        assert overview["fill_count"] == 2

        trades_res = service.trades({})
        assert trades_res["count"] == 1
        assert len(trades_res["fills"]) == 2

        report = service.analytics_report({})
        assert report["summary"]["trade_count"] == 1

        runtime_ctx = service.runtime.context_payload({})
        assert runtime_ctx["summary"]["trade_count"] == 1
    finally:
        service.close()
        trader_store.close()


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


def test_every_json_error_response_carries_the_safety_declaration(tmp_path) -> None:
    """A refusal is a response too, and the contract covers it.

    Regression: five error paths built their body without the declaration, so a
    client error was the one reply that did not state the product's safety
    contract. The GET paths that serve the interface shell are excluded on
    purpose -- those are the SPA for client-side routing, not API bodies.
    """
    service = _service(tmp_path)
    handler = type(
        "TestHandler",
        (WorkbenchHandler,),
        {"service": service, "asset_dir": None, "access_token": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    import urllib.error
    import urllib.request

    base = f"http://127.0.0.1:{server.server_port}"

    def post(path: str, body: dict):
        request = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8")

    try:
        # An unknown endpoint, a known endpoint refusing bad input, and a
        # malformed body. Each is a refusal rather than a success.
        cases = [
            post("/api/nonexistent", {}),
            post("/api/assistant/sessions/nope/messages", {}),
            post("/api/settings/providers/NOPE/remove", {}),
        ]
        for status, text in cases:
            assert status >= 400, (status, text)
            assert text.lstrip().startswith("{"), text[:120]
            assert '"safety"' in text, f"HTTP {status} body omits the declaration: {text[:160]}"
            assert SAFETY_DECLARATION in text, text[:160]
    finally:
        server.shutdown()
        server.server_close()
        service.close()


def test_plugin_endpoints_lifecycle_and_catalog(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        catalog = service.plugin_catalog()
        assert catalog["schema"] == "smartmoney_cub_plugin_catalog.v1"
        assert len(catalog["entries"]) > 0
        assert catalog["safety"] == SAFETY_DECLARATION

        detail = service.plugin_detail("toy.review-tagger")
        assert detail["status"] == "ok"
        assert detail["plugin_id"] == "toy.review-tagger"
        assert detail["safety"] == SAFETY_DECLARATION

        conf_res = service.plugin_configure("toy.review-tagger", {"foo": "bar"})
        assert conf_res["status"] == "ok"
        assert conf_res["config"] == {"foo": "bar"}

        en_res = service.plugin_enable("toy.review-tagger")
        assert en_res["status"] == "ok"
        assert en_res["plugin"]["state"] == "ACTIVE"

        dis_res = service.plugin_disable("toy.review-tagger")
        assert dis_res["status"] == "ok"
        assert dis_res["plugin"]["state"] == "DISABLED"

        reload_res = service.plugin_reload()
        assert reload_res["status"] == "ok"
    finally:
        service.close()


def test_agent_presets_and_open_config_file(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        settings = service.settings()
        assert "agent_presets" in settings
        assert settings["agent_presets"]["default_effort"] in ["off", "low", "medium", "high", "max"]

        updated = service.update_settings({
            "agent_presets": {
                "system_prompt": "Always be concise.",
                "default_effort": "high",
                "context_strategy": "summary_compact",
            }
        })
        refreshed = service.settings()
        assert refreshed["agent_presets"]["system_prompt"] == "Always be concise."
        assert refreshed["agent_presets"]["default_effort"] == "high"

        res = service.open_config_file()
        assert res["status"] == "ok"
        assert Path(res["path"]).is_file()
        assert res["safety"] == SAFETY_DECLARATION
    finally:
        service.close()


def test_review_scope_is_redacted_confirmable_and_challenger_only(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        session = service.create_session({
            "title": "结构化复盘",
            "context": {
                "portfolio_id": "PORT-DEFAULT",
                "decision_time": "2026-09-10T15:00:00+08:00",
                "horizons": ["next_session"],
                "case_ids": ["toy-case-1"],
            },
        })["session"]
        session_id = session["session_id"]
        preview = service.review_scope(session_id)
        assert preview["phase"] == "scope_preview"
        assert preview["envelope"]["scope"]["decision_time"] == "2026-09-10T15:00:00+08:00"
        assert "PORT-DEFAULT" not in json.dumps(preview)

        confirmed = service.confirm_review_scope(session_id, {"review_id": session_id})
        assert confirmed["phase"] == "scope_confirmed"
        assert confirmed["session"]["context"]["scope_confirmed"] is True

        proposal = {
            "candidate_role": "challenger",
            "rule_id": "TOY-CHALLENGER-1",
            "rationale": "只作为待验证候选。",
            "champion_mutated": False,
            "core_rules_mutated": False,
        }
        saved = service.record_challenger(session_id, {"proposal": proposal})
        assert saved["champion_mutated"] is False
        assert service.store.list_events(session_id)[-1]["kind"] == "challenger_proposal"
    finally:
        service.close()


def test_structured_review_package_is_validated_and_persisted(tmp_path) -> None:
    from smartmoney_cub_harness.review_contracts import StructuredReviewPackage

    service = _service(tmp_path)
    try:
        session_id = service.create_session({"title": "结构化结果"})["session"]["session_id"]
        envelope = service.runtime.build_review_envelope(session_id)
        package = StructuredReviewPackage(
            review_id=session_id,
            scope=envelope.scope,
            envelope=envelope,
            observations=({
                "action_label": "WATCH",
                "invalidation_price": "unknown",
                "time_stop": "next session close",
                "give_up_conditions": ["toy evidence incomplete"],
                "data_source": "toy_fixture",
                "available_at": envelope.scope.decision_time,
                "data_quality_flag": "ok",
            },),
            challenger_proposals=({
                "candidate_role": "challenger",
                "rule_id": "TOY-1",
                "rationale": "待验证",
                "champion_mutated": False,
                "core_rules_mutated": False,
            },),
        )
        saved = service.record_review_package(session_id, package.to_dict())
        assert saved["phase"] == "completed"
        event = service.store.list_events(session_id)[-1]
        assert event["kind"] == "review_package"
        assert event["payload"]["safety"] == SAFETY_DECLARATION

        future = package.to_dict()
        future["observations"][0]["available_at"] = "2999-01-01T00:00:00+00:00"
        with pytest.raises(ApiError, match="review_package_validation_failed") as error:
            service.record_review_package(session_id, future)
        assert error.value.code == "review_package_error"
    finally:
        service.close()


def test_runtime_uses_explicit_route_chain_for_review_turns(tmp_path, monkeypatch) -> None:
    import smartmoney_cub_harness.agent.route_chain as route_chain_module
    from smartmoney_cub_harness.agent.provider_errors import (
        ClassifiedProviderError,
        FailurePhase,
        ProviderErrorCode,
    )

    service = _service(tmp_path)
    try:
        session_id = service.create_session(
            {
                "title": "路线链",
                "provider_id": "primary",
                "model": "primary-model",
                "context": {
                    "portfolio_id": "PORT-DEFAULT",
                    "route_chain": [
                        {"provider_id": "primary", "model": "primary-model"},
                        {"provider_id": "offline", "model": "local-template", "protocol": "offline"},
                    ],
                },
            }
        )["session"]["session_id"]
        monkeypatch.setattr(
            service.runtime,
            "resolve_session_provider",
            lambda _session: {
                "provider_id": "primary",
                "model": "primary-model",
                "label": "Primary",
                "protocol": "openai-chat",
                "base_url": "https://example.invalid/v1",
                "api_key": "toy-key",
                "has_key": True,
            },
        )
        calls: list[str] = []

        def fake_provider_stream(provider, *, model, messages, tools=None, effort="off"):
            calls.append(provider["provider_id"])
            if provider["provider_id"] == "primary":
                raise ClassifiedProviderError(
                    code=ProviderErrorCode.INSUFFICIENT_QUOTA,
                    message="toy quota exhausted",
                    phase=FailurePhase.PRE_STREAM,
                    fallbackable=True,
                )
            return iter(
                [
                    {"kind": "delta", "text": "route-chain response"},
                    {"kind": "done", "finish_reason": "stop"},
                ]
            )

        monkeypatch.setattr(route_chain_module, "stream_chat", fake_provider_stream)
        events = list(service.runtime.run_turn(session_id, "请复盘"))

        assert calls == ["primary"]
        assert any(event.get("text", "").startswith("【本地离线复盘】") for event in events)
    finally:
        service.close()


def test_runtime_does_not_mutate_explicit_route_chain_context(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        route_chain = [{"provider_id": "offline", "model": "local-template"}]
        session_id = service.create_session(
            {
                "title": "路线链复制",
                "provider_id": "primary",
                "model": "primary-model",
                "context": {"route_chain": route_chain},
            }
        )["session"]["session_id"]
        primary = {
            "provider_id": "primary",
            "model": "primary-model",
            "label": "Primary",
            "protocol": "offline",
            "has_key": True,
        }

        service.runtime._route_candidates(service.store.get_session(session_id), primary)

        assert route_chain == [{"provider_id": "offline", "model": "local-template"}]
        assert service.store.get_session(session_id)["context"]["route_chain"] == route_chain
    finally:
        service.close()


def test_review_envelope_uses_a_valid_portfolio_alias_when_context_is_sparse(tmp_path) -> None:
    service = _service(tmp_path)
    try:
        session_id = service.create_session({"title": "稀疏范围"})["session"]["session_id"]
        service.runtime.context_payload = lambda _context: {"summary": {"trade_count": 0}}

        envelope = service.runtime.build_review_envelope(session_id)

        assert envelope.payload["portfolio_id"].startswith("portfolio-")
        assert len(envelope.payload["portfolio_id"]) == len("portfolio-") + 8
        assert service.runtime.build_review_envelope(session_id).payload["portfolio_id"] == envelope.payload["portfolio_id"]
    finally:
        service.close()


def test_cancel_resume_and_restart_recovery_are_durable(tmp_path) -> None:
    service = _service(tmp_path)
    session = service.create_session({"title": "可恢复复盘"})["session"]
    session_id = session["session_id"]
    service.store.update_session(session_id, status="running")
    try:
        cancelled = service.cancel_turn(session_id)
        assert cancelled["status"] == "cancel_requested"
        assert service.store.get_session(session_id)["status"] == "cancel_requested"
        resumed = list(service.resume_turn(session_id, {"text": "继续本地复盘"}))
        assert resumed[-1]["kind"] == "done"
        assert service.store.get_session(session_id)["status"] == "idle"
        kinds = [event["kind"] for event in service.store.list_events(session_id)]
        assert "turn_cancel_requested" in kinds
        assert "turn_resumed" in kinds

        service.store.append_event(session_id, kind="user_message", role="user", payload={"text": "恢复时复用这条"})
        service.store.update_session(session_id, status="interrupted")
        before = [event for event in service.store.list_events(session_id) if event["kind"] == "user_message"]
        list(service.resume_turn(session_id, {}))
        after = [event for event in service.store.list_events(session_id) if event["kind"] == "user_message"]
        assert len(after) == len(before)
    finally:
        service.close()

    raw = Store(tmp_path / "recovery")
    orphan = raw.create_session(title="中断会话")
    raw.update_session(orphan["session_id"], status="running")
    raw.close()
    recovered_service = _service(tmp_path / "recovery")
    try:
        assert recovered_service.recovered_sessions[0]["status"] == "interrupted"
        detail = recovered_service.session_detail(orphan["session_id"], {})
        assert detail["session"]["status"] == "interrupted"
        assert detail["events"][-1]["kind"] == "runtime_recovered"
    finally:
        recovered_service.close()
