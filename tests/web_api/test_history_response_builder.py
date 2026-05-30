from datetime import datetime
from types import SimpleNamespace

import pytest

from src.web_api.services import history_response_builder
from src.web_api.services.history_response_builder import build_favorite_gallery_payload


@pytest.mark.asyncio
async def test_build_favorite_gallery_payload_uses_history_media_type_when_gallery_post_missing(
    monkeypatch,
):
    history = SimpleNamespace(
        task_id="task-legacy-video",
        output_file="123/output_images/task-legacy-video.mp4",
        type="doggy_style",
        billing_resolution=None,
        width=720,
        height=1280,
        duration=8,
        prompt=None,
        created_at=datetime(2026, 5, 27),
    )

    async def fake_resolve_history_media_urls_func(**_kwargs):
        return "https://example.com/task-legacy-video.mp4", ""

    monkeypatch.setattr(
        history_response_builder,
        "resolve_history_media_urls",
        fake_resolve_history_media_urls_func,
    )

    items = await build_favorite_gallery_payload(
        histories=[history],
        gallery_post_map={},
    )

    assert len(items) == 1
    assert items[0].media_type == "video"
    assert items[0].task_type == "doggy_style"
