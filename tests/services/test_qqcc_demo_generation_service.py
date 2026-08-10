from io import BytesIO
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from config import MINIO_BUCKET

from src.services.qqcc_demo_generation_service import (
    QqccDemoGenerationError,
    get_qqcc_demo_generation,
    submit_qqcc_demo_generation,
)
from src.services.qqcc_video_frame_adapter import QqccVideoFrameAdaptationError
from src.services import qqcc_demo_generation_service as demo_service


class FakeStorage:
    r2_bucket = "demo-bucket"

    def __init__(self):
        self.r2_client = Mock()
        self.r2_client.get_object.return_value = {"Body": Mock(read=Mock(return_value=b"\x89PNG\r\n\x1a\ninput"))}
        self.client = Mock()
        self.upload_bytes = Mock(return_value="qqcc/demo-generation/task-1/input.png")


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, *, ex):
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, key):
        self.values.pop(key, None)


def _png_bytes(size=(400, 300)):
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_video_demo_generation_advances_and_stitches_full_scene_chain(monkeypatch):
    storage = FakeStorage()
    redis = FakeRedis()
    image = Mock()
    image.submit_image_to_video_task = AsyncMock(
        side_effect=["chain-demo-0", "chain-demo-1"]
    )
    image.get_task_status = AsyncMock(return_value={"status": "done"})
    image.download_video_result = AsyncMock(side_effect=[b"....ftyp-one", b"....ftyp-two"])
    monkeypatch.setattr(demo_service, "extract_qqcc_video_last_frame", AsyncMock(return_value=_png_bytes()))
    monkeypatch.setattr(demo_service, "_read_minio_bytes", lambda *_args: b"segment")
    stitch = AsyncMock(return_value=b"....ftyp-stitched")
    monkeypatch.setattr(demo_service, "stitch_qqcc_video_segments", stitch)
    upload = AsyncMock(return_value={"object_key": "qqcc/demo/video/first/generated/chain-demo/output"})
    config = {
        "video_scenes": [
            {"id": "first", "name": "First", "prompt": "one", "duration": "5s", "engine": "image_to_video", "next_scene_id": "second"},
            {"id": "second", "name": "Second", "prompt": "two", "duration": "5s", "engine": "image_to_video"},
        ]
    }
    root = {
        **config["video_scenes"][0],
        "demo_input_media": {"object_key": "qqcc/demo/video/first/input", "mime_type": "image/png"},
    }

    submitted = await submit_qqcc_demo_generation(
        scene_kind="video", scene=root, config=config, task_id="chain-demo",
        storage_service=storage, image_service_instance=image, redis_instance=redis,
    )
    first_poll = await get_qqcc_demo_generation(
        generation_id="chain-demo", scene_kind="video", scene_id="first",
        storage_service=storage, image_service_instance=image, redis_instance=redis,
        upload_demo_media_func=upload,
    )
    second_poll = await get_qqcc_demo_generation(
        generation_id="chain-demo", scene_kind="video", scene_id="first",
        storage_service=storage, image_service_instance=image, redis_instance=redis,
        upload_demo_media_func=upload, preview_url_builder=lambda _media: "preview",
    )

    assert submitted["status"] == "pending"
    assert first_poll["status"] == "pending"
    assert second_poll["status"] == "done"
    assert second_poll["preview_url"] == "preview"
    stitch.assert_awaited_once_with([b"segment", b"segment"])


@pytest.mark.asyncio
async def test_submit_draw_demo_uses_scene_model_without_billing_or_history():
    storage = FakeStorage()
    image = Mock()
    image.submit_pornmaster_flux2_edit_task = AsyncMock(return_value="task-1")

    result = await submit_qqcc_demo_generation(
        scene_kind="draw",
        scene={
            "id": "portrait",
            "prompt": "portrait prompt",
            "negative_prompt": "bad hands",
            "engine": "free_edit_v2",
            "demo_input_media": {
                "object_key": "qqcc/demo/draw/portrait/input",
                "mime_type": "image/png",
            },
        },
        object_prefix="qqcc/demo",
        task_id="task-1",
        storage_service=storage,
        image_service_instance=image,
    )

    assert result == {"generation_id": "task-1", "status": "pending"}
    image.submit_pornmaster_flux2_edit_task.assert_awaited_once_with(
        "task-1",
        execution_task_type="pornmaster_flux2_single_edit",
        prompt="portrait prompt",
        image_paths=["qqcc/demo-generation/task-1/input.png"],
        negative_prompt="bad hands",
        priority=0,
    )


