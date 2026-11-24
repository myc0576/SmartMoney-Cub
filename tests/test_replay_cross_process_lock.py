from __future__ import annotations

import multiprocessing
import time
from pathlib import Path

from smartmoney_cub_harness.trader.api.service import TraderService
from smartmoney_cub_harness.trader.auth.identity import LOCAL_CONTEXT
from smartmoney_cub_harness.trader.storage import open_store


def _bars() -> list[dict[str, object]]:
    return [
        {
            "symbol": "TOY-REPLAY",
            "interval": "1d",
            "open_time": f"2026-09-{day:02d}",
            "open": 10.0 + day,
            "high": 11.0 + day,
            "low": 9.0 + day,
            "close": 10.5 + day,
            "volume": 100.0,
        }
        for day in range(1, 5)
    ]


def _hold_replay_guard(root: str, entered, release) -> None:
    store = open_store(root, mode="local")
    service = TraderService(store, resume_watch=False)
    try:
        with service._replay_guard():
            entered.set()
            release.wait(10)
    finally:
        service.close()
        store.close()


def _step_replay(root: str, session_id: str, result) -> None:
    store = open_store(root, mode="local")
    service = TraderService(store, resume_watch=False)
    try:
        started = time.monotonic()
        response = service.replay_action(LOCAL_CONTEXT, session_id, {"action": "step"})
        result.put((response["session"]["index"], time.monotonic() - started))
    finally:
        service.close()
        store.close()


def test_replay_rmw_uses_one_root_lock_across_processes(tmp_path: Path) -> None:
    root = str(tmp_path / "shared-replay")
    store = open_store(root, mode="local")
    service = TraderService(store, resume_watch=False)
    try:
        session = service.create_replay_session(
            LOCAL_CONTEXT,
            {"symbol": "TOY-REPLAY", "interval": "1d", "bars": _bars()},
        )["session"]
        session_id = session["session_id"]
    finally:
        service.close()
        store.close()

    context = multiprocessing.get_context("spawn")
    entered = context.Event()
    release = context.Event()
    result = context.Queue()
    holder = context.Process(target=_hold_replay_guard, args=(root, entered, release))
    stepper = context.Process(target=_step_replay, args=(root, session_id, result))
    holder.start()
    assert entered.wait(10)
    stepper.start()
    time.sleep(0.25)
    assert result.empty()
    release.set()
    holder.join(10)
    stepper.join(10)
    assert holder.exitcode == 0
    assert stepper.exitcode == 0
    index, elapsed = result.get(timeout=5)
    assert index == 1
    assert elapsed >= 0.15
    final_store = open_store(root, mode="local")
    final_service = TraderService(final_store, resume_watch=False)
    try:
        assert final_service.replay_session(LOCAL_CONTEXT, session_id)["session"]["index"] == 1
    finally:
        final_service.close()
        final_store.close()
