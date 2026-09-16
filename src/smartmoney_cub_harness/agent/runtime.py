from __future__ import annotations

import hashlib
import json
import threading
from datetime import date, datetime, timezone
from typing import Any, Iterator

from smartmoney_cub_harness import analytics
from smartmoney_cub_harness.agent.providers import (
    ALPHATECH_PROVIDER_ID,
    OFFLINE_PROVIDER_ID,
    REASONING_ALIASES,
    ClassifiedProviderError,
    ProviderError,
    default_settings,
    load_credentials,
    load_settings,
    resolve_provider,
)
from smartmoney_cub_harness.agent.route_chain import (
    RouteCandidate,
    RouteChainPolicy,
    stream_chat_with_route_chain,
)
from smartmoney_cub_harness.agent.tools import TOOL_SPECS, ToolBox, _detect_trader_service
from smartmoney_cub_harness.redaction import alias_for, prepare_outbound
from smartmoney_cub_harness.redaction import redact_payload
from smartmoney_cub_harness.review_contracts import (
    RedactedReviewEnvelope,
    ReviewScope,
    StructuredReviewPackage,
)
from smartmoney_cub_harness.review_validation import (
    validate_challenger_only_mutation,
    validate_observation,
    validate_redacted_payload,
    validate_source_time,
)
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
REVIEW_PHASES = ("scope_preview", "scope_confirmed", "evidence", "synthesis", "challenger", "completed")


class ReviewLifecycleError(ValueError):
    """A safe lifecycle contract error that can be returned to the Workbench."""

