from unittest.mock import AsyncMock

import pytest

from src.core import task_core
from src.core.task_core_dependencies import TaskCoreProcessDependencies
from src.core.task_core_types import TaskSubmissionExecutionResult
from src.database import core as db_core
from src.database.models import History
from src.web_api.routers import tasks as tasks_router
from src.web_api.routers import users as users_router
from src.web_api.schemas.task_schema import TaskGenerateRequest
from src.web_api.services import task_submission_service


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


def _build_current_user():
    return type("User", (), {"id": 123, "username": "tester"})()


def _patch_web_generate_dependencies(monkeypatch, *, expected_balance=888):
    monitor_calls = []
    check_lock = AsyncMock(return_value=(True, ""))
    deduct_credits = AsyncMock(return_value=(True, ""))

    async def prepare_payload(**kwargs):
        inputs = kwargs["inputs"]
        video_request = task_core.build_video_task_request(kwargs["task_type"], inputs)
        return task_core.TaskSubmissionContext(
            task_type=kwargs["task_type"],
            is_video_task=True,
            user_logger=type("Logger", (), {"user_id": 123, "username": "tester"})(),
            prompt=inputs.get("prompt", ""),
            saved_inputs=list(inputs.get("images", [])),
            metadata={
                key: inputs[key]
                for key in ("lora_name", "lora_strength")
                if inputs.get(key) is not None
            },
            allow_contribute=True,
            final_priority=0,
            video_request=video_request,
        )

    async def execute_saga(**kwargs):
        return TaskSubmissionExecutionResult(
            registry_task_id=kwargs["registry_task_id"],
            backend_task_id="backend-task-1",
            submission_context=kwargs["submission_context"],
        )

    def attach_side_effects(**kwargs):
        monitor_calls.append(kwargs)

    dependencies = TaskCoreProcessDependencies(
        get_strategy_func=lambda _task_type: task_core.StrategyFactory.get_strategy(
            _task_type
        ),
        video_task_types={"custom_video", "video_lora"},
        build_video_task_request_func=task_core.build_video_task_request,
        check_concurrency_lock_func=check_lock,
        prepare_task_submission_payload_func=prepare_payload,
        check_and_deduct_credits_func=deduct_credits,
        execute_task_submission_saga_func=execute_saga,
        attach_submission_side_effects_func=attach_side_effects,
        compensate_failed_submission_func=AsyncMock(),
        release_concurrency_lock_func=AsyncMock(),
        shield_func=lambda coro: coro,
        logger=task_core.logger,
    )

    async def process_and_submit_task_with_dependencies(**kwargs):
        return await task_core.process_and_submit_task(
            **kwargs,
            dependencies=dependencies,
        )

    monkeypatch.setattr(
        task_submission_service,
        "process_and_submit_task",
        process_and_submit_task_with_dependencies,
    )
    monkeypatch.setattr(
        tasks_router.quota_manager,
        "get_credits",
        AsyncMock(return_value=expected_balance),
    )

    return monitor_calls, deduct_credits


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
    apply_context = await users_router.get_favorite_apply_context(
        "task-1", current_user=_build_current_user(), db=apply_session
    )

    assert apply_context.billing_resolution == "standard"
    assert apply_context.duration == 5
    assert apply_context.prompt == "cinematic action shot"

    monitor_calls, deduct_credits = _patch_web_generate_dependencies(monkeypatch)

    request = TaskGenerateRequest(
        task_type="custom_video",
        inputs={
            "images": ["123/input_images/base.png"],
            "resolution_preset": apply_context.billing_resolution,
            "duration": apply_context.requested_duration or apply_context.duration,
            "prompt": apply_context.prompt,
        },
        is_template=True,
        source_post_id=apply_context.source_post_id,
    )

    response = await tasks_router.create_generation_task(
        request, current_user=_build_current_user()
    )

    assert response.cost == 20
    assert response.balance_remaining == 888
    deduct_credits.assert_awaited_once()
    assert len(monitor_calls) == 1
    assert monitor_calls[0]["cost"] == 20
    submission_context = monitor_calls[0]["submission_context"]
    assert submission_context.billing_resolution == "standard"
    assert submission_context.requested_duration == 5


@pytest.mark.asyncio
async def test_web_apply_submit_cost_for_video_lora(monkeypatch):
    history = History(
        id=12,
        user_id=123,
        task_id="task-2",
        type="video_lora",
        prompt="[模型: BreastGrow] [强度: 0.80] glowing neon city",
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
    apply_context = await users_router.get_favorite_apply_context(
        "task-2", current_user=_build_current_user(), db=apply_session
    )

    assert apply_context.billing_resolution == "hd"
    assert apply_context.duration == 5
    assert apply_context.prompt == "glowing neon city"
    assert apply_context.lora_name == "BreastGrow"
    assert apply_context.lora_strength == 0.8

    monitor_calls, deduct_credits = _patch_web_generate_dependencies(monkeypatch)

    request = TaskGenerateRequest(
        task_type="video_lora",
        inputs={
            "images": ["123/input_images/base.png"],
            "resolution_preset": apply_context.billing_resolution,
            "duration": apply_context.requested_duration or apply_context.duration,
            "prompt": apply_context.prompt,
            "lora_name": apply_context.lora_name,
            "lora_strength": apply_context.lora_strength,
        },
        is_template=True,
        source_post_id=apply_context.source_post_id,
    )

    response = await tasks_router.create_generation_task(
        request, current_user=_build_current_user()
    )

    assert response.cost == 30
    assert response.balance_remaining == 888
    deduct_credits.assert_awaited_once()
    assert len(monitor_calls) == 1
    assert monitor_calls[0]["cost"] == 30
    submission_context = monitor_calls[0]["submission_context"]
    assert submission_context.billing_resolution == "hd"
    assert submission_context.requested_duration == 5
    assert submission_context.log_prompt == "[模型: BreastGrow] [强度: 0.80] glowing neon city"
