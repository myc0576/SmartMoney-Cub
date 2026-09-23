"""Lazy provider factory for the connection controller.

No optional SDK is imported and no terminal/network client is created until a
user explicitly connects a provider. Tests and local deployments can inject a
fixture adapter through the controller's factory hook instead.
"""

from __future__ import annotations

from typing import Any, Mapping

from .models import CredentialBundle


def build_connection(provider_id: str, values: Mapping[str, Any], config: Mapping[str, Any]):
    provider_id = str(provider_id)
    if provider_id in {"ccxt-binance", "ccxt-okx"}:
        symbols = config.get("symbols") or values.get("symbols")
        if isinstance(symbols, str):
            symbols = tuple(part.strip() for part in symbols.split(",") if part.strip())
        if not isinstance(symbols, (list, tuple)) or not symbols:
            raise ValueError("explicit_spot_symbols_required")
        account_id = str(config.get("account_id") or values.get("account_id") or "").strip()
        if not account_id:
            raise ValueError("stable_account_alias_required")
        try:
            import ccxt
        except ImportError as exc:
            raise RuntimeError("optional_dependency_missing:ccxt") from None
        from .ccxt import CCXTConnection

        exchange_name = "binance" if provider_id.endswith("binance") else "okx"
        exchange_class = getattr(ccxt, exchange_name)
        exchange = exchange_class({
            "apiKey": values.get("api_key"),
            "secret": values.get("api_secret"),
            "password": values.get("passphrase"),
            "enableRateLimit": True,
        })
        credentials = CredentialBundle(provider_id, dict(values))
        return CCXTConnection(provider_id, exchange, credentials, symbols=tuple(symbols), since=config.get("since"), limit=int(config.get("limit", 1000)), account_id=account_id)
    if provider_id == "ibkr-flex":
        from .ibkr import FlexTransport, IBKRFlexConnection

        credentials = CredentialBundle(provider_id, dict(values))
        return IBKRFlexConnection(FlexTransport(), credentials, account_id=config.get("account_id"), query_id=config.get("query_id"), page_size=int(config.get("page_size", 1000)))
    if provider_id == "metatrader-investor":
        try:
            import MetaTrader5 as mt5
        except ImportError:
            raise RuntimeError("optional_dependency_missing:MetaTrader5") from None
        from .mt5 import MetaTraderInvestorConnection

        if not mt5.initialize():
            raise ValueError("metatrader_terminal_attach_failed")
        return MetaTraderInvestorConnection(mt5, CredentialBundle(provider_id, dict(values)), page_size=int(config.get("page_size", 1000)))
    if provider_id == "local-statement-directory":
        from .local_statements import LocalStatementConnection

        return LocalStatementConnection(str(values.get("directory") or config.get("directory") or ""), CredentialBundle(provider_id, dict(values)), account_id=values.get("account_id") or config.get("account_id"))
    if provider_id == "vezgo":
        from .vezgo import VezgoConnection, VezgoTransport

        return VezgoConnection(VezgoTransport(), CredentialBundle(provider_id, dict(values)))
    if provider_id == "snaptrade-personal-mcp":
        from .snaptrade import SnapTradePersonalMCPConnection

        return SnapTradePersonalMCPConnection(CredentialBundle(provider_id, dict(values)))
    raise ValueError(f"unsupported_connection_provider:{provider_id}")
