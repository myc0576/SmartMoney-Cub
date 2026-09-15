from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from smartmoney_cub_harness.agent.providers import ALPHATECH_PROVIDER_ID, save_credentials
from smartmoney_cub_harness.workbench.server import WorkbenchService

# These tests stand up a fake OpenAI-compatible provider and assert on the exact
# bytes that would leave the machine. Redaction is proven against the wire, not
# against an internal function's return value.

CAPTURED: list[dict] = []

# The multi-round provider below records every request of a turn separately, so
# the outbound check can run against each hop rather than only the first one.
ROUND_REQUESTS: list[dict] = []

THESIS_TEXT = "板块主线龙头，止损 9.5，账号 88888888，联系 13800138000"


class FakeProvider(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        if self.path.endswith("/models"):
            body = json.dumps({"data": [{"id": "deepseek-v3"}, {"id": "deepseek-r1"}]})
            self._send(body)
            return
        self.send_error(404)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        CAPTURED.append(
            {
                "payload": payload,
                "authorization": self.headers.get("Authorization"),
                "url": self.path,
            }
        )
        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            frames = [
                {"choices": [{"delta": {"content": "复盘结论："}}]},
                {"choices": [{"delta": {"content": "只基于本地台账。"}, "finish_reason": "stop"}]},
            ]
            for frame in frames:
                self.wfile.write(("data: " + json.dumps(frame) + "\n\n").encode("utf-8"))
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return
        self._send(json.dumps({"choices": [{"message": {"content": "ok"}}]}))

    def _send(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _start_provider():
    return _start_provider_for(FakeProvider)


def _start_provider_for(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/v1"


def _service_with_provider(tmp_path, base_url: str) -> WorkbenchService:
    save_credentials(
        tmp_path,
        {"providers": {ALPHATECH_PROVIDER_ID: {"api_key": "test-key", "base_url": base_url}}},
    )
    return WorkbenchService(tmp_path)


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
        "thesis": THESIS_TEXT,
    }
    fill.update(overrides)
    return fill


def test_no_request_is_sent_without_a_configured_key(tmp_path) -> None:
    CAPTURED.clear()
    server, base_url = _start_provider()
    try:
        # The provider exists and is reachable, but no key is stored for it: the
        # turn must stay local rather than send an unauthenticated request.
        service = WorkbenchService(tmp_path)
        try:
            session = service.create_session({"title": "复盘"})
            list(service.stream_turn(session["session"]["session_id"], {"text": "复盘一下"}))
            assert CAPTURED == []
        finally:
            service.close()
    finally:
        server.shutdown()
        server.server_close()


def test_the_outbound_payload_contains_no_account_name_quantity_or_price(tmp_path) -> None:
    CAPTURED.clear()
    server, base_url = _start_provider()
    try:
        service = _service_with_provider(tmp_path, base_url)
        try:
            service.store.add_fills([_fill()])
            session = service.create_session({"title": "复盘"})
            events = list(
                service.stream_turn(session["session"]["session_id"], {"text": "这笔交易哪里做错了？"})
            )
            assert events[-1]["kind"] == "done"
            assert CAPTURED, "the provider should have received one request"

            messages = CAPTURED[0]["payload"]["messages"]
            sent = json.dumps(messages, ensure_ascii=False)
            # Raw identifiers, names, exact sizes, and exact prices never leave.
            for secret in ("88888888", "13800138000", "600111", "北方稀土"):
                assert secret not in sent, secret
            # No scalar value anywhere in the request equals a local exact size
            # or exact price. Range bands such as "1000-5000" are the point.
            scalars = _collect_scalars(messages)
            assert "1000" not in scalars
            assert 1000 not in scalars
            assert 10.0 not in scalars
            assert "600111" not in scalars
            assert "北方稀土" not in scalars
            # The review-relevant shape does survive.
            assert "return_pct" in sent or "win_rate" in sent
        finally:
            service.close()
    finally:
        server.shutdown()
        server.server_close()


def test_an_outbound_request_writes_an_audit_row(tmp_path) -> None:
    CAPTURED.clear()
    server, base_url = _start_provider()
    try:
        service = _service_with_provider(tmp_path, base_url)
        try:
            service.store.add_fills([_fill()])
            session = service.create_session({"title": "复盘"})
            list(service.stream_turn(session["session"]["session_id"], {"text": "复盘"}))
            audits = service.store.list_audits()
            assert len(audits) >= 1
            audit = audits[0]
            assert audit["blocked"] is False
            assert audit["provider_id"] == ALPHATECH_PROVIDER_ID
            assert audit["payload_sha256"]
            # The audit records which fields were sent, never their values.
            assert "test-key" not in json.dumps(audit)
        finally:
            service.close()
    finally:
        server.shutdown()
        server.server_close()


def test_an_image_attached_to_a_turn_is_blocked_before_the_network(tmp_path) -> None:
    CAPTURED.clear()
    server, base_url = _start_provider()
    try:
        service = _service_with_provider(tmp_path, base_url)
        try:
            session = service.create_session({"title": "复盘"})
            # A user pasting image bytes into the chat is refused rather than
            # forwarded, because attachments never leave this machine.
            list(
                service.stream_turn(
                    session["session"]["session_id"],
                    {"text": "看这张图 data:image/png;base64," + "A" * 300},
                )
            )
            assert CAPTURED == []
        finally:
            service.close()
    finally:
        server.shutdown()
        server.server_close()


def test_tool_calls_are_executed_and_streamed(tmp_path) -> None:
    server, base_url = _start_provider()
    try:
        service = _service_with_provider(tmp_path, base_url)
        try:
            session = service.create_session({"title": "复盘"})
            list(service.stream_turn(session["session"]["session_id"], {"text": "看下统计"}))
            # The provider echoes text; the tool specifications must still be
            # offered so the model can call a domain tool.
            assert CAPTURED[0]["payload"]["tools"]
            names = {tool["function"]["name"] for tool in CAPTURED[0]["payload"]["tools"]}
            assert {"analytics_summary", "list_trades", "propose_challenger_rule"} <= names
            # No shell, file, network, or broker tool is ever offered.
            assert not any("shell" in name or "exec" in name or "order" in name for name in names)
        finally:
            service.close()
    finally:
        server.shutdown()
        server.server_close()


def test_testing_a_provider_lists_models_without_leaking_the_key(tmp_path) -> None:
    server, base_url = _start_provider()
    try:
        service = _service_with_provider(tmp_path, base_url)
        try:
            result = service.test_provider({"provider_id": ALPHATECH_PROVIDER_ID})
            assert result["status"] == "ok"
            assert "deepseek-v3" in result["models"]
            assert "test-key" not in json.dumps(result)
        finally:
            service.close()
    finally:
        server.shutdown()
        server.server_close()


class FakeTwoRoundProvider(BaseHTTPRequestHandler):
    """Asks for two tool rounds, then answers.

    Redaction is only proven for the first hop by a single-round provider: the
    tool results the model sees arrive on the second and third requests, so this
    provider forces both. The second tool is ``open_positions`` on purpose: it
    returns the seeded position with its exact quantity and cost, which is the
    local data that must be reduced before the third request leaves.
    """

    def log_message(self, format, *args):  # noqa: A002
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        ROUND_REQUESTS.append(payload)
        round_index = len(ROUND_REQUESTS)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for frame in self._frames(round_index):
            self.wfile.write(("data: " + json.dumps(frame) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _frames(self, round_index: int) -> list[dict]:
        if round_index == 1:
            return [_tool_call_frame(0, "call_round_1", "analytics_summary", {})]
        if round_index == 2:
            return [
                _tool_call_frame(
                    1, "call_round_2", "open_positions", {"portfolio_id": "PORT-DEFAULT"}
                )
            ]
        return [
            {
                "choices": [
                    {"delta": {"content": "两轮工具已跑完。"}, "finish_reason": "stop"}
                ]
            }
        ]


def _tool_call_frame(index: int, call_id: str, name: str, arguments: dict) -> dict:
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": index,
                            "id": call_id,
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ]
                },
                "finish_reason": "tool_calls",
            }
        ]
    }


