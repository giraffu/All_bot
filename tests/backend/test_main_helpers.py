import asyncio
import os
import threading
import time
from functools import partial
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import main as backend_main
from app import main_response_helpers
from app import main_simple_task_routes
from app import main_status_result_routes
from app import main_t2i_helpers as t2i_helpers
from app.main_t2i_wiring import T2IWiring
from app.models import (
    FaceSwapRequest,
    PromptOptimizeRequest,
    Scail2ActionTransferLongRequest,
    Scail2FaceSwapRequest,
    Scail2VideoRequest,
    TaskType,
    VideoLoraRequest,
    Wan22VideoV2Request,
)


@pytest.fixture(autouse=True)
def _clear_system_snapshot_cache():
    main_response_helpers.clear_system_snapshot_cache()
    yield
    main_response_helpers.clear_system_snapshot_cache()


def test_validate_t2i_prompt_accepts_valid_prompt():
    prompt = t2i_helpers.validate_t2i_prompt("draw a dragon")

    assert prompt == "draw a dragon"


def test_validate_t2i_prompt_strips_surrounding_whitespace():
    prompt = t2i_helpers.validate_t2i_prompt("  draw a dragon  ")

    assert prompt == "draw a dragon"


@pytest.mark.parametrize("prompt", [None, "", "   ", 123, "x" * 2049])
def test_validate_t2i_prompt_rejects_invalid_values(prompt):
    with pytest.raises(HTTPException) as exc_info:
        t2i_helpers.validate_t2i_prompt(prompt)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "prompt is required and length must be 1-2048"


def test_validate_t2i_prompt_accepts_regression_prompt_shape():
    prompt = (
        "Ultra photorealistic RAW documentary 8K video, Sony A1 50mm f/1.4 "
        "cinematic footage, 20 seconds smooth continuous motion at 24fps, "
        "single unbroken shot with dynamic vertical tracking camera, warm "
        "bathroom lighting with heavy steam, wet tiled floor, maximum physical "
        "realism, stylize 0, raw film grain, (realism:1.9), (detail:1.95), "
        "(luminous glowing skin:1.9)"
    )

    assert t2i_helpers.validate_t2i_prompt(prompt) == prompt


def test_resolve_t2i_priority_prefers_body_value():
    assert t2i_helpers.resolve_t2i_priority({"priority": 9}, 3) == 9
    assert t2i_helpers.resolve_t2i_priority({}, 3) == 3


def test_prepare_t2i_request_payload_validates_prompt_and_builds_params(monkeypatch):
    monkeypatch.setattr(backend_main.uuid, "uuid4", lambda: "task-123")

    task_id, task_priority, params = t2i_helpers.prepare_t2i_request_payload(
        {"prompt": "draw a dragon", "priority": 9},
        default_priority=3,
        uuid_factory=backend_main.uuid.uuid4,
        validate_prompt_func=t2i_helpers.validate_t2i_prompt,
        resolve_priority_func=t2i_helpers.resolve_t2i_priority,
    )

    assert task_id == "task-123"
    assert task_priority == 9
    assert params == {"prompt": "draw a dragon"}


def test_build_t2i_terminal_response_returns_done_payload():
    def build_result_url(result_path):
        return main_response_helpers.build_result_url(
            result_path=result_path,
            settings=backend_main.settings,
        )

    response = t2i_helpers.build_t2i_terminal_response(
        task_id="task-1",
        status="done",
        result_path="foo/bar.png",
        error_msg=None,
        request_id="req-1",
        response_cls=backend_main.T2ITaskResponse,
        build_result_url_func=build_result_url,
        logger=backend_main.logger,
    )

    assert response.task_id == "task-1"
    assert response.image_url == build_result_url("foo/bar.png")


