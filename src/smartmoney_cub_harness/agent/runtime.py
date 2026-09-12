from __future__ import annotations

import json
from datetime import date
from typing import Any, Iterator

from smartmoney_cub_harness import analytics
from smartmoney_cub_harness.agent.providers import (
    ALPHATECH_PROVIDER_ID,
    OFFLINE_PROVIDER_ID,
    ProviderError,
    load_credentials,
    resolve_provider,
    stream_chat,
)
from smartmoney_cub_harness.agent.tools import TOOL_SPECS, ToolBox
from smartmoney_cub_harness.redaction import prepare_outbound
from smartmoney_cub_harness.redaction import redact_payload
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.store import DEFAULT_PORTFOLIO_ID, Store

# The review assistant runtime.
#
# The host owns the authoritative session state: every turn is written to the
# local event log before it is streamed to the browser, so a refresh, a crashed
# tab, or a restarted server resumes the same conversation.
#
# The outbound path is fixed: build a payload, redact it, audit it, send it.

MAX_TOOL_ROUNDS = 6

SYSTEM_PROMPT = """你是 smartmoney-cub 的复盘助手。

你的职责是帮助用户复盘已经确认的交易记录，指出执行偏差，并给出可以验证的改进规则。

硬性约束：
1. 这是只读复盘工具。不要给出买卖建议，不要预测价格，不要提供下单、撤单或任何交易指令。
2. 只依据工具返回的数据说话。样本量不足时必须说明样本量，不能把一两笔盈亏当成规律。
3. 你收到的是脱敏后的结构化字段：证券代码和组合名是本地别名，数量和金额是区间，时间是时间段。
   不要试图还原真实账号、姓名或精确金额，也不要要求用户提供这些信息。
4. 提出规则时只能提出 challenger 候选规则。永远不要声称规则已晋升为 champion；晋升必须由用户显式确认。
5. 如果数据记录存在阻断问题（例如无法配对的卖出），先说明问题，再给出复盘结论。

回答风格：简洁、具体、可执行。先给结论，再给依据。引用数据时说明它来自本地台账。
"""


