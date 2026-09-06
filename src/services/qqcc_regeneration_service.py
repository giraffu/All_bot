from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from src.constants import (
    MODE_RANDOM_FACESWAP,
)
from src.database.core import AsyncSessionLocal
from src.database.models import History
from src.domain_config.minimax_h3 import MINIMAX_H3_REF2V
from src.services.permission_service import permission_service
from src.services.fsm_temp_file_service import cleanup_fsm_temp_files
from src.services.qqcc_config_service import (
    VIDEO_DURATION_KEYS,
    VIDEO_RESOLUTION_KEYS,
    get_qqcc_ai_video_scene,
    load_runtime_qqcc_config,
)
from src.services.qqcc_regenerate_metadata import (
    QQCC_REGENERATE_KIND_QUICK_IMAGE,
    QQCC_REGENERATE_KIND_QUICK_VIDEO,
    extract_qqcc_regenerate_context,
)
from src.services.quick_image_submission_service import (
    QuickImageSubmissionPlan,
    QuickImageSubmissionReject,
    build_quick_image_submission_plan,
    list_quick_faceswap_template_files,
)
from src.services.quick_video_submission_service import (
    QuickVideoSubmissionPlan,
    QuickVideoSubmissionReject,
    build_quick_video_submission_plan,
)
from src.services.telegram_identity_service import (
    resolve_internal_user_id_for_telegram as resolve_internal_user_id_from_telegram,
)
from src.services.wan22_video_v2_extension_service import (
    download_output_file_to_fsm_temp,
    resolve_history_input_files,
)
from src.utils import load_prompts


class QQCCRegenerationError(Exception):
    """Raised when a QQCC result cannot be regenerated from history."""


@dataclass(frozen=True)
class QQCCRegenerationSubmission:
    kind: str
    display_mode_name: str
    image_path: str
    plan: QuickImageSubmissionPlan | QuickVideoSubmissionPlan

    @property
    def total_cost(self) -> int:
        return self.plan.total_cost


LoadOwnedHistoryFunc = Callable[..., Awaitable[History]]


async def load_owned_qqcc_regenerable_history(
    *,
    task_id: str,
    telegram_user_id: int,
    username: str | None,
) -> History:
    internal_user_id = await resolve_internal_user_id_from_telegram(
        telegram_user_id,
        username,
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(History).where(
                History.task_id == task_id,
                History.user_id == internal_user_id,
            )
        )
        history = result.scalar_one_or_none()
    if history is None:
        raise QQCCRegenerationError("未找到对应记录，或该记录不属于您。")
    return history


