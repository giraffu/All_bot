import pytest

from src.web_api.routers.utils import (
    probe_apply_context_media_metadata,
    resolve_apply_context_media_metadata,
)


def test_resolve_apply_context_media_metadata_prefers_primary_values():
    media_type, width, height, duration = resolve_apply_context_media_metadata(
        task_type="custom_video",
        primary_media_type="video",
        primary_width=720,
        primary_height=1280,
        primary_duration=8,
        fallback_width=512,
        fallback_height=768,
        fallback_duration=5,
    )

    assert media_type == "video"
    assert width == 720
    assert height == 1280
    assert duration == 8


def test_resolve_apply_context_media_metadata_falls_back_to_history_type_and_secondary_values():
    media_type, width, height, duration = resolve_apply_context_media_metadata(
        task_type="image",
        primary_width=None,
        primary_height=None,
        primary_duration=None,
        fallback_width=1024,
        fallback_height=1024,
        fallback_duration=None,
    )

    assert media_type == "image"
    assert width == 1024
    assert height == 1024
    assert duration is None


@pytest.mark.asyncio
async def test_probe_apply_context_media_metadata_backfills_missing_values():
    async def _probe(_output_file: str, _media_type: str):
        return 1024, 1024, 8

    width, height, duration, billing_resolution = (
        await probe_apply_context_media_metadata(
            output_file="bot-data/history/task-1/output.mp4",
            media_type="video",
            width=None,
            height=None,
            duration=None,
            billing_resolution=None,
            task_type="custom_video",
            task_id="task-1",
            probe_media_metadata=_probe,
        )
    )

    assert width == 1024
    assert height == 1024
    assert duration == 8
    assert billing_resolution == "1024"


@pytest.mark.asyncio
async def test_probe_apply_context_media_metadata_keeps_existing_values_on_probe_failure():
    async def _probe(_output_file: str, _media_type: str):
        raise RuntimeError("boom")

    width, height, duration, billing_resolution = (
        await probe_apply_context_media_metadata(
            output_file="bot-data/history/task-2/output.mp4",
            media_type="video",
            width=512,
            height=768,
            duration=5,
            billing_resolution="768",
            task_type="custom_video",
            task_id="task-2",
            probe_media_metadata=_probe,
        )
    )

    assert width == 512
    assert height == 768
    assert duration == 5
    assert billing_resolution == "768"
