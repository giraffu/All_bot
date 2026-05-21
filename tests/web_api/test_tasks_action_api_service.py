from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.task_core import (
    ConcurrencyLimitError,
    CoreDomainError,
    InsufficientCreditsError,
)
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse
from src.web_api.services.task_action_api_service import (
    cancel_pending_task_payload,
    submit_generation_task_payload,
)


@pytest.mark.asyncio
async def test_cancel_pending_task_payload_returns_success_shape():
    with patch(
        "src.web_api.services.task_action_api_service.cancel_user_task",
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
        "src.web_api.services.task_action_api_service.cancel_user_task",
        new=AsyncMock(side_effect=CoreDomainError("不能取消")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await cancel_pending_task_payload(task_id="task-1", user_id=123)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "不能取消"


@pytest.mark.asyncio
async def test_submit_generation_task_payload_returns_submission_result():
    request = TaskGenerateRequest(task_type="image", inputs={"prompt": "foo"})
    current_user = type("User", (), {"id": 123, "username": "tester"})()
    expected = TaskGenerateResponse(
        task_id="task-1",
        status="submitted",
        message="任务已提交",
        cost=5,
        balance_remaining=95,
    )

    with patch(
        "src.web_api.services.task_action_api_service.submit_generation_task",
        new=AsyncMock(return_value=expected),
    ) as mock_submit:
        result = await submit_generation_task_payload(
            req=request,
            current_user=current_user,
            get_balance=AsyncMock(return_value=100),
            logger=MagicMock(),
        )

    assert result == expected
    mock_submit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("side_effect", "status_code", "detail"),
    [
        (ConcurrencyLimitError("排队中"), 429, "排队中"),
        (InsufficientCreditsError(1, 5), 402, "(1, 5)"),
        (CoreDomainError("参数错误"), 400, "参数错误"),
    ],
)
async def test_submit_generation_task_payload_maps_domain_errors(
    side_effect,
    status_code,
    detail,
):
    request = TaskGenerateRequest(task_type="image", inputs={"prompt": "foo"})
    current_user = type("User", (), {"id": 123, "username": "tester"})()

    with patch(
        "src.web_api.services.task_action_api_service.submit_generation_task",
        new=AsyncMock(side_effect=side_effect),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await submit_generation_task_payload(
                req=request,
                current_user=current_user,
                get_balance=AsyncMock(return_value=100),
                logger=MagicMock(),
            )

    assert exc_info.value.status_code == status_code
    assert detail in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_submit_generation_task_payload_maps_unexpected_error_to_500_and_logs():
    request = TaskGenerateRequest(task_type="image", inputs={"prompt": "foo"})
    current_user = type("User", (), {"id": 123, "username": "tester"})()
    logger = MagicMock()

    with patch(
        "src.web_api.services.task_action_api_service.submit_generation_task",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await submit_generation_task_payload(
                req=request,
                current_user=current_user,
                get_balance=AsyncMock(return_value=100),
                logger=logger,
            )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal server error"
    logger.error.assert_called_once()
