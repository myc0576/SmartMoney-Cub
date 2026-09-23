from __future__ import annotations

import json

import pytest

from smartmoney_cub_harness.schemas import SAFETY_DECLARATION
from smartmoney_cub_harness.trader.connections import (
    ConnectionManager,
    LocalStatementConnection,
    ConnectionCursor,
    CredentialBundle,
    NormalizedEvent,
    SyncEngine,
    SyncState,
    all_fixture_adapters,
    fixture_adapter,
    list_manifests,
)
from smartmoney_cub_harness.trader.connections.models import validate_read_scope
from smartmoney_cub_harness.trader.connections.protocol import TransientConnectionError


def _read_credentials(provider_id: str, *scopes: str) -> CredentialBundle:
    scopes = scopes or ("read",)
    return CredentialBundle(
        provider_id,
        values={"api_key": "toy-secret", "api_secret": "toy-secret-2"},
        permissions={scope: True for scope in scopes},
    )


def test_all_manifests_have_public_metadata_and_safety() -> None:
    manifests = list_manifests()
    assert {manifest.provider_id for manifest in manifests} >= {
        "ccxt-binance",
        "ccxt-okx",
        "ibkr-flex",
        "metatrader-investor",
        "local-statement-directory",
        "snaptrade-personal-mcp",
        "vezgo",
    }
    for manifest in manifests:
        payload = manifest.to_dict()
        assert payload["safety"] == SAFETY_DECLARATION
        assert payload["official_links"]
        assert payload["auth"]["read_only"] is True
        assert payload["supported_assets"]
        assert payload["history"]["precision"]
        assert payload["validation"]["status"]
        forbidden = ("order", "cancel", "trade_execution", "account_mutation")
        assert not any(fragment in " ".join(payload["capabilities"]).lower() for fragment in forbidden)


def test_scope_unknown_is_a_hard_block_and_credentials_are_redacted() -> None:
    scope = validate_read_scope(("read",), CredentialBundle("snaptrade-personal-mcp", values={"token": "SECRET"}), provider_id="snaptrade-personal-mcp")
    assert scope.allowed is False
    assert scope.status == "unknown"
    rendered = json.dumps(CredentialBundle("x", values={"token": "SECRET", "api_key": "KEY"}).to_dict())
    assert "SECRET" not in rendered
    assert "KEY" not in rendered
    assert "[REDACTED]" in rendered


def test_cursor_is_durable_and_provider_bound() -> None:
    cursor = ConnectionCursor("ccxt-binance", "4", revision="4", as_of="2026-01-01T00:00:00Z")
    restored = ConnectionCursor.decode(cursor.encode())
    assert restored == cursor
    assert restored is not None
    with pytest.raises(ValueError):
        ConnectionCursor.decode(ConnectionCursor("ccxt-okx", "1").encode()).__class__.decode("bad")


def test_same_external_id_in_two_accounts_survives_sync_and_restart(tmp_path):
    adapter = fixture_adapter("ccxt-binance")
    original = adapter._events[0]
    adapter._events = tuple(NormalizedEvent(**{**original.to_dict(), "account_id": account}) for account in ("toy-a", "toy-b"))
    manager = ConnectionManager(state_path=tmp_path / "state.json")
    manager.register(adapter)
    manager.set_credentials("ccxt-binance", _read_credentials("ccxt-binance"))
    assert len(manager.sync("ccxt-binance").events) == 2
    assert len(manager.records("ccxt-binance")) == 2
    restarted = ConnectionManager(state_path=tmp_path / "state.json")
    restarted.register(adapter)
    assert len(restarted.records("ccxt-binance")) == 2


def test_adapter_exception_does_not_expose_credentials_in_sync_result():
    adapter = fixture_adapter("ccxt-binance")
    def fail(*args):
        raise RuntimeError("https://example.invalid?token=TOY-PRIVATE")
    adapter.read_events = fail
    result = SyncEngine(adapter, credentials=_read_credentials("ccxt-binance")).sync()
    assert result.partial
    assert "TOY-PRIVATE" not in str(result.to_dict())


