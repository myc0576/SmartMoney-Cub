from __future__ import annotations

import random
from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION


# 老游资辩手经典开场与训斥语录库
HARSH_CRITIQUES_BANK = [
    "短线是生与死的博弈，不是你跟主力谈恋爱的地方。做错了不可怕，做错了死不认账、自我催眠才是亏损的真正根源！",
    "不要用宏观的大逻辑来粉饰你盘中手痒的冲动。你买入那一瞬间，到底是因为看到了确定性的承接，还是仅仅受不了空仓的焦虑？",
    "盘前写的计划字字铿锵，盘中分时一拉脑子一片空白。你这不是交易系统，你这是受情绪操纵的无意识下注！",
    "超短的核心在于盈亏比与高周转。一旦破了防守位，每在里面多呆一分钟，你都在向市场交沉重的认知税。",
]

CHALLENGER_PERSONA = {
    "name": "老游资风控总监 · 严师",
    "motto": "不听好话，只挑骨头；纪律为骨，盈亏随缘。",
    "style": "犀利冷峻、直击要害、不留情面",
}


def generate_challenger_review(trade_analysis: dict[str, Any]) -> dict[str, Any]:
    """为单笔交易生成AI杠精/老游资的犀利复盘诊断与灵魂质问"""
    symbol = trade_analysis.get("symbol", "")
    name = trade_analysis.get("name", "")
    return_pct = float(trade_analysis.get("return_pct", 0))
    violations = trade_analysis.get("violations", [])
    invalidation_price = trade_analysis.get("invalidation_price")
    entry_price = trade_analysis.get("entry_price", 0)
    regime = trade_analysis.get("regime", "生长")
    thesis = trade_analysis.get("thesis", "")

    # 生成灵魂三问
    questions: list[str] = []
    verdict: str = ""
    proposed_rule: dict[str, Any] | None = None

    if return_pct < -5.0:
        # 严重亏损场景
        verdict = f"【当头棒喝】这一单对你的资金曲线是灾难性的重创！买入 {name}({symbol}) 亏损高达 {return_pct}%。"
        if invalidation_price:
            questions.append(
                f"你计划止损价是 {invalidation_price} 元，但实际出局价更低。跌破防守的那一秒钟，你在等什么奇迹发生？"
            )
        else:
            questions.append(
                "你连止损防守位都没定就按下买入键，这不是交易，这跟在赌场掷骰子有什么区别？"
            )
        questions.append(
            f"当时市场处于【{regime}】阶段。你为什么会觉得在此时此刻，这只票能走出独立于周期的奇迹行情？"
        )
        questions.append(
            "如果明天早盘核心主线给出极佳的分歧上车点，你被深套在这里的资金拿什么去抓确定性机会？"
        )

        proposed_rule = {
            "rule_id": f"RULE-DEFENSE-{symbol}",
            "family": "invalidation_discipline",
            "title": "单笔亏损硬刹车铁律",
            "condition": "一旦现价低于计划防守位或单笔回撤达-4%，无条件市价清仓，严禁补仓与心存侥幸。",
            "source_trade": f"{name} ({return_pct}%)",
            "status": "challenger",
            "tested_samples": 1,
            "target_samples": 20,
        }
    elif violations:
        # 有违规但可能亏损不大或微利
        verdict = f"【侥幸警告】虽然这一单没有大亏({return_pct}%)，但你的操作充满了致命的违规隐患！"
        questions.append(
            f"系统检测到【{violations[0]}】。这次侥幸没挨打，下次在同类场景下，你的本金经得起几次天地板？"
        )
        questions.append(
            "凭运气赚来的每一分钱，最后都会凭凭冲动和侥幸加倍还给市场。你愿意把这次微利作为坏习惯的借口吗？"
        )
        questions.append(
            f"买入理由：‘{thesis}’。请扪心自问：盘中到底是谁在做决策？是你的理性，还是跟风的贪婪？"
        )

        proposed_rule = {
            "rule_id": f"RULE-REGIME-{regime}",
            "family": "regime_alignment",
            "title": f"{regime}期动作禁绝规则",
            "condition": f"在【{regime}】情绪周期中，严格禁止开仓非主线杂毛与破位反弹，违背则记一级违规。",
            "source_trade": f"{name} ({violations[0]})",
            "status": "challenger",
            "tested_samples": 1,
            "target_samples": 20,
        }
    else:
        # 知行合一的优质交易
        verdict = f"【客观认可】这一单体现了标准的职业素养。收益率 {return_pct}%，执行严密，进退有据。"
        questions.append(
            "这笔顺势交易之所以成功，最核心的前提是踩对了市场情绪周期的哪个节拍？"
        )
        questions.append(
            "如果下次遇到类似的盘面，能否完全复制本次的冷静与仓位控制？"
        )
        questions.append(
            "当利润奔跑时，你的移动止盈点设置是否科学？有没有过早受杂音干扰交出筹码？"
        )

        proposed_rule = {
            "rule_id": f"RULE-PATTERN-{symbol}",
            "family": "mainline_momentum",
            "title": "主线核心身位复制规则",
            "condition": "在生长周期中，坚决锁定一进二/二进三换手身位龙头，不恐高，不分心杂毛。",
            "source_trade": f"{name} (+{return_pct}%)",
            "status": "challenger",
            "tested_samples": 1,
            "target_samples": 20,
        }

    critique_quote = random.choice(HARSH_CRITIQUES_BANK)

    return {
        "trade_id": trade_analysis.get("trade_id"),
        "persona": CHALLENGER_PERSONA,
        "critique_quote": critique_quote,
        "verdict": verdict,
        "cross_examination_questions": questions,
        "proposed_rule": proposed_rule,
        "safety": SAFETY_DECLARATION,
    }


