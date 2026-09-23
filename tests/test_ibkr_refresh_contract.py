"""Official-shaped toy Flex statements, never a live account."""
import pytest

from smartmoney_cub_harness.trader.connections.ibkr import IBKRFlexConnection
from smartmoney_cub_harness.trader.connections.models import CredentialBundle, NormalizedEvent


class FlexFixture:
    def __init__(self):
        self.version = 1
        self.pending = False

    def request(self, path, params):
        if path == "SendRequest":
            return b'<FlexStatementResponse><Status>Success</Status><ReferenceCode>toy</ReferenceCode></FlexStatementResponse>'
        if self.pending:
            return b'<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode><ErrorMessage>Statement generation in progress</ErrorMessage></FlexStatementResponse>'
        return f'''<FlexQueryResponse><FlexStatements><FlexStatement accountId="TOY-A"><Trades>
          <Trade tradeID="1" accountId="TOY-A" symbol="ES" conid="123" assetCategory="FUT" buySell="BUY" openCloseIndicator="O" quantity="0.25" tradePrice="5000" multiplier="50" currency="USD" ibCommission="-{self.version}" ibCommissionCurrency="USD" dateTime="20240101;100000"/>
        </Trades></FlexStatement></FlexStatements></FlexQueryResponse>'''.encode()


def connection(transport):
    return IBKRFlexConnection(transport, CredentialBundle("ibkr-flex", {"flex_token": "toy", "query_id": "1"}))


def test_flex_total_cost_is_not_misreported_as_unit_cost():
    class Positions(FlexFixture):
        def request(self, path, params):
            if path == 'SendRequest':
                return super().request(path, params)
            return b'<FlexQueryResponse><FlexStatements><FlexStatement accountId="TOY-A"><OpenPositions><OpenPosition accountId="TOY-A" symbol="TOY" position="10" costBasisMoney="200" currency="USD"/></OpenPositions></FlexStatement></FlexStatements></FlexQueryResponse>'
    position = connection(Positions()).read_positions()[0].to_dict()
    assert position['average_price'] is None


def test_flex_pending_report_is_not_verified_as_empty_success():
    transport = FlexFixture()
    transport.pending = True
    assert not connection(transport).validate_read_access().allowed


def test_flex_completed_sync_rescans_new_report_and_fee_corrections():
    transport = FlexFixture()
    adapter = connection(transport)
    assert adapter.validate_read_access().allowed
    first = adapter.read_events()
    assert first.next_cursor is None
    transport.version = 2
    second = adapter.read_events(first.checkpoint_cursor)
    assert len(second.events) == 1
    assert first.events[0].revision != second.events[0].revision
    assert second.events[0].to_dict()["fee"] == "2"


def test_flex_contract_metadata_and_accounts_do_not_fabricate():
    adapter = connection(FlexFixture())
    assert [row.account_id for row in adapter.list_accounts()] == ["TOY-A"]
    event = adapter.read_events().events[0]
    assert event.metadata["instrument_id"] == "123"
    assert event.metadata["multiplier"] == "50"
    assert event.available_at is None  # Settlement time is not availability.


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", True])
def test_connection_rejects_nonfinite_and_boolean_numbers(value):
    with pytest.raises(ValueError):
        NormalizedEvent("toy", 1, "a", "stock", "TOY", "fill", quantity=value)