def test_fixture_pagination_cursor_dedupe_revision_and_disconnect() -> None:
    adapter = fixture_adapter("ccxt-binance", page_size=2)
    credentials = _read_credentials("ccxt-binance")
    state = SyncState()
    first = SyncEngine(adapter, credentials=credentials, state=state).sync()
    assert len(first.events) == 4
    assert first.cursor is not None
    assert first.cursor.token == "4"
    assert state.cursor == first.cursor

    second = SyncEngine(adapter, credentials=credentials, state=state).sync()
    assert second.events == ()
    assert second.duplicate_count == 0

    replay = SyncEngine(adapter, credentials=credentials, state=SyncState()).sync(cursor=ConnectionCursor("ccxt-binance", "0"))
    assert len(replay.events) == 4

    adapter._events = tuple(
        event if event.external_id != "ccxt-binance-evt-2" else NormalizedEvent(**{**event.to_dict(), "revision": "2"})
        for event in adapter._events
    )
    revised = SyncEngine(adapter, credentials=credentials, state=state).sync(cursor=ConnectionCursor("ccxt-binance", "0"))
    assert revised.updated_count == 1
    assert revised.events[0].revision == "2"

    disconnected = SyncEngine(adapter, credentials=credentials, state=state).disconnect()
    assert disconnected.disconnected is True
    blocked_after_disconnect = SyncEngine(adapter, credentials=credentials, state=state).sync()
    assert blocked_after_disconnect.disconnected is False
    assert blocked_after_disconnect.events == ()


def test_partial_page_failure_is_visible_and_cursor_is_not_advanced() -> None:
    adapter = fixture_adapter("ibkr-flex", page_size=2, fail_pages=(1,))
    state = SyncState()
    result = SyncEngine(adapter, credentials=_read_credentials("ibkr-flex"), state=state).sync()
    assert result.partial is True
    assert result.errors
    assert result.cursor is not None
    assert result.cursor.token == "2"


class _RetryingConnection:
    def __init__(self) -> None:
        self.delegate = fixture_adapter("ccxt-okx", page_size=4)
        self.calls = 0

    def metadata(self):
        return self.delegate.metadata()

    def validate_read_access(self, credentials=None):
        return self.delegate.validate_read_access(credentials)

    def list_accounts(self, credentials=None):
        return self.delegate.list_accounts(credentials)

    def read_positions(self, credentials=None):
        return self.delegate.read_positions(credentials)

    def read_events(self, cursor=None, credentials=None):
        self.calls += 1
        if self.calls < 3:
            raise TransientConnectionError("toy transient")
        return self.delegate.read_events(cursor, credentials)

    def disconnect(self):
        return self.delegate.disconnect()


def test_retries_are_bounded_and_counted() -> None:
    connection = _RetryingConnection()
    result = SyncEngine(connection, credentials=_read_credentials("ccxt-okx"), max_attempts=3).sync()
    assert result.attempts == 3
    assert len(result.events) == 4


def test_all_fixture_adapters_are_offline_and_read_only() -> None:
    adapters = all_fixture_adapters()
    assert len(adapters) == len(list_manifests())
    for adapter in adapters:
        assert not hasattr(adapter, "create_order")
        assert not hasattr(adapter, "cancel_order")
        assert adapter.metadata().safety == SAFETY_DECLARATION


class _ToyTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def call(self, method: str, params=None):
        self.calls.append((method, dict(params or {})))
        if method == "list_accounts":
            return [{"id": "acct-1", "name": "Toy", "asset_class": "crypto", "currency": "USD"}]
        if method == "read_events":
            return {"data": [{"id": "remote-1", "symbol": "BTC/USDT", "quantity": "0.5", "price": "10"}], "next_cursor": None}
        if method == "read_positions":
            return [{"account_id": "acct-1", "symbol": "BTC/USDT", "quantity": "0.5", "asset": "crypto"}]
        raise AssertionError(method)


def test_transport_adapter_normalizes_structural_calls_without_mutation() -> None:
    from smartmoney_cub_harness.trader.connections import TransportConnection

    transport = _ToyTransport()
    connection = TransportConnection("ccxt-binance", transport, _read_credentials("ccxt-binance"))
    assert len(connection.list_accounts()) == 1
    page = connection.read_events()
    assert page.events[0].external_id == "remote-1"
    assert connection.read_positions()[0].quantity == "0.5"
    assert all(method in {"list_accounts", "read_events", "read_positions"} for method, _ in transport.calls)


