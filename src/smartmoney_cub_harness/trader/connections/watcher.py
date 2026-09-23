"""Opt-in local statement polling; no broker or export automation."""
from threading import Event, Thread, current_thread
from typing import Callable


class StatementWatcher:
    def __init__(self, tick: Callable[[], None], *, interval: float = 30) -> None:
        if interval <= 0:
            raise ValueError("watch_interval_must_be_positive")
        self._tick, self._interval = tick, interval
        self._stop = Event()
        self._thread = Thread(target=self._run, name="statement-watch", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                # An incomplete file can become valid on the next export.
                # The controller records a safe status; never log file contents.
                pass
            if self._stop.wait(self._interval):
                break

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive() and self._thread is not current_thread():
            self._thread.join(timeout=5)

    @property
    def stopped(self) -> bool:
        return self._stop.is_set() and not self._thread.is_alive()
