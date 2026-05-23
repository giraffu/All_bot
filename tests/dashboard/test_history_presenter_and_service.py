from datetime import datetime
from types import SimpleNamespace

import pytest

from config import MINIO_TEMPLATE_BUCKET
from dashboard.backend.presenters import history_presenter
from dashboard.backend.services import history_service


class _FakeStorage:
    def __init__(self):
        self.calls = []

    def get_presigned_url(self, object_name, bucket=None):
        self.calls.append((object_name, bucket))
        suffix = bucket or "default"
        return f"url://{suffix}/{object_name}"


class _FakeScalarResult:
    def __init__(self, scalar_value=0):
        self._scalar_value = scalar_value

    def scalar(self):
        return self._scalar_value


class _FakeRowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeHistoryDb:
    def __init__(self, total, rows):
        self.total = total
        self.rows = list(rows)
        self.execute_calls = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _FakeScalarResult(self.total)
        return _FakeRowsResult(self.rows)


def _build_history(**overrides):
    base = {
        "id": 1,
        "user_id": 123,
        "task_id": "task-1",
        "type": "img2img",
        "input_file": "template:tpl/a.png|user/input.png",
        "output_file": "result.png",
        "prompt": "hello",
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
        "rating": 1,
        "is_public": True,
        "source": "bot",
    }
    base.update(overrides)
    obj = SimpleNamespace(**base)
    obj.__table__ = SimpleNamespace(columns=[SimpleNamespace(name=k) for k in base.keys()])
    return obj


def test_build_history_item_payload_generates_storage_urls():
    storage_service = _FakeStorage()
    history = _build_history()

    result = history_presenter.build_history_item_payload(
        history=history,
        username="tester",
        full_name="Tester",
        worker_id="worker-1",
        storage_service=storage_service,
    )

    assert result["username"] == "tester"
    assert result["full_name"] == "Tester"
    assert result["worker_id"] == "worker-1"
    assert result["input_file_url"] == (
        f"url://{MINIO_TEMPLATE_BUCKET}/tpl/a.png|url://default/user/input.png"
    )
    assert result["output_file_url"] == "url://comfyui-temp/result.png"


@pytest.mark.asyncio
async def test_get_all_history_payload_uses_presenter_for_items():
    storage_service = _FakeStorage()
    history = _build_history()
    db = _FakeHistoryDb(total=1, rows=[(history, "tester", "Tester", "worker-1")])

    result = await history_service.get_all_history_payload(
        db=db,
        page=1,
        page_size=20,
        storage_service=storage_service,
    )

    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["username"] == "tester"
    assert result["items"][0]["worker_id"] == "worker-1"
    assert result["items"][0]["input_file_url"].startswith("url://")


@pytest.mark.asyncio
async def test_get_user_history_payload_uses_presenter_for_items():
    storage_service = _FakeStorage()
    history = _build_history(output_file="folder/output.png")
    db = _FakeRowsResult([(history, "worker-2")])

    class _FakeUserHistoryDb:
        async def execute(self, _stmt):
            return db

    result = await history_service.get_user_history_payload(
        user_id=123,
        db=_FakeUserHistoryDb(),
        storage_service=storage_service,
    )

    assert len(result) == 1
    assert result[0]["worker_id"] == "worker-2"
    assert result[0]["output_file_url"] == "url://default/folder/output.png"
