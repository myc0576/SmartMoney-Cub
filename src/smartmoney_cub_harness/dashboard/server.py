from __future__ import annotations

import json
import threading
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import mimetypes
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.challenger import generate_challenger_review, get_default_rules_matrix
from smartmoney_cub_harness import __version__
from smartmoney_cub_harness.fills import build_fill_ledger, ledger_to_analysis_trades
from smartmoney_cub_harness.plugin_cli import (
    plugin_catalog,
    plugin_disable,
    plugin_enable,
    plugin_install,
    plugin_list,
)
from smartmoney_cub_harness.plugins.profiles import BUILTIN_PROFILES, get_profile
from smartmoney_cub_harness.regime import REGIME_PHASES, get_regime_info
from smartmoney_cub_harness.registry import promotion_blockers
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.share_pack import build_share_pack
from smartmoney_cub_harness.trade_parser import (
    DEMO_TRADE_CASES,
    generate_portfolio_health_report,
    parse_csv_content,
)
from smartmoney_cub_harness.workspace_cli import workspace_list_cases, workspace_summary

TEMPLATES_DIR = Path(__file__).parent / "templates"

DEMO_DATA_ORIGIN = "demo_fixture"
USER_CSV_DATA_ORIGIN = "user_csv"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class DashboardState:
    def __init__(self) -> None:
        self.active_regime = "生长"
        self.active_profile = "default-offline"
        self.trades = list(DEMO_TRADE_CASES)
        self.rules = get_default_rules_matrix()
        self.data_origin = DEMO_DATA_ORIGIN
        self.ledger: dict[str, Any] | None = None
        self.needs_review: list[dict[str, Any]] = []
        self.plugin_dirs: list[str] = [
            str(Path(__file__).resolve().parents[3] / "examples" / "toy_plugin")
        ]
        self.state_db: str | None = None
        self._refresh()

    def _refresh(self) -> None:
        self.report = generate_portfolio_health_report(self.trades, self.active_regime)
        # Every number rendered by the dashboard declares whether it came from the
        # bundled demo fixture or from a user CSV whose ledger may be ambiguous.
        self.report["data_origin"] = self.data_origin
        self.report["ledger_status"] = self.ledger.get("status") if self.ledger else DEMO_DATA_ORIGIN
        self.report["needs_review"] = list(self.needs_review)
        self.challenger_reviews = [
            generate_challenger_review(t) for t in self.report["analyzed_trades"]
        ]

    def set_regime(self, regime_name: str) -> None:
        self.active_regime = regime_name
        self._refresh()

    def set_profile(self, profile_name: str) -> None:
        if profile_name in BUILTIN_PROFILES:
            self.active_profile = profile_name

    def load_trades_from_csv(self, csv_text: str) -> int:
        records = parse_csv_content(csv_text)
        if not records:
            self.ledger = None
            self.trades = []
            self.data_origin = USER_CSV_DATA_ORIGIN
            self.needs_review = [
                {
                    "code": "empty_csv",
                    "severity": "error",
                    "symbol": "",
                    "fill_id": "",
                    "detail": "no parsable fill rows were found in the uploaded CSV",
                }
            ]
            self._refresh()
            return 0

        # Replace the previous naive FIFO pairing. Ambiguous rows are surfaced as
        # needs_review issues instead of being silently turned into trades.
        # Language and symbol shape are not sufficient market evidence. A
        # caller's explicit market column controls market-specific policies.
        ledger = build_fill_ledger(records, market="UNKNOWN", allow_shorts=True)
        self.ledger = ledger
        self.data_origin = USER_CSV_DATA_ORIGIN
        self.needs_review = [issue for issue in ledger["issues"] if issue["severity"] == "error"]
        self.trades = ledger_to_analysis_trades(ledger)
        self._refresh()
        return len(self.trades)

    def reset_demo(self) -> None:
        self.trades = list(DEMO_TRADE_CASES)
        self.rules = get_default_rules_matrix()
        self.data_origin = DEMO_DATA_ORIGIN
        self.ledger = None
        self.needs_review = []
        self._refresh()

    def add_challenger_rule(self, rule_data: dict[str, Any]) -> None:
        self.rules.setdefault("challengers", [])
        # 查重
        rule_id = rule_data.get("rule_id", f"CHALL-{len(self.rules['challengers'])+101}")
        for r in self.rules["challengers"]:
            if r.get("rule_id") == rule_id:
                return
        rule_data["rule_id"] = rule_id
        rule_data.setdefault("tested_samples", 1)
        rule_data.setdefault("target_samples", 20)
        self.rules["challengers"].append(rule_data)


    def request_promotion(self, rule_id: str, *, confirm: bool = False, note: str = "") -> dict[str, Any]:
        """Evaluate a challenger promotion request.

        Without an explicit confirmation plus a written note, this only returns a
        recommendation. Champion mutation never happens on a dashboard click alone.
        """
        challengers = self.rules.get("challengers", [])
        target = next((rule for rule in challengers if rule.get("rule_id") == rule_id), None)
        if target is None:
            return {
                "status": "not_found",
                "rule_id": rule_id,
                "confirmation_required": False,
                "champion_mutated": False,
                "core_rules_mutated": False,
                "blockers": ["unknown_challenger_rule"],
                "rules": self.rules,
                "safety": SAFETY_DECLARATION,
            }

        metrics = {
            "sample_count": int(target.get("tested_samples") or 0),
            "false_alert_rate": float(target.get("false_alert_rate") or 0.0),
            "missed_opportunity_rate": float(target.get("missed_opportunity_rate") or 0.0),
            "future_leakage_count": int(target.get("future_leakage_count") or 0),
            "risk_contract_violation_rate": float(target.get("risk_contract_violation_rate") or 0.0),
        }
        blockers = promotion_blockers(metrics)
        promotion_requested = bool(confirm)
        if promotion_requested and not note.strip():
            blockers.append("explicit_confirmation_note_required")

        if blockers or not promotion_requested:
            return {
                "status": "recommendation",
                "rule_id": rule_id,
                "confirmation_required": True,
                "champion_mutated": False,
                "core_rules_mutated": False,
                "blockers": blockers,
                "metrics": metrics,
                "rules": self.rules,
                "safety": SAFETY_DECLARATION,
            }

        challengers.remove(target)
        promoted = dict(target)
        promoted["status"] = "champion"
        promoted["promoted_at"] = _now_iso()
        promoted["promotion_note"] = note.strip()
        promoted["sample_count"] = metrics["sample_count"]
        promoted["evidence_basis"] = "explicit_user_confirmation"
        # No fabricated win-rate or violation-rate numbers are attached on promotion.
        self.rules.setdefault("champions", []).append(promoted)
        return {
            "status": "promoted",
            "rule_id": rule_id,
            "confirmation_required": False,
            "champion_mutated": True,
            "core_rules_mutated": True,
            "blockers": [],
            "metrics": metrics,
            "rules": self.rules,
            "safety": SAFETY_DECLARATION,
        }


