import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models import GalleryPost, History
from src.core import gallery_core
from src.core import gallery_submission_effects
from src.services import storage as storage_module
from src.web_api.services.gallery_response_builder import build_gallery_post_responses
from src.web_api.services.gallery_service_queries import get_gallery_apply_context_payload
from src.web_api.services.gallery_service_support import (
    logger as gallery_support_logger,
    pick_gallery_media_urls,
    presenter_resolve_gallery_media_urls,
    resolve_gallery_post_media_urls,
)


class _FakeResult:
    def __init__(self, *, single=None, many=None):
        self._single = single
        if many is None:
            self._many = [] if single is None else [single]
        else:
            self._many = list(many)

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return self

    def first(self):
        return self._many[0] if self._many else None

    def all(self):
        return list(self._many)


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)
        self.commit = AsyncMock()
        self.add = MagicMock()

    async def execute(self, _stmt):
        return next(self._results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_build_post_responses_includes_billing_resolution_for_gallery_lists():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="prompt",
        output_file="bot-data/history/task-1/output.mp4",
        width=720,
        height=1280,
        duration=8,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=None,
        height=None,
        duration=None,
        tags="[]",
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        is_active=True,
        created_at=datetime.now(),
    )
    session = _FakeSession([_FakeResult(many=[history])])

    responses = await build_gallery_post_responses(
        session=session,
        posts=[post],
        current_user=None,
        pick_gallery_media_urls=AsyncMock(return_value=("media-url", "thumb-url")),
    )

    assert len(responses) == 1
    assert responses[0].billing_resolution == "standard"
    assert responses[0].media_url == "media-url"
    assert responses[0].thumbnail_url == "thumb-url"


