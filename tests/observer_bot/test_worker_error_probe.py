from datetime import datetime, timedelta, timezone

import pytest

from observer_bot.worker_error_probe import (
    WorkerErrorProbe,
    WorkerOutcomeSnapshot,
    WorkerOutcomeStats,
)


class MemoryStateRepository:
    def __init__(self):
        self.state = {}

    async def get_state(self, key):
        return dict(self.state.get(key, {}))

    async def set_state(self, key, value):
        self.state[key] = dict(value)


class FakeClient:
    def __init__(self, results):
        self.results = iter(results)

    async def fetch_worker_outcomes(self, *, window_seconds):
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        assert result.window_seconds == window_seconds
        return result


class RecordingNotifier:
    def __init__(self):
        self.messages = []

    async def send_admins(self, text):
        self.messages.append(text)


def _snapshot(*, failed, total, last_failure_at=1_788_200_000.0):
    return WorkerOutcomeSnapshot(
        window_seconds=3600,
        workers=(
            WorkerOutcomeStats(
                worker_id="runpod_prod_minimax_h3_manual_02",
                status="running",
                total_tasks=total,
                failed_tasks=failed,
                failure_rate=(failed / total if total else 0.0),
                failures_by_type={"minimax_h3_i2v": failed},
                last_failure_at=last_failure_at if failed else None,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_worker_error_probe_alerts_once_then_recovers():
    repository = MemoryStateRepository()
    notifier = RecordingNotifier()
    probe = WorkerErrorProbe(
        client=FakeClient(
            [
                _snapshot(failed=7, total=10),
                _snapshot(failed=8, total=11),
                _snapshot(failed=1, total=10),
            ]
        ),
        state_repository=repository,
        notifier=notifier,
        cooldown_seconds=3600,
        failure_threshold=3,
    )
    now = datetime(2026, 8, 31, 14, tzinfo=timezone.utc)

    for minute in (0, 5, 10):
        await probe.poll(
            window_seconds=3600,
            minimum_tasks=5,
            minimum_failures=3,
            failure_rate_threshold=0.5,
            now=now + timedelta(minutes=minute),
        )

    assert len(notifier.messages) == 2
    assert "Worker 失败率过高" in notifier.messages[0]
    assert "runpod_prod_minimax_h3_manual_02" in notifier.messages[0]
    assert "7/10（70.0%）" in notifier.messages[0]
    assert "minimax_h3_i2v: 7" in notifier.messages[0]
    assert "Worker 失败率恢复" in notifier.messages[1]


@pytest.mark.asyncio
async def test_worker_error_probe_requires_both_minimum_sample_and_failure_rate():
    notifier = RecordingNotifier()
    probe = WorkerErrorProbe(
        client=FakeClient(
            [
                _snapshot(failed=3, total=3),
                _snapshot(failed=3, total=10),
                _snapshot(failed=2, total=5),
            ]
        ),
        state_repository=MemoryStateRepository(),
        notifier=notifier,
        cooldown_seconds=3600,
        failure_threshold=3,
    )

    for minute in range(3):
        await probe.poll(
            window_seconds=3600,
            minimum_tasks=5,
            minimum_failures=3,
            failure_rate_threshold=0.5,
            now=datetime(2026, 8, 31, 14, minute * 5, tzinfo=timezone.utc),
        )

    assert notifier.messages == []


def test_worker_outcome_snapshot_parses_central_payload():
    snapshot = WorkerOutcomeSnapshot.from_payload(
        {
            "window_seconds": 3600,
            "workers": [
                {
                    "worker_id": "worker-1",
                    "status": "idle",
                    "total_tasks": 10,
                    "failed_tasks": 6,
                    "failure_rate": 0.6,
                    "failures_by_type": {"image_to_video": 4, "img2img": 2},
                    "last_failure_at": 123.0,
                }
            ],
        }
    )

    assert snapshot.workers[0].failed_tasks == 6
    assert snapshot.workers[0].failures_by_type == {
        "image_to_video": 4,
        "img2img": 2,
    }
