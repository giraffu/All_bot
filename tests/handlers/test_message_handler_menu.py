from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.handlers import message_handler_menu


def _build_context(lang: str = "zh"):
    return SimpleNamespace(lang=lang, t=lambda key: f"translated:{key}")


@pytest.mark.asyncio
async def test_build_photo_edit_payload_uses_context_translation(monkeypatch):
    keyboard_builder = AsyncMock(return_value="photo-keyboard")
    monkeypatch.setattr(
        message_handler_menu,
        "get_runtime_photo_edit_keyboard",
        keyboard_builder,
    )

    photo_msg, photo_keyboard = await message_handler_menu.build_photo_edit_payload(
        _build_context()
    )

    assert photo_msg == "translated:system.photo_edit_hint"
    assert photo_keyboard == "photo-keyboard"
    keyboard_builder.assert_awaited_once_with("zh")


def test_build_lazy_bot_payload_uses_telegram_url(monkeypatch):
    monkeypatch.setenv("QQCC_LAZY_BOT_URL", "https://t.me/QQCC666_bot?start=main")
    monkeypatch.delenv("QQCC_LAZY_BOT_USERNAME", raising=False)

    message, reply_markup = message_handler_menu.build_lazy_bot_payload(
        _build_context()
    )

    assert message == "translated:system.open_lazy_bot_hint"
    button = reply_markup.inline_keyboard[0][0]
    assert button.text == "translated:menu.open_lazy_bot"
    assert button.url == "https://t.me/QQCC666_bot?start=main"


def test_build_lazy_bot_payload_can_build_from_username(monkeypatch):
    monkeypatch.delenv("QQCC_LAZY_BOT_URL", raising=False)
    monkeypatch.setenv("QQCC_LAZY_BOT_USERNAME", "@QQCC666_bot")

    _message, reply_markup = message_handler_menu.build_lazy_bot_payload(
        _build_context()
    )

    assert reply_markup.inline_keyboard[0][0].url == "https://t.me/QQCC666_bot"


def test_build_lazy_bot_payload_handles_missing_config(monkeypatch):
    monkeypatch.delenv("QQCC_LAZY_BOT_URL", raising=False)
    monkeypatch.delenv("QQCC_LAZY_BOT_USERNAME", raising=False)

    message, reply_markup = message_handler_menu.build_lazy_bot_payload(
        _build_context()
    )

    assert message == "translated:system.lazy_bot_link_unavailable"
    assert reply_markup is None


def test_build_lazy_bot_payload_honors_disabled_entry_flag(monkeypatch):
    monkeypatch.setenv("QQCC_LAZY_BOT_ENABLED", "false")
    monkeypatch.setenv("QQCC_LAZY_BOT_URL", "https://t.me/QQCC666_bot?start=main")

    message, reply_markup = message_handler_menu.build_lazy_bot_payload(
        _build_context()
    )

    assert message == "translated:system.lazy_bot_link_unavailable"
    assert reply_markup is None


@pytest.mark.asyncio
async def test_build_back_main_and_recharge_payload(monkeypatch):
    keyboard_builder = AsyncMock(return_value="main-keyboard")
    monkeypatch.setattr(
        message_handler_menu,
        "get_runtime_main_menu_keyboard",
        keyboard_builder,
    )
    monkeypatch.setattr(
        message_handler_menu,
        "build_ton_payment_mini_app_url",
        lambda: "https://web.example/billing?method=ton&kind=membership",
    )
    message, keyboard = await message_handler_menu.build_back_to_main_payload(
        _build_context()
    )
    recharge_message, recharge_keyboard = message_handler_menu.build_recharge_payload(
        _build_context()
    )

    assert message == "translated:system.back_to_main"
    assert keyboard == "main-keyboard"
    assert recharge_message == "translated:billing.recharge_intro"
    assert (
        recharge_keyboard.inline_keyboard[0][0].text
        == "translated:billing.ton_monthly_plan_btn"
    )
    buttons = [row[0] for row in recharge_keyboard.inline_keyboard]
    assert [button.text for button in buttons] == [
        "translated:billing.ton_monthly_plan_btn",
        "translated:billing.stars_monthly_plan_btn",
        "translated:billing.stars_credit_btn",
        "translated:billing.rmb_monthly_plan_btn",
        "translated:billing.rmb_credit_btn",
    ]
    assert buttons[0].web_app.url.endswith(
        "/billing?method=ton&kind=membership"
    )
    assert [button.callback_data for button in buttons[1:]] == [
        "recharge_stars_menu",
        "recharge_stars_credit_menu",
        "recharge_rmb_menu",
        "recharge_rmb_credit_menu",
    ]