def test_build_t2i_terminal_response_raises_for_error_status():
    def build_result_url(result_path):
        return main_response_helpers.build_result_url(
            result_path=result_path,
            settings=backend_main.settings,
        )

    with pytest.raises(HTTPException) as exc_info:
        t2i_helpers.build_t2i_terminal_response(
            task_id="task-2",
            status="error",
            result_path=None,
            error_msg="worker failed",
            request_id="req-2",
            response_cls=backend_main.T2ITaskResponse,
            build_result_url_func=build_result_url,
            logger=backend_main.logger,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Task failed: worker failed"


def test_decode_t2i_pubsub_message_ignores_invalid_json():
    assert t2i_helpers.decode_t2i_pubsub_message(b'{"status":"done"}') == {
        "status": "done"
    }
    assert t2i_helpers.decode_t2i_pubsub_message("not-json") is None


@pytest.mark.asyncio
async def test_get_immediate_t2i_terminal_response_returns_done_payload():
    def build_result_url(result_path):
        return main_response_helpers.build_result_url(
            result_path=result_path,
            settings=backend_main.settings,
        )

    build_terminal_response = partial(
        t2i_helpers.build_t2i_terminal_response,
        response_cls=backend_main.T2ITaskResponse,
        build_result_url_func=build_result_url,
        logger=backend_main.logger,
    )

    class FakeQueueManager:
        async def get_task_status(self, task_id):
            assert task_id == "task-1"
            return {"status": "done", "result_path": "foo/bar.png", "error_msg": None}

    response = await t2i_helpers.get_immediate_t2i_terminal_response(
        queue_manager=FakeQueueManager(),
        task_id="task-1",
        request_id="req-1",
        build_terminal_response_func=build_terminal_response,
    )

    assert response is not None
    assert response.task_id == "task-1"
    assert response.image_url == build_result_url("foo/bar.png")


@pytest.mark.asyncio
async def test_enqueue_t2i_task_wraps_unexpected_errors():
    class FakeQueueManager:
        async def enqueue_task(self, _task_type, _params, _priority, _task_id):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc_info:
        await t2i_helpers.enqueue_t2i_task(
            queue_manager=FakeQueueManager(),
            task_type=TaskType.T2I_PORNMASTER_TURBO,
            task_id="task-1",
            params={"prompt": "dragon"},
            priority=3,
            request_id="req-1",
            logger=backend_main.logger,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"


@pytest.mark.asyncio
async def test_optional_t2i_task_subscription_subscribes_and_closes():
    events = []

    async def fake_subscribe_task_events(queue_manager, task_id):
        events.append(("subscribe", queue_manager, task_id))
        return "pubsub-1", "channel-1"

    async def fake_close_task_event_subscription(*, pubsub, channel):
        events.append(("close", pubsub, channel))

    async with t2i_helpers.optional_t2i_task_subscription(
        async_mode=False,
        queue_manager="qm",
        task_id="task-1",
        subscribe_task_events_func=fake_subscribe_task_events,
        close_task_event_subscription_func=fake_close_task_event_subscription,
    ) as (pubsub, channel):
        assert (pubsub, channel) == ("pubsub-1", "channel-1")
        events.append(("body", pubsub, channel))

    assert events == [
        ("subscribe", "qm", "task-1"),
        ("body", "pubsub-1", "channel-1"),
        ("close", "pubsub-1", "channel-1"),
    ]


@pytest.mark.asyncio
async def test_submit_t2i_task_request_returns_async_response_without_wait():
    enqueue_task = AsyncMock()
    wait_for_sync_result = AsyncMock()
    events = []

    class _AsyncSubscription:
        async def __aenter__(self):
            events.append("enter")
            return (None, None)

        async def __aexit__(self, exc_type, exc, tb):
            events.append("exit")
            return False

    response = await t2i_helpers.submit_t2i_task_request(
        async_mode=True,
        queue_manager="qm",
        task_id="task-1",
        params={"prompt": "dragon"},
        task_priority=3,
        request_id="req-1",
        response_cls=backend_main.T2ITaskResponse,
        optional_subscription_func=lambda **kwargs: _AsyncSubscription(),
        enqueue_t2i_task_func=enqueue_task,
        wait_for_sync_result_func=wait_for_sync_result,
        logger=backend_main.logger,
    )

    assert response.task_id == "task-1"
    assert events == ["enter", "exit"]
    enqueue_task.assert_awaited_once()
    wait_for_sync_result.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_t2i_task_request_waits_for_sync_result():
    enqueue_task = AsyncMock()
    wait_for_sync_result = AsyncMock(
        return_value=backend_main.T2ITaskResponse(
            task_id="task-1",
            image_url="https://example.com/a.png",
        )
    )

    class _SyncSubscription:
        async def __aenter__(self):
            return ("pubsub-1", "channel-1")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    response = await t2i_helpers.submit_t2i_task_request(
        async_mode=False,
        queue_manager="qm",
        task_id="task-1",
        params={"prompt": "dragon"},
        task_priority=3,
        request_id="req-1",
        response_cls=backend_main.T2ITaskResponse,
        optional_subscription_func=lambda **kwargs: _SyncSubscription(),
        enqueue_t2i_task_func=enqueue_task,
        wait_for_sync_result_func=wait_for_sync_result,
        logger=backend_main.logger,
    )

    assert response.task_id == "task-1"
    assert response.image_url == "https://example.com/a.png"
    enqueue_task.assert_awaited_once_with(
        queue_manager="qm",
        task_id="task-1",
        params={"prompt": "dragon"},
        priority=3,
        request_id="req-1",
    )
    wait_for_sync_result.assert_awaited_once_with(
        pubsub="pubsub-1",
        task_id="task-1",
        request_id="req-1",
        queue_manager="qm",
    )


@pytest.mark.asyncio
async def test_create_t2i_pornmaster_turbo_task_reraises_prompt_http_error(monkeypatch):
    invalid_prompt_error = HTTPException(status_code=400, detail="bad prompt")
    queue_manager = object()

    monkeypatch.setattr(
        backend_main,
        "_t2i_wiring",
        T2IWiring(
            prepare_task_request_func=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                invalid_prompt_error
            ),
            submit_task_request_func=backend_main._t2i_wiring.submit_task_request_func,
            build_task_status_response_func=(
                backend_main._t2i_wiring.build_task_status_response_func
            ),
            serve_task_result_file_func=(
                backend_main._t2i_wiring.serve_task_result_file_func
            ),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await backend_main.create_t2i_pornmaster_turbo_task(
            request={"prompt": ""},
            queue_manager=queue_manager,
            _token="token",
        )

    assert exc_info.value is invalid_prompt_error


def test_simple_task_type_map_keeps_image_to_video_and_video_lora_compatibility():
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["video_insert"]
        == TaskType.IMAGE_TO_VIDEO
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["video_edit"]
        == TaskType.IMAGE_TO_VIDEO
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["image_to_video"]
        == TaskType.IMAGE_TO_VIDEO
    )
    assert main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["video_lora"] == TaskType.IMAGE_TO_VIDEO
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["wan22_video_v2"]
        == TaskType.WAN22_VIDEO_V2
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["scail2_action_transfer"]
        == TaskType.SCAIL2_ACTION_TRANSFER
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["scail2_action_transfer_long"]
        == TaskType.SCAIL2_ACTION_TRANSFER_LONG
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["scail2_video_replacement"]
        == TaskType.SCAIL2_VIDEO_REPLACEMENT
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["scail2_face_swap_v2"]
        == TaskType.SCAIL2_FACE_SWAP_V2
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["pornmaster_flux2_single_edit"]
        == TaskType.PORNMASTER_FLUX2_SINGLE_EDIT
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["pornmaster_flux2_multi_edit"]
        == TaskType.PORNMASTER_FLUX2_MULTI_EDIT
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["pornmaster_flux2_edit_bf16"]
        == TaskType.PORNMASTER_FLUX2_EDIT_BF16
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP[
            "pornmaster_flux2_multi_edit_bf16"
        ]
        == TaskType.PORNMASTER_FLUX2_MULTI_EDIT_BF16
    )
    assert main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["img2img"] == TaskType.IMG2IMG
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["face_swap_v2"]
        == TaskType.FACE_SWAP_V2
    )
    assert (
        main_simple_task_routes.SIMPLE_TASK_TYPE_MAP["txt2img"]
        == TaskType.T2I_PORNMASTER_TURBO
    )


