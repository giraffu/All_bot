from unittest.mock import AsyncMock, Mock

import pytest

from config import MINIO_BUCKET

from src.services.qqcc_demo_generation_service import (
    QqccDemoGenerationError,
    get_qqcc_demo_generation,
    submit_qqcc_demo_generation,
)


class FakeStorage:
    r2_bucket = "demo-bucket"

    def __init__(self):
        self.r2_client = Mock()
        self.r2_client.get_object.return_value = {"Body": Mock(read=Mock(return_value=b"\x89PNG\r\n\x1a\ninput"))}
        self.client = Mock()
        self.upload_bytes = Mock(return_value="qqcc/demo-generation/task-1/input.png")


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
            {"name": "BreastGrow", "strength": 0.75},
            {"name": "Footjob", "strength": 1.4},
        ],
    )


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
            {"name": "BreastGrow", "strength": 0.75},
            {"name": "Footjob", "strength": 1.4},
        ],
    )

@pytest.mark.asyncio
async def test_submit_ai_video_demo_uses_ltx_without_running_tail_chain():
    storage = FakeStorage()
    image = Mock()
    image.submit_ltx_video_task = AsyncMock(return_value="task-ltx")

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
    image.submit_ltx_video_task.assert_awaited_once_with(
        "task-ltx",
        "camera orbit",
        "qqcc/demo-generation/task-ltx/input.png",
        lora_items=[
            {
                "name": "ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors",
                "strength": 0.75,
            }
        ],
        width=1280,
        height=704,
        length=15,
        priority=0,
        negative_prompt="blur",
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
