from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.media_paths import MINIO_BUCKET
from src.database.models import GalleryPost, History, User
from src.web_api.routers import gallery as gallery_router


class _FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)

    async def execute(self, _stmt):
        return next(self._results)


@pytest.mark.asyncio
async def test_build_post_responses_used_by_my_posts_generates_minio_urls_for_unprefixed_history_path(
    monkeypatch,
):
    post = GalleryPost(
        id=7,
        task_id="task-1",
        user_id=123,
        media_type="image",
        tags='["#task.mode_edit"]',
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        comments_count=0,
        is_active=True,
        created_at=datetime(2026, 5, 20, 12, 0, 0),
    )
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="edit",
        prompt="test prompt",
        output_file="123/output_images/task-1.png",
    )
    author = User(id=123, username="tester", full_name="测试账号")
    session = _FakeSession(
        [
            _FakeScalarResult([]),
            _FakeScalarResult([history]),
            _FakeScalarResult([author]),
        ]
    )
    presign_mock = MagicMock(
        side_effect=[
            "https://minio.example/original.png",
            "https://minio.example/thumb.webp",
        ]
    )

    monkeypatch.setattr(gallery_router.storage, "get_r2_public_url", MagicMock(return_value=""))
    monkeypatch.setattr(
        gallery_router.storage,
        "async_r2_object_exists",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(gallery_router.storage, "get_presigned_url", presign_mock)

    items = await gallery_router._build_post_responses(
        session,
        [post],
        current_user=type("User", (), {"id": 123})(),
    )

    assert len(items) == 1
    assert items[0].media_url == "https://minio.example/original.png"
    assert items[0].thumbnail_url == "https://minio.example/thumb.webp"
    assert presign_mock.call_args_list[0].args == ("123/output_images/task-1.png",)
    assert presign_mock.call_args_list[0].kwargs == {"bucket": MINIO_BUCKET}
    assert presign_mock.call_args_list[1].args == ("123/output_images/task-1_thumb.webp",)
    assert presign_mock.call_args_list[1].kwargs == {"bucket": MINIO_BUCKET}