def test_simple_task_route_specs_cover_expected_paths_and_handlers():
    specs_by_path = {
        path: (request_model_cls, task_key, handler_name)
        for path, request_model_cls, task_key, handler_name in main_simple_task_routes.SIMPLE_TASK_ROUTE_SPECS
    }

    assert specs_by_path["/comfy_img2img"][1:] == ("img2img", "create_img2img_task")
    assert specs_by_path["/perfect_video_insert"][1:] == (
        "video_insert",
        "create_video_insert_task",
    )
    assert specs_by_path["/perfect_video_edit"][1:] == (
        "video_edit",
        "create_video_edit_task",
    )
    assert specs_by_path["/image_to_video"][1:] == (
        "image_to_video",
        "create_image_to_video_task",
    )
    assert specs_by_path["/perfect_video_lora"][1:] == (
        "video_lora",
        "create_video_lora_task",
    )
    assert specs_by_path["/txt2img"][1:] == (
        "txt2img",
        "create_txt2img_task",
    )
    assert specs_by_path["/api/v1/ltx_video"][1:] == (
        "ltx_video",
        "create_ltx_video_task",
    )
    assert specs_by_path["/api/v1/wan22_video_v2"][1:] == (
        "wan22_video_v2",
        "create_wan22_video_v2_task",
    )
    assert specs_by_path["/api/v1/scail2_action_transfer"][1:] == (
        "scail2_action_transfer",
        "create_scail2_action_transfer_task",
    )
    assert specs_by_path["/api/v1/scail2_action_transfer_long"][1:] == (
        "scail2_action_transfer_long",
        "create_scail2_action_transfer_long_task",
    )
    assert specs_by_path["/api/v1/scail2_video_replacement"][1:] == (
        "scail2_video_replacement",
        "create_scail2_video_replacement_task",
    )
    assert specs_by_path["/api/v1/scail2_face_swap_v2"][1:] == (
        "scail2_face_swap_v2",
        "create_scail2_face_swap_v2_task",
    )
    assert specs_by_path["/api/v1/pornmaster_flux2_single_edit"][1:] == (
        "pornmaster_flux2_single_edit",
        "create_pornmaster_flux2_single_edit_task",
    )
    assert specs_by_path["/api/v1/pornmaster_flux2_multi_edit"][1:] == (
        "pornmaster_flux2_multi_edit",
        "create_pornmaster_flux2_multi_edit_task",
    )
    assert specs_by_path["/api/v1/pornmaster_flux2_edit_bf16"][1:] == (
        "pornmaster_flux2_edit_bf16",
        "create_pornmaster_flux2_edit_bf16_task",
    )
    assert specs_by_path["/api/v1/pornmaster_flux2_multi_edit_bf16"][1:] == (
        "pornmaster_flux2_multi_edit_bf16",
        "create_pornmaster_flux2_multi_edit_bf16_task",
    )


@pytest.mark.parametrize("request_type", [VideoLoraRequest, Wan22VideoV2Request])
def test_wan22_request_models_accept_at_most_five_lora_items(request_type):
    common = {"task_id": "task-1", "image": "input.png", "prompt": "move"}
    five = [
        {"name": f"model-{index}", "strength": 0.5 + index * 0.1}
        for index in range(5)
    ]

    assert len(request_type(**common, lora_items=five).lora_items or []) == 5
    with pytest.raises(ValidationError):
        request_type(
            **common,
            lora_items=five + [{"name": "model-6", "strength": 1.0}],
        )


def test_simple_task_routes_are_registered_with_stable_endpoint_names():
    routes_by_path = {
        route.path: route.endpoint.__name__
        for route in backend_main.app.routes
        if route.path in {path for path, *_rest in main_simple_task_routes.SIMPLE_TASK_ROUTE_SPECS}
    }

    assert routes_by_path["/comfy_img2img"] == "create_img2img_task"
    assert routes_by_path["/perfect_video_insert"] == "create_video_insert_task"
    assert routes_by_path["/perfect_video_edit"] == "create_video_edit_task"
    assert routes_by_path["/image_to_video"] == "create_image_to_video_task"
    assert routes_by_path["/perfect_video_lora"] == "create_video_lora_task"
    assert routes_by_path["/txt2img"] == "create_txt2img_task"
    assert routes_by_path["/api/v1/ltx_video"] == "create_ltx_video_task"
    assert routes_by_path["/api/v1/wan22_video_v2"] == "create_wan22_video_v2_task"
    assert (
        routes_by_path["/api/v1/scail2_action_transfer"]
        == "create_scail2_action_transfer_task"
    )
    assert (
        routes_by_path["/api/v1/scail2_action_transfer_long"]
        == "create_scail2_action_transfer_long_task"
    )
    assert (
        routes_by_path["/api/v1/scail2_video_replacement"]
        == "create_scail2_video_replacement_task"
    )
    assert (
        routes_by_path["/api/v1/scail2_face_swap_v2"]
        == "create_scail2_face_swap_v2_task"
    )
    assert (
        routes_by_path["/api/v1/pornmaster_flux2_single_edit"]
        == "create_pornmaster_flux2_single_edit_task"
    )
    assert (
        routes_by_path["/api/v1/pornmaster_flux2_multi_edit"]
        == "create_pornmaster_flux2_multi_edit_task"
    )
    assert (
        routes_by_path["/api/v1/pornmaster_flux2_multi_edit_bf16"]
        == "create_pornmaster_flux2_multi_edit_bf16_task"
    )


