from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.advanced_video_prompt_optimizer_service import (
    optimize_advanced_video_prompt,
)


@pytest.mark.asyncio
async def test_bot_optimizer_stages_flf_frames_and_uses_shared_h3_contract():
    submit = AsyncMock(return_value={"task_id": "optimizer-1"})
    get_result = AsyncMock(return_value={"result_text": "optimized prompt"})
    remove = AsyncMock()
    uploads = iter(["staging/user-uploads/7/start.png", "staging/user-uploads/7/end.png"])

    result = await optimize_advanced_video_prompt(
        internal_user_id=7,
        username="alice",
        mode="flf2v",
        prompt="original",
        images=["/tmp/start.png", "/tmp/end.png"],
        duration_seconds=10,
        client_request_id="761206f6-50ed-437c-855a-af14544352f9",
        upload_image=lambda _path: next(uploads),
        submit_func=submit,
        get_result_func=get_result,
        remove_object_func=remove,
        sleep_func=AsyncMock(),
        get_balance=AsyncMock(return_value=9),
    )

    assert result == "optimized prompt"
    request = submit.await_args.kwargs["request"]
    assert request.target_task_type == "minimax_h3_flf2v"
    assert request.template.id == "minimax_h3_10eros_naughtytimes"
    assert request.template.version == 4
    assert [item.role for item in request.media] == ["start_image", "end_image"]
    assert request.context == {"duration_seconds": 10}
    assert request.lora_items == []
    assert submit.await_args.kwargs["current_user"] == SimpleNamespace(id=7, username="alice")
    assert remove.await_count == 2


@pytest.mark.asyncio
async def test_bot_optimizer_preserves_staged_media_until_terminal_result():
    get_result = AsyncMock(
        side_effect=[None, {"status": "failed", "refund_status": "refunded"}]
    )
    remove = AsyncMock()
    with pytest.raises(RuntimeError, match="refunded"):
        await optimize_advanced_video_prompt(
            internal_user_id=7,
            username=None,
            mode="i2v",
            prompt="original",
            images=["/tmp/start.png"],
            duration_seconds=5,
            client_request_id="761206f6-50ed-437c-855a-af14544352f9",
            upload_image=lambda _path: "staging/user-uploads/7/start.png",
            submit_func=AsyncMock(return_value={"task_id": "optimizer-1"}),
            get_result_func=get_result,
            remove_object_func=remove,
            sleep_func=AsyncMock(),
            get_balance=AsyncMock(return_value=9),
        )

    assert get_result.await_count == 2
    remove.assert_awaited_once()
