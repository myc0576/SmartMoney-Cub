from test_trader_api import _serve, _call
from smartmoney_cub_harness.trader.api import TraderService
from smartmoney_cub_harness.trader.auth import resolve_identity
from smartmoney_cub_harness.trader.connections.adapters import fixture_adapter
from smartmoney_cub_harness.trader.connections.models import ScopeValidation
from smartmoney_cub_harness.trader.connections.snaptrade import SnapTradeOAuthClient
from smartmoney_cub_harness.trader.connections.ibkr import IBKRFlexConnection
from test_ibkr_refresh_contract import FlexFixture


def fixture_oauth(method, url, payload):
    if url.endswith("/register/"):
        return {"client_id": "toy-client"}
    if url.endswith("/token/"):
        return {"access_token": "toy-oauth-token", "scope": "read", "refresh_token": "toy-refresh", "expires_in": 600}
    return {}


def oauth_adapter(provider, values, config):
    adapter = fixture_adapter(provider)
    adapter.validate_read_access = lambda bundle=None: ScopeValidation(True, "verified", granted=("read",))
    return adapter


def trusted_fixture(provider, values, config):
    adapter = fixture_adapter(provider)
    def verify(bundle=None):
        # This stands in for a provider permission endpoint, not client claims.
        assert bundle is None or bundle.permissions == {}
        return ScopeValidation(values.get("api_key") == "toy-read-key", "verified" if values.get("api_key") == "toy-read-key" else "denied")
    adapter.validate_read_access = verify
    return adapter


def test_connection_sync_reaches_real_journal_and_survives_restart(tmp_path):
    with _serve(tmp_path) as (base, service):
        service.connections.factory = trusted_fixture
        provider = "ccxt-binance"
        prefix = "/api/trader/connections/" + provider
        status, connected = _call(base, "POST", prefix + "/connect", body={
            "credentials": {"api_key": "toy-read-key"}, "config": {}})
        assert status == 200 and connected["status"] == "ok", connected
        assert "toy-read-key" not in str(connected)
        status, synced = _call(base, "POST", prefix + "/sync", body={})
        assert status == 200 and synced["imported_count"] == 4, synced
        assert len(service.store.list_trades("local")) == 4
        restarted = TraderService(service.store, connection_factory=trusted_fixture)
        result = restarted.connections.sync(resolve_identity({}, mode="local"), provider)
        assert result["imported_count"] == 0
        assert len(service.store.list_trades("local")) == 4
        status, disconnected = _call(base, "POST", prefix + "/disconnect", body={})
        assert status == 200 and disconnected["journal_preserved"]
        assert len(service.store.list_trades("local")) == 4
        status, blocked = _call(base, "POST", prefix + "/sync", body={})
        assert status == 200 and blocked["status"] == "error"


def test_client_permission_claim_cannot_enable_a_connection(tmp_path):
    with _serve(tmp_path) as (base, service):
        service.connections.factory = trusted_fixture
        status, result = _call(base, "POST", "/api/trader/connections/ccxt-binance/connect", body={
            "credentials": {"api_key": "toy-wrong-key", "permissions": {"read": True}},
            "permissions": {"read": True}})
        assert status == 200 and result["status"] == "error"
        assert service.store.list_trades("local") == []


def test_oauth_state_is_single_use_and_no_token_reaches_http_body(tmp_path):
    with _serve(tmp_path) as (base, service):
        service.connections.oauth_client = SnapTradeOAuthClient(fixture_oauth)
        service.connections.factory = oauth_adapter
        prefix = "/api/trader/connections/snaptrade-personal-mcp/oauth"
        status, start = _call(base, "POST", prefix + "/start", body={"redirect_uri": base + prefix + "/callback"})
        assert status == 200, start
        assert "dashboard.snaptrade.com/oauth/authorize" in start["authorization_url"]
        assert "scope=read" in start["authorization_url"]
        status, completed = _call(base, "POST", prefix + "/complete", body={"code": "toy-code", "state": start["state"]})
        assert status == 200 and completed["status"] == "ok"
        assert "toy-oauth-token" not in str(completed)
        status, repeated = _call(base, "POST", prefix + "/complete", body={"code": "toy-code", "state": start["state"]})
        assert status == 400
        assert repeated["error"] == "oauth_state_invalid_or_expired"


def test_pending_flex_connect_reuses_generated_reference(tmp_path):
    with _serve(tmp_path) as (base, service):
        transport = FlexFixture()
        transport.pending = True
        built = []
        def factory(provider, values, config):
            from smartmoney_cub_harness.trader.connections.models import CredentialBundle
            built.append(provider)
            return IBKRFlexConnection(transport, CredentialBundle(provider, values))
        service.connections.factory = factory
        prefix = "/api/trader/connections/ibkr-flex/connect"
        body = {"credentials": {"flex_token": "toy", "query_id": "1"}}
        assert _call(base, "POST", prefix, body=body)[1]["status"] == "error"
        transport.pending = False
        assert _call(base, "POST", prefix, body=body)[1]["status"] == "ok"
        assert built == ["ibkr-flex"]


def test_unmapped_execution_is_visible_as_partial_sync(tmp_path):
    with _serve(tmp_path) as (base, service):
        from dataclasses import replace
        def factory(provider, values, config):
            adapter = trusted_fixture(provider, values, config)
            adapter._events = (replace(adapter._events[0], event_type="unmapped_trade", data_quality="requires_mapping"),)
            return adapter
        service.connections.factory = factory
        prefix = "/api/trader/connections/ccxt-binance"
        _call(base, "POST", prefix + "/connect", body={"credentials": {"api_key": "toy-read-key"}})
        result = _call(base, "POST", prefix + "/sync", body={})[1]
        assert result["partial"] is True
        assert any("event_requires_mapping" in error for error in result["errors"])
