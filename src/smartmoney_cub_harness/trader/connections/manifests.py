"""Curated provider metadata; no provider package or credentials are loaded."""

from __future__ import annotations

from .models import AuthSpec, ConnectionManifest, HistorySpec, OfficialLink, ValidationStatus


def _link(label: str, url: str) -> OfficialLink:
    return OfficialLink(label, url)


CONNECTION_MANIFESTS: tuple[ConnectionManifest, ...] = (
    ConnectionManifest(
        provider_id="ccxt-binance",
        name="CCXT Binance (read-only)",
        description="Optional CCXT adapter for selected spot pairs. Exchange history limits apply; statements cover older or omitted pairs.",
        official_links=(_link("CCXT manual", "https://docs.ccxt.com/"), _link("Binance API", "https://developers.binance.com/docs/binance-spot-api-docs")),
        auth=AuthSpec("api_key", ("api_key", "api_secret", "account_id", "symbols"), scopes=("read",), notes="Disable trading, transfers and withdrawals. Set a stable account alias and comma-separated spot pairs; this is not whole-account history discovery."),
        supported_assets=("crypto", "spot"),
        history=HistorySpec(precision="millisecond", timezones=("UTC",), max_page_size=1000),
        validation=ValidationStatus("fixture_only", issues=("live_authorization_not_performed",)),
        network_required=True,
    ),
    ConnectionManifest(
        provider_id="ccxt-okx",
        name="CCXT OKX (read-only)",
        description="Optional CCXT adapter for selected spot pairs. Exchange history limits apply; statements cover older or omitted pairs.",
        official_links=(_link("CCXT manual", "https://docs.ccxt.com/"), _link("OKX API", "https://www.okx.com/docs-v5/en/")),
        auth=AuthSpec("api_key", ("api_key", "api_secret", "passphrase", "account_id", "symbols"), scopes=("read",), notes="Use a read-only key and IP restrictions. Set a stable account alias and comma-separated spot pairs; derivatives and margin are not normalized by this adapter."),
        supported_assets=("crypto", "spot"),
        history=HistorySpec(precision="millisecond", timezones=("UTC",), max_page_size=1000),
        validation=ValidationStatus("fixture_only", issues=("live_authorization_not_performed",)),
        network_required=True,
    ),
    ConnectionManifest(
        provider_id="ibkr-flex",
        name="Interactive Brokers Flex Web Service", 
        description="Two-step statement/report import with normalized executions; no trading API.",
        official_links=(_link("Flex Web Service", "https://www.interactivebrokers.com/docs/web-api/flex-web-service/using-flex-web-service"), _link("Statements", "https://www.interactivebrokers.com/docs/web-api/account-management/reporting/activity-statements")),
        auth=AuthSpec("flex_token", ("flex_token", "query_id"), scopes=("read",), notes="Keep token local; request reports manually or through an explicitly configured read-only job."),
        supported_assets=("stocks", "options", "futures", "forex", "crypto_unknown"),
        history=HistorySpec(precision="second", timezones=("source_declared",), max_page_size=1000),
        validation=ValidationStatus("fixture_only", issues=("live_authorization_not_performed",)),
        network_required=True,
    ),
    ConnectionManifest(
        provider_id="metatrader-investor",
        name="MetaTrader investor terminal bridge",
        description="Optional local MetaTrader 5 terminal SDK. The user opens and signs into an investor-mode terminal; the bridge only reads its account, deals and positions.",
        official_links=(_link("MetaTrader authorization", "https://www.metatrader5.com/en/terminal/help/startworking/authorization"),),
        auth=AuthSpec("local_terminal", (), scopes=("read",), notes="Requires an installed compatible MetaTrader5 SDK/terminal. Trading-disabled account access is checked; the SDK cannot prove which password type was used. Terminal login remains a user action."),
        supported_assets=("forex", "cfd", "futures", "stocks_unknown"),
        history=HistorySpec(precision="millisecond", timezones=("UTC",), max_page_size=1000),
        validation=ValidationStatus("fixture_only", issues=("local_bridge_only",)),
    ),
    ConnectionManifest(
        provider_id="local-statement-directory",
        name="Local statement directory",
        description="Import/watch user-owned CSV and JSON statements, including rotki generic trade exports. PDF requires the separate import workflow.",
        official_links=(_link("Project", "https://github.com/myc0576/SmartMoney-Cub"), _link("rotki import formats", "https://docs.rotki.com/usage-guides/history/import-data.html")),
        auth=AuthSpec("local_files", ("directory",), scopes=("read",), notes="The directory must be selected by the user; no login/export automation."),
        supported_assets=("stocks", "crypto", "forex", "options", "unknown"),
        history=HistorySpec(precision="source_declared", timezones=("source_declared",), max_page_size=1000),
        validation=ValidationStatus("local_only"),
    ),
    ConnectionManifest(
        provider_id="snaptrade-personal-mcp",
        name="SnapTrade Personal MCP (read-only)",
        description="Optional official read-only MCP data connection using DCR + PKCE. Authorization callback currently requires local loopback mode.",
        official_links=(_link("MCP server", "https://docs.snaptrade.com/docs/mcp-server"), _link("Account activity", "https://docs.snaptrade.com/reference/Account%20Information/AccountInformation_getAccountActivities")),
        auth=AuthSpec("dcr_pkce", (), scopes=("read",), notes="Use the official OAuth button, not pasted tokens. Brokerage linking is performed by the user in SnapTrade; request_connection_link is excluded."),
        supported_assets=("stocks", "etf", "crypto", "forex", "options", "unknown"),
        history=HistorySpec(precision="day_or_source_declared", timezones=("source_declared",), max_page_size=1000),
        validation=ValidationStatus("fixture_only", issues=("live_authorization_not_performed", "daily_cache_possible")),
        network_required=True,
    ),
    ConnectionManifest(
        provider_id="vezgo",
        name="Vezgo (optional user-owned developer credential)",
        description="Optional portfolio data API adapter; user supplies credentials and accepts any vendor cost/limits.",
        official_links=(_link("Vezgo docs", "https://vezgo.com/docs/get-started/"),),
        auth=AuthSpec("developer_token", ("client_id", "client_secret", "login_name"), scopes=("read",), notes="User-owned Vezgo developer application and its end-user login name. Optional vendor cost and enrollment; never required for offline core."),
        supported_assets=("crypto", "wallet", "exchange"),
        history=HistorySpec(precision="source_declared", timezones=("UTC", "source_declared"), max_page_size=1000),
        validation=ValidationStatus("fixture_only", issues=("optional_vendor", "live_authorization_not_performed")),
        network_required=True,
    ),
)


MANIFEST_BY_ID = {manifest.provider_id: manifest for manifest in CONNECTION_MANIFESTS}


def get_manifest(provider_id: str) -> ConnectionManifest:
    try:
        return MANIFEST_BY_ID[str(provider_id)]
    except KeyError as exc:
        raise KeyError(f"unknown connection provider: {provider_id}") from exc


def list_manifests() -> tuple[ConnectionManifest, ...]:
    return CONNECTION_MANIFESTS
