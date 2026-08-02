from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable

from telegram.request import HTTPXRequest

logger = logging.getLogger("qqcc_bot.polling_liveness")


class QqccPollingLivenessWatchdog:
    """Restart the official QQCC process only when getUpdates polling stalls."""

    def __init__(
        self,
        *,
        stale_after_seconds: float = 180.0,
        check_interval_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
        exit_func: Callable[[int], object] = os._exit,
    ) -> None:
        self._stale_after_seconds = float(stale_after_seconds)
        self._check_interval_seconds = float(check_interval_seconds)
        self._clock = clock
        self._exit_func = exit_func
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_poll_completed_at = self._clock()
        self._tripped = False

    def record_poll_success(self, payload: bytes) -> None:
        with self._lock:
            self._last_poll_completed_at = self._clock()

    def mark_update_completed(self, update_id: int) -> None:
        # Kept as a compatibility hook for the final handler group. Business
        # backlog is not a polling failure and must never restart the process.
        return None

    def check_once(self) -> bool:
        now = self._clock()
        with self._lock:
            if self._tripped:
                return True
            poll_age = now - self._last_poll_completed_at
            if poll_age <= self._stale_after_seconds:
                return False
            self._tripped = True

        logger.critical(
            "QQCC polling liveness failed reason=get_updates_stalled "
            "poll_age_seconds=%.1f action=process_restart",
            poll_age,
        )
        self._exit_func(75)
        return True

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="qqcc-polling-watchdog",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self._check_interval_seconds * 2))
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self._check_interval_seconds):
            if self.check_once():
                return


class QqccPollingHeartbeatRequest(HTTPXRequest):
    def __init__(
        self,
        watchdog: QqccPollingLivenessWatchdog,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._watchdog = watchdog

    async def do_request(self, *args, **kwargs):
        status_code, payload = await super().do_request(*args, **kwargs)
        if 200 <= status_code < 300:
            self._watchdog.record_poll_success(payload)
        return status_code, payload