def test_scail2_video_request_accepts_only_supported_lengths():
    request = Scail2VideoRequest(
        task_id="task-1",
        image="ref.png",
        video="motion.mp4",
        prompt="dance",
        length=8,
    )

    assert request.length == 8

    with pytest.raises(ValidationError):
        Scail2VideoRequest(
            task_id="task-1",
            image="ref.png",
            video="motion.mp4",
            prompt="dance",
            length=10,
        )


def test_scail2_action_transfer_long_request_accepts_only_long_lengths():
    for length in (10, 15, 20):
        request = Scail2ActionTransferLongRequest(
            task_id=f"task-{length}",
            image="ref.png",
            video="motion.mp4",
            prompt="dance",
            length=length,
        )
        assert request.length == length

    for length in (5, 8, 25):
        with pytest.raises(ValidationError):
            Scail2ActionTransferLongRequest(
                task_id=f"task-{length}",
                image="ref.png",
                video="motion.mp4",
                prompt="dance",
                length=length,
            )


def test_task_status_and_result_route_specs_cover_expected_handlers():
    status_specs = {
        path: (include_image_url, include_task_type, handler_name)
        for path, include_image_url, include_task_type, handler_name in main_status_result_routes.TASK_STATUS_ROUTE_SPECS
    }
    result_specs = {
        path: (ready_error_detail, handler_name)
        for path, ready_error_detail, handler_name in main_status_result_routes.TASK_RESULT_ROUTE_SPECS
    }

    assert status_specs["/api/v1/tasks/{task_id}"] == (True, False, "get_task_status_v1")
    assert status_specs["/status/{task_id}"] == (False, True, "get_task_status")
    assert result_specs["/image/{task_id}"] == ("Image not ready", "get_task_image")
    assert result_specs["/video/{task_id}"] == ("Video not ready", "get_task_video")


def test_task_status_and_result_routes_keep_stable_endpoint_names():
    expected_paths = {
        *(path for path, *_rest in main_status_result_routes.TASK_STATUS_ROUTE_SPECS),
        *(path for path, *_rest in main_status_result_routes.TASK_RESULT_ROUTE_SPECS),
    }
    routes_by_path = {
        route.path: route.endpoint.__name__
        for route in backend_main.app.routes
        if route.path in expected_paths
    }

    assert routes_by_path["/api/v1/tasks/{task_id}"] == "get_task_status_v1"
    assert routes_by_path["/status/{task_id}"] == "get_task_status"
    assert routes_by_path["/image/{task_id}"] == "get_task_image"
    assert routes_by_path["/video/{task_id}"] == "get_task_video"


@pytest.mark.asyncio
async def test_enqueue_configured_task_uses_registered_task_type(monkeypatch):
    called = {}

    async def fake_enqueue_task_from_request(*, request_model, task_type, queue_manager):
        called["request_model"] = request_model
        called["task_type"] = task_type
        called["queue_manager"] = queue_manager
        return "queued"

    monkeypatch.setattr(
        main_simple_task_routes,
        "enqueue_task_from_request",
        fake_enqueue_task_from_request,
    )

    response = await main_simple_task_routes.enqueue_configured_task(
        request_model={"task_id": "x"},
        task_key="face_swap",
        queue_manager="qm",
    )

    assert response == "queued"
    assert called == {
        "request_model": {"task_id": "x"},
        "task_type": TaskType.FACE_SWAP,
        "queue_manager": "qm",
    }


def test_prompt_optimizer_request_preserves_stream_and_snapshot_contracts():
    request = PromptOptimizeRequest(
        task_id="prompt-task",
        profile_ref="ltx_eros_t2v_ic_msr@1",
        template_ref="ltx_scene_script_cinematic@4",
        template_hash="a" * 64,
        target_task_type="ltx_t2v_ic",
        prompt="A cinematic scene",
        context={"duration_seconds": 5},
        media=[{"role": "reference_character_1", "object_key": "panel.png"}],
        trusted_context={"character_descriptions": ["adult character"]},
        prompt_config_snapshot={"scene_key": "ltx_t2v_ic", "revision": 1},
        text_stream_contract={
            "schema_version": "allbot.text_stream.v1",
            "fields": ["positive_prompt"],
            "max_chars": 2000,
        },
    )

    _task_id, _priority, params = main_simple_task_routes.split_task_request(request)

    assert params["trusted_context"] == {
        "character_descriptions": ["adult character"]
    }
    assert params["prompt_config_snapshot"]["scene_key"] == "ltx_t2v_ic"
    assert params["text_stream_contract"] == {
        "schema_version": "allbot.text_stream.v1",
        "fields": ["positive_prompt"],
        "max_chars": 2000,
    }


