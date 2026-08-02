import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image
import io


ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = ROOT / "workers" / "comfy_agent"
if str(WORKER_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_DIR))

import agent_result_materialization as materialization  # noqa: E402


class DummyComfyClient:
    async def get_history(self, prompt_id):
        return {
            prompt_id: {
                "outputs": {
                    "28": {
                        "gifs": [
                            {
                                "filename": "image_to_video_42_video_00001.mp4",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    }
                }
            }
        }

    async def get_view(self, filename, subfolder="", type="output"):
        assert filename == "image_to_video_42_video_00001.mp4"
        return b"video-bytes"


@pytest.mark.asyncio
async def test_materialize_wan22_aio_extracts_fallback_last_frame(monkeypatch):
    monkeypatch.setattr(
        materialization,
        "_extract_last_frame_from_video_bytes",
        lambda _video_bytes, _logger: b"png-bytes",
    )
    execution = SimpleNamespace(
        prompt_id="prompt-1",
        task_id="task-1",
        task_result=None,
        task_result_priority=0,
    )

    outputs = await materialization.materialize_task_outputs(
        comfy_client=DummyComfyClient(),
        execution=execution,
        task_type="image_to_video",
        logger=SimpleNamespace(
            warning=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
        ),
    )

    assert outputs.primary.object_name == "task-1__image_to_video_42_video_00001.mp4"
    assert outputs.extra_outputs["last_frame"].object_name == (
        "task-1__image_to_video_42_last_frame_00001.png"
    )
    assert outputs.extra_outputs["last_frame"].media_type == "image"
    assert outputs.extra_outputs["last_frame"].file_data == b"png-bytes"


@pytest.mark.asyncio
@pytest.mark.parametrize("task_type", ["ltx_t2v_ic", "ltx_video_v2"])
async def test_materialize_ltx_video_extracts_fallback_last_frame(
    monkeypatch, task_type
):
    assert not hasattr(materialization, "_trim_ltx_t2v_ic_guide_tail")
    monkeypatch.setattr(
        materialization,
        "_extract_last_frame_from_video_bytes",
        lambda video_bytes, _logger: b"last-frame:" + video_bytes,
    )
    execution = SimpleNamespace(
        prompt_id="prompt-1",
        task_id="task-1",
        task_result=None,
        task_result_priority=0,
    )

    outputs = await materialization.materialize_task_outputs(
        comfy_client=DummyComfyClient(),
        execution=execution,
        task_type=task_type,
        logger=SimpleNamespace(
            warning=lambda *args, **kwargs: None,
            info=lambda *args, **kwargs: None,
        ),
    )

    assert outputs.primary.file_data == b"video-bytes"
    assert outputs.extra_outputs["last_frame"].file_data == (
        b"last-frame:video-bytes"
    )


def _png(color):
    output = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(output, format="PNG")
    return output.getvalue()


def _portrait_png_with_head_and_feet_markers():
    image = Image.new("RGB", (300, 900), "black")
    image.paste((255, 0, 0), (0, 0, 300, 100))
    image.paste((0, 0, 255), (0, 800, 300, 900))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_character_reference_sheet_is_one_official_style_character_panel():
    payload = materialization._compose_character_sheet(
        [_png((i * 30, 0, 0)) for i in range(1, 7)]
    )
    with Image.open(io.BytesIO(payload)) as sheet:
        assert sheet.size == (1536, 896)
        assert sheet.getpixel((288, 448)) == (30, 0, 0)
        assert sheet.getpixel((736, 448)) == (120, 0, 0)
        assert sheet.getpixel((1056, 448)) == (150, 0, 0)
        assert sheet.getpixel((1376, 448)) == (180, 0, 0)


def test_character_reference_sheet_preserves_portrait_head_and_feet():
    portrait = _portrait_png_with_head_and_feet_markers()

    payload = materialization._compose_character_sheet([portrait] * 6)

    with Image.open(io.BytesIO(payload)) as sheet:
        body_tile = sheet.crop((576, 0, 896, 896))
        colors = body_tile.getcolors(maxcolors=320 * 896)
        assert colors is not None
        color_counts = {color: count for count, color in colors}
        assert any(
            red > 200 and green < 30 and blue < 30 for red, green, blue in color_counts
        )
        assert any(
            blue > 200 and red < 30 and green < 30 for red, green, blue in color_counts
        )


def test_character_reference_sheet_rejects_missing_or_corrupt_views():
    with pytest.raises(RuntimeError, match="exactly six"):
        materialization._compose_character_sheet([_png("black")] * 5)
    with pytest.raises(RuntimeError, match="corrupt"):
        materialization._compose_character_sheet([b"broken"] + [_png("black")] * 5)


@pytest.mark.asyncio
async def test_character_reference_single_view_materializes_without_six_view_gate():
    payload = _png((10, 20, 30))
    comfy_client = SimpleNamespace(
        get_history=AsyncMock(
            return_value={
                "prompt-1": {
                    "outputs": {
                        "v3:201": {
                            "images": [
                                {
                                    "filename": "character_reference_view_03_task.png",
                                    "subfolder": "",
                                    "type": "output",
                                }
                            ]
                        }
                    }
                }
            }
        ),
        get_view=AsyncMock(return_value=payload),
    )
    execution = SimpleNamespace(
        prompt_id="prompt-1",
        task_id="task-1",
        params={"character_view_index": 3},
        task_result=None,
        task_result_priority=-1,
    )

    result = await materialization.materialize_task_outputs(
        comfy_client=comfy_client,
        execution=execution,
        task_type="character_reference_build",
        logger=SimpleNamespace(error=lambda *_args: None),
    )

    assert result.primary.file_data == payload
    assert result.primary.object_name == "task-1_character_reference_view_03.png"


def test_character_reference_views_reject_repeated_front_view():
    repeated = _portrait_png_with_head_and_feet_markers()

    with pytest.raises(RuntimeError, match="visual camera-view diversity"):
        materialization._validate_character_view_diversity([repeated] * 6)