def test_build_switch_lang_message():
    zh_text = message_handler_menu.build_switch_lang_message("zh")
    en_text = message_handler_menu.build_switch_lang_message("en")

    assert "语言已切换为中文" in zh_text
    assert "Language switched to English" in en_text


def test_build_queue_status_message_includes_known_and_unknown_types():
    translations = {
        "profile.queue_status_title": "排队状态",
        "profile.total_queue": "总排队任务",
        "profile.tasks_unit": "个",
        "profile.other_types": "其他",
        "task.img2img": "🎨 懒人/自由P图",
        "task.video_edit": "🎬 视频编辑 (通用)",
    }
    context = SimpleNamespace(t=lambda key: translations[key])
    text = message_handler_menu.build_queue_status_message(
        3,
        {"img2img": 2, "custom_x": 1},
        context,
        {"img2img": "task.img2img", "video_edit": "task.video_edit"},
    )

    assert "👥 总排队任务：`3` 个" in text
    assert "免费🟢 付费🟢 懒人/自由P图：`2` 个" in text
    assert "免费🟢 付费🟢 视频编辑 (通用)：`0` 个" in text
    assert "🎨 懒人/自由P图" not in text
    assert "🎬 视频编辑 (通用)" not in text
    assert "免费🟢 付费🟢 ❓ 其他 (custom\\_x)：`1` 个" in text


def test_build_queue_status_message_uses_wait_dot_and_merges_duplicate_labels():
    translations = {
        "profile.queue_status_title": "排队状态",
        "profile.total_queue": "总排队任务",
        "profile.tasks_unit": "个",
        "profile.other_types": "其他",
        "task.green": "🍃 绿色任务",
        "task.yellow": "🟡 黄色任务",
        "task.orange_a": "🎬 动作迁移",
        "task.orange_b": "🏃 动作迁移",
        "task.red": "🔴 红色任务",
    }
    context = SimpleNamespace(t=lambda key: translations[key])

    text = message_handler_menu.build_queue_status_message(
        10,
        {
            "green": 1,
            "yellow": 2,
            "orange_a": 3,
            "orange_b": 4,
            "red": 0,
        },
        context,
        {
            "green": "task.green",
            "yellow": "task.yellow",
            "orange_a": "task.orange_a",
            "orange_b": "task.orange_b",
            "red": "task.red",
        },
        {
            "green": {"max_pending_wait_seconds": 599},
            "yellow": {"max_pending_wait_seconds": 600},
            "orange_a": {
                "max_pending_wait_seconds": 1200,
                "max_non_low_trust_pending_wait_seconds": 3600,
            },
            "orange_b": {
                "max_pending_wait_seconds": 1800,
                "max_non_low_trust_pending_wait_seconds": 1500,
            },
            "red": {"max_pending_wait_seconds": 3600},
        },
    )

    assert "免费🟢 付费🟢 绿色任务：`1` 个" in text
    assert "免费🟡 付费🟢 黄色任务：`2` 个" in text
    assert "免费🟠 付费🔴 动作迁移：`7` 个" in text
    assert text.count("动作迁移") == 1
    assert "免费🔴 付费🟢 红色任务：`0` 个" in text
    assert "免费最长等待" not in text
    assert "付费最长等待" not in text


def test_build_queue_status_message_dots_use_free_and_paid_waits():
    translations = {
        "profile.queue_status_title": "排队状态",
        "profile.total_queue": "总排队任务",
        "profile.tasks_unit": "个",
        "task.img2img_lora": "🖼 图生图 (附加模型)",
    }
    context = SimpleNamespace(t=lambda key: translations[key])

    text = message_handler_menu.build_queue_status_message(
        14,
        {"img2img_lora": 14},
        context,
        {"img2img_lora": "task.img2img_lora"},
        {
            "img2img_lora": {
                "pending_count": 14,
                "max_pending_wait_seconds": 40 * 60 + 22,
                "max_non_low_trust_pending_wait_seconds": 11 * 60,
            },
        },
    )

    assert "免费🟠 付费🟡 图生图 (附加模型)：`14` 个" in text


