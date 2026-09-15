from __future__ import annotations

import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import smartmoney_cub_harness.agent.providers as providers_module
from smartmoney_cub_harness.agent.providers import (
    ALPHATECH_PROVIDER_ID,
    resolve_provider,
    save_credentials,
    stream_chat,
)
from smartmoney_cub_harness.agent.runtime import ReviewAgentRuntime
from smartmoney_cub_harness.agent.tools import ToolBox
from smartmoney_cub_harness.evolution_ledger import read_ledger
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.store import Store
from smartmoney_cub_harness.workspace import Workspace

# The multi-round tool loop against a fake OpenAI-compatible provider.
#
# A thinking model streams its private reasoning beside the tool call, and the
# NEXT round is rejected with HTTP 400 unless that text is handed back on the
# assistant message it belonged to. These tests keep a real provider in the loop
# -- a fake one that behaves like a thinking endpoint -- because the defect only
# appears on the second request of a turn.

REASONING_TEXT = "先核对样本量是否达到门槛，再决定是否提出候选规则。"
PREAMBLE_TEXT = "先看统计，再提规则。"
ANSWER_TEXT = "已按样本量记录候选规则，晋升仍需人工确认。"
TOOL_ARGUMENTS = {
    "rule_id": "ASST-1",
    "title": "开盘半小时不追高",
    "family": "entry",
    "sample_count": 3,
}

# Every request the fake provider received, in order. The second one is the
# round-trip that the provider would have rejected before the fix.
REQUESTS: list[dict] = []

# Response status per request. A live thinking model answers the second round
# with HTTP 400 when the reasoning it streamed is missing from the transcript,
# and the fake refuses the same way so this test fails for the real reason.
STATUSES: list[int] = []

REASONING_400_MESSAGE = "The reasoning_content in the thinking mode must be passed back to the API"


