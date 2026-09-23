"""SnapTrade Personal MCP adapter with a read-only JSON-RPC allowlist."""

from __future__ import annotations

import hashlib
import json
import base64
import secrets
import urllib.parse
import urllib.request
import urllib.error
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from .manifests import get_manifest
from .models import ConnectionAccount, ConnectionCursor, CredentialBundle, EventPage, NormalizedEvent, NormalizedPosition, ScopeValidation
from .protocol import PermissionConnectionError, TransientConnectionError
from .http import open_without_redirect


_READ_TOOLS = frozenset({
    "Connections_listBrokerageAuthorizations",
    "Connections_listBrokerageAuthorizationAccounts",
    "AccountInformation_getUserAccountDetails",
    "AccountInformation_getUserAccountBalance",
    "AccountInformation_getAllAccountPositions",
    "AccountInformation_getAccountBalanceHistory",
    "AccountInformation_getUserAccountOrdersV2",
    "AccountInformation_getUserAccountRecentOrdersV2",
    "AccountInformation_getUserAccountOrderDetailV2",
    "AccountInformation_getAccountActivities",
    "ReferenceData_listAllCurrencies",
    "ReferenceData_listAllCurrenciesRates",
    "ReferenceData_getCurrencyExchangeRatePair",
    "ReferenceData_getSecurityTypes",
    "ReferenceData_getStockExchanges",
    "ReferenceData_getPartnerInfo",
    "list_supported_brokerages",
})