# Fallback key when a provider event carries no field name of its own. The
# provider only ever emits the reasoning event for a field it really sent, so
# this is a defensive default for a hand-built event, not an invented value.
REASONING_FIELD_DEFAULT = REASONING_ALIASES[0]

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

    def __init__(
        self,
        store: Store,
        *,
        credentials_root: str | None = None,
        workspace_db: str | None = None,
        trader_service: Any = None,
        dsh_bridge: Any = None,
    ) -> None:
        self.store = store
        self.credentials_root = credentials_root or str(store.root)
        self.trader_service = (
            trader_service
            or _detect_trader_service(self.credentials_root)
            or _detect_trader_service(self.store.root)
        )
        self.toolbox = ToolBox(
            store, workspace_db, trader_service=self.trader_service
        )
        self.workspace_db = self.toolbox.workspace_db
        self.dsh_bridge = dsh_bridge
        self._cancel_lock = threading.RLock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._route_policy = RouteChainPolicy()

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
        today = date.today()
        analysis = self.toolbox._analysis(
            portfolio_id=portfolio_id, year=today.year, month=today.month
        )
        payload: dict[str, Any] = {
            "portfolio": self.store.get_portfolio(portfolio_id),
            "summary": analysis["summary"],
            "open_positions": analysis["open_positions"],
            "ledger_status": analysis["ledger_status"],
            "blocking_issues": analysis["blocking_issues"][:20],
            "calendar": analysis["calendar"],
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
        record_user_message: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Stream one assistant turn.

        Yields event dictionaries that the HTTP layer serializes. The same events
        are persisted, so replaying a session does not depend on the browser.
        """
        session = self.store.get_session(session_id)
        with self._cancel_lock:
            cancel_event = self._cancel_events.setdefault(session_id, threading.Event())
        # A previous cancelled run leaves its event set until the next explicit
        # turn/resume. Clearing here makes cancellation one-turn scoped.
        cancel_event.clear()
        if record_user_message:
            self.store.append_event(
                session_id, kind="user_message", role="user", payload={"text": user_text}
            )
        if not dry_run:
            self.store.update_session(session_id, status="running")
            self.store.append_event(
                session_id,
                kind="turn_started",
                role="system",
                payload={"phase": "evidence", "safety": SAFETY_DECLARATION},
            )

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
                if cancel_event.is_set():
                    yield from self._cancelled_events(session_id)
                    return
                yield event
            return

        try:
            for event in self._provider_turn(session_id, session, resolved, messages, context):
                if cancel_event.is_set():
                    yield from self._cancelled_events(session_id)
                    return
                yield event
        except ProviderError as error:
            if isinstance(error, ClassifiedProviderError):
                payload = error.to_dict()
                yield {
                    "kind": "error",
                    "error": str(error),
                    "classified": payload,
                    "safety": SAFETY_DECLARATION,
                }
            else:
                payload = {"text": str(error)}
                yield {"kind": "error", "error": str(error), "safety": SAFETY_DECLARATION}
            self.store.append_event(session_id, kind="error", payload=payload)
            self.store.update_session(session_id, status="error")

    def cancel_turn(self, session_id: str) -> dict[str, Any]:
        """Request cancellation of a running model turn without touching markets."""
        session = self.store.get_session(session_id)
        if session.get("status") not in {"running", "cancel_requested"}:
            return {
                "status": "not_running",
                "session": session,
                "safety": SAFETY_DECLARATION,
            }
        with self._cancel_lock:
            event = self._cancel_events.setdefault(session_id, threading.Event())
        event.set()
        self.store.append_event(
            session_id,
            kind="turn_cancel_requested",
            role="system",
            payload={"status": "cancel_requested", "safety": SAFETY_DECLARATION},
        )
        session = self.store.update_session(session_id, status="cancel_requested")
        return {"status": "cancel_requested", "session": session, "safety": SAFETY_DECLARATION}

    def resume_turn(self, session_id: str, user_text: str = "") -> Iterator[dict[str, Any]]:
        """Resume the last incomplete user turn using the durable local transcript."""
        session = self.store.get_session(session_id)
        if session.get("status") not in {"interrupted", "cancelled", "error", "cancel_requested"}:
            raise ReviewLifecycleError("session_is_not_resumable")
        text = user_text.strip()
        reused_last_user_turn = not text
        if not text:
            events = self.store.list_events(session_id)
            text = next(
                (
                    str(event["payload"].get("text") or "").strip()
                    for event in reversed(events)
                    if event["kind"] == "user_message"
                ),
                "",
            )
        if not text:
            raise ReviewLifecycleError("no_user_turn_to_resume")
        self.store.append_event(
            session_id,
            kind="turn_resumed",
            role="system",
            payload={"resume_from": session.get("status"), "safety": SAFETY_DECLARATION},
        )
        yield from self.run_turn(
            session_id,
            text,
            record_user_message=not reused_last_user_turn,
        )

    def _cancelled_events(self, session_id: str) -> Iterator[dict[str, Any]]:
        self.store.append_event(
            session_id,
            kind="turn_cancelled",
            role="system",
            payload={"status": "cancelled", "resume_available": True, "safety": SAFETY_DECLARATION},
        )
        self.store.update_session(session_id, status="cancelled")
        yield {"kind": "cancelled", "resume_available": True, "safety": SAFETY_DECLARATION}
        yield {"kind": "done", "cancelled": True, "safety": SAFETY_DECLARATION}

    def build_review_envelope(self, session_id: str) -> RedactedReviewEnvelope:
        """Build the only payload allowed to cross into the DSH sidecar."""
        session = self.store.get_session(session_id)
        context = self.context_payload(session.get("context"))
        redacted, _ = redact_payload(context, salt=self._salt())
        decision_time = str(
            session.get("context", {}).get("decision_time")
            or session.get("created_at")
            or datetime.now(timezone.utc).isoformat()
        )
        scope = ReviewScope(
            review_id=session_id,
            decision_time=decision_time,
            horizons=tuple(session.get("context", {}).get("horizons") or ("session",)),
            case_ids=tuple(session.get("context", {}).get("case_ids") or ()),
        )
        envelope_payload = {
            "portfolio_id": redacted.get("portfolio", {}).get(
                "portfolio_id",
                alias_for(DEFAULT_PORTFOLIO_ID, salt=self._salt(), kind="portfolio"),
            ),
            "summary": redacted.get("summary", {}),
            "open_positions": redacted.get("open_positions", []),
            "ledger_status": redacted.get("ledger_status", ""),
            "blocking_issues": redacted.get("blocking_issues", []),
            "calendar": redacted.get("calendar", []),
        }
        validation = validate_redacted_payload(envelope_payload)
        if not validation.ok:
            raise ReviewLifecycleError("review_envelope_failed_redaction")
        return RedactedReviewEnvelope(
            scope=scope,
            payload=envelope_payload,
            payload_sha256=hashlib.sha256(
                json.dumps(envelope_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            redaction_policy="redaction.v1",
            sent_keys=("context",),
        )

    def review_scope_preview(self, session_id: str) -> dict[str, Any]:
        envelope = self.build_review_envelope(session_id)
        self.store.append_event(
            session_id,
            kind="review_scope_preview",
            role="system",
            payload={"phase": "scope_preview", "envelope": envelope.to_dict(), "safety": SAFETY_DECLARATION},
        )
        return {
            "status": "ok",
            "phase": "scope_preview",
            "confirmed": bool(self.store.get_session(session_id).get("context", {}).get("scope_confirmed")),
            "envelope": envelope.to_dict(),
            "safety": SAFETY_DECLARATION,
        }

    def confirm_review_scope(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        envelope = self.build_review_envelope(session_id)
        if payload.get("review_id") and payload["review_id"] != session_id:
            raise ReviewLifecycleError("review_id_mismatch")
        context = dict(self.store.get_session(session_id).get("context") or {})
        context["scope_confirmed"] = True
        context["review_phase"] = "scope_confirmed"
        session = self.store.update_session(session_id, context=context)
        self.store.append_event(
            session_id,
            kind="review_scope_confirmed",
            role="system",
            payload={"phase": "scope_confirmed", "review_id": session_id, "safety": SAFETY_DECLARATION},
        )
        dsh = None
        if self.dsh_bridge is not None:
            try:
                dsh = self.dsh_bridge.handshake(envelope)
                self.dsh_bridge.subscribe()
            except Exception:
                self.store.append_event(
                    session_id,
                    kind="terminal",
                    role="system",
                    payload={"status": "dsh_handshake_failed", "safety": SAFETY_DECLARATION},
                )
                raise ReviewLifecycleError("dsh_handshake_failed") from None
            self.store.append_event(
                session_id,
                kind="sidecar_connected",
                role="system",
                payload={"profile": "smartmoney-review", "safety": SAFETY_DECLARATION},
            )
        return {"status": "ok", "phase": "scope_confirmed", "session": session, "envelope": envelope.to_dict(), "dsh": dsh, "safety": SAFETY_DECLARATION}

    def record_challenger_proposal(self, session_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        validation = validate_challenger_only_mutation(proposal)
        if not validation.ok:
            raise ReviewLifecycleError("challenger_validation_failed")
        self.store.append_event(
            session_id,
            kind="challenger_proposal",
            role="plugin",
            payload={"proposal": proposal, "champion_mutated": False, "safety": SAFETY_DECLARATION},
        )
        return {"status": "ok", "proposal": proposal, "champion_mutated": False, "safety": SAFETY_DECLARATION}

    def record_review_package(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            package = StructuredReviewPackage.from_dict(payload)
        except Exception:
            raise ReviewLifecycleError("review_package_decode_failed") from None
        if package.review_id != session_id or package.scope.review_id != session_id:
            raise ReviewLifecycleError("review_package_id_mismatch")
        errors = list(validate_redacted_payload(package.envelope.payload).errors)
        decision_time = package.scope.decision_time
        errors.extend(
            error
            for observation in package.observations
            for error in validate_observation(observation, decision_time=decision_time).errors
        )
        errors.extend(
            error
            for evidence in package.evidence
            for error in validate_source_time(
                decision_time=decision_time,
                data_source=evidence.data_source,
                available_at=evidence.available_at,
                data_quality_flag=evidence.data_quality_flag,
            ).errors
        )
        errors.extend(
            error
            for proposal in package.challenger_proposals
            for error in validate_challenger_only_mutation(proposal).errors
        )
        if errors:
            raise ReviewLifecycleError("review_package_validation_failed")
        stored = package.to_dict()
        self.store.append_event(
            session_id,
            kind="review_package",
            role="plugin",
            payload=stored,
        )
        context = dict(self.store.get_session(session_id).get("context") or {})
        context["review_phase"] = "completed"
        self.store.update_session(session_id, context=context)
        return {"status": "ok", "package": stored, "phase": "completed", "safety": SAFETY_DECLARATION}

    # ---- provider path -------------------------------------------------

    def resolve_session_provider(self, session: dict[str, Any]) -> dict[str, Any]:
        """Pick the provider for a turn, falling back to the offline review.

        A provider that was removed, or one with no usable key, must not send an
        unauthenticated request. In both cases the turn is answered locally.
        """
        credentials = load_credentials(self.credentials_root)
        settings = load_settings(self.credentials_root)
        provider_id = session.get("provider_id") or ALPHATECH_PROVIDER_ID

        def offline(reason: str, from_provider: str) -> dict[str, Any]:
            fallback = resolve_provider(
                OFFLINE_PROVIDER_ID, credentials=credentials, settings=settings
            )
            fallback["fallback_from"] = from_provider
            fallback["fallback_reason"] = reason
            return fallback

        try:
            resolved = resolve_provider(
                provider_id, credentials=credentials, settings=settings
            )
        except ProviderError:
            return offline("provider_not_available", provider_id)
        if resolved["protocol"] != "offline" and not resolved.get("has_key"):
            return offline("no_api_key_configured", provider_id)
        return resolved

    def _build_messages(self, session: dict[str, Any], user_text: str) -> list[dict[str, Any]]:
        system_content = SYSTEM_PROMPT
        custom_prompt = self.store.get_setting("agent_system_prompt")
        if custom_prompt and str(custom_prompt).strip():
            system_content = SYSTEM_PROMPT + "\n\n用户自定义预设要求：\n" + str(custom_prompt).strip()
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
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
        effort = session.get("reasoning") or "off"
        # The transcript kept here is local. Every request is a redacted and
        # audited copy made at the moment it is sent, because a later round
        # carries tool results that the first round never contained: the outbound
        # payload changes on each hop, so the redaction and the audit have to be
        # redone on each hop rather than inherited from the first one.
        working = list(messages)
        assistant_text = ""
        rounds = 0
        route_candidates = self._route_candidates(session, provider)
        while rounds < MAX_TOOL_ROUNDS:
            rounds += 1
            prepared = self._prepare(working, session=session, context=context)
            if prepared.get("blocked"):
                reason = prepared.get("reason")
                self.store.append_event(
                    session_id, kind="error", payload={"text": f"outbound blocked: {reason}"}
                )
                self.store.update_session(session_id, status="error")
                yield {
                    "kind": "error",
                    "error": f"outbound blocked: {reason}",
                    "safety": SAFETY_DECLARATION,
                }
                return
            request_messages = prepared["redacted_messages"]
            tool_calls: list[dict[str, Any]] = []
            turn_text = ""
            round_reasoning: dict[str, str] = {}
            self.store.append_event(
                session_id,
                kind="provider_attempt",
                role="system",
                payload={
                    "attempt": rounds,
                    "provider_id": provider.get("provider_id", ""),
                    "model": model,
                    "phase": "pre_stream",
                    "route_chain": [
                        {"provider_id": candidate.provider_id, "model": candidate.model}
                        for candidate in route_candidates
                    ],
                    "safety": SAFETY_DECLARATION,
                },
            )
            for event in stream_chat_with_route_chain(
                route_candidates,
                request_messages,
                tools=TOOL_SPECS,
                policy=self._route_policy,
            ):
                if event["kind"] == "delta":
                    turn_text += event["text"]
                    yield {"kind": "delta", "text": event["text"], "safety": SAFETY_DECLARATION}
                elif event["kind"] == "reasoning":
                    # Forwarded under the exact field the provider used, and only
                    # because the provider actually sent one. Thinking text stays
                    # out of the browser stream; it only goes back to the model
                    # that produced it, which is why it is kept per round rather
                    # than added to the persisted turn.
                    field = str(event.get("field") or REASONING_FIELD_DEFAULT)
                    round_reasoning[field] = round_reasoning.get(field, "") + event["text"]
                elif event["kind"] == "tool_call":
                    tool_calls.append(event["call"])
                elif event["kind"] == "done":
                    break

            if turn_text:
                assistant_text += turn_text

            if not tool_calls:
                # The last round is the answer itself, so its text is the
                # assistant message and the loop ends.
                if turn_text:
                    working.append({"role": "assistant", "content": turn_text})
                break

            # Exactly one assistant message per round. Appending the visible text
            # separately as well would send the provider the same sentence twice
            # in one turn, which reads as a duplicated transcript.
            assistant_message: dict[str, Any] = {
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
            assistant_message.update(round_reasoning)
            working.append(assistant_message)

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
                # A tool result is local data that the model may see. The local
                # transcript and the browser keep the real row; the copy sent
                # back is redacted when the next request is built.
                redacted_result = _redact_tool_result(result, salt=self._salt())
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
                        "content": redacted_result,
                    }
                )

        if assistant_text:
            self.store.append_event(
                session_id, kind="assistant_message", role="assistant", payload={"text": assistant_text}
            )
            self.store.append_event(
                session_id,
                kind="turn_completed",
                role="system",
                payload={"phase": "synthesis", "safety": SAFETY_DECLARATION},
            )
        self.store.update_session(session_id, status="idle")
        self.store.append_event(
            session_id,
            kind="terminal",
            role="system",
            payload={"status": "idle", "safety": SAFETY_DECLARATION},
        )
        yield {"kind": "done", "safety": SAFETY_DECLARATION}

    def _route_candidates(
        self, session: dict[str, Any], primary_provider: dict[str, Any]
    ) -> list[RouteCandidate]:
        """Resolve a session's explicit provider chain from local settings only.

        The session may choose route order and model names, but it cannot inject
        endpoints or credentials. Those values are resolved from the local
        provider store, and the offline route is always available as the final
        candidate.
        """
        settings = load_settings(self.credentials_root)
        credentials = load_credentials(self.credentials_root)
        context = session.get("context") or {}
        configured = context.get("route_chain")
        entries: list[Any] = list(configured) if isinstance(configured, list) else []
        primary_id = str(primary_provider.get("provider_id") or session.get("provider_id") or "")
        primary_model = str(session.get("model") or primary_provider.get("default_model") or "")

        if not entries:
            entries = [{"provider_id": primary_id, "model": primary_model}]
        else:
            primary_seen = any(
                (item.get("provider_id") if isinstance(item, dict) else item) == primary_id
                for item in entries
            )
            first_id = (
                entries[0].get("provider_id")
                if isinstance(entries[0], dict)
                else entries[0]
                if isinstance(entries[0], str)
                else ""
            )
            if not primary_seen or first_id != primary_id:
                entries.insert(0, {"provider_id": primary_id, "model": primary_model})

        candidates: list[RouteCandidate] = []
        seen: set[tuple[str, str]] = set()

        for item in entries:
            if isinstance(item, str):
                provider_id = item.strip()
                requested_model = ""
                requested_effort = ""
            elif isinstance(item, dict):
                provider_id = str(item.get("provider_id") or "").strip()
                requested_model = str(item.get("model") or "").strip()
                requested_effort = str(item.get("reasoning") or item.get("effort") or "").strip()
            else:
                continue
            if not provider_id:
                continue

            if provider_id == primary_id:
                resolved = dict(primary_provider)
            else:
                try:
                    resolved = resolve_provider(
                        provider_id, credentials=credentials, settings=settings
                    )
                except ProviderError:
                    continue
            if resolved.get("protocol") != "offline" and not resolved.get("has_key"):
                continue

            model = requested_model
            if not model:
                model = primary_model if provider_id == primary_id else str(resolved.get("default_model") or "")
            if not model and resolved.get("models"):
                model = str(resolved["models"][0].get("id") or "")
            effort = requested_effort or (str(session.get("reasoning") or "off") if provider_id == primary_id else "off")
            key = (provider_id, model)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                RouteCandidate(
                    provider_id=provider_id,
                    model=model,
                    effort=effort,
                    label=str(resolved.get("label") or provider_id),
                    base_url=str(resolved.get("base_url") or ""),
                    protocol=str(resolved.get("protocol") or "openai-chat"),
                    api_key=str(resolved.get("api_key") or ""),
                    portal_url=str(resolved.get("portal_url") or ""),
                )
            )

        if not any(candidate.provider_id == OFFLINE_PROVIDER_ID for candidate in candidates):
            offline = resolve_provider(
                OFFLINE_PROVIDER_ID, credentials=credentials, settings=settings
            )
            candidates.append(
                RouteCandidate(
                    provider_id=OFFLINE_PROVIDER_ID,
                    model=str(offline.get("default_model") or "local-template"),
                    effort="off",
                    label=str(offline.get("label") or OFFLINE_PROVIDER_ID),
                    protocol="offline",
                )
            )
        return candidates

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
        self.store.append_event(
            session_id,
            kind="turn_completed",
            role="system",
            payload={"phase": "completed", "safety": SAFETY_DECLARATION},
        )
        self.store.update_session(session_id, status="idle")
        self.store.append_event(
            session_id,
            kind="terminal",
            role="system",
            payload={"status": "idle", "safety": SAFETY_DECLARATION},
        )
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


def _redact_tool_result(result: dict[str, Any], *, salt: str) -> str:
    """Return the redacted text of a tool result for the outbound request.

    A tool result is structured review data -- keys such as quantity, price, and
    symbol -- so it goes through the payload redactor, which reduces each value
    by its own rule. That runs on every hop rather than once: a range band such
    as "1000-5000" only survives the string pass untouched, and an exact value
    that reaches the transcript later must still be reduced before it leaves.
    """
    payload = json.dumps(result, ensure_ascii=False)
    redacted, _ = redact_payload(json.loads(payload), salt=salt)
    return json.dumps(redacted, ensure_ascii=False)


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
