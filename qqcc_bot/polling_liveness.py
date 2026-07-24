from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable

from telegram.request import HTTPXRequest

logger = logging.getLogger("qqcc_bot.polling_liveness")


class QqccPollingLivenessWatchdog:
    """Restart only the official QQCC process when polling or processing stalls."""

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
        self._latest_fetched_update_id: int | None = None
        self._latest_completed_update_id: int | None = None
        self._unprocessed_since: float | None = None
        self._tripped = False

    def record_poll_success(self, payload: bytes) -> None:
        now = self._clock()
        update_ids: list[int] = []
        try:
            decoded = json.loads(payload)
            results = decoded.get("result", []) if isinstance(decoded, dict) else []
            update_ids = [
                int(item["update_id"])
                for item in results
                if isinstance(item, dict) and isinstance(item.get("update_id"), int)
            ]
        except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            logger.warning("QQCC polling heartbeat response could not be decoded")

        with self._lock:
            self._last_poll_completed_at = now
            if not update_ids:
                return
            latest = max(update_ids)
            if (
                self._latest_completed_update_id is None
                or latest > self._latest_completed_update_id
            ):
                if self._unprocessed_since is None:
                    self._unprocessed_since = now
                if (
                    self._latest_fetched_update_id is None
                    or latest > self._latest_fetched_update_id
                ):
                    self._latest_fetched_update_id = latest

    def mark_update_completed(self, update_id: int) -> None:
        with self._lock:
            if (
                self._latest_completed_update_id is None
                or update_id > self._latest_completed_update_id
            ):
                self._latest_completed_update_id = update_id
            if (
                self._latest_fetched_update_id is None
                or self._latest_completed_update_id >= self._latest_fetched_update_id
            ):
                self._unprocessed_since = None

    def check_once(self) -> bool:
        now = self._clock()
        with self._lock:
            if self._tripped:
                return True
            poll_age = now - self._last_poll_completed_at
            backlog_age = (
                now - self._unprocessed_since
                if self._unprocessed_since is not None
                else 0.0
            )
            reason = None
            if poll_age > self._stale_after_seconds:
                reason = "get_updates_stalled"
            elif backlog_age > self._stale_after_seconds:
                reason = "update_processing_stalled"
            if reason is None:
                return False
            self._tripped = True

        logger.critical(
            "QQCC polling liveness failed reason=%s poll_age_seconds=%.1f "
            "backlog_age_seconds=%.1f action=process_restart",
            reason,
            poll_age,
            backlog_age,
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
