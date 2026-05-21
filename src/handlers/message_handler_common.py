from telegram import Update

from src.services.permission_service import permission_service
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


def format_invitation_stats(invitation_recharge: dict) -> str:
    total_commission = invitation_recharge.get(
        "total_commission_usdt", invitation_recharge.get("commission_usdt", 0.0)
    )
    return (
        "🤝 **邀请数据**：\n"
        f"  - 邀请充值：已有 `{invitation_recharge['recharged_invitees_count']}` 位道友完成 `{invitation_recharge['total_recharge_count']}` 次充值\n"
        f"  - 累积充值：`{invitation_recharge['total_ton']:.2f}` TON\n"
        f"  - 累积充值：`¥ {invitation_recharge['total_rmb']:.2f}`\n"
        f"  - 累积贡献：`{invitation_recharge['total_stars']}` Stars\n"
        f"  - 历史累计返佣：*$ {float(total_commission):.2f} USDT*\n"
        f"  - 已兑换返佣：*$ {invitation_recharge.get('spent_commission_usdt', 0.0):.2f} USDT*\n"
        f"  - 当前可兑换余额：*$ {invitation_recharge.get('available_balance_usdt', 0.0):.2f} USDT*\n"
        "  - 返佣说明：历史累计返佣用于展示成绩；当前可兑换余额才会随兑换减少"
    )


def build_private_prompt_fallback(lang: str) -> str:
    if lang == "en":
        return (
            "✨ Unrecognized command.\n"
            "👇 Please use the menu below, or type /start to wake up the menu."
        )
    return "✨ 似乎是不认识的指令呢。\n👇 请使用下方菜单进行操作，或输入 /start 重新唤醒菜单。"


async def ensure_user_access_reward(context, user):
    is_member = await get_user_channel_status(context.bot, user.id)
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
