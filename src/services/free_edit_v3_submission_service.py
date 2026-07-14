"""Submission flow for the main Bot's upgraded Free Edit entry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable

from src.constants import MODE_PORNMASTER_FLUX2_EDIT_BF16
from src.services.wan22_video_v2_extension_service import (
    download_output_file_to_fsm_temp,
)


FREE_EDIT_V3_COST = 5
FACE_SWAP_PROMPT = "face swap"

ProcessGenerationTask = Callable[..., Awaitable[tuple[bytes | None, str | None]]]
DownloadOutputFile = Callable[..., Awaitable[str]]


async def process_free_edit_v3_task(
    *,
    context: Any,
    chat_id: int,
    user_id: int,
    username: str | None,
    prompt: str,
    image_path: str,
    process_generation_task_func: ProcessGenerationTask,
    download_output_file_to_fsm_temp_func: DownloadOutputFile = download_output_file_to_fsm_temp,
) -> None:
    """Run BF16 edit then restore the source face as one 5-credit operation."""
    _media_bytes, edited_output = await process_generation_task_func(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=prompt,
        images=[image_path],
        task_type=MODE_PORNMASTER_FLUX2_EDIT_BF16,
        cleanup=False,
        send_result=False,
        record_history=False,
        allow_contribute=False,
        cost_override=FREE_EDIT_V3_COST,
        base_priority=0,
        allow_cancel=True,
        user_cancel_allowed=True,
    )
    if not edited_output:
        return

    suffix = Path(str(edited_output)).suffix or ".png"
    edited_image_path = await download_output_file_to_fsm_temp_func(
        output_file=str(edited_output),
        suffix=suffix,
        name_hint="free_edit_v3_body",
    )
    await process_generation_task_func(
        context=context,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        prompt=FACE_SWAP_PROMPT,
        images=[edited_image_path, image_path],
        task_type="face_swap",
        cleanup=True,
        send_result=True,
        allow_contribute=True,
        deduct_quota=False,
        base_priority=100,
        allow_cancel=False,
        user_cancel_allowed=False,
        result_task_type=MODE_PORNMASTER_FLUX2_EDIT_BF16,
        result_prompt=prompt,
        result_input_image_indices=[1],
    )
