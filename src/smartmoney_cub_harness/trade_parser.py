from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from smartmoney_cub_harness.regime import evaluate_regime_fit, get_regime_info
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


# 预设的典型实战案例（包含知行合一的优秀操作与知行不合一的反面教材）
DEMO_TRADE_CASES: list[dict[str, Any]] = [
    {
        "trade_id": "TR-20260901-01",
        "symbol": "002466",
        "name": "天齐锂业",
        "regime": "亢龙",
        "thesis": "板块大涨5天，看盘中脉冲冲动买入跟风，博弈后排补涨首板",
        "invalidation_price": 54.00,
        "entry_time": "2026-09-01 13:45:00",
        "entry_price": 56.50,
        "exit_time": "2026-09-03 10:15:00",
        "exit_price": 48.10,
        "volume": 2000,
        "max_adverse_excursion_pct": -15.2,
        "tags": ["杂毛跟风", "冲动追高", "破止损死扛"],
    },
    {
        "trade_id": "TR-20260902-02",
        "symbol": "603993",
        "name": "洛阳钼业",
        "regime": "生长",
        "thesis": "主线板块分歧转一致，一进二身位龙头，早盘承接有力上板确认",
        "invalidation_price": 7.80,
        "entry_time": "2026-09-02 09:42:00",
        "entry_price": 8.10,
        "exit_time": "2026-09-04 14:50:00",
        "exit_price": 9.60,
        "volume": 10000,
        "max_adverse_excursion_pct": -0.8,
        "tags": ["主线龙头", "身位优势", "顺应周期"],
    },
    {
        "trade_id": "TR-20260903-03",
        "symbol": "000725",
        "name": "京东方A",
        "regime": "衰退",
        "thesis": "前龙头破位连续大跌3天，觉得跌透了左侧抄底博超跌反弹",
        "invalidation_price": 4.10,
        "entry_time": "2026-09-03 14:10:00",
        "entry_price": 4.25,
        "exit_time": "2026-09-05 09:35:00",
        "exit_price": 3.86,
        "volume": 15000,
        "max_adverse_excursion_pct": -9.8,
        "tags": ["左侧抄底", "退潮接飞刀", "逆周期交易"],
    },
    {
        "trade_id": "TR-20260904-04",
        "symbol": "300059",
        "name": "东方财富",
        "regime": "初生",
        "thesis": "冰点回暖首日试错先锋板，轻仓试探，跌破分时均线即刻止损",
        "invalidation_price": 14.70,
        "entry_time": "2026-09-04 10:20:00",
        "entry_price": 15.00,
        "exit_time": "2026-09-05 09:40:00",
        "exit_price": 14.65,
        "volume": 4000,
        "max_adverse_excursion_pct": -2.5,
        "tags": ["轻仓试错", "果断止损", "纪律合格"],
    },
    {
        "trade_id": "TR-20260905-05",
        "symbol": "600030",
        "name": "中信证券",
        "regime": "潜藏",
        "thesis": "混沌期大盘缩量震荡，手痒反复做T，来回被摩擦",
        "invalidation_price": 20.00,
        "entry_time": "2026-09-05 11:15:00",
        "entry_price": 20.40,
        "exit_time": "2026-09-05 14:45:00",
        "exit_price": 20.10,
        "volume": 3000,
        "max_adverse_excursion_pct": -1.8,
        "tags": ["混沌期频繁做T", "管不住手", "无意义磨损"],
    },
]


