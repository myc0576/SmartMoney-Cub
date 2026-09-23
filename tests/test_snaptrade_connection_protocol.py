"""Official-shaped structural fixtures, never real accounts or OAuth calls."""
from smartmoney_cub_harness.trader.connections.models import CredentialBundle
from smartmoney_cub_harness.trader.connections.snaptrade import SnapTradePersonalMCPConnection


class MCPFixture:
    def initialize(self, token):
        return {"protocolVersion": "2025-06-18"}

    def list_tools(self, token):
        return [{"name": name, "inputSchema": {"type": "object", "properties": {key: {} for key in required}, "required": required}}
                for name, required in (("Connections_listBrokerageAuthorizations", []),
                    ("Connections_listBrokerageAuthorizationAccounts", ["authorizationId"]),
                    ("AccountInformation_getAccountActivities", ["accountId"]),
                    ("AccountInformation_getAllAccountPositions", ["accountId"]))]

    def call(self, token, tool, arguments):
        assert token == "toy-read-token"
        if tool == "Connections_listBrokerageAuthorizations":
            return [{"id": "toy-authorization"}]
        if tool == "Connections_listBrokerageAuthorizationAccounts":
            assert arguments["authorizationId"] == "toy-authorization"
            return [{"id": "toy-account", "name": "Toy account", "currency": {"code": "CAD"}}]
        assert arguments["accountId"] == "toy-account"
        if tool == "AccountInformation_getAllAccountPositions":
            return []
        assert tool == "AccountInformation_getAccountActivities"
        if arguments["offset"]:
            return {"data": [], "pagination": {"total": 1}}
        return {"data": [{"id": "toy-activity", "type": "BUY", "symbol": {
            "id": "toy-security", "symbol": "TOY.TO", "type": {"code": "cs"},
            "exchange": {"mic_code": "XTSE", "timezone": "America/Toronto"}},
            "currency": {"code": "CAD"}, "units": 0.5, "price": 20, "fee": 1,
            "trade_date": "2026-08-01"}], "pagination": {"total": 1}}


def test_snaptrade_reads_accounts_then_scoped_activity_and_preserves_precision():
    connection = SnapTradePersonalMCPConnection(CredentialBundle("snaptrade-personal-mcp", {"access_token": "toy-read-token", "scope": "read"}), transport=MCPFixture())
    assert connection.validate_read_access().allowed
    assert connection.list_accounts()[0].currency == "CAD"
    page = connection.read_events()
    event = page.events[0]
    assert event.account_id == "toy-account"
    assert event.symbol == "TOY.TO"
    assert event.currency == "CAD"
    assert event.metadata["instrument_id"] == "toy-security"
    assert event.metadata["time_precision"] == "date"
    assert event.available_at is None
    # A completed newest-first history scan must restart at the beginning next
    # sync so new recent fills/revisions cannot be skipped forever.
    assert not page.checkpoint_cursor.token
