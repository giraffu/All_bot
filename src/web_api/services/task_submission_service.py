import uuid
from collections.abc import Awaitable, Callable

from asgi_correlation_id import correlation_id

from src.core.task_core import process_and_submit_task
from src.core.task_core_types import CoreDomainError
from src.core.task_core_types import TaskSubmissionSideEffectPlan
from src.utils import is_maintenance_mode
from src.web_api.schemas.task_schema import TaskGenerateRequest, TaskGenerateResponse

WEB_DISABLED_GENERATION_TASK_TYPE_DETAILS = {
    "i2i_draw": "局部重绘已在 Web 端关闭，暂不支持提交。",
}


def _raise_if_web_generation_task_disabled(task_type: str) -> None:
    detail = WEB_DISABLED_GENERATION_TASK_TYPE_DETAILS.get(task_type)
    if detail:
        raise CoreDomainError(detail)


async def submit_generation_task(
    *,
    req: TaskGenerateRequest,
    current_user,
    get_balance: Callable[[int], Awaitable[int]],
    logger=None,
) -> TaskGenerateResponse:
    try:
        if is_maintenance_mode():
            raise CoreDomainError("系统维护中，生成任务暂时不可提交，请稍后再试。")

        _raise_if_web_generation_task_disabled(req.task_type)

        is_template = getattr(req, "is_template", False)

        inputs = dict(req.inputs)
        if req.prompt:
            inputs["prompt"] = req.prompt

        task_id = str(uuid.uuid4())
        correlation_id.set(task_id)

        result = await process_and_submit_task(
            user_id=current_user.id,
            username=current_user.username,
            task_type=req.task_type,
            inputs=inputs,
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