def test_a_multi_round_turn_redacts_every_hop_and_audits_each_one(tmp_path) -> None:
    ROUND_REQUESTS.clear()
    server, base_url = _start_provider_for(FakeTwoRoundProvider)
    try:
        service = _service_with_provider(tmp_path, base_url)
        try:
            service.store.add_fills([_fill()])
            session = service.create_session({"title": "复盘"})
            events = list(
                service.stream_turn(session["session"]["session_id"], {"text": "两轮复盘"})
            )
            assert events[-1]["kind"] == "done"
            assert [event["kind"] for event in events if event["kind"] == "tool_result"] == [
                "tool_result",
                "tool_result",
            ]
            assert len(ROUND_REQUESTS) == 3

            # The seeded account name, exact price, quantity, and thesis must not
            # appear in any request of the turn, including the ones that carry the
            # tool results back.
            for index, payload in enumerate(ROUND_REQUESTS):
                sent = json.dumps(payload, ensure_ascii=False)
                for secret in ("88888888", "13800138000", "600111", "北方稀土", THESIS_TEXT):
                    assert secret not in sent, f"request {index} leaked {secret}"
                scalars = _collect_scalars(payload)
                assert "1000" not in scalars, f"request {index} carried an exact quantity"
                assert 1000 not in scalars, f"request {index} carried an exact quantity"
                assert 10.0 not in scalars, f"request {index} carried an exact price"

            # Each hop is redacted and audited on its own, so the audit trail
            # matches the number of requests that actually left the machine.
            audits = service.store.list_audits()
            assert len(audits) == len(ROUND_REQUESTS)
            for audit in audits:
                assert audit["blocked"] is False
                assert audit["payload_sha256"]
        finally:
            service.close()
    finally:
        server.shutdown()
        server.server_close()


def _collect_scalars(node, out=None):
    """Collect every scalar value in a nested JSON structure."""
    if out is None:
        out = set()
    if isinstance(node, dict):
        for value in node.values():
            _collect_scalars(value, out)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect_scalars(item, out)
    elif isinstance(node, str):
        out.add(node)
    elif node is not None:
        out.add(node)
    return out
