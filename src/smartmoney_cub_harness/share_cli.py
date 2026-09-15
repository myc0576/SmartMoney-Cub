from __future__ import annotations

from pathlib import Path
from typing import Any

from smartmoney_cub_harness.challenger import generate_challenger_review, get_default_rules_matrix
from smartmoney_cub_harness.fills import build_fill_ledger, ledger_to_analysis_trades
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.share_pack import build_share_pack, write_share_pack
from smartmoney_cub_harness.trade_parser import (
    DEMO_TRADE_CASES,
    generate_portfolio_health_report,
    parse_csv_content,
)


def build_share_pack_from_source(
    *,
    csv_path: str | None = None,
    output_dir: str | None = None,
    regime: str = "生长",
    title: str = "SmartMoney-Cub Review Pack",
    write: bool = False,
) -> dict[str, Any]:
    """Build (and optionally write) a privacy-reduced share pack.

    With no CSV the bundled toy case is used and clearly labelled as demo data, so
    demo numbers can never be mistaken for real performance.
    """
    if csv_path:
        content = Path(csv_path).read_text(encoding="utf-8")
        records = parse_csv_content(content)
        ledger = build_fill_ledger(records)
        trades = ledger_to_analysis_trades(ledger)
        data_origin = "user_csv"
    else:
        ledger = None
        trades = list(DEMO_TRADE_CASES)
        data_origin = "demo_fixture"

    report = generate_portfolio_health_report(trades, regime)
    report["data_origin"] = data_origin
    if ledger is not None:
        report["ledger_status"] = ledger["status"]
        report["needs_review"] = [i for i in ledger["issues"] if i["severity"] == "error"]

    reviews = [generate_challenger_review(trade) for trade in report.get("analyzed_trades", [])]
    pack = build_share_pack(
        report=report,
        ledger=ledger,
        challenger_reviews=reviews,
        rules=get_default_rules_matrix(),
        title=title,
    )
    result: dict[str, Any] = {
        "status": "ok",
        "data_origin": data_origin,
        "ledger_status": ledger["status"] if ledger else None,
        "audit": pack["audit"],
        "upload": False,
        "safety": SAFETY_DECLARATION,
    }
    if write:
        if not output_dir:
            raise ValueError("output_dir is required when write is enabled")
        result.update(write_share_pack(pack, output_dir))
    return result
