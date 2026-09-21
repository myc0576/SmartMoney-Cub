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
import subprocess
import sys
from smartmoney_cub_harness.agent.providers import (
    ALPHATECH_PROVIDER_ID,
    default_settings,
    settings_path,
    OFFLINE_PROVIDER_ID,
    PROVIDER_PROTOCOLS,
    ProviderError,
    catalog_view,
    check_provider_models,
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
from smartmoney_cub_harness.agent.runtime import ReviewAgentRuntime, ReviewLifecycleError
from smartmoney_cub_harness.governance import GovernanceStore, profile_facts_from_trades
from smartmoney_cub_harness.local_state import LOCAL_STATE_DIR
from smartmoney_cub_harness.plugin_marketplace import MarketplaceStore
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

    def __init__(
        self,
        root: str | Path,
        *,
        workspace_db: str | None = None,
        trader_service: Any = None,
        dsh_bridge: Any = None,
    ) -> None:
        self.root = Path(root)
        self.store = Store(self.root)
        self.recovered_sessions = self.store.recover_interrupted_sessions()
        self.workspace_db = workspace_db or str(self.root / "workspace" / "review.db")
        self.trader_service = trader_service
        self._owned_trader_service = False
        if self.trader_service is None:
            from smartmoney_cub_harness.agent.tools import _detect_trader_service

            detected = _detect_trader_service(self.root)
            if detected is not None:
                self.trader_service = detected
                self._owned_trader_service = True
        self.runtime = ReviewAgentRuntime(
            self.store,
            credentials_root=str(self.root),
            workspace_db=self.workspace_db,
            trader_service=self.trader_service,
            dsh_bridge=dsh_bridge,
        )
        self.governance = GovernanceStore(self.root)
        self.marketplace = MarketplaceStore(self.root)
        self._lock = threading.Lock()

    def close(self) -> None:
        self.store.close()
        if getattr(self, "_owned_trader_service", False) and self.trader_service is not None:
            close = getattr(getattr(self.trader_service, "store", None), "close", None)
            if callable(close):
                close()


    # ---- profile / strategy governance --------------------------------

    def governance_view(self) -> dict[str, Any]:
        snapshot = self.governance.snapshot()
        return {
            "status": "ok",
            "profiles": snapshot.get("profiles", []),
            "strategies": snapshot.get("strategies", []),
            "evaluations": snapshot.get("evaluations", []),
            "promotions": snapshot.get("promotions", []),
            "events": snapshot.get("events", [])[-100:],
            "safety": SAFETY_DECLARATION,
        }

    def generate_profile(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        portfolio_id = str((payload or {}).get("portfolio_id") or DEFAULT_PORTFOLIO_ID)
        fills = self.store.list_fills(portfolio_id=portfolio_id)
        facts = profile_facts_from_trades(fills)
        source = str((payload or {}).get("source_snapshot") or f"fills:{len(fills)}")
        result = self.governance.create_baseline_from_import(
            source_snapshot=source, sample_count=len(fills), facts=facts
        )
        return {"status": "ok", **result, "safety": SAFETY_DECLARATION}

    def edit_profile(self, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.governance.edit_profile(profile_id, payload, edited_by="user")
        except KeyError as error:
            raise ApiError(f"no profile {profile_id!r}", status=404, code="not_found") from error
        return {"status": "ok", **result, "safety": SAFETY_DECLARATION}

    def create_chat_challenger(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = str(payload.get("text") or "")
        rules = payload.get("rules")
        if not isinstance(rules, list):
            rules = [{"rule": str(payload.get("rule") or text), "evidence_required": True}]
        result = self.governance.create_challenger_from_chat(
            text=text,
            rules=rules,
            family=str(payload.get("family") or "general"),
            metrics=payload.get("metrics") if isinstance(payload.get("metrics"), dict) else None,
        )
        return {"status": "ok", **result, "safety": SAFETY_DECLARATION}

    def evaluate_strategy(self, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            evaluation = self.governance.evaluate(strategy_id, payload.get("metrics") if isinstance(payload.get("metrics"), dict) else None)
        except KeyError as error:
            raise ApiError(f"no strategy {strategy_id!r}", status=404, code="not_found") from error
        return {"status": "ok", "evaluation": evaluation, "safety": SAFETY_DECLARATION}

    def request_promotion(self, strategy_id: str) -> dict[str, Any]:
        try:
            request = self.governance.request_promotion(strategy_id)
        except KeyError as error:
            raise ApiError(f"no strategy {strategy_id!r}", status=404, code="not_found") from error
        except ValueError as error:
            raise ApiError(str(error), code="promotion_refused") from error
        return {"status": "ok", "promotion": request, "safety": SAFETY_DECLARATION}

    def confirm_promotion(self, promotion_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.governance.confirm_promotion(promotion_id, str(payload.get("note") or ""))
        except KeyError as error:
            raise ApiError(f"no promotion {promotion_id!r}", status=404, code="not_found") from error
        except ValueError as error:
            raise ApiError(str(error), code="promotion_refused") from error
        return {"status": "ok", **result, "safety": SAFETY_DECLARATION}

    def rollback_strategy(self, strategy_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.governance.rollback(strategy_id, str(payload.get("note") or ""))
        except KeyError as error:
            raise ApiError(f"no strategy {strategy_id!r}", status=404, code="not_found") from error
        except ValueError as error:
            raise ApiError(str(error), code="rollback_refused") from error
        return {"status": "ok", **result, "safety": SAFETY_DECLARATION}

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

    def _analysis(
        self,
        portfolio_id: str | None = None,
        *,
        year: int | None = None,
        month: int | None = None,
    ) -> dict[str, Any]:
        return self.runtime.toolbox._analysis(portfolio_id=portfolio_id, year=year, month=month)

    def overview(self, query: dict[str, list[str]]) -> dict[str, Any]:
        portfolio_id = _one(query, "portfolio_id") or DEFAULT_PORTFOLIO_ID
        today = datetime.now(timezone.utc).astimezone()
        year = int(_one(query, "year") or today.year)
        month = int(_one(query, "month") or today.month)
        analysis = self._analysis(portfolio_id=portfolio_id, year=year, month=month)
        fills = self.store.list_fills(portfolio_id=portfolio_id)
        if not fills and self.trader_service is not None:
            try:
                from smartmoney_cub_harness.trader.auth.identity import LOCAL_CONTEXT

                fills = self.trader_service._fills(LOCAL_CONTEXT, limit=100000)
            except Exception:
                pass
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
            "fill_count": len(fills),
            "recent_documents": self.store.list_documents(portfolio_id=portfolio_id)[:5],
            "safety": SAFETY_DECLARATION,
        }

    def trades(self, query: dict[str, list[str]]) -> dict[str, Any]:
        portfolio_id = _one(query, "portfolio_id") or DEFAULT_PORTFOLIO_ID
        analysis = self._analysis(portfolio_id=portfolio_id)
        trips = analysis["round_trips"]
        symbol = _one(query, "symbol")
        regime = _one(query, "regime")
        if symbol:
            trips = [trip for trip in trips if symbol in trip["symbol"] or symbol in (trip.get("name") or "")]
        if regime:
            trips = [trip for trip in trips if (trip.get("regime") or "") == regime]
        fills = self.store.list_fills(portfolio_id=portfolio_id)
        if not fills and self.trader_service is not None:
            try:
                from smartmoney_cub_harness.trader.auth.identity import LOCAL_CONTEXT

                fills = self.trader_service._fills(LOCAL_CONTEXT, limit=100000)
            except Exception:
                pass
        return {
            "status": "ok",
            "count": len(trips),
            "trades": trips,
            "fills": fills,
            "open_positions": analysis["open_positions"],
            "issues": analysis["issues"],
            "safety": SAFETY_DECLARATION,
        }

    def trade_detail(self, round_trip_id: str) -> dict[str, Any]:
        analysis = self._analysis()
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
        analysis = self._analysis(portfolio_id=portfolio_id, year=year, month=month)
        return {
            "status": "ok",
            "year": year,
            "month": month,
            "days": analysis["calendar"],
            "safety": SAFETY_DECLARATION,
        }

    def analytics_report(self, query: dict[str, list[str]]) -> dict[str, Any]:
        portfolio_id = _one(query, "portfolio_id") or DEFAULT_PORTFOLIO_ID
        analysis = self._analysis(portfolio_id=portfolio_id)
        return {
            "status": "ok",
            "summary": analysis["summary"],
            "breakdown": analysis["breakdown"],
            "dimensions": list(analytics.DIMENSIONS),
            "safety": SAFETY_DECLARATION,
        }

    def rules(self) -> dict[str, Any]:
        """List the rule library with the promotion blockers on each row.

        The blockers are computed at read time from the one frozen threshold
        check the rest of the product uses, so the interface can say what a rule
        is still missing without storing a second, drift-prone copy of it.
        """
        from smartmoney_cub_harness.workspace import Workspace  # noqa: PLC0415

        workspace = Workspace(self.workspace_db)
        try:
            rules = workspace.list_rules_with_blockers()
        finally:
            workspace.close()
        return {"status": "ok", "rules": rules, "safety": SAFETY_DECLARATION}

    def promote_rule(self, rule_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Promote one challenger rule to champion behind the human gate.

        The note is required and withheld no default: it is the artifact that
        records who authorized the champion row and why. A blank note is refused
        rather than substituted, because a defaulted note would turn the human
        gate into a rubber stamp.
        """
        from smartmoney_cub_harness.workspace import Workspace  # noqa: PLC0415

        note = str(payload.get("note") or "").strip()
        if not note:
            raise ApiError("晋级必须写一条确认说明", code="note_required")
        workspace = Workspace(self.workspace_db)
        try:
            if workspace.get_rule(rule_id) is None:
                raise ApiError(f"no rule {rule_id!r}", status=404, code="not_found")
            try:
                record = workspace.promote_rule(rule_id=rule_id, note=note)
            except ValueError as error:
                raise ApiError(str(error), code="promotion_refused") from error
            # Re-read the row so the response has the same shape as one entry of
            # GET /api/rules -- status, metrics, and the recomputed blockers.
            # Returning the write result instead would give the caller a
            # differently shaped object with rule_status where a listed rule has
            # status, and the interface would have to special-case it.
            promoted = next(
                (
                    rule
                    for rule in workspace.list_rules_with_blockers()
                    if rule["rule_id"] == rule_id
                ),
                None,
            )
        finally:
            workspace.close()
        return {
            "status": "ok",
            "rule": promoted or record,
            "promotion_note": record.get("promotion_note", note),
            "safety": SAFETY_DECLARATION,
        }

    def _plugin_state_db(self) -> str | None:
        candidates = [
            self.root / "plugins" / "plugin_state.db",
            self.root.parent / "plugins" / "plugin_state.db",
            Path("state/plugins/plugin_state.db"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return None

    def plugins(self) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_list  # noqa: PLC0415

        try:
            result = plugin_list(state_db=self._plugin_state_db())
            result["marketplace"] = self.marketplace.view()
            return result
        except Exception as error:  # pragma: no cover - plugin tree is optional
            return {
                "status": "unavailable",
                "error": str(error),
                "plugins": [],
                "marketplace": self.marketplace.view(),
                "safety": SAFETY_DECLARATION,
            }

    def plugin_market(self) -> dict[str, Any]:
        return {"status": "ok", **self.marketplace.view(), "safety": SAFETY_DECLARATION}

    def install_market_plugin(self, plugin_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.marketplace.install(plugin_id, payload.get("config") if isinstance(payload.get("config"), dict) else None)
        except KeyError as error:
            raise ApiError(f"no official plugin {plugin_id!r}", status=404, code="not_found") from error

    def update_market_plugin(self, plugin_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.marketplace.update(plugin_id, confirm=bool(payload.get("confirm")))
        except KeyError as error:
            raise ApiError(f"plugin {plugin_id!r} is not installed", status=404, code="not_found") from error

    def set_market_plugin_enabled(self, plugin_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.marketplace.set_enabled(plugin_id, bool(payload.get("enabled", True)))
        except KeyError as error:
            raise ApiError(f"plugin {plugin_id!r} is not installed", status=404, code="not_found") from error

    def plugin_enable(self, plugin_id: str) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_enable  # noqa: PLC0415

        try:
            return plugin_enable(plugin_id, state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to enable plugin: {error}") from error

    def plugin_disable(self, plugin_id: str) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_disable  # noqa: PLC0415

        try:
            return plugin_disable(plugin_id, state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to disable plugin: {error}") from error

    def plugin_catalog(self) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_catalog  # noqa: PLC0415

        try:
            return plugin_catalog()
        except Exception as error:
            raise ApiError(f"failed to read plugin catalog: {error}") from error

    def plugin_detail(self, plugin_id: str) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_detail  # noqa: PLC0415

        try:
            return plugin_detail(plugin_id, state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to read plugin detail: {error}") from error

    def plugin_configure(self, plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_configure  # noqa: PLC0415

        try:
            return plugin_configure(plugin_id, config, state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to configure plugin: {error}") from error

    def plugin_reload(self) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import profile_reload  # noqa: PLC0415

        try:
            return profile_reload(state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to reload plugins: {error}") from error

    def open_config_file(self) -> dict[str, Any]:
        # DSH style openDocument: opens the configuration file in native desktop editor
        providers_file = settings_path(self.root)
        if not providers_file.is_file():
            providers_file.parent.mkdir(parents=True, exist_ok=True)
            providers_file.write_text(
                json.dumps(default_settings(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        resolved = providers_file.resolve()
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-t", str(resolved)])
            elif sys.platform == "win32":
                os.startfile(str(resolved))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(resolved)])
            return {
                "status": "ok",
                "path": str(resolved),
                "safety": SAFETY_DECLARATION,
            }
        except Exception as error:
            return {
                "status": "error",
                "error": f"无法打开配置文件: {error}",
                "path": str(resolved),
                "safety": SAFETY_DECLARATION,
            }

    def plugin_enable(self, plugin_id: str) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_enable  # noqa: PLC0415

        try:
            return plugin_enable(plugin_id, state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to enable plugin: {error}") from error

    def plugin_disable(self, plugin_id: str) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_disable  # noqa: PLC0415

        try:
            return plugin_disable(plugin_id, state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to disable plugin: {error}") from error

    def plugin_catalog(self) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_catalog  # noqa: PLC0415

        try:
            return plugin_catalog()
        except Exception as error:
            raise ApiError(f"failed to read plugin catalog: {error}") from error

    def plugin_detail(self, plugin_id: str) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_detail  # noqa: PLC0415

        try:
            return plugin_detail(plugin_id, state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to read plugin detail: {error}") from error

    def plugin_configure(self, plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import plugin_configure  # noqa: PLC0415

        try:
            return plugin_configure(plugin_id, config, state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to configure plugin: {error}") from error

    def plugin_reload(self) -> dict[str, Any]:
        from smartmoney_cub_harness.plugin_cli import profile_reload  # noqa: PLC0415

        try:
            return profile_reload(state_db=self._plugin_state_db())
        except Exception as error:
            raise ApiError(f"failed to reload plugins: {error}") from error

    def open_config_file(self) -> dict[str, Any]:
        # DSH style openDocument: opens the configuration file in native desktop editor
        providers_file = settings_path(self.root)
        if not providers_file.is_file():
            providers_file.parent.mkdir(parents=True, exist_ok=True)
            providers_file.write_text(
                json.dumps(default_settings(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        resolved = providers_file.resolve()
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-t", str(resolved)])
            elif sys.platform == "win32":
                os.startfile(str(resolved))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(resolved)])
            return {
                "status": "ok",
                "path": str(resolved),
                "safety": SAFETY_DECLARATION,
            }
        except Exception as error:
            return {
                "status": "error",
                "error": f"无法打开配置文件: {error}",
                "path": str(resolved),
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
        if self.trader_service is not None:
            try:
                from smartmoney_cub_harness.trader.auth.identity import LOCAL_CONTEXT

                self.trader_service.import_trades(LOCAL_CONTEXT, rows=normalized)
            except Exception:
                pass
        onboarding = self.governance.create_baseline_from_import(
            source_snapshot=str(document_id or extraction_id or f"fills:{len(normalized)}"),
            sample_count=len(normalized),
            facts=profile_facts_from_trades(normalized),
        )
        analysis = self._analysis(portfolio_id=portfolio_id)
        return {
            **result,
            "onboarding": onboarding,
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
        if self.trader_service is not None:
            try:
                from smartmoney_cub_harness.trader.auth.identity import LOCAL_CONTEXT

                self.trader_service.import_trades(LOCAL_CONTEXT, rows=[result["fill"]])
            except Exception:
                pass
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

        # A rule expressed in chat is a governance artifact, not an invisible
        # side effect. Persist and stream the challenger card before the model
        # turn so the user can inspect and explicitly promote it even when the
        # selected provider is unavailable.
        def events() -> Any:
            artifact = self.create_chat_challenger({
                "text": text,
                "rules": payload.get("rules"),
                "family": payload.get("family") or "general",
                "metrics": payload.get("metrics"),
            })
            if artifact.get("created"):
                self.store.append_event(
                    session_id,
                    kind="artifact",
                    payload={"artifact": artifact},
                )
                yield {
                    "kind": "artifact",
                    "artifact": artifact,
                    "safety": SAFETY_DECLARATION,
                }
            yield from self.runtime.run_turn(session_id, text)

        return events()

    def review_scope(self, session_id: str) -> dict[str, Any]:
        try:
            return self.runtime.review_scope_preview(session_id)
        except ReviewLifecycleError as error:
            raise ApiError(str(error), status=400, code="review_scope_error") from None

    def confirm_review_scope(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.runtime.confirm_review_scope(session_id, payload)
        except ReviewLifecycleError as error:
            raise ApiError(str(error), status=400, code="review_scope_error") from None

    def cancel_turn(self, session_id: str) -> dict[str, Any]:
        return self.runtime.cancel_turn(session_id)

    def resume_turn(self, session_id: str, payload: dict[str, Any]) -> Any:
        try:
            return self.runtime.resume_turn(session_id, str(payload.get("text") or ""))
        except ReviewLifecycleError as error:
            raise ApiError(str(error), status=400, code="resume_error") from None

    def record_challenger(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.runtime.record_challenger_proposal(session_id, payload.get("proposal") or payload)
        except ReviewLifecycleError as error:
            raise ApiError(str(error), status=400, code="challenger_error") from None

    def record_review_package(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.runtime.record_review_package(
                session_id, payload.get("review_package") or payload
            )
        except ReviewLifecycleError as error:
            raise ApiError(str(error), status=400, code="review_package_error") from None

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
            "agent_presets": {
                "system_prompt": str(self.store.get_setting("agent_system_prompt", "") or ""),
                "default_effort": str(self.store.get_setting("agent_default_effort", "medium") or "medium"),
                "context_strategy": str(self.store.get_setting("agent_context_strategy", "summary_compact") or "summary_compact"),
            },
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
        if "agent_presets" in payload and isinstance(payload["agent_presets"], dict):
            presets = payload["agent_presets"]
            if "system_prompt" in presets:
                self.store.set_setting("agent_system_prompt", str(presets["system_prompt"] or ""))
            if "default_effort" in presets:
                self.store.set_setting("agent_default_effort", str(presets["default_effort"] or "medium"))
            if "context_strategy" in presets:
                self.store.set_setting("agent_context_strategy", str(presets["context_strategy"] or "summary_compact"))

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
        if (
            not resolved.get("api_key")
            and resolved.get("protocol") != "offline"
            and resolved.get("requires_key", True)
        ):
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
        if provider.get("requires_key", True) and not provider["has_key"]:
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

    def check_models(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Reconcile a provider's declared models against what the endpoint serves.

        This is the answer to a model list that is not the latest. The catalog is
        a snapshot of an endpoint that keeps moving, so it rots. Rather than
        trusting it, this asks the endpoint and merges the answer into the
        declared list: a model that disappeared is marked stale but kept, and
        anything new is appended. The selector therefore stops offering ids that
        can never answer without silently deleting a choice the user made.

        A failed lookup is reported as a failed lookup. It never marks every
        model stale, because an outage teaches us nothing about the catalog.
        """
        provider_id = str(payload.get("provider_id") or "")
        if not provider_id:
            raise ApiError("a provider_id is required to check models")
        credentials = load_credentials(self.root)
        settings = load_settings(self.root)
        try:
            result = check_provider_models(
                provider_id, credentials=credentials, settings=settings
            )
        except ProviderError as error:
            raise ApiError(str(error), status=400, code="provider_error") from error
        # The reconciled list is written back, otherwise the correction is only a
        # message and the stale entry survives the next reload. A failed lookup
        # is never written: an outage must not rewrite the user's catalog.
        persisted = False
        if result.get("verified"):
            try:
                update_provider(self.root, provider_id, models=result["models"])
                persisted = True
            except ProviderError:
                persisted = False
        return {
            **result,
            "provider_id": provider_id,
            "persisted": persisted,
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

    def jev_connection(self) -> dict[str, Any]:
        from smartmoney_cub_harness.jev.connection import describe
        return describe(self.root)

    def update_jev_connection(self, payload: dict[str, Any]) -> dict[str, Any]:
        from smartmoney_cub_harness.jev.connection import save
        try:
            with self._lock:
                return save(self.root, payload)
        except ValueError as error:
            raise ApiError(str(error), code="jev_settings_error") from error
        except OSError as error:
            raise ApiError("本地凭据保存失败；请检查目录权限。", status=500) from error

    def test_jev_connection(self) -> dict[str, Any]:
        from smartmoney_cub_harness.jev.connection import probe
        return probe(self.root)

    def jev_status(self) -> dict[str, Any]:
        """Diagnostic state of the Jev reasoning engine and configured backends."""
        try:
            from smartmoney_cub_harness.jev.cli import run_jev_doctor  # noqa: PLC0415
            doc = run_jev_doctor(self.root)
        except ImportError as err:
            return {
                "engine": "jev",
                "provider_id": "none",
                "model_requested": "",
                "model_resolved": None,
                "available": False,
                "safety": SAFETY_DECLARATION,
                "reason": f"import_error: {err}",
                "detail": str(err),
            }

        backends = doc.get("backends", {})
        direct = backends.get("typesafe-direct", {})
        openrouter = backends.get("openrouter-jev", {})

        active = direct if direct.get("available") else (openrouter if openrouter.get("available") else direct)

        return {
            "engine": doc.get("engine", "jev"),
            "provider_id": active.get("provider_id", "typesafe"),
            "model_requested": active.get("model_requested", ""),
            "model_resolved": active.get("model_resolved"),
            "available": bool(active.get("available", False)),
            "safety": doc.get("safety", SAFETY_DECLARATION),
            "reason": active.get("reason"),
            "detail": doc,
            "backends": backends,
        }

    def jev_tracks(self) -> dict[str, Any]:
        """Track definitions and question packs for the Jev reasoning engine."""
        from dataclasses import asdict  # noqa: PLC0415
        from smartmoney_cub_harness.jev.questions import available_tracks, build_questions  # noqa: PLC0415

        load_track = None
        try:
            from smartmoney_cub_harness.benchmark.cases import load_track  # noqa: PLC0415
        except ImportError:
            pass

        tracks_data = []
        for track_id in available_tracks():
            questions = build_questions(track_id)
            case_count = 60
            if load_track is not None:
                try:
                    case_count = len(load_track(track_id))
                except Exception:
                    pass
            tracks_data.append({
                "track": track_id,
                "question_count": len(questions),
                "case_count": case_count,
                "questions": [asdict(q) for q in questions],
            })
        return {
            "tracks": tracks_data,
            "safety": SAFETY_DECLARATION,
        }

    def agents(self) -> dict[str, Any]:
        """Scan detected coding agents and their integration status."""
        from dataclasses import asdict  # noqa: PLC0415
        try:
            from smartmoney_cub_harness.agent.integrations import scan_agents  # noqa: PLC0415
            agent_list = [asdict(a) for a in scan_agents()]
        except ImportError as err:
            raise ApiError(f"Agent integration subsystem unavailable: {err}", status=503)

        return {
            "agents": agent_list,
            "safety": SAFETY_DECLARATION,
        }

    def agents_apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        from dataclasses import asdict  # noqa: PLC0415
        agent_id = str(payload.get("agent_id") or "").strip()
        if not agent_id:
            raise ApiError("agent_id is required", status=400, code="missing_parameter")
        dry_run = bool(payload.get("dry_run", False))
        try:
            from smartmoney_cub_harness.agent.integrations import apply_agent  # noqa: PLC0415
            res = apply_agent(agent_id, dry_run=dry_run)
            return {"agent": asdict(res), "safety": SAFETY_DECLARATION}
        except ImportError as err:
            raise ApiError(f"Agent integration subsystem unavailable: {err}", status=503)
        except (KeyError, ValueError):
            raise ApiError(f"unknown agent: {agent_id}", status=404, code="not_found")

    def agents_disable(self, payload: dict[str, Any]) -> dict[str, Any]:
        from dataclasses import asdict  # noqa: PLC0415
        agent_id = str(payload.get("agent_id") or "").strip()
        if not agent_id:
            raise ApiError("agent_id is required", status=400, code="missing_parameter")
        try:
            from smartmoney_cub_harness.agent.integrations import disable_agent  # noqa: PLC0415
            res = disable_agent(agent_id)
            return {"agent": asdict(res), "safety": SAFETY_DECLARATION}
        except ImportError as err:
            raise ApiError(f"Agent integration subsystem unavailable: {err}", status=503)
        except (KeyError, ValueError):
            raise ApiError(f"unknown agent: {agent_id}", status=404, code="not_found")

    def agents_restore(self, payload: dict[str, Any]) -> dict[str, Any]:
        from dataclasses import asdict  # noqa: PLC0415
        agent_id = str(payload.get("agent_id") or "").strip()
        if not agent_id:
            raise ApiError("agent_id is required", status=400, code="missing_parameter")
        try:
            from smartmoney_cub_harness.agent.integrations import restore_agent  # noqa: PLC0415
            res = restore_agent(agent_id)
            return {"agent": asdict(res), "safety": SAFETY_DECLARATION}
        except ImportError as err:
            raise ApiError(f"Agent integration subsystem unavailable: {err}", status=503)
        except (KeyError, ValueError):
            raise ApiError(f"unknown agent: {agent_id}", status=404, code="not_found")

    def _benchmark_dir(self) -> Path | None:
        resolved = self._resolve_benchmark_run()
        if resolved:
            return resolved[0]
        return None

    def _resolve_benchmark_run(self) -> tuple[Path, str, dict[str, Any]] | None:
        """Resolve active benchmark run directory, source ('local' or 'bundled'), and run payload."""
        roots: list[Path] = []
        for r in (self.root, self.root.parent):
            if r not in roots:
                roots.append(r)
        cwd = Path.cwd()
        if cwd not in roots:
            roots.append(cwd)

        for r in roots:
            # 1. Local artifacts under this root
            art_dir = r / "artifacts" / "benchmark"
            if art_dir.is_dir():
                run_dirs = [d for d in art_dir.iterdir() if d.is_dir() and (d / "run.json").is_file()]
                if run_dirs:
                    run_dirs.sort(key=lambda d: d.name, reverse=True)
                    latest_dir = run_dirs[0]
                    try:
                        run_data = json.loads((latest_dir / "run.json").read_text(encoding="utf-8"))
                        return latest_dir, "local", run_data
                    except Exception:
                        pass

            # 2. Bundled assets under this root
            ast_dir = r / "assets" / "benchmark"
            if ast_dir.is_dir():
                if (ast_dir / "run.json").is_file():
                    try:
                        run_data = json.loads((ast_dir / "run.json").read_text(encoding="utf-8"))
                        return ast_dir, "bundled", run_data
                    except Exception:
                        pass
                run_dirs = [d for d in ast_dir.iterdir() if d.is_dir() and (d / "run.json").is_file()]
                if run_dirs:
                    run_dirs.sort(key=lambda d: d.name, reverse=True)
                    latest_dir = run_dirs[0]
                    try:
                        run_data = json.loads((latest_dir / "run.json").read_text(encoding="utf-8"))
                        return latest_dir, "bundled", run_data
                    except Exception:
                        pass

        return None

    def benchmark_latest(self) -> dict[str, Any]:
        """Return the latest benchmark run details and image locations."""
        resolved = self._resolve_benchmark_run()
        if not resolved:
            return {"run_id": None, "safety": SAFETY_DECLARATION}

        latest_dir, source, run_data = resolved

        run_id = run_data.get("run_id") or latest_dir.name
        generated_at = run_data.get("generated_at") or run_data.get("run_date")
        tracks = run_data.get("tracks", [])
        systems = run_data.get("systems", [])

        images = [
            {
                "name": p.name,
                "url": f"/api/benchmark/images/{run_id}/{p.name}",
            }
            for p in sorted(latest_dir.glob("*.png"))
        ]

        return {
            "run_id": run_id,
            "source": source,
            "generated_at": generated_at,
            "run_date": run_data.get("run_date"),
            "benchmark_id": run_data.get("benchmark_id", "finance-jev-v1"),
            "mode": run_data.get("mode", "all"),
            "sample_count": run_data.get("sample_count", 240),
            "git_sha": run_data.get("git_sha"),
            "run_hash": run_data.get("run_hash"),
            "tracks": tracks,
            "systems": systems,
            "images": images,
            "image_urls": {
                p.name: f"/api/benchmark/images/{run_id}/{p.name}"
                for p in sorted(latest_dir.glob("*.png"))
            },
            "safety": run_data.get("safety", SAFETY_DECLARATION),
        }

    def benchmark_image(self, run_id: str, filename: str) -> tuple[bytes, str] | None:
        """Read a benchmark run image and return (bytes, mime_type)."""
        import re  # noqa: PLC0415
        if not re.match(r"^[a-zA-Z0-9_.-]+$", filename) or ".." in filename:
            return None
        if not re.match(r"^[a-zA-Z0-9_.-]+$", run_id) or ".." in run_id:
            return None

        target_dir: Path | None = None
        if run_id == "latest":
            resolved = self._resolve_benchmark_run()
            if resolved:
                target_dir = resolved[0]
        else:
            roots: list[Path] = []
            for r in (self.root, self.root.parent):
                if r not in roots:
                    roots.append(r)
            cwd = Path.cwd()
            if cwd not in roots:
                roots.append(cwd)

            # 1. Look in local artifacts for matching run_id directory
            for r in roots:
                candidate = r / "artifacts" / "benchmark" / run_id
                if candidate.is_dir():
                    target_dir = candidate
                    break

            # 2. If not found in artifacts, look in bundled assets
            if target_dir is None:
                for r in roots:
                    c = r / "assets" / "benchmark"
                    if not c.is_dir():
                        continue
                    if (c / "run.json").is_file():
                        try:
                            data = json.loads((c / "run.json").read_text(encoding="utf-8"))
                            if data.get("run_id") == run_id or run_id == "bundled":
                                target_dir = c
                                break
                        except Exception:
                            pass
                    candidate_sub = c / run_id
                    if candidate_sub.is_dir():
                        target_dir = candidate_sub
                        break

        if target_dir is None:
            return None

        target_file = (target_dir / filename).resolve()
        try:
            target_file.relative_to(target_dir.resolve())
        except ValueError:
            return None

        if not target_file.is_file():
            return None

        content_types = {
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".json": "application/json; charset=utf-8",
        }
        mime = content_types.get(target_file.suffix.lower(), "application/octet-stream")
        return target_file.read_bytes(), mime



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

        The comparison is on path segments rather than a prefix string, so the bare
        '/api' counts as an API path too. A plain 'startswith("/api/")' test let
        '/api' through the gate -- it returned 200 without a token while '/api/'
        correctly returned 401. Serving the shell there turned out to be harmless,
        but the rule should not depend on that: the safe reading of "under /api" is
        every spelling of it, and a future handler mounted at '/api' would have been
        exposed by the looser test.
        """
        return not (path == "/api" or path.startswith("/api/"))

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
            if path == "/api/governance":
                self._json(self.service.governance_view())
                return
            if path == "/api/plugins":
                self._json(self.service.plugins())
                return
            if path == "/api/plugins/market":
                self._json(self.service.plugin_market())
                return
            if path == "/api/plugins/catalog":
                self._json(self.service.plugin_catalog())
                return
            if path == "/api/plugins/detail":
                plugin_id = _one(query, "plugin_id") or ""
                if not plugin_id:
                    raise ApiError("plugin_id query parameter is required")
                self._json(self.service.plugin_detail(plugin_id))
                return
            if path == "/api/documents":
                self._json(self.service.documents(query))
                return
            if path == "/api/assistant/sessions":
                self._json(self.service.sessions())
                return
            if path.startswith("/api/assistant/sessions/"):
                rest = path[len("/api/assistant/sessions/"):]
                if rest.endswith("/review/scope"):
                    session_id = urllib.parse.unquote(rest[:-len("/review/scope")].rstrip("/"))
                    self._json(self.service.review_scope(session_id))
                    return
                session_id = urllib.parse.unquote(rest)
                self._json(self.service.session_detail(session_id, query))
                return
            if path == "/api/settings/jev":
                self._json(self.service.jev_connection())
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
            if path == "/api/jev/status":
                self._json(self.service.jev_status())
                return
            if path == "/api/jev/tracks":
                self._json(self.service.jev_tracks())
                return
            if path == "/api/agents":
                self._json(self.service.agents())
                return
            if path == "/api/benchmark/latest":
                self._json(self.service.benchmark_latest())
                return
            if path.startswith("/api/benchmark/images/"):
                rest = path[len("/api/benchmark/images/"):].lstrip("/")
                run_id, _, filename = rest.partition("/")
                res = self.service.benchmark_image(run_id, filename)
                if res is None:
                    self._json(
                        {"status": "error", "error": "image not found", "code": "not_found", "safety": SAFETY_DECLARATION},
                        status=404,
                    )
                    return
                body, content_type = res
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        except ApiError as error:
            # The declaration belongs on every response, refusals included. These
            # two paths omitted it, so a client error was the one reply that did
            # not state the product's safety contract.
            self._json(
                {
                    "status": "error",
                    "error": str(error),
                    "code": error.code,
                    "safety": SAFETY_DECLARATION,
                },
                status=error.status,
            )
            return
        except KeyError as error:
            self._json(
                {
                    "status": "error",
                    "error": f"not found: {error}",
                    "code": "not_found",
                    "safety": SAFETY_DECLARATION,
                },
                status=404,
            )
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
            if path == "/api/governance/profile":
                self._json(self.service.generate_profile(self._read_json()))
                return
            if path.startswith("/api/governance/profile/"):
                profile_id = urllib.parse.unquote(path[len("/api/governance/profile/"):])
                self._json(self.service.edit_profile(profile_id, self._read_json()))
                return
            if path == "/api/governance/challengers":
                self._json(self.service.create_chat_challenger(self._read_json()))
                return
            if path.startswith("/api/governance/strategies/") and path.endswith("/evaluate"):
                strategy_id = urllib.parse.unquote(path[len("/api/governance/strategies/"):-len("/evaluate")])
                self._json(self.service.evaluate_strategy(strategy_id, self._read_json()))
                return
            if path.startswith("/api/governance/strategies/") and path.endswith("/promote"):
                strategy_id = urllib.parse.unquote(path[len("/api/governance/strategies/"):-len("/promote")])
                self._json(self.service.request_promotion(strategy_id))
                return
            if path.startswith("/api/governance/promotions/") and path.endswith("/confirm"):
                promotion_id = urllib.parse.unquote(path[len("/api/governance/promotions/"):-len("/confirm")])
                self._json(self.service.confirm_promotion(promotion_id, self._read_json()))
                return
            if path.startswith("/api/governance/strategies/") and path.endswith("/rollback"):
                strategy_id = urllib.parse.unquote(path[len("/api/governance/strategies/"):-len("/rollback")])
                self._json(self.service.rollback_strategy(strategy_id, self._read_json()))
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
                if action == "cancel":
                    self._json(self.service.cancel_turn(session_id))
                    return
                if action == "resume":
                    self._stream_events(
                        session_id,
                        self.service.resume_turn(session_id, self._read_json()),
                    )
                    return
                if action == "review/scope":
                    self._json(self.service.review_scope(session_id))
                    return
                if action == "review/confirm":
                    self._json(self.service.confirm_review_scope(session_id, self._read_json()))
                    return
                if action == "review/challenger":
                    self._json(self.service.record_challenger(session_id, self._read_json()))
                    return
                if action == "review/package":
                    self._json(self.service.record_review_package(session_id, self._read_json()))
                    return
                if action == "preview":
                    self._json(self.service.session_preview(session_id))
                    return
                if action == "" or action == "update":
                    self._json(self.service.update_session(session_id, self._read_json()))
                    return
            if path == "/api/settings/jev":
                self._json(self.service.update_jev_connection(self._read_json()))
                return
            if path == "/api/settings/jev/test":
                self._read_json()
                self._json(self.service.test_jev_connection())
                return
            if path == "/api/settings":
                self._json(self.service.update_settings(self._read_json()))
                return
            if path == "/api/settings/open-file":
                if not is_loopback(self.client_address[0]):
                    raise ApiError("open-file is only allowed from local loopback", status=403, code="forbidden")
                self._json(self.service.open_config_file())
                return
            if path == "/api/plugins/enable":
                payload = self._read_json()
                plugin_id = str(payload.get("plugin_id") or "")
                if not plugin_id:
                    raise ApiError("plugin_id is required")
                self._json(self.service.plugin_enable(plugin_id))
                return
            if path == "/api/plugins/disable":
                payload = self._read_json()
                plugin_id = str(payload.get("plugin_id") or "")
                if not plugin_id:
                    raise ApiError("plugin_id is required")
                self._json(self.service.plugin_disable(plugin_id))
                return
            if path == "/api/plugins/configure":
                payload = self._read_json()
                plugin_id = str(payload.get("plugin_id") or "")
                if not plugin_id:
                    raise ApiError("plugin_id is required")
                config = payload.get("config") or {}
                if not isinstance(config, dict):
                    raise ApiError("config must be a dictionary")
                self._json(self.service.plugin_configure(plugin_id, config))
                return
            if path.startswith("/api/plugins/market/"):
                rest = path[len("/api/plugins/market/"):]
                plugin_id, _, action = rest.partition("/")
                plugin_id = urllib.parse.unquote(plugin_id)
                payload = self._read_json()
                if action in {"", "install", "configure"}:
                    self._json(self.service.install_market_plugin(plugin_id, payload))
                    return
                if action == "update":
                    self._json(self.service.update_market_plugin(plugin_id, payload))
                    return
                if action in {"enable", "disable"}:
                    self._json(self.service.set_market_plugin_enabled(plugin_id, {"enabled": action == "enable"}))
                    return
            if path == "/api/plugins/reload":
                self._json(self.service.plugin_reload())
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
                if action == "check-models":
                    self._json(self.service.check_models({**self._read_json(), "provider_id": provider_id}))
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
            if path.startswith("/api/rules/") and path.endswith("/promote"):
                # The one rule-library write. It sits behind the same access
                # check as every other route, and on a shared host the shipped
                # proxy refuses the whole workbench surface, so promotion is
                # reachable only from the local single-user workbench.
                rule_id = urllib.parse.unquote(path[len("/api/rules/"):-len("/promote")])
                self._json(self.service.promote_rule(rule_id, self._read_json()))
                return
            if path == "/api/agents/apply":
                self._json(self.service.agents_apply(self._read_json()))
                return
            if path == "/api/agents/disable":
                self._json(self.service.agents_disable(self._read_json()))
                return
            if path == "/api/agents/restore":
                self._json(self.service.agents_restore(self._read_json()))
                return
        except ApiError as error:
            self._json(
                {
                    "status": "error",
                    "error": str(error),
                    "code": error.code,
                    "safety": SAFETY_DECLARATION,
                },
                status=error.status,
            )
            return
        except KeyError as error:
            self._json(
                {
                    "status": "error",
                    "error": f"not found: {error}",
                    "code": "not_found",
                    "safety": SAFETY_DECLARATION,
                },
                status=404,
            )
            return

        self._json(
            {
                "status": "error",
                "error": f"unknown endpoint {path}",
                "safety": SAFETY_DECLARATION,
            },
            status=404,
        )

    def _stream_turn(self, session_id: str, payload: dict[str, Any]) -> None:
        events = self.service.stream_turn(session_id, payload)
        self._stream_events(session_id, events)

    def _stream_events(self, session_id: str, events: Any) -> None:
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
    # The shared local state root, not a third copy of it: a caller that omits
    # root must land on the same account the other front door uses.
    root: str | Path = LOCAL_STATE_DIR,
    host: str = "127.0.0.1",
    port: int = 8787,
    asset_dir: str | Path | None = None,
    open_browser: bool = True,
    access_token: str | None = None,
    workspace_db: str | None = None,
    trader_service: Any = None,
    trader_store: Any = None,
    dsh_bridge: Any = None,
    ready: Callable[[str], None] | None = None,
) -> None:
    if trader_service is not None and trader_store is not None:
        raise ValueError("pass either trader_service or trader_store, not both")
    owned_trader_store = None
    if trader_service is None and trader_store is not None:
        from smartmoney_cub_harness.trader.api import TraderService

        trader_service = TraderService(trader_store)
        owned_trader_store = trader_store

    service = WorkbenchService(
        root, workspace_db=workspace_db, trader_service=trader_service, dsh_bridge=dsh_bridge
    )
    if trader_service is None and service.trader_service is not None:
        trader_service = service.trader_service
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
