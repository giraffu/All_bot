import pytest
from pydantic import ValidationError

from backend.app.models import Ltx25VideoUpscaleRequest


def test_ltx25_upscale_request_accepts_twenty_seconds_and_2k():
    request = Ltx25VideoUpscaleRequest(
        task_id="task-1",
        video="source.mp4",
        length=20,
        resolution="2K",
    )

    assert request.length == 20
    assert request.resolution == "2k"


def test_ltx25_upscale_request_rejects_unsupported_resolution():
    with pytest.raises(ValidationError, match="720p、1080p 或 2K"):
        Ltx25VideoUpscaleRequest(
            task_id="task-1",
            video="source.mp4",
            length=5,
            resolution="4k",
        )
