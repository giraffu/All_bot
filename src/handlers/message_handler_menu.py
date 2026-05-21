from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import WEBAPP_URL


def build_photo_edit_payload(context) -> tuple[str, object]:
    from src.i18n.keyboards import get_photo_edit_keyboard

    return context.t("system.photo_edit_hint"), get_photo_edit_keyboard(context.lang)


def build_video_edit_payload(context) -> tuple[str, object]:
    from src.i18n.keyboards import get_video_edit_keyboard

    return context.t("system.video_edit_hint"), get_video_edit_keyboard(context.lang)


def build_gallery_payload() -> tuple[str, None]:
    return (
        "浏览器进入 `https://web.aivison.it.com/` 或点击web按钮，查看市集内容哦",
        None,
    )


def build_back_to_main_payload(context) -> tuple[str, object]:
    from src.i18n.keyboards import get_main_menu_keyboard

    return "🏠 **已返回主菜单**", get_main_menu_keyboard(context.lang)


def build_recharge_payload() -> tuple[str, InlineKeyboardMarkup]:
    webapp_url = WEBAPP_URL or "https://pay.aivison.it.com/"
    keyboard = [
        [InlineKeyboardButton("💎 TON月卡套餐", web_app=WebAppInfo(url=webapp_url))],
        [InlineKeyboardButton("⭐️ Star月卡套餐", callback_data="recharge_stars_menu")],
        [
            InlineKeyboardButton(
                "⭐️ Star直充灵石",
                callback_data="recharge_stars_credit_menu",
            )
        ],
        [InlineKeyboardButton("¥ 人民币充值月卡", callback_data="recharge_rmb_menu")],
        [
            InlineKeyboardButton(
                "¥ 人民币直充灵石",
                callback_data="recharge_rmb_credit_menu",
            )
        ],
    ]
    msg = (
        "📜 **【合欢宗账房】灵石充值与身份晋升**\n\n"
        "欢迎来到合欢宗账房！灵石乃修仙界之硬通货，可用以驱动阵法（生成图像与视频）。\n\n"
        "🔰 **【内门弟子】** 1.99 TON / ¥ 30.00\n"
        "   └ 🎁 直接获得 `400` 灵石\n"
        "   └ 📅 每日签到额外 `+30` 灵石\n"
        "   └ 🔓 解锁特权 `720p` 画质，最长 `8s` 视频\n"
        "   └ ⚡ 排队优先级 `+20`\n\n"
        "💠 **【核心弟子】** 4.99 TON / ¥ 70.00\n"
        "   └ 🎁 直接获得 `1200` 灵石\n"
        "   └ 📅 每日签到额外 `+40` 灵石\n"
        "   └ 🔓 解锁特权 `1024p` 画质，最长 `10s` 视频\n"
        "   └ ⚡ 排队优先级 `+30`\n\n"
        "👑 **【真传弟子】** 9.99 TON / ¥ 120.00\n"
        "   └ 🎁 直接获得 `3000` 灵石\n"
        "   └ 📅 每日签到额外 `+50` 灵石\n"
        "   └ 🔓 解锁特权 `1024p` 画质，最长 `10s` 视频\n"
        "   └ 🚀 排队优先级 `+45` (极速)\n\n"
        "⚠️ **注意事项**：\n"
        "1. 充值所获灵石与身份特权，一经交付，不可退换。\n\n"
        "👇 **请选择您的支付法门**："
    )
    return msg, InlineKeyboardMarkup(keyboard)


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
