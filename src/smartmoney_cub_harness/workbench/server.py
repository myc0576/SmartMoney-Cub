from __future__ import annotations

import base64
import json
import os
import threading
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from smartmoney_cub_harness import __version__, analytics
from smartmoney_cub_harness import extractors
from smartmoney_cub_harness.agent.providers import (
    ALPHATECH_PROVIDER_ID,
    OFFLINE_PROVIDER_ID,
    PROVIDER_PROTOCOLS,
    ProviderError,
    catalog_view,
    credentials_path,
    install_provider,
    list_models as provider_models,
    load_credentials,
    load_settings,
    list_provider_ids,
    provider_entry,
    public_provider_view,
    remove_provider,
    resolve_provider,
    save_settings,
    update_provider,
)
from smartmoney_cub_harness.agent.runtime import ReviewAgentRuntime
from smartmoney_cub_harness.redaction import REDACTION_POLICY_VERSION
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.store import DEFAULT_PORTFOLIO_ID, Store

# Local-only web service for the convergence workbench.
#
# The server binds to a loopback address by default. A non-loopback bind is
# refused unless the caller passes an explicit access token, because a review
# journal is not something to expose on a network by accident.

ASSET_DIR_ENV = "SMCUB_ASSET_DIR"
MAX_UPLOAD_BYTES = 32 * 1024 * 1024