def normalize_trade_record(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    """标准化单笔交割单交易记录"""
    symbol = str(
        raw.get("证券代码")
        or raw.get("代码")
        or raw.get("symbol")
        or raw.get("code")
        or ""
    ).strip()
    name = str(
        raw.get("证券名称")
        or raw.get("名称")
        or raw.get("name")
        or raw.get("symbol_name")
        or f"标的_{symbol}"
    ).strip()
    action = str(
        raw.get("操作")
        or raw.get("买卖标志")
        or raw.get("业务名称")
        or raw.get("action")
        or raw.get("side")
        or ""
    ).strip()

    date_str = str(
        raw.get("成交日期")
        or raw.get("发生日期")
        or raw.get("date")
        or raw.get("trade_date")
        or ""
    ).strip()
    time_str = str(
        raw.get("成交时间")
        or raw.get("委托时间")
        or raw.get("time")
        or raw.get("trade_time")
        or ""
    ).strip()

    price = float(
        raw.get("成交均价")
        or raw.get("成交价格")
        or raw.get("价格")
        or raw.get("price")
        or 0
    )
    volume = abs(
            float(
                raw.get("成交数量")
                or raw.get("数量")
                or raw.get("volume")
                or raw.get("quantity")
                or 0
            )
    )
    amount = float(
        raw.get("成交金额")
        or raw.get("金额")
        or raw.get("amount")
        or (price * volume)
    )

    thesis = str(raw.get("买入理由") or raw.get("thesis") or "")
    invalidation = raw.get("止损价") or raw.get("invalidation_price")
    invalidation_price = float(invalidation) if invalidation is not None else None
    regime = str(raw.get("情绪周期") or raw.get("regime") or "")

    return {
        **raw,
        "index": idx,
        "symbol": symbol,
        "name": name,
        "action": action,
        "datetime": f"{date_str} {time_str}".strip(),
        "price": price,
        "volume": volume,
        "amount": amount,
        "thesis": thesis,
        "invalidation_price": invalidation_price,
        "regime": regime,
        "tags": raw.get("tags") or [],
    }


def parse_csv_content(content: str) -> list[dict[str, Any]]:
    """解析通用或同花顺格式的交割单CSV文本"""
    # 尝试自动跳过同花顺首行多余元数据
    lines = content.strip().splitlines()
    if not lines:
        return []

    # 寻找表头行
    start_idx = 0
    for i, line in enumerate(lines[:10]):
        if any(h in line for h in ["证券代码", "代码", "symbol", "成交日期", "买卖标志", "操作"]):
            start_idx = i
            break

    csv_reader = csv.DictReader(lines[start_idx:])
    records: list[dict[str, Any]] = []
    for idx, row in enumerate(csv_reader, start=1):
        if not row:
            continue
        # 清理字段键中的空字符与BOM
        clean_row = {str(k).strip().lstrip("\ufeff"): v for k, v in row.items() if k}
        records.append(normalize_trade_record(clean_row, idx))
    return records


def analyze_trade(trade: dict[str, Any]) -> dict[str, Any]:
    """对单笔交易进行深度体检诊断"""
    entry_price = float(trade["entry_price"])
    exit_price = float(trade["exit_price"])
    return_pct = round(((exit_price - entry_price) / entry_price) * 100, 2)
    max_adverse = float(trade.get("max_adverse_excursion_pct", return_pct if return_pct < 0 else 0))

    invalidation_price = trade.get("invalidation_price")
    regime = trade.get("regime") or "生长"
    thesis = trade.get("thesis") or ""

    # 1. 周期契合度评估
    regime_res = evaluate_regime_fit(
        action="买入",
        target_desc=f"{trade.get('name')} {thesis} {' '.join(trade.get('tags', []))}",
        regime_name=regime
    )

    # 2. 知行合一与止损执行纪律
    discipline_score = 100
    violations: list[str] = []
    critiques: list[str] = []

    # 止损纪律检查
    if invalidation_price is None:
        violations.append("开仓未设置硬止损防守价位 (裸奔开仓)")
        discipline_score -= 30
        critiques.append("无防守不买入：连止损价都没想好就冲进去，本质是把希望寄托在运气上。")
    else:
        # 如果触及止损价
        stop_triggered = (exit_price < invalidation_price) or (max_adverse <= -abs(((invalidation_price - entry_price) / entry_price) * 100))
        if stop_triggered:
            if return_pct < -abs(((invalidation_price - entry_price) / entry_price) * 100) - 2.0:
                violations.append(f"击穿计划止损位({invalidation_price}元)未及时斩仓，导致严重深亏({return_pct}%)")
                discipline_score -= 40
                critiques.append(f"知行不合一：买入时信誓旦旦计划{invalidation_price}止损，跌破后心存侥幸死扛，把小亏抗成重伤。")
            else:
                critiques.append("止损执行果断：触及止损位按计划离场，保住元气，此单虽亏尤荣。")

    # 周期违背检查
    if not regime_res["is_aligned"]:
        discipline_score -= (100 - regime_res["fit_score"]) // 2
        for v in regime_res["violations"]:
            violations.append(v)
        for w in regime_res["warnings"]:
            critiques.append(w)

    discipline_score = max(0, min(100, discipline_score))

    # 结果定级
    if discipline_score >= 85:
        health_grade = "S (知行合一典范)"
        badge_color = "emerald"
    elif discipline_score >= 70:
        health_grade = "A (执行力合格)"
        badge_color = "blue"
    elif discipline_score >= 50:
        health_grade = "B (存在纪律瑕疵)"
        badge_color = "amber"
    else:
        health_grade = "D (严重违规接盘)"
        badge_color = "rose"

    return {
        "trade_id": trade.get("trade_id") or f"TR-{trade.get('symbol')}",
        "symbol": trade.get("symbol"),
        "name": trade.get("name"),
        "regime": regime,
        "entry_time": trade.get("entry_time"),
        "entry_price": entry_price,
        "exit_time": trade.get("exit_time"),
        "exit_price": exit_price,
        "volume": trade.get("volume", 1000),
        "return_pct": return_pct,
        "max_adverse_excursion_pct": max_adverse,
        "pnl_amount": round((exit_price - entry_price) * trade.get("volume", 1000), 2),
        "thesis": thesis,
        "invalidation_price": invalidation_price,
        "discipline_score": discipline_score,
        "health_grade": health_grade,
        "badge_color": badge_color,
        "violations": violations,
        "critiques": critiques,
        "safety": SAFETY_DECLARATION,
    }


def generate_portfolio_health_report(trades: list[dict[str, Any]], current_regime: str = "生长") -> dict[str, Any]:
    """生成整套交割单的综合体检报告"""
    if not trades:
        return {
            "summary": {"total_trades": 0, "win_rate": 0, "avg_discipline_score": 0},
            "analyzed_trades": [],
            "regime": get_regime_info(current_regime),
            "safety": SAFETY_DECLARATION,
        }

    analyzed_trades = [analyze_trade(t) for t in trades]

    total = len(analyzed_trades)
    win_trades = [t for t in analyzed_trades if t["return_pct"] > 0]
    loss_trades = [t for t in analyzed_trades if t["return_pct"] < 0]
    win_rate = round((len(win_trades) / total) * 100, 1)

    total_profit = sum(t["pnl_amount"] for t in win_trades)
    total_loss = abs(sum(t["pnl_amount"] for t in loss_trades))
    profit_loss_ratio = round(total_profit / total_loss, 2) if total_loss > 0 else 99.9

    avg_discipline = round(sum(t["discipline_score"] for t in analyzed_trades) / total, 1)
    violation_count = sum(len(t["violations"]) for t in analyzed_trades)

    # 归因分布
    violation_categories: dict[str, int] = {}
    for t in analyzed_trades:
        for v in t["violations"]:
            category = v.split("（")[0]
            violation_categories[category] = violation_categories.get(category, 0) + 1

    # 综合体检评级
    if avg_discipline >= 80 and win_rate >= 50:
        overall_grade = "成熟游资型 (情绪与执行力均在线)"
        grade_tag = "S"
    elif avg_discipline >= 70:
        overall_grade = "进阶修炼期 (大体守纪律，偶有上头)"
        grade_tag = "B+"
    elif avg_discipline >= 50:
        overall_grade = "危险摇摆期 (知行脱节，情绪化交易频发)"
        grade_tag = "C"
    else:
        overall_grade = "严重ICU期 (频繁逆周期追高与死扛，资金处于极高风险)"
        grade_tag = "D"

    return {
        "summary": {
            "total_trades": total,
            "win_count": len(win_trades),
            "loss_count": len(loss_trades),
            "win_rate": win_rate,
            "total_profit_loss": round(sum(t["pnl_amount"] for t in analyzed_trades), 2),
            "profit_loss_ratio": profit_loss_ratio,
            "avg_discipline_score": avg_discipline,
            "total_violations": violation_count,
            "overall_grade": overall_grade,
            "grade_tag": grade_tag,
            "violation_categories": violation_categories,
        },
        "current_regime": get_regime_info(current_regime),
        "analyzed_trades": analyzed_trades,
        "safety": SAFETY_DECLARATION,
    }
