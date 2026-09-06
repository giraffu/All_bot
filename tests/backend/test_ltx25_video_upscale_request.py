import pytest
from pydantic import ValidationError

from backend.app.models import Ltx25VideoUpscaleRequest


def test_ltx25_upscale_request_accepts_fifteen_seconds_and_2k():
    request = Ltx25VideoUpscaleRequest(
        task_id="task-1",
        video="source.mp4",
        length=15,
        resolution="2K",
    )

    assert request.length == 15
    assert request.resolution == "2k"


def test_ltx25_upscale_request_rejects_unsupported_resolution():
    with pytest.raises(ValidationError, match="720p、1080p 或 2K"):
        Ltx25VideoUpscaleRequest(
            task_id="task-1",
            video="source.mp4",
            length=5,
            resolution="4k",
        )


def test_ltx25_upscale_request_rejects_more_than_fifteen_seconds():
    with pytest.raises(ValidationError, match="1 至 15 秒"):
        Ltx25VideoUpscaleRequest(
            task_id="task-1",
            video="source.mp4",
            length=16,
            resolution="1080p",
        )
