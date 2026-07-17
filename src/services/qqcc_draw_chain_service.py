from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from src.constants import (
    MODE_FACE_SWAP_V2,
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_EDIT_BF16,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    TASK_COSTS,
)
from src.lora_catalog import get_lora_default_strength
from src.services.fsm_temp_file_service import cleanup_fsm_temp_files
from src.services.qqcc_config_service import (
    DRAW_SCENE_ENGINE_FREE_EDIT,
    DRAW_SCENE_ENGINE_FREE_EDIT_V3,
    get_qqcc_draw_scene,
    get_qqcc_filter_scene,
)


ProcessGenerationTask = Callable[..., Awaitable[tuple[bytes | None, str | None]]]
DownloadOutputFile = Callable[..., Awaitable[str]]


@dataclass(frozen=True)
class QQCCDrawChainResult:
    output_file: str | None = None
    local_output_path: str | None = None


QQCC_ORIGINAL_FACE_SWAP_COST = 2
QQCC_ORIGINAL_FACE_SWAP_PROMPT = "face swap"
QQCC_CHAIN_CONTINUATION_BASE_PRIORITY = 100
QQCC_SCENE_KIND_DRAW = "draw"
QQCC_SCENE_KIND_FILTER = "filter"
QQCC_SCENE_KIND_KEY = "_qqcc_scene_kind"


def build_qqcc_chain_task_controls(subtask_index: int) -> dict[str, object]:
    is_first = subtask_index == 0
    return {
        "base_priority": 0 if is_first else QQCC_CHAIN_CONTINUATION_BASE_PRIORITY,
        "allow_cancel": is_first,
        "user_cancel_allowed": is_first,
        "show_queue_status": is_first,
    }


def is_qqcc_original_face_swap_enabled(scene: dict[str, object] | None) -> bool:
    return bool(scene and scene.get("original_face_swap_enabled") is True)


def resolve_qqcc_draw_scene_task_type(scene: dict[str, object]) -> str:
    if scene.get("engine") == DRAW_SCENE_ENGINE_FREE_EDIT:
        return MODE_IMG2IMG_LORA if str(scene.get("lora_name") or "").strip() else MODE_EDIT
    if scene.get("engine") == DRAW_SCENE_ENGINE_FREE_EDIT_V3:
        return MODE_PORNMASTER_FLUX2_EDIT_BF16
    return MODE_PORNMASTER_FLUX2_SINGLE_EDIT


def calculate_qqcc_draw_scene_cost(scene: dict[str, object] | None) -> int:
    if scene is None:
        return 0
    task_type = resolve_qqcc_draw_scene_task_type(scene)
    draw_cost = (
        2
        if task_type in (MODE_EDIT, MODE_IMG2IMG_LORA)
        else TASK_COSTS.get(task_type, 2)
    )
    if is_qqcc_original_face_swap_enabled(scene):
        return draw_cost + QQCC_ORIGINAL_FACE_SWAP_COST
    return draw_cost


def _with_scene_kind(scene: dict[str, Any], scene_kind: str) -> dict[str, Any]:
    return {**scene, QQCC_SCENE_KIND_KEY: scene_kind}


def resolve_qqcc_draw_scene_chain(
    config: dict[str, Any],
    scene_or_id: dict[str, object] | str | None,
    *,
    scene_kind: str = QQCC_SCENE_KIND_DRAW,
) -> list[dict[str, Any]]:
    scene_id = (
        str(scene_or_id.get("id") or "").strip()
        if isinstance(scene_or_id, dict)
        else str(scene_or_id or "").strip()
    )
    if isinstance(scene_or_id, dict):
        raw_scene_kind = str(scene_or_id.get(QQCC_SCENE_KIND_KEY) or "").strip()
        if raw_scene_kind:
            scene_kind = raw_scene_kind

    if scene_kind == QQCC_SCENE_KIND_FILTER:
        scene = get_qqcc_filter_scene(config, scene_id)
        return [_with_scene_kind(scene, QQCC_SCENE_KIND_FILTER)] if scene else []

    chain: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    while scene_id and scene_id not in seen_ids:
        scene = get_qqcc_draw_scene(config, scene_id)
        if scene is None:
            break
        chain.append(_with_scene_kind(scene, QQCC_SCENE_KIND_DRAW))
        seen_ids.add(scene_id)
        filter_scene_id = str(scene.get("postprocess_filter_scene_id") or "").strip()
        if filter_scene_id:
            filter_scene = get_qqcc_filter_scene(config, filter_scene_id)
            if filter_scene is not None:
                chain.append(_with_scene_kind(filter_scene, QQCC_SCENE_KIND_FILTER))
            break
        scene_id = str(scene.get("postprocess_draw_scene_id") or "").strip()
    return chain


def calculate_qqcc_draw_chain_cost(chain: list[dict[str, object]]) -> int:
    return sum(calculate_qqcc_draw_scene_cost(scene) for scene in chain)


def resolve_qqcc_draw_scene_prompt(
    _config: dict[str, Any],
    scene: dict[str, object],
    _prompts_config: dict[str, str] | None = None,
) -> str:
    return str(scene.get("prompt") or "").strip()


def resolve_qqcc_draw_chain_prompts(
    config: dict[str, Any],
    chain: list[dict[str, Any]],
    prompts_config: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            **scene,
            "prompt": resolve_qqcc_draw_scene_prompt(
                config,
                scene,
                prompts_config,
            ),
        }
        for scene in chain
    ]