@pytest.mark.asyncio
async def test_submit_rejects_input_from_another_tenant_namespace():
    with pytest.raises(QqccDemoGenerationError, match="input media"):
        await submit_qqcc_demo_generation(
            scene_kind="filter",
            scene={
                "id": "portrait",
                "prompt": "prompt",
                "engine": "free_edit_v2",
                "demo_input_media": {
                    "object_key": "qqcc/private/8/demo/filter/portrait/input",
                    "mime_type": "image/png",
                },
            },
            object_prefix="qqcc/private/7/demo",
            task_id="task-2",
            storage_service=FakeStorage(),
            image_service_instance=Mock(),
        )


@pytest.mark.asyncio
async def test_done_generation_uploads_output_to_draft_demo_slot_and_cleans_input():
    storage = FakeStorage()
    image = Mock()
    image.get_task_status = AsyncMock(return_value={"status": "done"})
    image.download_result = AsyncMock(return_value=b"\x89PNG\r\n\x1a\noutput")
    upload = AsyncMock(return_value={"object_key": "qqcc/demo/draw/portrait/output"})

    result = await get_qqcc_demo_generation(
        generation_id="task-1",
        scene_kind="draw",
        scene_id="portrait",
        object_prefix="qqcc/demo",
        storage_service=storage,
        image_service_instance=image,
        upload_demo_media_func=upload,
        preview_url_builder=lambda media: "https://preview.example/output.png",
    )

    assert result["status"] == "done"
    assert result["media"]["object_key"].endswith("/output")
    assert result["preview_url"] == "https://preview.example/output.png"
    assert upload.await_args.kwargs["generated_object_id"] == "task-1"
    storage.client.remove_object.assert_called_once_with(
        MINIO_BUCKET, "qqcc/demo-generation/task-1/input.png"
    )


@pytest.mark.asyncio
async def test_submit_video_demo_uses_scene_duration_prompt_and_engine():
    storage = FakeStorage()
    image = Mock()
    image.submit_wan22_video_v2_task = AsyncMock(return_value="task-video")

    result = await submit_qqcc_demo_generation(
        scene_kind="video",
        scene={
            "id": "kiss",
            "prompt": "kiss prompt",
            "negative_prompt": "blur",
            "engine": "wan22_video_v2",
            "duration": "8s",
            "lora_items": [
                {"name": "BreastGrow", "strength": 0.75},
                {"name": "Footjob", "strength": 1.4},
            ],
            "demo_input_media": {
                "object_key": "qqcc/demo/video/kiss/input",
                "mime_type": "image/png",
            },
        },
        task_id="task-video",
        storage_service=storage,
        image_service_instance=image,
    )

    assert result["status"] == "pending"
    image.submit_wan22_video_v2_task.assert_awaited_once_with(
        "task-video",
        "kiss prompt",
        "qqcc/demo-generation/task-video/input.png",
        negative_prompt="blur",
        resolution_preset="512p",
        length=8,
        priority=0,
        lora_items=[
            {"name": "wan22_explicit_077", "strength": 0.75},
            {"name": "wan22_explicit_040", "strength": 1.4},
        ],
    )


@pytest.mark.asyncio
async def test_submit_video_demo_safely_adapts_input_bytes_before_central_upload():
    storage = FakeStorage()
    storage.r2_client.get_object.return_value = {
        "Body": Mock(read=Mock(return_value=_png_bytes()))
    }
    image = Mock()
    image.submit_wan22_video_v2_task = AsyncMock(return_value="task-portrait")

    await submit_qqcc_demo_generation(
        scene_kind="video",
        scene={
            "id": "portrait",
            "prompt": "move",
            "engine": "wan22_video_v2",
            "aspect_ratio": "9:16",
            "demo_input_media": {
                "object_key": "qqcc/demo/video/portrait/input",
                "mime_type": "image/png",
            },
        },
        task_id="task-portrait",
        storage_service=storage,
        image_service_instance=image,
    )

    uploaded = storage.upload_bytes.call_args.args[0]
    with Image.open(BytesIO(uploaded)) as uploaded_image:
        assert uploaded_image.size == (225, 400)


