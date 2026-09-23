from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
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
    "fees_unknown",
    "unpaired_buy",
    "limit_board_fill",
    "suspended_or_no_trade",
    "ambiguous_execution_time",
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
    quantity: float
    currency: str = ""
    multiplier: float = 1.0
    time_precision: str = "unknown"
    market: str = "UNKNOWN"
    timezone: str = "unknown"
    account_id: str = ""
    instrument_id: str = ""
    position_effect: str = "AUTO"
    commission: float | None = None
    stamp_duty: float | None = None
    transfer_fee: float | None = None
    invalidation_price: float | None = None
    thesis: str = ""
    regime: str = ""
    tags: list[str] = field(default_factory=list)
    source_row: int = 0
    explicit_fill_id: bool = False
    price_decimal: Decimal = Decimal("0")
    quantity_decimal: Decimal = Decimal("0")
    multiplier_decimal: Decimal = Decimal("1")
    fee_decimal: Decimal | None = None
    fee_precision_missing: bool = False
    fee_known: bool = False

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
    quantity: float
    remaining: float
    buy_fee_per_share: float
    invalidation_price: float | None
    thesis: str
    regime: str
    tags: list[str]
    account_id: str = ""
    instrument_id: str = ""
    currency: str = ""
    multiplier: float = 1.0
    direction: str = "LONG"
    fees_known: bool = True
    price_decimal: Decimal = Decimal("0")
    quantity_decimal: Decimal = Decimal("0")
    remaining_decimal: Decimal = Decimal("0")
    fee_remaining_decimal: Decimal = Decimal("0")
    fee_known: bool = False
    multiplier_decimal: Decimal = Decimal("1")


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


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _decimal_float(value: Decimal) -> float:
    return float(value)


def _raw_decimal(raw: dict[str, Any], *keys: str) -> Decimal | None:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return _to_decimal(raw[key])
    return None


def _raw_present(raw: dict[str, Any], *keys: str) -> bool:
    return any(key in raw and raw[key] not in (None, "") for key in keys)


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

    time_str = str(time_text).strip() if time_text else ""
    return date_str, time_str


def _execution_sort_key(fill: Fill) -> tuple[int, str, int]:
    """Sort aware timestamps by instant; retain deterministic fallback for naive rows."""
    text = f"{fill.trade_date}T{fill.trade_time.replace('Z', '+00:00')}"
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            return (0, parsed.astimezone(timezone.utc).isoformat(), fill.source_row)
    except ValueError:
        pass
    try:
        parsed = datetime.strptime(fill.datetime_text, "%Y-%m-%d %H:%M:%S")
        return (1, parsed.isoformat(), fill.source_row)
    except ValueError:
        return (2, fill.datetime_text, fill.source_row)


def _classify_side(action: Any) -> str | None:
    if action is None:
        return None
    text = str(action).strip()
    lowered = text.lower()
    if lowered in {"buy", "b", "buy_open", "buy_close"}:
        return "BUY"
    if lowered in {"sell", "s", "sell_open", "sell_close"}:
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


def estimate_fees(side: str, price: float, quantity: float, policy: dict[str, Any], *, multiplier: float = 1.0) -> dict[str, float]:
    amount = price * quantity * multiplier
    commission = max(amount * float(policy["commission_rate"]), float(policy["commission_min"]))
    stamp_duty = amount * float(policy["stamp_duty_rate"]) if side == policy["stamp_duty_side"] else 0.0
    transfer_fee = amount * float(policy["transfer_fee_rate"])
    return {
        "commission": round(commission, 2),
        "stamp_duty": round(stamp_duty, 2),
        "transfer_fee": round(transfer_fee, 2),
    }


