from __future__ import annotations

from typing import Any, Mapping

TOOL_TITLES: dict[str, str] = {
    "list_trades": "查询历史交易",
    "get_trade": "获取单笔交易详情",
    "analytics_summary": "查询复盘统计摘要",
    "calendar_month": "查询月度交易日历",
    "open_positions": "查询当前持仓",
    "list_rules": "查询规则库",
    "list_review_cases": "查询复盘案例",
    "propose_challenger_rule": "提出挑战者规则",
    "data_quality_report": "检查数据质量报告",
}


def get_tool_title(name: str) -> str:
    """返回工具的人类可读中文动作名称，未知工具回退为其原始名称。"""
    return TOOL_TITLES.get(name, f"调用工具 {name}")


def summarize_tool_result(
    name: str,
    args: Mapping[str, Any],
    result: Any,
    elapsed_ms: float,
) -> dict[str, Any]:
    """生成工具调用的结构化人类可读中文摘要。

    返回:
        {
            "title": 中文动作名,
            "summary": 一句中文摘要含真实数字,
            "stats": {...},
            "status": "ok" | "error",
            "duration_ms": float,
        }
    注意：数字严禁编造，必须严格来自 result；result 不含数字或出错时只客观描述动作与状态。
    """
    title = get_tool_title(name)
    duration_ms = round(float(elapsed_ms), 2)

    # 1. 容错处理非字典或出错返回
    if not isinstance(result, dict):
        return {
            "title": title,
            "summary": f"{title}完成",
            "stats": {},
            "status": "ok",
            "duration_ms": duration_ms,
        }

    status = "error" if result.get("status") == "error" else "ok"
    if status == "error":
        err = result.get("error")
        err_msg = ""
        err_code = ""
        if isinstance(err, dict):
            err_msg = str(err.get("message") or "")
            err_code = str(err.get("code") or "")
        elif err is not None:
            err_msg = str(err)
        detail = f"：{err_msg}" if err_msg else ""
        return {
            "title": title,
            "summary": f"{title}失败{detail}",
            "stats": {"error": err_msg or err_code or "unknown_error"},
            "status": "error",
            "duration_ms": duration_ms,
        }

    stats: dict[str, Any] = {}
    summary = f"{title}完成"

    try:
        if name == "list_trades":
            count = result.get("count")
            returned = result.get("returned")
            if count is not None:
                stats["count"] = count
            if returned is not None:
                stats["returned"] = returned
            if count is not None and returned is not None:
                summary = f"查询到 {count} 笔交易，当前返回前 {returned} 笔"
            elif count is not None:
                summary = f"查询到 {count} 笔交易"

        elif name == "get_trade":
            trade = result.get("trade")
            if isinstance(trade, dict):
                symbol = trade.get("symbol")
                net_pnl = trade.get("net_pnl")
                return_pct = trade.get("return_pct")
                holding_days = trade.get("holding_days")
                if symbol is not None:
                    stats["symbol"] = symbol
                if net_pnl is not None:
                    stats["net_pnl"] = net_pnl
                if return_pct is not None:
                    stats["return_pct"] = return_pct
                if holding_days is not None:
                    stats["holding_days"] = holding_days

                parts: list[str] = []
                if symbol:
                    parts.append(f"标的 {symbol}")
                if net_pnl is not None:
                    parts.append(f"净盈亏 {net_pnl}")
                if return_pct is not None:
                    parts.append(f"收益率 {return_pct}%")
                if holding_days is not None:
                    parts.append(f"持仓 {holding_days} 天")

                if parts:
                    summary = f"获取交易详情（{ '，'.join(parts)}）"
                else:
                    summary = "获取单笔交易详情完成"

        elif name == "analytics_summary":
            summary_data = result.get("summary")
            if isinstance(summary_data, dict):
                trade_count = summary_data.get("trade_count")
                win_rate = summary_data.get("win_rate")
                total_net_pnl = summary_data.get("total_net_pnl")
                if trade_count is not None:
                    stats["trade_count"] = trade_count
                if win_rate is not None:
                    stats["win_rate"] = win_rate
                if total_net_pnl is not None:
                    stats["total_net_pnl"] = total_net_pnl

                parts = []
                if trade_count is not None:
                    parts.append(f"总交易 {trade_count} 笔")
                if win_rate is not None:
                    parts.append(f"胜率 {win_rate}%")
                if total_net_pnl is not None:
                    parts.append(f"累计盈亏 {total_net_pnl}")

                if parts:
                    summary = f"统计分析完成：{'，'.join(parts)}"
                else:
                    summary = "统计分析完成"

        elif name == "calendar_month":
            year = result.get("year", args.get("year"))
            month = result.get("month", args.get("month"))
            days = result.get("days")
            day_count = len(days) if isinstance(days, list) else None
            if year is not None:
                stats["year"] = year
            if month is not None:
                stats["month"] = month
            if day_count is not None:
                stats["day_count"] = day_count

            if year is not None and month is not None and day_count is not None:
                summary = f"获取 {year} 年 {month} 月交易日历，包含 {day_count} 个交易日记录"
            elif year is not None and month is not None:
                summary = f"获取 {year} 年 {month} 月交易日历"
            else:
                summary = "获取月度交易日历完成"

        elif name == "open_positions":
            count = result.get("count")
            if count is None and isinstance(result.get("positions"), list):
                count = len(result["positions"])
            if count is not None:
                stats["count"] = count
                summary = f"查询到 {count} 个当前未了结持仓"
            else:
                summary = "查询未了结持仓完成"

        elif name == "list_rules":
            count = result.get("count")
            if count is None and isinstance(result.get("rules"), list):
                count = len(result["rules"])
            if count is not None:
                stats["count"] = count
                summary = f"查询到 {count} 条规则库记录"
            else:
                summary = "查询规则库完成"

        elif name == "list_review_cases":
            count = result.get("count")
            if count is None and isinstance(result.get("cases"), list):
                count = len(result["cases"])
            if count is not None:
                stats["count"] = count
                summary = f"查询到 {count} 个复盘案例"
            else:
                summary = "查询复盘案例完成"

        elif name == "propose_challenger_rule":
            rule = result.get("rule") if isinstance(result.get("rule"), dict) else {}
            rule_id = rule.get("rule_id") or args.get("rule_id") or ""
            metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
            sample_count = metrics.get("sample_count")
            blockers = metrics.get("blockers")
            blocker_count = len(blockers) if isinstance(blockers, list) else 0

            if rule_id:
                stats["rule_id"] = rule_id
            if sample_count is not None:
                stats["sample_count"] = sample_count
            stats["blocker_count"] = blocker_count

            parts = []
            if rule_id:
                parts.append(f"规则 ID {rule_id}")
            if sample_count is not None:
                parts.append(f"样本数 {sample_count}")
            if blocker_count > 0:
                parts.append(f"含 {blocker_count} 项待补齐门禁")
            else:
                parts.append("无阻碍门禁")

            if parts:
                summary = f"提出挑战者规则（{'，'.join(parts)}）"
            else:
                summary = "提出挑战者规则成功"

        elif name == "data_quality_report":
            ledger_status = result.get("ledger_status")
            blocking_issues = result.get("blocking_issue_count")
            open_pos = result.get("open_position_count")
            if ledger_status is not None:
                stats["ledger_status"] = ledger_status
            if blocking_issues is not None:
                stats["blocking_issue_count"] = blocking_issues
            if open_pos is not None:
                stats["open_position_count"] = open_pos

            parts = []
            if ledger_status:
                parts.append(f"账本状态为 {ledger_status}")
            if blocking_issues is not None:
                parts.append(f"阻塞问题 {blocking_issues} 项")
            if open_pos is not None:
                parts.append(f"未闭合持仓 {open_pos} 个")

            if parts:
                summary = f"数据质量报告：{'，'.join(parts)}"
            else:
                summary = "数据质量检查完成"

        else:
            # 未知工具回退
            count_candidates = [
                result.get(k)
                for k in ("count", "total", "returned", "size")
                if isinstance(result.get(k), (int, float))
            ]
            if count_candidates:
                summary = f"{title}完成（数量 {count_candidates[0]}）"
            else:
                summary = f"{title}完成"

    except Exception:  # noqa: BLE001 - 保证未知或异常结构不抛出异常
        summary = f"{title}完成"

    return {
        "title": title,
        "summary": summary,
        "stats": stats,
        "status": status,
        "duration_ms": duration_ms,
    }

