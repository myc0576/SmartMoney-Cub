from __future__ import annotations

import json
import threading
import urllib.request
from http.server import HTTPServer

from smartmoney_cub_harness.challenger import generate_challenger_review
from smartmoney_cub_harness.dashboard.server import DashboardHTTPHandler, DashboardState
from smartmoney_cub_harness.regime import evaluate_regime_fit, get_regime_info, REGIME_PHASES
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trade_parser import (
    analyze_trade,
    DEMO_TRADE_CASES,
    generate_portfolio_health_report,
    parse_csv_content,
)


def test_regime_phases() -> None:
    assert len(REGIME_PHASES) == 5
    for phase in ("初生", "生长", "亢龙", "衰退", "潜藏"):
        info = get_regime_info(phase)
        assert info["name"] == phase
        assert "sentiment_score" in info
        assert "maxims" in info

    # Test misaligned regime fit (e.g. buying follower in 亢龙)
    eval_kanglong = evaluate_regime_fit("买入", "后排跟风杂毛", "亢龙")
    assert not eval_kanglong["is_aligned"]
    assert len(eval_kanglong["violations"]) > 0

    # Test aligned regime fit (e.g. buying leader in 生长)
    eval_growth = evaluate_regime_fit("买入", "主线身位换手龙", "生长")
    assert eval_growth["is_aligned"]
    assert eval_growth["safety"] == SAFETY_DECLARATION


def test_trade_parser_and_diagnosis() -> None:
    csv_sample = """成交日期,成交时间,证券代码,证券名称,操作,成交均价,成交数量,成交金额,买入理由,止损价,情绪周期
2026-09-01,10:30:00,002466,天齐锂业,买入,50.00,1000,50000,板块主线龙头一进二,48.00,生长
2026-09-02,14:40:00,002466,天齐锂业,卖出,55.00,1000,55000,,,
"""
    records = parse_csv_content(csv_sample)
    assert len(records) == 2
    assert records[0]["symbol"] == "002466"
    assert records[0]["price"] == 50.00

    report = generate_portfolio_health_report(DEMO_TRADE_CASES, current_regime="生长")
    summary = report["summary"]
    assert summary["total_trades"] == len(DEMO_TRADE_CASES)
    assert summary["total_violations"] > 0
    assert report["safety"] == SAFETY_DECLARATION


def test_challenger_review_and_rule_generation() -> None:
    worst_trade = analyze_trade(DEMO_TRADE_CASES[0])  # 天齐锂业 -14.8% loss
    review = generate_challenger_review(worst_trade)

    assert review["persona"]["name"] == "老游资风控总监 · 严师"
    assert len(review["cross_examination_questions"]) >= 3
    assert review["proposed_rule"] is not None
    assert review["proposed_rule"]["status"] == "challenger"
    assert review["safety"] == SAFETY_DECLARATION


