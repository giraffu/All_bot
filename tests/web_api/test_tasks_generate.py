from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

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
        video_task_types={
            "custom_video",
            "video_lora",
            "image_to_video",
            "wan22_video_v2",
        },
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
    assert submission_context.log_prompt == "glowing neon city"


@pytest.mark.asyncio
async def test_web_generate_accepts_literal_image_to_video_task_type(monkeypatch):
    monitor_calls, deduct_credits = _patch_web_generate_dependencies(monkeypatch)

    request = TaskGenerateRequest(
        task_type="image_to_video",
        inputs={
            "images": ["123/input_images/base.png"],
            "resolution_preset": "preview",
            "duration": 5,
            "prompt": "镜头中出现一个女人",
            "lora_name": "Insertion",
            "lora_strength": 1.0,
            "extract_last_frame": True,
        },
    )

    response = await tasks_router.create_generation_task(
        request,
        current_user=_build_current_user(),
    )

    assert response.cost == 6
    assert response.balance_remaining == 888
    deduct_credits.assert_awaited_once()
    assert len(monitor_calls) == 1
    submission_context = monitor_calls[0]["submission_context"]
    assert submission_context.task_type == "image_to_video"
    assert submission_context.is_video_task is True
    assert submission_context.billing_resolution == "preview"
    assert submission_context.requested_duration == 5


@pytest.mark.asyncio
async def test_web_generate_rejects_i2i_draw_without_submitting(monkeypatch):
    process_task = AsyncMock()
    monkeypatch.setattr(
        task_submission_service,
        "process_and_submit_task",
        process_task,
    )

    request = TaskGenerateRequest(
        task_type="i2i_draw",
        inputs={
            "images": ["123/input_images/base.png"],
        },
        prompt="repaint local area",
    )

    with pytest.raises(HTTPException) as exc_info:
        await tasks_router.create_generation_task(
            request,
            current_user=_build_current_user(),
        )

    assert exc_info.value.status_code == 400
    assert "局部重绘" in exc_info.value.detail
    process_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_web_generate_submits_free_edit_v3_as_one_five_credit_logical_task(
    monkeypatch,
):
    process_task = AsyncMock(return_value={"task_id": "logical-task-1", "cost": 5})
    monkeypatch.setattr(
        task_submission_service,
        "process_and_submit_task",
        process_task,
    )
    monkeypatch.setattr(
        tasks_router.quota_manager,
        "get_credits",
        AsyncMock(return_value=95),
    )

    response = await tasks_router.create_generation_task(
        TaskGenerateRequest(
            task_type="pornmaster_flux2_edit_bf16",
            inputs={"images": ["123/input_images/original.png"]},
            prompt="keep the pose",
        ),
        current_user=_build_current_user(),
    )

    assert response.task_id == "logical-task-1"
    assert response.cost == 5
    submit_kwargs = process_task.await_args.kwargs
    assert submit_kwargs["cost_override"] == 5
    assert submit_kwargs["user_cancel_allowed"] is True
    assert submit_kwargs["registry_metadata"]["_web_free_edit_v3"] == {
        "version": 1,
        "kind": "free_edit_v3",
        "stage": "bf16",
        "stage2_task_type": "face_swap_v2",
        "original_image": "123/input_images/original.png",
        "final_allow_contribute": True,
    }


@pytest.mark.asyncio
async def test_web_scail2_face_swap_prepares_first_frame_and_persists_continuation(
    monkeypatch,
):
    process_task = AsyncMock(return_value={"task_id": "logical-video", "cost": 40})
    prepare_first_frame = AsyncMock(
        return_value="123/pipeline_inputs/logical-video_first_frame.png"
    )
    monkeypatch.setattr(
        task_submission_service,
        "process_and_submit_task",
        process_task,
    )
    monkeypatch.setattr(
        task_submission_service,
        "prepare_scail2_face_swap_first_frame",
        prepare_first_frame,
    )
    monkeypatch.setattr(
        tasks_router.quota_manager,
        "get_credits",
        AsyncMock(return_value=60),
    )

    response = await tasks_router.create_generation_task(
        TaskGenerateRequest(
            task_type="scail2_face_swap_v2",
            inputs={
                "images": [
                    "123/input_images/reference.png",
                    "123/input_images/motion.mp4",
                ],
                "duration": 5,
            },
            prompt="keep the original scene",
            priority=7,
        ),
        current_user=_build_current_user(),
    )

    assert response.task_id == "logical-video"
    submit_kwargs = process_task.await_args.kwargs
    generated_task_id = submit_kwargs["task_id"]
    prepare_first_frame.assert_awaited_once_with(
        internal_user_id=123,
        registry_task_id=generated_task_id,
        motion_video_path="123/input_images/motion.mp4",
    )
    assert submit_kwargs["base_priority"] == 7
    assert submit_kwargs["inputs"]["_scail2_face_swap_first_frame"] == (
        "123/pipeline_inputs/logical-video_first_frame.png"
    )
    assert submit_kwargs["registry_metadata"]["_web_scail2_face_swap_v2"] == {
        "version": 1,
        "kind": "scail2_face_swap_v2",
        "stage": "face_swap_v2",
        "first_frame": "123/pipeline_inputs/logical-video_first_frame.png",
        "original_reference": "123/input_images/reference.png",
        "motion_video": "123/input_images/motion.mp4",
        "duration": 5,
        "normal_priority": 7,
        "final_allow_contribute": True,
    }


