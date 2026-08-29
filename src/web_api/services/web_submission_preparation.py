from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from src.core.task_core_types import CoreDomainError
from src.domain_config.scail2_video import SCAIL2_FACE_SWAP_V2_TASK_TYPE


WEB_DISABLED_GENERATION_TASK_TYPE_DETAILS = {
    "i2i_draw": "局部重绘已在 Web 端关闭，暂不支持提交。",
    "pornmaster_flux2_single_edit": "自由P图 v2 已升级，请刷新页面使用 v3。",
    "pornmaster_flux2_multi_edit": "自由P图 v2 已升级，请刷新页面使用 v3。",
    "pornmaster_flux2_multi_edit_bf16": "该执行类型仅供内部调度，请刷新页面使用自由P图 v2.5。",
}
WEB_FREE_EDIT_V3_TASK_TYPE = "pornmaster_flux2_edit_bf16"
WEB_FREE_EDIT_V3_COST = 5
WEB_FREE_EDIT_V2_5_TASK_TYPE = "free_edit_v2_5"


@dataclass(frozen=True)
class PreparedWebSubmission:
    inputs: dict[str, Any]
    images: list[str]
    is_template: bool
    registry_metadata: dict[str, Any] | None = None
    allow_contribute_override: bool | None = None


@dataclass(frozen=True)
class PreparedWebPipeline:
    registry_metadata: dict[str, Any]
    cleanup_object_key: str | None = None


def _assert_task_access(
    task_type: str,
    *,
    operator_canary_authorized: bool,
    env_enabled: Callable[[str], bool],
) -> None:
    disabled_detail = WEB_DISABLED_GENERATION_TASK_TYPE_DETAILS.get(task_type)
    if disabled_detail:
        raise CoreDomainError(disabled_detail)
    if task_type in {"ltx_video_v2", "ltx_video_v2_flf2v"} and not env_enabled(
        "ENABLE_LTX_VIDEO_V2"
    ):
        raise CoreDomainError("高级图生视频 v2 当前未开放。")
    gated_types = {"ltx_t2v", "ltx_t2v_ic"}
    if (
        task_type in gated_types
        and not operator_canary_authorized
        and not env_enabled("LTX_T2V_BACKEND_ENABLED")
    ):
        raise CoreDomainError("文生视频与人物图库功能当前未开放。")
    if (
        task_type == "character_reference_build"
        and not operator_canary_authorized
        and not env_enabled("CHARACTER_ASSETS_ENABLED")
    ):
        raise CoreDomainError("人物身份素材功能当前未开放。")
    if (
        task_type.startswith("minimax_h3_")
        and not operator_canary_authorized
        and not env_enabled("MINIMAX_H3_BACKEND_ENABLED")
    ):
        raise CoreDomainError("高级视频生成功能当前未开放。")
    if (
        task_type == "minimax_h3_ref2v"
        and not operator_canary_authorized
        and not env_enabled("MINIMAX_H3_REF2V_ENABLED")
    ):
        raise CoreDomainError("参考图生视频功能当前未开放。")


async def _resolve_ltx_character_inputs(
    inputs: dict[str, Any],
    *,
    internal_user_id: int,
    env_enabled: Callable[[str], bool],
) -> None:
    if not env_enabled("LTX_T2V_MSR_ENABLED"):
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
        raise CoreDomainError("不得直接指定角色参考表、背景存储路径或 LoRA 强度。")

    from src.database.core import AsyncSessionLocal
    from src.web_api.services.reference_asset_service import (
        normalize_reference_inputs,
        resolve_reference_set,
    )

    character_refs, environment_ref = normalize_reference_inputs(inputs)
    async with AsyncSessionLocal() as character_db:
        resolved = await resolve_reference_set(
            db=character_db,
            user_id=internal_user_id,
            character_refs=character_refs,
            environment_ref=environment_ref,
        )
    for key in (
        "character_ids",
        "background_object_key",
        "character_refs",
        "environment_ref",
    ):
        inputs.pop(key, None)
    inputs["character_sheets"] = list(resolved.character_sheets)
    inputs["character_descriptions"] = list(resolved.character_descriptions)
    inputs["background_image"] = resolved.environment_object_key