@pytest.mark.asyncio
async def test_get_apply_context_backfills_missing_video_billing_resolution_from_short_side():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="prompt",
        width=720,
        height=1280,
        duration=8,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=None,
        height=None,
        duration=None,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.post_id == 2
    assert response.source_post_id == 2
    assert response.billing_resolution == "standard"
    assert response.width == 720
    assert response.height == 1280
    assert response.duration == 5
    assert response.requested_duration == 5
    assert history.billing_resolution is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_clears_non_video_billing_resolution():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt",
        billing_resolution="720",
        width=1024,
        height=1024,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="image",
        width=1024,
        height=1024,
        duration=None,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.billing_resolution is None
    assert history.billing_resolution == "720"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_prefers_requested_duration_and_strips_ltx_prefix():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="ltx_video",
        prompt="[1344x768|20s] wide cinematic dolly shot",
        billing_resolution="1344x768",
        width=1344,
        height=768,
        duration=1,
        requested_duration=20,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=1344,
        height=768,
        duration=1,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.prompt == "wide cinematic dolly shot"
    assert response.duration == 1
    assert response.requested_duration == 20
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_strips_ltx_prefix_without_promoting_it_to_requested_duration():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="ltx_video",
        prompt="[1344x768|20s] wide cinematic dolly shot",
        billing_resolution="1344x768",
        width=1344,
        height=768,
        duration=1,
        requested_duration=None,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=1344,
        height=768,
        duration=1,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.prompt == "wide cinematic dolly shot"
    assert response.duration == 1
    assert response.requested_duration is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_maps_legacy_ltx_media_duration_to_requested_duration():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="ltx_video",
        prompt="wide cinematic dolly shot",
        billing_resolution="512x704",
        width=512,
        height=704,
        duration=21,
        requested_duration=None,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=512,
        height=704,
        duration=21,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.duration == 21
    assert response.requested_duration == 20
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_maps_legacy_ltx_media_duration_16_to_15():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="ltx_video",
        prompt="wide cinematic dolly shot",
        billing_resolution="512x704",
        width=512,
        height=704,
        duration=16,
        requested_duration=None,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=512,
        height=704,
        duration=16,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.duration == 16
    assert response.requested_duration == 15
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_maps_legacy_custom_video_duration_9_to_fixed_5():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="cinematic action shot",
        billing_resolution="720",
        width=720,
        height=1280,
        duration=9,
        requested_duration=None,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=720,
        height=1280,
        duration=9,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.duration == 5
    assert response.requested_duration == 5
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_maps_legacy_video_lora_duration_11_to_fixed_5():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="video_lora",
        prompt="[模型: BreastGrow] glowing neon city",
        billing_resolution="1024",
        width=1024,
        height=1024,
        duration=11,
        requested_duration=None,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="video",
        width=1024,
        height=1024,
        duration=11,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.duration == 5
    assert response.requested_duration == 5
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_restores_lora_strength_from_new_prompt_format():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="img2img_lora",
        prompt="[模型: qwen/YARN_1.0.safetensors] [强度: 0.35] cinematic portrait",
        output_file="bot-data/history/task-1/output.png",
        width=1024,
        height=1024,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="image",
        width=1024,
        height=1024,
        duration=None,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.prompt == "cinematic portrait"
    assert response.lora_name == "qwen/YARN_1.0.safetensors"
    assert response.lora_strength == 0.35
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_keeps_legacy_lora_prompt_without_strength():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="img2img_lora",
        prompt="[模型: 真实质感] cinematic portrait",
        output_file="bot-data/history/task-1/output.png",
        width=1024,
        height=1024,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="image",
        width=1024,
        height=1024,
        duration=None,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.prompt == "cinematic portrait"
    assert response.lora_name == "qwen/realistic_texture.safetensors"
    assert response.lora_strength is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_prefers_existing_history_task_key(
    monkeypatch,
):
    monkeypatch.setattr(
        storage_module.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    async_exists_mock = AsyncMock(side_effect=[True, True])
    monkeypatch.setattr(storage_module.storage, "async_r2_object_exists", async_exists_mock)

    media_url, thumbnail_url = await resolve_gallery_post_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "https://cdn.example/history/task-1/original.png"
    assert thumbnail_url == "https://cdn.example/history/task-1/thumb.webp"
    assert async_exists_mock.await_count == 2


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_falls_back_to_legacy_keys_when_history_keys_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        storage_module.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    async_exists_mock = AsyncMock(side_effect=[False, True, False, True])
    monkeypatch.setattr(storage_module.storage, "async_r2_object_exists", async_exists_mock)

    media_url, thumbnail_url = await resolve_gallery_post_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "https://cdn.example/task-1.png"
    assert thumbnail_url == "https://cdn.example/task-1_thumb.webp"
    assert async_exists_mock.await_count == 4


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_falls_back_to_presigned_storage_urls_when_r2_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        storage_module.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    async_exists_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(storage_module.storage, "async_r2_object_exists", async_exists_mock)
    monkeypatch.setattr(
        storage_module.storage,
        "async_object_exists",
        AsyncMock(return_value=True),
    )
    presign_mock = MagicMock(
        side_effect=[
            "https://minio.example/original.png",
            "https://minio.example/thumb.webp",
        ]
    )
    monkeypatch.setattr(storage_module.storage, "get_presigned_url", presign_mock)

    media_url, thumbnail_url = await resolve_gallery_post_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "https://minio.example/original.png"
    assert thumbnail_url == "https://minio.example/thumb.webp"
    assert async_exists_mock.await_count == 4
    assert presign_mock.call_count == 2


@pytest.mark.asyncio
async def test_build_post_responses_uses_r2_fallback_chain(monkeypatch):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt",
        output_file="123/output_images/task-1.png",
        width=1024,
        height=1024,
    )
    post = GalleryPost(
        id=2,
        task_id="task-1",
        media_type="image",
        width=1024,
        height=1024,
        duration=None,
        tags="[]",
        likes_count=0,
        dislikes_count=0,
        applied_count=0,
        is_active=True,
        created_at=datetime.now(),
    )
    session = _FakeSession([_FakeResult(many=[history])])

    monkeypatch.setattr(
        storage_module.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    monkeypatch.setattr(
        storage_module.storage,
        "async_r2_object_exists",
        AsyncMock(side_effect=[False, True, False, True]),
    )

    responses = await build_gallery_post_responses(
        session=session,
        posts=[post],
        current_user=None,
    )

    assert len(responses) == 1
    assert responses[0].media_url == "https://cdn.example/task-1.png"
    assert responses[0].thumbnail_url == "https://cdn.example/task-1_thumb.webp"


@pytest.mark.asyncio
async def test_build_post_responses_preserves_post_order_with_concurrent_url_tasks():
    history_1 = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt-1",
        output_file="bot-data/history/task-1/output.png",
    )
    history_2 = History(
        id=12,
        user_id=123,
        task_id="task-2",
        type="image",
        prompt="prompt-2",
        output_file="bot-data/history/task-2/output.png",
    )
    posts = [
        GalleryPost(
            id=2,
            task_id="task-1",
            media_type="image",
            tags="[]",
            likes_count=0,
            dislikes_count=0,
            applied_count=0,
            is_active=True,
            created_at=datetime.now(),
        ),
        GalleryPost(
            id=3,
            task_id="task-2",
            media_type="image",
            tags="[]",
            likes_count=0,
            dislikes_count=0,
            applied_count=0,
            is_active=True,
            created_at=datetime.now(),
        ),
    ]
    session = _FakeSession([_FakeResult(many=[history_1, history_2])])

    async def fake_pick_gallery_media_urls(*, task_id, output_file, media_type):
        assert output_file is not None
        assert media_type == "image"
        if task_id == "task-1":
            await asyncio.sleep(0.02)
            return "media-1", "thumb-1"
        await asyncio.sleep(0.001)
        return "media-2", "thumb-2"

    responses = await build_gallery_post_responses(
        session=session,
        posts=posts,
        current_user=None,
        pick_gallery_media_urls=fake_pick_gallery_media_urls,
    )

    assert [item.task_id for item in responses] == ["task-1", "task-2"]
    assert [item.media_url for item in responses] == ["media-1", "media-2"]
    assert [item.thumbnail_url for item in responses] == ["thumb-1", "thumb-2"]