def test_build_user_queue_tasks_section_uses_display_names_and_status_text():
    translations = {
        "profile.my_tasks_title": "我的任务",
        "profile.my_tasks_status_unknown": "状态未知",
        "task.img2img": "🎨 懒人/自由P图",
        "task.mode_video_lora": "🎬 图生视频",
    }
    context = SimpleNamespace(t=lambda key, **_: translations[key])

    text = message_handler_menu.build_user_queue_tasks_section(
        [
            {"task_type": "img2img", "status_text": "全局排队第 2 位"},
            {"task_type": "img2video_group", "status_text": "生成中"},
        ],
        context,
        {
            "img2img": "task.img2img",
            "img2video_group": "task.mode_video_lora",
        },
    )

    assert "**我的任务**" in text
    assert "1. 懒人/自由P图：全局排队第 2 位" in text
    assert "2. 图生视频：生成中" in text
    assert "🎨" not in text
    assert "🎬" not in text


@pytest.mark.asyncio
async def test_reply_with_built_payload_uses_message_and_optional_reply_markup():
    reply_text = AsyncMock()
    message = SimpleNamespace()
    update = SimpleNamespace(
        effective_message=message, message=None, edited_message=None
    )

    await message_handler_menu.reply_with_built_payload(
        update,
        reply_text=reply_text,
        build_payload=lambda: ("hello", None),
    )

    reply_text.assert_awaited_once_with(
        message,
        "hello",
        parse_mode="Markdown",
    )


@pytest.mark.asyncio
async def test_reply_with_built_payload_supports_context_builder_and_reply_markup():
    reply_text = AsyncMock()
    message = SimpleNamespace()
    update = SimpleNamespace(
        effective_message=message, message=None, edited_message=None
    )
    context = _build_context()

    await message_handler_menu.reply_with_built_payload(
        update,
        reply_text=reply_text,
        build_payload=lambda ctx: (ctx.t("system.video_edit_hint"), "keyboard"),
        context=context,
    )

    reply_text.assert_awaited_once_with(
        message,
        "translated:system.video_edit_hint",
        parse_mode="Markdown",
        reply_markup="keyboard",
    )


@pytest.mark.asyncio
async def test_reply_with_built_payload_supports_async_context_builder():
    reply_text = AsyncMock()
    message = SimpleNamespace()
    update = SimpleNamespace(
        effective_message=message, message=None, edited_message=None
    )
    context = _build_context()
    builder = AsyncMock(return_value=("async-message", "async-keyboard"))

    await message_handler_menu.reply_with_built_payload(
        update,
        reply_text=reply_text,
        build_payload=builder,
        context=context,
    )

    builder.assert_awaited_once_with(context)
    reply_text.assert_awaited_once_with(
        message,
        "async-message",
        parse_mode="Markdown",
        reply_markup="async-keyboard",
    )


@pytest.mark.asyncio
async def test_reply_with_async_payload_supports_tuple_payload_and_no_parse_mode():
    reply_text = AsyncMock()
    message = SimpleNamespace()
    update = SimpleNamespace(
        effective_message=message, message=None, edited_message=None
    )

    async def build_payload(*, context, user):
        return (f"{context.lang}:{user.id}", "keyboard")

    await message_handler_menu.reply_with_async_payload(
        update,
        reply_text=reply_text,
        build_payload=build_payload,
        parse_mode=None,
        context=SimpleNamespace(lang="zh"),
        user=SimpleNamespace(id=7),
    )

    reply_text.assert_awaited_once_with(
        message,
        "zh:7",
        reply_markup="keyboard",
    )


@pytest.mark.asyncio
async def test_reply_with_async_payload_supports_plain_text_payload():
    reply_text = AsyncMock()
    message = SimpleNamespace()
    update = SimpleNamespace(
        effective_message=message, message=None, edited_message=None
    )

    async def build_payload(*, context, task_type_display_names):
        return f"{context.lang}:{sorted(task_type_display_names)}"

    await message_handler_menu.reply_with_async_payload(
        update,
        reply_text=reply_text,
        build_payload=build_payload,
        context=SimpleNamespace(lang="en"),
        task_type_display_names={"img2img": "task.img2img"},
    )

    reply_text.assert_awaited_once_with(
        message,
        "en:['img2img']",
        parse_mode="Markdown",
    )