async def execute_qqcc_draw_scene_chain(
    *,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str | None,
    image_path: str,
    chain: list[dict[str, object]],
    status_msg_id: int | None,
    process_generation_task_func: ProcessGenerationTask,
    download_output_file_to_fsm_temp_func: DownloadOutputFile,
    final_send_result: bool,
    final_allow_contribute: bool,
    final_delete_status: bool = True,
    final_reply_markup: Any = None,
    final_display_mode_name: str | None = None,
    final_result_meta: dict[str, Any] | None = None,
    keep_initial_image: bool = False,
    download_final_output: bool = False,
    name_hint: str = "qqcc_draw_chain",
) -> QQCCDrawChainResult:
    if not chain:
        return QQCCDrawChainResult()

    current_image_path = image_path
    original_face_image_path = image_path
    submitted_subtask_index = 0
    for index, draw_scene in enumerate(chain):
        is_last = index == len(chain) - 1
        original_face_swap_enabled = is_qqcc_original_face_swap_enabled(draw_scene)
        original_needed_from_draw = (
            current_image_path == original_face_image_path
            and any(is_qqcc_original_face_swap_enabled(scene) for scene in chain[index:])
        )
        original_needed_after_face_swap = keep_initial_image or any(
            is_qqcc_original_face_swap_enabled(scene) for scene in chain[index + 1 :]
        )
        task_type = resolve_qqcc_draw_scene_task_type(draw_scene)
        lora_name = (
            str(draw_scene.get("lora_name") or "")
            if task_type == MODE_IMG2IMG_LORA
            else ""
        )
        send_result = final_send_result and is_last and not original_face_swap_enabled
        task_kwargs: dict[str, Any] = {
            "context": context,
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "prompt": str(draw_scene.get("prompt") or ""),
            "negative_prompt": str(draw_scene.get("negative_prompt") or ""),
            "images": [current_image_path],
            "task_type": task_type,
            "status_msg_id": status_msg_id,
            "delete_status": final_delete_status if send_result else False,
            "cleanup": not (
                (keep_initial_image and index == 0) or original_needed_from_draw
            ),
            "send_result": send_result,
            "allow_contribute": final_allow_contribute if send_result else False,
        }
        task_kwargs.update(build_qqcc_chain_task_controls(submitted_subtask_index))
        if send_result:
            task_kwargs["reply_markup"] = final_reply_markup
            if final_display_mode_name:
                task_kwargs["display_mode_name_override"] = final_display_mode_name
            if final_result_meta is not None:
                task_kwargs["result_meta"] = final_result_meta
        if lora_name:
            task_kwargs["lora_name"] = lora_name
            task_kwargs["lora_strength"] = get_lora_default_strength(lora_name)

        _media_bytes, output_file = await process_generation_task_func(**task_kwargs)
        submitted_subtask_index += 1
        if not output_file:
            return QQCCDrawChainResult()

        output_file = str(output_file)
        if is_last and not download_final_output and not original_face_swap_enabled:
            return QQCCDrawChainResult(output_file=output_file)

        suffix = Path(output_file).suffix or ".png"
        current_image_path = await download_output_file_to_fsm_temp_func(
            output_file=output_file,
            suffix=suffix,
            name_hint=name_hint,
        )
        if original_face_swap_enabled:
            face_swap_body_path = current_image_path
            face_swap_send_result = final_send_result and is_last
            face_swap_kwargs: dict[str, Any] = {
                "context": context,
                "chat_id": chat_id,
                "user_id": user_id,
                "username": username,
                "prompt": QQCC_ORIGINAL_FACE_SWAP_PROMPT,
                "images": [current_image_path, original_face_image_path],
                "task_type": MODE_FACE_SWAP_V2,
                "status_msg_id": status_msg_id,
                "delete_status": (
                    final_delete_status if face_swap_send_result else False
                ),
                "cleanup": not original_needed_after_face_swap,
                "send_result": face_swap_send_result,
                "allow_contribute": (
                    final_allow_contribute if face_swap_send_result else False
                ),
                "cost_override": QQCC_ORIGINAL_FACE_SWAP_COST,
            }
            face_swap_kwargs.update(
                build_qqcc_chain_task_controls(submitted_subtask_index)
            )
            if face_swap_send_result:
                face_swap_kwargs["reply_markup"] = final_reply_markup
                face_swap_kwargs["result_task_type"] = task_type
                face_swap_kwargs["result_prompt"] = str(draw_scene.get("prompt") or "")
                face_swap_kwargs["result_input_image_indices"] = [1]
                if final_display_mode_name:
                    face_swap_kwargs["display_mode_name_override"] = final_display_mode_name
                if final_result_meta is not None:
                    face_swap_kwargs["result_meta"] = final_result_meta

            _media_bytes, output_file = await process_generation_task_func(
                **face_swap_kwargs
            )
            submitted_subtask_index += 1
            if (
                original_needed_after_face_swap
                and face_swap_body_path != original_face_image_path
            ):
                cleanup_fsm_temp_files([face_swap_body_path])
            if not output_file:
                return QQCCDrawChainResult()

            output_file = str(output_file)
            if is_last and not download_final_output:
                return QQCCDrawChainResult(output_file=output_file)

            suffix = Path(output_file).suffix or ".png"
            current_image_path = await download_output_file_to_fsm_temp_func(
                output_file=output_file,
                suffix=suffix,
                name_hint=name_hint,
            )
        if is_last:
            return QQCCDrawChainResult(
                output_file=output_file,
                local_output_path=current_image_path,
            )

    return QQCCDrawChainResult()