def test_dashboard_state_and_http_endpoints() -> None:
    server = HTTPServer(("127.0.0.1", 0), DashboardHTTPHandler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"

    # 1. GET /
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
        assert "SmartMoney-Cub" in html
        assert "READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE" in html

    # 2. GET /api/status
    with urllib.request.urlopen(f"{base_url}/api/status") as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert data["safety"] == SAFETY_DECLARATION

    # 3. GET /api/data
    with urllib.request.urlopen(f"{base_url}/api/data") as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert "report" in data
        assert "rules" in data
        assert "challenger_reviews" in data

    # 4. POST /api/set_regime
    post_req = urllib.request.Request(
        f"{base_url}/api/set_regime",
        data=json.dumps({"regime": "亢龙"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(post_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["active_regime"] == "亢龙"

    # 5. POST /api/promote_rule
    post_promote = urllib.request.Request(
        f"{base_url}/api/promote_rule",
        data=json.dumps({"rule_id": "CHALL-101"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(post_promote) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        # A dashboard click can only request a promotion; it never mutates champion.
        assert data["status"] == "recommendation"
        assert data["champion_mutated"] is False
        assert data["core_rules_mutated"] is False
        assert data["confirmation_required"] is True
        assert "sample_count_below_20" in data["blockers"]

    server.shutdown()
    server.server_close()


def test_demo_data_is_labelled_and_promotion_requires_confirmation() -> None:
    state = DashboardState()
    # Demo fixture data must be clearly labelled so its numbers are never read
    # as the user's real performance.
    assert state.data_origin == "demo_fixture"
    assert state.report["data_origin"] == "demo_fixture"

    # A bare request recommends only.
    requested = state.request_promotion("CHALL-101")
    assert requested["status"] == "recommendation"
    assert requested["champion_mutated"] is False
    assert any(rule["rule_id"] == "CHALL-101" for rule in state.rules["challengers"])
    assert all(rule["rule_id"] != "CHALL-101" for rule in state.rules["champions"])

    # Explicit confirmation without a written note is still rejected.
    no_note = state.request_promotion("CHALL-101", confirm=True, note="   ")
    assert no_note["champion_mutated"] is False
    assert "explicit_confirmation_note_required" in no_note["blockers"]

    # Unknown rules never become champion.
    unknown = state.request_promotion("CHALL-999", confirm=True, note="approve")
    assert unknown["status"] == "not_found"
    assert unknown["champion_mutated"] is False


def test_promotion_with_real_metrics_requires_note_then_mutates() -> None:
    state = DashboardState()
    state.rules["challengers"].append(
        {
            "rule_id": "CHALL-TEST",
            "title": "样本充足候选规则",
            "family": "risk_contract",
            "status": "challenger",
            "tested_samples": 25,
            "target_samples": 20,
        }
    )
    recommended = state.request_promotion("CHALL-TEST")
    assert recommended["status"] == "recommendation"
    assert recommended["champion_mutated"] is False

    promoted = state.request_promotion("CHALL-TEST", confirm=True, note="25 笔样本复盘确认")
    assert promoted["champion_mutated"] is True
    champion = next(rule for rule in state.rules["champions"] if rule["rule_id"] == "CHALL-TEST")
    assert champion["promotion_note"] == "25 笔样本复盘确认"
    # No fabricated performance numbers are attached during promotion.
    assert "win_rate_impact" not in champion
    assert "violation_rate" not in champion


def test_csv_import_surfaces_needs_review_instead_of_inventing_trades() -> None:
    state = DashboardState()
    # A sell with no prior position cannot be silently paired into a trade.
    csv_text = """成交日期,成交时间,证券代码,证券名称,操作,成交均价,成交数量
2026-09-02,10:00:00,600519,贵州茅台,卖出,1500.00,100
"""
    count = state.load_trades_from_csv(csv_text)
    assert count == 0
    assert state.data_origin == "user_csv"
    assert state.ledger is not None
    assert state.ledger["status"] == "needs_review"
    assert any(issue["code"] == "sell_without_position" for issue in state.needs_review)
    assert state.report["data_origin"] == "user_csv"


def test_csv_import_pairs_real_round_trip_with_t_plus_one() -> None:
    state = DashboardState()
    csv_text = """成交日期,成交时间,证券代码,证券名称,操作,成交均价,成交数量,买入理由,market
2026-09-01,09:40:00,600111,北方稀土,买入,10.00,1000,主线龙头,CN-A
2026-09-01,14:00:00,600111,北方稀土,卖出,11.00,1000,,CN-A
"""
    state.load_trades_from_csv(csv_text)
    assert state.ledger is not None
    # Same-day sell of a same-day buy violates T+1 and must be flagged.
    assert state.ledger["status"] == "needs_review"
    assert any(issue["code"] == "t_plus_one_violation" for issue in state.needs_review)

def test_dashboard_extended_api_endpoints() -> None:
    server = HTTPServer(("127.0.0.1", 0), DashboardHTTPHandler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"

    # 1. OPTIONS 请求
    opt_req = urllib.request.Request(f"{base_url}/api/status", method="OPTIONS")
    with urllib.request.urlopen(opt_req) as resp:
        assert resp.status == 200
        assert resp.headers.get("Access-Control-Allow-Origin") == "*"

    # 2. GET /api/workspace/summary
    with urllib.request.urlopen(f"{base_url}/api/workspace/summary") as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert "summary" in data
        assert data["safety"] == SAFETY_DECLARATION

    # 3. GET /api/workspace/cases
    with urllib.request.urlopen(f"{base_url}/api/workspace/cases") as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert "cases" in data

    # 4. GET /api/plugins/list
    with urllib.request.urlopen(f"{base_url}/api/plugins/list") as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert "plugins" in data

    # 5. GET /api/plugins/catalog
    with urllib.request.urlopen(f"{base_url}/api/plugins/catalog") as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert "entries" in data
        assert len(data["entries"]) >= 10

    # 6. GET /api/profiles
    with urllib.request.urlopen(f"{base_url}/api/profiles") as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert data["active_profile"] == "default-offline"
        assert "a-share-review" in data["profiles"]

    # 7. POST /api/profiles/switch
    switch_req = urllib.request.Request(
        f"{base_url}/api/profiles/switch",
        data=json.dumps({"profile": "a-share-review"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(switch_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert data["active_profile"] == "a-share-review"

    # 8. POST /api/share_pack/generate
    share_req = urllib.request.Request(
        f"{base_url}/api/share_pack/generate",
        data=json.dumps({"title": "测试复盘包"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(share_req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert "html" in data
        assert "audit" in data
        assert data["audit"]["status"] == "ok"

    # 9. POST /api/plugins/install (来源不在目录白名单内 -> 拒绝)
    #
    # The install channel used to refuse anything with a remote scheme. It now
    # installs curated projects by id through a whitelist, so the equivalent
    # guarantee is that an arbitrary URL is not a valid install target: it
    # resolves to nothing in the catalog and is reported as not found.
    install_req = urllib.request.Request(
        f"{base_url}/api/plugins/install",
        data=json.dumps({"source": "https://github.com/malicious/remote"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(install_req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] in ("not_found", "refused")
    except urllib.error.HTTPError as err:
        assert err.code == 400
        data = json.loads(err.read().decode("utf-8"))
        assert data["status"] in ("not_found", "refused")

    server.shutdown()
    server.server_close()
