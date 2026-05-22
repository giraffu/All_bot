from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import main as backend_main
from app.models import TaskType


def test_validate_t2i_prompt_accepts_valid_prompt():
    prompt = backend_main._validate_t2i_prompt("draw a dragon")

    assert prompt == "draw a dragon"


@pytest.mark.parametrize("prompt", [None, "", 123, "x" * 513])
def test_validate_t2i_prompt_rejects_invalid_values(prompt):
    with pytest.raises(HTTPException) as exc_info:
        backend_main._validate_t2i_prompt(prompt)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "prompt is required and length must be 1-512"


def test_resolve_t2i_priority_prefers_body_value():
    assert backend_main._resolve_t2i_priority({"priority": 9}, 3) == 9
    assert backend_main._resolve_t2i_priority({}, 3) == 3


def test_prepare_t2i_request_payload_validates_prompt_and_builds_params(monkeypatch):
    monkeypatch.setattr(backend_main.uuid, "uuid4", lambda: "task-123")

    task_id, task_priority, params = backend_main._prepare_t2i_request_payload(
        {"prompt": "draw a dragon", "priority": 9},
        default_priority=3,
    )

    assert task_id == "task-123"
    assert task_priority == 9
    assert params == {"prompt": "draw a dragon"}


def test_build_t2i_terminal_response_returns_done_payload():
    response = backend_main._build_t2i_terminal_response(
        task_id="task-1",
        status="done",
        result_path="foo/bar.png",
        error_msg=None,
        request_id="req-1",
    )

    assert response.task_id == "task-1"
    assert response.image_url == backend_main._build_result_url("foo/bar.png")


