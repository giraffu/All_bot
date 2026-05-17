from unittest.mock import AsyncMock

import pytest

from src.core import task_core
from src.database import core as db_core
from src.database.models import History
from src.web_api import dependencies as web_dependencies
from src.web_api.routers import tasks as tasks_router
from src.web_api.routers import users as users_router
from src.web_api.schemas.task_schema import TaskGenerateRequest


class _FakeResult:
    def __init__(self, *, single=None, many=None):
        self._single = single
        if many is None:
            self._many = [] if single is None else [single]
        else:
            self._many = list(many)

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return self

    def all(self):
        return list(self._many)


class _FakeSession:
    def __init__(self, results):
        self._results = iter(results)
        self.commit = AsyncMock()
        self.closed = False

    async def execute(self, _stmt):
        return next(self._results)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.closed = True
        return False


def _capture_background_task(coro):
    coro.close()
    return None


def _build_current_user():
    return type("User", (), {"id": 123, "username": "tester"})()


def _patch_web_generate_dependencies(monkeypatch, *, expected_balance=888):
    monitor_mock = AsyncMock()

    monkeypatch.setattr(
        task_core, "check_concurrency_lock", AsyncMock(return_value=(True, ""))
    )
    monkeypatch.setattr(
        task_core, "check_and_deduct_credits", AsyncMock(return_value=(True, ""))
    )
    monkeypatch.setattr(
        task_core,
        "get_user_priority_and_identity",
        AsyncMock(return_value=(0, "tester", "外门弟子")),
    )
    monkeypatch.setattr(task_core, "load_prompts", lambda: {})
    monkeypatch.setattr(
        task_core.TaskRegistry, "add_task", AsyncMock(return_value="reg-1")
    )
    monkeypatch.setattr(
        task_core.TaskRegistry, "update_backend_task_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        task_core, "dispatch_to_worker", AsyncMock(return_value="backend-task-1")
    )
    monkeypatch.setattr(task_core, "monitor_task_and_release_lock", monitor_mock)
    monkeypatch.setattr(task_core.asyncio, "create_task", _capture_background_task)
    monkeypatch.setattr(
        tasks_router.quota_manager,
        "get_credits",
        AsyncMock(return_value=expected_balance),
    )

    return monitor_mock


@pytest.mark.asyncio
async def test_web_apply_submit_cost_for_custom_video(monkeypatch):
    history = History(
        id=11,
        user_id=123,
        task_id="task-1",
        type="custom_video",
        prompt="cinematic action shot",
        billing_resolution="720",
        width=720,
        height=1280,
        duration=8,
        output_file="bot-data/history/task-1/output.mp4",
    )
    apply_session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: apply_session)
    monkeypatch.setattr(
        web_dependencies,
        "get_current_user",
        AsyncMock(return_value=_build_current_user()),
    )

    apply_context = await users_router.get_favorite_apply_context(
        "task-1", token="test-token"
    )

    assert apply_context.billing_resolution == "720"
    assert apply_context.duration == 8
    assert apply_context.prompt == "cinematic action shot"

    monitor_mock = _patch_web_generate_dependencies(monkeypatch)

    request = TaskGenerateRequest(
        task_type="custom_video",
        inputs={
            "images": ["123/input_images/base.png"],
            "resolution": int(apply_context.billing_resolution),
            "duration": apply_context.requested_duration or apply_context.duration,
            "prompt": apply_context.prompt,
        },
        is_template=True,
        source_post_id=apply_context.source_post_id,
    )

    response = await tasks_router.create_generation_task(
        request, current_user=_build_current_user()
    )

    assert response.cost == 36
    assert response.balance_remaining == 888
    monitor_mock.assert_called_once()
    assert monitor_mock.call_args.kwargs["cost"] == 36
    assert monitor_mock.call_args.kwargs["billing_resolution"] == "720"
    assert monitor_mock.call_args.kwargs["requested_duration"] == 8


@pytest.mark.asyncio
async def test_web_apply_submit_cost_for_video_lora(monkeypatch):
    history = History(
        id=12,
        user_id=123,
        task_id="task-2",
        type="video_lora",
        prompt="[模型: BreastGrow] glowing neon city",
        billing_resolution="1024",
        width=1024,
        height=1024,
        duration=8,
        output_file="bot-data/history/task-2/output.mp4",
    )
    apply_session = _FakeSession(
        [
            _FakeResult(single=history),
            _FakeResult(many=[]),
        ]
    )

    monkeypatch.setattr(db_core, "AsyncSessionLocal", lambda: apply_session)
    monkeypatch.setattr(
        web_dependencies,
        "get_current_user",
        AsyncMock(return_value=_build_current_user()),
    )

    apply_context = await users_router.get_favorite_apply_context(
        "task-2", token="test-token"
    )

    assert apply_context.billing_resolution == "1024"
    assert apply_context.duration == 8
    assert apply_context.prompt == "glowing neon city"
    assert apply_context.lora_name == "BreastGrow"

    monitor_mock = _patch_web_generate_dependencies(monkeypatch)

    request = TaskGenerateRequest(
        task_type="video_lora",
        inputs={
            "images": ["123/input_images/base.png"],
            "resolution": int(apply_context.billing_resolution),
            "duration": apply_context.requested_duration or apply_context.duration,
            "prompt": apply_context.prompt,
            "lora_name": apply_context.lora_name,
        },
        is_template=True,
        source_post_id=apply_context.source_post_id,
    )

    response = await tasks_router.create_generation_task(
        request, current_user=_build_current_user()
    )

    assert response.cost == 72
    assert response.balance_remaining == 888
    monitor_mock.assert_called_once()
    assert monitor_mock.call_args.kwargs["cost"] == 72
    assert monitor_mock.call_args.kwargs["billing_resolution"] == "1024"
    assert monitor_mock.call_args.kwargs["requested_duration"] == 8
