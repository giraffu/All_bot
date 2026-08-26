from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services.advanced_video_prompt_task_service import (
    deliver_advanced_video_prompt_result,
    start_advanced_video_prompt_task,
)


@pytest.mark.asyncio
async def test_start_prompt_task_checkpoints_before_submission_and_freezes_generation_settings():
    events = []
    saved = []

    async def save(draft, *, monitor=True):
        events.append(("save", draft.status))
        saved.append(draft)

    async def upload(path, object_key):
        events.append(("upload", path, object_key))
        return True

    async def submit(**kwargs):
        events.append(("submit", kwargs["object_keys"]))
        return "optimizer-1"

    draft = await start_advanced_video_prompt_task(
        token="draft-token",
        internal_user_id=77,
        telegram_user_id=7007,
        username="alice",
        chat_id=99,
        language="zh",
        client_request_id="request-id",
        mode="i2v",
        original_prompt="original",
        image_paths=["/tmp/start.png"],
        duration=10,
        resolution_preset="hd",
        aspect_ratio="source",
        addon_models=["breasts"],
        reference_descriptions=[],
        generation_cost=60,
        addon_items=[{"name": "breasts", "strength": 1.35}],
        save_draft=save,
        upload_object=upload,
        submit_optimizer=submit,
        now=lambda: 100.0,
    )

    assert events[0] == ("save", "staging")
    assert events[-2][0] == "submit"
    assert events[-1] == ("save", "submitted")
    assert draft.optimizer_task_id == "optimizer-1"
    assert draft.resolution_preset == "hd"
    assert draft.addon_models == ("breasts",)
    assert draft.addon_items == ({"name": "breasts", "strength": 1.35},)
    assert draft.object_keys[0].startswith("staging/user-uploads/77/")


@pytest.mark.asyncio
async def test_delivery_sends_new_result_message_with_action_button_after_fsm_is_gone():
    store = SimpleNamespace(save=AsyncMock(), stop_monitoring=AsyncMock())
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=501)))
    draft = SimpleNamespace(
        token="draft-token",
        chat_id=99,
        language="zh",
        original_prompt="original",
        optimized_prompt=None,
        status="submitted",
        created_at=100.0,
        running_at=105.0,
        optimizer_task_id="optimizer-1",
        with_updates=lambda **changes: SimpleNamespace(
            token="draft-token",
            chat_id=99,
            language="zh",
            original_prompt="original",
            optimized_prompt=changes.get("optimized_prompt"),
            status=changes.get("status", "ready"),
            created_at=100.0,
            running_at=105.0,
            completed_at=changes.get("completed_at"),
            delivered_message_ids=changes.get("delivered_message_ids", ()),
            with_updates=lambda **_more: None,
        ),
    )

    result = await deliver_advanced_video_prompt_result(
        draft,
        result_text="optimized prompt",
        bot=bot,
        store=store,
        now=lambda: 112.0,
    )

    assert result.status == "ready"
    assert result.optimized_prompt == "optimized prompt"
    assert bot.send_message.await_count == 1
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 99
    assert "总耗时 12.0 秒" in kwargs["text"]
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.callback_data == "avpopt_prepare:draft-token"
    store.stop_monitoring.assert_awaited_once_with("draft-token")
