from datetime import datetime, timedelta
from types import SimpleNamespace

from src.handlers import message_handler_profile


def test_build_identity_display_handles_remaining_time_and_expired_state():
    future = datetime(2026, 6, 10, 12, 0, 0)
    now = datetime(2026, 6, 8, 10, 0, 0)
    expired = datetime(2026, 6, 7, 10, 0, 0)

    active_text = message_handler_profile.build_identity_display(
        "核心弟子",
        future,
        now=now,
    )
    expired_text = message_handler_profile.build_identity_display(
        "核心弟子",
        expired,
        now=now,
    )

    assert "剩余 2 天" in active_text
    assert "2026-06-10 12:00 到期" in active_text
    assert expired_text.endswith("(已过期)")


def test_build_personal_center_payload_builds_unlocked_markup():
    dto = SimpleNamespace(
        first_name="Tester",
        current_group="练气期",
        current_identity="核心弟子",
        identity_expire_at=datetime.now() + timedelta(days=3),
        current_priority=6,
        credits=120,
        invitations=2,
        checkins=5,
        generations=18,
        is_unlocked=True,
    )

    msg, reply_markup = message_handler_profile.build_personal_center_payload(
        dto,
        invite_link="https://t.me/AiVisionAV",
        web_url="https://web.aivison.it.com/",
    )

    assert "突破至筑基期" in msg
    assert "合欢密宗已解锁" in msg
    assert reply_markup is not None
    assert reply_markup.inline_keyboard[0][0].text == "📱 Mini App 自动登录"
    assert reply_markup.inline_keyboard[0][0].web_app is not None
    assert reply_markup.inline_keyboard[0][1].text == "🌐 浏览器 Web 登录"


def test_build_checkin_messages_keep_disclaimer_and_stats():
    success_text = message_handler_profile.build_checkin_success_message(
        user_group="筑基期",
        user_identity="核心弟子",
        total_days=7,
        reward=5,
        current_credits=88,
    )
    repeat_text = message_handler_profile.build_checkin_repeat_message(
        user_group="筑基期",
        user_identity="核心弟子",
        total_days=7,
    )

    assert "签到成功" in success_text
    assert "`5` 灵石" in success_text
    assert "累计签到统计始于3月5日" in success_text
    assert "今日已领取灵石" in repeat_text
    assert "累计签到统计始于3月5日" in repeat_text


def test_build_checkin_messages_translate_group_and_identity_in_english():
    success_text = message_handler_profile.build_checkin_success_message(
        user_group="练气期",
        user_identity="真传弟子",
        total_days=4,
        reward=60,
        current_credits=13468,
        lang="en",
    )

    assert "Check-in successful" in success_text
    assert "Qi Condensation" in success_text
    assert "True Disciple" in success_text
    assert "练气期" not in success_text
    assert "真传弟子" not in success_text


def test_build_share_payload_keeps_affiliate_actions():
    dto = SimpleNamespace(
        current_group="练气期",
        invitations=2,
        invitation_recharge={
            "recharged_invitees_count": 3,
            "total_recharge_count": 4,
            "total_ton": 1.23,
            "total_rmb": 45.67,
            "total_stars": 89,
            "total_commission_usdt": 9.99,
            "spent_commission_usdt": 1.11,
            "available_balance_usdt": 8.88,
        },
    )

    msg, reply_markup = message_handler_profile.build_share_payload(
        dto,
        invite_link="https://t.me/aivision666_bot?start=123",
    )

    assert "分享赚灵石" in msg
    assert "历史累计返佣：`USDT 9.99`" in msg
    assert reply_markup.inline_keyboard[0][0].callback_data == "affiliate_redeem_credits_menu"
    assert reply_markup.inline_keyboard[0][1].callback_data == "affiliate_redeem_membership_menu"


def test_build_share_payload_translates_group_and_stats_in_english():
    dto = SimpleNamespace(
        current_group="练气期",
        invitations=0,
        invitation_recharge={
            "recharged_invitees_count": 0,
            "total_recharge_count": 0,
            "total_ton": 0.0,
            "total_rmb": 0.0,
            "total_stars": 0,
            "total_commission_usdt": 300.0,
            "spent_commission_usdt": 105.94,
            "available_balance_usdt": 194.06,
        },
    )

    msg, _reply_markup = message_handler_profile.build_share_payload(
        dto,
        invite_link="https://t.me/aivision666_bot?start=123",
        lang="en",
    )

    assert "Share for Credits" in msg
    assert "Qi Condensation" in msg
    assert "Invitation stats" in msg
    assert "Historical commission: `USDT 300.00`" in msg
    assert "练气期" not in msg
    assert "邀请数据" not in msg
