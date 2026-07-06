from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.handlers import command_handler


@pytest.mark.asyncio
async def test_cancel_uses_unified_fsm_cleanup(monkeypatch):
    cleanup = MagicMock()
    monkeypatch.setattr(command_handler, "cleanup_fsm_user_data", cleanup)
    monkeypatch.setattr(
        "src.i18n.keyboards.get_main_menu_keyboard",
        lambda _lang: "menu-keyboard",
    )
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=None,
        message=SimpleNamespace(reply_text=reply_text),
    )
    context = SimpleNamespace(
        lang="zh",
        t=lambda key: key,
        user_data={
            "in_conversation": "QUICK_IMAGE",
            "quick_image_data": {"image_path": "/tmp/a.png"},
        },
    )

    await command_handler.cancel(update, context)

    cleanup.assert_called_once_with(context.user_data)
    reply_text.assert_awaited_once()
