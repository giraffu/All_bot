import json

import pytest

from dashboard.backend.services import worker_listener


class _FakeRedis:
    def __init__(self):
        self.hashes = {}

    async def set(self, *_args, **_kwargs):
        return True

    async def hset(self, key, *, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    async def hsetnx(self, key, field, value):
        values = self.hashes.setdefault(key, {})
        if field in values:
            return False
        values[field] = value
        return True

    async def expire(self, *_args, **_kwargs):
        return True

    async def delete(self, key):
        self.hashes.pop(key, None)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hget(self, _key, _field):
        return None


class _FakeSelect:
    def where(self, *_args, **_kwargs):
        return self


class _FakeExecuteResult:
    def scalars(self):
        return self

    def first(self):
        return None


class _FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return _FakeExecuteResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_process_message_uses_event_payload_when_redis_details_missing(
    monkeypatch,
):
    fake_session = _FakeSession()
    warnings = []

    monkeypatch.setattr(worker_listener, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(worker_listener, "select", lambda _model: _FakeSelect())
    monkeypatch.setattr(
        worker_listener.logger,
        "warning",
        lambda message, *args, **kwargs: warnings.append(
            message % args if args else message
        ),
    )

    message = {
        "type": "pmessage",
        "channel": "comfy:task_events:task-123",
        "data": json.dumps(
            {
                "status": "done",
                "task_type": "img2img",
                "worker_id": "agent-test",
                "created_at": 1000.0,
                "result_path": "outputs/a.png",
            }
        ),
    }

    await worker_listener.process_message(message, _FakeRedis(), _FakeRedis())

    assert warnings == []
    assert fake_session.committed is True
    assert len(fake_session.added) == 1

    log_entry = fake_session.added[0]
    assert log_entry.task_id == "task-123"
    assert log_entry.worker_id == "agent-test"
    assert log_entry.task_type == "img2img"
    assert log_entry.status == "success"


@pytest.mark.asyncio
async def test_process_message_records_exact_gpu_phase_for_actual_all_worker_task(
    monkeypatch,
):
    fake_session = _FakeSession()
    fake_worker_redis = _FakeRedis()
    times = iter([1_000.0, 1_030.0])

    monkeypatch.setattr(worker_listener, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(worker_listener, "select", lambda _model: _FakeSelect())
    monkeypatch.setattr(worker_listener, "_now_timestamp", lambda: next(times))

    await worker_listener.process_message(
        {
            "channel": "comfy:task_events:task-all-1",
            "data": json.dumps({"status": "running", "execution_phase": "running"}),
        },
        fake_worker_redis,
        _FakeRedis(),
    )
    await worker_listener.process_message(
        {
            "channel": "comfy:task_events:task-all-1",
            "data": json.dumps({"status": "running", "execution_phase": "delivering"}),
        },
        fake_worker_redis,
        _FakeRedis(),
    )
    await worker_listener.process_message(
        {
            "channel": "comfy:task_events:task-all-1",
            "data": json.dumps(
                {
                    "status": "done",
                    "task_type": "minimax_h3_ref2v",
                    "worker_id": "lan_aio_prod_gpu226_gpu0_all_01",
                    "created_at": 100.0,
                }
            ),
        },
        fake_worker_redis,
        _FakeRedis(),
    )

    assert len(fake_session.added) == 1
    log_entry = fake_session.added[0]
    assert log_entry.worker_id == "lan_aio_prod_gpu226_gpu0_all_01"
    assert log_entry.task_type == "minimax_h3_ref2v"
    assert log_entry.duration == 30
    assert log_entry.start_time.timestamp() == pytest.approx(1_000.0)
    assert log_entry.end_time.timestamp() == pytest.approx(1_030.0)
    assert log_entry.error_message.startswith("dashboard_gpu_phase_v1|")
    assert "factor=1" in log_entry.error_message


@pytest.mark.asyncio
async def test_process_message_does_not_mark_unmapped_gpu_as_precise(monkeypatch):
    fake_session = _FakeSession()
    fake_worker_redis = _FakeRedis()
    times = iter([2_000.0, 2_010.0])

    monkeypatch.setattr(worker_listener, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(worker_listener, "select", lambda _model: _FakeSelect())
    monkeypatch.setattr(worker_listener, "_now_timestamp", lambda: next(times))

    for phase in ("running", "gpu_done"):
        await worker_listener.process_message(
            {
                "channel": "comfy:task_events:task-unknown-gpu",
                "data": json.dumps({"status": "running", "execution_phase": phase}),
            },
            fake_worker_redis,
            _FakeRedis(),
        )
    await worker_listener.process_message(
        {
            "channel": "comfy:task_events:task-unknown-gpu",
            "data": json.dumps(
                {
                    "status": "done",
                    "task_type": "ltx_video",
                    "worker_id": "runpod_prod_ltx_video_manual_99",
                    "created_at": 100.0,
                }
            ),
        },
        fake_worker_redis,
        _FakeRedis(),
    )

    log_entry = fake_session.added[0]
    assert log_entry.duration == 10
    assert log_entry.error_message == ""
