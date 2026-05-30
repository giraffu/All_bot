import uuid
from collections.abc import Awaitable, Callable

from asgi_correlation_id import correlation_id

from src.core.task_core import process_and_submit_task
from src.core.task_core_types import TaskSubmissionSideEffectPlan
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse


async def submit_generation_task(
    *,
    req: TaskGenerateRequest,
    current_user,
    get_balance: Callable[[int], Awaitable[int]],
    logger=None,
) -> TaskGenerateResponse:
    try:
        is_template = getattr(req, "is_template", False)

        if req.prompt:
            req.inputs["prompt"] = req.prompt

        task_id = str(uuid.uuid4())
        correlation_id.set(task_id)

        result = await process_and_submit_task(
            user_id=current_user.id,
            username=current_user.username,
            task_type=req.task_type,
            inputs=req.inputs,
            task_id=task_id,
            base_priority=req.priority,
            is_template=is_template,
            source_post_id=req.source_post_id,
            submission_side_effect_plan=TaskSubmissionSideEffectPlan(
                attach_web_monitor=True,
                source_post_id=req.source_post_id,
            ),
        )

        balance = await get_balance(current_user.id)
        return TaskGenerateResponse(
            task_id=result["task_id"],
            status="pending",
            message="Task submitted successfully",
            cost=result["cost"],
            balance_remaining=balance,
        )
    except Exception as exc:
        if logger is not None:
            logger.error("Task submission error: %s", exc, exc_info=True)
        raise
