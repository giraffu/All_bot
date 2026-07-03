from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from src.constants import (
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    TASK_COSTS,
)
from src.lora_catalog import get_lora_default_strength
from src.services.qqcc_config_service import (
    DRAW_SCENE_ENGINE_FREE_EDIT,
    get_qqcc_draw_scene,
)


ProcessGenerationTask = Callable[..., Awaitable[tuple[bytes | None, str | None]]]
DownloadOutputFile = Callable[..., Awaitable[str]]


@dataclass(frozen=True)
class QQCCDrawChainResult:
    output_file: str | None = None
    local_output_path: str | None = None


def resolve_qqcc_draw_scene_task_type(scene: dict[str, object]) -> str:
    if scene.get("engine") == DRAW_SCENE_ENGINE_FREE_EDIT:
        return MODE_IMG2IMG_LORA if str(scene.get("lora_name") or "").strip() else MODE_EDIT
    return MODE_PORNMASTER_FLUX2_SINGLE_EDIT


def calculate_qqcc_draw_scene_cost(scene: dict[str, object] | None) -> int:
    if scene is None:
        return 0
    task_type = resolve_qqcc_draw_scene_task_type(scene)
    if task_type in (MODE_EDIT, MODE_IMG2IMG_LORA):
        return 2
    return TASK_COSTS.get(task_type, 2)


def resolve_qqcc_draw_scene_chain(
    config: dict[str, Any],
    scene_or_id: dict[str, object] | str | None,
) -> list[dict[str, Any]]:
    scene_id = (
        str(scene_or_id.get("id") or "").strip()
        if isinstance(scene_or_id, dict)
        else str(scene_or_id or "").strip()
    )
    chain: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    while scene_id and scene_id not in seen_ids:
        scene = get_qqcc_draw_scene(config, scene_id)
        if scene is None:
            break
        chain.append(scene)
        seen_ids.add(scene_id)
        scene_id = str(scene.get("postprocess_draw_scene_id") or "").strip()
    return chain


def calculate_qqcc_draw_chain_cost(chain: list[dict[str, object]]) -> int:
    return sum(calculate_qqcc_draw_scene_cost(scene) for scene in chain)


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
    keep_initial_image: bool = False,
    download_final_output: bool = False,
    name_hint: str = "qqcc_draw_chain",
) -> QQCCDrawChainResult:
    if not chain:
        return QQCCDrawChainResult()

    current_image_path = image_path
    for index, draw_scene in enumerate(chain):
        is_last = index == len(chain) - 1
        task_type = resolve_qqcc_draw_scene_task_type(draw_scene)
        lora_name = (
            str(draw_scene.get("lora_name") or "")
            if task_type == MODE_IMG2IMG_LORA
            else ""
        )
        send_result = final_send_result and is_last
        task_kwargs: dict[str, Any] = {
            "context": context,
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "prompt": str(draw_scene.get("prompt") or ""),
            "images": [current_image_path],
            "task_type": task_type,
            "status_msg_id": status_msg_id,
            "delete_status": final_delete_status if send_result else False,
            "cleanup": not (keep_initial_image and index == 0),
            "send_result": send_result,
            "allow_contribute": final_allow_contribute if send_result else False,
        }
        if send_result:
            task_kwargs["reply_markup"] = final_reply_markup
        if lora_name:
            task_kwargs["lora_name"] = lora_name
            task_kwargs["lora_strength"] = get_lora_default_strength(lora_name)

        _media_bytes, output_file = await process_generation_task_func(**task_kwargs)
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
