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
    "pornmaster_flux2_single_edit": "自由P图 v2 已升级，请刷新页面使用 v3。",
    "pornmaster_flux2_multi_edit": "自由P图 v2 已升级，请刷新页面使用 v3。",
    "pornmaster_flux2_multi_edit_bf16": "该执行类型仅供内部调度，请刷新页面使用自由P图 v2.5。",
}

WEB_FREE_EDIT_V3_TASK_TYPE = "pornmaster_flux2_edit_bf16"
WEB_FREE_EDIT_V3_COST = 5
WEB_FREE_EDIT_V2_5_TASK_TYPE = "free_edit_v2_5"


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
        images = list(inputs.get("images") or [])
        if req.task_type == WEB_FREE_EDIT_V2_5_TASK_TYPE and len(images) not in {1, 2}:
            raise CoreDomainError("自由P图 v2.5 仅支持上传 1 或 2 张原图。")
        if req.task_type == WEB_FREE_EDIT_V3_TASK_TYPE and len(images) != 1:
            raise CoreDomainError("自由P图 v3 仅支持上传 1 张原图。")
        if req.prompt:
            inputs["prompt"] = req.prompt

        task_id = str(uuid.uuid4())
        correlation_id.set(task_id)

        free_edit_v3_metadata = None
        if req.task_type == WEB_FREE_EDIT_V3_TASK_TYPE:
            free_edit_v3_metadata = {
                "_web_free_edit_v3": {
                    "version": 1,
                    "kind": "free_edit_v3",
                    "stage": "bf16",
                    "original_image": images[0],
                    "final_allow_contribute": not is_template,
                }
            }

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
            cost_override=(
                WEB_FREE_EDIT_V3_COST
                if req.task_type == WEB_FREE_EDIT_V3_TASK_TYPE
                else None
            ),
            user_cancel_allowed=True,
            registry_metadata=free_edit_v3_metadata,
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