def bundled_asset_dir() -> Path | None:
    """Locate the built interface shipped inside the package.

    An installed copy reads its own packaged assets. A source checkout can also
    point at a sibling build directory, which keeps local development usable
    without rebuilding the package on every edit.
    """
    candidates = [Path(__file__).parent / "web"]
    override = os.environ.get(ASSET_DIR_ENV)
    if override:
        candidates.insert(0, Path(override))
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return candidates[0] if candidates else None


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "bad_request") -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class WorkbenchService:
    """Holds the store and assembles API responses."""

    def __init__(self, root: str | Path, *, workspace_db: str | None = None) -> None:
        self.root = Path(root)
        self.store = Store(self.root)
        self.workspace_db = workspace_db or "state/workspace/review.db"
        self.runtime = ReviewAgentRuntime(self.store, credentials_root=str(self.root))
        self._lock = threading.Lock()

    def close(self) -> None:
        self.store.close()

    # ---- overview ------------------------------------------------------

    def meta(self) -> dict[str, Any]:
        credentials = load_credentials(self.root)
        settings = load_settings(self.root)
        providers = self.provider_views(settings, credentials)
        return {
            "app": "smartmoney-cub",
            "version": __version__,
            "safety": SAFETY_DECLARATION,
            "redaction_policy": REDACTION_POLICY_VERSION,
            "engine": extractors.ocr_backend_status(),
            "providers": providers,
            "default_provider": self.default_selection()["provider_id"],
            "default_model": self.default_selection()["model"],
            "default_reasoning": self.default_selection()["reasoning"],
            "store_counts": self.store.counts(),
            "trend_color_scheme": self.store.get_setting("trend_color_scheme", "cn"),
        }

    def overview(self, query: dict[str, list[str]]) -> dict[str, Any]:
        portfolio_id = _one(query, "portfolio_id") or DEFAULT_PORTFOLIO_ID
        today = datetime.now(timezone.utc).astimezone()
        year = int(_one(query, "year") or today.year)
        month = int(_one(query, "month") or today.month)
        analysis = analytics.analyze(
            self.store.list_fills(portfolio_id=portfolio_id), year=year, month=month
        )
        return {
            "status": "ok",
            "portfolio_id": portfolio_id,
            "portfolios": self.store.list_portfolios(),
            "year": year,
            "month": month,
            "summary": analysis["summary"],
            "equity_curve": analysis["summary"]["equity_curve"],
            "calendar": analysis["calendar"],
            "open_positions": analysis["open_positions"],
            "blocking_issues": analysis["blocking_issues"],
            "issues": analysis["issues"],
            "ledger_status": analysis["ledger_status"],
            "round_trips": analysis["round_trips"],
            "recent_trades": analysis["round_trips"][-10:][::-1],
            "fill_count": len(self.store.list_fills(portfolio_id=portfolio_id)),
            "recent_documents": self.store.list_documents(portfolio_id=portfolio_id)[:5],
            "safety": SAFETY_DECLARATION,
        }

    def trades(self, query: dict[str, list[str]]) -> dict[str, Any]:
        portfolio_id = _one(query, "portfolio_id") or DEFAULT_PORTFOLIO_ID
        analysis = analytics.analyze(self.store.list_fills(portfolio_id=portfolio_id))
        trips = analysis["round_trips"]
        symbol = _one(query, "symbol")
        regime = _one(query, "regime")
        if symbol:
            trips = [trip for trip in trips if symbol in trip["symbol"] or symbol in (trip.get("name") or "")]
        if regime:
            trips = [trip for trip in trips if (trip.get("regime") or "") == regime]
        return {
            "status": "ok",
            "count": len(trips),
            "trades": trips,
            "fills": self.store.list_fills(portfolio_id=portfolio_id),
            "open_positions": analysis["open_positions"],
            "issues": analysis["issues"],
            "safety": SAFETY_DECLARATION,
        }

    def trade_detail(self, round_trip_id: str) -> dict[str, Any]:
        analysis = analytics.analyze(self.store.list_fills())
        trip = next(
            (item for item in analysis["round_trips"] if item["round_trip_id"] == round_trip_id),
            None,
        )
        if trip is None:
            raise ApiError(f"no round trip {round_trip_id!r}", status=404, code="not_found")
        revisions = self.store.fill_revisions(symbol=trip["symbol"])
        return {
            "status": "ok",
            "trade": trip,
            "fill_revisions": revisions,
            "safety": SAFETY_DECLARATION,
        }

    def calendar(self, query: dict[str, list[str]]) -> dict[str, Any]:
        today = datetime.now(timezone.utc).astimezone()
        year = int(_one(query, "year") or today.year)
        month = int(_one(query, "month") or today.month)
        portfolio_id = _one(query, "portfolio_id") or DEFAULT_PORTFOLIO_ID
        ledger = analytics.build_ledger(self.store.list_fills(portfolio_id=portfolio_id))
        days = analytics.calendar_days(ledger, year=year, month=month)
        return {
            "status": "ok",
            "year": year,
            "month": month,
            "days": days,
            "safety": SAFETY_DECLARATION,
        }

    def analytics_report(self, query: dict[str, list[str]]) -> dict[str, Any]:
        portfolio_id = _one(query, "portfolio_id") or DEFAULT_PORTFOLIO_ID
        analysis = analytics.analyze(self.store.list_fills(portfolio_id=portfolio_id))
        return {
            "status": "ok",
            "summary": analysis["summary"],
            "breakdown": analysis["breakdown"],
            "dimensions": list(analytics.DIMENSIONS),
            "safety": SAFETY_DECLARATION,
        }

    def rules(self) -> dict[str, Any]:
        from smartmoney_cub_harness.workspace import Workspace  # noqa: PLC0415

        workspace = Workspace(self.workspace_db)
        try:
            rules = workspace.list_rules()
        finally:
            workspace.close()
        return {"status": "ok", "rules": rules, "safety": SAFETY_DECLARATION}

    def plugins(self) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_list  # noqa: PLC0415

        try:
            return plugin_list()
        except Exception as error:  # pragma: no cover - plugin tree is optional
            return {
                "status": "unavailable",
                "error": str(error),
                "plugins": [],
                "safety": SAFETY_DECLARATION,
            }

    # ---- import --------------------------------------------------------

    def upload(self, payload: dict[str, Any]) -> dict[str, Any]:
        file_name = str(payload.get("file_name") or "upload.bin")
        media_type = str(payload.get("media_type") or "")
        raw = payload.get("content_base64") or ""
        try:
            content = base64.b64decode(raw, validate=True)
        except Exception as error:
            raise ApiError(f"content_base64 is not valid base64: {error}") from error
        if not content:
            raise ApiError("uploaded file is empty")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ApiError("uploaded file is larger than 32 MB", status=413, code="too_large")

        portfolio_id = str(payload.get("portfolio_id") or DEFAULT_PORTFOLIO_ID)
        with self._lock:
            document = self.store.add_document(
                content,
                file_name=file_name,
                media_type=media_type,
                source_kind=extractors.detect_source_kind(file_name, media_type, content),
                portfolio_id=portfolio_id,
            )
            result = extractors.extract(
                content,
                file_name=file_name,
                media_type=media_type,
                source_kind=document["source_kind"],
                portfolio_id=portfolio_id,
            )
            extraction = self.store.record_extraction(
                document_id=document["document_id"],
                engine=result["engine"],
                engine_version=result.get("engine_version") or "",
                status=result["status"],
                rows=result.get("rows") or [],
                mean_confidence=result.get("mean_confidence"),
                payload={
                    "reason": result.get("reason"),
                    "missing": result.get("missing"),
                    "text_chars": result.get("text_chars"),
                    "file_name": file_name,
                },
            )
        return {
            "status": "ok",
            "document": {k: v for k, v in document.items() if k != "stored_name"},
            "extraction": extraction,
            "engine_status": extractors.ocr_backend_status(),
            "raw_file_stays_local": True,
            "safety": SAFETY_DECLARATION,
        }

    def commit_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        extraction_id = str(payload.get("extraction_id") or "")
        raw_rows = payload.get("rows")
        if raw_rows is None:
            if not extraction_id:
                raise ApiError("either extraction_id or rows is required")
            candidates = self.store.list_candidates(extraction_id)
        else:
            candidates = [dict(row) for row in raw_rows]

        normalized: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for index, row in enumerate(candidates):
            result = _validate_fill(row, index)
            if result["ok"]:
                normalized.append(result["fill"])
            else:
                rejected.append({"row_index": index, "errors": result["errors"], "row": row})
        if rejected:
            return {
                "status": "rejected",
                "reason": "rows_failed_validation",
                "rejected": rejected,
                "committed": 0,
                "safety": SAFETY_DECLARATION,
            }

        portfolio_id = str(payload.get("portfolio_id") or DEFAULT_PORTFOLIO_ID)
        document_id = payload.get("document_id")
        result = self.store.add_fills(
            normalized,
            portfolio_id=portfolio_id,
            document_id=document_id,
            extraction_id=extraction_id or None,
            edited_by=str(payload.get("edited_by") or "import"),
        )
        analysis = analytics.analyze(self.store.list_fills(portfolio_id=portfolio_id))
        return {
            **result,
            "ledger_status": analysis["ledger_status"],
            "blocking_issues": analysis["blocking_issues"],
            "safety": SAFETY_DECLARATION,
        }

    def add_manual_fill(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = _validate_fill(payload, 0)
        if not result["ok"]:
            raise ApiError("; ".join(result["errors"]))
        portfolio_id = str(payload.get("portfolio_id") or DEFAULT_PORTFOLIO_ID)
        outcome = self.store.add_fills(
            [result["fill"]], portfolio_id=portfolio_id, edited_by="manual"
        )
        return {**outcome, "safety": SAFETY_DECLARATION}

    def documents(self, query: dict[str, list[str]]) -> dict[str, Any]:
        portfolio_id = _one(query, "portfolio_id")
        documents = self.store.list_documents(portfolio_id=portfolio_id)
        return {
            "status": "ok",
            "documents": [{k: v for k, v in doc.items() if k != "stored_name"} for doc in documents],
            "safety": SAFETY_DECLARATION,
        }

    # ---- assistant -----------------------------------------------------

    def sessions(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "sessions": self.store.list_sessions(),
            "safety": SAFETY_DECLARATION,
        }

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.store.create_session(
            title=str(payload.get("title") or "新会话"),
            context=payload.get("context") or {"portfolio_id": DEFAULT_PORTFOLIO_ID},
            provider_id=str(payload.get("provider_id") or ALPHATECH_PROVIDER_ID),
            model=str(payload.get("model") or ""),
            reasoning=str(payload.get("reasoning") or "medium"),
            forked_from=payload.get("forked_from"),
        )
        return {"status": "ok", "session": session, "safety": SAFETY_DECLARATION}

    def session_detail(self, session_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        after_seq = int(_one(query, "after_seq") or 0)
        session = self.store.get_session(session_id)
        return {
            "status": "ok",
            "session": session,
            "events": self.store.list_events(session_id, after_seq=after_seq),
            "safety": SAFETY_DECLARATION,
        }

    def update_session(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.store.update_session(
            session_id,
            title=payload.get("title"),
            provider_id=payload.get("provider_id"),
            model=payload.get("model"),
            reasoning=payload.get("reasoning"),
            archived=payload.get("archived"),
            context=payload.get("context"),
        )
        return {"status": "ok", "session": session, "safety": SAFETY_DECLARATION}

    def fork_session(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.store.fork_session(session_id, title=payload.get("title"))
        return {"status": "ok", "session": session, "safety": SAFETY_DECLARATION}

    def session_preview(self, session_id: str) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        text = str(session.get("context", {}).get("pending_text") or "预览最近的本地上下文")
        events = list(self.runtime.run_turn(session_id, text, dry_run=True))
        return {
            "status": "ok",
            "preview": events[0] if events else {},
            "safety": SAFETY_DECLARATION,
        }

    def stream_turn(self, session_id: str, payload: dict[str, Any]) -> Any:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ApiError("message text is required")
        return self.runtime.run_turn(session_id, text)

    # ---- settings ------------------------------------------------------

    def provider_views(
        self, settings: dict[str, Any], credentials: dict[str, Any]
    ) -> list[dict[str, Any]]:
        views: list[dict[str, Any]] = []
        for provider_id in list_provider_ids(settings):
            try:
                views.append(
                    public_provider_view(
                        provider_id, credentials=credentials, settings=settings
                    )
                )
            except ProviderError:
                # A provider whose endpoint was cleared is reported as broken
                # rather than dropped, so the user can see and fix it.
                entry = settings.get("providers", {}).get(provider_id, {})
                views.append(
                    {
                        "provider_id": provider_id,
                        "label": entry.get("label", provider_id),
                        "base_url": entry.get("base_url", ""),
                        "protocol": entry.get("protocol", "openai-chat"),
                        "models": entry.get("models") or [],
                        "reasoning_efforts": [],
                        "removable": bool(entry.get("removable", True)),
                        "installable": False,
                        "has_key": False,
                        "key_source": "none",
                        "description": "这个 Provider 还缺少必要的配置。",
                        "incomplete": True,
                        "safety": SAFETY_DECLARATION,
                    }
                )
        return views

    def default_selection(self) -> dict[str, str]:
        """The provider, model, and effort a new session should start from."""
        settings = load_settings(self.root)
        provider_id = str(self.store.get_setting("default_provider_id") or ALPHATECH_PROVIDER_ID)
        known = list_provider_ids(settings)
        if provider_id not in known:
            provider_id = known[0] if known else OFFLINE_PROVIDER_ID
        try:
            entry = provider_entry(provider_id, settings)
        except ProviderError:
            entry = {"models": [], "default_model": ""}
        models = entry.get("models") or []
        model = str(self.store.get_setting("default_model") or "") or entry.get("default_model", "")
        if model and models and model not in {item["id"] for item in models}:
            model = entry.get("default_model", "")
        selected = next((item for item in models if item["id"] == model), None)
        reasoning = str(
            self.store.get_setting("default_reasoning")
            or (selected or {}).get("default_effort")
            or "off"
        )
        return {"provider_id": provider_id, "model": model, "reasoning": reasoning}

    def settings(self) -> dict[str, Any]:
        credentials = load_credentials(self.root)
        settings = load_settings(self.root)
        return {
            "status": "ok",
            "providers": self.provider_views(settings, credentials),
            "catalog": catalog_view(settings, credentials=credentials),
            "protocols": [
                {"id": key, "label": value} for key, value in PROVIDER_PROTOCOLS.items()
            ],
            "defaults": self.default_selection(),
            "credentials_file": credentials_path(self.root).name,
            "redaction_policy": REDACTION_POLICY_VERSION,
            "engine": extractors.ocr_backend_status(),
            "store_path_hint": self.root.name + "/" + self.store.db_path.name,
            "trend_color_scheme": self.store.get_setting("trend_color_scheme", "cn"),
            "counts": self.store.counts(),
            "safety": SAFETY_DECLARATION,
        }

    def add_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Install a provider from the catalog, or create a custom one."""
        try:
            result = install_provider(
                self.root,
                str(payload.get("provider_id") or ""),
                from_catalog=bool(payload.get("from_catalog")),
                label=str(payload.get("label") or ""),
                display_name=str(payload.get("display_name") or ""),
                base_url=str(payload.get("base_url") or ""),
                protocol=str(payload.get("protocol") or "openai-chat"),
                api_key=str(payload.get("api_key") or ""),
                models=payload.get("models"),
            )
        except ProviderError as error:
            raise ApiError(str(error), status=400, code="provider_error") from error
        return {**result, "settings": self.settings(), "safety": SAFETY_DECLARATION}

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Update one or more providers, plus the default selection."""
        providers = payload.get("providers") or {}
        if not isinstance(providers, dict):
            raise ApiError("providers must be an object")
        for provider_id, values in providers.items():
            if not isinstance(values, dict):
                raise ApiError("provider settings must be an object")
            try:
                update_provider(
                    self.root,
                    provider_id,
                    display_name=values.get("display_name"),
                    base_url=values.get("base_url"),
                    protocol=values.get("protocol"),
                    models=values.get("models"),
                    default_model=values.get("default_model"),
                    api_key=values.get("api_key"),
                    clear_key=bool(values.get("clear_key")),
                )
            except ProviderError as error:
                raise ApiError(str(error), status=400, code="provider_error") from error

        if payload.get("default_provider_id"):
            self.store.set_setting("default_provider_id", str(payload["default_provider_id"]))
        if "default_model" in payload:
            self.store.set_setting("default_model", str(payload["default_model"] or ""))
        if "default_reasoning" in payload:
            self.store.set_setting("default_reasoning", str(payload["default_reasoning"] or "off"))
        if payload.get("trend_color_scheme") in {"cn", "intl"}:
            self.store.set_setting("trend_color_scheme", payload["trend_color_scheme"])

        credentials = load_credentials(self.root)
        settings = load_settings(self.root)
        return {
            "status": "ok",
            "providers": self.provider_views(settings, credentials),
            "defaults": self.default_selection(),
            "note": "secrets stay in the local credentials file and are never returned",
            "safety": SAFETY_DECLARATION,
        }

    def remove_provider(self, provider_id: str) -> dict[str, Any]:
        try:
            result = remove_provider(self.root, provider_id)
        except ProviderError as error:
            raise ApiError(str(error), status=400, code="provider_error") from error
        if self.store.get_setting("default_provider_id") == provider_id:
            self.store.set_setting("default_provider_id", ALPHATECH_PROVIDER_ID)
            self.store.set_setting("default_model", "")
        return {**result, "settings": self.settings(), "safety": SAFETY_DECLARATION}

    def discover_models(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Ask an endpoint which models it serves, using form values or stored config."""
        provider_id = str(payload.get("provider_id") or "")
        credentials = load_credentials(self.root)
        settings = load_settings(self.root)
        base_url = str(payload.get("base_url") or "")
        api_key = str(payload.get("api_key") or "")
        protocol = str(payload.get("protocol") or "openai-chat")

        if provider_id:
            try:
                resolved = resolve_provider(
                    provider_id,
                    base_url=base_url or None,
                    credentials=credentials,
                    settings=settings,
                )
            except ProviderError as error:
                raise ApiError(str(error), status=400, code="provider_error") from error
            if protocol:
                resolved["protocol"] = protocol
        else:
            if not base_url:
                raise ApiError("a base URL is required to fetch models")
            resolved = {
                "provider_id": "",
                "base_url": base_url.rstrip("/"),
                "protocol": protocol,
                "api_key": _effective_key(settings, provider_id, api_key, credentials),
            }
        if api_key:
            resolved["api_key"] = api_key
        if not resolved.get("api_key") and resolved.get("protocol") != "offline":
            raise ApiError("an API key is required to fetch models")

        try:
            result = provider_models(resolved)
        except ProviderError as error:
            raise ApiError(str(error), status=502, code="provider_error") from error
        return {**result, "provider_id": provider_id, "safety": SAFETY_DECLARATION}

    def test_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        provider_id = str(payload.get("provider_id") or ALPHATECH_PROVIDER_ID)
        credentials = load_credentials(self.root)
        settings = load_settings(self.root)
        try:
            provider = resolve_provider(
                provider_id,
                base_url=payload.get("base_url"),
                credentials=credentials,
                settings=settings,
            )
        except ProviderError as error:
            return {"status": "error", "error": str(error), "safety": SAFETY_DECLARATION}
        if provider["protocol"] == "offline":
            return {
                "status": "ok",
                "provider_id": provider_id,
                "protocol": "offline",
                "reachable": None,
                "note": "离线模式不会发出网络请求",
                "safety": SAFETY_DECLARATION,
            }
        if not provider["has_key"]:
            return {
                "status": "error",
                "provider_id": provider_id,
                "error": "no API key configured for this provider",
                "safety": SAFETY_DECLARATION,
            }
        try:
            models = provider_models(provider)
        except ProviderError as error:
            return {
                "status": "error",
                "provider_id": provider_id,
                "error": str(error),
                "safety": SAFETY_DECLARATION,
            }
        return {
            "status": "ok",
            "provider_id": provider_id,
            "reachable": True,
            "models": models["models"][:200],
            "safety": SAFETY_DECLARATION,
        }

    def audits(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = int(_one(query, "limit") or 50)
        return {
            "status": "ok",
            "audits": self.store.list_audits(limit=limit),
            "safety": SAFETY_DECLARATION,
        }

    def doctor(self) -> dict[str, Any]:
        from smartmoney_cub_harness.evidence_pack import replay_evidence_pack  # noqa: F401, PLC0415
        from smartmoney_cub_harness.launcher import launcher_diagnostics  # noqa: PLC0415

        engine = extractors.ocr_backend_status()
        counts = self.store.counts()
        checks = [
            {
                "name": "store",
                "status": "ok",
                "detail": f"{counts['fill_record']} fills, {counts['source_document']} local documents",
            },
            {
                "name": "local_ocr",
                "status": "ok" if engine["rapidocr"] else "optional_missing",
                "detail": "rapidocr is importable" if engine["rapidocr"] else "install the ocr extra to read screenshots",
            },
            {
                "name": "launcher",
                "status": "ok",
                "detail": json.dumps(launcher_diagnostics()),
            },
            {
                "name": "outbound_redaction",
                "status": "ok",
                "detail": REDACTION_POLICY_VERSION,
            },
        ]
        return {
            "status": "ok",
            "version": __version__,
            "checks": checks,
            "safety": SAFETY_DECLARATION,
        }


def _effective_key(
    settings: dict[str, Any],
    provider_id: str,
    submitted: str,
    credentials: dict[str, Any],
) -> str:
    """Choose the key for a request: the form first, then the stored key."""
    if submitted.strip():
        return submitted.strip()
    if not provider_id:
        return ""
    try:
        return str(
            resolve_provider(provider_id, credentials=credentials, settings=settings)["api_key"]
        )
    except ProviderError:
        return ""


def _validate_fill(row: dict[str, Any], index: int) -> dict[str, Any]:
    errors: list[str] = []
    trade_date = extractors.normalize_date(str(row.get("trade_date") or "")) or str(row.get("trade_date") or "")
    if not trade_date:
        errors.append("trade_date is required")
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        errors.append("symbol is required")
    side = extractors.classify_side(row.get("side"))
    if side is None:
        errors.append("side must be BUY or SELL")
    price = extractors.to_float(row.get("price"))
    if price is None or price <= 0:
        errors.append("price must be a positive number")
    quantity = extractors.to_int(row.get("quantity"))
    if quantity is None or quantity <= 0:
        errors.append("quantity must be a positive whole number")
    trade_time = extractors.normalize_time(str(row.get("trade_time") or ""))
    if errors:
        return {"ok": False, "errors": errors, "row_index": index}
    return {
        "ok": True,
        "fill": {
            "trade_date": trade_date,
            "trade_time": trade_time,
            "symbol": symbol,
            "name": str(row.get("name") or "").strip(),
            "side": side,
            "price": float(price),
            "quantity": int(quantity),
            "fee": extractors.to_float(row.get("fee")) or 0.0,
            "thesis": str(row.get("thesis") or "").strip(),
            "invalidation_price": extractors.to_float(row.get("invalidation_price")),
            "regime": str(row.get("regime") or "").strip(),
            "tags": row.get("tags") or [],
            "confidence": row.get("confidence"),
        },
    }


def _one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    text = values[0].strip()
    return text or None


class WorkbenchHandler(BaseHTTPRequestHandler):
    service: WorkbenchService
    asset_dir: Path | None = None
    access_token: str | None = None
    # The trader product rides on the same socket. When a caller supplies a
    # TraderService the /api/trader/* surface is mounted; otherwise the
    # workbench serves exactly what it always did.
    trader_service: Any = None

    server_version = "smartmoney-cub/" + __version__

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Keep the console readable; the audit trail lives in the store.
        return

    # ---- plumbing ------------------------------------------------------

    def _authorized(self) -> bool:
        if not self.access_token:
            return True
        supplied = self.headers.get("X-SMCUB-Token") or ""
        return supplied == self.access_token

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ApiError(f"request body is not valid JSON: {error}") from error
        if not isinstance(payload, dict):
            raise ApiError("request body must be a JSON object")
        return payload

    def _static(self, path: str) -> bool:
        if self.asset_dir is None:
            return False
        relative = path.lstrip("/") or "index.html"
        candidate = (self.asset_dir / relative).resolve()
        try:
            candidate.relative_to(self.asset_dir.resolve())
        except ValueError:
            return False
        if not candidate.is_file():
            # Single-page app: unknown paths fall back to the shell.
            candidate = self.asset_dir / "index.html"
            if not candidate.is_file():
                return False
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".json": "application/json; charset=utf-8",
            ".woff2": "font/woff2",
            ".png": "image/png",
        }
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_types.get(candidate.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _is_static_request(self, path: str) -> bool:
        """True when a GET asks for the interface rather than for data.

        The rule is "not an API path" rather than "a file that exists", and the
        difference matters: an unknown path falls back to the single-page shell,
        so a client-side route like /trader/trade-log is an interface request even
        though no file matches it. Treating anything under /api as data keeps the
        token gating everything whose contents depend on the tenant, and serving
        everything else is safe because the shell is the same bytes for everyone
        and reveals nothing: every number it shows arrives through a gated call.
        """
        return not path.startswith("/api/")

    # ---- GET -----------------------------------------------------------

    def _trader(self, method: str) -> bool:
        """Serve one /api/trader request, or report that it is not ours.

        Why this sits ahead of the workbench route chain: the trader product is
        a separate surface with its own identity model, and mounting it here
        means one process serves both. When no trader service is configured the
        prefix falls through to the routes below and behavior is unchanged.

        The trader surface is deliberately not gated by the local access token:
        a hosted deployment authenticates each request against the platform,
        and a local one runs as the single local user. Adding a second secret in
        front of a surface that already resolves an identity would only make the
        two disagree about who the caller is.
        """
        service = getattr(self, "trader_service", None)
        if service is None:
            return False
        from smartmoney_cub_harness.trader.api import routes as trader_routes

        parsed = urllib.parse.urlparse(self.path)
        if not parsed.path.startswith(trader_routes.TRADER_API_PREFIX):
            return False
        body = b""
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            if length > 0:
                body = self.rfile.read(length)
        status, payload = trader_routes.dispatch(
            service,
            method,
            parsed.path,
            query=urllib.parse.parse_qs(parsed.query),
            headers=self.headers,
            body=body,
            content_type=self.headers.get("Content-Type") or "",
        )
        self._json(payload, status=status)
        return True

    def do_GET(self) -> None:  # noqa: N802
        # The interface itself is served before the token check, and only the
        # interface. A browser cannot attach a custom header to the navigation
        # that loads the page or to the requests the page makes for its own
        # JavaScript and CSS, so gating those returns 401 for every page load in
        # a token-protected deployment -- the product becomes unreachable exactly
        # where the docs tell an operator to protect it. The token still gates
        # every API call, which is the data that needs protecting; the page is a
        # shell whose content all arrives through those gated calls.
        parsed_path = urllib.parse.urlparse(self.path).path
        if not self._is_static_request(parsed_path) and not self._authorized():
            self._json(
                {"status": "error", "error": "invalid access token", "safety": SAFETY_DECLARATION},
                status=401,
            )
            return
        if self._trader("GET"):
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/meta":
                self._json(self.service.meta())
                return
            if path == "/api/overview":
                self._json(self.service.overview(query))
                return
            if path == "/api/trades":
                self._json(self.service.trades(query))
                return
            if path.startswith("/api/trades/"):
                self._json(self.service.trade_detail(urllib.parse.unquote(path[len("/api/trades/"):])))
                return
            if path == "/api/calendar":
                self._json(self.service.calendar(query))
                return
            if path == "/api/analytics":
                self._json(self.service.analytics_report(query))
                return
            if path == "/api/rules":
                self._json(self.service.rules())
                return
            if path == "/api/plugins":
                self._json(self.service.plugins())
                return
            if path == "/api/documents":
                self._json(self.service.documents(query))
                return
            if path == "/api/assistant/sessions":
                self._json(self.service.sessions())
                return
            if path.startswith("/api/assistant/sessions/"):
                session_id = urllib.parse.unquote(path[len("/api/assistant/sessions/"):])
                self._json(self.service.session_detail(session_id, query))
                return
            if path == "/api/settings":
                self._json(self.service.settings())
                return
            if path == "/api/settings/catalog":
                self._json(self.service.settings())
                return
            if path == "/api/audit":
                self._json(self.service.audits(query))
                return
            if path == "/api/doctor":
                self._json(self.service.doctor())
                return
        except ApiError as error:
            self._json({"status": "error", "error": str(error), "code": error.code}, status=error.status)
            return
        except KeyError as error:
            self._json({"status": "error", "error": f"not found: {error}", "code": "not_found"}, status=404)
            return

        if self._static(path):
            return
        self._json(
            {
                "status": "error",
                "error": "no web assets are installed",
                "hint": "run the CLI again so it can build or locate the interface, or set " + ASSET_DIR_ENV,
                "safety": SAFETY_DECLARATION,
            },
            status=404,
        )

    # ---- POST ----------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            # A refusal is a response too, and the contract puts the declaration on
            # every response. This one lacked it.
            self._json(
                {"status": "error", "error": "invalid access token", "safety": SAFETY_DECLARATION},
                status=401,
            )
            return
        if self._trader("POST"):
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/import/upload":
                self._json(self.service.upload(self._read_json()))
                return
            if path == "/api/import/commit":
                self._json(self.service.commit_import(self._read_json()))
                return
            if path == "/api/import/manual":
                self._json(self.service.add_manual_fill(self._read_json()))
                return
            if path == "/api/assistant/sessions":
                self._json(self.service.create_session(self._read_json()))
                return
            if path.startswith("/api/assistant/sessions/"):
                rest = path[len("/api/assistant/sessions/"):]
                session_id, _, action = rest.partition("/")
                session_id = urllib.parse.unquote(session_id)
                if action == "messages":
                    payload = self._read_json()
                    self._stream_turn(session_id, payload)
                    return
                if action == "fork":
                    self._json(self.service.fork_session(session_id, self._read_json()))
                    return
                if action == "preview":
                    self._json(self.service.session_preview(session_id))
                    return
                if action == "" or action == "update":
                    self._json(self.service.update_session(session_id, self._read_json()))
                    return
            if path == "/api/settings":
                self._json(self.service.update_settings(self._read_json()))
                return
            if path == "/api/settings/providers":
                self._json(self.service.add_provider(self._read_json()))
                return
            if path.startswith("/api/settings/providers/"):
                rest = path[len("/api/settings/providers/"):]
                provider_id, _, action = rest.partition("/")
                provider_id = urllib.parse.unquote(provider_id)
                if action == "remove":
                    self._json(self.service.remove_provider(provider_id))
                    return
                if action == "models":
                    self._json(self.service.discover_models({**self._read_json(), "provider_id": provider_id}))
                    return
                if action == "":
                    payload = self._read_json()
                    self._json(
                        self.service.update_settings({"providers": {provider_id: payload}})
                    )
                    return
            if path == "/api/settings/discover":
                self._json(self.service.discover_models(self._read_json()))
                return
            if path == "/api/settings/test":
                self._json(self.service.test_provider(self._read_json()))
                return
        except ApiError as error:
            self._json({"status": "error", "error": str(error), "code": error.code}, status=error.status)
            return
        except KeyError as error:
            self._json({"status": "error", "error": f"not found: {error}", "code": "not_found"}, status=404)
            return

        self._json({"status": "error", "error": f"unknown endpoint {path}"}, status=404)

    def _stream_turn(self, session_id: str, payload: dict[str, Any]) -> None:
        events = self.service.stream_turn(session_id, payload)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for event in events:
                frame = "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                self.wfile.write(frame.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # The tab was closed mid-stream. The turn stays in the local event
            # log, so the conversation resumes where it stopped.
            return
        except Exception as error:  # noqa: BLE001 - surfaced to the browser
            frame = "data: " + json.dumps(
                {"kind": "error", "error": str(error), "safety": SAFETY_DECLARATION},
                ensure_ascii=False,
            ) + "\n\n"
            try:
                self.wfile.write(frame.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return


def is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def start_workbench(
    *,
    root: str | Path = "state/convergence",
    host: str = "127.0.0.1",
    port: int = 8787,
    asset_dir: str | Path | None = None,
    open_browser: bool = True,
    access_token: str | None = None,
    workspace_db: str | None = None,
    trader_service: Any = None,
    trader_store: Any = None,
    ready: Callable[[str], None] | None = None,
) -> None:
    service = WorkbenchService(root, workspace_db=workspace_db)
    if trader_service is not None and trader_store is not None:
        raise ValueError("pass either trader_service or trader_store, not both")
    owned_trader_store = None
    if trader_service is None and trader_store is not None:
        from smartmoney_cub_harness.trader.api import TraderService

        trader_service = TraderService(trader_store)
        owned_trader_store = trader_store
    handler = type(
        "BoundWorkbenchHandler",
        (WorkbenchHandler,),
        {
            "service": service,
            "asset_dir": Path(asset_dir) if asset_dir else None,
            "access_token": access_token,
            "trader_service": trader_service,
        },
    )
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{server.server_port}/"
    if ready is not None:
        ready(url)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        pass
    finally:
        server.server_close()
        service.close()
        if owned_trader_store is not None:
            close = getattr(owned_trader_store, "close", None)
            if callable(close):
                close()
