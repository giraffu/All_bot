import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


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