def test_local_statement_connection_reads_only_user_selected_files(tmp_path) -> None:
    (tmp_path / "statement.csv").write_text("id,symbol,quantity,price,account_id,asset\nlocal-1,AAPL,2,100,acct,stocks\n", encoding="utf-8")
    connection = LocalStatementConnection(tmp_path, CredentialBundle("local-statement-directory", permissions={"read": True}))
    page = connection.read_events()
    assert page.events[0].external_id == "local-1"
    assert page.events[0].source == "local-statement-directory"
    assert page.checkpoint_cursor is not None
    assert connection.read_events(page.checkpoint_cursor).events == ()


class _ToyExchange:
    def __init__(self, permissions=None):
        self.permissions = permissions

    def fetch_api_restrictions(self, params=None):
        return self.permissions if self.permissions is not None else {"status": "ok"}

    def fetch_balance(self, params=None):
        return []

    def fetch_my_trades(self, params=None):
        return []


def test_ccxt_permission_fact_must_be_reported_by_exchange() -> None:
    from smartmoney_cub_harness.trader.connections import CCXTReadOnlyConnection

    credentials = _read_credentials("ccxt-binance")
    unknown = CCXTReadOnlyConnection(_ToyExchange(), "ccxt-binance", credentials)
    assert unknown.validate_read_access().allowed is False
    assert unknown.validate_read_access().status == "unknown"
    allowed = CCXTReadOnlyConnection(CCXTRestrictionExchange({"enableReading": True, "enableSpotAndMarginTrading": False, "enableMargin": False, "enableFutures": False, "enableWithdrawals": False, "enableInternalTransfer": False, "enablePortfolioMarginTrading": False}), "ccxt-binance", credentials)
    assert allowed.validate_read_access().allowed is True


class CCXTRestrictionExchange(_ToyExchange):
    def fetch_api_restrictions(self, params=None):
        return self.permissions


class _DirectCCXT:
    def __init__(self):
        self.calls = []

    def check_required_credentials(self):
        self.calls.append("credentials")

    def sapiGetAccountApiRestrictions(self, params=None):
        return {"enableReading": True, "enableSpotAndMarginTrading": False, "enableWithdrawals": False, "enableMargin": False, "enableFutures": False, "enableInternalTransfer": False, "permitsUniversalTransfer": False, "enableVanillaOptions": False, "enableFixApiTrade": False, "enablePortfolioMarginTrading": False}

    def fetch_balance(self, params=None):
        return {"total": {"BTC": "0.5"}, "info": {"uid": "binance-user"}}

    def fetch_my_trades(self, symbol, since=None, limit=None, params=None):
        self.calls.append((symbol, since, limit))
        if symbol == "BTC/USDT":
            return [{"id": "trade-1", "symbol": symbol, "timestamp": 1000, "datetime": "1970-01-01T00:00:01Z", "side": "buy", "amount": "0.5", "price": "10", "fee": {"cost": "0.01", "currency": "USDT"}}]
        return []


def test_direct_ccxt_adapter_uses_private_restrictions_and_cursor() -> None:
    from smartmoney_cub_harness.trader.connections import CCXTConnection

    exchange = _DirectCCXT()
    credentials = CredentialBundle("ccxt-binance", {"api_key": "toy", "api_secret": "toy"})
    connection = CCXTConnection("ccxt-binance", exchange, credentials, symbols=["BTC/USDT", "ETH/USDT"], limit=100)
    assert connection.validate_read_access().allowed is True
    page = connection.read_events()
    assert page.events[0].external_id == "trade-1"
    assert page.next_cursor is not None
    assert connection.read_events(page.next_cursor).events == ()
    assert any(call[0] == "BTC/USDT" for call in exchange.calls if isinstance(call, tuple))


class _FlexTransport:
    def request(self, path, params):
        if path.lower().endswith("sendrequest"):
            return b'<FlexStatementResponse status="Success" referenceCode="toy-reference" />'
        return b'<FlexQueryResponse><Trade tradeID="flex-1" accountId="U1" symbol="AAPL" dateTime="2026-01-01, 10:00:00" buySell="BUY" quantity="2" tradePrice="100" currency="USD" settleDateTarget="2026-01-03" /></FlexQueryResponse>'


