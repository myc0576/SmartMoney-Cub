"""Synthetic terminal and HTTP fixtures; no vendor account access."""
from types import SimpleNamespace as NS

from smartmoney_cub_harness.trader.connections.models import CredentialBundle
from smartmoney_cub_harness.trader.connections.mt5 import MetaTraderInvestorConnection
from smartmoney_cub_harness.trader.connections.vezgo import VezgoConnection
from smartmoney_cub_harness.trader.connections.ccxt import CCXTConnection


class Terminal:
    def __init__(self, allowed=False):
        self.allowed = allowed

    def account_info(self):
        return NS(login=42, server="Toy", currency="USD", trade_allowed=self.allowed)

    def terminal_info(self):
        return NS(connected=True)

    def history_deals_get(self, start, end):
        return [NS(ticket=1, type=1, entry=0, symbol="EURUSD", volume=0.1,
                   price=1.2, time_msc=1704067200000, commission=-2, fee=0,
                   swap=0, profit=0, position_id=99, order=8)]

    def symbol_info(self, symbol):
        return NS(currency_profit="USD", trade_contract_size=100000)

    def positions_get(self):
        return []


def test_mt5_attaches_without_login_and_uses_short_effect_multiplier():
    connection = MetaTraderInvestorConnection(Terminal(), CredentialBundle("metatrader-investor"))
    assert connection.validate_read_access().allowed
    event = connection.read_events().events[0]
    assert event.side == "SELL_OPEN"
    assert event.metadata["multiplier"] == 100000
    assert event.currency == "USD"
    assert event.to_dict()["fee"] == "2"
    assert event.occurred_at == "2024-01-01T00:00:00+00:00"


def test_mt5_rejects_trade_enabled_or_unverifiable_terminal():
    assert not MetaTraderInvestorConnection(Terminal(True), CredentialBundle("metatrader-investor")).validate_read_access().allowed
    assert not MetaTraderInvestorConnection(Terminal(None), CredentialBundle("metatrader-investor")).validate_read_access().allowed


def test_mt5_fee_correction_changes_revision_but_not_event_identity():
    terminal = Terminal()
    deal = terminal.history_deals_get(None, None)[0]
    terminal.history_deals_get = lambda start, end: [deal]
    connection = MetaTraderInvestorConnection(terminal, CredentialBundle('metatrader-investor'))
    first = connection.read_events().events[0]
    deal.commission = -3
    second = connection.read_events().events[0]
    assert first.external_id == second.external_id
    assert first.revision != second.revision
    assert second.to_dict()['fee'] == '3'


class VezgoFixture:
    def __init__(self):
        self.calls = []

    def authenticate(self, values):
        assert values["login_name"] == "toy-user"
        return "toy-token"

    def get(self, path, token, params=None):
        self.calls.append((path, params))
        assert token == "toy-token"
        if path == "/accounts":
            return [{"id": "toy", "name": "Toy account", "balances": []}]
        assert path == "/accounts/toy/transactions"
        if params["last"]:
            return []
        return [{"id": "tx1", "transaction_type": "trade", "confirmed_at": 1704067200000,
                 "parts": [{"ticker": "BTC", "direction": "received", "amount": "0.01"},
                           {"ticker": "USD", "direction": "sent", "amount": "400"}],
                 "fees": [{"ticker": "USD", "amount": "1"}]}]


def test_vezgo_uses_vendor_auth_and_continues_after_short_page():
    transport = VezgoFixture()
    connection = VezgoConnection(transport, CredentialBundle("vezgo", {
        "client_id": "toy", "client_secret": "not-a-real-secret", "login_name": "toy-user"}))
    assert connection.validate_read_access().allowed
    first = connection.read_events()
    assert first.next_cursor is not None  # Short page is NOT proof of end.
    event = first.events[0]
    assert (event.symbol, event.side, event.to_dict()["price"]) == ("BTC/USD", "BUY", "40000")
    assert event.to_dict()["quantity"] == "0.01"
    second = connection.read_events(first.next_cursor)
    assert second.next_cursor is None
    assert all(params is None or params["from"] == "1970-01-01" for _, params in transport.calls)


def test_vezgo_ambiguous_swap_keeps_raw_event_without_fake_fill():
    row = {"id": "swap", "transaction_type": "trade", "confirmed_at": 1704067200000,
           "parts": [{"ticker": "BTC", "direction": "received", "amount": "1"},
                     {"ticker": "ETH", "direction": "sent", "amount": "10"}]}
    event = VezgoConnection.normalize(row, "toy")
    assert event.event_type == "unmapped_trade"
    assert event.price is None
    assert event.data_quality == "requires_mapping"


def test_ccxt_fee_asset_is_not_misused_as_price_currency():
    connection = CCXTConnection("ccxt-binance", object(), CredentialBundle("ccxt-binance"), symbols=["BTC/USDT"], account_id="toy")
    event = connection._normalize_trade("BTC/USDT", {"id": "1", "side": "buy", "amount": "0.1", "price": "50000", "fee": {"currency": "BNB", "cost": "0.0001"}}, 0)
    assert event.currency == "USDT"
    assert event.fee is None
    assert event.metadata["fee_components"] == [{"currency": "BNB", "cost": "0.0001"}]