GLOBAL_STATE = DashboardState()


class DashboardHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # 静默处理避免过多请求刷屏
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _send_html(self, html_text: str, status: int = 200) -> None:
        payload = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        url_parts = urllib.parse.urlparse(self.path)
        path = url_parts.path
        query = urllib.parse.parse_qs(url_parts.query)

        # 静态资源请求 (/assets/*.js, *.css, *.svg 等)
        if path.startswith("/assets/"):
            asset_path = TEMPLATES_DIR / path.lstrip("/")
            if asset_path.exists() and asset_path.is_file():
                content_type, _ = mimetypes.guess_type(str(asset_path))
                content_bytes = asset_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type or "application/octet-stream")
                self.send_header("Content-Length", str(len(content_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content_bytes)
                return

        if path in {"/", "/index.html"}:
            html_file = TEMPLATES_DIR / "index.html"
            if html_file.exists():
                self._send_html(html_file.read_text(encoding="utf-8"))
            else:
                self._send_html("<h1>Dashboard template not found</h1>", status=404)
            return

        if path == "/api/status":
            self._send_json({
                "status": "ok",
                "app": "smartmoney-cub-dashboard",
                "version": __version__,
                "safety": SAFETY_DECLARATION,
                "active_regime": GLOBAL_STATE.active_regime,
                "active_profile": GLOBAL_STATE.active_profile,
                "data_origin": GLOBAL_STATE.data_origin,
            })
            return

        if path == "/api/data":
            self._send_json({
                "safety": SAFETY_DECLARATION,
                "data_origin": GLOBAL_STATE.data_origin,
                "needs_review": GLOBAL_STATE.needs_review,
                "active_regime": GLOBAL_STATE.active_regime,
                "active_profile": GLOBAL_STATE.active_profile,
                "regime_info": get_regime_info(GLOBAL_STATE.active_regime),
                "regime_phases": REGIME_PHASES,
                "report": GLOBAL_STATE.report,
                "challenger_reviews": GLOBAL_STATE.challenger_reviews,
                "rules": GLOBAL_STATE.rules,
            })
            return

        if path == "/api/regime":
            self._send_json({
                "active": get_regime_info(GLOBAL_STATE.active_regime),
                "all_phases": REGIME_PHASES,
                "safety": SAFETY_DECLARATION,
            })
            return

        if path == "/api/workspace/summary":
            self._send_json(workspace_summary())
            return

        if path == "/api/workspace/cases":
            action = query.get("action", [None])[0]
            symbol = query.get("symbol", [None])[0]
            regime = query.get("regime", [None])[0]
            self._send_json(workspace_list_cases(action=action, symbol=symbol, regime=regime))
            return

        if path == "/api/plugins/list":
            res = plugin_list(
                profile_name=GLOBAL_STATE.active_profile,
                plugin_dirs=GLOBAL_STATE.plugin_dirs,
                state_db=GLOBAL_STATE.state_db,
            )
            self._send_json(res)
            return

        if path == "/api/plugins/catalog":
            self._send_json(plugin_catalog())
            return

        if path == "/api/profiles":
            profiles_data = {
                name: p.to_dict() for name, p in BUILTIN_PROFILES.items()
            }
            self._send_json({
                "status": "ok",
                "active_profile": GLOBAL_STATE.active_profile,
                "profiles": profiles_data,
                "safety": SAFETY_DECLARATION,
            })
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        url_parts = urllib.parse.urlparse(self.path)
        path = url_parts.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""

        if path == "/api/set_regime":
            try:
                data = json.loads(body)
                regime = str(data.get("regime", "生长")).strip()
                GLOBAL_STATE.set_regime(regime)
                self._send_json({
                    "status": "ok",
                    "active_regime": GLOBAL_STATE.active_regime,
                "active_profile": GLOBAL_STATE.active_profile,
                    "report": GLOBAL_STATE.report,
                })
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        if path == "/api/upload_csv":
            try:
                # 可能是直接的CSV文本或JSON包
                if body.startswith("{"):
                    data = json.loads(body)
                    csv_content = data.get("content", "")
                else:
                    csv_content = body
                count = GLOBAL_STATE.load_trades_from_csv(csv_content)
                self._send_json({
                    "status": "ok",
                    "loaded_trades_count": count,
                    "report": GLOBAL_STATE.report,
                    "challenger_reviews": GLOBAL_STATE.challenger_reviews,
                })
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        if path == "/api/reset_demo":
            GLOBAL_STATE.reset_demo()
            self._send_json({
                "status": "ok",
                "message": "已恢复预设实战与反思交割单案例",
                "report": GLOBAL_STATE.report,
                "challenger_reviews": GLOBAL_STATE.challenger_reviews,
                "rules": GLOBAL_STATE.rules,
            })
            return

        if path == "/api/add_rule":
            try:
                data = json.loads(body)
                GLOBAL_STATE.add_challenger_rule(data)
                self._send_json({"status": "ok", "rules": GLOBAL_STATE.rules})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        if path in {"/api/promote_rule", "/api/request_promotion"}:
            try:
                data = json.loads(body)
                rule_id = str(data.get("rule_id", ""))
                # A dashboard click can only ever request a promotion. Champion
                # mutation additionally requires confirm=true plus a written note
                # and passing sample-size gates.
                self._send_json(
                    GLOBAL_STATE.request_promotion(
                        rule_id,
                        confirm=bool(data.get("confirm", False)),
                        note=str(data.get("note", "")),
                    )
                )
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        if path == "/api/plugins/toggle":
            try:
                data = json.loads(body)
                plugin_id = str(data.get("plugin_id", "")).strip()
                enabled = bool(data.get("enabled", True))
                if enabled:
                    res = plugin_enable(
                        plugin_id,
                        profile_name=GLOBAL_STATE.active_profile,
                        plugin_dirs=GLOBAL_STATE.plugin_dirs,
                        state_db=GLOBAL_STATE.state_db,
                    )
                else:
                    res = plugin_disable(
                        plugin_id,
                        profile_name=GLOBAL_STATE.active_profile,
                        state_db=GLOBAL_STATE.state_db,
                    )
                self._send_json(res)
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        if path == "/api/plugins/install":
            try:
                data = json.loads(body)
                source = str(data.get("source", "")).strip()
                res = plugin_install(
                    source,
                    profile_name=GLOBAL_STATE.active_profile,
                    state_db=GLOBAL_STATE.state_db,
                )
                self._send_json(res, status=200 if res.get("status") == "ok" else 400)
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        if path == "/api/profiles/switch":
            try:
                data = json.loads(body)
                profile_name = str(data.get("profile", "default-offline")).strip()
                GLOBAL_STATE.set_profile(profile_name)
                self._send_json({
                    "status": "ok",
                    "active_profile": GLOBAL_STATE.active_profile,
                    "profile": get_profile(GLOBAL_STATE.active_profile).to_dict(),
                    "safety": SAFETY_DECLARATION,
                })
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        if path == "/api/share_pack/generate":
            try:
                data = json.loads(body) if body.strip() else {}
                title = str(data.get("title", "SmartMoney-Cub 复盘分享包")).strip()
                policy = data.get("policy")
                pack = build_share_pack(
                    report=GLOBAL_STATE.report,
                    ledger=GLOBAL_STATE.ledger,
                    challenger_reviews=GLOBAL_STATE.challenger_reviews,
                    rules=GLOBAL_STATE.rules,
                    title=title,
                    policy=policy,
                )
                self._send_json({
                    "status": "ok",
                    "title": title,
                    "html": pack["html"],
                    "audit": pack["audit"],
                    "safety": SAFETY_DECLARATION,
                })
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, status=400)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")


def start_dashboard_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """启动本地 Web 交易复盘与纪律工作台服务"""
    server_address = (host, port)
    server = HTTPServer(server_address, DashboardHTTPHandler)
    url = f"http://{host}:{port}"
    print("[SmartMoney-Cub Dashboard] 启动成功！")
    print(f"-> 本地访问地址: {url}")
    print(f"-> 安全准则: {SAFETY_DECLARATION}")
    print("-> 按 Ctrl+C 停止服务\n")

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SmartMoney-Cub Dashboard] 服务已停止。")
        server.server_close()


if __name__ == "__main__":
    start_dashboard_server()
