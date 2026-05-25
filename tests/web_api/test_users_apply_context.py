from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.database import core as db_core
from src.database.models import GalleryPost, History
from src.web_api.routers import users as users_router
from src.web_api.services import users_history_service
from src.web_api.services.history_response_builder import (
    build_favorite_gallery_payload,
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

    def all(self):
        return list(self._many)


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)
        self.commit = AsyncMock()
        self.closed = False

    async def execute(self, _stmt):
        return next(self._results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.closed = True
        return False


def test_pick_preferred_gallery_post_prefers_active_and_newer_post():
    now = datetime.now()
    inactive_newest = GalleryPost(
        id=3,
        task_id="task-1",
        is_active=False,
        created_at=now + timedelta(minutes=2),
    )
    active_oldest = GalleryPost(
        id=1,
        task_id="task-1",
        is_active=True,
        created_at=now,
    )
    active_newest = GalleryPost(
        id=2,
        task_id="task-1",
        is_active=True,
        created_at=now + timedelta(minutes=1),
    )

    preferred = users_history_service.pick_preferred_gallery_post(
        [inactive_newest, active_oldest, active_newest]
    )

    assert preferred is active_newest


@pytest.mark.asyncio
async def test_get_user_history_payload_resolves_media_urls_with_keyword_arguments(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt",
        output_file="bot-data/history/task-1/output.png",
        created_at=datetime.now(),
    )

    async def _fake_fetch_recent_user_history(*, db, current_user_id, limit):
        assert current_user_id == 123
        assert limit == 8
        return [history], ["task-1"]

    async def _fake_fetch_active_public_gallery_task_ids(*, db, task_ids):
        assert task_ids == ["task-1"]
        return {"task-1"}

    async def _fake_resolve_history_media_urls(
        *,
        task_id: str | None,
        output_file: str | None,
        history_type: str | None,
        fallback_to_storage_path: bool = False,
    ):
        assert task_id == "task-1"
        assert output_file == "bot-data/history/task-1/output.png"
        assert history_type == "image"
        assert fallback_to_storage_path is False
        return ("https://example.com/output.png", "https://example.com/thumb.png")

    monkeypatch.setattr(
        users_history_service,
        "fetch_recent_user_history",
        _fake_fetch_recent_user_history,
    )
    monkeypatch.setattr(
        users_history_service,
        "fetch_active_public_gallery_task_ids",
        _fake_fetch_active_public_gallery_task_ids,
    )

    response = await users_history_service.get_user_history_payload(
        current_user=type("User", (), {"id": 123})(),
        db=object(),
        resolve_history_media_urls=_fake_resolve_history_media_urls,
    )

    assert response.total == 1
    assert response.items[0].task_id == "task-1"
    assert response.items[0].output_file_url == "https://example.com/output.png"
    assert response.items[0].thumbnail_url == "https://example.com/thumb.png"
    assert response.items[0].is_public is True


@pytest.mark.asyncio
async def test_build_favorite_gallery_payload_resolves_media_urls_with_keyword_arguments():
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="image",
        prompt="prompt",
        output_file="bot-data/history/task-1/output.png",
        created_at=datetime.now(),
    )

    async def _fake_resolve_history_media_urls(
        *,
        task_id: str | None,
        output_file: str | None,
        history_type: str | None,
        fallback_to_storage_path: bool = False,
    ):
        assert task_id == "task-1"
        assert output_file == "bot-data/history/task-1/output.png"
        assert history_type == "image"
        assert fallback_to_storage_path is False
        return ("https://example.com/output.png", "https://example.com/thumb.png")

    response_items = await build_favorite_gallery_payload(
        histories=[history],
        gallery_post_map={},
        resolve_history_media_urls_func=_fake_resolve_history_media_urls,
    )

    assert len(response_items) == 1
    assert response_items[0].task_id == "task-1"
    assert response_items[0].media_url == "https://example.com/output.png"
    assert response_items[0].thumbnail_url == "https://example.com/thumb.png"