def merge_qqcc_regenerate_context_into_meta(
    history: History,
    message_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    history_meta = (
        getattr(history, "extra_outputs", None)
        if isinstance(getattr(history, "extra_outputs", None), dict)
        else {}
    )
    return {
        **extract_qqcc_regenerate_context(history_meta),
        **extract_qqcc_regenerate_context(message_meta),
    }


def resolve_qqcc_regenerate_display_name(meta: dict[str, Any], history: History) -> str:
    return (
        str(meta.get("display_mode_name") or "").strip()
        or str(getattr(history, "type", "") or "").strip()
        or "当前功能"
    )


async def download_history_input_file_to_fsm_temp(
    *,
    history: History,
    index: int,
    name_hint: str,
) -> str:
    input_files = resolve_history_input_files(history)
    try:
        output_file = input_files[index]
    except IndexError as exc:
        raise QQCCRegenerationError("这条记录缺少可复用的原始图片。") from exc
    suffix = Path(output_file).suffix or ".png"
    if output_file.startswith("template:"):
        raise QQCCRegenerationError("这条记录缺少可复用的用户原图。")
    return await download_output_file_to_fsm_temp(
        output_file=output_file,
        suffix=suffix,
        name_hint=name_hint,
    )


async def resolve_allowed_quick_video_resolutions(
    *,
    telegram_user_id: int,
    username: str | None,
) -> list[str]:
    internal_user_id = await resolve_internal_user_id_from_telegram(
        telegram_user_id,
        username,
    )
    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    resolutions, _durations = await permission_service.get_video_permissions(
        internal_user_id,
        user_group=user_group,
        user_identity=user_identity,
    )
    return [res for res in VIDEO_RESOLUTION_KEYS if res in resolutions]


def _resolve_regeneration_image_index(meta: dict[str, Any]) -> int:
    return 1 if meta.get("mode") == MODE_RANDOM_FACESWAP else 0


def _coerce_quick_video_duration(history: History) -> str:
    raw_duration = getattr(history, "requested_duration", None) or getattr(
        history,
        "duration",
        None,
    )
    try:
        duration = int(raw_duration)
    except (TypeError, ValueError):
        return "5s"
    normalized = f"{duration}s"
    return normalized if normalized in VIDEO_DURATION_KEYS else "5s"


async def prepare_qqcc_regeneration_submission(
    *,
    task_id: str,
    telegram_user_id: int,
    username: str | None,
    message_meta: dict[str, Any] | None = None,
    load_history_func: LoadOwnedHistoryFunc = load_owned_qqcc_regenerable_history,
    load_config_func: Callable[[], Awaitable[dict[str, Any]]] = load_runtime_qqcc_config,
) -> QQCCRegenerationSubmission:
    history = await load_history_func(
        task_id=task_id,
        telegram_user_id=telegram_user_id,
        username=username,
    )
    meta = merge_qqcc_regenerate_context_into_meta(history, message_meta)
    kind = str(meta.get("kind") or "").strip()
    mode = str(meta.get("mode") or "").strip()
    if kind not in {QQCC_REGENERATE_KIND_QUICK_IMAGE, QQCC_REGENERATE_KIND_QUICK_VIDEO}:
        raise QQCCRegenerationError("这条结果暂不支持重新生成。")
    if not mode:
        raise QQCCRegenerationError("这条结果缺少可重建的功能信息。")

    qqcc_config = await load_config_func()
    display_mode_name = resolve_qqcc_regenerate_display_name(meta, history)
    if kind == QQCC_REGENERATE_KIND_QUICK_IMAGE:
        image_path = await download_history_input_file_to_fsm_temp(
            history=history,
            index=_resolve_regeneration_image_index(meta),
            name_hint="qqcc_regenerate_image",
        )
        try:
            plan = build_quick_image_submission_plan(
                fsm_data={
                    "mode": mode,
                    "scene_id": meta.get("scene_id"),
                    "scene_kind": meta.get("scene_kind"),
                },
                qqcc_config=qqcc_config,
                image_path=image_path,
                prompts_config=load_prompts(),
                template_files=(
                    list_quick_faceswap_template_files()
                    if mode == MODE_RANDOM_FACESWAP
                    else None
                ),
            )
        except Exception:
            cleanup_fsm_temp_files([image_path])
            raise
        if isinstance(plan, QuickImageSubmissionReject):
            cleanup_fsm_temp_files([image_path])
            raise QQCCRegenerationError("功能暂未开放或配置已变更。")
        return QQCCRegenerationSubmission(
            kind=kind,
            display_mode_name=plan.display_mode_name or display_mode_name,
            image_path=image_path,
            plan=plan,
        )

    image_path = await download_history_input_file_to_fsm_temp(
        history=history,
        index=0,
        name_hint="qqcc_regenerate_video",
    )
    reference_image_paths: list[str] = []
    if mode == MINIMAX_H3_REF2V:
        scene = get_qqcc_ai_video_scene(qqcc_config, meta.get("scene_id"))
        reference_images = list(scene.get("reference_images") or []) if scene else []
        input_files = resolve_history_input_files(history)
        if not 1 <= len(reference_images) <= 4 or len(input_files) != 1 + len(
            reference_images
        ):
            cleanup_fsm_temp_files([image_path])
            raise QQCCRegenerationError(
                "这条记录缺少完整的参考模板组，无法按原输入重新生成。"
            )
        try:
            for index in range(len(reference_images)):
                reference_image_paths.append(
                    await download_history_input_file_to_fsm_temp(
                        history=history,
                        index=index + 1,
                        name_hint=f"qqcc_regenerate_ref2v_template_{index + 1}",
                    )
                )
        except Exception:
            cleanup_fsm_temp_files([image_path, *reference_image_paths])
            raise
    try:
        plan = build_quick_video_submission_plan(
            fsm_data={
                "mode": mode,
                "scene_id": meta.get("scene_id"),
                "scene_kind": meta.get("scene_kind"),
                "resolution": getattr(history, "billing_resolution", None) or "512p",
                "duration": _coerce_quick_video_duration(history),
                "selected_reference_image": meta.get("selected_reference_image"),
                "selected_reference_name": meta.get("selected_reference_name"),
                "reference_image_replacement_paths": {
                    str(index): path
                    for index, path in enumerate(reference_image_paths)
                },
            },
            qqcc_config=qqcc_config,
            allowed_resolutions=None,
        )
    except Exception:
        cleanup_fsm_temp_files([image_path, *reference_image_paths])
        raise
    if isinstance(plan, QuickVideoSubmissionReject):
        cleanup_fsm_temp_files([image_path, *reference_image_paths])
        raise QQCCRegenerationError("功能暂未开放或配置已变更。")
    return QQCCRegenerationSubmission(
        kind=kind,
        display_mode_name=plan.display_mode_name or display_mode_name,
        image_path=image_path,
        plan=plan,
    )
