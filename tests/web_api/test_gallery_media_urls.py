from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.media_paths import MINIO_BUCKET
from src.database.models import GalleryPost, History, User
from src.web_api.presenters import media_presenter
from src.web_api.services import history_input_presenter
from src.web_api.services.gallery_response_builder import build_gallery_post_responses


class _FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)
        self._index = 0

    async def execute(self, _stmt):
        if self._index >= len(self._results):
            return _FakeScalarResult([])
        result = self._results[self._index]
        self._index += 1
        return result


@pytest.mark.asyncio
async def test_get_r2_url_if_exists_uses_public_probe_for_timeout_path(monkeypatch):
    public_url = "https://r2-test.example/history/task-1/original.mp4"
    public_probe_mock = AsyncMock(return_value=True)
    storage_exists_mock = AsyncMock(return_value=False)
    mark_mock = MagicMock()
    monkeypatch.setattr(media_presenter.storage, "get_r2_public_url", MagicMock(return_value=public_url))
    monkeypatch.setattr(
        media_presenter.storage,
        "async_r2_object_exists",
        storage_exists_mock,
    )
    monkeypatch.setattr(media_presenter.storage, "mark_r2_object_exists", mark_mock)
    monkeypatch.setattr(media_presenter, "r2_public_url_exists", public_probe_mock)

    url = await media_presenter.get_r2_url_if_exists(
        "history/task-1/original.mp4",
        timeout_seconds=2.5,
    )

    assert url == public_url
    public_probe_mock.assert_awaited_once_with(
        "history/task-1/original.mp4",
        public_url,
        timeout_seconds=2.5,
    )
    storage_exists_mock.assert_not_called()
    mark_mock.assert_called_once_with("history/task-1/original.mp4")


@pytest.mark.asyncio
async def test_get_r2_url_if_exists_skips_s3_head_when_public_probe_misses(
    monkeypatch,
):
    public_url = "https://r2-test.example/history/task-1/original.mp4"
    public_probe_mock = AsyncMock(return_value=False)
    storage_exists_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(media_presenter.storage, "get_r2_public_url", MagicMock(return_value=public_url))
    monkeypatch.setattr(
        media_presenter.storage,
        "async_r2_object_exists",
        storage_exists_mock,
    )
    monkeypatch.setattr(media_presenter, "r2_public_url_exists", public_probe_mock)

    url = await media_presenter.get_r2_url_if_exists(
        "history/task-1/original.mp4",
        timeout_seconds=2.5,
    )

    assert url == ""
    public_probe_mock.assert_awaited_once_with(
        "history/task-1/original.mp4",
        public_url,
        timeout_seconds=2.5,
    )
    storage_exists_mock.assert_not_called()