def test_build_t2i_terminal_response_raises_for_error_status():
    with pytest.raises(HTTPException) as exc_info:
        backend_main._build_t2i_terminal_response(
            task_id="task-2",
            status="error",
            result_path=None,
            error_msg="worker failed",
            request_id="req-2",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Task failed: worker failed"


def test_decode_t2i_pubsub_message_ignores_invalid_json():
    assert backend_main._decode_t2i_pubsub_message(b'{"status":"done"}') == {
        "status": "done"
    }
    assert backend_main._decode_t2i_pubsub_message("not-json") is None


@pytest.mark.asyncio
async def test_get_immediate_t2i_terminal_response_returns_done_payload():
    class FakeQueueManager:
        async def get_task_status(self, task_id):
            assert task_id == "task-1"
            return {"status": "done", "result_path": "foo/bar.png", "error_msg": None}

    response = await backend_main._get_immediate_t2i_terminal_response(
        queue_manager=FakeQueueManager(),
        task_id="task-1",
        request_id="req-1",
    )

    assert response is not None
    assert response.task_id == "task-1"
    assert response.image_url == backend_main._build_result_url("foo/bar.png")


@pytest.mark.asyncio
async def test_enqueue_t2i_task_wraps_unexpected_errors():
    class FakeQueueManager:
        async def enqueue_task(self, _task_type, _params, _priority, _task_id):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc_info:
        await backend_main._enqueue_t2i_task(
            queue_manager=FakeQueueManager(),
            task_id="task-1",
            params={"prompt": "dragon"},
            priority=3,
            request_id="req-1",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"


@pytest.mark.asyncio
async def test_optional_t2i_task_subscription_subscribes_and_closes(monkeypatch):
    events = []

    async def fake_subscribe_task_events(queue_manager, task_id):
        events.append(("subscribe", queue_manager, task_id))
        return "pubsub-1", "channel-1"

    async def fake_close_task_event_subscription(*, pubsub, channel):
        events.append(("close", pubsub, channel))

    monkeypatch.setattr(backend_main, "_subscribe_task_events", fake_subscribe_task_events)
    monkeypatch.setattr(
        backend_main,
        "_close_task_event_subscription",
        fake_close_task_event_subscription,
    )

    async with backend_main._optional_t2i_task_subscription(
        async_mode=False,
        queue_manager="qm",
        task_id="task-1",
    ) as (pubsub, channel):
        assert (pubsub, channel) == ("pubsub-1", "channel-1")
        events.append(("body", pubsub, channel))

    assert events == [
        ("subscribe", "qm", "task-1"),
        ("body", "pubsub-1", "channel-1"),
        ("close", "pubsub-1", "channel-1"),
    ]


@pytest.mark.asyncio
async def test_submit_t2i_task_request_returns_async_response_without_wait(monkeypatch):
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

    monkeypatch.setattr(backend_main, "_optional_t2i_task_subscription", lambda **kwargs: _AsyncSubscription())
    monkeypatch.setattr(backend_main, "_enqueue_t2i_task", enqueue_task)
    monkeypatch.setattr(backend_main, "_wait_for_t2i_sync_result", wait_for_sync_result)

    response = await backend_main._submit_t2i_task_request(
        async_mode=True,
        queue_manager="qm",
        task_id="task-1",
        params={"prompt": "dragon"},
        task_priority=3,
        request_id="req-1",
    )

    assert response.task_id == "task-1"
    assert events == ["enter", "exit"]
    enqueue_task.assert_awaited_once()
    wait_for_sync_result.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_t2i_task_request_waits_for_sync_result(monkeypatch):
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

    monkeypatch.setattr(backend_main, "_optional_t2i_task_subscription", lambda **kwargs: _SyncSubscription())
    monkeypatch.setattr(backend_main, "_enqueue_t2i_task", enqueue_task)
    monkeypatch.setattr(backend_main, "_wait_for_t2i_sync_result", wait_for_sync_result)

    response = await backend_main._submit_t2i_task_request(
        async_mode=False,
        queue_manager="qm",
        task_id="task-1",
        params={"prompt": "dragon"},
        task_priority=3,
        request_id="req-1",
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


def test_simple_task_type_map_keeps_video_lora_compatibility():
    assert backend_main.SIMPLE_TASK_TYPE_MAP["video_lora"] == TaskType.VIDEO_EDIT
    assert backend_main.SIMPLE_TASK_TYPE_MAP["img2img"] == TaskType.IMG2IMG


def test_simple_task_route_specs_cover_expected_paths_and_handlers():
    specs_by_path = {
        path: (request_model_cls, task_key, handler_name)
        for path, request_model_cls, task_key, handler_name in backend_main.SIMPLE_TASK_ROUTE_SPECS
    }

    assert specs_by_path["/comfy_img2img"][1:] == ("img2img", "create_img2img_task")
    assert specs_by_path["/perfect_video_lora"][1:] == (
        "video_lora",
        "create_video_lora_task",
    )
    assert specs_by_path["/api/v1/ltx_video"][1:] == (
        "ltx_video",
        "create_ltx_video_task",
    )


def test_simple_task_routes_are_registered_with_stable_endpoint_names():
    routes_by_path = {
        route.path: route.endpoint.__name__
        for route in backend_main.app.routes
        if route.path in {path for path, *_rest in backend_main.SIMPLE_TASK_ROUTE_SPECS}
    }

    assert routes_by_path["/comfy_img2img"] == "create_img2img_task"
    assert routes_by_path["/perfect_video_lora"] == "create_video_lora_task"
    assert routes_by_path["/api/v1/ltx_video"] == "create_ltx_video_task"


def test_task_status_and_result_route_specs_cover_expected_handlers():
    status_specs = {
        path: (include_image_url, include_task_type, handler_name)
        for path, include_image_url, include_task_type, handler_name in backend_main.TASK_STATUS_ROUTE_SPECS
    }
    result_specs = {
        path: (ready_error_detail, handler_name)
        for path, ready_error_detail, handler_name in backend_main.TASK_RESULT_ROUTE_SPECS
    }

    assert status_specs["/api/v1/tasks/{task_id}"] == (True, False, "get_task_status_v1")
    assert status_specs["/status/{task_id}"] == (False, True, "get_task_status")
    assert result_specs["/image/{task_id}"] == ("Image not ready", "get_task_image")
    assert result_specs["/video/{task_id}"] == ("Video not ready", "get_task_video")


def test_task_status_and_result_routes_keep_stable_endpoint_names():
    expected_paths = {
        *(path for path, *_rest in backend_main.TASK_STATUS_ROUTE_SPECS),
        *(path for path, *_rest in backend_main.TASK_RESULT_ROUTE_SPECS),
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
        backend_main,
        "_enqueue_task_from_request",
        fake_enqueue_task_from_request,
    )

    response = await backend_main._enqueue_configured_task(
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

    response = await backend_main._build_system_workers_response(FakeQueueManager())

    assert response.count == 2
    assert response.workers[0].agent_id == "agent-1"
    assert response.workers[1].agent_id == "agent-2"


@pytest.mark.asyncio
async def test_build_system_status_response_uses_queue_metrics_and_worker_count():
    class FakeQueueManager:
        async def get_queue_size(self):
            return 3

        async def get_active_workers_count(self):
            return 2

        async def get_queue_metrics_by_type(self):
            return {"ltx_video": 2, "i2i_pro": 1}

    response = await backend_main._build_system_status_response(FakeQueueManager())

    assert response.queue_size == 3
    assert response.active_workers == 2
    assert response.comfy_online is True
    assert response.queue_by_type == {"ltx_video": 2, "i2i_pro": 1}


@pytest.mark.asyncio
async def test_cancel_task_or_404_returns_cancel_result():
    class FakeQueueManager:
        async def cancel_task(self, task_id):
            assert task_id == "task-1"
            return {"state": "cancelled", "task_id": task_id}

    result = await backend_main._cancel_task_or_404(FakeQueueManager(), "task-1")

    assert result == {"state": "cancelled", "task_id": "task-1"}


@pytest.mark.asyncio
async def test_cancel_task_or_404_raises_not_found():
    class FakeQueueManager:
        async def cancel_task(self, task_id):
            assert task_id == "missing-task"
            return None

    with pytest.raises(HTTPException) as exc_info:
        await backend_main._cancel_task_or_404(FakeQueueManager(), "missing-task")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Task not found"
