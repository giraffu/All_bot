import re
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import WEBAPP_URL
from src.handlers.message_handler_common import get_reply_message


def build_photo_edit_payload(context) -> tuple[str, object]:
    from src.i18n.keyboards import get_photo_edit_keyboard

    return context.t("system.photo_edit_hint"), get_photo_edit_keyboard(context.lang)


def build_video_edit_payload(context) -> tuple[str, object]:
    from src.i18n.keyboards import get_video_edit_keyboard

    return context.t("system.video_edit_hint"), get_video_edit_keyboard(context.lang)


def build_video_to_video_payload(context) -> tuple[str, object]:
    from src.i18n.keyboards import get_video_to_video_keyboard

    return context.t("system.video_to_video_hint"), get_video_to_video_keyboard(context.lang)


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

def _strip_queue_display_icon(label: str) -> str:
    return re.sub(r"^[^\w\u4e00-\u9fff]+\s*", "", label)


def _context_text(context, key: str, default: str) -> str:
    try:
        text = context.t(key)
    except Exception:
        return default
    return default if text == key else text


def _coerce_wait_seconds(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        wait_seconds = int(float(value))
    except (TypeError, ValueError):
        return None
    return wait_seconds if wait_seconds >= 0 else None


def _format_wait_duration(value: Any, context) -> str | None:
    wait_seconds = _coerce_wait_seconds(value)
    if wait_seconds is None:
        return None

    hours, remainder = divmod(wait_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if getattr(context, "lang", "zh") == "en":
        if hours:
            return f"{hours}h {minutes:02d}m {seconds:02d}s"
        if minutes:
            return f"{minutes}m {seconds:02d}s"
        return f"{seconds}s"

    if hours:
        return f"{hours}小时{minutes:02d}分{seconds:02d}秒"
    if minutes:
        return f"{minutes}分{seconds:02d}秒"
    return f"{seconds}秒"


def _build_wait_stats_suffix(queue_type_detail: dict | None, context) -> str:
    queue_type_detail = queue_type_detail or {}
    free_label = _context_text(
        context,
        "profile.queue_free_max_wait",
        "免费最长等待",
    )
    paid_label = _context_text(
        context,
        "profile.queue_paid_max_wait",
        "付费最长等待",
    )
    empty_label = _context_text(context, "profile.queue_wait_none", "暂无")
    free_wait = (
        _format_wait_duration(
            queue_type_detail.get("max_free_pending_wait_seconds"),
            context,
        )
        or empty_label
    )
    paid_wait = (
        _format_wait_duration(
            queue_type_detail.get("max_paid_pending_wait_seconds"),
            context,
        )
        or empty_label
    )
    return f"（{free_label}：`{free_wait}`，{paid_label}：`{paid_wait}`）"


def build_queue_status_message(
    queue_size: int,
    queue_by_type: dict,
    context,
    task_type_display_names: dict,
    queue_by_type_details: dict | None = None,
) -> str:
    total_queue_label = context.t("profile.total_queue")
    tasks_unit = context.t("profile.tasks_unit")
    queue_by_type_details = queue_by_type_details or {}
    msg_lines = [
        f"📊 **{context.t('profile.queue_status_title')}**\n",
        f"👥 {total_queue_label}：`{queue_size}` {tasks_unit}",
    ]

    for task_type, i18n_key in task_type_display_names.items():
        count = queue_by_type.get(task_type, 0)
        display_name = _strip_queue_display_icon(context.t(i18n_key))
        wait_suffix = _build_wait_stats_suffix(
            queue_by_type_details.get(task_type),
            context,
        )
        msg_lines.append(f"{display_name}：`{count}` {tasks_unit}{wait_suffix}")

    for task_type, count in queue_by_type.items():
        if task_type not in task_type_display_names and count > 0:
            safe_task_type = task_type.replace("_", "\\_")
            wait_suffix = _build_wait_stats_suffix(
                queue_by_type_details.get(task_type),
                context,
            )
            msg_lines.append(
                f"❓ {context.t('profile.other_types')} ({safe_task_type})：`{count}` {tasks_unit}{wait_suffix}"
            )

    return "\n".join(msg_lines)


def build_user_queue_tasks_section(user_tasks: list[dict], context, task_type_display_names: dict) -> str:
    if not user_tasks:
        return ""

    msg_lines = ["", f"**{context.t('profile.my_tasks_title')}**"]
    for index, task in enumerate(user_tasks, start=1):
        task_type = task.get("task_type", "")
        task_name = task_type
        i18n_key = task_type_display_names.get(task_type)
        if i18n_key:
            task_name = _strip_queue_display_icon(context.t(i18n_key))

        status_text = task.get("status_text") or context.t("profile.my_tasks_status_unknown")
        msg_lines.append(f"{index}. {task_name}：{status_text}")

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
