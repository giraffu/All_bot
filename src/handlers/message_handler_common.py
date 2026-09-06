from telegram import Update

from src.i18n.translator import get_text
from src.services.permission_service import permission_service
from src.services.main_bot_menu_runtime import get_runtime_main_menu_keyboard
from src.utils import (
    create_background_task,
    get_user_channel_status,
    notify_inviter_reward,
)


def get_reply_message(update: Update):
    return (
        getattr(update, "effective_message", None)
        or update.message
        or update.edited_message
    )


def format_invitation_stats(invitation_recharge: dict, *, lang: str = "zh") -> str:
    total_commission = invitation_recharge.get(
        "total_commission_usdt", invitation_recharge.get("commission_usdt", 0.0)
    )
    return get_text(
        "profile_extra.invitation_stats_block",
        lang,
        recharged_invitees_count=invitation_recharge["recharged_invitees_count"],
        total_recharge_count=invitation_recharge["total_recharge_count"],
        total_ton=f"{invitation_recharge['total_ton']:.2f}",
        total_rmb=f"{invitation_recharge['total_rmb']:.2f}",
        total_stars=invitation_recharge["total_stars"],
        total_commission=f"{float(total_commission):.2f}",
        spent_commission=f"{float(invitation_recharge.get('spent_commission_usdt', 0.0)):.2f}",
        available_balance=f"{float(invitation_recharge.get('available_balance_usdt', 0.0)):.2f}",
    )


def build_private_prompt_fallback(lang: str) -> str:
    if lang == "en":
        return (
            "✨ Unrecognized command.\n"
            "👇 Please use the menu below, or type /start to wake up the menu."
        )
    return "✨ 似乎是不认识的指令呢。\n👇 请使用下方菜单进行操作，或输入 /start 重新唤醒菜单。"


def extract_prompt_message_text(update: Update) -> tuple[object | None, str]:
    message = get_reply_message(update)
    if not message:
        return None, ""
    text = message.text.strip() if getattr(message, "text", None) else ""
    return message, text


def resolve_prompt_route_handler(text: str, prompt_routes: dict, reverse_map: dict):
    route_key = reverse_map.get(text)
    if not route_key:
        return None
    return prompt_routes.get(route_key)


async def dispatch_prompt_route(
    update: Update,
    context,
    text: str,
    *,
    prompt_routes: dict,
    reverse_map: dict,
) -> tuple[bool, object]:
    route_handler = resolve_prompt_route_handler(text, prompt_routes, reverse_map)
    if not route_handler:
        return False, None
    return True, await route_handler(update, context, text)


async def reply_private_prompt_fallback(message, *, lang: str, reply_text):
    chat = getattr(message, "chat", None)
    if not chat or chat.type != "private":
        return None
    fallback_text = build_private_prompt_fallback(lang)
    reply_markup = await get_runtime_main_menu_keyboard(lang)
    await reply_text(
        message,
        fallback_text,
        reply_markup=reply_markup,
    )
    return None


async def ensure_user_access_reward(context, user):
    is_member = await get_user_channel_status(context, user.id)
    inviter_id = await permission_service.check_access(
        user.id,
        user.username,
        user.full_name,
        is_member,
    )
    if inviter_id:
        create_background_task(
            context,
            notify_inviter_reward(context.bot, inviter_id, user.full_name),
        )
    return inviter_id
