import json
from pathlib import Path

from smartmoney_cub_harness.trader.connections.local_statements import LocalStatementConnection
from smartmoney_cub_harness.trader.connections.controller import journal_row
from smartmoney_cub_harness.trader.connections.models import CredentialBundle


def test_directory_validates_actual_path_without_client_permission_boolean(tmp_path):
    (tmp_path / "toy.json").write_text(json.dumps([
        {"account_id": "toy", "symbol": "TOY", "side": "BUY", "quantity": "0.1", "price": "10", "trade_date": "2026-01-01", "trade_time": "14:25:03"},
        {"account_id": "toy", "symbol": "TOY", "side": "BUY", "quantity": "0.1", "price": "10", "trade_date": "2026-01-01", "trade_time": "14:25:03"}]))
    adapter = LocalStatementConnection(tmp_path, CredentialBundle("local-statement-directory"))
    assert adapter.validate_read_access().allowed
    page = adapter.read_events()
    assert len(page.events) == 2
    assert len({event.external_id for event in page.events}) == 2
    assert journal_row(page.events[0])["trade_time"] == "14:25:03"
    assert adapter.read_events(page.checkpoint_cursor).events == ()


def test_rotki_generic_trades_map_quote_pair_and_keep_fee_currency(tmp_path):
    (tmp_path / "rotki.csv").write_text("Location,Spend Currency,Spend Amount,Receive Currency,Receive Amount,Fee,Fee Currency,Timestamp\ntoy,USD,100,BTC,0.01,1,USD,1704067200000\n")
    adapter = LocalStatementConnection(tmp_path, CredentialBundle("local-statement-directory"))
    event = adapter.read_events().events[0]
    assert event.symbol == "BTC/USD"
    assert event.to_dict()["price"] == "10000"
    assert event.metadata["format"] == "rotki_generic_trades"
    assert event.account_id == "toy"


def test_directory_never_reads_symlinked_file_outside_selected_root(tmp_path):
    chosen = tmp_path / "chosen"
    chosen.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('[{"id":"must-not-read"}]')
    (chosen / "link.json").symlink_to(outside)
    assert not LocalStatementConnection(chosen).read_events().events
