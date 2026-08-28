from datetime import datetime, timedelta, timezone

import pytest

from observer_bot.queue_monitor import QueueMonitor, QueueSnapshot


class MemoryStateRepository:
    def __init__(self):
        self.state = {}

    async def get_state(self, key):
        return dict(self.state.get(key, {}))

    async def set_state(self, key, value):
        self.state[key] = dict(value)


class FakeQueueClient:
    def __init__(self, results):
        self.results = iter(results)

    async def fetch(self):
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


class RecordingNotifier:
    def __init__(self):
        self.messages = []

    async def send_admins(self, text):
        self.messages.append(text)


@pytest.mark.asyncio
async def test_queue_monitor_alerts_once_then_recovers():
    repository = MemoryStateRepository()
    notifier = RecordingNotifier()
    client = FakeQueueClient(
        [
            QueueSnapshot(queue_size=25, accepting_workers=2, max_wait_seconds=300),
            QueueSnapshot(queue_size=26, accepting_workers=2, max_wait_seconds=320),
            QueueSnapshot(queue_size=2, accepting_workers=2, max_wait_seconds=20),
        ]
    )
    monitor = QueueMonitor(
        client=client,
        state_repository=repository,
        notifier=notifier,
        queue_size_threshold=20,
        wait_threshold_seconds=900,
        cooldown_seconds=1800,
        failure_threshold=3,
    )
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)

    await monitor.poll(now=now)
    await monitor.poll(now=now + timedelta(minutes=2))
    await monitor.poll(now=now + timedelta(minutes=4))

    assert len(notifier.messages) == 2
    assert "队列拥堵" in notifier.messages[0]
    assert "25" in notifier.messages[0]
    assert "队列恢复" in notifier.messages[1]


@pytest.mark.asyncio
async def test_queue_monitor_reports_repeated_central_failure_and_recovery():
    repository = MemoryStateRepository()
    notifier = RecordingNotifier()
    client = FakeQueueClient(
        [RuntimeError("offline"), RuntimeError("offline"), RuntimeError("offline"),
         QueueSnapshot(queue_size=0, accepting_workers=1, max_wait_seconds=0)]
    )
    monitor = QueueMonitor(
        client=client,
        state_repository=repository,
        notifier=notifier,
        queue_size_threshold=20,
        wait_threshold_seconds=900,
        cooldown_seconds=1800,
        failure_threshold=3,
    )
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)

    for minute in range(4):
        await monitor.poll(now=now + timedelta(minutes=minute))

    assert ["监控不可用" in text for text in notifier.messages] == [True, False]
    assert "监控恢复" in notifier.messages[1]


def test_queue_snapshot_uses_central_wait_details():
    snapshot = QueueSnapshot.from_payload(
        {
            "queue_size": 7,
            "accepting_workers": 0,
            "queue_by_type_details": {
                "image_to_video": {
                    "pending_count": 5,
                    "max_pending_wait_seconds": 1234.5,
                }
            },
        }
    )

    assert snapshot.queue_size == 7
    assert snapshot.accepting_workers == 0
    assert snapshot.max_wait_seconds == 1234