@pytest.mark.asyncio
async def test_build_post_responses_degrades_single_url_task_exception():
    history_1 = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt-1",
        output_file="bot-data/history/task-1/output.png",
    )
    history_2 = History(
        id=12,
        user_id=123,
        task_id="task-2",
        type="image",
        prompt="prompt-2",
        output_file="bot-data/history/task-2/output.png",
    )
    posts = [
        GalleryPost(
            id=2,
            task_id="task-1",
            media_type="image",
            tags="[]",
            likes_count=0,
            dislikes_count=0,
            applied_count=0,
            is_active=True,
            created_at=datetime.now(),
        ),
        GalleryPost(
            id=3,
            task_id="task-2",
            media_type="image",
            tags="[]",
            likes_count=0,
            dislikes_count=0,
            applied_count=0,
            is_active=True,
            created_at=datetime.now(),
        ),
    ]
    session = _FakeSession([_FakeResult(many=[history_1, history_2])])

    async def fake_pick_gallery_media_urls(*, task_id, output_file, media_type):
        assert output_file is not None
        assert media_type == "image"
        if task_id == "task-1":
            return "media-1", "thumb-1"
        raise RuntimeError("r2 probe failed")

    responses = await build_gallery_post_responses(
        session=session,
        posts=posts,
        current_user=None,
        pick_gallery_media_urls=fake_pick_gallery_media_urls,
    )

    assert len(responses) == 2
    assert responses[0].media_url == "media-1"
    assert responses[0].thumbnail_url == "thumb-1"
    assert responses[1].media_url == "bot-data/history/task-2/output.png"
    assert responses[1].thumbnail_url == ""


