"""The trader product's route table and the HTTP dispatch entry point.

Why this file exists: the workbench server owns HTTP plumbing, and the product
owns routes and rules. One dispatch function sits between them, so the server
needs three lines of glue and this module can be tested without a socket.

Identity is resolved once, here, before any route runs. A handler never reads a
user id from a query parameter, because no handler is given the chance: the only
thing that reaches the service is the AuthContext resolved from the request
headers. An unverifiable request stops at the door with 401.

ROUTES is the frozen list this product promises, and docs/trader-api.md
documents the same list. A test asserts both, so a route cannot be added to one
and forgotten in the other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.api.service import (
    TraderRequestError,
    TraderService,
    coerce_float,
    coerce_int,
    parse_import_payload,
)
from smartmoney_cub_harness.trader.auth import AuthContext, AuthError, resolve_identity
from smartmoney_cub_harness.trader.backtest import StrategyError
from smartmoney_cub_harness.trader.market import MAX_LIMIT, MarketDataError
from smartmoney_cub_harness.trader.storage import StoreError

TRADER_API_PREFIX = "/api/trader"
DOCUMENTED_IN = "docs/trader-api.md"

# The default page for a list endpoint, matching the market layer's default.
DEFAULT_PAGE = 500


@dataclass(frozen=True)
class Route:
    """One documented endpoint: method, path template, handler, and summary."""

    method: str
    template: str
    handler: str
    summary: str


ROUTES: tuple[Route, ...] = (
    Route("GET", "/api/trader/health", "health", "Liveness, the resolved identity, and the safety declaration."),
    Route("GET", "/api/trader/meta", "meta", "Product metadata: tenant, storage engine, and capabilities."),
    Route("GET", "/api/trader/market/providers", "market_providers", "The built-in keyless market data sources."),
    Route("GET", "/api/trader/market/bars", "market_bars", "Fetch one normalized OHLCV series on demand."),
    Route("GET", "/api/trader/trades", "list_trades", "The tenant's journal and its closed round trips."),
    Route("POST", "/api/trader/trades/import", "import_trades", "Import the tenant's executions from CSV or JSON."),
    Route("GET", "/api/trader/trades/{round_trip_id}", "get_trade", "One round trip, with the issues touching its symbol."),
    Route("GET", "/api/trader/accounts", "list_accounts", "The tenant's accounts."),
    Route("POST", "/api/trader/accounts", "upsert_account", "Create or update one account."),
    Route("GET", "/api/trader/analytics/summary", "analytics_summary", "Performance summary over the tenant's own ledger."),
    Route("GET", "/api/trader/analytics/breakdown", "analytics_breakdown", "Performance grouped by one reviewed dimension."),
    Route("GET", "/api/trader/calendar", "calendar", "Closed round trips aggregated by exit day."),
    Route("GET", "/api/trader/playbooks", "playbooks", "Declared and observed playbooks, each scored."),
    Route("POST", "/api/trader/playbooks", "upsert_playbook", "Declare or update one playbook."),
    Route("POST", "/api/trader/backtest/run", "backtest_run", "Validate a strategy, run it, and save the run."),
    Route("GET", "/api/trader/backtest/runs", "backtest_runs", "The tenant's saved backtest runs."),
    Route("GET", "/api/trader/backtest/runs/{run_id}", "backtest_run_detail", "One saved run, with its spec and curve."),
    Route("POST", "/api/trader/replay/sessions", "create_replay_session", "Hold a bar series for a browser to step through."),
    Route("GET", "/api/trader/replay/sessions/{session_id}", "replay_session", "Step a replay session to a frame index."),
)

# The documentation lines for the same table, in the same order. Kept beside
# ROUTES so a doc test can hold the reference and the code to one list.
ROUTE_LINES: tuple[str, ...] = tuple(f"{route.method} {route.template}" for route in ROUTES)

_PLACEHOLDER_OPEN = "{"
_PLACEHOLDER_CLOSE = "}"


@dataclass(frozen=True)
class Request:
    """Everything one handler may look at, after identity was resolved."""

    service: TraderService
    ctx: AuthContext
    params: Mapping[str, str]
    query: Mapping[str, Sequence[str]]
    body: str = ""
    content_type: str = ""
    json_body: Any = None


def _one(query: Mapping[str, Sequence[str]], name: str) -> str | None:
    """First value of one query parameter, or None when it is absent or blank."""
    values = query.get(name)
    if not values:
        return None
    text = str(values[0]).strip()
    return text or None


def _int(
    query: Mapping[str, Sequence[str]],
    name: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    """One optional integer query parameter, validated by the service helper."""
    return coerce_int(
        _one(query, name), name=name, default=default, minimum=minimum, maximum=maximum
    )


def _limit(query: Mapping[str, Sequence[str]], *, default: int = DEFAULT_PAGE) -> int:
    resolved = _int(query, "limit", default=default, minimum=1, maximum=MAX_LIMIT)
    return int(resolved if resolved is not None else default)


def _offset(query: Mapping[str, Sequence[str]]) -> int:
    resolved = _int(query, "offset", default=0, minimum=0)
    return int(resolved or 0)


def _float(
    query: Mapping[str, Sequence[str]], name: str, *, default: float | None = None
) -> float | None:
    """One optional number query parameter, validated by the service helper."""
    return coerce_float(_one(query, name), name=name, default=default)


# ---- handlers ----------------------------------------------------------
#
# One function per endpoint. Each takes a resolved Request and returns a plain
# mapping; dispatch attaches the safety declaration and maps exceptions onto
# HTTP statuses, so a handler never writes a status code itself.


def _health(request: Request) -> dict[str, Any]:
    return request.service.health(request.ctx)


def _meta(request: Request) -> dict[str, Any]:
    return request.service.meta(request.ctx)


def _market_providers(request: Request) -> dict[str, Any]:
    return request.service.market_providers(request.ctx)


def _market_bars(request: Request) -> dict[str, Any]:
    return request.service.market_bars(
        request.ctx,
        provider=_one(request.query, "provider") or "",
        symbol=_one(request.query, "symbol") or "",
        interval=_one(request.query, "interval") or "",
        start=_one(request.query, "start"),
        end=_one(request.query, "end"),
        limit=_limit(request.query),
    )


def _list_trades(request: Request) -> dict[str, Any]:
    return request.service.list_trades(
        request.ctx,
        account_id=_one(request.query, "account_id"),
        symbol=_one(request.query, "symbol"),
        start=_one(request.query, "from"),
        end=_one(request.query, "to"),
        limit=_limit(request.query),
        offset=_offset(request.query),
    )


def _import_trades(request: Request) -> dict[str, Any]:
    rows, source_format = parse_import_payload(
        request.body, content_type=request.content_type, payload=request.json_body
    )
    return request.service.import_trades(
        request.ctx, rows=rows, source_format=source_format
    )


def _get_trade(request: Request) -> dict[str, Any]:
    return request.service.get_trade(request.ctx, request.params.get("round_trip_id", ""))


def _list_accounts(request: Request) -> dict[str, Any]:
    return request.service.list_accounts(request.ctx)


def _upsert_account(request: Request) -> dict[str, Any]:
    payload = request.json_body
    if payload is None:
        raise TraderRequestError("the request body must be a JSON object")
    return request.service.upsert_account(request.ctx, payload)


def _analytics_summary(request: Request) -> dict[str, Any]:
    return request.service.analytics_summary(
        request.ctx,
        start=_one(request.query, "from"),
        end=_one(request.query, "to"),
        account_id=_one(request.query, "account_id"),
    )


def _analytics_breakdown(request: Request) -> dict[str, Any]:
    refresh_param = _one(request.query, "refresh")
    refresh = str(refresh_param or "").lower() in ("1", "true", "yes")
    return request.service.analytics_breakdown(
        request.ctx,
        dimension=_one(request.query, "dimension"),
        start=_one(request.query, "from"),
        end=_one(request.query, "to"),
        refresh=refresh,
    )


def _calendar(request: Request) -> dict[str, Any]:
    return request.service.calendar(
        request.ctx,
        year=_int(request.query, "year", minimum=1, maximum=9999),
        month=_int(request.query, "month", minimum=1, maximum=12),
    )


def _playbooks(request: Request) -> dict[str, Any]:
    return request.service.playbooks(request.ctx)


def _upsert_playbook(request: Request) -> dict[str, Any]:
    payload = request.json_body
    if payload is None:
        raise TraderRequestError("the request body must be a JSON object")
    return request.service.upsert_playbook(request.ctx, payload)


def _backtest_run(request: Request) -> dict[str, Any]:
    payload = request.json_body
    if payload is None:
        raise TraderRequestError("the request body must be a JSON object")
    return request.service.backtest_run(request.ctx, payload)


def _backtest_runs(request: Request) -> dict[str, Any]:
    limit = _int(request.query, "limit", default=100, minimum=1, maximum=1_000)
    return request.service.backtest_runs(request.ctx, limit=int(limit or 100))


def _backtest_run_detail(request: Request) -> dict[str, Any]:
    return request.service.backtest_run_detail(request.ctx, request.params.get("run_id", ""))


def _create_replay_session(request: Request) -> dict[str, Any]:
    payload = request.json_body
    if payload is None:
        raise TraderRequestError("the request body must be a JSON object")
    return request.service.create_replay_session(request.ctx, payload)


def _replay_session(request: Request) -> dict[str, Any]:
    return request.service.replay_session(
        request.ctx,
        request.params.get("session_id", ""),
        index=_int(request.query, "index", minimum=0),
    )


HANDLERS: dict[str, Callable[[Request], dict[str, Any]]] = {
    "health": _health,
    "meta": _meta,
    "market_providers": _market_providers,
    "market_bars": _market_bars,
    "list_trades": _list_trades,
    "import_trades": _import_trades,
    "get_trade": _get_trade,
    "list_accounts": _list_accounts,
    "upsert_account": _upsert_account,
    "analytics_summary": _analytics_summary,
    "analytics_breakdown": _analytics_breakdown,
    "calendar": _calendar,
    "playbooks": _playbooks,
    "upsert_playbook": _upsert_playbook,
    "backtest_run": _backtest_run,
    "backtest_runs": _backtest_runs,
    "backtest_run_detail": _backtest_run_detail,
    "create_replay_session": _create_replay_session,
    "replay_session": _replay_session,
}


def _match_template(template: str, path: str) -> dict[str, str] | None:
    """Match one path against one template, returning its placeholder values."""
    if _PLACEHOLDER_OPEN not in template:
        return {} if template == path else None
    template_parts = template.strip("/").split("/")
    path_parts = path.strip("/").split("/")
    if len(template_parts) != len(path_parts):
        return None
    params: dict[str, str] = {}
    for expected, actual in zip(template_parts, path_parts):
        if expected.startswith(_PLACEHOLDER_OPEN) and expected.endswith(_PLACEHOLDER_CLOSE):
            if not actual:
                return None
            params[expected[1:-1]] = actual
            continue
        if expected != actual:
            return None
    return params


def match_route(method: str, path: str) -> tuple[Route, dict[str, str]] | None:
    """Resolve one method and path to a route.

    Literal templates are tried first, so a literal segment such as
    /trades/import can never be swallowed by a placeholder route.
    """
    wanted = (method or "").strip().upper()
    for route in ROUTES:
        if route.method != wanted or _PLACEHOLDER_OPEN in route.template:
            continue
        params = _match_template(route.template, path)
        if params is not None:
            return route, params
    for route in ROUTES:
        if route.method != wanted or _PLACEHOLDER_OPEN not in route.template:
            continue
        params = _match_template(route.template, path)
        if params is not None:
            return route, params
    return None


def _error_payload(
    message: str, *, code: str, status: int, auth_mode: str = ""
) -> dict[str, Any]:
    """One error shape for the whole product, always carrying the declaration."""
    payload: dict[str, Any] = {
        "status": "error",
        "error": message,
        "code": code,
        "status_code": status,
        "safety": SAFETY_DECLARATION,
    }
    if auth_mode:
        payload["auth_mode"] = auth_mode
    return payload


def _decode_body(body: bytes) -> tuple[str, Any]:
    """Return the body as text plus, when it is JSON, the decoded value.

    A body that is not JSON is not an error here: the import endpoint accepts
    CSV text, and every other endpoint reports its own refusal. Decoding is
    strict about the encoding, so a binary body is refused rather than silently
    mangled.
    """
    if not body:
        return "", None
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise TraderRequestError("the request body is not valid UTF-8") from None
    if text.lstrip()[:1] in ("{", "["):
        try:
            return text, json.loads(text)
        except json.JSONDecodeError as error:
            raise TraderRequestError(
                "the request body is not valid JSON: " + str(error)
            ) from None
    return text, None


def dispatch(
    service: TraderService,
    method: str,
    path: str,
    *,
    query: Mapping[str, Sequence[str]] | None = None,
    headers: Mapping[str, str] | None = None,
    body: bytes | str = b"",
    content_type: str = "",
    auth_mode: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Serve one /api/trader request and return its status and JSON body.

    Never raises: every failure becomes a JSON body carrying the safety
    declaration, so a client always reads a checked response. Identity is
    resolved before routing, so an unauthenticated request cannot tell a real
    route from an unknown one.
    """
    mode = str(auth_mode or getattr(service, "auth_mode", "local") or "local")
    try:
        ctx = resolve_identity(headers or {}, mode=mode)
    except AuthError as error:
        return 401, _error_payload(
            str(error), code="unauthorized", status=401, auth_mode=mode
        )
    except Exception as error:  # noqa: BLE001 - an unresolvable request is refused
        return 401, _error_payload(
            "identity could not be resolved: " + str(error),
            code="unauthorized",
            status=401,
        )

    matched = match_route(method, path)
    if matched is None:
        return 404, _error_payload(
            "no trader endpoint for " + (method or "").upper() + " " + path,
            code="not_found",
            status=404,
        )
    route, params = matched

    raw_body = body.encode("utf-8") if isinstance(body, str) else (body or b"")
    try:
        text, json_body = _decode_body(raw_body)
    except TraderRequestError as error:
        return error.status, _error_payload(
            str(error), code=error.code, status=error.status
        )

    request = Request(
        service=service,
        ctx=ctx,
        params=params,
        query=query or {},
        body=text,
        content_type=content_type or "",
        json_body=json_body,
    )
    try:
        payload = HANDLERS[route.handler](request)
    except TraderRequestError as error:
        return error.status, _error_payload(
            str(error), code=error.code, status=error.status
        )
    except MarketDataError as error:
        # An upstream source that will not answer is a bad gateway, never an
        # empty series: a quiet market and a broken source must not look alike.
        return 502, _error_payload(
            str(error), code="market_data_unavailable", status=502
        )
    except StrategyError as error:
        return 400, _error_payload(
            "strategy is invalid: " + str(error), code="invalid_strategy", status=400
        )
    except StoreError as error:
        return 400, _error_payload(str(error), code="store_error", status=400)
    except ValueError as error:
        return 400, _error_payload(str(error), code="bad_request", status=400)
    except Exception as error:  # noqa: BLE001 - a handler must never crash the server
        return 500, _error_payload(
            "the trader service failed: " + type(error).__name__ + ": " + str(error),
            code="internal_error",
            status=500,
        )

    if not isinstance(payload, Mapping):
        return 500, _error_payload(
            "the trader service returned a non-object response",
            code="internal_error",
            status=500,
        )
    return 200, {**payload, "safety": SAFETY_DECLARATION}
