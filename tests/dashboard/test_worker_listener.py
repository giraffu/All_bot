import json
from types import SimpleNamespace

import pytest

from dashboard.backend.services import worker_listener


class _FakeRedis:
    async def set(self, *_args, **_kwargs):
        return True

    async def hgetall(self, _key):
        return {}

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
async def test_process_message_uses_event_payload_when_redis_details_missing(monkeypatch):
    fake_session = _FakeSession()
    warnings = []

    monkeypatch.setattr(worker_listener, "AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(worker_listener, "select", lambda _model: _FakeSelect())
    monkeypatch.setattr(
        worker_listener.logger,
        "warning",
        lambda message, *args, **kwargs: warnings.append(message % args if args else message),
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
