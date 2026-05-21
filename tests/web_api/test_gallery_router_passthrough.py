from unittest.mock import AsyncMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from src.web_api.routers import gallery as gallery_router
from src.web_api.schemas.gallery_schema import GallerySubmitRequest
from src.web_api.services import gallery_service


def _build_current_user():
    return type("User", (), {"id": 123, "username": "tester"})()


@pytest.mark.asyncio
async def test_build_gallery_config_payload_uses_mode_names_and_filters_empty_img2img_lora():
    payload = gallery_service.build_gallery_config_payload(
        allowed_type_configs=[
            ("mode_a", "task.mode_a"),
            ("mode_b", "task.mode_b"),
        ],
        mode_name_map={"mode_a": "显示名称A"},
        video_lora_models={"video-1": "视频模型"},
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


@pytest.mark.asyncio
async def test_submit_gallery_post_payload_extracts_request_dimensions():
    process_submit = AsyncMock(return_value={"status": "success"})
    request = GallerySubmitRequest(width=1024, height=768, duration=5)

    response = await gallery_service.submit_gallery_post_payload(
        task_id="task-1",
        background_tasks=BackgroundTasks(),
        request=request,
        current_user=_build_current_user(),
        process_submit_to_gallery_fn=process_submit,
    )

    assert response == {"status": "success"}
    process_submit.assert_awaited_once()
    assert process_submit.await_args.args[0] == 123
    assert process_submit.await_args.args[1] == "task-1"
    assert isinstance(process_submit.await_args.args[2], BackgroundTasks)
    assert process_submit.await_args.args[3:] == (1024, 768, 5)


@pytest.mark.asyncio
async def test_submit_gallery_post_payload_maps_gallery_core_error_to_400():
    class GalleryCoreError(Exception):
        pass

    process_submit = AsyncMock(side_effect=GalleryCoreError("cannot submit"))

    with pytest.raises(HTTPException) as exc_info:
        await gallery_service.submit_gallery_post_payload(
            task_id="task-1",
            background_tasks=BackgroundTasks(),
            request=None,
            current_user=_build_current_user(),
            process_submit_to_gallery_fn=process_submit,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "cannot submit"


@pytest.mark.asyncio
async def test_get_gallery_config_routes_to_service():
    expected = {"allowed_types": [], "lora_models": [], "img2img_lora_models": []}

    with patch(
        "src.web_api.routers.gallery.build_gallery_config_payload",
        return_value=expected,
    ) as mock_service:
        response = await gallery_router.get_gallery_config()

    assert response == expected
    mock_service.assert_called_once()


@pytest.mark.asyncio
async def test_submit_to_gallery_routes_to_service():
    request = GallerySubmitRequest(width=512, height=512, duration=4)
    background_tasks = BackgroundTasks()
    current_user = _build_current_user()

    with patch(
        "src.web_api.routers.gallery.submit_gallery_post_payload",
        new=AsyncMock(return_value={"status": "success"}),
    ) as mock_service:
        response = await gallery_router.submit_to_gallery(
            "task-1",
            background_tasks,
            current_user=current_user,
            request=request,
        )

    assert response == {"status": "success"}
    mock_service.assert_awaited_once_with(
        task_id="task-1",
        background_tasks=background_tasks,
        request=request,
        current_user=current_user,
        process_submit_to_gallery_fn=gallery_router.process_submit_to_gallery,
    )
