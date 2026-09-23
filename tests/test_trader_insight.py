"""Tests for the trader insight module (mistake clusters and edges).

All fixtures use offline toy data with invented symbols, timestamps, and prices.
No real trading records, no network access, and absolute execution ban declaration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.api.service import TraderService, build_tenant_ledger
from smartmoney_cub_harness.trader.auth import AuthContext
from smartmoney_cub_harness.trader.insight import (
    CLUSTER_KINDS,
    EDGE_DIMENSIONS,
    cluster_mistakes,
    extract_edges,
)
from smartmoney_cub_harness.trader.storage import open_store

REPO_ROOT = Path(__file__).resolve().parents[1]


def _toy_trade(trade_id: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "trade_id": trade_id,
        "account_id": "ACC-TOY",
        "symbol": "TOY-A",
        "market": "CN-A",
        "name": "Toy Stock A",
        "side": "BUY",
        "trade_date": "2026-08-03",
        "trade_time": "09:40:00",
        "price": 10.0,
        "quantity": 100.0,
        "fee": 1.0,
        "thesis": "test-thesis",
        "invalidation_price": 9.5,
        "regime": "主升",
        "tags": ["龙头"],
    }
    row.update(overrides)
    return row


def test_insight_mistake_clusters_four_kinds_detected() -> None:
    """Test deterministic identification of all 4 mistake cluster kinds."""
    trades = [
        # 1. 跌破 invalidation_price 未离场: 买入止损9.5，卖出价8.5 (< 9.5 发生实质跌破)，且发生亏损
        _toy_trade("T-1", symbol="TOY-A", side="BUY", trade_date="2026-08-03", trade_time="09:40:00", price=10.0, invalidation_price=9.5),
        _toy_trade("T-2", symbol="TOY-A", side="SELL", trade_date="2026-08-05", trade_time="10:00:00", price=8.5, invalidation_price=None),

        # 2. 开盘 15 分钟内平仓: 卖出时间在 09:30:00 到 09:45:00 之间
        _toy_trade("T-3", symbol="TOY-B", side="BUY", trade_date="2026-08-03", trade_time="10:00:00", price=20.0, invalidation_price=18.0),
        _toy_trade("T-4", symbol="TOY-B", side="SELL", trade_date="2026-08-06", trade_time="09:38:00", price=19.0, invalidation_price=None),

        # 3. 持仓仅 1 日 (次日平仓，holding_days == 1)
        _toy_trade("T-5", symbol="TOY-C", side="BUY", trade_date="2026-08-03", trade_time="11:00:00", price=30.0, invalidation_price=28.0),
        _toy_trade("T-6", symbol="TOY-C", side="SELL", trade_date="2026-08-04", trade_time="14:00:00", price=29.0, invalidation_price=None),

        # 4. 连续亏损后 10 分钟内再次开仓: T-6 在 2026-08-04 14:00:00 卖出亏损，T-7 在 14:05:00 (5分钟内) 再次开仓
        _toy_trade("T-7", symbol="TOY-C", side="BUY", trade_date="2026-08-04", trade_time="14:05:00", price=40.0, invalidation_price=38.0),
        _toy_trade("T-8", symbol="TOY-C", side="SELL", trade_date="2026-08-10", trade_time="14:00:00", price=39.0, invalidation_price=None),
    ]

    ledger = build_tenant_ledger(trades)
    clusters = cluster_mistakes(ledger, trades=trades)

    kinds_found = {c["kind"] for c in clusters}
    assert "broken_invalidation_unstopped" in kinds_found
    assert "early_morning_exit" in kinds_found
    assert "one_day_holding" in kinds_found
    assert "revenge_reentry" in kinds_found

    # Check non-silent observation envelope for every cluster
    for cluster in clusters:
        assert cluster["cluster_id"]
        assert cluster["kind"] in CLUSTER_KINDS
        assert cluster["label_seed"]
        assert cluster["count"] >= 1
        assert "net_pnl" in cluster
        assert "avg_return_pct" in cluster
        assert cluster["first_at"] != "unknown"
        assert cluster["last_at"] != "unknown"
        assert cluster["evidence"]
        # Required observation fields (AGENTS.md #5)
        for field_name in ("invalidation", "time_stop", "give_up", "data_source", "available_at", "data_quality"):
            assert field_name in cluster
            assert cluster[field_name] != ""


def test_insight_mistake_degrades_when_no_invalidation_price() -> None:
    """Trades without invalidation_price must safely skip broken_invalidation check."""
    trades = [
        _toy_trade("T-1", symbol="TOY-A", side="BUY", trade_date="2026-08-03", trade_time="09:40:00", price=10.0, invalidation_price=None),
        _toy_trade("T-2", symbol="TOY-A", side="SELL", trade_date="2026-08-05", trade_time="10:00:00", price=8.5, invalidation_price=None),
    ]
    ledger = build_tenant_ledger(trades)
    clusters = cluster_mistakes(ledger, trades=trades)
    kinds_found = {c["kind"] for c in clusters}
    assert "broken_invalidation_unstopped" not in kinds_found


def test_insight_never_interprets_other_accounts_or_symbols_as_revenge():
    rows = [_toy_trade("B"), _toy_trade("S", side="SELL", trade_date="2026-08-04", trade_time="10:00:00", price=8),
            _toy_trade("OTHER", account_id="another-toy", trade_date="2026-08-04", trade_time="10:01:00")]
    clusters = cluster_mistakes(build_tenant_ledger(rows), trades=rows)
    assert all(c["kind"] != "revenge_reentry" for c in clusters)
    assert all("情绪化" not in c["label_seed"] and "草率" not in c["label_seed"] for c in clusters)


def test_insight_edges_grouping_and_small_sample() -> None:
    """Test edge library extraction on tag, regime, holding with small_sample flag."""
    trades = [
        # tag "龙头", regime "主升", holding 3 days
        _toy_trade("T-1", symbol="TOY-A", side="BUY", trade_date="2026-08-03", trade_time="09:40:00", price=10.0, tags=["龙头"], regime="主升", currency="USD"),
        _toy_trade("T-2", symbol="TOY-A", side="SELL", trade_date="2026-08-06", trade_time="10:00:00", price=12.0, currency="USD"),
    ]
    ledger = build_tenant_ledger(trades)
    edges = extract_edges(ledger)

    assert len(edges) >= 1
    for edge in edges:
        assert edge["edge_id"]
        assert edge["dimension"] in EDGE_DIMENSIONS
        assert edge["key"]
        assert edge["trade_count"] == 1
        assert edge["small_sample"] is True
        assert edge["win_rate"] == 100.0
        assert edge["net_pnl"] > 0
        # Required observation fields
        for field_name in ("invalidation", "time_stop", "give_up", "data_source", "available_at", "data_quality"):
            assert field_name in edge
            assert edge[field_name] != ""


def test_service_insight_endpoints_and_safety(tmp_path: Path) -> None:
    """Test TraderService.insight_mistakes and insight_edges endpoints."""
    # A plain path, matching every other test in the suite. The URL form is still
    # accepted by resolve_database_path and covered in the storage tests, but this
    # test is about the insight endpoints rather than about URL parsing.
    store = open_store(tmp_path / "trader.db")
    service = TraderService(store)
    ctx = AuthContext(user_id="toy-user", tenant_id="toy-tenant", display_name="Toy User", mode="local")

    # Empty journal case
    mistakes_empty = service.insight_mistakes(ctx)
    assert mistakes_empty["status"] == "ok"
    assert mistakes_empty["count"] == 0
    assert mistakes_empty["rows"] == []
    assert mistakes_empty["safety"] == SAFETY_DECLARATION

    edges_empty = service.insight_edges(ctx)
    assert edges_empty["status"] == "ok"
    assert edges_empty["count"] == 0
    assert edges_empty["rows"] == []
    assert edges_empty["dimensions"] == list(EDGE_DIMENSIONS)
    assert edges_empty["safety"] == SAFETY_DECLARATION

    # Import trades
    service.import_trades(ctx, rows=[
        _toy_trade("T-1", symbol="TOY-A", side="BUY", trade_date="2026-08-03", trade_time="09:40:00", price=10.0, invalidation_price=9.5),
        _toy_trade("T-2", symbol="TOY-A", side="SELL", trade_date="2026-08-04", trade_time="09:40:00", price=9.0, invalidation_price=None),
    ])

    mistakes = service.insight_mistakes(ctx)
    assert mistakes["status"] == "ok"
    assert mistakes["count"] >= 1
    assert mistakes["safety"] == SAFETY_DECLARATION

    edges = service.insight_edges(ctx)
    assert edges["status"] == "ok"
    assert edges["count"] >= 1
    assert edges["safety"] == SAFETY_DECLARATION
