"""The one curated catalog: every project, its upstream, and how to obtain it.

This module replaces the two lists that used to disagree. The old
`plugin_marketplace.official_catalog` carried twenty entries whose "bundle" was
an `official://` URI that resolved to nothing, and `plugins.catalog` carried
eleven real projects; a user saw the union with no way to tell which entries
corresponded to code that could actually be installed.

Every entry here names a real upstream and an install discriminator, so the
interface can show one honest answer per card: where it comes from, how it is
obtained, and what it may never do.

Provenance for each entry was verified against PyPI metadata and the upstream
repository before it was written down. Two entries have no importable Python
distribution and are marked as such rather than given a fabricated one.
"""

from __future__ import annotations

from typing import Any

from smartmoney_cub_harness.plugins.catalog_contract import (
    CATALOG_SCHEMA,
    INSTALL_BUILTIN,
    INSTALL_GIT,
    INSTALL_PYPI,
    LEVEL_ADAPTER,
    LEVEL_COMPANION,
    catalog_entry,
    install_spec,
    manual_install_command,
)
from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

CATEGORY_DATA = "数据"
CATEGORY_PERFORMANCE = "绩效与风险"
CATEGORY_RESEARCH = "研究与评估"
CATEGORY_AGENT = "Agent"
CATEGORY_ORDER = (
    CATEGORY_DATA,
    CATEGORY_PERFORMANCE,
    CATEGORY_RESEARCH,
    CATEGORY_AGENT,
)

# Every data source may only read. The sentence is repeated in the interface and
# in the wizard, so it is written once here and reused.
_READ_ONLY_DATA_BOUNDARY = (
    "只读行情/财务数据，输出仅作为复盘证据；不连接券商、不下单、不改账户。"
)
_READ_ONLY_REPORT_BOUNDARY = (
    "只读计算结果与报表；不产生买卖指令，不写入账户与订单。"
)

