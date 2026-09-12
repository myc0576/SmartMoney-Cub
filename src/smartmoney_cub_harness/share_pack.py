from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartmoney_cub_harness.safety import redact
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

SHARE_PACK_SCHEMA = "smartmoney_cub_share_pack.v1"
SHARE_AUDIT_SCHEMA = "smartmoney_cub_share_audit.v1"

SHARE_PACK_HTML_NAME = "share_pack.html"
SHARE_AUDIT_NAME = "share_audit.json"
SHARE_SEAL_NAME = "share_pack.sha256"

# Defaults chosen so a shared pack cannot leak identity, while still being useful
# for discussion. Codes, names, and amounts are reduced, never uploaded.
DEFAULT_REDACTION_POLICY: dict[str, str] = {
    "symbol": "hash",
    "name": "replace",
    "amount": "coarsen",
    "time": "date_only",
    "note": "redact_paths_and_identifiers",
}

AMOUNT_COARSEN_STEP = 1000.0

IDENTIFIER_PATTERNS = (
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("phone", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("windows_path", re.compile(r"(?i)\b[A-Z]:\\[^\s\"'<>|]+")),
    ("home_path", re.compile(r"(?i)/(?:Users|home)/[^\s\"'<>|]+")),
    ("secret", re.compile(r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{8,})\b")),
    ("cookie", re.compile(r"(?i)\bcookie\s*=")),
    ("token", re.compile(r"(?i)\b(?:token|api_key|apikey|password|passwd|secret|session)\s*=")),
    ("account", re.compile(r"(?i)\baccount(?:[_\s-]?id)?\s*[:=]")),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _coarsen(value: Any, step: float = AMOUNT_COARSEN_STEP) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number / step) * step


def _hash_identifier(value: Any, salt: str = "smartmoney-cub-share") -> str:
    text = f"{salt}:{value}"
    return "id-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def _date_only(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Keep only the calendar date so intraday timing is not disclosed.
    match = re.match(r"^(d{4}-d{2}-d{2})", text)
    if match:
        return match.group(1)
    return None


def _scan_identifiers(text: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for label, pattern in IDENTIFIER_PATTERNS:
        for match in pattern.finditer(text):
            hits.append({"kind": label, "match": match.group(0)[:80]})
    return hits


def build_share_pack(
    *,
    report: dict[str, Any],
    ledger: dict[str, Any] | None = None,
    challenger_reviews: list[dict[str, Any]] | None = None,
    rules: dict[str, Any] | None = None,
    title: str = "SmartMoney-Cub Review Pack",
    policy: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an offline, privacy-reduced HTML review pack.

    The result is returned in memory and never uploaded. Symbols, names, amounts,
    and timestamps are reduced according to the policy so the artifact can be
    shared for discussion without disclosing a real trading account.
    """
    active_policy = dict(DEFAULT_REDACTION_POLICY)
    if policy:
        active_policy.update(policy)

    redacted_trades: list[dict[str, Any]] = []
    for trade in report.get("analyzed_trades", []):
        entry: dict[str, Any] = {}
        for key, value in trade.items():
            if key in ("symbol", "code"):
                entry[key] = (
                    _hash_identifier(value)
                    if active_policy["symbol"] == "hash"
                    else "REDACTED"
                )
            elif key in ("name",):
                entry[key] = (
                    _hash_identifier(value)
                    if active_policy["name"] == "hash"
                    else "REDACTED"
                )
            elif key in ("pnl_amount", "amount", "net_pnl"):
                entry[key] = _coarsen(value)
            elif key in ("entry_time", "exit_time"):
                entry[key] = _date_only(value) if active_policy["time"] == "date_only" else value
            else:
                entry[key] = value
        redacted_trades.append(entry)

    redacted_report = {
        key: value for key, value in report.items() if key != "analyzed_trades"
    }
    redacted_report["analyzed_trades"] = redacted_trades

    html = _render_html(
        title=title,
        report=redacted_report,
        ledger=_reduce_ledger(ledger, active_policy) if ledger else None,
        challenger_reviews=challenger_reviews or [],
        rules=rules or {},
        policy=active_policy,
    )

    audit = audit_share_pack(html)
    return {
        "schema": SHARE_PACK_SCHEMA,
        "title": title,
        "generated_at": _now_iso(),
        "policy": active_policy,
        "html": html,
        "audit": audit,
        "upload": False,
        "network_required": False,
        "safety": SAFETY_DECLARATION,
    }


def _reduce_ledger(ledger: dict[str, Any], policy: dict[str, str]) -> dict[str, Any]:
    reduced: dict[str, Any] = {
        "status": ledger.get("status"),
        "counts": ledger.get("counts"),
        "issues": [
            {**issue, "symbol": _hash_identifier(issue.get("symbol")) if issue.get("symbol") else ""}
            for issue in ledger.get("issues", [])
        ],
        "round_trips": [
            {
                **{key: value for key, value in trip.items() if key not in ("symbol", "name", "net_pnl")},
                "symbol": _hash_identifier(trip.get("symbol")),
                "name": "REDACTED",
                "net_pnl": _coarsen(trip.get("net_pnl")),
            }
            for trip in ledger.get("round_trips", [])
        ],
    }
    return reduced


def audit_share_pack(content: str) -> dict[str, Any]:
    """Check a share pack for identifiers, paths, and credentials before sharing."""
    hits = _scan_identifiers(content or "")
    return {
        "schema": SHARE_AUDIT_SCHEMA,
        "status": "ok" if not hits else "needs_review",
        "identifier_hits": hits[:50],
        "hit_count": len(hits),
        "has_safety_declaration": SAFETY_DECLARATION in (content or ""),
        "upload": False,
        "checked_at": _now_iso(),
        "safety": SAFETY_DECLARATION,
    }


def _render_html(
    *,
    title: str,
    report: dict[str, Any],
    ledger: dict[str, Any] | None,
    challenger_reviews: list[dict[str, Any]],
    rules: dict[str, Any],
    policy: dict[str, str],
) -> str:
    summary = report.get("summary") or {}
    trades = report.get("analyzed_trades") or []
    data_origin = report.get("data_origin") or "user_csv"

    def esc(value: Any) -> str:
        text = str(value)
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    trade_rows = "\n".join(
        "<tr>"
        f"<td>{esc(trade.get('symbol'))}</td>"
        f"<td>{esc(trade.get('name'))}</td>"
        f"<td>{esc(trade.get('regime'))}</td>"
        f"<td>{esc(trade.get('return_pct'))}%</td>"
        f"<td>{esc(trade.get('discipline_score'))}</td>"
        f"<td>{esc(trade.get('health_grade'))}</td>"
        f"<td>{esc(trade.get('entry_time'))}</td>"
        "</tr>"
        for trade in trades
    )

    issue_items = "\n".join(
        f"<li><code>{esc(issue.get('code'))}</code> {esc(issue.get('detail'))}</li>"
        for issue in (ledger or {}).get("issues", [])
    )

    challenger_items = "\n".join(
        "<div class='card'>"
        f"<h4>{esc(review.get('verdict'))}</h4>"
        "<ul>"
        + "".join(f"<li>{esc(question)}</li>" for question in review.get("cross_examination_questions", []))
        + "</ul></div>"
        for review in challenger_reviews
    )

    champion_items = "\n".join(
        f"<li><strong>{esc(rule.get('rule_id'))}</strong> {esc(rule.get('title'))}</li>"
        for rule in (rules.get("champions") or [])
    )

    origin_note = (
        "本包由演示 (DEMO) 数据生成，仅用于展示流程，不代表任何真实交易。"
        if data_origin == "demo_fixture"
        else "本包由本地复盘数据生成，标识与金额已按分享策略降精度。"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{esc(title)}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; padding:32px; background:#0b1220; color:#e2e8f0;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif; }}
  h1 {{ font-size:22px; margin:0 0 4px; }}
  h2 {{ font-size:15px; margin:28px 0 10px; color:#94a3b8; text-transform:uppercase; letter-spacing:.08em; }}
  .safety {{ display:inline-block; margin:10px 0 0; padding:6px 10px; border-radius:8px;
             background:#052e2b; border:1px solid #10b98155; color:#34d399; font-family:ui-monospace,monospace; font-size:12px; }}
  .note {{ margin-top:8px; font-size:12px; color:#94a3b8; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }}
  .kpi {{ background:#111c33; border:1px solid #1e293b; border-radius:12px; padding:14px; }}
  .kpi .label {{ font-size:12px; color:#94a3b8; }}
  .kpi .value {{ font-size:20px; font-weight:700; margin-top:6px; font-family:ui-monospace,monospace; }}
  table {{ width:100%; border-collapse:collapse; background:#111c33; border-radius:12px; overflow:hidden; font-size:13px; }}
  th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #1e293b; }}
  th {{ background:#16233d; color:#94a3b8; font-weight:600; }}
  .card {{ background:#111c33; border:1px solid #1e293b; border-radius:12px; padding:14px; margin-bottom:10px; }}
  ul {{ margin:6px 0 0 18px; padding:0; }}
  code {{ background:#1e293b; padding:1px 6px; border-radius:5px; font-size:12px; }}
  footer {{ margin-top:32px; font-size:12px; color:#64748b; }}
</style>
</head>
<body>
  <h1>{esc(title)}</h1>
  <div class="safety">{SAFETY_DECLARATION}</div>
  <p class="note">{esc(origin_note)}</p>
  <p class="note">分享策略：证券代码 {esc(policy.get('symbol'))} / 名称 {esc(policy.get('name'))} / 金额 {esc(policy.get('amount'))} / 时间 {esc(policy.get('time'))}。本文件为静态离线产物，系统不会自动上传。</p>

  <h2>复盘概览</h2>
  <div class="grid">
    <div class="kpi"><div class="label">交易笔数</div><div class="value">{esc(summary.get('total_trades', 0))}</div></div>
    <div class="kpi"><div class="label">胜率</div><div class="value">{esc(summary.get('win_rate', 0))}%</div></div>
    <div class="kpi"><div class="label">纪律评分</div><div class="value">{esc(summary.get('avg_discipline_score', 0))}</div></div>
    <div class="kpi"><div class="label">违规次数</div><div class="value">{esc(summary.get('total_violations', 0))}</div></div>
  </div>

  <h2>交易明细（已降精度）</h2>
  <table>
    <thead><tr><th>标的</th><th>名称</th><th>周期</th><th>收益</th><th>纪律</th><th>评级</th><th>日期</th></tr></thead>
    <tbody>{trade_rows or '<tr><td colspan="7">无已平仓交易</td></tr>'}</tbody>
  </table>

  <h2>数据质量与待核对项</h2>
  <div class="card">
    <ul>{issue_items or '<li>无阻断项</li>'}</ul>
  </div>

  <h2>反方审查</h2>
  {challenger_items or '<div class="card">无反方审查记录</div>'}

  <h2>当前 Champion 规则</h2>
  <div class="card"><ul>{champion_items or '<li>暂无已晋级规则</li>'}</ul></div>

  <footer>
    本包为只读复盘证据，不构成任何投资建议，也不包含下单、撤单或账户操作能力。
    生成方式：本地静态导出，未经自动上传。
  </footer>
</body>
</html>
"""


def write_share_pack(pack: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    """Persist a share pack locally and seal it with a checksum."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    html_bytes = pack["html"].encode("utf-8")
    (root / SHARE_PACK_HTML_NAME).write_bytes(html_bytes)
    (root / SHARE_AUDIT_NAME).write_text(
        json.dumps(redact(pack["audit"]), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(html_bytes).hexdigest()
    (root / SHARE_SEAL_NAME).write_text(f"{digest}  {SHARE_PACK_HTML_NAME}\n", encoding="utf-8")
    return {
        "status": "ok",
        "output_dir": str(root),
        "html_path": str(root / SHARE_PACK_HTML_NAME),
        "audit_path": str(root / SHARE_AUDIT_NAME),
        "seal_path": str(root / SHARE_SEAL_NAME),
        "sha256": digest,
        "audit": pack["audit"],
        "upload": False,
        "safety": SAFETY_DECLARATION,
    }
