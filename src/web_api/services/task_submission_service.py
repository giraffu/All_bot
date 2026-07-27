import os
import uuid
from collections.abc import Awaitable, Callable

from asgi_correlation_id import correlation_id
from fastapi import HTTPException

from src.core.task_core import process_and_submit_task
from src.core.task_core_types import CoreDomainError
from src.core.task_core_types import TaskSubmissionSideEffectPlan
from src.domain_config.scail2_video import SCAIL2_FACE_SWAP_V2_TASK_TYPE
from src.services.scail2_face_swap_pipeline_service import (
    cleanup_scail2_face_swap_first_frame,
    prepare_scail2_face_swap_first_frame,
)
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
LTX_T2V_CANARY_OBJECT_PREFIX = "runpod-canary/ltx-t2v/"


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
    operator_canary_authorized: bool = False,
) -> TaskGenerateResponse:
    scail2_first_frame_to_cleanup = None
    try:
        if is_maintenance_mode():
            raise CoreDomainError("系统维护中，生成任务暂时不可提交，请稍后再试。")

        _raise_if_web_generation_task_disabled(req.task_type)

        if (
            req.task_type
            in {
                "ltx_t2v",
                "ltx_t2v_ic",
                "character_reference_build",
            }
            and not operator_canary_authorized
            and os.getenv("LTX_T2V_BACKEND_ENABLED", "false").strip().lower()
            not in {
                "1",
                "true",
                "yes",
                "on",
            }
        ):
            raise CoreDomainError("文生视频与人物图库功能当前未开放。")

        is_template = getattr(req, "is_template", False)

        inputs = dict(req.inputs)
        if req.negative_prompt:
            inputs["negative_prompt"] = req.negative_prompt
        if req.task_type == "character_reference_build":
            raise CoreDomainError("人物参考表只能通过人物图库构建接口创建。")
        if req.task_type == "ltx_t2v_ic":
            character_sheet = str(inputs.get("character_sheet") or "").strip()
            if character_sheet and not operator_canary_authorized:
                raise CoreDomainError("不得直接指定人物参考表存储路径。")
            if character_sheet and operator_canary_authorized:
                if not character_sheet.startswith(LTX_T2V_CANARY_OBJECT_PREFIX):
                    raise CoreDomainError("IC canary 参考图必须位于隔离测试前缀。")
            else:
                character_id = str(inputs.get("character_id") or "").strip()
                if not character_id:
                    raise CoreDomainError("请选择一个已就绪人物。")
                from src.database.core import AsyncSessionLocal
                from src.web_api.services.character_reference_service import (
                    resolve_ready_character_sheet,
                )

                async with AsyncSessionLocal() as character_db:
                    try:
                        inputs["character_sheet"] = await resolve_ready_character_sheet(
                            db=character_db,
                            user_id=current_user.id,
                            character_id=character_id,
                        )
                    except HTTPException as exc:
                        raise CoreDomainError(str(exc.detail)) from exc
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
        scail2_face_swap_metadata = None
        if req.task_type == WEB_FREE_EDIT_V3_TASK_TYPE:
            free_edit_v3_metadata = {
                "_web_free_edit_v3": {
                    "version": 1,
                    "kind": "free_edit_v3",
                    "stage": "bf16",
                    "stage2_task_type": "face_swap_v2",
                    "original_image": images[0],
                    "final_allow_contribute": not is_template,
                }
            }
        elif req.task_type == SCAIL2_FACE_SWAP_V2_TASK_TYPE:
            if len(images) != 2:
                raise CoreDomainError("视频换脸需要上传参考图片和驱动视频。")
            first_frame = await prepare_scail2_face_swap_first_frame(
                internal_user_id=current_user.id,
                registry_task_id=task_id,
                motion_video_path=images[1],
            )
            inputs["_scail2_face_swap_first_frame"] = first_frame
            scail2_first_frame_to_cleanup = first_frame
            scail2_face_swap_metadata = {
                "_web_scail2_face_swap_v2": {
                    "version": 1,
                    "kind": SCAIL2_FACE_SWAP_V2_TASK_TYPE,
                    "stage": "face_swap_v2",
                    "first_frame": first_frame,
                    "original_reference": images[0],
                    "motion_video": images[1],
                    "duration": inputs.get("duration", 5),
                    "normal_priority": req.priority,
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
            registry_metadata=free_edit_v3_metadata or scail2_face_swap_metadata,
        )
        scail2_first_frame_to_cleanup = None

        balance = await get_balance(current_user.id)
        return TaskGenerateResponse(
            task_id=result["task_id"],
            status="pending",
            message="Task submitted successfully",
            cost=result["cost"],
            balance_remaining=balance,
        )
    except Exception as exc:
        if scail2_first_frame_to_cleanup:
            await cleanup_scail2_face_swap_first_frame(scail2_first_frame_to_cleanup)
        if logger is not None:
            logger.error("Task submission error: %s", exc, exc_info=True)
        raise
