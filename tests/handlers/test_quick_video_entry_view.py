from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.handlers.fsm.quick_draw_callback_data import (
    build_quick_draw_v1_scene_callback_data,
)
from src.handlers.fsm.quick_video_entry_view import present_quick_video_entry
from src.services.qqcc_config_service import (
    SCENE_PRESET_VERSION,
    normalize_qqcc_config,
)
from src.services.quick_video_entry_service import build_quick_video_entry_plan


@pytest.mark.asyncio
async def test_v1_entry_view_uses_v1_draw_scene_for_jump_button():
    config = normalize_qqcc_config(
        {
            "scene_preset_version": SCENE_PRESET_VERSION,
            "main_buttons": {"video_edit_v1": True, "ai_draw_v1": True},
            "draw_scenes_v1": [
                {"id": "draw-v1", "name": "V1 输入图", "prompt": "draw prompt"}
            ],
            "video_scenes_v1": [
                {
                    "id": "video-v1",
                    "name": "V1 动图",
                    "prompt": "video prompt",
                    "duration": "5s",
                    "engine": "image_to_video",
                    "jump_draw_scene_id": "draw-v1",
                }
            ],
        }
    )
    plan = build_quick_video_entry_plan(
        mode=None,
        mode_name="",
        route_key=None,
        scene_id="video-v1",
        scene_kind="video_v1",
        qqcc_config=config,
    )
    reply_text = AsyncMock()

    async def await_interaction(awaitable, **_kwargs):
        return await awaitable

    await present_quick_video_entry(
        context=SimpleNamespace(
            bot=SimpleNamespace(id=999),
            bot_data={"bot_client_type": "bot:qqcc"},
            lang="zh",
            t=lambda key, **kwargs: (
                f"预计消耗：{kwargs['cost']} 灵石"
                if key == "fsm.common.estimated_cost"
                else key
            ),
        ),
        reply_message=SimpleNamespace(chat_id=123),
        plan=plan,
        reply_text_func=reply_text,
        interaction_io_func=await_interaction,
        demo_sender_func=AsyncMock(),
        ref2v_gallery_sender_func=AsyncMock(),
    )

    markup = reply_text.await_args.kwargs["reply_markup"]
    jump_button = markup.inline_keyboard[0][0]
    assert jump_button.text == "先去 AI绘图V1生成「V1 输入图」"
    assert jump_button.callback_data == build_quick_draw_v1_scene_callback_data(
        "draw-v1"
    )
