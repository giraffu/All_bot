from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.task_core_types import CoreDomainError
from src.web_api.schemas.task_schema import TaskGenerateRequest
from src.web_api.services import task_submission_service
from src.web_api.services.web_submission_preparation import (
    prepare_web_submission_request,
)


def _request(images):
    return SimpleNamespace(
        task_type="ltx25_video_upscale",
        inputs={
            "images": images,
            "duration": 5,
            "resolution": "1080p",
            "prompt": "preserve details",
        },
        prompt=None,
        negative_prompt=None,
        is_template=False,
        source_post_id=None,
    )


@pytest.mark.asyncio
async def test_ltx25_upscale_web_submission_requires_backend_flag():
    with pytest.raises(CoreDomainError, match="高清化"):
        await prepare_web_submission_request(
            _request(["owned/video.mp4"]),
            internal_user_id=7,
            operator_canary_authorized=False,
            env_enabled=lambda _name: False,
        )


@pytest.mark.asyncio
async def test_ltx25_upscale_web_submission_requires_exactly_one_video():
    with pytest.raises(CoreDomainError, match="一个视频"):
        await prepare_web_submission_request(
            _request([]),
            internal_user_id=7,
            operator_canary_authorized=False,
            env_enabled=lambda name: name == "LTX25_VIDEO_UPSCALE_ENABLED",
        )


@pytest.mark.asyncio
async def test_ltx25_upscale_web_submission_uses_probed_duration_before_dispatch():
    probed = []

    async def probe_video_duration(source):
        probed.append(source)
        return 10.125

    prepared = await prepare_web_submission_request(
        _request(["task-results/source/original.mp4"]),
        internal_user_id=7,
        operator_canary_authorized=False,
        env_enabled=lambda name: name == "LTX25_VIDEO_UPSCALE_ENABLED",
        probe_video_duration_func=probe_video_duration,
        probe_video_metadata_func=lambda _source: _async_value((768, 448, 10)),
    )

    assert probed == ["task-results/source/original.mp4"]
    assert prepared.inputs["duration"] == 10
    assert prepared.inputs["resolution"] == "1080p"
    assert prepared.inputs["source_width"] == 768
    assert prepared.inputs["source_height"] == 448


@pytest.mark.asyncio
async def test_ltx25_upscale_web_submission_accepts_h3_encoding_tail():
    prepared = await prepare_web_submission_request(
        _request(["task-results/source/original.mp4"]),
        internal_user_id=7,
        operator_canary_authorized=False,
        env_enabled=lambda name: name == "LTX25_VIDEO_UPSCALE_ENABLED",
        probe_video_duration_func=lambda _source: _async_value(5.166667),
        probe_video_metadata_func=lambda _source: _async_value((768, 448, 5)),
    )

    assert prepared.images == ["task-results/source/original.mp4"]
    assert prepared.inputs["duration"] == 5


@pytest.mark.asyncio
async def test_ltx25_upscale_web_submission_accepts_twenty_second_encoding_tail():
    prepared = await prepare_web_submission_request(
        _request(["task-results/source/original.mp4"]),
        internal_user_id=7,
        operator_canary_authorized=False,
        env_enabled=lambda name: name == "LTX25_VIDEO_UPSCALE_ENABLED",
        probe_video_duration_func=lambda _source: _async_value(20.25),
        probe_video_metadata_func=lambda _source: _async_value((768, 448, 20)),
    )

    assert prepared.inputs["duration"] == 20


@pytest.mark.asyncio
async def test_ltx25_upscale_web_submission_fails_closed_when_duration_is_unknown():
    with pytest.raises(CoreDomainError, match="无法读取视频时长"):
        await prepare_web_submission_request(
            _request(["task-results/source/original.mp4"]),
            internal_user_id=7,
            operator_canary_authorized=False,
            env_enabled=lambda name: name == "LTX25_VIDEO_UPSCALE_ENABLED",
            probe_video_duration_func=lambda _source: _async_value(None),
            probe_video_metadata_func=lambda _source: _async_value((768, 448, 5)),
        )


@pytest.mark.asyncio
async def test_ltx25_upscale_rejects_target_not_above_verified_source_resolution():
    req = _request(["task-results/source/original.mp4"])
    req.inputs["resolution"] = "720p"

    with pytest.raises(CoreDomainError, match="高于原视频"):
        await prepare_web_submission_request(
            req,
            internal_user_id=7,
            operator_canary_authorized=False,
            env_enabled=lambda name: name == "LTX25_VIDEO_UPSCALE_ENABLED",
            probe_video_duration_func=lambda _source: _async_value(10.125),
            probe_video_metadata_func=lambda _source: _async_value((1920, 1080, 10)),
        )


@pytest.mark.asyncio
async def test_ltx25_upscale_over_twenty_seconds_never_reaches_billing_or_promotion(monkeypatch):
    monkeypatch.setenv("LTX25_VIDEO_UPSCALE_ENABLED", "true")
    probe = AsyncMock(return_value=20.251)
    promote = AsyncMock()
    application = SimpleNamespace(submit=AsyncMock())

    with pytest.raises(CoreDomainError, match="最长 20 秒"):
        await task_submission_service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="ltx25_video_upscale",
                inputs={
                    "images": ["staging/user-uploads/7/ten-seconds.mp4"],
                    "duration": 5,
                },
            ),
            current_user=SimpleNamespace(id=7, username="tester"),
            get_balance=AsyncMock(return_value=100),
            promote_staged_inputs_func=promote,
            task_application=application,
            probe_video_duration_func=probe,
            probe_video_metadata_func=lambda _source: _async_value((768, 448, 20)),
        )

    probe.assert_awaited_once_with("staging/user-uploads/7/ten-seconds.mp4")
    promote.assert_not_awaited()
    application.submit.assert_not_awaited()


async def _async_value(value):
    return value