CATALOG: tuple[dict[str, Any], ...] = (
    # ---- 数据 -------------------------------------------------------------
    catalog_entry(
        plugin_id="akshare",
        name="AKShare",
        category=CATEGORY_DATA,
        description="A 股公开数据适配器：行情、财务与宏观公开接口。",
        repo="https://github.com/akfamily/akshare",
        install=install_spec(INSTALL_PYPI, package="akshare", module="akshare"),
        license_name="MIT",
        level=LEVEL_ADAPTER,
        capabilities=["market_context"],
        requires_credentials=False,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="tushare-pro",
        credential_mode="managed_local",
        credential_requirements=[{
            "name": "TOKEN", "label": "TuShare token", "required": True,
            "obtain_url": "https://tushare.pro/document/1?doc_id=40",
            "help": "Create a personal token in your TuShare account. Data access depends on your account permissions.",
            "scopes": ["market_data_read"],
        }],
        name="TuShare Pro",
        category=CATEGORY_DATA,
        description="TuShare Pro 历史行情与财务数据，需要官方 token。",
        repo="https://tushare.pro",
        docs_url="https://github.com/waditu/tushare",
        install=install_spec(INSTALL_PYPI, package="tushare", module="tushare"),
        license_name="BSD-3-Clause",
        level=LEVEL_ADAPTER,
        capabilities=["market_context"],
        requires_credentials=True,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="baostock",
        name="BaoStock",
        category=CATEGORY_DATA,
        description="BaoStock 证券历史行情，免注册。上游以官网分发，无 GitHub 仓库。",
        repo="http://www.baostock.com",
        install=install_spec(INSTALL_PYPI, package="baostock", module="baostock"),
        license_name="Apache-2.0",
        level=LEVEL_ADAPTER,
        capabilities=["market_context"],
        requires_credentials=False,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="eastmoney",
        name="东方财富行情",
        category=CATEGORY_DATA,
        description="东方财富公开行情接口的 Python 封装（efinance）。",
        repo="https://github.com/Micro-sheep/efinance",
        install=install_spec(INSTALL_PYPI, package="efinance", module="efinance"),
        license_name="MIT",
        level=LEVEL_ADAPTER,
        capabilities=["market_context"],
        requires_credentials=False,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="yahoo-finance",
        name="Yahoo Finance",
        category=CATEGORY_DATA,
        description="Yahoo Finance 历史行情与基本面（yfinance）。",
        repo="https://github.com/ranaroussi/yfinance",
        install=install_spec(INSTALL_PYPI, package="yfinance", module="yfinance"),
        license_name="Apache-2.0",
        level=LEVEL_ADAPTER,
        capabilities=["market_context"],
        requires_credentials=False,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="stooq",
        name="Stooq 行情",
        category=CATEGORY_DATA,
        description="Stooq 历史行情，通过 pandas-datareader 读取。",
        repo="https://github.com/pydata/pandas-datareader",
        install=install_spec(
            INSTALL_PYPI, package="pandas-datareader", module="pandas_datareader"
        ),
        license_name="BSD-3-Clause",
        level=LEVEL_ADAPTER,
        capabilities=["market_context"],
        requires_credentials=False,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="fred",
        credential_mode="managed_local",
        credential_requirements=[{
            "name": "FRED_API_KEY", "label": "FRED API key", "required": True,
            "obtain_url": "https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html",
            "help": "Request a personal API key from the Federal Reserve Bank of St. Louis.",
            "scopes": ["economic_data_read"],
        }],
        name="FRED 宏观数据",
        category=CATEGORY_DATA,
        description="圣路易斯联储 FRED 宏观时间序列，需要免费 API key。",
        repo="https://github.com/mortada/fredapi",
        install=install_spec(INSTALL_PYPI, package="fredapi", module="fredapi"),
        license_name="Apache-2.0",
        level=LEVEL_ADAPTER,
        capabilities=["market_context"],
        requires_credentials=True,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="tencent-quotes",
        name="腾讯行情快照",
        category=CATEGORY_DATA,
        description=(
            "腾讯证券公开行情接口没有独立维护的 Python 发行版，由 harness 内置的"
            "只读抓取适配器提供，不安装第三方代码。"
        ),
        repo="https://gu.qq.com/",
        install=install_spec(
            INSTALL_BUILTIN, note="由 harness 内置只读适配器提供，无需安装第三方包"
        ),
        license_name="builtin",
        level=LEVEL_ADAPTER,
        capabilities=["market_context"],
        requires_credentials=False,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
    # ---- 绩效与风险 -------------------------------------------------------
    catalog_entry(
        plugin_id="quantstats",
        name="QuantStats",
        category=CATEGORY_PERFORMANCE,
        description="绩效报告与风险统计：收益、回撤、夏普等指标。",
        repo="https://github.com/ranaroussi/quantstats",
        install=install_spec(INSTALL_PYPI, package="quantstats", module="quantstats"),
        license_name="Apache-2.0",
        level=LEVEL_ADAPTER,
        capabilities=["report_renderer", "evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="empyrical-reloaded",
        name="Empyrical Reloaded",
        category=CATEGORY_PERFORMANCE,
        description="收益、回撤与风险指标计算（Quantopian empyrical 维护分支）。",
        repo="https://github.com/stefan-jansen/empyrical-reloaded",
        install=install_spec(
            INSTALL_PYPI, package="empyrical-reloaded", module="empyrical"
        ),
        license_name="Apache-2.0",
        level=LEVEL_ADAPTER,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="pyfolio-reloaded",
        name="Pyfolio Reloaded",
        category=CATEGORY_PERFORMANCE,
        description="组合归因与事件分析报告。",
        repo="https://github.com/stefan-jansen/pyfolio-reloaded",
        install=install_spec(
            INSTALL_PYPI, package="pyfolio-reloaded", module="pyfolio"
        ),
        license_name="Apache-2.0",
        level=LEVEL_ADAPTER,
        capabilities=["report_renderer", "evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="riskfolio-lib",
        name="Riskfolio-Lib",
        category=CATEGORY_PERFORMANCE,
        description="组合风险与约束分析。",
        repo="https://github.com/dcajasn/Riskfolio-Lib",
        install=install_spec(INSTALL_PYPI, package="riskfolio-lib", module="riskfolio"),
        license_name="BSD-3-Clause",
        level=LEVEL_ADAPTER,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="pyportfolioopt",
        name="PyPortfolioOpt",
        category=CATEGORY_PERFORMANCE,
        description="组合优化结果评估：有效前沿与风险模型。",
        repo="https://github.com/pyportfolio/pyportfolioopt",
        install=install_spec(
            INSTALL_PYPI, package="pyportfolioopt", module="pypfopt"
        ),
        license_name="MIT",
        level=LEVEL_ADAPTER,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="skfolio",
        name="skfolio",
        category=CATEGORY_PERFORMANCE,
        description="基于 scikit-learn 的样本外组合风险评估。",
        repo="https://github.com/skfolio/skfolio",
        install=install_spec(INSTALL_PYPI, package="skfolio", module="skfolio"),
        license_name="BSD-3-Clause",
        level=LEVEL_ADAPTER,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    # ---- 研究与评估 -------------------------------------------------------
    catalog_entry(
        plugin_id="pandas-ta-classic",
        name="pandas-ta-classic",
        category=CATEGORY_RESEARCH,
        description="技术指标特征计算（pandas-ta 的持续维护分支）。",
        repo="https://github.com/xgboosted/pandas-ta-classic",
        install=install_spec(
            INSTALL_PYPI, package="pandas-ta-classic", module="pandas_ta_classic"
        ),
        license_name="MIT",
        level=LEVEL_ADAPTER,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="pandas-market-calendars",
        name="pandas-market-calendars",
        category=CATEGORY_RESEARCH,
        description="交易日历与时间语义，用于 available_at 与决策时间的对齐校对。",
        repo="https://github.com/rsheftel/pandas_market_calendars",
        install=install_spec(
            INSTALL_PYPI,
            package="pandas-market-calendars",
            module="pandas_market_calendars",
        ),
        license_name="MIT",
        level=LEVEL_ADAPTER,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="qlib-factor-evaluator",
        name="Qlib 因子评估",
        category=CATEGORY_RESEARCH,
        description=(
            "微软 Qlib（PyPI: pyqlib）的因子研究与 point-in-time 评估。仓库分发为主，"
            "安装后由 harness 以只读方式调用。"
        ),
        repo="https://github.com/microsoft/qlib",
        install=install_spec(INSTALL_PYPI, package="pyqlib", module="qlib"),
        license_name="MIT",
        level=LEVEL_COMPANION,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="vectorbt-evidence",
        name="vectorbt 证据检查",
        category=CATEGORY_RESEARCH,
        description="回测证据与未来数据检查。",
        repo="https://github.com/polakowo/vectorbt",
        install=install_spec(INSTALL_PYPI, package="vectorbt", module="vectorbt"),
        license_name="Apache-2.0",
        level=LEVEL_ADAPTER,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="backtesting-py",
        name="backtesting.py",
        category=CATEGORY_RESEARCH,
        description="轻量回测框架，用于策略原型的样本外检查。",
        repo="https://github.com/kernc/backtesting.py",
        install=install_spec(INSTALL_PYPI, package="backtesting", module="backtesting"),
        license_name="AGPL-3.0",
        level=LEVEL_COMPANION,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="backtrader",
        name="Backtrader",
        category=CATEGORY_RESEARCH,
        description="经典回测框架，用于历史策略复盘。",
        repo="https://github.com/mementum/backtrader",
        install=install_spec(INSTALL_PYPI, package="backtrader", module="backtrader"),
        license_name="GPL-3.0",
        level=LEVEL_COMPANION,
        capabilities=["evaluator"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary=_READ_ONLY_REPORT_BOUNDARY,
    ),
    catalog_entry(
        plugin_id="zvt",
        name="ZVT",
        category=CATEGORY_RESEARCH,
        description="本地量化数据与选股框架，仅作为只读数据与因子来源。",
        repo="https://github.com/zvtvz/zvt",
        install=install_spec(INSTALL_PYPI, package="zvt", module="zvt"),
        license_name="MIT",
        level=LEVEL_COMPANION,
        capabilities=["market_context", "evaluator"],
        requires_credentials=False,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
    # ---- Agent ------------------------------------------------------------
    catalog_entry(
        plugin_id="multi-agent-trade-review",
        name="多 Agent 复盘",
        category=CATEGORY_AGENT,
        description=(
            "由 harness 内置的 reviewer/challenger 协作链提供，无需安装第三方包。"
        ),
        repo="builtin://smartmoney-cub/multi-agent-review",
        install=install_spec(INSTALL_BUILTIN, note="harness 内置的复盘协作链"),
        license_name="builtin",
        level=LEVEL_ADAPTER,
        capabilities=["reviewer", "challenger"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary="只生成 challenger 候选与复盘观察；champion 变更必须人工确认。",
    ),
    catalog_entry(
        plugin_id="challenger-rule-critic",
        name="反方规则质询",
        category=CATEGORY_AGENT,
        description="由 harness 内置的 challenger 规则质询能力提供。",
        repo="builtin://smartmoney-cub/challenger-critic",
        install=install_spec(INSTALL_BUILTIN, note="harness 内置的 challenger 质询"),
        license_name="builtin",
        level=LEVEL_ADAPTER,
        capabilities=["challenger"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary="只提出候选与反例；不自动晋级 champion，不改写规则库。",
    ),
    catalog_entry(
        plugin_id="tradingagents",
        credential_mode="external_only",
        credential_setup_url="https://github.com/TauricResearch/TradingAgents#installation-and-setup",
        name="TradingAgents",
        category=CATEGORY_AGENT,
        description=(
            "多智能体交易分析框架。用户自行运行生成报告后导入为只读复盘材料；"
            "harness 不代管其 LLM 密钥。"
        ),
        repo="https://github.com/TauricResearch/TradingAgents",
        docs_url="docs/tradingagents-adapter.md",
        install=install_spec(
            INSTALL_GIT,
            repo="https://github.com/TauricResearch/TradingAgents",
            module="tradingagents",
        ),
        license_name="Apache-2.0",
        level=LEVEL_COMPANION,
        capabilities=["reviewer", "agent_bridge"],
        requires_credentials=True,
        network_required=True,
        execution_risk="medium",
        boundary=(
            "用户自备 LLM/API key 并在本仓库之外配置；harness 不保存、不收集、不上传密钥；"
            "其输出只能作为复盘证据，不得转成订单意图或执行计划。"
        ),
    ),
    catalog_entry(
        plugin_id="uzi-skill",
        name="UZI-Skill",
        category=CATEGORY_AGENT,
        description="外部分析技能与叙述灵感，输出可本地保存后进入 reviewer/challenger 流程。",
        repo="https://github.com/wbh604/UZI-Skill",
        install=install_spec(
            INSTALL_GIT, repo="https://github.com/wbh604/UZI-Skill", module="uzi_skill"
        ),
        license_name="unverified",
        level=LEVEL_COMPANION,
        capabilities=["reviewer"],
        requires_credentials=False,
        network_required=False,
        execution_risk="low",
        boundary="只能描述为推荐搭配与生态接入位；不得称为内置依赖，不得把结论变成买卖指令。",
    ),
    catalog_entry(
        plugin_id="tick-stock-panel",
        name="tick-stock-panel",
        category=CATEGORY_AGENT,
        description="Tick 级行情面板项目，作为只读行情可视化参考实现。",
        repo="https://github.com/shy3130/tick-stock-panel",
        install=install_spec(
            INSTALL_GIT,
            repo="https://github.com/shy3130/tick-stock-panel",
            module="tick_stock_panel",
        ),
        license_name="unverified",
        level=LEVEL_COMPANION,
        capabilities=["market_context"],
        requires_credentials=False,
        network_required=True,
        execution_risk="low",
        boundary=_READ_ONLY_DATA_BOUNDARY,
    ),
)


def catalog_entries() -> list[dict[str, Any]]:
    """Every curated entry, with the command a user can run by hand."""
    entries: list[dict[str, Any]] = []
    for entry in CATALOG:
        item = dict(entry)
        item["manual_command"] = manual_install_command(entry)
        entries.append(item)
    return entries


def catalog_index() -> dict[str, dict[str, Any]]:
    """Entries keyed by plugin id, for the installer's whitelist lookup."""
    return {
        str(entry["plugin_id"]): {**entry, "manual_command": manual_install_command(entry)}
        for entry in CATALOG
    }


def catalog_payload() -> dict[str, Any]:
    """The catalog as the interface consumes it, grouped by category."""
    entries = catalog_entries()
    by_category: dict[str, list[dict[str, Any]]] = {name: [] for name in CATEGORY_ORDER}
    for entry in entries:
        by_category.setdefault(str(entry["category"]), []).append(entry)
    return {
        "schema": CATALOG_SCHEMA,
        "categories": list(CATEGORY_ORDER),
        "entries": entries,
        "by_category": by_category,
        "counts": {
            "total": len(entries),
            "by_category": {name: len(items) for name, items in by_category.items()},
            "by_install_kind": {
                kind: sum(1 for entry in entries if entry["install"]["kind"] == kind)
                for kind in ("pypi", "git", "builtin")
            },
        },
        "policy": (
            "目录只描述上游来源与安装方式。安装由用户在工作台逐项确认后触发，"
            "非静默、非后台；高风险项目（自带下单能力）永不安装。"
        ),
        "safety": SAFETY_DECLARATION,
    }
