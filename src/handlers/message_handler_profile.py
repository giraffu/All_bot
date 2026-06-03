from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import REFUGE_INVITE_LINK
from src.handlers.message_handler_common import format_invitation_stats
from src.i18n.translator import get_text


def _translate_group(group: str, *, lang: str = "zh") -> str:
    translated = get_text(f"group.{group}", lang)
    return translated if translated != f"group.{group}" else group


def _translate_identity(identity: str, *, lang: str = "zh") -> str:
    translated = get_text(f"identity.{identity}", lang)
    return translated if translated != f"identity.{identity}" else identity


def build_breakthrough_message(dto, invite_link: str, *, lang: str = "zh") -> str:
    if dto.current_group == "凡人":
        return get_text(
            "profile_extra.breakthrough_mortal", lang, invite_link=invite_link
        )
    if dto.current_group == "练气期":
        inv_done = "✅" if dto.invitations > 1 else "❌"
        checkin_done = "✅" if dto.checkins > 3 else "❌"
        gen_done = "✅" if dto.generations > 10 else "❌"
        return get_text(
            "profile_extra.breakthrough_qi",
            lang,
            invite_done=inv_done,
            checkin_done=checkin_done,
            generation_done=gen_done,
        )
    if dto.current_group == "筑基期":
        inv_done = "✅" if dto.invitations > 10 else "❌"
        checkin_done = "✅" if dto.checkins > 30 else "❌"
        gen_done = "✅" if dto.generations > 100 else "❌"
        return get_text(
            "profile_extra.breakthrough_foundation",
            lang,
            invite_done=inv_done,
            checkin_done=checkin_done,
            generation_done=gen_done,
        )
    if dto.current_group == "金丹期":
        inv_done = "✅" if dto.invitations > 100 else "❌"
        checkin_done = "✅" if dto.checkins > 300 else "❌"
        gen_done = "✅" if dto.generations > 1000 else "❌"
        return get_text(
            "profile_extra.breakthrough_core",
            lang,
            invite_done=inv_done,
            checkin_done=checkin_done,
            generation_done=gen_done,
        )
    if dto.current_group == "元婴期":
        return get_text("profile_extra.breakthrough_nascent", lang)
    return ""


def build_identity_display(
    current_identity: str,
    identity_expire_at,
    *,
    now: datetime | None = None,
    lang: str = "zh",
) -> str:
    identity_display = f"`{_translate_identity(current_identity, lang=lang)}`"
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
            return get_text(
                "profile_extra.identity_remaining_days",
                lang,
                identity=identity_display,
                days=days,
                expire_at=expire_str,
            )
        return get_text(
            "profile_extra.identity_remaining_hours",
            lang,
            identity=identity_display,
            hours=hours,
            expire_at=expire_str,
        )
    return get_text("profile_extra.identity_expired", lang, identity=identity_display)


def build_personal_center_payload(
    dto, *, invite_link: str, web_url: str, lang: str = "zh"
) -> tuple[str, InlineKeyboardMarkup | None]:
    breakthrough_msg = build_breakthrough_message(dto, invite_link, lang=lang)
    identity_display = build_identity_display(
        dto.current_identity, dto.identity_expire_at, lang=lang
    )
    msg = get_text(
        "profile_extra.personal_center",
        lang,
        name=dto.first_name,
        group=_translate_group(dto.current_group, lang=lang),
        identity_display=identity_display,
        priority=dto.current_priority,
        credits=dto.credits,
        invitations=dto.invitations,
        checkins=dto.checkins,
        generations=dto.generations,
        breakthrough_msg=breakthrough_msg,
    )
    if not dto.is_unlocked:
        return msg, None

    msg += f"\n\n{get_text('profile_extra.web_unlocked', lang)}"
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    get_text("profile_extra.miniapp_button", lang),
                    web_app=WebAppInfo(url=web_url),
                ),
                InlineKeyboardButton(get_text("profile_extra.web_button", lang), url=web_url),
            ]
        ]
    )
    return msg, reply_markup


def build_refuge_checkin_payload(lang: str = "zh") -> tuple[str, InlineKeyboardMarkup]:
    link = REFUGE_INVITE_LINK or "https://t.me/+J0velHHqUF01NGM1"
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(get_text("profile_extra.refuge_join_button", lang), url=link)]]
    )
    return get_text("profile_extra.refuge_checkin", lang), reply_markup


def build_checkin_success_message(
    *,
    user_group: str,
    user_identity: str,
    total_days: int,
    reward,
    current_credits,
    lang: str = "zh",
) -> str:
    disclaimer = get_text("profile_extra.checkin_disclaimer", lang)
    return get_text(
        "profile_extra.checkin_success",
        lang,
        group=_translate_group(user_group, lang=lang),
        identity=_translate_identity(user_identity, lang=lang),
        total_days=total_days,
        reward=reward,
        current_credits=current_credits,
        disclaimer=disclaimer,
    )


def build_checkin_repeat_message(
    *,
    user_group: str,
    user_identity: str,
    total_days: int,
    lang: str = "zh",
) -> str:
    disclaimer = get_text("profile_extra.checkin_disclaimer", lang)
    return get_text(
        "profile_extra.checkin_repeat",
        lang,
        group=_translate_group(user_group, lang=lang),
        identity=_translate_identity(user_identity, lang=lang),
        total_days=total_days,
        disclaimer=disclaimer,
    )


def build_share_payload(
    dto, *, invite_link: str, lang: str = "zh"
) -> tuple[str, InlineKeyboardMarkup]:
    msg = get_text(
        "profile_extra.share_panel",
        lang,
        group=_translate_group(dto.current_group, lang=lang),
        invite_link=invite_link,
        invitations=dto.invitations,
        invitation_stats=format_invitation_stats(dto.invitation_recharge, lang=lang),
    )
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    get_text("profile_extra.redeem_credits_btn", lang),
                    callback_data="affiliate_redeem_credits_menu",
                ),
                InlineKeyboardButton(
                    get_text("profile_extra.redeem_membership_btn", lang),
                    callback_data="affiliate_redeem_membership_menu",
                ),
            ]
        ]
    )
    return msg, reply_markup