def test_face_swap_v2_reuses_face_swap_request_contract():
    specs_by_path = {
        path: (request_model, task_key, endpoint_name)
        for path, request_model, task_key, endpoint_name in (
            main_simple_task_routes.SIMPLE_TASK_ROUTE_SPECS
        )
    }

    assert specs_by_path["/face_swap_v2"] == (
        FaceSwapRequest,
        "face_swap_v2",
        "create_face_swap_v2_task",
    )


def test_scail2_face_swap_route_requires_preprocessed_reference():
    specs_by_path = {
        path: request_model
        for path, request_model, _task_key, _endpoint_name in (
            main_simple_task_routes.SIMPLE_TASK_ROUTE_SPECS
        )
    }
    assert specs_by_path["/api/v1/scail2_face_swap_v2"] is Scail2FaceSwapRequest

    with pytest.raises(ValidationError):
        Scail2FaceSwapRequest(
            task_id="task-1",
            image="swapped-first-frame.png",
            video="motion.mp4",
            prompt="keep scene",
            reference_preprocessed=False,
        )

    request = Scail2FaceSwapRequest(
        task_id="task-1",
        image="swapped-first-frame.png",
        video="motion.mp4",
        prompt="keep scene",
        reference_preprocessed=True,
    )
    assert request.reference_preprocessed is True


@pytest.mark.asyncio
async def test_enqueue_configured_task_allows_hidden_scail2_long_route(monkeypatch):
    enqueue_mock = AsyncMock(return_value="queued")
    request_model = Scail2ActionTransferLongRequest(
        task_id="task-1",
        image="ref.png",
        video="motion.mp4",
        prompt="dance",
        length=10,
    )

    response = await main_simple_task_routes.enqueue_configured_task(
        request_model=request_model,
        task_key="scail2_action_transfer_long",
        queue_manager="qm",
        enqueue_task_from_request_func=enqueue_mock,
    )

    assert response == "queued"
    enqueue_mock.assert_awaited_once_with(
        request_model=request_model,
        task_type=TaskType.SCAIL2_ACTION_TRANSFER_LONG,
        queue_manager="qm",
    )


def test_normalize_legacy_video_simple_request_uses_wan22_contract():
    request = main_simple_task_routes.VideoEditRequest(
        task_id="task-video",
        image="inputs/start.png",
        prompt="built in prompt",
        width=720,
        height=720,
        length=129,
        priority=4,
    )

    normalized = main_simple_task_routes.normalize_simple_task_request_model(
        "video_edit", request
    ).dict()

    assert normalized["task_id"] == "task-video"
    assert normalized["priority"] == 4
    assert normalized["image"] == "inputs/start.png"
    assert normalized["prompt"] == "built in prompt"
    assert normalized["resolution_preset"] == "standard"
    assert normalized["length"] == 8
    assert "width" not in normalized
    assert "height" not in normalized
    assert normalized["wan22_model_profile"] == "legacy_image_to_video"
    assert normalized["extract_last_frame"] is True


@pytest.mark.asyncio
async def test_build_system_workers_response_counts_workers():
    class FakeQueueManager:
        async def get_all_workers(self):
            return [
                {
                    "agent_id": "agent-1",
                    "types": "ltx_video",
                    "status": "running",
                    "last_seen": "123.0",
                },
                {
                    "agent_id": "agent-2",
                    "types": "i2i_pro",
                    "status": "idle",
                    "last_seen": "456.0",
                },
            ]

    response = await main_response_helpers.build_system_workers_response(
        FakeQueueManager()
    )

    assert response.count == 2
    assert response.workers[0].agent_id == "agent-1"
    assert response.workers[1].agent_id == "agent-2"


@pytest.mark.asyncio
async def test_build_system_worker_outcomes_response_reports_window():
    class FakeQueueManager:
        async def get_active_worker_outcome_stats(self, *, window_seconds, now):
            assert window_seconds == 3600
            assert isinstance(now, float)
            return [
                {
                    "worker_id": "agent-1",
                    "status": "running",
                    "total_tasks": 10,
                    "failed_tasks": 7,
                    "failure_rate": 0.7,
                    "failures_by_type": {"minimax_h3_i2v": 7},
                    "last_failure_at": 123.0,
                }
            ]

    response = await main_response_helpers.build_system_worker_outcomes_response(
        FakeQueueManager(),
        window_seconds=3600,
    )

    assert response.window_seconds == 3600
    assert response.workers[0].worker_id == "agent-1"
    assert response.workers[0].failed_tasks == 7


@pytest.mark.asyncio
async def test_build_system_status_response_uses_queue_metrics_and_worker_count():
    class FakeQueueManager:
        async def get_queue_size(self):
            return 3

        async def get_all_workers(self):
            return [
                {"agent_id": "agent-1", "status": "running"},
                {"agent_id": "agent-2", "status": "idle"},
                {"agent_id": "agent-3", "status": "error"},
                {"agent_id": "agent-4", "status": "quarantined"},
            ]

        async def get_queue_metrics_by_type(self):
            return {"ltx_video": 2, "i2i_pro": 1}

        async def get_queue_metrics_by_type_details(self):
            return {
                "ltx_video": {
                    "pending_count": 2,
                    "max_pending_wait_seconds": 120,
                },
                "i2i_pro": {
                    "pending_count": 1,
                    "max_pending_wait_seconds": 30,
                },
            }

    response = await main_response_helpers.build_system_status_response(
        FakeQueueManager()
    )

    assert response.queue_size == 3
    assert response.active_workers == 4
    assert response.healthy_workers == 2
    assert response.accepting_workers == 2
    assert response.error_workers == 1
    assert response.quarantined_workers == 1
    assert response.workers_by_status == {
        "running": 1,
        "idle": 1,
        "error": 1,
        "quarantined": 1,
    }
    assert response.workers_by_control_state == {"enabled": 4}
    assert response.comfy_online is True
    assert response.queue_by_type == {"ltx_video": 2, "i2i_pro": 1}
    assert response.queue_by_type_details == {
        "ltx_video": {
            "pending_count": 2,
            "max_pending_wait_seconds": 120,
        },
        "i2i_pro": {
            "pending_count": 1,
            "max_pending_wait_seconds": 30,
        },
    }


