from types import SimpleNamespace

from src.handlers import message_handler_menu


def _build_context(lang: str = "zh"):
    return SimpleNamespace(lang=lang, t=lambda key: f"translated:{key}")


def test_build_photo_and_video_edit_payload_use_context_translation(monkeypatch):
    monkeypatch.setattr(
        "src.i18n.keyboards.get_photo_edit_keyboard",
        lambda _lang: "photo-keyboard",
    )
    monkeypatch.setattr(
        "src.i18n.keyboards.get_video_edit_keyboard",
        lambda _lang: "video-keyboard",
    )

    photo_msg, photo_keyboard = message_handler_menu.build_photo_edit_payload(
        _build_context()
    )
    video_msg, video_keyboard = message_handler_menu.build_video_edit_payload(
        _build_context()
    )

    assert photo_msg == "translated:system.photo_edit_hint"
    assert photo_keyboard == "photo-keyboard"
    assert video_msg == "translated:system.video_edit_hint"
    assert video_keyboard == "video-keyboard"


def test_build_back_main_and_recharge_payload():
    message, keyboard = message_handler_menu.build_back_to_main_payload(_build_context())
    recharge_message, recharge_keyboard = message_handler_menu.build_recharge_payload()

    assert "已返回主菜单" in message
    assert keyboard is not None
    assert "合欢宗账房" in recharge_message
    assert recharge_keyboard.inline_keyboard[0][0].text == "💎 TON月卡套餐"


def test_build_switch_lang_message_and_gallery_payload():
    zh_text = message_handler_menu.build_switch_lang_message("zh")
    en_text = message_handler_menu.build_switch_lang_message("en")
    gallery_message, reply_markup = message_handler_menu.build_gallery_payload()

    assert "语言已切换为中文" in zh_text
    assert "Language switched to English" in en_text
    assert "web.aivison.it.com" in gallery_message
    assert reply_markup is None


def test_build_queue_status_message_includes_known_and_unknown_types():
    context = SimpleNamespace(t=lambda key: f"T:{key}")
    text = message_handler_menu.build_queue_status_message(
        3,
        {"img2img": 2, "custom_x": 1},
        context,
        {"img2img": "task.img2img", "video_edit": "task.video_edit"},
    )

    assert "总排队任务：`3` 个" in text
    assert "T:task.img2img：`2` 个" in text
    assert "T:task.video_edit：`0` 个" in text
    assert "❓ 其他 (custom\\_x)：`1` 个" in text
