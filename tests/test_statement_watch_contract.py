import threading

from smartmoney_cub_harness.trader.connections.watcher import StatementWatcher


def test_watch_retries_changes_and_stops_without_another_import():
    observed = threading.Event()
    calls = []
    def tick():
        calls.append(True)
        if len(calls) == 1:
            raise ValueError("toy_invalid_partial_statement")
        observed.set()
    watcher = StatementWatcher(tick, interval=0.01)
    watcher.start()
    assert observed.wait(1)
    watcher.close()
    before = len(calls)
    assert watcher.stopped
    assert len(calls) == before