@pytest.mark.asyncio
async def test_build_system_status_response_counts_accepting_workers_by_control_state():
    class FakeQueueManager:
        async def get_queue_size(self):
            return 3

        async def get_all_workers(self):
            return [
                {"agent_id": "agent-1", "status": "running"},
                {"agent_id": "agent-2", "status": "idle"},
                {"agent_id": "agent-3", "status": "idle"},
                {"agent_id": "agent-4", "status": "error"},
            ]

        async def get_agent_control_state(self, agent_id):
            return {
                "agent-1": {"state": "enabled", "reason": ""},
                "agent-2": {"state": "disabled", "reason": "maintenance"},
                "agent-3": {"state": "draining", "reason": "canary"},
                "agent-4": {"state": "enabled", "reason": ""},
            }[agent_id]

        async def get_queue_metrics_by_type(self):
            return {"scail2_action_transfer": 1}

    response = await main_response_helpers.build_system_status_response(
        FakeQueueManager()
    )

    assert response.healthy_workers == 3
    assert response.accepting_workers == 1
    assert response.workers_by_control_state == {
        "enabled": 2,
        "disabled": 1,
        "draining": 1,
    }
    assert response.comfy_online is True


@pytest.mark.asyncio
async def test_build_system_status_response_groups_queue_pressure_by_worker_profile():
    class FakeQueueManager:
        async def get_queue_size(self):
            return 68

        async def get_all_workers(self):
            return [
                {
                    "agent_id": "runpod_prod_i2i_pro_manual_01",
                    "provider": "runpod",
                    "types": "i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap",
                    "status": "idle",
                    "control_state": "enabled",
                },
                {
                    "agent_id": "local-i2i",
                    "types": "i2i_pro,t2i-pornmaster-turbo,face_swap_v2,face_swap",
                    "status": "running",
                    "control_state": "enabled",
                },
                {
                    "agent_id": "local-i2i-paused",
                    "types": "i2i_pro",
                    "status": "idle",
                    "control_state": "disabled",
                },
                {
                    "agent_id": "local-i2i-error",
                    "types": "face_swap_v2",
                    "status": "error",
                    "control_state": "enabled",
                },
                {
                    "agent_id": "local-scail2",
                    "types": "scail2_action_transfer_long,scail2_face_swap_v2",
                    "status": "idle",
                    "control_state": "enabled",
                },
            ]

        async def get_queue_metrics_by_type(self):
            return {
                "i2i_pro": 40,
                "txt2img": 20,
                "face_swap_v2": 4,
                "face_swap": 2,
                "scail2_action_transfer_long": 3,
                "video_insert": 1,
            }

    response = await main_response_helpers.build_system_status_response(
        FakeQueueManager()
    )

    assert response.queue_pressure_by_worker_profile["i2i_pro"] == {
        "supported_task_types": [
            "i2i_pro",
            "t2i-pornmaster-turbo",
            "face_swap_v2",
            "face_swap",
        ],
        "pending_count": 66,
        "accepting_worker_count": 2,
        "accepting_runpod_worker_count": 1,
        "accepting_local_worker_count": 1,
    }
    assert response.queue_pressure_by_worker_profile["scail2"]["pending_count"] == 3
    assert (
        response.queue_pressure_by_worker_profile["scail2"][
            "accepting_worker_count"
        ]
        == 1
    )
    assert (
        response.queue_pressure_by_worker_profile["image_to_video"]["pending_count"]
        == 1
    )
    assert (
        response.queue_pressure_by_worker_profile["wan22_video_v2"][
            "accepting_worker_count"
        ]
        == 0
    )


@pytest.mark.asyncio
async def test_build_system_workers_response_includes_control_state():
    class FakeQueueManager:
        async def get_all_workers(self):
            return [
                {
                    "agent_id": "agent-1",
                    "types": "scail2_action_transfer",
                    "status": "idle",
                    "last_seen": "123.0",
                }
            ]

        async def get_agent_control_state(self, agent_id):
            assert agent_id == "agent-1"
            return {
                "state": "disabled",
                "reason": "scail2_test_initial_disabled",
                "updated_at": "1782047600.0",
            }

    response = await main_response_helpers.build_system_workers_response(
        FakeQueueManager()
    )

    assert response.workers[0].control_state == "disabled"
    assert response.workers[0].control_reason == "scail2_test_initial_disabled"
    assert response.workers[0].control_updated_at == 1782047600.0


@pytest.mark.asyncio
async def test_build_system_status_response_marks_offline_when_all_workers_unhealthy():
    class FakeQueueManager:
        async def get_queue_size(self):
            return 0

        async def get_all_workers(self):
            return [
                {"agent_id": "agent-1", "status": "error"},
                {"agent_id": "agent-2", "status": "quarantined"},
            ]

        async def get_queue_metrics_by_type(self):
            return {}

    response = await main_response_helpers.build_system_status_response(
        FakeQueueManager()
    )

    assert response.active_workers == 2
    assert response.healthy_workers == 0
    assert response.accepting_workers == 0
    assert response.error_workers == 1
    assert response.quarantined_workers == 1
    assert response.comfy_online is False