class FakeThinkingProvider(BaseHTTPRequestHandler):
    """Streams reasoning_content plus one tool call, then records the next body."""

    def log_message(self, format, *args):  # noqa: A002
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        REQUESTS.append(payload)
        if len(REQUESTS) > 1 and _assistant_tool_message_without_reasoning(payload):
            self._reject()
            return
        STATUSES.append(200)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for frame in (self._tool_round_frames() if len(REQUESTS) == 1 else self._answer_frames()):
            self.wfile.write(("data: " + json.dumps(frame) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _reject(self) -> None:
        """Answer exactly the way the live endpoint answered before the fix."""
        STATUSES.append(400)
        body = json.dumps({"error": {"message": REASONING_400_MESSAGE, "type": "invalid_request_error"}})
        data = body.encode("utf-8")
        self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def _tool_round_frames(self) -> list[dict]:
        return [
            {"choices": [{"delta": {"reasoning_content": REASONING_TEXT}}]},
            # Visible text beside the tool call. The older runtime appended this
            # once as its own assistant message and again on the tool-call
            # message, so the second request carried the same sentence twice.
            {"choices": [{"delta": {"content": PREAMBLE_TEXT}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_asst_1",
                                    "function": {
                                        "name": "propose_challenger_rule",
                                        "arguments": json.dumps(TOOL_ARGUMENTS, ensure_ascii=False),
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        ]

    def _answer_frames(self) -> list[dict]:
        return [
            {
                "choices": [
                    {"delta": {"content": ANSWER_TEXT}, "finish_reason": "stop"}
                ]
            }
        ]


def _start_provider() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeThinkingProvider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/v1"


def _runtime_with_provider(root: Path, base_url: str) -> tuple[Store, ReviewAgentRuntime]:
    """A runtime whose provider is the fake thinking endpoint."""
    save_credentials(
        root,
        {"providers": {ALPHATECH_PROVIDER_ID: {"api_key": "test-key", "base_url": base_url}}},
    )
    store = Store(root)
    return store, ReviewAgentRuntime(store, credentials_root=str(root))


def _assistant_messages(payload: dict) -> list[dict]:
    return [message for message in payload["messages"] if message.get("role") == "assistant"]


def _assistant_tool_message_without_reasoning(payload: dict) -> bool:
    """True when a tool-call turn was rebuilt without its reasoning text."""
    return any(
        message.get("tool_calls") and not message.get("reasoning_content")
        for message in _assistant_messages(payload)
    )


def _rule_rows(db_path: Path) -> list[dict]:
    """Read the rule table directly so a champion row anywhere would be visible."""
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT rule_id, status, metrics, promotion_note FROM rule_state ORDER BY rule_id"
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def test_a_thinking_model_passes_reasoning_back_and_stores_the_rule(tmp_path, monkeypatch) -> None:
    REQUESTS.clear()
    STATUSES.clear()
    # The process working directory is a scratch directory, so "wrote nothing
    # under the CWD" is an observable fact rather than an assumption. Before the
    # storage fix the rule landed in ./state/workspace/review.db instead.
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    server, base_url = _start_provider()
    try:
        store_root = tmp_path / "state"
        store, runtime = _runtime_with_provider(store_root, base_url)
        try:
            session = store.create_session(title="复盘")
            events = list(
                runtime.run_turn(session["session_id"], "看下统计并提出规则")
            )

            # (a) the turn completed, and the provider never had to reject it.
            assert events[-1]["kind"] == "done"
            assert not [event for event in events if event["kind"] == "error"]
            assert len(REQUESTS) == 2, "the tool loop should have made exactly two requests"
            assert STATUSES == [200, 200]

            # (b) the reasoning the provider streamed is handed back verbatim.
            sent = json.dumps(REQUESTS[1]["messages"], ensure_ascii=False)
            assert REASONING_TEXT in sent
            reasoning_messages = [
                message for message in _assistant_messages(REQUESTS[1]) if message.get("reasoning_content")
            ]
            assert len(reasoning_messages) == 1
            assert reasoning_messages[0]["reasoning_content"] == REASONING_TEXT

            # (c) one assistant message per round carrying the tool calls, and no
            # duplicated content from the older append-alongside bug.
            tool_messages = [
                message
                for message in _assistant_messages(REQUESTS[1])
                if message.get("tool_calls")
            ]
            assert len(tool_messages) == 1
            assert tool_messages[0]["content"] == PREAMBLE_TEXT
            carried = [call["function"]["name"] for call in tool_messages[0]["tool_calls"]]
            assert carried == ["propose_challenger_rule"]
            contents = [
                message["content"]
                for message in _assistant_messages(REQUESTS[1])
                if message.get("content")
            ]
            assert contents == [PREAMBLE_TEXT]
            assert len(contents) == len(set(contents))

            # (d) the proposal is a challenger, and no champion exists anywhere.
            workspace_db = Path(runtime.workspace_db)
            assert workspace_db == store_root / "workspace" / "review.db"
            rows = _rule_rows(workspace_db)
            assert [row["status"] for row in rows] == ["challenger"]
            assert not [row for row in rows if row["status"] == "champion"]
            assert not [row for row in rows if row["promotion_note"]]
            # The rule library the review workbench reads is the same database
            # the proposal was written into.
            library = Workspace(runtime.workspace_db)
            assert [rule["rule_id"] for rule in library.list_rules()] == ["ASST-1"]

            # (e) the metrics record what is still missing, computed with the
            # product's own thresholds rather than a copy of them.
            metrics = json.loads(rows[0]["metrics"])
            assert metrics["sample_count"] == 3
            assert "sample_count_below_20" in metrics["blockers"]

            # Nothing was written under the process working directory.
            assert list(cwd.iterdir()) == []
        finally:
            store.close()
    finally:
        server.shutdown()
        server.server_close()


def test_the_rule_lands_next_to_the_store_root_or_in_an_explicit_workspace_db(
    tmp_path, monkeypatch
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    derived_root = tmp_path / "derived"
    derived_store = Store(derived_root)
    try:
        derived = ReviewAgentRuntime(derived_store)
        # The default is derived from the store root, never from the CWD.
        assert derived.workspace_db == str(derived_root / "workspace" / "review.db")
        assert derived.toolbox.workspace_db == derived.workspace_db
        derived.toolbox.call(
            "propose_challenger_rule",
            json.dumps({**TOOL_ARGUMENTS, "rule_id": "ASST-DERIVED"}),
        )
        assert (derived_root / "workspace" / "review.db").is_file()
        assert Workspace(derived.workspace_db).get_rule("ASST-DERIVED") is not None
    finally:
        derived_store.close()

    explicit_root = tmp_path / "explicit"
    explicit_store = Store(explicit_root)
    explicit_db = tmp_path / "elsewhere" / "rules.db"
    try:
        explicit = ReviewAgentRuntime(explicit_store, workspace_db=str(explicit_db))
        assert explicit.workspace_db == str(explicit_db)
        explicit.toolbox.call(
            "propose_challenger_rule",
            json.dumps({**TOOL_ARGUMENTS, "rule_id": "ASST-EXPLICIT"}),
        )
        assert explicit_db.is_file()
        assert Workspace(str(explicit_db)).get_rule("ASST-EXPLICIT") is not None
        # The default location is untouched when a caller names a database.
        assert not (explicit_root / "workspace").exists()
    finally:
        explicit_store.close()

    # A ToolBox built on its own follows the same rule.
    toolbox_store = Store(tmp_path / "toolbox")
    try:
        assert ToolBox(toolbox_store).workspace_db == str(
            tmp_path / "toolbox" / "workspace" / "review.db"
        )
        assert ToolBox(toolbox_store, str(explicit_db)).workspace_db == str(explicit_db)
    finally:
        toolbox_store.close()

    # Nothing was written under the process working directory in any case.
    assert list(cwd.iterdir()) == []


def test_a_proposal_is_journalled_with_blockers_and_the_safety_declaration(tmp_path) -> None:
    store = Store(tmp_path)
    try:
        runtime = ReviewAgentRuntime(store)
        result = runtime.toolbox.call(
            "propose_challenger_rule",
            json.dumps({**TOOL_ARGUMENTS, "evidence_note": "连续三笔追高后回撤"}),
        )
        assert result["champion_mutated"] is False
        assert result["note"] == (
            "Challenger proposed. Promotion still requires the human confirmation gate."
        )

        workspace_dir = Path(runtime.workspace_db).parent
        entries = read_ledger(workspace_dir / "evolution_ledger.jsonl")
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event"] == "challenger_rule_proposed"
        assert entry["champion_mutated"] is False
        assert entry["safety"] == SAFETY_DECLARATION
        assert entry["rule_id"] == "ASST-1"
        assert entry["sample_count"] == 3
        assert entry["proposed_by"] == "review_assistant"
        assert "sample_count_below_20" in entry["blockers"]

        memory = (workspace_dir / "memory.md").read_text(encoding="utf-8")
        assert "ASST-1" in memory
        assert "sample_count_below_20" in memory
        assert SAFETY_DECLARATION in memory
    finally:
        store.close()


def test_the_provider_streams_reasoning_only_when_it_was_actually_sent(monkeypatch) -> None:
    """The provider event must mirror the wire, including its absence.

    A fabricated (empty) reasoning field would change the request shape for every
    model that never streams one, so the event is only emitted for a field the
    endpoint really sent.
    """
    provider = resolve_provider(
        ALPHATECH_PROVIDER_ID,
        base_url="http://127.0.0.1:1/v1",
        credentials={"providers": {ALPHATECH_PROVIDER_ID: {"api_key": "k"}}},
    )

    class _FakeResponse:
        def __init__(self, lines: list[str]) -> None:
            self._lines = lines

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            # stream_chat iterates the response object itself, so the fake has to
            # be its own iterator rather than a context manager wrapping one.
            return iter(line.encode("utf-8") for line in self._lines)

    def _events(lines: list[str]) -> list[dict]:
        monkeypatch.setattr(providers_module, "_open", lambda *args, **kwargs: _FakeResponse(lines))
        return list(stream_chat(provider, model="m", messages=[], tools=None))

    def _frame(delta: dict) -> str:
        return "data: " + json.dumps({"choices": [{"delta": delta}]}) + "\n"

    thinking = _events(
        [
            _frame({"reasoning_content": "先算样本量"}),
            _frame({"content": "结论", "finish_reason": "stop"}),
        ]
    )
    assert [event["kind"] for event in thinking] == ["reasoning", "delta", "done"]
    assert thinking[0]["field"] == "reasoning_content"
    assert thinking[0]["text"] == "先算样本量"
    # The existing event kinds and their payloads are unchanged.
    assert thinking[1]["text"] == "结论"

    plain = _events([_frame({"content": "结论", "finish_reason": "stop"})])
    assert [event["kind"] for event in plain] == ["delta", "done"]
    assert not [event for event in plain if event["kind"] == "reasoning"]