@pytest.mark.asyncio
async def test_get_favorite_apply_context_probes_media_after_session_closes(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="prompt",
        output_file="bot-data/history/task-1/output.mp4",
    )
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    async def _probe(_output_file, _media_type):
        return (1024, 1024, 8)

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(users_history_service, "extract_media_metadata_from_storage", _probe)

    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.task_id == "task-1"
    assert response.billing_resolution == "1024"
    assert response.width == 1024
    assert response.height == 1024
    assert response.duration == 8
    assert response.requested_duration == 8
    assert history.billing_resolution is None
    assert history.width is None
    assert history.height is None
    assert history.duration is None
    assert session.closed is False
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_prefers_active_newer_gallery_post_metadata(
    monkeypatch,
):
    now = datetime.now()
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="prompt",
        output_file="bot-data/history/task-1/output.mp4",
    )
    inactive_newer = GalleryPost(
        id=3,
        task_id="task-1",
        is_active=False,
        created_at=now + timedelta(minutes=2),
        width=512,
        height=512,
        duration=5,
    )
    active_older = GalleryPost(
        id=1,
        task_id="task-1",
        is_active=True,
        created_at=now,
        width=720,
        height=720,
        duration=8,
    )
    active_newer = GalleryPost(
        id=2,
        task_id="task-1",
        is_active=True,
        created_at=now + timedelta(minutes=1),
        width=1024,
        height=1024,
        duration=10,
    )
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[inactive_newer, active_older, active_newer]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.post_id == 2
    assert response.source_post_id == 2
    assert response.billing_resolution == "1024"
    assert response.width == 1024
    assert response.height == 1024
    assert response.duration == 10
    assert response.requested_duration == 10
    assert history.billing_resolution is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_uses_short_side_for_video_billing_tier(
    monkeypatch,
):
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
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.billing_resolution == "720"
    assert response.width == 720
    assert response.height == 1280
    assert response.duration == 8
    assert response.requested_duration == 8
    assert history.billing_resolution is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_maps_512x768_to_512_billing_tier(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="prompt",
        width=512,
        height=768,
        duration=5,
    )
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.billing_resolution == "512"
    assert response.width == 512
    assert response.height == 768
    assert response.duration == 5
    assert response.requested_duration == 5
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_maps_1024x1536_to_1024_billing_tier(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="video_lora",
        prompt="[模型: BreastGrow] prompt",
        width=1024,
        height=1536,
        duration=10,
    )
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.billing_resolution == "1024"
    assert response.width == 1024
    assert response.height == 1536
    assert response.duration == 10
    assert response.requested_duration == 10
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_strips_ltx_prefix_but_keeps_media_duration(
    monkeypatch,
):
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
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.prompt == "wide cinematic dolly shot"
    assert response.duration == 1
    assert response.requested_duration is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_maps_legacy_ltx_media_duration_to_requested_duration(
    monkeypatch,
):
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
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.duration == 21
    assert response.requested_duration == 20
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_maps_legacy_ltx_media_duration_16_to_15(
    monkeypatch,
):
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
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.duration == 16
    assert response.requested_duration == 15
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_maps_legacy_custom_video_duration_9_to_8(
    monkeypatch,
):
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
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.duration == 9
    assert response.requested_duration == 8
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_maps_legacy_video_lora_duration_11_to_10(
    monkeypatch,
):
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
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.duration == 11
    assert response.requested_duration == 10
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_restores_lora_strength_from_new_prompt_format(
    monkeypatch,
):
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
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.prompt == "cinematic portrait"
    assert response.lora_name == "qwen/YARN_1.0.safetensors"
    assert response.lora_strength == 0.35
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_keeps_legacy_lora_prompt_without_strength(
    monkeypatch,
):
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
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.prompt == "cinematic portrait"
    assert response.lora_name == "qwen/realistic_texture.safetensors"
    assert response.lora_strength is None
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_keeps_non_video_billing_resolution_read_only(
    monkeypatch,
):
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
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.billing_resolution is None
    assert history.billing_resolution == "720"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_apply_context_prefers_requested_duration_and_strips_ltx_prefix(
    monkeypatch,
):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="ltx_video",
        prompt="[1280x704|20s] cinematic motion",
        billing_resolution="1280x704",
        width=1280,
        height=704,
        duration=1,
        requested_duration=20,
    )
    session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: session)
    response = await users_router.get_favorite_apply_context(
        "task-1",
        current_user=type("User", (), {"id": 123})(),
        db=session,
    )

    assert response.prompt == "cinematic motion"
    assert response.duration == 1
    assert response.requested_duration == 20
    session.commit.assert_not_awaited()