@pytest.mark.asyncio
async def test_build_post_responses_runs_url_tasks_concurrently():
    history_1 = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt-1",
        output_file="bot-data/history/task-1/output.png",
    )
    history_2 = History(
        id=12,
        user_id=123,
        task_id="task-2",
        type="image",
        prompt="prompt-2",
        output_file="bot-data/history/task-2/output.png",
    )
    posts = [
        GalleryPost(
            id=2,
            task_id="task-1",
            media_type="image",
            tags="[]",
            likes_count=0,
            dislikes_count=0,
            applied_count=0,
            is_active=True,
            created_at=datetime.now(),
        ),
        GalleryPost(
            id=3,
            task_id="task-2",
            media_type="image",
            tags="[]",
            likes_count=0,
            dislikes_count=0,
            applied_count=0,
            is_active=True,
            created_at=datetime.now(),
        ),
    ]
    session = _FakeSession([_FakeResult(many=[history_1, history_2])])
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    first_finished = False

    async def fake_pick_gallery_media_urls(*, task_id, output_file, media_type):
        nonlocal first_finished
        assert output_file is not None
        assert media_type == "image"
        if task_id == "task-1":
            first_started.set()
            # If the implementation becomes serial again, this wait times out
            # because task-2 cannot start before task-1 returns.
            await asyncio.wait_for(second_started.wait(), timeout=0.2)
            first_finished = True
            return "media-1", "thumb-1"

        assert first_started.is_set()
        assert first_finished is False
        second_started.set()
        return "media-2", "thumb-2"

    responses = await build_gallery_post_responses(
        session=session,
        posts=posts,
        current_user=None,
        pick_gallery_media_urls=fake_pick_gallery_media_urls,
    )

    assert second_started.is_set()
    assert [item.media_url for item in responses] == ["media-1", "media-2"]


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_best_effort_when_inner_probes_raise():
    media_url, thumbnail_url = await pick_gallery_media_urls(
        task_id="task-1",
        output_file="bot-data/history/task-1/output.png",
        media_type="image",
        resolve_gallery_media_urls_fn=presenter_resolve_gallery_media_urls,
        build_media_url_fn=AsyncMock(side_effect=RuntimeError("media failed")),
        build_thumbnail_url_fn=AsyncMock(side_effect=RuntimeError("thumb failed")),
        logger=gallery_support_logger,
    )

    assert media_url == "bot-data/history/task-1/output.png"
    assert thumbnail_url == ""


@pytest.mark.asyncio
async def test_process_submit_to_gallery_result_builds_expected_outcome():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="i2i_pro",
        prompt="prompt",
        output_file="123/output_images/task-1.png",
        allow_contribute=True,
    )
    user = type("User", (), {"id": 123, "total_contributions": 0})()

    existing_result = _FakeResult(many=[])
    history_result = _FakeResult(many=[history])
    user_result = _FakeResult(single=user)
    session = _FakeSession([existing_result, history_result, user_result])
    gallery_submission_outbox = SimpleNamespace(
        check_gallery_submit_limit=AsyncMock(return_value=True),
        increment_gallery_submit=AsyncMock(),
    )

    outcome = await gallery_core.process_submit_to_gallery_result(
        user_id=123,
        task_id="task-1",
        session_factory=lambda: session,
        gallery_submission_outbox=gallery_submission_outbox,
    )

    assert outcome.payload["status"] == "success"
    assert len(outcome.side_effects) == 2

    copy_func, copy_args = outcome.side_effects[0]
    assert copy_func is gallery_submission_effects.async_copy_to_r2_background
    assert copy_args[1] == "123/output_images/task-1.png"
    assert copy_args[2] == "history/task-1/original.png"

    thumb_func, thumb_args = outcome.side_effects[1]
    assert thumb_func is gallery_submission_effects.generate_and_upload_thumbnail
    assert thumb_args[0] == "123/output_images/task-1.png"
    assert thumb_args[1] == "image"
    assert thumb_args[2] == "history/task-1/thumb.webp"
    gallery_submission_outbox.check_gallery_submit_limit.assert_awaited_once_with(
        123, limit=10
    )
    gallery_submission_outbox.increment_gallery_submit.assert_awaited_once_with(123)


def test_build_gallery_submit_side_effects_returns_copy_and_thumbnail_jobs():
    copy_job = AsyncMock()
    thumbnail_job = AsyncMock()
    side_effects = gallery_submission_effects.build_gallery_submit_side_effects(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
        copy_to_r2_background_func=copy_job,
        generate_thumbnail_func=thumbnail_job,
    )

    assert len(side_effects) == 2

    copy_func, copy_args = side_effects[0]
    assert copy_func is copy_job
    assert copy_args == (
        "bot-data",
        "123/output_images/task-1.png",
        "history/task-1/original.png",
    )

    thumb_func, thumb_args = side_effects[1]
    assert thumb_func is thumbnail_job
    assert thumb_args == ("123/output_images/task-1.png", "image", "history/task-1/thumb.webp")