@pytest.mark.asyncio
async def test_build_task_status_response_uses_short_task_snapshot_cache(monkeypatch):
    class FakeQueueManager:
        def __init__(self):
            self.redis = object()
            self.pending_key = "pending"
            self.running_key = "running"
            self.agent_heartbeat_prefix = "agent:"
            self.status_calls = 0
            self.position_calls = 0
            self.type_position_calls = 0

        async def get_task_status(self, task_id):
            assert task_id == "task-1"
            self.status_calls += 1
            return {
                "status": "pending",
                "type": "img2img",
                "progress": "0.25",
                "error_msg": "",
                "result_path": "",
                "extra_outputs": "",
            }

        async def get_queue_position(self, task_id):
            assert task_id == "task-1"
            self.position_calls += 1
            return 4

        async def get_queue_position_by_type(self, task_id):
            assert task_id == "task-1"
            self.type_position_calls += 1
            return 1

        @staticmethod
        def _maybe_parse_json_dict(value):
            return None if not value else value

        @staticmethod
        def _as_bool(value):
            return bool(value)

    monkeypatch.setattr(main_response_helpers, "TASK_STATUS_CACHE_TTL_SECONDS", 2.0)
    queue_manager = FakeQueueManager()

    first = await main_response_helpers.build_task_status_response(
        task_id="task-1",
        queue_manager=queue_manager,
        include_type_position=True,
        build_result_url_func=lambda _path: "unused",
    )
    second = await main_response_helpers.build_task_status_response(
        task_id="task-1",
        queue_manager=queue_manager,
        include_type_position=True,
        build_result_url_func=lambda _path: "unused",
    )

    assert first.queue_pos == 4
    assert first.queue_type_pos == 1
    assert second.queue_pos == 4
    assert second.queue_type_pos == 1
    assert queue_manager.status_calls == 1
    assert queue_manager.position_calls == 1
    assert queue_manager.type_position_calls == 1


@pytest.mark.asyncio
async def test_build_task_status_response_skips_type_position_by_default():
    class FakeQueueManager:
        redis = object()
        pending_key = "pending"
        running_key = "running"
        agent_heartbeat_prefix = "agent:"

        async def get_task_status(self, task_id):
            assert task_id == "task-1"
            return {
                "status": "pending",
                "type": "img2img",
                "progress": "0.25",
                "error_msg": "",
                "result_path": "",
                "extra_outputs": "",
                "result_asset": {
                    "object_key": "task-results/task-1/primary.png",
                    "sha256": "a" * 64,
                },
            }

        async def get_queue_position(self, task_id):
            assert task_id == "task-1"
            return 4

        async def get_queue_position_by_type(self, _task_id):
            raise AssertionError("type position should be opt-in")

        @staticmethod
        def _maybe_parse_json_dict(value):
            return None if not value else value

        @staticmethod
        def _as_bool(value):
            return bool(value)

    result = await main_response_helpers.build_task_status_response(
        task_id="task-1",
        queue_manager=FakeQueueManager(),
        build_result_url_func=lambda _path: "unused",
    )

    assert result.queue_pos == 4
    assert result.queue_type_pos is None
    assert result.result_asset["object_key"] == "task-results/task-1/primary.png"


@pytest.mark.asyncio
async def test_build_task_status_response_prunes_old_task_snapshot_cache(monkeypatch):
    class FakeQueueManager:
        def __init__(self):
            self.redis = object()
            self.pending_key = "pending"
            self.running_key = "running"
            self.agent_heartbeat_prefix = "agent:"
            self.status_calls = []

        async def get_task_status(self, task_id):
            self.status_calls.append(task_id)
            return {
                "status": "done",
                "progress": "1.0",
                "error_msg": "",
                "result_path": "",
                "extra_outputs": "",
            }

        @staticmethod
        def _maybe_parse_json_dict(value):
            return None if not value else value

        @staticmethod
        def _as_bool(value):
            return bool(value)

    monkeypatch.setattr(main_response_helpers, "TASK_STATUS_CACHE_TTL_SECONDS", 30.0)
    monkeypatch.setattr(main_response_helpers, "TASK_STATUS_CACHE_STALE_SECONDS", 30.0)
    monkeypatch.setattr(main_response_helpers, "TASK_STATUS_CACHE_MAX_ENTRIES", 1)
    queue_manager = FakeQueueManager()

    await main_response_helpers.build_task_status_response(
        task_id="task-1",
        queue_manager=queue_manager,
        build_result_url_func=lambda _path: "unused",
    )
    await main_response_helpers.build_task_status_response(
        task_id="task-2",
        queue_manager=queue_manager,
        build_result_url_func=lambda _path: "unused",
    )
    await main_response_helpers.build_task_status_response(
        task_id="task-1",
        queue_manager=queue_manager,
        build_result_url_func=lambda _path: "unused",
    )

    assert len(main_response_helpers._task_status_snapshot_cache) == 1
    assert queue_manager.status_calls == ["task-1", "task-2", "task-1"]


