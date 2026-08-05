from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
    QueueCapacityError,
)
from src.web_api.routers import tasks as tasks_router
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse
from src.web_api.services.task_submission_service import submit_generation_task
from src.web_api.services.user_task_api_service import cancel_pending_task_payload


@pytest.mark.asyncio
async def test_cancel_pending_task_payload_returns_success_shape():
    with patch(
        "src.web_api.services.user_task_api_service.cancel_user_task",
        new=AsyncMock(return_value={"message": "已取消", "state": "cancelled"}),
    ):
        payload = await cancel_pending_task_payload(task_id="task-1", user_id=123)

    assert payload == {
        "status": "success",
        "message": "已取消",
        "cancel_state": "cancelled",
    }


@pytest.mark.asyncio
async def test_cancel_pending_task_payload_maps_domain_error_to_400():
    with patch(
        "src.web_api.services.user_task_api_service.cancel_user_task",
        new=AsyncMock(side_effect=CoreDomainError("不能取消")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await cancel_pending_task_payload(task_id="task-1", user_id=123)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "不能取消"


@pytest.mark.asyncio
async def test_submit_generation_task_returns_submission_result():
    request = TaskGenerateRequest(task_type="image", inputs={"prompt": "foo"})
    current_user = type("User", (), {"id": 123, "username": "tester"})()

    with patch(
        "src.web_api.services.task_submission_service.process_and_submit_task",
        new=AsyncMock(return_value={"task_id": "task-1", "cost": 5}),
    ), patch(
        "src.web_api.services.task_submission_service.uuid.uuid4",
        return_value="task-1",
    ):
        result = await submit_generation_task(
            req=request,
            current_user=current_user,
            get_balance=AsyncMock(return_value=95),
            logger=MagicMock(),
        )

    assert result == TaskGenerateResponse(
        task_id="task-1",
        status="pending",
        message="Task submitted successfully",
        cost=5,
        balance_remaining=95,
    )


@pytest.mark.asyncio
async def test_submit_generation_task_copies_top_level_prompt_into_txt2img_inputs():
    request = TaskGenerateRequest(
        task_type="txt2img",
        inputs={"images": []},
        prompt="sky city",
    )
    current_user = type("User", (), {"id": 123, "username": "tester"})()

    with patch(
        "src.web_api.services.task_submission_service.process_and_submit_task",
        new=AsyncMock(return_value={"task_id": "task-1", "cost": 2}),
    ) as process_mock, patch(
        "src.web_api.services.task_submission_service.uuid.uuid4",
        return_value="task-1",
    ):
        await submit_generation_task(
            req=request,
            current_user=current_user,
            get_balance=AsyncMock(return_value=98),
            logger=MagicMock(),
        )

    process_mock.assert_awaited_once()
    assert process_mock.await_args.kwargs["task_type"] == "txt2img"
    assert process_mock.await_args.kwargs["inputs"] == {
        "images": [],
        "prompt": "sky city",
    }
    assert request.inputs == {"images": []}


@pytest.mark.asyncio
async def test_submit_generation_task_promotes_staged_web_inputs_before_queueing():
    request = TaskGenerateRequest(
        task_type="image",
        inputs={"images": ["user-data-prod/staging/user-uploads/123/u1.png"]},
    )
    current_user = type("User", (), {"id": 123, "username": "tester"})()
    promote = AsyncMock(return_value=["task-inputs/task-1/0.png"])

    with patch(
        "src.web_api.services.task_submission_service.process_and_submit_task",
        new=AsyncMock(return_value={"task_id": "task-1", "cost": 2}),
    ) as process_mock, patch(
        "src.web_api.services.task_submission_service.uuid.uuid4",
        return_value="task-1",
    ):
        await submit_generation_task(
            req=request,
            current_user=current_user,
            get_balance=AsyncMock(return_value=98),
            promote_staged_inputs_func=promote,
        )

    assert promote.await_args.kwargs["task_id"] == "task-1"
    assert promote.await_args.kwargs["user_id"] == 123
    assert process_mock.await_args.kwargs["inputs"]["images"] == [
        "task-inputs/task-1/0.png"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "side_effect",
    [
        ConcurrencyLimitError("排队中"),
        InsufficientCreditsError(1, 5),
        CoreDomainError("参数错误"),
    ],
)
async def test_submit_generation_task_reraises_domain_errors(side_effect):
    request = TaskGenerateRequest(task_type="image", inputs={"prompt": "foo"})
    current_user = type("User", (), {"id": 123, "username": "tester"})()
    logger = MagicMock()

    with patch(
        "src.web_api.services.task_submission_service.process_and_submit_task",
        new=AsyncMock(side_effect=side_effect),
    ):
        with pytest.raises(type(side_effect)) as exc_info:
            await submit_generation_task(
                req=request,
                current_user=current_user,
                get_balance=AsyncMock(return_value=100),
                logger=logger,
            )

    assert str(exc_info.value) == str(side_effect)
    logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_submit_generation_task_reraises_unexpected_error_and_logs():
    request = TaskGenerateRequest(task_type="image", inputs={"prompt": "foo"})
    current_user = type("User", (), {"id": 123, "username": "tester"})()
    logger = MagicMock()

    with patch(
        "src.web_api.services.task_submission_service.process_and_submit_task",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await submit_generation_task(
                req=request,
                current_user=current_user,
                get_balance=AsyncMock(return_value=100),
                logger=logger,
            )

    logger.error.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("side_effect", "status_code", "detail"),
    [
        (ConcurrencyLimitError("排队中"), 429, "排队中"),
        (InsufficientCreditsError(1, 5), 402, "(1, 5)"),
        (CoreDomainError("参数错误"), 400, "参数错误"),
        (RuntimeError("boom"), 500, "Internal server error"),
    ],
)
async def test_create_generation_task_maps_service_errors_to_http(
    side_effect,
    status_code,
    detail,
):
    request = TaskGenerateRequest(task_type="image", inputs={"prompt": "foo"})
    current_user = type("User", (), {"id": 123, "username": "tester"})()

    with patch(
        "src.web_api.routers.tasks.submit_generation_task",
        new=AsyncMock(side_effect=side_effect),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await tasks_router.create_generation_task(
                request,
                current_user=current_user,
            )

    assert exc_info.value.status_code == status_code
    assert detail in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_generation_task_exposes_queue_capacity_reason_for_frontend_i18n():
    request = TaskGenerateRequest(task_type="image", inputs={"prompt": "foo"})
    current_user = type("User", (), {"id": 123, "username": "tester"})()

    with patch(
        "src.web_api.routers.tasks.submit_generation_task",
        new=AsyncMock(side_effect=QueueCapacityError("queue full")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await tasks_router.create_generation_task(
                request,
                current_user=current_user,
            )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == {
        "code": "GENERATION_QUEUE_FULL",
        "detail": "queue full",
    }
