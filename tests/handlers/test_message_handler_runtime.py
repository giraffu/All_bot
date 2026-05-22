from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.handlers import message_handler_runtime


def test_normalize_supported_language_code_falls_back_to_zh():
    assert message_handler_runtime.normalize_supported_language_code(None) == "zh"
    assert message_handler_runtime.normalize_supported_language_code("ja") == "zh"
    assert message_handler_runtime.normalize_supported_language_code("en-US") == "en"


@pytest.mark.asyncio
async def test_toggle_user_language_persists_context_db_and_redis(monkeypatch):
    redis_get = AsyncMock(return_value=b"zh")
    redis_set = AsyncMock()
    fake_redis = SimpleNamespace(get=redis_get, set=redis_set)
    fake_redis_client = SimpleNamespace(redis=fake_redis)
    fake_internal_user = SimpleNamespace(id=321)
    fake_db_user = SimpleNamespace(language_code="zh")

    class _FakeSession:
        def __init__(self):
            self.commit = AsyncMock()

        async def get(self, _model_cls, user_id):
            assert user_id == 321
            return fake_db_user

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_session = _FakeSession()
    context = SimpleNamespace(user_data={}, t=None)
    user = SimpleNamespace(
        id=123,
        username="dao",
        full_name="道友",
        language_code="zh-CN",
    )

    monkeypatch.setattr(
        "src.services.redis_client.redis_client",
        fake_redis_client,
    )
    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(fake_internal_user, True)),
    )
    monkeypatch.setattr(
        "src.database.core.AsyncSessionLocal",
        lambda: fake_session,
    )
    monkeypatch.setattr(
        "src.i18n.translator.I18nTranslator",
        lambda lang: f"translator:{lang}",
    )
    monkeypatch.setattr(
        "src.i18n.keyboards.get_main_menu_keyboard",
        lambda lang: f"keyboard:{lang}",
    )

    msg, reply_markup = await message_handler_runtime.toggle_user_language(context, user)

    assert msg == "🌐 Language switched to English."
    assert reply_markup == "keyboard:en"
    assert context.user_data["language_code"] == "en"
    assert context.t == "translator:en"
    assert fake_db_user.language_code == "en"
    fake_session.commit.assert_awaited_once()
    redis_get.assert_awaited_once_with("allbot:user_lang:tg:123")
    assert redis_set.await_args_list[0].args == ("allbot:user_lang:321", "en")
    assert redis_set.await_args_list[1].args == ("allbot:user_lang:tg:123", "en")


@pytest.mark.asyncio
async def test_get_queue_status_reply_handles_success_and_unavailable(monkeypatch):
    context = SimpleNamespace(t=lambda key: f"T:{key}")

    monkeypatch.setattr(
        message_handler_runtime.image_service,
        "get_queue_info",
        AsyncMock(
            side_effect=[
                {"queue_size": 2, "queue_by_type": {"img2img": 1, "custom_x": 1}},
                None,
            ]
        ),
    )

    text = await message_handler_runtime.get_queue_status_reply(
        context,
        {"img2img": "task.img2img"},
    )
    unavailable = await message_handler_runtime.get_queue_status_reply(
        context,
        {"img2img": "task.img2img"},
    )

    assert "总排队任务：`2` 个" in text
    assert "T:task.img2img：`1` 个" in text
    assert "❓ 其他 (custom\\_x)：`1` 个" in text
    assert unavailable == "⚠️ 无法获取实时排队数据，请稍后再试。"


@pytest.mark.asyncio
async def test_get_checkin_gate_reply_returns_refuge_payload_for_non_members():
    context = SimpleNamespace(
        bot=SimpleNamespace(
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left"))
        )
    )
    update = SimpleNamespace(effective_user=SimpleNamespace(id=123))

    result = await message_handler_runtime.get_checkin_gate_reply(
        update,
        context,
        "-100123",
    )

    assert result is not None
    assert "避难所签到检测" in result[0]
    assert result[1] is not None