class ReviewAgentRuntime:
    """Owns session turns, provider calls, redaction, and event persistence."""

    def __init__(self, store: Store, *, credentials_root: str | None = None) -> None:
        self.store = store
        self.credentials_root = credentials_root or str(store.root)
        self.toolbox = ToolBox(store)

    # ---- session helpers ----------------------------------------------

    def _salt(self) -> str:
        salt = self.store.get_setting("alias_salt")
        if not salt:
            salt = _new_salt()
            self.store.set_setting("alias_salt", salt)
        return str(salt)

    def context_payload(self, context: dict[str, Any] | None) -> dict[str, Any]:
        """Assemble the local context a turn may draw on."""
        context = context or {}
        portfolio_id = context.get("portfolio_id") or DEFAULT_PORTFOLIO_ID
        fills = self.store.list_fills(portfolio_id=portfolio_id)
        analysis = analytics.analyze(fills)
        today = date.today()
        payload: dict[str, Any] = {
            "portfolio": self.store.get_portfolio(portfolio_id),
            "summary": analysis["summary"],
            "open_positions": analysis["open_positions"],
            "ledger_status": analysis["ledger_status"],
            "blocking_issues": analysis["blocking_issues"][:20],
            "calendar": analytics.calendar_days(
                analytics.build_ledger(fills), year=today.year, month=today.month
            ),
        }
        if context.get("round_trip_id"):
            payload["focus_trade"] = next(
                (
                    trip
                    for trip in analysis["round_trips"]
                    if trip["round_trip_id"] == context["round_trip_id"]
                ),
                None,
            )
        if context.get("date"):
            payload["focus_date"] = context["date"]
        return payload

    # ---- the turn ------------------------------------------------------

    def run_turn(
        self,
        session_id: str,
        user_text: str,
        *,
        dry_run: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Stream one assistant turn.

        Yields event dictionaries that the HTTP layer serializes. The same events
        are persisted, so replaying a session does not depend on the browser.
        """
        session = self.store.get_session(session_id)
        self.store.append_event(
            session_id, kind="user_message", role="user", payload={"text": user_text}
        )
        if not dry_run:
            self.store.update_session(session_id, status="running")

        messages = self._build_messages(session, user_text)
        context = self.context_payload(session.get("context"))

        if dry_run:
            outbound = self._prepare(messages, session=session, context=context, audit=False)
            yield {
                "kind": "preview",
                "payload": outbound.get("payload"),
                "redaction_summary": outbound.get("redaction_summary"),
                "blocked": outbound.get("blocked", False),
                "reason": outbound.get("reason"),
                "safety": SAFETY_DECLARATION,
            }
            return

        resolved = self.resolve_session_provider(session)
        if resolved["provider_id"] == OFFLINE_PROVIDER_ID:
            for event in self._offline_turn(session_id, session, context):
                yield event
            return

        try:
            for event in self._provider_turn(session_id, session, resolved, messages, context):
                yield event
        except ProviderError as error:
            payload = {"text": str(error)}
            self.store.append_event(session_id, kind="error", payload=payload)
            self.store.update_session(session_id, status="error")
            yield {"kind": "error", "error": str(error), "safety": SAFETY_DECLARATION}

    # ---- provider path -------------------------------------------------

    def resolve_session_provider(self, session: dict[str, Any]) -> dict[str, Any]:
        credentials = load_credentials(self.credentials_root)
        provider_id = session.get("provider_id") or ALPHATECH_PROVIDER_ID
        try:
            resolved = resolve_provider(provider_id, credentials=credentials)
        except ProviderError:
            # A missing key must not break anything else. Fall back to the local
            # template so the user still gets a review.
            return resolve_provider(OFFLINE_PROVIDER_ID, credentials=credentials)
        if resolved["protocol"] != "offline" and not resolved.get("has_key"):
            # Never send an unauthenticated request: without a usable key the turn
            # is answered from local data instead of reaching the network.
            fallback = resolve_provider(OFFLINE_PROVIDER_ID, credentials=credentials)
            fallback["fallback_from"] = provider_id
            fallback["fallback_reason"] = "no_api_key_configured"
            return fallback
        return resolved

    def _build_messages(self, session: dict[str, Any], user_text: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for event in self.store.list_events(session["session_id"]):
            if event["kind"] == "user_message":
                messages.append({"role": "user", "content": event["payload"].get("text", "")})
            elif event["kind"] == "assistant_message":
                messages.append({"role": "assistant", "content": event["payload"].get("text", "")})
        if not messages[-1:] or messages[-1].get("content") != user_text:
            messages.append({"role": "user", "content": user_text})
        # The local context is redacted as structured data first, so keys such as
        # quantity, price, symbol, and name are reduced by their rule instead of
        # being serialized into one opaque string.
        redacted_context, _ = redact_payload(
            self.context_payload(session.get("context")), salt=self._salt()
        )
        messages.append(
            {
                "role": "system",
                "content": "本地脱敏上下文（JSON）："
                + json.dumps(redacted_context, ensure_ascii=False),
            }
        )
        return messages

    def _prepare(
        self,
        messages: list[dict[str, Any]],
        *,
        session: dict[str, Any],
        context: dict[str, Any],
        audit: bool = True,
    ) -> dict[str, Any]:
        redacted_messages, summary = _redact_messages(messages, salt=self._salt())
        prepared = prepare_outbound(
            {"messages": redacted_messages},
            salt=self._salt(),
            attachments_present=False,
        )
        if prepared.get("blocked"):
            self.store.record_audit(
                session_id=session["session_id"],
                provider_id=session.get("provider_id") or ALPHATECH_PROVIDER_ID,
                model=session.get("model") or "",
                payload_sha256="",
                sent_keys=[],
                redaction_summary=summary,
                blocked=True,
                reason=prepared.get("reason"),
            )
            return prepared
        if audit:
            self.store.record_audit(
                session_id=session["session_id"],
                provider_id=session.get("provider_id") or ALPHATECH_PROVIDER_ID,
                model=session.get("model") or "",
                payload_sha256=prepared["payload_sha256"],
                sent_keys=prepared["sent_keys"],
                redaction_summary=summary,
            )
        return {
            **prepared,
            "redacted_messages": redacted_messages,
            "redaction_summary": {**(prepared.get("redaction_summary") or {}), "message_pass": summary},
        }

    def _provider_turn(
        self,
        session_id: str,
        session: dict[str, Any],
        provider: dict[str, Any],
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> Iterator[dict[str, Any]]:
        model = session.get("model") or provider.get("default_model") or ""
        prepared = self._prepare(messages, session=session, context=context)
        if prepared.get("blocked"):
            reason = prepared.get("reason")
            self.store.append_event(
                session_id, kind="error", payload={"text": f"outbound blocked: {reason}"}
            )
            self.store.update_session(session_id, status="error")
            yield {"kind": "error", "error": f"outbound blocked: {reason}", "safety": SAFETY_DECLARATION}
            return

        working = list(prepared["redacted_messages"])
        assistant_text = ""
        rounds = 0
        while rounds < MAX_TOOL_ROUNDS:
            rounds += 1
            tool_calls: list[dict[str, Any]] = []
            turn_text = ""
            for event in stream_chat(provider, model=model, messages=working, tools=TOOL_SPECS):
                if event["kind"] == "delta":
                    turn_text += event["text"]
                    yield {"kind": "delta", "text": event["text"], "safety": SAFETY_DECLARATION}
                elif event["kind"] == "tool_call":
                    tool_calls.append(event["call"])
                elif event["kind"] == "done":
                    break

            if turn_text:
                assistant_text += turn_text
                working.append({"role": "assistant", "content": turn_text})

            if not tool_calls:
                break

            working.append(
                {
                    "role": "assistant",
                    "content": turn_text or None,
                    "tool_calls": [
                        {
                            "id": call["call_id"] or f"call_{index}",
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": call["arguments"] or "{}",
                            },
                        }
                        for index, call in enumerate(tool_calls)
                    ],
                }
            )

            for index, call in enumerate(tool_calls):
                call_id = call["call_id"] or f"call_{index}"
                started = {
                    "call_id": call_id,
                    "name": call["name"],
                    "arguments": call["arguments"],
                }
                self.store.append_event(session_id, kind="tool_call", payload=started)
                yield {
                    "kind": "tool_call",
                    "call_id": call_id,
                    "name": call["name"],
                    "arguments": call["arguments"],
                    "safety": SAFETY_DECLARATION,
                }
                result = self.toolbox.call(call["name"], call["arguments"])
                # A tool result is local data that the model may see. It goes
                # through the same redactor as the prompt.
                redacted_result, _ = _redact_messages(
                    [{"role": "tool", "content": json.dumps(result, ensure_ascii=False)}],
                    salt=self._salt(),
                )
                self.store.append_event(
                    session_id, kind="tool_result", payload={"call_id": call_id, "result": result}
                )
                yield {
                    "kind": "tool_result",
                    "call_id": call_id,
                    "name": call["name"],
                    "result": result,
                    "safety": SAFETY_DECLARATION,
                }
                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": redacted_result[0]["content"],
                    }
                )

        if assistant_text:
            self.store.append_event(
                session_id, kind="assistant_message", role="assistant", payload={"text": assistant_text}
            )
        self.store.update_session(session_id, status="idle")
        yield {"kind": "done", "safety": SAFETY_DECLARATION}

    # ---- offline path --------------------------------------------------

    def _offline_turn(
        self, session_id: str, session: dict[str, Any], context: dict[str, Any]
    ) -> Iterator[dict[str, Any]]:
        text = render_offline_review(context)
        for chunk in _chunks(text, 80):
            yield {"kind": "delta", "text": chunk, "safety": SAFETY_DECLARATION}
        self.store.append_event(
            session_id, kind="assistant_message", role="assistant", payload={"text": text}
        )
        self.store.update_session(session_id, status="idle")
        yield {"kind": "done", "safety": SAFETY_DECLARATION}


def _new_salt() -> str:
    import secrets  # noqa: PLC0415 - only needed when the salt is first created

    return secrets.token_hex(32)


def _chunks(text: str, size: int) -> Iterator[str]:
    for index in range(0, len(text), size):
        yield text[index : index + size]


def _redact_messages(
    messages: list[dict[str, Any]], *, salt: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Redact message contents while keeping the provider protocol intact."""
    redacted: list[dict[str, Any]] = []
    total: dict[str, int] = {}
    for message in messages:
        copy = dict(message)
        content = copy.get("content")
        if isinstance(content, str):
            # Message text is free-form. Identifiers and paths are removed by the
            # string redactor; structured aliases are handled by the payload pass.
            prepared = prepare_outbound({"text": content}, salt=salt)
            copy["content"] = (prepared.get("payload") or {}).get("text", content)
            for key, value in (prepared.get("redaction_summary") or {}).get("counts", {}).items():
                total[key] = total.get(key, 0) + value
        elif isinstance(content, list):
            copy["content"] = content
        redacted.append(copy)
    return redacted, {"policy": "redaction.v1", "counts": total, "total": sum(total.values())}


def render_offline_review(context: dict[str, Any]) -> str:
    """Deterministic local review text. No network, no model, no guessing."""
    summary = context.get("summary") or {}
    lines = [
        "## 本地离线复盘",
        "",
        f"- 已确认平仓交易：{summary.get('trade_count', 0)} 笔",
        f"- 胜率：{summary.get('win_rate', 0)}%",
        f"- 净盈亏合计：{summary.get('total_net_pnl', 0)}",
    ]
    if summary.get("profit_factor") is None:
        lines.append("- 盈亏比：当前样本没有亏损交易，无法计算")
    else:
        lines.append(f"- 盈亏比：{summary['profit_factor']}（总盈利 / 总亏损绝对值）")
    lines.append(f"- 平均持有：{summary.get('avg_holding_days', 0)} 天")
    lines.append("")
    if context.get("blocking_issues"):
        lines.append("### 需要先处理的数据问题")
        for issue in context["blocking_issues"][:5]:
            lines.append(f"- {issue.get('code')}：{issue.get('detail')}")
        lines.append("")
    if context.get("open_positions"):
        lines.append("### 尚未配对的持仓")
        for position in context["open_positions"][:5]:
            lines.append(
                f"- {position['symbol']} 剩余 {position['quantity']} 股，均价 {position['avg_cost']}"
            )
        lines.append("")
    lines.extend(
        [
            "### 复盘提示",
            "- 上述数字来自本地台账，样本是自选复盘历史，不代表总体胜率。",
            "- 配置模型 Provider 后可以获得逐笔归因和规则建议；配置前只有本地统计。",
            f"- {SAFETY_DECLARATION}",
        ]
    )
    return "\n".join(lines)
