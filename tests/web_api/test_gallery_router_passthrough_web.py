from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException
from types import SimpleNamespace

from src.web_api.schemas.gallery_schema import GallerySubmitRequest
from src.web_api.services.gallery_service_support import (
    DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS,
    build_gallery_config_payload,
    submit_gallery_post_payload,
)


def _build_current_user():
    return type("User", (), {"id": 123, "username": "tester"})()


@pytest.mark.asyncio
async def test_build_gallery_config_payload_uses_mode_names_and_filters_empty_lora_entries():
    payload = build_gallery_config_payload(
        allowed_type_configs=[
            ("mode_a", "task.mode_a"),
            ("mode_b", "task.mode_b"),
        ],
        mode_name_map={"mode_a": "显示名称A"},
        video_lora_models={"": "ignore", "video-1": "视频模型"},
        image_lora_models={"": "ignore", "img-1": "图片模型"},
    )

    assert payload == {
        "allowed_types": [
            {"id": "mode_a", "name": "显示名称A"},
            {"id": "mode_b", "name": "task.mode_b"},
        ],
        "lora_models": [{"id": "video-1", "name": "视频模型"}],
        "img2img_lora_models": [{"id": "img-1", "name": "图片模型"}],
    }


def test_default_gallery_allowed_type_configs_include_txt2img():
    assert ("txt2img", "task.mode_txt2img") in DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS


def test_default_gallery_allowed_type_configs_include_wan22_video_v2():
    assert ("wan22_video_v2", "task.mode_wan22_video_v2") in DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS


def test_default_gallery_allowed_type_configs_include_scail2_modes():
    assert (
        "scail2_action_transfer",
        "task.mode_scail2_action_transfer",
    ) in DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS
    assert (
        "scail2_video_replacement",
        "task.mode_scail2_video_replacement",
    ) in DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS
    assert (
        "scail2_face_swap_v2",
        "task.mode_scail2_face_swap_v2",
    ) in DEFAULT_GALLERY_ALLOWED_TYPE_CONFIGS


@pytest.mark.asyncio
async def test_submit_gallery_post_payload_extracts_request_dimensions():
    process_submit = AsyncMock(return_value={"status": "success"})
    request = GallerySubmitRequest(width=1024, height=768, duration=5)

    response = await submit_gallery_post_payload(
        task_id="task-1",
        schedule_background_task=BackgroundTasks().add_task,
        request=request,
        current_user=_build_current_user(),
        process_submit_to_gallery_fn=process_submit,
    )

    assert response == {"status": "success"}
    process_submit.assert_awaited_once()
    assert process_submit.await_args.kwargs["user_id"] == 123
    assert process_submit.await_args.kwargs["task_id"] == "task-1"
    assert process_submit.await_args.kwargs["width"] == 1024
    assert process_submit.await_args.kwargs["height"] == 768
    assert process_submit.await_args.kwargs["duration"] == 5


@pytest.mark.asyncio
async def test_submit_gallery_post_payload_schedules_side_effects_from_outcome():
    background_tasks = BackgroundTasks()
    scheduled_calls = []

    def _fake_add_task(func, *args):
        scheduled_calls.append((func, args))

    background_tasks.add_task = _fake_add_task
    effect_func = AsyncMock()
    outcome = SimpleNamespace(
        payload={"status": "success", "message": "ok"},
        side_effects=[(effect_func, ("a", "b"))],
    )
    process_submit = AsyncMock(return_value=outcome)

    response = await submit_gallery_post_payload(
        task_id="task-1",
        schedule_background_task=background_tasks.add_task,
        request=GallerySubmitRequest(width=1024, height=768, duration=5),
        current_user=_build_current_user(),
        process_submit_to_gallery_fn=process_submit,
    )

    assert response == {"status": "success", "message": "ok"}
    assert scheduled_calls == [(effect_func, ("a", "b"))]


@pytest.mark.asyncio
async def test_submit_gallery_post_payload_maps_gallery_core_error_to_400():
    class GalleryCoreError(Exception):
        pass

    process_submit = AsyncMock(side_effect=GalleryCoreError("cannot submit"))

    with pytest.raises(HTTPException) as exc_info:
        await submit_gallery_post_payload(
            task_id="task-1",
            schedule_background_task=BackgroundTasks().add_task,
            request=None,
            current_user=_build_current_user(),
            process_submit_to_gallery_fn=process_submit,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "cannot submit"


@pytest.mark.asyncio
async def test_submit_gallery_post_payload_rejects_submission_banned_user():
    with pytest.raises(HTTPException) as exc_info:
        await submit_gallery_post_payload(
            task_id="task-1",
            schedule_background_task=BackgroundTasks().add_task,
            request=None,
            current_user=type(
                "User",
                (),
                {
                    "id": 123,
                    "username": "tester",
                    "is_submission_banned": True,
                    "submission_ban_reason": None,
                },
            )(),
            process_submit_to_gallery_fn=AsyncMock(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "违禁被封，请联系管理员解封"
