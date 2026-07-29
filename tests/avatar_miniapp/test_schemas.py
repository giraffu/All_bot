import pytest
from pydantic import ValidationError

from src.avatar_miniapp.schemas import RenderCreateRequest


def test_render_request_accepts_catalog_values():
    payload = RenderCreateRequest(
        asset_id="asset-id",
        animation_id="dance_lite",
        camera_preset="portrait",
        resolution="720x1280",
        fps=24,
        duration_seconds=3,
        background="studio",
        loop=True,
    )

    assert payload.resolution == "720x1280"
    assert payload.duration_seconds == 3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("animation_id", "custom-script"),
        ("resolution", "3840x2160"),
        ("fps", 60),
        ("duration_seconds", 11),
        ("camera_preset", "../../etc/passwd"),
    ],
)
def test_render_request_rejects_values_outside_catalog(field, value):
    values = {
        "asset_id": "asset-id",
        "animation_id": "idle",
        "camera_preset": "full_body",
        "resolution": "1280x720",
        "fps": 30,
        "duration_seconds": 5,
        "background": "dark",
        "loop": True,
    }
    values[field] = value

    with pytest.raises(ValidationError):
        RenderCreateRequest(**values)