async def _resolve_h3_reference_inputs(
    inputs: dict[str, Any],
    *,
    internal_user_id: int,
    env_enabled: Callable[[str], bool],
) -> None:
    reference_refs = inputs.get("reference_refs")
    if reference_refs is None:
        return
    if inputs.get("images") not in (None, [], ()):
        raise CoreDomainError("H3 新旧参考图格式不能同时提交。")
    if inputs.get("reference_descriptions") not in (None, [], ()):
        raise CoreDomainError("人物参考说明只能由服务端生成。")
    uses_character_assets = any(
        isinstance(item, dict) and item.get("source") == "private_character_view"
        for item in reference_refs
    )
    if uses_character_assets and not env_enabled("CHARACTER_ASSETS_ENABLED"):
        raise CoreDomainError("人物身份素材功能当前未开放。")

    from src.database.core import AsyncSessionLocal
    from src.web_api.services.reference_asset_service import (
        resolve_h3_reference_refs,
    )

    async with AsyncSessionLocal() as character_db:
        resolved = await resolve_h3_reference_refs(
            db=character_db,
            user_id=internal_user_id,
            reference_refs=reference_refs,
            explicit_views_enabled=env_enabled("CHARACTER_EXPLICIT_VIEWS_ENABLED"),
        )
    inputs.pop("reference_refs", None)
    inputs["images"] = list(resolved.images)
    inputs["reference_descriptions"] = list(resolved.descriptions)


async def prepare_web_submission_request(
    req,
    *,
    internal_user_id: int,
    operator_canary_authorized: bool,
    env_enabled: Callable[[str], bool],
    advanced_video_profile_loader=None,
    prepare_h3_extension_func=None,
) -> PreparedWebSubmission:
    _assert_task_access(
        req.task_type,
        operator_canary_authorized=operator_canary_authorized,
        env_enabled=env_enabled,
    )
    inputs = dict(req.inputs)
    if req.task_type.startswith("minimax_h3_"):
        if inputs.get("reference_video") is not None:
            raise CoreDomainError("不得直接指定 H3 参考视频存储路径。")
        if advanced_video_profile_loader is None:
            from src.services.feature_entry_visibility_service import (
                load_advanced_video_pro_profile,
            )

            advanced_video_profile_loader = load_advanced_video_pro_profile
        profile = await advanced_video_profile_loader(
            req.task_type.removeprefix("minimax_h3_")
        )
        for key in (
            "addon_models",
            "lora_name",
            "lora_strength",
            "lora_items",
        ):
            inputs.pop(key, None)
        inputs["main_model"] = profile["main_model"]
        inputs["lora_items"] = list(profile["addon_items"])
        if inputs.get("reference_audio") is not None:
            raise CoreDomainError("不得直接指定主角参考语音存储路径。")
        reference_audio_ref = inputs.get("reference_audio_ref")
        if reference_audio_ref is not None:
            if req.task_type != "minimax_h3_ref2v":
                raise CoreDomainError("主角参考语音仅支持参考图生视频。")
            from src.web_api.services.reference_asset_service import (
                resolve_h3_reference_audio_ref,
            )

            inputs["reference_audio"] = await resolve_h3_reference_audio_ref(
                user_id=internal_user_id,
                reference_audio_ref=reference_audio_ref,
                source_post_id=req.source_post_id,
                is_template=req.is_template,
            )
            inputs.pop("reference_audio_ref", None)
    h3_extension_metadata: dict[str, Any] | None = None
    h3_allow_contribute: bool | None = None
    h3_prev_task_id = str(inputs.pop("minimax_h3_prev_task_id", "") or "").strip()
    if h3_prev_task_id:
        if not req.task_type.startswith("minimax_h3_"):
            raise CoreDomainError("扩展父任务仅支持 H3 视频生成。")
        if prepare_h3_extension_func is None:
            from src.services.minimax_h3_extension_service import (
                prepare_minimax_h3_web_extension,
            )

            prepare_h3_extension_func = prepare_minimax_h3_web_extension
        try:
            extension = await prepare_h3_extension_func(
                prev_task_id=h3_prev_task_id,
                internal_user_id=internal_user_id,
                target_task_type=req.task_type,
                client_images=list(inputs.get("images") or []),
            )
        except ValueError as exc:
            raise CoreDomainError(str(exc)) from exc
        inputs["images"] = list(extension.images)
        if extension.reference_video:
            inputs["reference_video"] = extension.reference_video
        if extension.aspect_ratio:
            inputs["aspect_ratio"] = extension.aspect_ratio
        h3_extension_metadata = dict(extension.metadata)
        h3_allow_contribute = bool(extension.allow_contribute)

    h3_character_binding = ""
    if req.negative_prompt:
        inputs["negative_prompt"] = req.negative_prompt
    if req.task_type == "character_reference_build":
        raise CoreDomainError("人物参考表只能通过人物图库构建接口创建。")
    if inputs.get("reference_refs") is not None:
        if req.task_type != "minimax_h3_ref2v":
            raise CoreDomainError("人物库参考图仅支持参考图生视频。")
        from src.web_api.services.reference_asset_service import (
            build_h3_character_reference_binding,
        )

        h3_character_binding = build_h3_character_reference_binding(
            inputs["reference_refs"]
        )
        await _resolve_h3_reference_inputs(
            inputs,
            internal_user_id=internal_user_id,
            env_enabled=env_enabled,
        )
    if req.task_type == "ltx_t2v_ic":
        await _resolve_ltx_character_inputs(
            inputs,
            internal_user_id=internal_user_id,
            env_enabled=env_enabled,
        )
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
        inputs["prompt"] = (
            f"{h3_character_binding}\n\nUser scene request:\n{req.prompt}"
            if h3_character_binding
            else req.prompt
        )
    return PreparedWebSubmission(
        inputs=inputs,
        images=images,
        is_template=bool(getattr(req, "is_template", False)),
        registry_metadata=h3_extension_metadata,
        allow_contribute_override=h3_allow_contribute,
    )


