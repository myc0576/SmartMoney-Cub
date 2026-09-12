from __future__ import annotations

from typing import Any

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

# 易经五阶段与游资情绪周期映射
REGIME_PHASES: dict[str, dict[str, Any]] = {
    "初生": {
        "key": "probing",
        "name": "初生",
        "title": "新题材试错 · 潜龙勿用/见龙在田",
        "stage_order": 1,
        "sentiment_score": 35,
        "description": "上一轮周期出清后的冰点回暖期。新题材暗流涌动，首板试错活跃，板块效应初现雏形但尚未被市场共识认可。",
        "ladder_height_range": "1 - 2 板",
        "recommended_position": "20% - 40% (轻仓试错)",
        "action_stance": "WATCH_AND_PROBE",
        "maxims": [
            "潜龙勿用，阳气初动；看懂之前只打底仓。",
            "试错新题材核心身位，拒绝老题材超跌反弹杂毛。",
            "宁可在冰点转折处买错龙头，不在混沌期做对杂毛。"
        ],
        "allowed_setups": ["新题材首板", "一进二首选身位板", "冰点弱转强换手板"],
        "forbidden_actions": ["盲目重仓押注单一题材", "顶一字追高无换手个股", "抄底上一轮A杀周期的老核心"],
        "color": "#10b981",
        "badge_class": "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    },
    "生长": {
        "key": "growth",
        "name": "生长",
        "title": "主线确立 · 见龙在田/终日乾乾",
        "stage_order": 2,
        "sentiment_score": 75,
        "description": "主线板块大幅爆发，板块内梯队完整（首板-2板-3板）。资金高度聚焦，容错率极高，赚钱效应向全市场扩散。",
        "ladder_height_range": "3 - 5 板",
        "recommended_position": "60% - 90% (主升重仓)",
        "action_stance": "AGGRESSIVE_MAINLINE",
        "maxims": [
            "顺大势，立主线；主升浪里不言顶，分歧低吸选总龙。",
            "围绕绝对核心做T或加仓，不盲目切换分支边缘票。",
            "只要主线领头羊不倒，分歧就是加仓上车点。"
        ],
        "allowed_setups": ["主线分歧转一致板", "二进三/三进四梯队换手龙", "主线中军大成交量承接板"],
        "forbidden_actions": ["恐高去买跟风低位杂毛", "主升阶段过早获利了结", "逆势去开辟非主线独立逻辑"],
        "color": "#3b82f6",
        "badge_class": "bg-blue-500/10 text-blue-400 border-blue-500/30",
    },
    "亢龙": {
        "key": "acceleration",
        "name": "亢龙",
        "title": "极盛高潮 · 亢龙有悔/飞龙在天",
        "stage_order": 3,
        "sentiment_score": 95,
        "description": "市场情绪狂热，连板高度逼近极致（如6-8板+）。后排杂毛全部无厘头补涨一字涨停，板块成交占比过载，盛极必衰随时来临。",
        "ladder_height_range": "6板以上 / 连板极致",
        "recommended_position": "20% - 40% (只卖不买，逢高兑现)",
        "action_stance": "HARVEST_AND_REDUCE",
        "maxims": [
            "亢龙有悔，盈不可久；所有人都在赚钱的时候，屠刀已经在路上。",
            "加速即是卖点，加速段严禁追买任何后排跟风！",
            "只享受手中龙头的疯狂，绝不开设任何新仓位。"
        ],
        "allowed_setups": ["总龙头盘中冲高分批兑现", "紧密跟随移动止盈线", "严格空仓看戏"],
        "forbidden_actions": ["【绝禁】盘中追高打后排跟风板", "【绝禁】加杠杆追买加速缩量一字", "【绝禁】误将高潮看做主升启动"],
        "color": "#f59e0b",
        "badge_class": "bg-amber-500/10 text-amber-400 border-amber-500/30",
    },
    "衰退": {
        "key": "divergence",
        "name": "衰退",
        "title": "分歧扩散 · 亢龙破位/退潮杀跌",
        "stage_order": 4,
        "sentiment_score": 20,
        "description": "领头羊高位跌停或断板大幅负反馈，全市场炸板率激增至40%-60%。亏钱效应向中位股大面积传染，盘面闪崩跌停频现。",
        "ladder_height_range": "高度骤降，连板断层",
        "recommended_position": "0% - 10% (空仓防守)",
        "action_stance": "STRICT_EMPTY_DEFENSE",
        "maxims": [
            "君子不立危墙之下，退潮期空仓比任何赚钱技巧都重要。",
            "大跌不言底，千万不要在退潮第一波当‘抄底烈士’！",
            "管住手是顶级游资与亏损散户的唯一分水岭。"
        ],
        "allowed_setups": ["快速割肉离场/执行破位止损", "空仓复盘观察", "1手单体感冰点温度"],
        "forbidden_actions": ["【违规必批】抄底高位破位龙头做反弹", "【违规必批】打半路分歧破位板", "【违规必批】持仓亏损不断补仓加码"],
        "color": "#ef4444",
        "badge_class": "bg-red-500/10 text-red-400 border-red-500/30",
    },
    "潜藏": {
        "key": "retreat",
        "name": "潜藏",
        "title": "混沌蓄势 · 纯阴剥极/复卦潜伏",
        "stage_order": 5,
        "sentiment_score": 10,
        "description": "极度冰点，成交量萎缩至极致。市场热点散乱轮动，没有持续性赚钱效应，资金都在观望等待新周期的导火索。",
        "ladder_height_range": "空间压制在2板以内",
        "recommended_position": "0% (绝对空仓修养)",
        "action_stance": "REST_AND_STUDY",
        "maxims": [
            "藏器于身，待时而动；忍得住寂寞，才能接得住暴利。",
            "不买也是一种交易，最高级的进攻是防守。",
            "多复盘、多读规则、多做沙盘推演，勿在混沌中消耗子弹。"
        ],
        "allowed_setups": ["完全空仓观战", "梳理规则库与教训复盘", "跟踪龙虎榜顶级席位建仓异动"],
        "forbidden_actions": ["手痒频繁做T", "在电风扇轮动行情里天天追涨杀跌", "借钱加仓"],
        "color": "#8b5cf6",
        "badge_class": "bg-purple-500/10 text-purple-400 border-purple-500/30",
    },
}


def get_regime_info(phase_name: str) -> dict[str, Any]:
    """返回特定周期的详细信息，缺省返回'生长'阶段。"""
    normalized = (phase_name or "").strip()
    if normalized in REGIME_PHASES:
        return REGIME_PHASES[normalized]
    for name, info in REGIME_PHASES.items():
        if info["key"].lower() == normalized.lower():
            return info
    return REGIME_PHASES["生长"]


def evaluate_regime_fit(action: str, target_desc: str, regime_name: str) -> dict[str, Any]:
    """
    评估一笔交易行为是否与当时的市场周期匹配。
    如果违背游资周期心法（例如在亢龙或衰退期追后排），输出违规标签与严厉警告。
    """
    regime = get_regime_info(regime_name)
    phase = regime["name"]
    action_upper = (action or "").upper()
    target_desc = str(target_desc or "")
    violations: list[str] = []
    warnings: list[str] = []
    fit_score = 100

    if phase == "亢龙":
        if "买入" in action or "BUY" in action_upper or "ALERT" in action_upper:
            if any(w in target_desc for w in ["杂毛", "后排", "跟风", "补涨"]):
                violations.append("亢龙加速期追买后排跟风（极高暴毙风险，高潮退潮最先杀后排）")
                fit_score -= 50
            else:
                warnings.append("亢龙加速阶段新开仓，注意随时面临大分歧天地板风险")
                fit_score -= 20
    elif phase == "衰退":
        if "买入" in action or "BUY" in action_upper or "ALERT" in action_upper:
            violations.append("衰退退潮期逆势开仓（严重违规，市场炸板率极高）")
            fit_score -= 60
            if "抄底" in target_desc or "反弹" in target_desc:
                violations.append("退潮期左侧抄底破位股，属于违规接飞刀")
                fit_score -= 20
    elif phase == "潜藏":
        if "买入" in action or "BUY" in action_upper or "ALERT" in action_upper:
            warnings.append("潜藏冰点混沌期轻举妄动，资金容易被轮动电风扇绞杀磨损")
            fit_score -= 30
    elif phase == "初生":
        if "卖出" in action or "SELL" in action_upper:
            if "龙头" in target_desc or "身位" in target_desc:
                warnings.append("初生期过早抛售潜在破局总龙头，未让利润奔跑")
                fit_score -= 15

    fit_score = max(0, min(100, fit_score))
    return {
        "regime": phase,
        "fit_score": fit_score,
        "is_aligned": fit_score >= 70,
        "violations": violations,
        "warnings": warnings,
        "safety": SAFETY_DECLARATION,
    }
