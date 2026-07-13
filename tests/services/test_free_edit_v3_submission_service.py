from unittest.mock import AsyncMock

import pytest

from src.constants import MODE_PORNMASTER_FLUX2_EDIT_BF16
from src.services.free_edit_v3_submission_service import (
    FREE_EDIT_V3_COST,
    process_free_edit_v3_task,
)


@pytest.mark.asyncio
async def test_free_edit_v3_runs_bf16_then_face_swap_with_one_charge():
    process_task = AsyncMock(
        side_effect=[(None, "outputs/edited.png"), (None, "outputs/final.png")]
    )
    download = AsyncMock(return_value="/tmp/edited.png")

    await process_free_edit_v3_task(
        context=object(),
        chat_id=12,
        user_id=34,
        username="tester",
        prompt="make it cinematic",
        image_path="/tmp/source.png",
        process_generation_task_func=process_task,
        download_output_file_to_fsm_temp_func=download,
    )

    bf16_call, face_swap_call = process_task.await_args_list
    assert bf16_call.kwargs["task_type"] == MODE_PORNMASTER_FLUX2_EDIT_BF16
    assert bf16_call.kwargs["cost_override"] == FREE_EDIT_V3_COST
    assert bf16_call.kwargs["send_result"] is False
    assert face_swap_call.kwargs["task_type"] == "face_swap"
    assert face_swap_call.kwargs["images"] == ["/tmp/edited.png", "/tmp/source.png"]
    assert face_swap_call.kwargs["deduct_quota"] is False
    assert face_swap_call.kwargs["result_task_type"] == MODE_PORNMASTER_FLUX2_EDIT_BF16
    assert face_swap_call.kwargs["result_prompt"] == "make it cinematic"