async def prepare_web_pipeline(
    *,
    task_type: str,
    inputs: dict[str, Any],
    images: list[str],
    internal_user_id: int,
    task_id: str,
    priority: int,
    is_template: bool,
    allow_contribute_override: bool | None,
    registry_metadata_extra: dict | None,
    prepare_scail2_first_frame: Callable[..., Awaitable[str]],
) -> PreparedWebPipeline:
    metadata = dict(registry_metadata_extra or {})
    final_allow_contribute = (
        bool(allow_contribute_override)
        if allow_contribute_override is not None
        else not is_template
    )
    if task_type == WEB_FREE_EDIT_V3_TASK_TYPE:
        metadata["_web_free_edit_v3"] = {
            "version": 1,
            "kind": "free_edit_v3",
            "stage": "bf16",
            "stage2_task_type": "face_swap_v2",
            "original_image": images[0],
            "final_allow_contribute": final_allow_contribute,
        }
        return PreparedWebPipeline(metadata)

    if task_type != SCAIL2_FACE_SWAP_V2_TASK_TYPE:
        return PreparedWebPipeline(metadata)
    if len(images) != 2:
        raise CoreDomainError("视频换脸需要上传参考图片和驱动视频。")
    first_frame = await prepare_scail2_first_frame(
        internal_user_id=internal_user_id,
        registry_task_id=task_id,
        motion_video_path=images[1],
    )
    inputs["_scail2_face_swap_first_frame"] = first_frame
    metadata["_web_scail2_face_swap_v2"] = {
        "version": 1,
        "kind": SCAIL2_FACE_SWAP_V2_TASK_TYPE,
        "stage": "face_swap_v2",
        "first_frame": first_frame,
        "original_reference": images[0],
        "motion_video": images[1],
        "duration": inputs.get("duration", 5),
        "normal_priority": priority,
        "final_allow_contribute": final_allow_contribute,
    }
    return PreparedWebPipeline(metadata, cleanup_object_key=first_frame)