@pytest.mark.asyncio
async def test_build_checkin_reply_handles_success_repeat_and_error(monkeypatch):
    fake_internal_user = SimpleNamespace(id=321)
    user = SimpleNamespace(id=123, username="dao", full_name="道友")
    context = SimpleNamespace(bot="bot")
    reward_coro = object()
    background_task_mock = MagicMock()

    monkeypatch.setattr(
        "src.core.user_core.get_or_create_user_by_telegram",
        AsyncMock(return_value=(fake_internal_user, True)),
    )
    monkeypatch.setattr(
        message_handler_runtime,
        "get_user_channel_status",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        message_handler_runtime.permission_service,
        "sync_channel_status",
        AsyncMock(return_value=456),
    )
    monkeypatch.setattr(
        message_handler_runtime,
        "notify_inviter_reward",
        lambda bot, inviter_id, full_name: reward_coro,
    )
    monkeypatch.setattr(
        message_handler_runtime,
        "create_background_task",
        background_task_mock,
    )
    monkeypatch.setattr(
        message_handler_runtime.permission_service,
        "get_user_group",
        AsyncMock(return_value="筑基期"),
    )
    monkeypatch.setattr(
        message_handler_runtime.permission_service,
        "get_user_identity",
        AsyncMock(return_value="核心弟子"),
    )

    perform_checkin = AsyncMock(
        side_effect=[
            (True, 88, "", 7, 5),
            (False, 88, "", 7, 0),
            (False, 88, "业务错误", 7, 0),
        ]
    )
    monkeypatch.setattr(
        message_handler_runtime.permission_service,
        "perform_checkin",
        perform_checkin,
    )

    update = SimpleNamespace(effective_user=user)

    success_text = await message_handler_runtime.build_checkin_reply(update, context)
    repeat_text = await message_handler_runtime.build_checkin_reply(update, context)
    error_text = await message_handler_runtime.build_checkin_reply(update, context)

    assert "签到成功" in success_text
    assert "当前总灵石：`88`" in success_text
    assert "今日已领取灵石" in repeat_text
    assert error_text == "业务错误"
    background_task_mock.assert_called()


@pytest.mark.asyncio
async def test_build_personal_center_reply_syncs_status_and_builds_payload(monkeypatch):
    user = SimpleNamespace(
        id=123,
        username="dao",
        full_name="道友",
        first_name="Tester",
        language_code="zh",
    )
    context = SimpleNamespace(bot="bot")
    fake_dto = SimpleNamespace(current_group="练气期")
    monkeypatch.setattr(
        message_handler_runtime,
        "get_user_channel_status",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        message_handler_runtime.permission_service,
        "sync_channel_status",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        message_handler_runtime.permission_service,
        "ensure_user",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "src.core.user_facade.get_user_dashboard_info",
        AsyncMock(return_value=fake_dto),
    )
    monkeypatch.setattr(
        message_handler_runtime,
        "build_personal_center_payload",
        lambda dto, *, invite_link, web_url: (
            f"profile:{dto.current_group}:{invite_link}:{web_url}",
            "profile-keyboard",
        ),
    )

    msg, reply_markup = await message_handler_runtime.build_personal_center_reply(
        context,
        user,
        invite_link="https://invite.example",
        web_url="https://web.example",
    )

    assert msg == "profile:练气期:https://invite.example:https://web.example"
    assert reply_markup == "profile-keyboard"


@pytest.mark.asyncio
async def test_build_share_reply_prefers_cached_bot_username_and_builds_payload(monkeypatch):
    context = SimpleNamespace(bot=SimpleNamespace(username="aivision666_bot"))
    user = SimpleNamespace(id=123, first_name="Tester")
    fake_dto = SimpleNamespace(invitations=2)

    monkeypatch.setattr(
        "src.core.user_facade.get_user_dashboard_info",
        AsyncMock(return_value=fake_dto),
    )
    monkeypatch.setattr(
        message_handler_runtime,
        "build_share_payload",
        lambda dto, *, invite_link: (f"share:{dto.invitations}:{invite_link}", "share-keyboard"),
    )

    msg, reply_markup = await message_handler_runtime.build_share_reply(context, user)

    assert msg == "share:2:https://t.me/aivision666_bot?start=123"
    assert reply_markup == "share-keyboard"


@pytest.mark.asyncio
async def test_build_share_reply_falls_back_to_get_me_when_username_missing(monkeypatch):
    context = SimpleNamespace(
        bot=SimpleNamespace(
            username=None,
            get_me=AsyncMock(return_value=SimpleNamespace(username="fallback_bot")),
        )
    )
    user = SimpleNamespace(id=456, first_name="Tester")

    monkeypatch.setattr(
        "src.core.user_facade.get_user_dashboard_info",
        AsyncMock(return_value=SimpleNamespace(invitations=1)),
    )
    monkeypatch.setattr(
        message_handler_runtime,
        "build_share_payload",
        lambda dto, *, invite_link: (invite_link, "share-keyboard"),
    )

    msg, reply_markup = await message_handler_runtime.build_share_reply(context, user)

    assert msg == "https://t.me/fallback_bot?start=456"
    assert reply_markup == "share-keyboard"
    context.bot.get_me.assert_awaited_once()
