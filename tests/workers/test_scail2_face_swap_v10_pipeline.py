import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKER_MODULE_DIR = ROOT / "workers" / "comfy_agent"
if str(WORKER_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKER_MODULE_DIR))

from workers.comfy_agent.scail2_face_swap_v10_pipeline import (  # noqa: E402
    prepare_scail2_face_swap_v10_reference,
)


class FakePatcher:
    def __init__(self, workflows_dir: Path):
        self.workflows_dir = str(workflows_dir)

    def strip_meta(self, workflow):
        return workflow

    def patch_workflow(self, task_type, workflow, params):
        assert task_type == "face_swap_v2"
        workflow["2"]["inputs"]["image"] = params["face_image"]
        workflow["3"]["inputs"]["image"] = params["body_image"]
        workflow["18"]["inputs"]["noise_seed"] = params["seed"]
        return workflow


class FakeAuxComfyClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.uploads = []
        self.queued_prompt = None
        self.closed = False

    async def upload_image(self, file_content, filename):
        self.uploads.append((filename, file_content))

    async def queue_prompt(self, prompt, client_id):
        self.queued_prompt = (prompt, client_id)
        return "aux-prompt"

    async def get_history(self, prompt_id):
        assert prompt_id == "aux-prompt"
        return {
            "aux-prompt": {
                "outputs": {
                    "4": {
                        "images": [
                            {
                                "filename": "swapped.png",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    }
                }
            }
        }

    async def get_view(self, filename, subfolder="", type="output"):
        assert filename == "swapped.png"
        return b"swapped-image"

    async def close(self):
        self.closed = True


class FakePrimaryComfyClient:
    def __init__(self):
        self.uploads = []

    async def upload_image(self, file_content, filename):
        self.uploads.append((filename, file_content))


@pytest.mark.asyncio
async def test_prepare_scail2_face_swap_v10_reference_replaces_reference_image(tmp_path):
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir()
    (workflows_dir / "face_swap_v2.json").write_text(
        json.dumps(
            {
                "2": {"inputs": {"image": "face.png"}, "class_type": "LoadImage"},
                "3": {"inputs": {"image": "body.png"}, "class_type": "LoadImage"},
                "4": {
                    "inputs": {"filename_prefix": "face_swap_v2"},
                    "class_type": "SaveImage",
                },
                "18": {
                    "inputs": {"noise_seed": 0},
                    "class_type": "RandomNoise",
                },
            }
        ),
        encoding="utf-8",
    )

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "reference.png").write_bytes(b"reference")
    (input_dir / "motion.mp4").write_bytes(b"video")

    def fake_extract_first_frame(video_path: Path, output_path: Path) -> None:
        assert video_path == input_dir / "motion.mp4"
        output_path.write_bytes(b"first-frame")

    aux_clients = []

    def make_aux_client(base_url):
        client = FakeAuxComfyClient(base_url)
        aux_clients.append(client)
        return client

    params = {"image": "reference.png", "video": "motion.mp4", "seed": 123}
    downloaded = []
    primary_client = FakePrimaryComfyClient()

    swapped_name = await prepare_scail2_face_swap_v10_reference(
        task_id="task-1",
        params=params,
        downloaded_input_paths=downloaded,
        comfy_input_dir=str(input_dir),
        workflows_dir=str(workflows_dir),
        patcher=FakePatcher(workflows_dir),
        primary_comfy_client=primary_client,
        face_swap_comfy_api_url="http://face-swap-runtime",
        face_swap_workflow_filename="face_swap_v2.json",
        client_id="agent_worker_v10",
        logger=SimpleNamespace(info=lambda *args, **kwargs: None),
        timeout_seconds=1,
        poll_interval_seconds=0,
        comfy_client_factory=make_aux_client,
        extract_first_frame_func=fake_extract_first_frame,
    )

    assert swapped_name == "task-1_v10_swapped_first_frame.png"
    assert params["image"] == swapped_name
    assert (input_dir / swapped_name).read_bytes() == b"swapped-image"
    assert primary_client.uploads == [(swapped_name, b"swapped-image")]
    assert len(aux_clients) == 1
    aux_client = aux_clients[0]
    assert aux_client.base_url == "http://face-swap-runtime"
    assert aux_client.closed is True
    assert [name for name, _ in aux_client.uploads] == [
        "task-1_v10_face_reference.png",
        "task-1_v10_body_first_frame.png",
    ]
    prompt, client_id = aux_client.queued_prompt
    assert client_id == "agent_worker_v10"
    assert prompt["2"]["inputs"]["image"] == "task-1_v10_face_reference.png"
    assert prompt["3"]["inputs"]["image"] == "task-1_v10_body_first_frame.png"
    assert prompt["4"]["inputs"]["filename_prefix"] == (
        "task-1_v10_firstframe_faceswap_image"
    )
    assert prompt["18"]["inputs"]["noise_seed"] == 123
    assert str(input_dir / "task-1_v10_driving_first_frame.png") in downloaded
    assert str(input_dir / swapped_name) in downloaded
