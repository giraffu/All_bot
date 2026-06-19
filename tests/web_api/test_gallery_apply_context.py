import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.database.models import GalleryPost, History
from src.domain_config.scail2_video import SCAIL2_DEFAULT_NEGATIVE_PROMPT
from src.core import gallery_core
from src.core import gallery_submission_effects
from src.services import storage as storage_module
from src.web_api.services.gallery_response_builder import build_gallery_post_responses
from src.web_api.services import gallery_media_resolver
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


def _async_r2_exists_for(existing_keys: set[str]):
    async def _exists(object_key):
        return object_key in existing_keys

    return AsyncMock(side_effect=_exists)


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
async def test_build_post_responses_marks_wan22_stitched_template_apply_disabled():
    history = History(
        id=11,
        user_id=123,
        task_id="task-stitched",
        type="wan22_video_v2",
        prompt="stitched summary",
        output_file="bot-data/history/task-stitched/output.mp4",
        extra_outputs={
            "wan22_chain_stitch": {
                "segment_count": 2,
                "wan22_chain_task_ids": ["task-a", "task-b"],
            }
        },
    )
    post = GalleryPost(
        id=2,
        task_id="task-stitched",
        media_type="video",
        width=720,
        height=1280,
        duration=10,
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

    assert responses[0].result_meta == {"wan22_is_stitched": True}
    assert responses[0].template_apply_supported is False
    assert responses[0].template_apply_disabled_reason == "wan22_stitched"


@pytest.mark.asyncio
async def test_build_post_responses_masks_locked_prompt_for_non_author():
    history = History(
        id=11,
        user_id=123,
        task_id="task-locked-prompt",
        type="image",
        prompt="abcdefghij",
        output_file="bot-data/history/task-locked-prompt/output.png",
    )
    post = GalleryPost(
        id=2,
        task_id="task-locked-prompt",
        user_id=123,
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
    session = _FakeSession(
        [
            _FakeResult(many=[]),
            _FakeResult(many=[history]),
            _FakeResult(many=[]),
            _FakeResult(many=[]),
            _FakeResult(many=[]),
        ]
    )

    responses = await build_gallery_post_responses(
        session=session,
        posts=[post],
        current_user=SimpleNamespace(id=999),
        pick_gallery_media_urls=AsyncMock(return_value=("media-url", "thumb-url")),
    )

    assert responses[0].prompt == "abcde*****"
    assert responses[0].prompt_unlocked is False
    assert responses[0].prompt_unlockable is True
    assert responses[0].prompt_is_masked is True
    assert responses[0].prompt_unlock_price == 1


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
async def test_get_apply_context_returns_scail2_motion_video_template_input_only():
    history = History(
        id=11,
        user_id=123,
        task_id="task-scail2",
        type="scail2_action_transfer",
        prompt="natural dance motion",
        input_file="uploads/reference.png|uploads/motion.mp4",
        output_file="bot-data/history/task-scail2/output.mp4",
        width=512,
        height=896,
        duration=5,
        requested_duration=8,
        extra_outputs={
            "scail2_context": {
                "scail2_negative_prompt": "low quality blur",
                "scail2_duration_seconds": 8,
            }
        },
    )
    post = GalleryPost(
        id=2,
        task_id="task-scail2",
        media_type="video",
        width=512,
        height=896,
        duration=5,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(
        post_id=2,
        db=session,
        build_input_file_url=lambda key: f"https://storage.test/{key}",
    )

    assert response.task_type == "scail2_action_transfer"
    assert response.prompt == "natural dance motion"
    assert response.negative_prompt == "low quality blur"
    assert response.requested_duration == 8
    assert response.input_file == "uploads/motion.mp4"
    assert response.input_files == ["uploads/motion.mp4"]
    assert response.input_file_url == "https://storage.test/uploads/motion.mp4"
    assert response.input_file_urls == ["https://storage.test/uploads/motion.mp4"]
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_uses_default_scail2_negative_prompt_for_legacy_history():
    history = History(
        id=11,
        user_id=123,
        task_id="task-scail2",
        type="scail2_video_replacement",
        prompt="replace performer",
        input_file="uploads/reference.png|uploads/motion.mp4",
        requested_duration=5,
    )
    post = GalleryPost(
        id=2,
        task_id="task-scail2",
        media_type="video",
        width=512,
        height=896,
        duration=5,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(
        post_id=2,
        db=session,
        build_input_file_url=lambda key: f"https://storage.test/{key}",
    )

    assert response.negative_prompt == SCAIL2_DEFAULT_NEGATIVE_PROMPT
    assert response.input_files == ["uploads/motion.mp4"]


@pytest.mark.asyncio
async def test_get_apply_context_rejects_scail2_history_missing_motion_video():
    history = History(
        id=11,
        user_id=123,
        task_id="task-scail2",
        type="scail2_action_transfer",
        prompt="motion template",
        input_file="uploads/reference.png",
    )
    post = GalleryPost(
        id=2,
        task_id="task-scail2",
        media_type="video",
        width=512,
        height=896,
        duration=5,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_gallery_apply_context_payload(post_id=2, db=session)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "missing_scail2_motion_video"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_apply_context_restores_wan22_video_v2_single_segment_context():
    history = History(
        id=11,
        user_id=123,
        task_id="task-wan22-v2",
        type="wan22_video_v2",
        prompt="cinematic v2 motion",
        billing_resolution=None,
        width=512,
        height=768,
        duration=13,
        requested_duration=None,
        extra_outputs={
            "_wan22_context": {
                "wan22_resolution_preset": "standard",
                "wan22_negative_prompt": "low quality blur",
                "wan22_duration_seconds": 10,
                "wan22_use_end_frame": False,
            }
        },
    )
    post = GalleryPost(
        id=2,
        task_id="task-wan22-v2",
        media_type="video",
        width=512,
        height=768,
        duration=13,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    response = await get_gallery_apply_context_payload(post_id=2, db=session)

    assert response.prompt == "cinematic v2 motion"
    assert response.negative_prompt == "low quality blur"
    assert response.billing_resolution == "standard"
    assert response.duration == 10
    assert response.requested_duration == 10
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("task_type", ["custom_video", "video_lora", "wan22_video_v2"])
async def test_get_apply_context_rejects_wan22_stitched_records(task_type):
    history = History(
        id=11,
        user_id=123,
        task_id="task-stitched",
        type=task_type,
        prompt="stitched summary",
        width=720,
        height=1280,
        duration=10,
        extra_outputs={
            "wan22_chain_stitch": {
                "segment_count": 2,
                "wan22_chain_task_ids": ["task-a", "task-b"],
            }
        },
    )
    post = GalleryPost(
        id=2,
        task_id="task-stitched",
        media_type="video",
        width=720,
        height=1280,
        duration=10,
    )
    session = _FakeSession(
        [
            _FakeResult(single=post),
            _FakeResult(many=[history]),
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_gallery_apply_context_payload(post_id=2, db=session)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "wan22_stitched"
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
    async_exists_mock = _async_r2_exists_for(
        {
            "history/task-1/original.png",
            "history/task-1/thumb.webp",
        }
    )
    monkeypatch.setattr(storage_module.storage, "async_r2_object_exists", async_exists_mock)
    monkeypatch.setattr(
        gallery_media_resolver,
        "build_r2_presigned_url",
        lambda key, **_kwargs: f"https://r2-s3.example/{key}",
    )

    media_url, thumbnail_url = await resolve_gallery_post_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "https://r2-s3.example/history/task-1/original.png"
    assert thumbnail_url == "https://r2-s3.example/history/task-1/thumb.webp"
    assert async_exists_mock.await_count == 2


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_falls_back_to_original_object_keys_when_history_keys_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        storage_module.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    async_exists_mock = _async_r2_exists_for(
        {
            "123/output_images/task-1.png",
            "123/output_images/task-1_thumb.webp",
        }
    )
    monkeypatch.setattr(storage_module.storage, "async_r2_object_exists", async_exists_mock)
    monkeypatch.setattr(
        gallery_media_resolver,
        "build_r2_presigned_url",
        lambda key, **_kwargs: f"https://r2-s3.example/{key}",
    )

    media_url, thumbnail_url = await resolve_gallery_post_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "https://r2-s3.example/123/output_images/task-1.png"
    assert thumbnail_url == "https://r2-s3.example/123/output_images/task-1_thumb.webp"
    assert async_exists_mock.await_count == 4


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_can_use_raw_bot_data_r2_prefix(
    monkeypatch,
):
    monkeypatch.setattr(
        storage_module.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    async_exists_mock = _async_r2_exists_for(
        {
            "bot-data/history/task-1/output.png",
            "bot-data/history/task-1/output_thumb.webp",
        }
    )
    monkeypatch.setattr(storage_module.storage, "async_r2_object_exists", async_exists_mock)
    monkeypatch.setattr(
        gallery_media_resolver,
        "build_r2_presigned_url",
        lambda key, **_kwargs: f"https://r2-s3.example/{key}",
    )

    media_url, thumbnail_url = await resolve_gallery_post_media_urls(
        task_id="task-1",
        output_file="bot-data/history/task-1/output.png",
        media_type="image",
    )

    assert media_url == "https://r2-s3.example/bot-data/history/task-1/output.png"
    assert thumbnail_url == "https://r2-s3.example/bot-data/history/task-1/output_thumb.webp"
    assert async_exists_mock.await_count == 6


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_returns_public_url_when_presign_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(
        storage_module.storage,
        "get_r2_public_url",
        lambda key: f"https://cdn.example/{key}",
    )
    async_exists_mock = _async_r2_exists_for(
        {
            "history/task-1/original.png",
            "history/task-1/thumb.webp",
        }
    )
    monkeypatch.setattr(storage_module.storage, "async_r2_object_exists", async_exists_mock)
    monkeypatch.setattr(
        gallery_media_resolver,
        "build_r2_presigned_url",
        MagicMock(return_value=""),
    )

    media_url, thumbnail_url = await resolve_gallery_post_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "https://cdn.example/history/task-1/original.png"
    assert thumbnail_url == "https://cdn.example/history/task-1/thumb.webp"
    assert async_exists_mock.await_count == 2


@pytest.mark.asyncio
async def test_pick_gallery_media_urls_falls_back_to_media_storage_but_skips_slow_thumbnail_fallback_when_r2_missing(
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
    presign_mock = MagicMock(return_value="https://minio.example/original.png")
    monkeypatch.setattr(storage_module.storage, "get_presigned_url", presign_mock)

    media_url, thumbnail_url = await resolve_gallery_post_media_urls(
        task_id="task-1",
        output_file="123/output_images/task-1.png",
        media_type="image",
    )

    assert media_url == "https://minio.example/original.png"
    assert thumbnail_url == ""
    assert async_exists_mock.await_count == 6
    assert presign_mock.call_count == 1


@pytest.mark.asyncio
async def test_build_gallery_thumbnail_url_fast_mode_skips_storage_fallback():
    async def fake_async_r2_object_exists(_object_key):
        return False

    async def fail_resolve_thumbnail_url(*_args, **_kwargs):
        raise AssertionError("fast list mode must not call thumbnail fallback")

    thumbnail_url = await gallery_media_resolver.build_gallery_thumbnail_url(
        "123/output_images/task-1.png",
        "image",
        task_id="task-1",
        resolve_thumbnail_url_fn=fail_resolve_thumbnail_url,
        async_r2_object_exists_fn=fake_async_r2_object_exists,
    )

    assert thumbnail_url == ""


@pytest.mark.asyncio
async def test_build_gallery_thumbnail_url_full_mode_preserves_thumbnail_fallback():
    async def fake_async_r2_object_exists(_object_key):
        return False

    async def fake_resolve_thumbnail_url(*_args, **_kwargs):
        return "https://legacy.example/thumb.webp"

    thumbnail_url = await gallery_media_resolver.build_gallery_thumbnail_url(
        "123/output_images/task-1.png",
        "image",
        task_id="task-1",
        fast_list_mode=False,
        resolve_thumbnail_url_fn=fake_resolve_thumbnail_url,
        async_r2_object_exists_fn=fake_async_r2_object_exists,
    )

    assert thumbnail_url == "https://legacy.example/thumb.webp"


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
        _async_r2_exists_for(
            {
                "123/output_images/task-1.png",
                "123/output_images/task-1_thumb.webp",
            }
        ),
    )
    monkeypatch.setattr(
        gallery_media_resolver,
        "build_r2_presigned_url",
        lambda key, **_kwargs: f"https://r2-s3.example/{key}",
    )

    responses = await build_gallery_post_responses(
        session=session,
        posts=[post],
        current_user=None,
    )

    assert len(responses) == 1
    assert responses[0].media_url == "https://r2-s3.example/123/output_images/task-1.png"
    assert responses[0].thumbnail_url == "https://r2-s3.example/123/output_images/task-1_thumb.webp"


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
