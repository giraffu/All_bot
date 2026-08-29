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
        cooldown_seconds=1800,
        failure_threshold=3,
    )
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)

    await monitor.poll(
        now=now,
        total_pending_threshold=20,
        type_pending_threshold=10,
    )
    await monitor.poll(
        now=now + timedelta(minutes=2),
        total_pending_threshold=20,
        type_pending_threshold=10,
    )
    await monitor.poll(
        now=now + timedelta(minutes=4),
        total_pending_threshold=20,
        type_pending_threshold=10,
    )

    assert len(notifier.messages) == 2
    assert "队列拥堵" in notifier.messages[0]
    assert "25" in notifier.messages[0]
    assert "队列恢复" in notifier.messages[1]


@pytest.mark.asyncio
async def test_queue_monitor_reports_repeated_central_failure_and_recovery():
    repository = MemoryStateRepository()
    notifier = RecordingNotifier()
    client = FakeQueueClient(
        [
            RuntimeError("offline"),
            RuntimeError("offline"),
            RuntimeError("offline"),
            QueueSnapshot(queue_size=0, accepting_workers=1, max_wait_seconds=0),
        ]
    )
    monitor = QueueMonitor(
        client=client,
        state_repository=repository,
        notifier=notifier,
        cooldown_seconds=1800,
        failure_threshold=3,
    )
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)

    for minute in range(4):
        await monitor.poll(
            now=now + timedelta(minutes=minute),
            total_pending_threshold=20,
            type_pending_threshold=10,
        )

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
    assert snapshot.pending_by_type == {"image_to_video": 5}


@pytest.mark.asyncio
async def test_queue_monitor_alerts_when_one_task_type_exceeds_its_threshold():
    repository = MemoryStateRepository()
    notifier = RecordingNotifier()
    monitor = QueueMonitor(
        client=FakeQueueClient(
            [
                QueueSnapshot(
                    queue_size=7,
                    accepting_workers=2,
                    max_wait_seconds=30,
                    pending_by_type={"image_to_video": 6, "text_to_image": 2},
                )
            ]
        ),
        state_repository=repository,
        notifier=notifier,
        cooldown_seconds=1800,
        failure_threshold=3,
    )

    await monitor.poll(
        now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        total_pending_threshold=20,
        type_pending_threshold=5,
    )

    assert len(notifier.messages) == 1
    assert "image_to_video" in notifier.messages[0]
    assert "待处理 6（单类型阈值 5）" in notifier.messages[0]
    assert "text_to_image" not in notifier.messages[0]


@pytest.mark.asyncio
async def test_queue_monitor_ignores_wait_time_and_worker_count_below_count_thresholds():
    repository = MemoryStateRepository()
    notifier = RecordingNotifier()
    monitor = QueueMonitor(
        client=FakeQueueClient(
            [
                QueueSnapshot(
                    queue_size=200,
                    accepting_workers=0,
                    max_wait_seconds=5_733,
                    pending_by_type={"image_to_image": 100, "text_to_image": 100},
                )
            ]
        ),
        state_repository=repository,
        notifier=notifier,
        cooldown_seconds=1800,
        failure_threshold=3,
    )

    await monitor.poll(
        now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        total_pending_threshold=200,
        type_pending_threshold=100,
    )

    assert notifier.messages == []


@pytest.mark.asyncio
async def test_queue_monitor_reports_only_count_thresholds_that_are_exceeded():
    repository = MemoryStateRepository()
    notifier = RecordingNotifier()
    monitor = QueueMonitor(
        client=FakeQueueClient(
            [
                QueueSnapshot(
                    queue_size=201,
                    accepting_workers=0,
                    max_wait_seconds=5_733,
                    pending_by_type={"image_to_image": 120, "text_to_image": 81},
                )
            ]
        ),
        state_repository=repository,
        notifier=notifier,
        cooldown_seconds=1800,
        failure_threshold=3,
    )

    await monitor.poll(
        now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        total_pending_threshold=200,
        type_pending_threshold=100,
    )

    assert notifier.messages == [
        "🚨 AllBot 队列拥堵\n"
        "• 待处理 201（总量阈值 200）\n"
        "• image_to_image 待处理 120（单类型阈值 100）"
    ]


@pytest.mark.asyncio
async def test_queue_monitor_does_not_send_recovery_for_legacy_wait_only_state():
    repository = MemoryStateRepository()
    repository.state["queue_monitor"] = {
        "congested": True,
        "last_notification_at": datetime(2026, 8, 29, tzinfo=timezone.utc).isoformat(),
    }
    notifier = RecordingNotifier()
    monitor = QueueMonitor(
        client=FakeQueueClient(
            [
                QueueSnapshot(
                    queue_size=190,
                    accepting_workers=0,
                    max_wait_seconds=5_733,
                    pending_by_type={"image_to_image": 95, "text_to_image": 95},
                )
            ]
        ),
        state_repository=repository,
        notifier=notifier,
        cooldown_seconds=1800,
        failure_threshold=3,
    )

    await monitor.poll(
        now=datetime(2026, 8, 29, 1, tzinfo=timezone.utc),
        total_pending_threshold=200,
        type_pending_threshold=100,
    )

    assert notifier.messages == []
