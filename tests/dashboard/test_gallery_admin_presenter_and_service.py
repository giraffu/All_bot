from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dashboard.backend.presenters import gallery_admin_presenter
from dashboard.backend.services import gallery_admin_service


class _FakeStorage:
    def __init__(self):
        self.calls = []

    def get_file_url(self, output_file):
        self.calls.append(("file", output_file))
        return f"file://{output_file}"

    def get_presigned_url(self, output_file):
        self.calls.append(("presigned", output_file))
        return f"presigned://{output_file}"


def _build_history(**overrides):
    base = {
        "output_file": "demo.png",
        "type": "img2img",
        "prompt": "hello",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _build_post(**overrides):
    base = {
        "id": 1,
        "task_id": "task-1",
        "user_id": 123,
        "user": SimpleNamespace(username="tester"),
        "media_type": "image",
        "width": 512,
        "height": 512,
        "duration": None,
        "tags": "tag1",
        "likes_count": 1,
        "dislikes_count": 0,
        "applied_count": 2,
        "comments_count": 3,
        "is_active": True,
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
        "histories": [_build_history()],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_gallery_post_item_prefers_storage_file_url():
    storage_service = _FakeStorage()
    post = _build_post()

    result = gallery_admin_presenter.build_gallery_post_item(
        post=post,
        storage_service=storage_service,
    )

    assert result["media_url"] == "file://demo.png"
    assert result["task_type"] == "img2img"
    assert result["prompt"] == "hello"


@pytest.mark.asyncio
async def test_get_all_gallery_posts_payload_uses_presenter():
    posts = [_build_post()]

    async def _fake_get_gallery_feed(**kwargs):
        return posts, 1

    result = await gallery_admin_service.get_all_gallery_posts_payload(
        page=1,
        page_size=20,
        is_active=True,
        media_type="image",
        task_type="img2img",
        sort_by="latest",
        storage_service=_FakeStorage(),
        get_gallery_feed_func=_fake_get_gallery_feed,
    )

    assert result["total"] == 1
    assert result["items"][0]["media_url"] == "file://demo.png"


def test_build_dashboard_comment_item_formats_author_name_and_post_metadata():
    comment = SimpleNamespace(
        id=10,
        post_id=7,
        post=SimpleNamespace(task_id="task-7", is_active=True),
        user_id=123,
        user=SimpleNamespace(full_name=None, username="tester"),
        content="hello",
        is_active=True,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )

    result = gallery_admin_presenter.build_dashboard_comment_item(comment)

    assert result["post_task_id"] == "task-7"
    assert result["author_name"] == "tester"
    assert result["created_at"] == "2026-01-01T12:00:00"


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _DeleteGalleryPostDB:
    def __init__(self, results):
        self._results = iter(results)
        self.delete = AsyncMock()
        self.commit = AsyncMock()

    async def execute(self, stmt):
        return next(self._results)


@pytest.mark.asyncio
async def test_delete_gallery_post_payload_cleans_r2_objects_from_history():
    post = SimpleNamespace(id=7, task_id="task-1", user_id=123)
    history = SimpleNamespace(
        task_id="task-1",
        user_id=123,
        output_file="123/output_images/task-1.png",
        type="image",
        is_public=True,
    )
    db = _DeleteGalleryPostDB([
        _ScalarResult(post),
        _ScalarResult(history),
    ])
    cleanup_mock = AsyncMock(return_value=4)

    response = await gallery_admin_service.delete_gallery_post_payload(
        post_id=7,
        db=db,
        storage_service=SimpleNamespace(async_delete_r2_objects=cleanup_mock),
    )

    assert response == {"success": True, "message": "Post deleted successfully"}
    assert history.is_public is False
    db.delete.assert_awaited_once_with(post)
    db.commit.assert_awaited_once()
    cleanup_mock.assert_awaited_once()
    assert set(cleanup_mock.await_args.args[0]) == {
        "history/task-1/original.png",
        "history/task-1/thumb.webp",
        "task-1.png",
        "task-1_thumb.webp",
    }