def test_ibkr_flex_adapter_uses_two_step_xml_report() -> None:
    from smartmoney_cub_harness.trader.connections import FlexTransport, IBKRFlexConnection

    credentials = CredentialBundle("ibkr-flex", {"flex_token": "toy", "query_id": "1"}, {"read": True})
    connection = IBKRFlexConnection(_FlexTransport(), credentials, account_id="U1")
    page = connection.read_events()
    assert page.events[0].external_id == "flex-1"
    assert page.events[0].symbol == "AAPL"


def test_snaptrade_oauth_is_pkce_read_only_and_never_returns_secret() -> None:
    from smartmoney_cub_harness.trader.connections import SnapTradeOAuthClient

    calls = []
    def http(method, url, payload):
        calls.append((method, url, payload))
        if url.endswith("register"):
            return {"client_id": "toy-client", "client_secret": "must-not-leak"}
        if url.endswith("token") and payload.get("code"):
            return {"access_token": "toy-access", "scope": "read", "expires_in": 300}
        return {}

    oauth = SnapTradeOAuthClient(http, registration_endpoint="https://toy/register", token_endpoint="https://toy/token", authorization_endpoint="https://toy/authorize", revocation_endpoint="https://toy/revoke")
    registration = oauth.register_dynamic_client(redirect_uri="http://localhost/callback")
    assert registration["client_secret"] is None
    url, verifier = oauth.authorization_url(client_id=registration["client_id"], redirect_uri=registration["redirect_uri"])
    assert "scope=read" in url and "code_challenge=" in url
    token = oauth.exchange_code(code="toy-code", verifier=verifier, client_id="toy-client", redirect_uri="http://localhost/callback")
    assert token["scope"] == "read"
    assert "must-not-leak" not in json.dumps(registration)
    assert "dashboard.snaptrade.com" in SnapTradeOAuthClient(http).authorization_endpoint


def test_manager_persists_only_cursor_metadata_and_revokes_secrets(tmp_path) -> None:
    state_path = tmp_path / "connections.json"
    adapter = fixture_adapter("ccxt-binance", page_size=2)
    manager = ConnectionManager(state_path=state_path)
    manager.register(adapter)
    manager.set_credentials("ccxt-binance", _read_credentials("ccxt-binance"))
    assert manager.status("ccxt-binance")["scope"]["status"] == "unverified"
    result = manager.sync("ccxt-binance", max_pages=1)
    assert len(result.events) == 2
    assert result.partial is True
    status = manager.status("ccxt-binance")
    assert status["credential_values"] == "[REDACTED]"
    raw = state_path.read_text(encoding="utf-8")
    assert "toy-secret" not in raw
    assert "ccxt-binance" in raw

    restarted = ConnectionManager(state_path=state_path)
    restarted.register(fixture_adapter("ccxt-binance", page_size=4))
    assert restarted.status("ccxt-binance")["cursor"]["token"] == "2"

    revoked = manager.revoke("ccxt-binance")
    assert revoked.disconnected is True
    assert manager.status("ccxt-binance")["connected"] is False
    blocked = manager.sync("ccxt-binance")
    assert blocked.blocked is True


def test_manager_keeps_credentials_in_separate_private_file(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    credentials_path = tmp_path / "secrets" / "credentials.json"
    manager = ConnectionManager(state_path=state_path, credentials_path=credentials_path)
    manager.register(fixture_adapter("ccxt-binance"))
    manager.set_credentials("ccxt-binance", _read_credentials("ccxt-binance"))
    assert credentials_path.exists()
    assert credentials_path.stat().st_mode & 0o077 == 0
    assert "toy-secret" in credentials_path.read_text(encoding="utf-8")
    assert "toy-secret" not in state_path.read_text(encoding="utf-8")

    restarted = ConnectionManager(state_path=state_path, credentials_path=credentials_path)
    restarted.register(fixture_adapter("ccxt-binance"))
    assert restarted.credentials("ccxt-binance") is not None
    restarted.clear_credentials("ccxt-binance")
    assert restarted.credentials("ccxt-binance") is None
