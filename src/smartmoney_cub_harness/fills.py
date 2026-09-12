from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION

FILL_LEDGER_SCHEMA = "smartmoney_cub_fill_ledger.v1"

COST_BASIS_FIFO = "fifo"

# Documented A-share defaults used only when a fill does not declare its own fees.
# They are conservative estimates for review bookkeeping, not tax advice.
DEFAULT_FEE_POLICY: dict[str, Any] = {
    "commission_rate": 0.00025,
    "commission_min": 5.0,
    "stamp_duty_rate": 0.0005,
    "stamp_duty_side": "SELL",
    "transfer_fee_rate": 0.00001,
    "basis": "documented_a_share_estimate",
}

BUY_KEYWORDS = ("买入", "买", "担保品买入", "融资买入")
SELL_KEYWORDS = ("卖出", "卖", "担保品卖出", "融券卖出")
NON_TRADE_KEYWORDS = (
    "银行转证券",
    "证券转银行",
    "利息",
    "红利",
    "股息",
    "派息",
    "申购",
    "中签",
    "配号",
    "转托管",
)

ERROR_CODES = {
    "missing_symbol",
    "invalid_price",
    "invalid_quantity",
    "zero_quantity",
    "unknown_side",
    "duplicate_fill",
    "t_plus_one_violation",
    "sell_without_position",
    "oversell",
}

WARNING_CODES = {
    "non_trade_row",
    "cost_basis_assumed_fifo",
    "fees_estimated",
    "unpaired_buy",
    "limit_board_fill",
    "suspended_or_no_trade",
}


@dataclass
class Fill:
    fill_id: str
    symbol: str
    name: str
    side: str
    trade_date: str
    trade_time: str
    price: float
    quantity: int
    commission: float | None = None
    stamp_duty: float | None = None
    transfer_fee: float | None = None
    invalidation_price: float | None = None
    thesis: str = ""
    regime: str = ""
    tags: list[str] = field(default_factory=list)
    source_row: int = 0
    explicit_fill_id: bool = False

    @property
    def datetime_text(self) -> str:
        return f"{self.trade_date} {self.trade_time}".strip()


@dataclass
class _Lot:
    fill_id: str
    symbol: str
    name: str
    trade_date: str
    entry_time: str
    price: float
    quantity: int
    remaining: int
    buy_fee_per_share: float
    invalidation_price: float | None
    thesis: str
    regime: str
    tags: list[str]


