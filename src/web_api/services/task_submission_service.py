import os
import uuid
from collections.abc import Awaitable, Callable

from asgi_correlation_id import correlation_id

from config import MINIO_BUCKET
from src.core.task_core import process_and_submit_task
from src.core.task_core_types import CoreDomainError
from src.core.task_core_types import TaskSubmissionSideEffectPlan
from src.domain_config.scail2_video import SCAIL2_FACE_SWAP_V2_TASK_TYPE
from src.services.scail2_face_swap_pipeline_service import (
    cleanup_scail2_face_swap_first_frame,
    prepare_scail2_face_swap_first_frame,
)
from src.services.storage import storage
from src.services.storage_r2_promotion import promote_staged_user_inputs
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
_ENABLED_VALUES = {"1", "true", "yes", "on"}


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in _ENABLED_VALUES


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
    task_id_override: str | None = None,
    registry_metadata_extra: dict | None = None,
    allow_contribute_override: bool | None = None,
    promote_staged_inputs_func=None,
) -> TaskGenerateResponse:
    scail2_first_frame_to_cleanup = None
    try:
        if is_maintenance_mode():
            raise CoreDomainError("系统维护中，生成任务暂时不可提交，请稍后再试。")

        _raise_if_web_generation_task_disabled(req.task_type)

        if req.task_type in {"ltx_video_v2", "ltx_video_v2_flf2v"} and not _env_enabled(
            "ENABLE_LTX_VIDEO_V2"
        ):
            raise CoreDomainError("高级图生视频 v2 当前未开放。")

        if (
            req.task_type
            in {
                "ltx_t2v",
                "ltx_t2v_ic",
                "character_reference_build",
            }
            and not operator_canary_authorized
            and not _env_enabled("LTX_T2V_BACKEND_ENABLED")
        ):
            raise CoreDomainError("文生视频与人物图库功能当前未开放。")

        if (
            req.task_type.startswith("minimax_h3_")
            and not operator_canary_authorized
            and not _env_enabled("MINIMAX_H3_BACKEND_ENABLED")
        ):
            raise CoreDomainError("高级视频生成功能当前未开放。")

        is_template = getattr(req, "is_template", False)

        inputs = dict(req.inputs)
        if req.negative_prompt:
            inputs["negative_prompt"] = req.negative_prompt
        if req.task_type == "character_reference_build":
            raise CoreDomainError("人物参考表只能通过人物图库构建接口创建。")
        if req.task_type == "ltx_t2v_ic":
            if (
                not _env_enabled("LTX_T2V_MSR_ENABLED")
                and not operator_canary_authorized
            ):
                raise CoreDomainError("MSR 双角色模式当前未开放。")
            forbidden = {
                "character_id",
                "character_sheet",
                "character_sheets",
                "character_description",
                "character_descriptions",
                "background_image",
                "sulphur_strength",
            }
            if any(inputs.get(key) is not None for key in forbidden):
                raise CoreDomainError(
                    "不得直接指定角色参考表、背景存储路径或 LoRA 强度。"
                )
            from src.database.core import AsyncSessionLocal
            from src.web_api.services.reference_asset_service import (
                normalize_reference_inputs,
                resolve_reference_set,
            )

            character_refs, environment_ref = normalize_reference_inputs(inputs)
            async with AsyncSessionLocal() as character_db:
                resolved_references = await resolve_reference_set(
                    db=character_db,
                    user_id=current_user.id,
                    character_refs=character_refs,
                    environment_ref=environment_ref,
                )
            inputs.pop("character_ids", None)
            inputs.pop("background_object_key", None)
            inputs.pop("character_refs", None)
            inputs.pop("environment_ref", None)
            inputs["character_sheets"] = list(resolved_references.character_sheets)
            inputs["character_descriptions"] = list(
                resolved_references.character_descriptions
            )
            inputs["background_image"] = resolved_references.environment_object_key
        elif req.task_type == "ltx_t2v" and any(
            inputs.get(key) is not None
            for key in (
                "character_ids",
                "background_object_key",
                "character_refs",
                "environment_ref",
            )
        ):
            raise CoreDomainError("纯文生视频不能携带角色或环境引用。")
        images = list(inputs.get("images") or [])
        if req.task_type == WEB_FREE_EDIT_V2_5_TASK_TYPE and len(images) not in {1, 2}:
            raise CoreDomainError("自由P图 v2.5 仅支持上传 1 或 2 张原图。")
        if req.task_type == WEB_FREE_EDIT_V3_TASK_TYPE and len(images) != 1:
            raise CoreDomainError("自由P图 v3 仅支持上传 1 张原图。")
        if req.prompt:
            inputs["prompt"] = req.prompt

        task_id = task_id_override or str(uuid.uuid4())
        correlation_id.set(task_id)
        promote_staged_inputs_func = (
            promote_staged_inputs_func or promote_staged_user_inputs
        )
        if images:
            images = await promote_staged_inputs_func(
                input_refs=images,
                task_id=task_id,
                user_id=current_user.id,
                bucket=MINIO_BUCKET,
                client=storage.client,
            )
            inputs["images"] = images

        registry_metadata = dict(registry_metadata_extra or {})
        if req.task_type == WEB_FREE_EDIT_V3_TASK_TYPE:
            registry_metadata["_web_free_edit_v3"] = {
                "version": 1,
                "kind": "free_edit_v3",
                "stage": "bf16",
                "stage2_task_type": "face_swap_v2",
                "original_image": images[0],
                "final_allow_contribute": (
                    bool(allow_contribute_override)
                    if allow_contribute_override is not None
                    else not is_template
                ),
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
            registry_metadata["_web_scail2_face_swap_v2"] = {
                "version": 1,
                "kind": SCAIL2_FACE_SWAP_V2_TASK_TYPE,
                "stage": "face_swap_v2",
                "first_frame": first_frame,
                "original_reference": images[0],
                "motion_video": images[1],
                "duration": inputs.get("duration", 5),
                "normal_priority": req.priority,
                "final_allow_contribute": (
                    bool(allow_contribute_override)
                    if allow_contribute_override is not None
                    else not is_template
                ),
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
            registry_metadata=registry_metadata or None,
            allow_contribute_override=allow_contribute_override,
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