@pytest.mark.asyncio
async def test_submit_video_demo_adaptation_failure_does_not_upload_or_submit():
    storage = FakeStorage()
    image = Mock()
    image.submit_wan22_video_v2_task = AsyncMock()

    with pytest.raises(QqccVideoFrameAdaptationError):
        await submit_qqcc_demo_generation(
            scene_kind="video",
            scene={
                "id": "broken",
                "prompt": "move",
                "engine": "wan22_video_v2",
                "aspect_ratio": "1:1",
                "demo_input_media": {
                    "object_key": "qqcc/demo/video/broken/input",
                    "mime_type": "image/png",
                },
            },
            task_id="task-broken",
            storage_service=storage,
            image_service_instance=image,
        )

    storage.upload_bytes.assert_not_called()
    image.submit_wan22_video_v2_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_legacy_video_demo_forwards_ordered_lora_items_and_strengths():
    storage = FakeStorage()
    image = Mock()
    image.submit_image_to_video_task = AsyncMock(return_value="task-legacy-video")

    await submit_qqcc_demo_generation(
        scene_kind="video",
        scene={
            "id": "legacy",
            "prompt": "move",
            "engine": "image_to_video",
            "duration": "5s",
            "lora_items": [
                {"name": "BreastGrow", "strength": 0.75},
                {"name": "Footjob", "strength": 1.4},
            ],
            "demo_input_media": {
                "object_key": "qqcc/demo/video/legacy/input",
                "mime_type": "image/png",
            },
        },
        task_id="task-legacy-video",
        storage_service=storage,
        image_service_instance=image,
    )

    image.submit_image_to_video_task.assert_awaited_once_with(
        "task-legacy-video",
        "move",
        "qqcc/demo-generation/task-legacy-video/input.png",
        "",
        negative_prompt="",
        resolution_preset="512p",
        width=512,
        height=512,
        length=5,
        priority=0,
        lora_items=[
            {"name": "wan22_explicit_077", "strength": 0.75},
            {"name": "wan22_explicit_040", "strength": 1.4},
        ],
    )

@pytest.mark.asyncio
async def test_submit_ai_video_demo_uses_pro_i2v_without_running_tail_chain():
    storage = FakeStorage()
    image = Mock()
    image.submit_minimax_h3_task = AsyncMock(return_value="task-ltx")

    result = await submit_qqcc_demo_generation(
        scene_kind="ai_video",
        scene={
            "id": "cinema",
            "prompt": "camera orbit",
            "negative_prompt": "blur",
            "duration": 15,
            "end_frame_draw_scene_id": "tail_scene",
            "lora_items": [
                {
                    "path": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                    "strength": 0.75,
                }
            ],
            "demo_input_media": {
                "object_key": "qqcc/demo/ai_video/cinema/input",
                "mime_type": "image/png",
            },
        },
        task_id="task-ltx",
        storage_service=storage,
        image_service_instance=image,
    )

    assert result["status"] == "pending"
    image.submit_minimax_h3_task.assert_awaited_once_with(
        "task-ltx",
        task_type="minimax_h3_i2v",
        prompt="camera orbit",
        images=("qqcc/demo-generation/task-ltx/input.png",),
        reference_descriptions=(),
        duration=15,
        resolution_preset="preview",
        aspect_ratio="source",
        width=0,
        height=0,
        frame_count=362,
        fps=24,
        seed=None,
        priority=0,
    )


@pytest.mark.asyncio
async def test_failed_generation_reports_terminal_error_and_cleans_input():
    storage = FakeStorage()
    image = Mock()
    image.get_task_status = AsyncMock(return_value={"status": "error", "error": "worker failed"})

    result = await get_qqcc_demo_generation(
        generation_id="task-1",
        scene_kind="draw",
        scene_id="portrait",
        storage_service=storage,
        image_service_instance=image,
    )

    assert result == {
        "generation_id": "task-1",
        "status": "failed",
        "error": "worker failed",
    }
    storage.client.remove_object.assert_called_once()