def _fill_total_fee(fill: Fill, policy: dict[str, Any]) -> tuple[Decimal, bool]:
    declared = [fill.commission, fill.stamp_duty, fill.transfer_fee]
    if fill.fee_known:
        total = fill.fee_decimal if fill.fee_decimal is not None else Decimal("0")
        if fill.stamp_duty is not None and fill.fee_decimal is None:
            total += Decimal(str(fill.stamp_duty))
        if fill.transfer_fee is not None and fill.fee_decimal is None:
            total += Decimal(str(fill.transfer_fee))
        return total, False
    if fill.market != "CN-A":
        # Zero is only the accounted fee amount; fees_known and an issue
        # explicitly distinguish an absent fee from a declared zero fee.
        return Decimal("0"), False
    estimated = estimate_fees(fill.side, fill.price, fill.quantity, policy, multiplier=fill.multiplier)
    total = sum((Decimal(str(value)) for value in estimated.values()), Decimal("0"))
    return total, True


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

    price_decimal = _raw_decimal(raw, "price_exact", "price", "成交均价", "成交价格", "价格")
    price = _to_float(price_decimal)
    quantity_raw = _first_present(raw, "quantity", "volume", "成交数量", "数量")
    quantity_decimal = _raw_decimal(raw, "quantity_exact", "quantity", "volume", "成交数量", "数量")
    quantity_value = _to_float(quantity_decimal)
    quantity = abs(quantity_value) if quantity_value is not None else 0.0
    if quantity_decimal is not None:
        quantity_decimal = abs(quantity_decimal)
    if price_decimal is not None:
        price_decimal = abs(price_decimal)

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

    raw_precision = str(_first_present(raw, "time_precision", "source_precision", "timestamp_precision") or "")
    if not raw_precision:
        raw_precision = "time" if _first_present(raw, "trade_time", "time", "委托时间") else "date"
    multiplier_decimal = _raw_decimal(raw, "multiplier_exact", "multiplier", "contract_multiplier") or Decimal("1")
    multiplier = _to_float(multiplier_decimal) or 0.0
    if multiplier <= 0:
        issues.append({"code": "invalid_quantity", "severity": "error", "symbol": symbol, "fill_id": fill_id, "detail": "multiplier must be positive"})
        return None
    action_token = str(action or "").strip().upper()
    inferred_effect = {
        "BUY_OPEN": "OPEN",
        "SELL_OPEN": "OPEN",
        "BUY_CLOSE": "CLOSE",
        "SELL_CLOSE": "CLOSE",
    }.get(action_token, "AUTO")
    fill = Fill(
        fill_id=fill_id,
        symbol=symbol,
        name=name,
        side=side,
        trade_date=trade_date,
        trade_time=trade_time,
        price=float(price),
        quantity=float(quantity),
        price_decimal=price_decimal or Decimal(str(price)),
        quantity_decimal=quantity_decimal or Decimal(str(quantity)),
        multiplier_decimal=multiplier_decimal,
        currency=str(_first_present(raw, "currency", "quote_currency", "币种") or "").strip(),
        multiplier=multiplier,
        time_precision=raw_precision,
        market=str(raw.get("market") or "UNKNOWN"),
        timezone=str(raw.get("timezone") or "unknown"),
        account_id=str(_first_present(raw, "account_id", "account", "账户") or "").strip(),
        instrument_id=str(_first_present(raw, "instrument_id", "contract_id", "合约代码") or symbol).strip(),
        position_effect=str(_first_present(raw, "position_effect", "offset", "open_close") or inferred_effect).upper(),
        # A broker export usually declares one combined fee column rather than
        # separate commission, stamp duty, and transfer fee columns.
        commission=_to_float(_first_present(raw, "commission", "佣金", "手续费", "费用", "fee", "费用合计")),
        stamp_duty=_to_float(_first_present(raw, "stamp_duty", "印花税")),
        transfer_fee=_to_float(_first_present(raw, "transfer_fee", "过户费")),
        invalidation_price=invalidation,
        thesis=thesis,
        regime=regime,
        tags=list(tags) if isinstance(tags, list) else [],
        source_row=index,
        explicit_fill_id=declared_fill_id is not None,
        fee_decimal=_raw_decimal(raw, "fee_exact", "commission_exact", "commission", "佣金", "手续费", "费用", "fee", "费用合计"),
        fee_known=(
            _raw_present(raw, "fee_exact", "commission_exact", "commission", "佣金", "手续费", "费用", "费用合计", "stamp_duty", "transfer_fee")
            or (_first_present(raw, "fee") not in (None, "", 0, 0.0, "0", "0.0"))
        ),
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
            fill.account_id,
            fill.symbol,
            fill.instrument_id or fill.symbol,
            fill.currency,
            fill.side,
            fill.position_effect,
            fill.trade_date,
            fill.trade_time,
            fill.price,
            fill.quantity,
            fill.multiplier,
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


def _allocate(fee: float, matched: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return fee * matched / total


def _allocate_decimal(fee: Decimal, matched: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal("0")
    return fee * matched / total


def build_fill_ledger(
    records: Iterable[dict[str, Any]],
    *,
    cost_basis: str = COST_BASIS_FIFO,
    fee_policy: dict[str, Any] | None = None,
    market: str = "UNKNOWN",
    market_policy: str | None = None,
    allow_shorts: bool = False,
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
        fill = _coerce_fill({"market": market, **raw}, index, issues)
        if fill is not None:
            fill.market = fill.market.strip().upper()
            fills.append(fill)

    fills = _dedupe_fills(fills, issues)
    fills.sort(key=_execution_sort_key)

    open_lots: dict[tuple[str, str, str], list[_Lot]] = {}
    round_trips: list[dict[str, Any]] = []
    estimated_fee_symbols: set[str] = set()
    fifo_symbols: set[str] = set()

    for fill in fills:
        scope = (fill.account_id, fill.instrument_id or fill.symbol, fill.currency)
        total_fee, estimated = _fill_total_fee(fill, policy)
        fees_known = fill.fee_known or estimated
        if not fees_known:
            issues.append({"code": "fees_unknown", "severity": "warning", "symbol": fill.symbol,
                           "fill_id": fill.fill_id, "account_id": fill.account_id,
                           "detail": "Fees were not declared; no market fee schedule was assumed. PnL excludes unknown fees."})
        if estimated:
            estimated_fee_symbols.add(fill.symbol)

        is_short_open = fill.side == "SELL" and fill.position_effect == "OPEN"
        is_short_close = fill.side == "BUY" and fill.position_effect == "CLOSE"
        if fill.side == "BUY" and not is_short_close:
            lot = _Lot(
                fill_id=fill.fill_id,
                symbol=fill.symbol,
                name=fill.name,
                trade_date=fill.trade_date,
                entry_time=fill.datetime_text,
                price=fill.price,
                quantity=fill.quantity,
                remaining=fill.quantity,
                buy_fee_per_share=float(total_fee / fill.quantity_decimal),
                invalidation_price=fill.invalidation_price,
                thesis=fill.thesis,
                regime=fill.regime,
                tags=list(fill.tags),
                fees_known=fees_known,
                price_decimal=fill.price_decimal,
                quantity_decimal=fill.quantity_decimal,
                remaining_decimal=fill.quantity_decimal,
                fee_remaining_decimal=total_fee,
                fee_known=fees_known,
                multiplier_decimal=fill.multiplier_decimal,
            )
            lot.account_id, lot.instrument_id, lot.currency, lot.multiplier = scope[0], scope[1], scope[2], fill.multiplier
            open_lots.setdefault(scope, []).append(lot)
            continue

        lots = open_lots.get(scope, [])
        enforce_t1 = fill.market == "CN-A" and market_policy != "none"
        if is_short_close:
            sellable = [lot for lot in lots if lot.remaining > 0 and lot.direction == "SHORT"]
        else:
            sellable = [lot for lot in lots if lot.remaining > 0 and lot.direction == "LONG" and (not enforce_t1 or lot.trade_date < fill.trade_date)]
        blocked_same_day = [lot for lot in lots if lot.remaining > 0 and enforce_t1 and lot.trade_date >= fill.trade_date]

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

        if is_short_open and allow_shorts:
            short_lot = _Lot(fill_id=fill.fill_id, symbol=fill.symbol, name=fill.name, trade_date=fill.trade_date, entry_time=fill.datetime_text, price=fill.price, quantity=fill.quantity, remaining=fill.quantity, buy_fee_per_share=float(total_fee / fill.quantity_decimal), invalidation_price=fill.invalidation_price, thesis=fill.thesis, regime=fill.regime, tags=list(fill.tags), account_id=scope[0], instrument_id=scope[1], currency=scope[2], multiplier=fill.multiplier, direction="SHORT", price_decimal=fill.price_decimal, quantity_decimal=fill.quantity_decimal, remaining_decimal=fill.quantity_decimal, fee_remaining_decimal=total_fee, fee_known=fees_known, multiplier_decimal=fill.multiplier_decimal)
            short_lot.fees_known = fees_known
            open_lots.setdefault(scope, []).append(short_lot)
            continue

        if not sellable and is_short_close and allow_shorts:
            issues.append({"code": "sell_without_position", "severity": "error", "symbol": fill.symbol, "fill_id": fill.fill_id, "detail": "short cover has no prior short position"})
            continue
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
        remaining_to_sell_decimal = fill.quantity_decimal
        matches: list[dict[str, Any]] = []
        first_lot: _Lot | None = None
        for lot in sellable:
            if remaining_to_sell_decimal <= 0:
                break
            lot_quantity_before = lot.remaining_decimal
            matched_decimal = min(lot_quantity_before, remaining_to_sell_decimal)
            buy_fee_decimal = _allocate_decimal(lot.fee_remaining_decimal, matched_decimal, lot_quantity_before)
            lot.fee_remaining_decimal -= buy_fee_decimal
            lot.remaining_decimal -= matched_decimal
            lot.remaining = float(lot.remaining_decimal)
            remaining_to_sell_decimal -= matched_decimal
            matched = float(matched_decimal)
            if first_lot is None:
                first_lot = lot
            matches.append(
                {
                    "lot_fill_id": lot.fill_id,
                    "entry_time": lot.entry_time,
                    "entry_price": lot.price,
                    "entry_price_exact": _decimal_text(lot.price_decimal),
                    "quantity": matched,
                    "quantity_exact": _decimal_text(matched_decimal),
                    "buy_fee": float(buy_fee_decimal),
                    "buy_fee_exact": _decimal_text(buy_fee_decimal),
                    "fees_known": lot.fees_known,
                }
            )

        if remaining_to_sell_decimal > 0:
            issues.append(
                {
                    "code": "oversell",
                    "severity": "error",
                    "symbol": fill.symbol,
                    "fill_id": fill.fill_id,
                    "detail": f"sell exceeds recorded sellable position by {remaining_to_sell_decimal} shares",
                }
            )

        matched_quantity_decimal = fill.quantity_decimal - remaining_to_sell_decimal
        matched_quantity = float(matched_quantity_decimal)
        if matched_quantity <= 0:
            continue

        sell_fee_decimal = _allocate_decimal(total_fee, matched_quantity_decimal, fill.quantity_decimal)
        sell_fee = float(sell_fee_decimal)
        is_short = bool(first_lot and first_lot.direction == "SHORT")
        multiplier = first_lot.multiplier if first_lot else fill.multiplier
        cost_decimal = sum((Decimal(match["entry_price_exact"]) * Decimal(match["quantity_exact"]) for match in matches), Decimal("0")) * first_lot.multiplier_decimal
        buy_fee_decimal = sum((Decimal(str(match["buy_fee_exact"])) for match in matches), Decimal("0"))
        proceeds_decimal = fill.price_decimal * matched_quantity_decimal * fill.multiplier_decimal
        gross_pnl_decimal = (cost_decimal - proceeds_decimal) if is_short else (proceeds_decimal - cost_decimal)
        fees_decimal = buy_fee_decimal + sell_fee_decimal
        net_pnl_decimal = gross_pnl_decimal - fees_decimal
        cost, buy_fee, proceeds = float(cost_decimal), float(buy_fee_decimal), float(proceeds_decimal)
        gross_pnl, fees, net_pnl = float(gross_pnl_decimal), float(fees_decimal), float(net_pnl_decimal)
        entry_time = matches[0]["entry_time"]
        entry_date = entry_time.split(" ")[0]
        try:
            holding_days = (
                datetime.strptime(fill.trade_date, "%Y-%m-%d") - datetime.strptime(entry_date, "%Y-%m-%d")
            ).days
        except ValueError:
            holding_days = 0

        identity = "|".join(
            [scope[0], scope[1], scope[2], fill.fill_id, *(match["lot_fill_id"] for match in matches)]
        )
        stable_id = "RT-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        round_trips.append(
            {
                "round_trip_id": stable_id,
                "symbol": fill.symbol,
                "account_id": scope[0],
                "instrument_id": scope[1],
                "currency": scope[2],
                "market": fill.market,
                "source_precision": fill.time_precision,
                "timezone": fill.timezone,
                "name": fill.name or (first_lot.name if first_lot else ""),
                "regime": fill.regime or (first_lot.regime if first_lot else ""),
                "thesis": fill.thesis or (first_lot.thesis if first_lot else ""),
                "tags": list(fill.tags) or (list(first_lot.tags) if first_lot else []),
                "invalidation_price": (
                    fill.invalidation_price if fill.invalidation_price is not None else
                    (first_lot.invalidation_price if first_lot else None)
                ),
                "entry_time": entry_time,
                "entry_price": round(cost / matched_quantity / multiplier, 8),
                "entry_price_exact": _decimal_text(cost_decimal / matched_quantity_decimal / first_lot.multiplier_decimal),
                "exit_time": fill.datetime_text,
                "exit_price": fill.price,
                "quantity": matched_quantity,
                "quantity_exact": _decimal_text(matched_quantity_decimal),
                "cost_basis": cost_basis,
                "gross_pnl": _decimal_float(gross_pnl_decimal),
                "gross_pnl_exact": _decimal_text(gross_pnl_decimal),
                "fees": _decimal_float(fees_decimal),
                "fees_exact": _decimal_text(fees_decimal),
                "fees_known": fees_known and all(match["fees_known"] for match in matches),
                "net_pnl": _decimal_float(net_pnl_decimal),
                "net_pnl_exact": _decimal_text(net_pnl_decimal),
                "return_pct": round(net_pnl / (cost + buy_fee) * 100, 2) if (cost + buy_fee) > 0 else 0.0,
                "holding_days": holding_days,
                "matched_lots": matches,
                "exit_complete": remaining_to_sell_decimal == 0,
                "cost_basis_assumed": len(matches) > 1,
                "position_side": "SHORT" if is_short else "LONG",
                "multiplier": first_lot.multiplier if first_lot else fill.multiplier,
            }
        )

    open_positions: list[dict[str, Any]] = []
    for scope, lots in sorted(open_lots.items()):
        account_id, instrument_id, currency = scope
        for direction in ("LONG", "SHORT"):
            symbol = lots[0].symbol if lots else instrument_id
            active = [lot for lot in lots if lot.remaining > 0 and lot.direction == direction]
            if not active:
                continue
            signed = -1 if direction == "SHORT" else 1
            quantity = signed * sum(lot.remaining for lot in active)
            cost = sum(lot.price * lot.remaining for lot in active)
            position_key = (account_id, instrument_id, currency, direction)
            open_positions.append(
                {
                    "position_id": "POS-" + "-".join(
                        part.replace("/", "_").replace(" ", "_") or "UNKNOWN"
                        for part in position_key
                    ),
                    "symbol": symbol,
                    "account_id": account_id,
                    "instrument_id": instrument_id,
                    "currency": currency,
                    "name": active[0].name,
                    "quantity": quantity,
                    "position_side": direction,
                    "avg_cost": round(cost / abs(quantity), 4) if quantity else 0.0,
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
        "market_policy": market_policy or "per_fill_market",
        "allow_shorts": bool(allow_shorts),
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
                "price_exact": _decimal_text(fill.price_decimal),
                "quantity": fill.quantity,
                "quantity_exact": _decimal_text(fill.quantity_decimal),
                "currency": fill.currency,
                "multiplier": fill.multiplier,
                "multiplier_exact": _decimal_text(fill.multiplier_decimal),
                "time_precision": fill.time_precision,
                "account_id": fill.account_id,
                "instrument_id": fill.instrument_id,
                "position_effect": fill.position_effect,
                "market": fill.market,
                "timezone": fill.timezone,
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
                "account_id": trip.get("account_id", ""),
                "instrument_id": trip.get("instrument_id", trip["symbol"]),
                "currency": trip.get("currency", "UNKNOWN"),
                "market": trip.get("market", "UNKNOWN"),
                "multiplier": trip.get("multiplier", 1),
                "position_side": trip.get("position_side", "LONG"),
                "source_precision": trip.get("source_precision", "unknown"),
                "timezone": trip.get("timezone", "unknown"),
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
