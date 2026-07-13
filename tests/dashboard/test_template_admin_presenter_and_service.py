from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import MINIO_TEMPLATE_BUCKET
from dashboard.backend.presenters import template_admin_presenter
from dashboard.backend.services import template_admin_service


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


class _FakeStorage:
    def __init__(self):
        self.calls = []
        self.client = SimpleNamespace(
            copy_object=lambda *args, **kwargs: self.calls.append(("copy", args, kwargs)),
            remove_object=lambda *args, **kwargs: self.calls.append(("remove", args, kwargs)),
        )

    def get_presigned_url(self, object_name, bucket=None):
        self.calls.append(("presigned", object_name, bucket))
        return f"url://{bucket}/{object_name}"


class _FakeTemplateDb:
    def __init__(self, execute_results):
        self.execute_results = list(execute_results)
        self.commit = AsyncMock()

    async def execute(self, _stmt):
        if not self.execute_results:
            raise AssertionError("unexpected execute call")
        return self.execute_results.pop(0)


def _build_contribution(**overrides):
    base = {
        "id": 1,
        "user_id": 123,
        "file_path": "temps/demo.png",
        "file_type": "photo",
        "is_reviewed": False,
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_template_contribution_response_generates_preview_url():
    storage_service = _FakeStorage()
    contribution = _build_contribution(file_path="folder/demo.mp4", file_type="video", is_reviewed=True)

    result = template_admin_presenter.build_template_contribution_response(
        contribution=contribution,
        username="tester",
        full_name="Tester",
        storage_service=storage_service,
    )

    assert result.preview_url == f"url://{MINIO_TEMPLATE_BUCKET}/video_nice/demo.mp4"
    assert result.username == "tester"
    assert result.file_type == "video"


@pytest.mark.asyncio
async def test_get_template_contributions_payload_uses_presenter():
    storage_service = _FakeStorage()
    contribution = _build_contribution()
    db = _FakeTemplateDb([_RowsResult([(contribution, "tester", "Tester")])])

    result = await template_admin_service.get_template_contributions_payload(
        db=db,
        storage_service=storage_service,
    )

    assert len(result) == 1
    assert result[0].preview_url == f"url://{MINIO_TEMPLATE_BUCKET}/temps/demo.png"


@pytest.mark.asyncio
async def test_approve_contribution_payload_marks_reviewed_and_rewards_user(monkeypatch):
    contribution = _build_contribution(file_path="temps/demo.png", file_type="photo", is_reviewed=False)
    user = SimpleNamespace(id=123, credits=5, approved_contributions=1)
    db = _FakeTemplateDb([_ScalarResult(contribution), _ScalarResult(user)])
    storage_service = _FakeStorage()

    class _FakeCopySource:
        def __init__(self, bucket, object_name):
            self.bucket = bucket
            self.object_name = object_name

    monkeypatch.setattr("minio.commonconfig.CopySource", _FakeCopySource)

    result = await template_admin_service.approve_contribution_payload(
        contribution_id=1,
        db=db,
        storage_service=storage_service,
    )

    assert result["status"] == "ok"
    assert contribution.is_reviewed is True
    assert contribution.file_path == "quick_face/demo.png"
    assert user.credits == 15
    assert user.approved_contributions == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_contribution_payload_deletes_object_and_row():
    contribution = _build_contribution(file_path="quick_face/demo.png", is_reviewed=True)
    db = _FakeTemplateDb([_ScalarResult(contribution), _ScalarResult(None)])
    storage_service = _FakeStorage()

    result = await template_admin_service.delete_contribution_payload(
        contribution_id=1,
        db=db,
        storage_service=storage_service,
    )

    assert result == {"status": "ok", "message": "Contribution deleted"}
    assert any(call[0] == "remove" for call in storage_service.calls)
    db.commit.assert_awaited_once()
