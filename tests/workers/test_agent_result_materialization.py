import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
import io


ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = ROOT / "workers" / "runpod_runtime" / "comfy_agent"
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


def test_character_reference_sheet_is_deterministic_three_by_two():
    payload = materialization._compose_character_sheet(
        [_png((i * 30, 0, 0)) for i in range(1, 7)]
    )
    with Image.open(io.BytesIO(payload)) as sheet:
        assert sheet.size == (1536, 896)
        assert sheet.getpixel((256, 224)) == (30, 0, 0)
        assert sheet.getpixel((1280, 672)) == (180, 0, 0)


def test_character_reference_sheet_preserves_portrait_head_and_feet():
    portrait = _portrait_png_with_head_and_feet_markers()

    payload = materialization._compose_character_sheet([portrait] * 6)

    with Image.open(io.BytesIO(payload)) as sheet:
        first_tile = sheet.crop((0, 0, 512, 448))
        colors = first_tile.getcolors(maxcolors=512 * 448)
        assert colors is not None
        color_counts = {color: count for count, color in colors}
        assert any(
            red > 200 and green < 30 and blue < 30
            for red, green, blue in color_counts
        )
        assert any(
            blue > 200 and red < 30 and green < 30
            for red, green, blue in color_counts
        )


def test_character_reference_sheet_rejects_missing_or_corrupt_views():
    with pytest.raises(RuntimeError, match="exactly six"):
        materialization._compose_character_sheet([_png("black")] * 5)
    with pytest.raises(RuntimeError, match="corrupt"):
        materialization._compose_character_sheet([b"broken"] + [_png("black")] * 5)