@pytest.mark.asyncio
async def test_get_r2_url_if_exists_can_fallback_to_presigned_when_public_probe_misses(
    monkeypatch,
):
    public_url = "https://r2-test.example/history/task-1/original.mp4"
    public_probe_mock = AsyncMock(return_value=False)
    storage_exists_mock = AsyncMock(return_value=True)
    presign_mock = MagicMock(return_value="https://r2-s3.example/presigned")
    monkeypatch.setattr(
        media_presenter.storage,
        "get_r2_public_url",
        MagicMock(return_value=public_url),
    )
    monkeypatch.setattr(
        media_presenter.storage,
        "async_r2_object_exists",
        storage_exists_mock,
    )
    monkeypatch.setattr(media_presenter, "build_r2_presigned_url", presign_mock)
    monkeypatch.setattr(media_presenter, "r2_public_url_exists", public_probe_mock)

    url = await media_presenter.get_r2_url_if_exists(
        "history/task-1/original.mp4",
        timeout_seconds=2.5,
        fallback_to_presigned=True,
    )

    assert url == "https://r2-s3.example/presigned"
    public_probe_mock.assert_awaited_once_with(
        "history/task-1/original.mp4",
        public_url,
        timeout_seconds=2.5,
    )
    storage_exists_mock.assert_awaited_once_with("history/task-1/original.mp4")
    presign_mock.assert_called_once_with(
        "history/task-1/original.mp4",
        expires_hours=1.0,
    )


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
    presign_mock = MagicMock(return_value="https://minio.example/original.png")

    monkeypatch.setattr(media_presenter.storage, "get_r2_public_url", MagicMock(return_value=""))
    monkeypatch.setattr(
        media_presenter.storage,
        "async_r2_object_exists",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(media_presenter.storage, "get_presigned_url", presign_mock)
    monkeypatch.setattr(
        media_presenter.storage,
        "async_object_exists",
        AsyncMock(return_value=True),
    )

    items = await build_gallery_post_responses(
        session=session,
        posts=[post],
        current_user=type("User", (), {"id": 123})(),
    )

    assert len(items) == 1
    assert items[0].media_url == "https://minio.example/original.png"
    assert items[0].thumbnail_url == ""
    assert presign_mock.call_args_list[0].args == ("123/output_images/task-1.png",)
    assert presign_mock.call_args_list[0].kwargs == {"bucket": MINIO_BUCKET}
    assert presign_mock.call_count == 1


@pytest.mark.asyncio
async def test_build_gallery_post_responses_appends_wan22_mode_tag_from_history():
    post = GalleryPost(
        id=8,
        task_id="task-wan22-1",
        user_id=123,
        media_type="video",
        tags='["task.wan22_video_v2"]',
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        comments_count=0,
        is_active=True,
        created_at=datetime(2026, 5, 31, 10, 23, 0),
    )
    history = History(
        id=12,
        user_id=123,
        task_id="task-wan22-1",
        type="wan22_video_v2",
        prompt="test prompt",
        output_file="123/output_images/task-wan22-1.mp4",
        extra_outputs={"_wan22_context": {"wan22_use_end_frame": True}},
    )
    author = User(id=123, username="tester", full_name="测试账号")
    session = _FakeSession(
        [
            _FakeScalarResult([history]),
            _FakeScalarResult([author]),
        ]
    )

    items = await build_gallery_post_responses(
        session=session,
        posts=[post],
        current_user=None,
        pick_gallery_media_urls=AsyncMock(return_value=("media-url", "thumb-url")),
    )

    assert len(items) == 1
    assert items[0].tags == [
        "task.wan22_video_v2",
        "task.wan22_start_end_frame",
        "task.wan22_segment:1",
    ]


@pytest.mark.asyncio
async def test_build_gallery_post_responses_exposes_original_input_files(monkeypatch):
    post = GalleryPost(
        id=18,
        task_id="task-scail2-inputs",
        user_id=123,
        media_type="video",
        tags='["task.scail2_action_transfer"]',
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        comments_count=0,
        is_active=True,
        created_at=datetime(2026, 6, 19, 9, 0, 0),
    )
    history = History(
        id=24,
        user_id=123,
        task_id="task-scail2-inputs",
        type="scail2_action_transfer",
        prompt="test prompt",
        input_file="uploads/reference.png|uploads/motion.mp4",
        output_file="123/output_images/task-scail2-inputs.mp4",
    )
    author = User(id=123, username="tester", full_name="测试账号")
    session = _FakeSession(
        [
            _FakeScalarResult([history]),
            _FakeScalarResult([author]),
        ]
    )
    presign_mock = MagicMock(
        side_effect=lambda object_name, bucket=None: f"https://storage.test/{object_name}"
    )
    monkeypatch.setattr(history_input_presenter.storage, "get_presigned_url", presign_mock)

    items = await build_gallery_post_responses(
        session=session,
        posts=[post],
        current_user=None,
        pick_gallery_media_urls=AsyncMock(return_value=("media-url", "thumb-url")),
    )

    assert len(items) == 1
    assert items[0].input_file == "uploads/reference.png"
    assert items[0].input_file_url == "https://storage.test/uploads/reference.png"
    assert items[0].input_files == ["uploads/reference.png", "uploads/motion.mp4"]
    assert items[0].input_file_urls == [
        "https://storage.test/uploads/reference.png",
        "https://storage.test/uploads/motion.mp4",
    ]
    assert presign_mock.call_count == 2


@pytest.mark.asyncio
async def test_build_gallery_post_responses_appends_wan22_segment_tag_for_mid_segment():
    post = GalleryPost(
        id=10,
        task_id="task-wan22-2",
        user_id=123,
        media_type="video",
        tags='["task.wan22_video_v2"]',
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        comments_count=0,
        is_active=True,
        created_at=datetime(2026, 5, 31, 10, 26, 0),
    )
    history = History(
        id=14,
        user_id=123,
        task_id="task-wan22-2",
        type="wan22_video_v2",
        prompt="test prompt 2",
        output_file="123/output_images/task-wan22-2.mp4",
        extra_outputs={
            "_wan22_context": {
                "wan22_use_end_frame": False,
                "wan22_prev_task_id": "task-wan22-1",
                "wan22_chain_task_ids": ["task-wan22-1"],
            }
        },
    )
    author = User(id=123, username="tester", full_name="测试账号")
    session = _FakeSession(
        [
            _FakeScalarResult([history]),
            _FakeScalarResult([author]),
        ]
    )

    items = await build_gallery_post_responses(
        session=session,
        posts=[post],
        current_user=None,
        pick_gallery_media_urls=AsyncMock(return_value=("media-url", "thumb-url")),
    )

    assert len(items) == 1
    assert items[0].tags == [
        "task.wan22_video_v2",
        "task.wan22_start_frame",
        "task.wan22_segment:2",
    ]


@pytest.mark.asyncio
async def test_build_gallery_post_responses_skips_mode_tag_for_stitched_wan22_record():
    post = GalleryPost(
        id=9,
        task_id="task-wan22-stitched",
        user_id=123,
        media_type="video",
        tags='["task.wan22_video_v2"]',
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        comments_count=0,
        is_active=True,
        created_at=datetime(2026, 5, 31, 10, 30, 0),
    )
    history = History(
        id=13,
        user_id=123,
        task_id="task-wan22-stitched",
        type="wan22_video_v2",
        prompt="stitched prompt",
        output_file="123/output_images/task-wan22-stitched.mp4",
        extra_outputs={
            "wan22_chain_stitch": {
                "segment_count": 2,
                "wan22_chain_task_ids": ["task-wan22-1", "task-wan22-2"],
            }
        },
    )
    author = User(id=123, username="tester", full_name="测试账号")
    session = _FakeSession(
        [
            _FakeScalarResult([history]),
            _FakeScalarResult([author]),
        ]
    )

    items = await build_gallery_post_responses(
        session=session,
        posts=[post],
        current_user=None,
        pick_gallery_media_urls=AsyncMock(return_value=("media-url", "thumb-url")),
    )

    assert len(items) == 1
    assert items[0].tags == ["task.wan22_video_v2", "task.wan22_stitched_video:2"]
