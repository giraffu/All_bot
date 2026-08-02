import json
from unittest.mock import AsyncMock

import pytest
from telegram.request import HTTPXRequest

from qqcc_bot.polling_liveness import (
    QqccPollingHeartbeatRequest,
    QqccPollingLivenessWatchdog,
)


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _poll_payload(*update_ids: int) -> bytes:
    return json.dumps(
        {
            "ok": True,
            "result": [{"update_id": update_id} for update_id in update_ids],
        }
    ).encode()


def test_watchdog_keeps_quiet_but_successful_polling_alive():
    clock = _Clock()
    exits = []
    watchdog = QqccPollingLivenessWatchdog(
        stale_after_seconds=10,
        clock=clock,
        exit_func=exits.append,
    )

    watchdog.record_poll_success(_poll_payload())
    clock.now = 9

    assert watchdog.check_once() is False
    assert exits == []


def test_watchdog_restarts_when_get_updates_stops_completing():
    clock = _Clock()
    exits = []
    watchdog = QqccPollingLivenessWatchdog(
        stale_after_seconds=10,
        clock=clock,
        exit_func=exits.append,
    )

    watchdog.record_poll_success(_poll_payload())
    clock.now = 11

    assert watchdog.check_once() is True
    assert exits == [75]


def test_watchdog_does_not_restart_for_business_backlog_while_polling_is_healthy():
    clock = _Clock()
    exits = []
    watchdog = QqccPollingLivenessWatchdog(
        stale_after_seconds=10,
        clock=clock,
        exit_func=exits.append,
    )

    watchdog.record_poll_success(_poll_payload(41))
    clock.now = 8
    watchdog.record_poll_success(_poll_payload())
    clock.now = 11

    assert watchdog.check_once() is False
    assert exits == []


def test_watchdog_clears_backlog_after_update_finishes_processing():
    clock = _Clock()
    exits = []
    watchdog = QqccPollingLivenessWatchdog(
        stale_after_seconds=10,
        clock=clock,
        exit_func=exits.append,
    )

    watchdog.record_poll_success(_poll_payload(41))
    watchdog.mark_update_completed(41)
    clock.now = 9
    watchdog.record_poll_success(_poll_payload())
    clock.now = 18

    assert watchdog.check_once() is False
    assert exits == []


@pytest.mark.asyncio
async def test_get_updates_request_records_only_successful_round_trip(monkeypatch):
    clock = _Clock()
    exits = []
    watchdog = QqccPollingLivenessWatchdog(
        stale_after_seconds=10,
        clock=clock,
        exit_func=exits.append,
    )
    payload = _poll_payload()
    monkeypatch.setattr(
        HTTPXRequest,
        "do_request",
        AsyncMock(return_value=(200, payload)),
    )
    request = QqccPollingHeartbeatRequest(watchdog)

    clock.now = 8
    assert await request.do_request("http://telegram.local/getUpdates", "POST") == (
        200,
        payload,
    )
    clock.now = 17

    assert watchdog.check_once() is False
    assert exits == []
