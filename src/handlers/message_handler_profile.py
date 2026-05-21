from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import REFUGE_INVITE_LINK
from src.handlers.message_handler_common import format_invitation_stats


def build_breakthrough_message(dto, invite_link: str) -> str:
    if dto.current_group == "凡人":
        return f"🚀 **突破至练气期条件**：\n🔸 拜入宗门 [👉 [点击即刻拜入]({invite_link})]"
    if dto.current_group == "练气期":
        inv_done = "✅" if dto.invitations > 1 else "❌"
        checkin_done = "✅" if dto.checkins > 3 else "❌"
        gen_done = "✅" if dto.generations > 10 else "❌"
        return (
            "🚀 **突破至筑基期(视野更加清晰了)条件**：\n"
            f"🔸 邀请道友 > 1人 ({inv_done})\n"
            f"🔸 累计签到 > 3天 ({checkin_done})\n"
            f"🔸 修炼次数 > 10次 ({gen_done})"
        )
    if dto.current_group == "筑基期":
        inv_done = "✅" if dto.invitations > 10 else "❌"
        checkin_done = "✅" if dto.checkins > 30 else "❌"
        gen_done = "✅" if dto.generations > 100 else "❌"
        return (
            "🚀 **突破至金丹期条件**：\n"
            f"🔸 邀请道友 > 10人 ({inv_done})\n"
            f"🔸 累计签到 > 30天 ({checkin_done})\n"
            f"🔸 修炼次数 > 100次 ({gen_done})"
        )
    if dto.current_group == "金丹期":
        inv_done = "✅" if dto.invitations > 100 else "❌"
        checkin_done = "✅" if dto.checkins > 300 else "❌"
        gen_done = "✅" if dto.generations > 1000 else "❌"
        return (
            "🚀 **突破至元婴期条件**：\n"
            f"🔸 邀请道友 > 100人 ({inv_done})\n"
            f"🔸 累计签到 > 300天 ({checkin_done})\n"
            f"🔸 修炼次数 > 1000次 ({gen_done})"
        )
    if dto.current_group == "元婴期":
        return "✨ **已修成元婴，神通广大，万法不侵**"
    return ""


def build_identity_display(
    current_identity: str,
    identity_expire_at,
    *,
    now: datetime | None = None,
) -> str:
    identity_display = f"`{current_identity}`"
    if current_identity == "外门弟子" or not identity_expire_at:
        return identity_display

    current_time = now or datetime.now()
    expire_at = identity_expire_at
    if expire_at.tzinfo is not None:
        expire_at = expire_at.replace(tzinfo=None)
    if expire_at > current_time:
        remaining = expire_at - current_time
        days = remaining.days
        hours = remaining.seconds // 3600
        expire_str = expire_at.strftime("%Y-%m-%d %H:%M")
        if days > 0:
            return f"{identity_display} (剩余 {days} 天，{expire_str} 到期)"
        return f"{identity_display} (剩余 {hours} 小时，{expire_str} 到期)"
    return f"{identity_display} (已过期)"


def build_personal_center_payload(dto, *, invite_link: str, web_url: str) -> tuple[str, InlineKeyboardMarkup | None]:
    breakthrough_msg = build_breakthrough_message(dto, invite_link)
    identity_display = build_identity_display(dto.current_identity, dto.identity_expire_at)
    msg = (
        f"👤 **道友**：`{dto.first_name}`\n"
        f"📜 **修为**：`{dto.current_group}`\n"
        f"🪪 **身份**：{identity_display}\n"
        f"⚡ **排队加速**：`+{dto.current_priority}` 优先级\n"
        f"💰 **灵石余额**：`{dto.credits}`\n\n"
        f"📊 **修炼数据**：\n"
        f"  - 邀请同道：`{dto.invitations}` 人\n"
        f"  - 累计签到：`{dto.checkins}` 天\n"
        f"  - 施法次数：`{dto.generations}` 次\n\n"
        "💡 *提示：1点加速优先级约等于为您节约1分钟的排队时间。*\n\n"
        f"{breakthrough_msg}"
    )
    if not dto.is_unlocked:
        return msg, None

    msg += "\n\n🌐 **合欢密宗已解锁**"
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🌐 前往合欢密宗 (Web端)", url=web_url),
                InlineKeyboardButton("📱 沉浸式 Mini App", web_app=WebAppInfo(url=web_url)),
            ]
        ]
    )
    return msg, reply_markup


def build_refuge_checkin_payload() -> tuple[str, InlineKeyboardMarkup]:
    link = REFUGE_INVITE_LINK or "https://t.me/+J0velHHqUF01NGM1"
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🛡️ 点击加入避难所", url=link)]]
    )
    msg = (
        "🛡️ **避难所签到检测**\n\n"
        "道友，检测到您尚未加入【合欢宗避难所】。\n"
        "**加入避难所，防封不迷路！**\n\n"
        "请先加入避难所后，再来进行每日签到领取奖励吧！"
    )
    return msg, reply_markup


def build_checkin_success_message(
    *,
    user_group: str,
    user_identity: str,
    total_days: int,
    reward,
    current_credits,
) -> str:
    disclaimer = "\n\n⚠️ _注：累计签到统计始于3月5日，此前的数据未计入系统。_"
    reward_msg = f"`{reward}` 灵石"
    return (
        f"✅ **签到成功！**\n\n"
        f"👤 当前境界：`{user_group}`\n"
        f"🪪 当前身份：`{user_identity}`\n"
        f"📅 累计签到：`{total_days}` 天\n"
        f"🎉 本次获得：{reward_msg}\n"
        f"💰 当前总灵石：`{current_credits}`"
        f"{disclaimer}"
    )


def build_checkin_repeat_message(
    *,
    user_group: str,
    user_identity: str,
    total_days: int,
) -> str:
    disclaimer = "\n\n⚠️ _注：累计签到统计始于3月5日，此前的数据未计入系统。_"
    return (
        f"📅 **今日已领取灵石**\n\n"
        f"👤 当前境界：`{user_group}`\n"
        f"🪪 当前身份：`{user_identity}`\n"
        f"📅 累计签到：`{total_days}` 天\n\n"
        "请明天再来领取奖励吧！"
        f"{disclaimer}"
    )


def build_share_payload(dto, *, invite_link: str) -> tuple[str, InlineKeyboardMarkup]:
    msg = (
        "🤝 **分享赚灵石**\n\n"
        f"👤 **当前等级**：`{dto.current_group}`\n"
        f"🔗 **您的专属链接**：\n`{invite_link}`\n\n"
        "📈 **邀请统计**：\n"
        f"👥 已邀请人数：`{dto.invitations}` 人\n\n"
        f"{format_invitation_stats(dto.invitation_recharge)}\n\n"
        "💡 **规则**：\n"
        "每成功邀请一位**新道友**使用机器人，您将自动获得 **5 灵石**奖励！\n"
        "**新道友**加入宗门，您将自动获得 **10 灵石**奖励！\n"
    )
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("返佣兑灵石", callback_data="affiliate_redeem_credits_menu"),
                InlineKeyboardButton("返佣兑身份", callback_data="affiliate_redeem_membership_menu"),
            ]
        ]
    )
    return msg, reply_markup