def _first_present(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _split_datetime(raw: dict[str, Any]) -> tuple[str, str]:
    combined = _first_present(raw, "datetime", "成交时间", "trade_datetime")
    date_text = _first_present(raw, "trade_date", "date", "成交日期", "发生日期")
    time_text = _first_present(raw, "trade_time", "time", "委托时间")

    if combined and not date_text:
        text = str(combined).strip()
        parts = text.split(" ", 1)
        date_text = parts[0]
        if len(parts) > 1 and not time_text:
            time_text = parts[1]

    date_str = str(date_text).strip() if date_text else ""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            date_str = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
            break
        except ValueError:
            continue

    time_str = str(time_text).strip() if time_text else "09:30:00"
    return date_str, time_str


def _classify_side(action: Any) -> str | None:
    if action is None:
        return None
    text = str(action).strip()
    lowered = text.lower()
    if lowered in {"buy", "b"}:
        return "BUY"
    if lowered in {"sell", "s"}:
        return "SELL"
    for keyword in NON_TRADE_KEYWORDS:
        if keyword in text:
            return None
    for keyword in BUY_KEYWORDS:
        if keyword in text:
            return "BUY"
    for keyword in SELL_KEYWORDS:
        if keyword in text:
            return "SELL"
    return None


def _is_non_trade(action: Any) -> bool:
    if action is None:
        return False
    text = str(action)
    return any(keyword in text for keyword in NON_TRADE_KEYWORDS)


def _has_limit_marker(raw: dict[str, Any]) -> bool:
    haystack = " ".join(str(value) for value in raw.values() if isinstance(value, (str, int, float)))
    return any(marker in haystack for marker in ("涨停", "跌停", "一字"))


def _has_suspension_marker(raw: dict[str, Any]) -> bool:
    haystack = " ".join(str(value) for value in raw.values() if isinstance(value, (str, int, float)))
    return "停牌" in haystack


def estimate_fees(side: str, price: float, quantity: int, policy: dict[str, Any]) -> dict[str, float]:
    amount = price * quantity
    commission = max(amount * float(policy["commission_rate"]), float(policy["commission_min"]))
    stamp_duty = amount * float(policy["stamp_duty_rate"]) if side == policy["stamp_duty_side"] else 0.0
    transfer_fee = amount * float(policy["transfer_fee_rate"])
    return {
        "commission": round(commission, 2),
        "stamp_duty": round(stamp_duty, 2),
        "transfer_fee": round(transfer_fee, 2),
    }


def _fill_total_fee(fill: Fill, policy: dict[str, Any]) -> tuple[float, bool]:
    declared = [fill.commission, fill.stamp_duty, fill.transfer_fee]
    if any(value is not None for value in declared):
        total = sum(value for value in declared if value is not None)
        return round(total, 4), False
    estimated = estimate_fees(fill.side, fill.price, fill.quantity, policy)
    total = sum(estimated.values())
    return round(total, 4), True


def _coerce_fill(raw: dict[str, Any], index: int, issues: list[dict[str, Any]]) -> Fill | None:
    action = _first_present(raw, "action", "side", "操作", "买卖标志", "业务名称")
    if _is_non_trade(action):
        issues.append(
            {
                "code": "non_trade_row",
                "severity": "warning",
                "symbol": "",
                "fill_id": f"row-{index}",
                "detail": f"skipped non-trade row: {action}",
            }
        )
        return None

    side = _classify_side(action)
    symbol_raw = _first_present(raw, "symbol", "code", "证券代码", "代码")
    symbol = str(symbol_raw).strip() if symbol_raw is not None else ""
    declared_fill_id = _first_present(raw, "fill_id", "成交编号", "合同编号")
    fill_id = str(declared_fill_id or f"row-{index}")

    if side is None:
        issues.append(
            {
                "code": "unknown_side",
                "severity": "error",
                "symbol": symbol,
                "fill_id": fill_id,
                "detail": f"cannot classify trade side from {action!r}",
            }
        )
        return None

    if not symbol:
        issues.append(
            {
                "code": "missing_symbol",
                "severity": "error",
                "symbol": "",
                "fill_id": fill_id,
                "detail": "fill row has no security code",
            }
        )
        return None

    price = _to_float(_first_present(raw, "price", "成交均价", "成交价格", "价格"))
    quantity_raw = _first_present(raw, "quantity", "volume", "成交数量", "数量")
    quantity_value = _to_float(quantity_raw)
    quantity = int(abs(quantity_value)) if quantity_value is not None else 0

    if quantity == 0:
        issues.append(
            {
                "code": "zero_quantity",
                "severity": "error",
                "symbol": symbol,
                "fill_id": fill_id,
                "detail": "fill quantity is zero; a suspended or cancelled row cannot become a trade",
            }
        )
        return None
    if price is None or price <= 0:
        issues.append(
            {
                "code": "invalid_price",
                "severity": "error",
                "symbol": symbol,
                "fill_id": fill_id,
                "detail": f"fill price is not a positive number: {price!r}",
            }
        )
        return None

    trade_date, trade_time = _split_datetime(raw)
    if not trade_date:
        issues.append(
            {
                "code": "invalid_quantity",
                "severity": "error",
                "symbol": symbol,
                "fill_id": fill_id,
                "detail": "fill row has no usable trade date",
            }
        )
        return None

    name = str(_first_present(raw, "name", "证券名称", "名称") or symbol).strip()
    invalidation = _to_float(_first_present(raw, "invalidation_price", "止损价"))
    thesis = str(_first_present(raw, "thesis", "买入理由") or "")
    regime = str(_first_present(raw, "regime", "情绪周期") or "")
    tags = _first_present(raw, "tags")

    fill = Fill(
        fill_id=fill_id,
        symbol=symbol,
        name=name,
        side=side,
        trade_date=trade_date,
        trade_time=trade_time,
        price=float(price),
        quantity=quantity,
        commission=_to_float(_first_present(raw, "commission", "佣金")),
        stamp_duty=_to_float(_first_present(raw, "stamp_duty", "印花税")),
        transfer_fee=_to_float(_first_present(raw, "transfer_fee", "过户费")),
        invalidation_price=invalidation,
        thesis=thesis,
        regime=regime,
        tags=list(tags) if isinstance(tags, list) else [],
        source_row=index,
        explicit_fill_id=declared_fill_id is not None,
    )

    if _has_suspension_marker(raw):
        issues.append(
            {
                "code": "suspended_or_no_trade",
                "severity": "warning",
                "symbol": symbol,
                "fill_id": fill_id,
                "detail": "fill row carries a suspension marker; verify it is a real execution",
            }
        )
    if _has_limit_marker(raw):
        issues.append(
            {
                "code": "limit_board_fill",
                "severity": "warning",
                "symbol": symbol,
                "fill_id": fill_id,
                "detail": "fill row carries a limit-up or limit-down marker; board fills are not guaranteed",
            }
        )
    return fill


def _dedupe_fills(fills: list[Fill], issues: list[dict[str, Any]]) -> list[Fill]:
    seen: set[tuple[Any, ...]] = set()
    kept: list[Fill] = []
    for fill in fills:
        # Duplicate detection uses the economic identity of the fill. An
        # auto-generated row id must not make two identical rows look distinct.
        key = (
            fill.symbol,
            fill.side,
            fill.trade_date,
            fill.trade_time,
            fill.price,
            fill.quantity,
            fill.fill_id if fill.explicit_fill_id else None,
        )
        if key in seen:
            issues.append(
                {
                    "code": "duplicate_fill",
                    "severity": "error",
                    "symbol": fill.symbol,
                    "fill_id": fill.fill_id,
                    "detail": "identical fill row already recorded; refusing to double count",
                }
            )
            continue
        seen.add(key)
        kept.append(fill)
    return kept


def _allocate(fee: float, matched: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return fee * matched / total


def build_fill_ledger(
    records: Iterable[dict[str, Any]],
    *,
    cost_basis: str = COST_BASIS_FIFO,
    fee_policy: dict[str, Any] | None = None,
    market: str = "CN-A",
) -> dict[str, Any]:
    """Normalize raw fills into a reviewable position ledger.

    Ambiguity never becomes a silent trade: blocking conditions are reported as
    error-severity issues and drive the ledger status to needs_review.
    """
    policy = dict(DEFAULT_FEE_POLICY)
    if fee_policy:
        policy.update(fee_policy)

    issues: list[dict[str, Any]] = []
    fills: list[Fill] = []
    for index, raw in enumerate(records, start=1):
        if not isinstance(raw, dict):
            issues.append(
                {
                    "code": "invalid_quantity",
                    "severity": "error",
                    "symbol": "",
                    "fill_id": f"row-{index}",
                    "detail": "record is not a mapping",
                }
            )
            continue
        fill = _coerce_fill(raw, index, issues)
        if fill is not None:
            fills.append(fill)

    fills = _dedupe_fills(fills, issues)
    fills.sort(key=lambda item: (item.trade_date, item.trade_time, item.source_row))

    open_lots: dict[str, list[_Lot]] = {}
    round_trips: list[dict[str, Any]] = []
    estimated_fee_symbols: set[str] = set()
    fifo_symbols: set[str] = set()

    for fill in fills:
        total_fee, estimated = _fill_total_fee(fill, policy)
        if estimated:
            estimated_fee_symbols.add(fill.symbol)

        if fill.side == "BUY":
            lot = _Lot(
                fill_id=fill.fill_id,
                symbol=fill.symbol,
                name=fill.name,
                trade_date=fill.trade_date,
                entry_time=fill.datetime_text,
                price=fill.price,
                quantity=fill.quantity,
                remaining=fill.quantity,
                buy_fee_per_share=round(total_fee / fill.quantity, 6),
                invalidation_price=fill.invalidation_price,
                thesis=fill.thesis,
                regime=fill.regime,
                tags=list(fill.tags),
            )
            open_lots.setdefault(fill.symbol, []).append(lot)
            continue

        lots = open_lots.get(fill.symbol, [])
        sellable = [lot for lot in lots if lot.remaining > 0 and lot.trade_date < fill.trade_date]
        blocked_same_day = [lot for lot in lots if lot.remaining > 0 and lot.trade_date >= fill.trade_date]

        if cost_basis != COST_BASIS_FIFO:
            issues.append(
                {
                    "code": "cost_basis_assumed_fifo",
                    "severity": "warning",
                    "symbol": fill.symbol,
                    "fill_id": fill.fill_id,
                    "detail": f"cost basis {cost_basis!r} is not implemented; fell back to fifo",
                }
            )
            fifo_symbols.add(fill.symbol)

        if not sellable:
            code = "t_plus_one_violation" if blocked_same_day else "sell_without_position"
            issues.append(
                {
                    "code": code,
                    "severity": "error",
                    "symbol": fill.symbol,
                    "fill_id": fill.fill_id,
                    "detail": (
                        "sell exceeds shares that are sellable under T+1"
                        if blocked_same_day
                        else "sell has no prior recorded position; cost basis is unknown"
                    ),
                }
            )
            continue

        if len(sellable) > 1:
            fifo_symbols.add(fill.symbol)

        remaining_to_sell = fill.quantity
        matches: list[dict[str, Any]] = []
        first_lot: _Lot | None = None
        for lot in sellable:
            if remaining_to_sell <= 0:
                break
            matched = min(lot.remaining, remaining_to_sell)
            lot.remaining -= matched
            remaining_to_sell -= matched
            if first_lot is None:
                first_lot = lot
            matches.append(
                {
                    "lot_fill_id": lot.fill_id,
                    "entry_time": lot.entry_time,
                    "entry_price": lot.price,
                    "quantity": matched,
                    "buy_fee": round(_allocate(lot.buy_fee_per_share * lot.quantity, matched, lot.quantity), 4),
                }
            )

        if remaining_to_sell > 0:
            issues.append(
                {
                    "code": "oversell",
                    "severity": "error",
                    "symbol": fill.symbol,
                    "fill_id": fill.fill_id,
                    "detail": f"sell exceeds recorded sellable position by {remaining_to_sell} shares",
                }
            )

        matched_quantity = fill.quantity - remaining_to_sell
        if matched_quantity <= 0:
            continue

        sell_fee = _allocate(total_fee, matched_quantity, fill.quantity)
        cost = sum(match["entry_price"] * match["quantity"] for match in matches)
        buy_fee = sum(match["buy_fee"] for match in matches)
        proceeds = fill.price * matched_quantity
        gross_pnl = proceeds - cost
        fees = buy_fee + sell_fee
        net_pnl = gross_pnl - fees
        entry_time = matches[0]["entry_time"]
        entry_date = entry_time.split(" ")[0]
        try:
            holding_days = (
                datetime.strptime(fill.trade_date, "%Y-%m-%d") - datetime.strptime(entry_date, "%Y-%m-%d")
            ).days
        except ValueError:
            holding_days = 0

        round_trips.append(
            {
                "round_trip_id": f"RT-{fill.symbol}-{len(round_trips) + 1}",
                "symbol": fill.symbol,
                "name": fill.name or (first_lot.name if first_lot else ""),
                "regime": fill.regime or (first_lot.regime if first_lot else ""),
                "thesis": fill.thesis or (first_lot.thesis if first_lot else ""),
                "tags": list(fill.tags) or (list(first_lot.tags) if first_lot else []),
                "invalidation_price": (
                    fill.invalidation_price if fill.invalidation_price is not None else
                    (first_lot.invalidation_price if first_lot else None)
                ),
                "entry_time": entry_time,
                "entry_price": round(cost / matched_quantity, 4),
                "exit_time": fill.datetime_text,
                "exit_price": fill.price,
                "quantity": matched_quantity,
                "cost_basis": cost_basis,
                "gross_pnl": round(gross_pnl, 2),
                "fees": round(fees, 2),
                "net_pnl": round(net_pnl, 2),
                "return_pct": round(net_pnl / (cost + buy_fee) * 100, 2) if (cost + buy_fee) > 0 else 0.0,
                "holding_days": holding_days,
                "matched_lots": matches,
                "exit_complete": remaining_to_sell == 0,
                "cost_basis_assumed": len(matches) > 1,
            }
        )

    open_positions: list[dict[str, Any]] = []
    for symbol, lots in sorted(open_lots.items()):
        active = [lot for lot in lots if lot.remaining > 0]
        if not active:
            continue
        quantity = sum(lot.remaining for lot in active)
        cost = sum(lot.price * lot.remaining for lot in active)
        open_positions.append(
            {
                "position_id": f"POS-{symbol}",
                "symbol": symbol,
                "name": active[0].name,
                "quantity": quantity,
                "avg_cost": round(cost / quantity, 4) if quantity else 0.0,
                "opened_at": active[0].entry_time,
                "lots": [
                    {
                        "fill_id": lot.fill_id,
                        "trade_date": lot.trade_date,
                        "price": lot.price,
                        "remaining": lot.remaining,
                    }
                    for lot in active
                ],
                "status": "open",
            }
        )
        issues.append(
            {
                "code": "unpaired_buy",
                "severity": "warning",
                "symbol": symbol,
                "fill_id": active[0].fill_id,
                "detail": f"{quantity} shares remain open and were not paired into a round trip",
            }
        )

    for symbol in sorted(fifo_symbols):
        issues.append(
            {
                "code": "cost_basis_assumed_fifo",
                "severity": "warning",
                "symbol": symbol,
                "fill_id": "",
                "detail": "multiple open lots matched first-in-first-out; verify lot attribution",
            }
        )
    for symbol in sorted(estimated_fee_symbols):
        issues.append(
            {
                "code": "fees_estimated",
                "severity": "warning",
                "symbol": symbol,
                "fill_id": "",
                "detail": "fees were not declared; documented default estimate was applied",
            }
        )

    seen_issue_keys: set[tuple[Any, ...]] = set()
    deduped_issues: list[dict[str, Any]] = []
    for issue in issues:
        key = (issue["code"], issue["symbol"], issue["fill_id"])
        if key in seen_issue_keys:
            continue
        seen_issue_keys.add(key)
        deduped_issues.append(issue)

    blocking = [issue for issue in deduped_issues if issue["severity"] == "error"]
    return {
        "schema": FILL_LEDGER_SCHEMA,
        "market": market,
        "cost_basis": cost_basis,
        "fee_policy": policy,
        "fills": [
            {
                "fill_id": fill.fill_id,
                "symbol": fill.symbol,
                "name": fill.name,
                "side": fill.side,
                "trade_date": fill.trade_date,
                "trade_time": fill.trade_time,
                "price": fill.price,
                "quantity": fill.quantity,
            }
            for fill in fills
        ],
        "round_trips": round_trips,
        "open_positions": open_positions,
        "issues": deduped_issues,
        "status": "needs_review" if blocking else "ok",
        "counts": {
            "fills": len(fills),
            "round_trips": len(round_trips),
            "open_positions": len(open_positions),
            "errors": len(blocking),
            "warnings": len(deduped_issues) - len(blocking),
        },
        "safety": SAFETY_DECLARATION,
    }


def ledger_to_analysis_trades(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Project closed round trips into the trade view consumed by the review report."""
    trades: list[dict[str, Any]] = []
    for trip in ledger.get("round_trips", []):
        trades.append(
            {
                "trade_id": trip["round_trip_id"],
                "symbol": trip["symbol"],
                "name": trip.get("name") or trip["symbol"],
                "regime": trip.get("regime") or "生长",
                "thesis": trip.get("thesis") or "CSV import: no entry thesis recorded",
                "invalidation_price": trip.get("invalidation_price"),
                "entry_time": trip["entry_time"],
                "entry_price": trip["entry_price"],
                "exit_time": trip["exit_time"],
                "exit_price": trip["exit_price"],
                "volume": trip["quantity"],
                "fees": trip.get("fees", 0.0),
                "net_pnl": trip.get("net_pnl", 0.0),
                "holding_days": trip.get("holding_days", 0),
                "cost_basis_assumed": trip.get("cost_basis_assumed", False),
                "max_adverse_excursion_pct": 0.0,
                "tags": list(trip.get("tags") or []),
            }
        )
    return trades