class SnapTradeOAuthClient:
    """DCR + PKCE helper for the Personal MCP connector.

    The client receives an injected HTTP callable in tests/hosts. It never
    stores a client secret in a public DTO and never requests a write scope.
    """

    def __init__(self, http_call, *, authorization_endpoint: str = "https://dashboard.snaptrade.com/oauth/authorize", token_endpoint: str = "https://api.snaptrade.com/oauth/token/", registration_endpoint: str = "https://api.snaptrade.com/oauth/register/", revocation_endpoint: str = "https://api.snaptrade.com/oauth/revoke_token/") -> None:
        self.http_call = http_call
        self.authorization_endpoint = authorization_endpoint
        self.token_endpoint = token_endpoint
        self.registration_endpoint = registration_endpoint
        self.revocation_endpoint = revocation_endpoint

    @staticmethod
    def pkce() -> tuple[str, str]:
        verifier = secrets.token_urlsafe(48)
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        return verifier, challenge

    def register_dynamic_client(self, *, redirect_uri: str, client_name: str = "Smartmoney-Cub") -> Mapping[str, Any]:
        response = self.http_call("POST", self.registration_endpoint, {"client_name": client_name, "redirect_uris": [redirect_uri], "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"], "token_endpoint_auth_method": "none"})
        if not isinstance(response, Mapping) or not response.get("client_id"):
            raise RuntimeError("snaptrade_dcr_failed")
        return {"client_id": str(response["client_id"]), "redirect_uri": redirect_uri, "client_secret": None}

    def authorization_url(self, *, client_id: str, redirect_uri: str, state: str | None = None) -> tuple[str, str]:
        verifier, challenge = self.pkce()
        query = urllib.parse.urlencode({"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "scope": "read", "code_challenge": challenge, "code_challenge_method": "S256", "state": state or secrets.token_urlsafe(24)})
        return f"{self.authorization_endpoint}?{query}", verifier

    def exchange_code(self, *, code: str, verifier: str, client_id: str, redirect_uri: str) -> Mapping[str, Any]:
        response = self.http_call("POST", self.token_endpoint, {"grant_type": "authorization_code", "code": code, "code_verifier": verifier, "client_id": client_id, "redirect_uri": redirect_uri})
        if not isinstance(response, Mapping) or not response.get("access_token"):
            raise PermissionConnectionError("snaptrade_token_exchange_failed")
        scopes = {str(item) for item in str(response.get("scope") or "read").split()}
        if scopes != {"read"}:
            raise PermissionConnectionError("snaptrade_write_scope_rejected")
        return {"access_token": str(response["access_token"]), "refresh_token": response.get("refresh_token"), "expires_in": response.get("expires_in"), "scope": "read", "token_type": response.get("token_type", "Bearer")}

    def revoke(self, *, token: str) -> None:
        self.http_call("POST", self.revocation_endpoint, {"token": token, "token_type_hint": "access_token"})

    def refresh(self, *, refresh_token: str, client_id: str) -> Mapping[str, Any]:
        response = self.http_call("POST", self.token_endpoint, {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id})
        if not isinstance(response, Mapping) or not response.get("access_token"):
            raise PermissionConnectionError("snaptrade_token_refresh_failed")
        scopes = {str(item) for item in str(response.get("scope") or "read").split()}
        if scopes != {"read"}:
            raise PermissionConnectionError("snaptrade_write_scope_rejected")
        return {"access_token": str(response["access_token"]), "refresh_token": response.get("refresh_token"), "expires_in": response.get("expires_in"), "scope": "read", "token_type": response.get("token_type", "Bearer")}


class MCPTransport:
    def __init__(self, base_url: str = "https://mcp.snaptrade.com/mcp", timeout: int = 20) -> None:
        self.base_url, self.timeout = base_url, timeout
        self._request_id = 0
        self._session_id = None

    def _rpc(self, token: str, method: str, params: Mapping[str, Any] | None = None, *, notification=False) -> Any:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": dict(params or {})}
        if notification:
            payload.pop("id")
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        request = urllib.request.Request(self.base_url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            with open_without_redirect(request, timeout=self.timeout) as response:
                raw = response.read(16 * 1024 * 1024)
                if response.headers.get("Mcp-Session-Id"):
                    self._session_id = response.headers["Mcp-Session-Id"]
        except TimeoutError as exc:
            raise TransientConnectionError("snaptrade_mcp_timeout") from exc
        except Exception as exc:
            raise RuntimeError(f"snaptrade_mcp_http_error:{type(exc).__name__}") from None
        text = raw.decode("utf-8", errors="replace").strip()
        if notification and not text:
            return None
        if not text.startswith("{"):
            events = ["\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")) for block in text.replace("\r\n", "\n").split("\n\n")]
            matching = [value for value in events if value and json.loads(value).get("id") == self._request_id]
            if not matching:
                raise ValueError("snaptrade_mcp_sse_response_missing")
            text = matching[-1]
        result = json.loads(text)
        if not isinstance(result, Mapping) or result.get("error"):
            raise PermissionConnectionError("snaptrade_mcp_request_failed")
        return result.get("result")

    def initialize(self, token: str) -> Mapping[str, Any]:
        result = self._rpc(token, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smartmoney-cub", "version": "1"}})
        if not isinstance(result, Mapping):
            raise RuntimeError("snaptrade_mcp_initialize_invalid")
        self._rpc(token, "notifications/initialized", notification=True)
        return result

    def list_tools(self, token: str) -> tuple[Mapping[str, Any], ...]:
        result = self._rpc(token, "tools/list", {})
        tools = result.get("tools") if isinstance(result, Mapping) else None
        return tuple(item for item in tools if isinstance(item, Mapping)) if isinstance(tools, list) else ()

    def call(self, token: str, tool: str, arguments: Mapping[str, Any] | None = None) -> Any:
        if tool not in _READ_TOOLS:
            raise PermissionConnectionError("snaptrade_tool_not_read_only")
        result = self._rpc(token, "tools/call", {"name": tool, "arguments": dict(arguments or {})})
        if isinstance(result, Mapping) and result.get("isError"):
            raise RuntimeError("snaptrade_mcp_tool_failed")
        if isinstance(result, Mapping) and isinstance(result.get("structuredContent"), Mapping):
            return result["structuredContent"]
        if isinstance(result, Mapping) and isinstance(result.get("content"), list):
            values = [item.get("text") for item in result["content"] if isinstance(item, Mapping) and isinstance(item.get("text"), str)]
            for value in values:
                try:
                    return json.loads(value)
                except ValueError:
                    continue
        return result


class SnapTradePersonalMCPConnection:
    def __init__(self, credentials: CredentialBundle, *, transport: MCPTransport | None = None, base_url: str = "https://mcp.snaptrade.com/mcp") -> None:
        self._credentials, self.transport = credentials, transport or MCPTransport(base_url)
        self._disconnected, self._verified = False, False
        self._initialized = False
        self._tool_schemas: dict[str, Mapping[str, Any]] = {}
        self._accounts: tuple[ConnectionAccount, ...] | None = None

    def metadata(self):
        return get_manifest("snaptrade-personal-mcp")

    def bind_credentials(self, credentials: CredentialBundle) -> None:
        if credentials.provider_id != "snaptrade-personal-mcp":
            raise ValueError("credential_provider_mismatch")
        self._credentials, self._verified = credentials, False

    def validate_read_access(self, credentials: CredentialBundle | None = None) -> ScopeValidation:
        supplied = credentials or self._credentials
        token = str(supplied.values.get("access_token") or supplied.values.get("read_token") or "").strip() if supplied else ""
        if self._disconnected or not token:
            return ScopeValidation(False, "missing", required=("read",), missing=("read",), issues=("snaptrade_read_token_required",))
        try:
            self._refresh_if_needed(supplied)
            token = str(supplied.values.get("access_token") or supplied.values.get("read_token") or "")
            self.transport.initialize(token)
            discovered = self.transport.list_tools(token)
            self._tool_schemas = {str(item.get("name")): item for item in discovered if item.get("name") in _READ_TOOLS}
            self._initialized = True
            result = self.transport.call(token, "Connections_listBrokerageAuthorizations", {})
            if result is None:
                raise ValueError("empty_brokerage_authorizations")
        except Exception as exc:
            self._verified = False
            return ScopeValidation(False, "unknown", required=("read",), missing=("read",), issues=(f"snaptrade_read_verification_failed:{type(exc).__name__}",))
        self._verified = True
        return ScopeValidation(True, "verified", required=("read",), granted=("read",))

    def _token(self, credentials: CredentialBundle | None) -> str:
        supplied = credentials or self._credentials
        if not self._verified:
            scope = self.validate_read_access(supplied)
            if not scope.allowed:
                raise PermissionConnectionError("snaptrade_read_access_required")
        return str(supplied.values.get("access_token") or supplied.values.get("read_token"))

    def _call(self, token: str, tool: str, arguments: Mapping[str, Any] | None = None) -> Any:
        if not self._initialized:
            self.validate_read_access()
        schema = self._tool_schemas.get(tool)
        if schema is None:
            raise ValueError("snaptrade_read_tool_unavailable")
        if schema is not None:
            required = schema.get("inputSchema", {}).get("required", []) if isinstance(schema.get("inputSchema"), Mapping) else []
            missing = [str(name) for name in required if name not in (arguments or {}) or (arguments or {})[name] is None]
            if missing:
                raise ValueError("snaptrade_tool_arguments_missing:" + ",".join(missing))
        return self.transport.call(token, tool, arguments)

    @staticmethod
    def _rows(payload: Any) -> tuple[Mapping[str, Any], ...]:
        if isinstance(payload, list):
            return tuple(item for item in payload if isinstance(item, Mapping))
        if isinstance(payload, Mapping):
            for key in ("data", "items", "accounts", "activities", "positions", "orders"):
                if isinstance(payload.get(key), list):
                    return tuple(item for item in payload[key] if isinstance(item, Mapping))
        return ()

    def list_accounts(self, credentials: CredentialBundle | None = None) -> tuple[ConnectionAccount, ...]:
        token = self._token(credentials)
        authorizations = self._rows(self._call(token, "Connections_listBrokerageAuthorizations", {}))
        rows = []
        for authorization in authorizations:
            rows.extend(self._rows(self._call(token, "Connections_listBrokerageAuthorizationAccounts", {"authorizationId": str(authorization["id"])})))
        self._accounts = tuple(ConnectionAccount(str(row.get("id") or row.get("account_id")), str(row.get("name") or row.get("institution_name") or "SnapTrade account"), "snaptrade-personal-mcp", str(row.get("type") or "unknown"), self._code(row.get("currency")), ("read",)) for row in rows)
        return self._accounts

    def read_events(self, cursor: ConnectionCursor | None = None, credentials: CredentialBundle | None = None) -> EventPage:
        token = self._token(credentials)
        state = json.loads(cursor.token) if cursor and cursor.token else {"offset": 0}
        if cursor and cursor.provider_id != "snaptrade-personal-mcp":
            raise ValueError("cursor_provider_mismatch")
        accounts = state.get("accounts") or [a.account_id for a in (self._accounts if self._accounts is not None else self.list_accounts(credentials))]
        index = int(state.get("index", 0))
        if index >= len(accounts):
            return EventPage(checkpoint_cursor=ConnectionCursor("snaptrade-personal-mcp"))
        account_id = accounts[index]
        payload = self._call(token, "AccountInformation_getAccountActivities", {"accountId": account_id, "offset": int(state.get("offset", 0)), "limit": 1000})
        rows = self._rows(payload)
        offset = int(state.get("offset", 0))
        events = tuple(self._event({**row, "account_id": account_id}) for row in rows)
        next_offset = offset + len(rows)
        if len(rows) < 1000:
            index, next_offset = index + 1, 0
        next_cursor = ConnectionCursor("snaptrade-personal-mcp", json.dumps({"accounts": accounts, "index": index, "offset": next_offset})) if index < len(accounts) else None
        checkpoint = next_cursor or ConnectionCursor("snaptrade-personal-mcp")
        return EventPage(events=events, next_cursor=next_cursor, checkpoint_cursor=checkpoint)

    @staticmethod
    def _event(row: Mapping[str, Any]) -> NormalizedEvent:
        occurred = row.get("trade_date") or row.get("date") or row.get("activity_date")
        identity = str(row.get("id") or row.get("activity_id") or hashlib.sha256(json.dumps(dict(row), sort_keys=True, default=str).encode()).hexdigest())
        side = str(row.get("type") or row.get("action") or "").upper() if row.get("type") or row.get("action") else None
        security = row.get("symbol") if isinstance(row.get("symbol"), Mapping) else {}
        exchange = security.get("exchange") or {}
        currency = SnapTradePersonalMCPConnection._code(row.get("currency"))
        quote_security = row.get("currency_universal_symbol") or {}
        if quote_security:
            currency = quote_security.get("symbol")
        revision = str(row.get("revision") or row.get("updated_at") or hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:24])
        return NormalizedEvent(identity, revision, str(row.get("account_id") or "unknown-account"),
            SnapTradePersonalMCPConnection._code(security.get("type")) or "unknown", str(security.get("symbol") or "unknown"),
            "fill" if side in {"BUY", "SELL"} else str(row.get("type") or "activity"), side if side in {"BUY", "SELL"} else None,
            row.get("units"), row.get("price"), currency, row.get("fee"), str(occurred) if occurred else None, None,
            data_quality="daily_cached", source="snaptrade-personal-mcp", metadata={"raw_type": row.get("type"), "amount": row.get("amount"),
            "instrument_id": security.get("id"), "market": exchange.get("mic_code") or "UNKNOWN", "timezone": exchange.get("timezone") or "unknown",
            "time_precision": "date" if len(str(occurred or "")) == 10 else "source_declared", "settlement_date": row.get("settlement_date")})

    def read_positions(self, credentials: CredentialBundle | None = None) -> tuple[NormalizedPosition, ...]:
        token = self._token(credentials)
        result = []
        for account in (self._accounts if self._accounts is not None else self.list_accounts(credentials)):
            rows = self._rows(self._call(token, "AccountInformation_getAllAccountPositions", {"accountId": account.account_id}))
            for row in rows:
                security = row.get("symbol") or {}
                security = security.get("symbol", security) if isinstance(security, Mapping) else {}
                if not isinstance(security, Mapping):
                    security = {"symbol": security}
                result.append(NormalizedPosition(account.account_id, "source_declared", str(security.get("symbol") or "unknown"), row.get("units") or row.get("quantity") or "0", row.get("average_purchase_price"), row.get("market_value"), self._code(row.get("currency")), row.get("as_of"), source="snaptrade-personal-mcp"))
        return tuple(result)

    @staticmethod
    def _code(value):
        return value.get("code") if isinstance(value, Mapping) else value

    def _refresh_if_needed(self, credentials):
        values = credentials.values
        if values.get("expires_at_epoch") and float(values["expires_at_epoch"]) <= time.time() + 30:
            if not values.get("refresh_token") or not values.get("client_id"):
                raise PermissionConnectionError("snaptrade_reauthorization_required")
            fresh = SnapTradeOAuthClient(oauth_http).refresh(refresh_token=values["refresh_token"], client_id=values["client_id"])
            if not fresh.get("refresh_token"):
                fresh["refresh_token"] = values["refresh_token"]
            fresh["expires_at_epoch"] = time.time() + float(fresh.get("expires_in") or 600)
            values.update(fresh)

    def disconnect(self) -> None:
        if self._credentials and self._credentials.values.get("access_token"):
            try:
                SnapTradeOAuthClient(oauth_http).revoke(token=self._credentials.values["access_token"])
            except Exception:
                # Local removal must still work offline. Provider revocation is
                # also available in the official Connected apps dashboard.
                self.remote_revocation_pending = True
        self._credentials, self._verified, self._disconnected = None, False, True


def oauth_http(method, url, payload):
    allowed = {"https://api.snaptrade.com/oauth/register/", "https://api.snaptrade.com/oauth/token/", "https://api.snaptrade.com/oauth/revoke_token/"}
    if method != "POST" or url not in allowed:
        raise ValueError("snaptrade_oauth_endpoint_not_allowed")
    registration = url.endswith("/register/")
    data = json.dumps(payload).encode() if registration else urllib.parse.urlencode(payload).encode()
    headers = {"Content-Type": "application/json" if registration else "application/x-www-form-urlencoded", "Accept": "application/json"}
    try:
        with open_without_redirect(urllib.request.Request(url, data=data, headers=headers, method="POST"), timeout=20) as response:
            content = response.read(1024 * 1024)
            return json.loads(content) if content else {}
    except Exception:
        raise PermissionConnectionError("snaptrade_oauth_request_failed") from None