def get_default_rules_matrix() -> dict[str, Any]:
    """返回初始的规则进化矩阵（包含Champion铁律与Challenger候选规则）"""
    champion_rules = [
        {
            "rule_id": "CHAMP-001",
            "title": "无明确止损位与逻辑严禁开仓",
            "family": "risk_contract",
            "description": "盘前或下单前必须书面确立不可动摇的防守价位与放弃条件，否则视为裸奔违规。",
            "status": "champion",
            "win_rate_impact": "+18.2%",
            "violation_rate": "0%",
            "sample_count": 86,
            "promoted_at": "2026-08-15",
        },
        {
            "rule_id": "CHAMP-002",
            "title": "衰退退潮期执行绝对0仓位冷冻",
            "family": "regime_discipline",
            "description": "当市场龙头A杀且全市场炸板率>40%时，收盘仓位必须为0，绝对严禁抄底任何反弹飞刀。",
            "status": "champion",
            "win_rate_impact": "+24.5%",
            "violation_rate": "1.2%",
            "sample_count": 64,
            "promoted_at": "2026-08-28",
        },
        {
            "rule_id": "CHAMP-003",
            "title": "只做主线核心身位，拒绝边缘杂毛",
            "family": "target_selection",
            "description": "资金只流向题材第一身位龙头或中军，任何跟风二波、边缘助攻票全部列入禁买黑名单。",
            "status": "champion",
            "win_rate_impact": "+15.0%",
            "violation_rate": "3.5%",
            "sample_count": 52,
            "promoted_at": "2026-09-01",
        },
    ]

    challenger_rules = [
        {
            "rule_id": "CHALL-101",
            "title": "亢龙极盛加速段仅限卖出减仓",
            "family": "acceleration_defense",
            "description": "连板高度达到极致或后排全线补涨时，只执行移动止盈，严禁在加速日开立任何新仓位。",
            "status": "challenger",
            "tested_samples": 12,
            "target_samples": 20,
            "avoided_loss_est": "38,500 元",
            "created_at": "2026-09-02",
        },
        {
            "rule_id": "CHALL-102",
            "title": "浮亏超过计划止损0.5%强制闭眼斩仓",
            "family": "execution_speed",
            "description": "盘中一旦跌破止损位，必须使用市价单直接砍仓，禁止等待‘反抽一口’的心态。",
            "status": "challenger",
            "tested_samples": 8,
            "target_samples": 20,
            "avoided_loss_est": "21,200 元",
            "created_at": "2026-09-04",
        },
    ]

    return {
        "champions": champion_rules,
        "challengers": challenger_rules,
        "safety": SAFETY_DECLARATION,
    }
