from types import SimpleNamespace

import pytest

from src.core.task_core_types import CoreDomainError
from src.web_api.services.web_submission_preparation import (
    prepare_web_submission_request,
)


def _request(images):
    return SimpleNamespace(
        task_type="ltx25_video_upscale",
        inputs={"images": images, "duration": 5, "prompt": "preserve details"},
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
