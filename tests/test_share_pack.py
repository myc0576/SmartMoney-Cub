from __future__ import annotations

import json
from pathlib import Path

from smartmoney_cub_harness.share_cli import build_share_pack_from_source
from smartmoney_cub_harness.share_pack import (
    DEFAULT_REDACTION_POLICY,
    audit_share_pack,
    build_share_pack,
    write_share_pack,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trade_parser import DEMO_TRADE_CASES, generate_portfolio_health_report


def _report(origin: str = "user_csv") -> dict:
    report = generate_portfolio_health_report(DEMO_TRADE_CASES, "生长")
    report["data_origin"] = origin
    return report


def test_share_pack_hashes_symbols_and_names() -> None:
    pack = build_share_pack(report=_report(), title="Test Pack")
    html = pack["html"]
    assert pack["safety"] == SAFETY_DECLARATION
    assert pack["upload"] is False
    assert pack["network_required"] is False
    assert SAFETY_DECLARATION in html
    # No raw security code or name may survive into the shareable artifact.
    for trade in _report()["analyzed_trades"]:
        assert str(trade["symbol"]) not in html
        assert str(trade["name"]) not in html
    assert pack["audit"]["status"] == "ok"


def test_share_pack_is_offline_and_declares_default_policy() -> None:
    pack = build_share_pack(report=_report())
    assert pack["policy"]["symbol"] == DEFAULT_REDACTION_POLICY["symbol"]
    assert pack["policy"]["amount"] == "coarsen"
    assert pack["policy"]["time"] == "date_only"


def test_share_pack_labels_demo_data() -> None:
    demo = build_share_pack(report=_report("demo_fixture"))
    assert "DEMO" in demo["html"]
    real = build_share_pack(report=_report("user_csv"))
    assert "DEMO" not in real["html"]


def test_share_pack_audit_detects_identifiers_paths_and_secrets() -> None:
    dirty = (
        "contact a@b.com or 13800138000 token=abc123 "
        # A synthetic home path. It deliberately does not name a real account:
        # this file is published, and a fixture is not a reason to record
        # somebody's username in it.
        "path /Users/example/private C:\\Users\\me\\notes account_id: 998877"
    )
    audit = audit_share_pack(dirty)
    assert audit["status"] == "needs_review"
    kinds = {hit["kind"] for hit in audit["identifier_hits"]}
    assert {"email", "phone", "token", "home_path", "windows_path", "account"} <= kinds
    assert audit["upload"] is False


def test_share_pack_audit_flags_missing_safety_declaration() -> None:
    audit = audit_share_pack("plain content with no declaration")
    assert audit["has_safety_declaration"] is False


def test_write_share_pack_creates_html_audit_and_seal(tmp_path: Path) -> None:
    pack = build_share_pack(report=_report())
    result = write_share_pack(pack, tmp_path / "pack")
    assert result["status"] == "ok"
    assert result["upload"] is False
    html_path = Path(result["html_path"])
    audit_path = Path(result["audit_path"])
    seal_path = Path(result["seal_path"])
    assert html_path.exists()
    assert audit_path.exists()
    assert seal_path.exists()
    assert result["sha256"] in seal_path.read_text(encoding="utf-8")
    assert SAFETY_DECLARATION in html_path.read_text(encoding="utf-8")
    stored_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert stored_audit["safety"] == SAFETY_DECLARATION


def test_share_pack_from_demo_source_is_labelled(tmp_path: Path) -> None:
    result = build_share_pack_from_source(output_dir=str(tmp_path / "pack"), write=True)
    assert result["status"] == "ok"
    assert result["data_origin"] == "demo_fixture"
    assert result["ledger_status"] is None
    assert result["audit"]["status"] == "ok"
    html = (tmp_path / "pack" / "share_pack.html").read_text(encoding="utf-8")
    assert "DEMO" in html


def test_share_pack_from_csv_uses_ledger_and_stays_private(tmp_path: Path) -> None:
    csv_path = tmp_path / "fills.csv"
    rows = [
        "成交日期,成交时间,证券代码,证券名称,操作,成交均价,成交数量",
        "2026-09-01,09:40:00,600111,北方稀土,买入,10.00,1000",
        "2026-09-02,14:00:00,600111,北方稀土,卖出,11.00,1000",
    ]
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    result = build_share_pack_from_source(
        csv_path=str(csv_path), output_dir=str(tmp_path / "pack"), write=True
    )
    assert result["data_origin"] == "user_csv"
    assert result["ledger_status"] == "ok"
    assert result["upload"] is False
    html = (tmp_path / "pack" / "share_pack.html").read_text(encoding="utf-8")
    assert "600111" not in html
    assert "北方稀土" not in html


def test_share_pack_flags_ambiguous_csv_as_needs_review(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    rows = [
        "成交日期,成交时间,证券代码,证券名称,操作,成交均价,成交数量",
        "2026-09-02,10:00:00,600519,贵州茅台,卖出,1500.00,100",
    ]
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    result = build_share_pack_from_source(
        csv_path=str(csv_path), output_dir=str(tmp_path / "pack"), write=True
    )
    assert result["ledger_status"] == "needs_review"
    html = (tmp_path / "pack" / "share_pack.html").read_text(encoding="utf-8")
    assert "sell_without_position" in html
