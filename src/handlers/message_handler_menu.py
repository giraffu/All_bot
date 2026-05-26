from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import WEBAPP_URL
from src.handlers.message_handler_common import get_reply_message


def build_photo_edit_payload(context) -> tuple[str, object]:
    from src.i18n.keyboards import get_photo_edit_keyboard

    return context.t("system.photo_edit_hint"), get_photo_edit_keyboard(context.lang)


def build_video_edit_payload(context) -> tuple[str, object]:
    from src.i18n.keyboards import get_video_edit_keyboard

    return context.t("system.video_edit_hint"), get_video_edit_keyboard(context.lang)


def build_gallery_payload(context) -> tuple[str, None]:
    return (context.t("system.gallery_web_hint"), None)


def build_back_to_main_payload(context) -> tuple[str, object]:
    from src.i18n.keyboards import get_main_menu_keyboard

    return context.t("system.back_to_main"), get_main_menu_keyboard(context.lang)


def build_recharge_payload(context) -> tuple[str, InlineKeyboardMarkup]:
    webapp_url = WEBAPP_URL or "https://pay.aivison.it.com/"
    keyboard = [
        [
            InlineKeyboardButton(
                context.t("billing.ton_monthly_plan_btn"),
                web_app=WebAppInfo(url=webapp_url),
            )
        ],
        [
            InlineKeyboardButton(
                context.t("billing.stars_monthly_plan_btn"),
                callback_data="recharge_stars_menu",
            )
        ],
        [
            InlineKeyboardButton(
                context.t("billing.stars_credit_btn"),
                callback_data="recharge_stars_credit_menu",
            )
        ],
        [
            InlineKeyboardButton(
                context.t("billing.rmb_monthly_plan_btn"),
                callback_data="recharge_rmb_menu",
            )
        ],
        [
            InlineKeyboardButton(
                context.t("billing.rmb_credit_btn"),
                callback_data="recharge_rmb_credit_menu",
            )
        ],
    ]
    return context.t("billing.recharge_intro"), InlineKeyboardMarkup(keyboard)


def build_switch_lang_message(new_lang: str) -> str:
    return (
        "🌐 语言已切换为中文。"
        if new_lang == "zh"
        else "🌐 Language switched to English."
    )


def build_queue_status_message(queue_size: int, queue_by_type: dict, context, task_type_display_names: dict) -> str:
    msg_lines = ["📊 **宗门灵气损耗现状**\n", f"👥 总排队任务：`{queue_size}` 个"]

    for task_type, i18n_key in task_type_display_names.items():
        count = queue_by_type.get(task_type, 0)
        display_name = context.t(i18n_key)
        msg_lines.append(f"{display_name}：`{count}` 个")

    for task_type, count in queue_by_type.items():
        if task_type not in task_type_display_names and count > 0:
            safe_task_type = task_type.replace("_", "\\_")
            msg_lines.append(f"❓ 其他 ({safe_task_type})：`{count}` 个")

    return "\n".join(msg_lines)


async def reply_with_built_payload(
    update,
    *,
    reply_text,
    build_payload,
    context=None,
    parse_mode: str | None = "Markdown",
):
    message = get_reply_message(update)
    if not message:
        return None

    if context is None:
        msg, reply_markup = build_payload()
    else:
        msg, reply_markup = build_payload(context)

    reply_kwargs = {}
    if parse_mode is not None:
        reply_kwargs["parse_mode"] = parse_mode
    if reply_markup is not None:
        reply_kwargs["reply_markup"] = reply_markup

    await reply_text(message, msg, **reply_kwargs)
    return None


async def reply_with_async_payload(
    update,
    *,
    reply_text,
    build_payload,
    parse_mode: str | None = "Markdown",
    **build_kwargs,
):
    message = get_reply_message(update)
    if not message:
        return None

    payload = await build_payload(**build_kwargs)
    if payload is None:
        return None

    if isinstance(payload, tuple):
        msg, reply_markup = payload
    else:
        msg, reply_markup = payload, None

    reply_kwargs = {}
    if parse_mode is not None:
        reply_kwargs["parse_mode"] = parse_mode
    if reply_markup is not None:
        reply_kwargs["reply_markup"] = reply_markup

    await reply_text(message, msg, **reply_kwargs)
    return None
