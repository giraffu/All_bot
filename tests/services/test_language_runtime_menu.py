from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.services import main_bot_menu_runtime
from src.services.language_runtime_service import toggle_user_language_runtime


class _Session:
    def __init__(self):
        self.user = SimpleNamespace(language_code="zh")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, _model, _user_id):
        return self.user

    async def commit(self):
        return None


@pytest.mark.asyncio
async def test_language_toggle_uses_latest_runtime_main_menu(monkeypatch):
    runtime_keyboard = AsyncMock(return_value="runtime-menu")
    monkeypatch.setattr(
        main_bot_menu_runtime,
        "get_runtime_main_menu_keyboard",
        runtime_keyboard,
    )
    internal_user = SimpleNamespace(id=9)

    result = await toggle_user_language_runtime(
        telegram_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Tester",
            language_code="zh",
        ),
        cached_language_code="zh",
        redis_client_obj=SimpleNamespace(redis=None),
        get_or_create_user_by_telegram_func=AsyncMock(
            return_value=(internal_user, False)
        ),
        session_factory=_Session,
        user_model=object(),
        translator_factory=lambda lang: f"translator:{lang}",
    )

    assert result.new_lang == "en"
    assert result.reply_markup == "runtime-menu"
    runtime_keyboard.assert_awaited_once_with("en")