@pytest.mark.asyncio
async def test_web_scail2_face_swap_cleans_hidden_frame_when_submission_fails(
    monkeypatch,
):
    hidden_frame = "123/pipeline_inputs/logical-video_first_frame.png"
    cleanup_first_frame = AsyncMock(return_value=True)
    monkeypatch.setattr(
        task_submission_service,
        "prepare_scail2_face_swap_first_frame",
        AsyncMock(return_value=hidden_frame),
    )
    monkeypatch.setattr(
        task_submission_service,
        "cleanup_scail2_face_swap_first_frame",
        cleanup_first_frame,
    )
    monkeypatch.setattr(
        task_submission_service,
        "process_and_submit_task",
        AsyncMock(side_effect=RuntimeError("submission failed")),
    )

    with pytest.raises(RuntimeError, match="submission failed"):
        await task_submission_service.submit_generation_task(
            req=TaskGenerateRequest(
                task_type="scail2_face_swap_v2",
                inputs={
                    "images": [
                        "123/input_images/reference.png",
                        "123/input_images/motion.mp4",
                    ],
                    "duration": 5,
                },
                prompt="keep the original scene",
            ),
            current_user=_build_current_user(),
            get_balance=AsyncMock(return_value=60),
        )

    cleanup_first_frame.assert_awaited_once_with(hidden_frame)


@pytest.mark.asyncio
async def test_web_generate_submits_free_edit_v25_as_one_three_credit_stage(
    monkeypatch,
):
    process_task = AsyncMock(return_value={"task_id": "logical-v25", "cost": 3})
    monkeypatch.setattr(
        task_submission_service,
        "process_and_submit_task",
        process_task,
    )
    monkeypatch.setattr(
        tasks_router.quota_manager,
        "get_credits",
        AsyncMock(return_value=97),
    )

    response = await tasks_router.create_generation_task(
        TaskGenerateRequest(
            task_type="free_edit_v2_5",
            inputs={"images": ["123/input_images/original.png"]},
            prompt="keep the pose",
            is_template=True,
            source_post_id=25,
        ),
        current_user=_build_current_user(),
    )

    assert response.task_id == "logical-v25"
    assert response.cost == 3
    submit_kwargs = process_task.await_args.kwargs
    assert submit_kwargs["task_type"] == "free_edit_v2_5"
    assert submit_kwargs["is_template"] is True
    assert submit_kwargs["source_post_id"] == 25
    assert submit_kwargs["cost_override"] is None
    assert submit_kwargs["registry_metadata"] is None


@pytest.mark.asyncio
async def test_web_generate_submits_two_image_free_edit_v25_for_seven_credits(
    monkeypatch,
):
    process_task = AsyncMock(return_value={"task_id": "logical-v25-2", "cost": 7})
    monkeypatch.setattr(
        task_submission_service, "process_and_submit_task", process_task
    )
    monkeypatch.setattr(
        tasks_router.quota_manager,
        "get_credits",
        AsyncMock(return_value=93),
    )

    response = await tasks_router.create_generation_task(
        TaskGenerateRequest(
            task_type="free_edit_v2_5",
            inputs={"images": ["123/input_images/one.png", "123/input_images/two.png"]},
            prompt="combine both references",
        ),
        current_user=_build_current_user(),
    )

    assert response.cost == 7
    assert process_task.await_args.kwargs["inputs"]["images"] == [
        "123/input_images/one.png",
        "123/input_images/two.png",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "task_type,images",
    [
        ("pornmaster_flux2_edit_bf16", []),
        (
            "pornmaster_flux2_edit_bf16",
            ["123/input_images/one.png", "123/input_images/two.png"],
        ),
        ("pornmaster_flux2_single_edit", ["123/input_images/one.png"]),
        (
            "pornmaster_flux2_multi_edit",
            ["123/input_images/one.png", "123/input_images/two.png"],
        ),
        (
            "pornmaster_flux2_multi_edit_bf16",
            ["123/input_images/one.png", "123/input_images/two.png"],
        ),
    ],
)
async def test_web_generate_rejects_invalid_or_legacy_free_edit_requests(
    monkeypatch,
    task_type,
    images,
):
    process_task = AsyncMock()
    monkeypatch.setattr(
        task_submission_service,
        "process_and_submit_task",
        process_task,
    )

    with pytest.raises(HTTPException) as exc_info:
        await tasks_router.create_generation_task(
            TaskGenerateRequest(
                task_type=task_type,
                inputs={"images": images},
                prompt="edit prompt",
            ),
            current_user=_build_current_user(),
        )

    assert exc_info.value.status_code == 400
    assert "v" in str(exc_info.value.detail)
    process_task.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "images",
    [[], ["a.png", "b.png", "c.png"]],
)
async def test_web_generate_requires_one_or_two_free_edit_v2_5_images(
    monkeypatch, images
):
    process_task = AsyncMock()
    monkeypatch.setattr(
        task_submission_service,
        "process_and_submit_task",
        process_task,
    )

    with pytest.raises(HTTPException) as exc_info:
        await tasks_router.create_generation_task(
            TaskGenerateRequest(
                task_type="free_edit_v2_5",
                inputs={"images": images},
                prompt="edit prompt",
            ),
            current_user=_build_current_user(),
        )

    assert exc_info.value.status_code == 400
    assert "v2.5" in str(exc_info.value.detail)
    process_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_web_generate_rejects_during_maintenance(monkeypatch):
    monkeypatch.setattr(task_submission_service, "is_maintenance_mode", lambda: True)

    request = TaskGenerateRequest(
        task_type="image_to_video",
        inputs={
            "images": ["123/input_images/base.png"],
            "duration": 5,
            "prompt": "maintenance gate",
        },
    )

    with pytest.raises(tasks_router.HTTPException) as exc_info:
        await tasks_router.create_generation_task(
            request,
            current_user=_build_current_user(),
        )

    assert exc_info.value.status_code == 400
    assert "系统维护中" in str(exc_info.value.detail)