@pytest.mark.asyncio
async def test_system_status_and_workers_share_short_worker_snapshot_cache():
    class FakeQueueManager:
        def __init__(self):
            self.worker_calls = 0
            self.queue_size_calls = 0
            self.queue_metrics_calls = 0

        async def get_queue_size(self):
            self.queue_size_calls += 1
            return 3

        async def get_all_workers(self):
            self.worker_calls += 1
            return [
                {
                    "agent_id": "agent-1",
                    "types": "ltx_video",
                    "status": "running",
                    "last_seen": "123.0",
                },
                {
                    "agent_id": "agent-2",
                    "types": "i2i_pro",
                    "status": "idle",
                    "last_seen": "456.0",
                },
            ]

        async def get_queue_metrics_by_type(self):
            self.queue_metrics_calls += 1
            return {"ltx_video": 2, "i2i_pro": 1}

    queue_manager = FakeQueueManager()

    status_response = await main_response_helpers.build_system_status_response(
        queue_manager
    )
    workers_response = await main_response_helpers.build_system_workers_response(
        queue_manager
    )
    cached_status_response = await main_response_helpers.build_system_status_response(
        queue_manager
    )

    assert status_response.active_workers == 2
    assert workers_response.count == 2
    assert cached_status_response.queue_size == 3
    assert queue_manager.worker_calls == 1
    assert queue_manager.queue_size_calls == 1
    assert queue_manager.queue_metrics_calls == 1


@pytest.mark.asyncio
async def test_system_status_cache_key_follows_shared_redis_client():
    class FakeRedis:
        def __init__(self):
            self.connection_pool = type(
                "ConnectionPool",
                (),
                {"connection_kwargs": {"host": "redis", "port": 6379, "db": 0}},
            )()

    class FakeQueueManager:
        def __init__(self, redis):
            self.redis = redis
            self.pending_key = "comfy:queue:pending"
            self.running_key = "comfy:queue:running"
            self.agent_heartbeat_prefix = "comfy:agent:heartbeat:"
            self.queue_size_calls = 0
            self.worker_calls = 0
            self.queue_metrics_calls = 0

        async def get_queue_size(self):
            self.queue_size_calls += 1
            return 7

        async def get_all_workers(self):
            self.worker_calls += 1
            return [{"agent_id": "agent-1", "status": "idle"}]

        async def get_queue_metrics_by_type(self):
            self.queue_metrics_calls += 1
            return {"img2img": 7}

    first_manager = FakeQueueManager(FakeRedis())
    second_manager = FakeQueueManager(FakeRedis())

    first_response = await main_response_helpers.build_system_status_response(
        first_manager
    )
    second_response = await main_response_helpers.build_system_status_response(
        second_manager
    )

    assert first_response.queue_size == 7
    assert second_response.queue_size == 7
    assert first_manager.queue_size_calls == 1
    assert first_manager.worker_calls == 1
    assert first_manager.queue_metrics_calls == 1
    assert second_manager.queue_size_calls == 0
    assert second_manager.worker_calls == 0
    assert second_manager.queue_metrics_calls == 0


@pytest.mark.asyncio
async def test_cached_snapshot_returns_stale_while_refreshing():
    cache = {}
    locks = {}
    now = 100.0
    calls = 0

    async def collect_snapshot():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return f"snapshot-{calls}"

    def now_func():
        return now

    first = await main_response_helpers._get_cached_snapshot(
        cache=cache,
        locks=locks,
        cache_key=1,
        collect_func=collect_snapshot,
        ttl_seconds=1.0,
        stale_seconds=120.0,
        now_func=now_func,
    )
    assert first == "snapshot-1"

    now = 102.0
    second = await main_response_helpers._get_cached_snapshot(
        cache=cache,
        locks=locks,
        cache_key=1,
        collect_func=collect_snapshot,
        ttl_seconds=1.0,
        stale_seconds=120.0,
        now_func=now_func,
    )
    assert second == "snapshot-1"

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    third = await main_response_helpers._get_cached_snapshot(
        cache=cache,
        locks=locks,
        cache_key=1,
        collect_func=collect_snapshot,
        ttl_seconds=1.0,
        stale_seconds=120.0,
        now_func=now_func,
    )
    assert third == "snapshot-2"
    assert calls == 2


@pytest.mark.asyncio
async def test_cancel_task_or_404_returns_cancel_result():
    class FakeQueueManager:
        async def cancel_task(self, task_id):
            assert task_id == "task-1"
            return {"state": "cancelled", "task_id": task_id}

    result = await main_response_helpers.cancel_task_or_404(
        FakeQueueManager(),
        "task-1",
    )

    assert result == {"state": "cancelled", "task_id": "task-1"}


@pytest.mark.asyncio
async def test_cancel_task_or_404_raises_not_found():
    class FakeQueueManager:
        async def cancel_task(self, task_id):
            assert task_id == "missing-task"
            return None

    with pytest.raises(HTTPException) as exc_info:
        await main_response_helpers.cancel_task_or_404(
            FakeQueueManager(),
            "missing-task",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Task not found"


@pytest.mark.asyncio
async def test_serving_result_file_does_not_block_worker_heartbeats():
    heartbeat_completed = threading.Event()
    download_observations = []

    class FakeQueueManager:
        async def get_task_status(self, task_id):
            assert task_id == "task-1"
            return {"status": "done", "result_path": "result.png"}

    class SlowMinioClient:
        def fget_object(self, bucket_name, object_name, file_path):
            assert bucket_name == "results"
            assert object_name == "result.png"
            time.sleep(0.05)
            download_observations.append(heartbeat_completed.is_set())
            Path(file_path).write_bytes(b"image")

    class Settings:
        minio_result_bucket = "results"

    async def publish_heartbeat():
        await asyncio.sleep(0.01)
        heartbeat_completed.set()

    response, _ = await asyncio.gather(
        main_response_helpers.serve_task_result_file(
            task_id="task-1",
            ready_error_detail="not ready",
            queue_manager=FakeQueueManager(),
            minio_client=SlowMinioClient(),
            settings=Settings(),
            logger=main_response_helpers.logger,
        ),
        publish_heartbeat(),
    )

    try:
        assert download_observations == [True]
    finally:
        os.remove(response.path)
