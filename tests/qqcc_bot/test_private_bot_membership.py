from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.warnings import PTBUserWarning

from qqcc_bot import commands, main
from src.core.exceptions import AccessDeniedError
from src.services.qqcc_config_service import normalize_qqcc_config


def test_private_application_receives_only_central_membership_callable():
    checker = AsyncMock(return_value=True)

    # The shared quick-image/video ConversationHandlers intentionally keep the
    # project's existing per_message=False behavior.
    with pytest.warns(PTBUserWarning):
        application = main.build_application(
            "123456:private-tenant-credential",
            bot_client_type="bot:qqcc-private:7",
            private_bot_id=7,
            include_private_bot_provisioning=False,
            channel_membership_checker=checker,
        )

    assert application.bot_data["qqcc_channel_membership_checker"] is checker


def _private_context(*, checker):
    tenant_bot = SimpleNamespace(get_chat_member=AsyncMock())
    context = SimpleNamespace(
        args=[],
        lang="zh",
        t=lambda key: f"translated:{key}",
        bot=tenant_bot,
        bot_data={
            "bot_client_type": "bot:qqcc-private:7",
            "private_qqcc_bot_id": 7,
            "qqcc_channel_membership_checker": checker,
            "qqcc_config_loader": AsyncMock(return_value=normalize_qqcc_config(None)),
            "private_bot_provisioning_enabled": False,
        },
        user_data={},
    )
    return context, tenant_bot


def _update(reply_text):
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=12345,
            username="visitor",
            full_name="Visitor",
            language_code="zh",
        ),
        message=SimpleNamespace(reply_text=reply_text),
    )


@pytest.mark.asyncio
async def test_first_entry_via_private_bot_allows_joined_user_through_official_checker(
    monkeypatch,
):
    monkeypatch.setattr("src.utils.REQUIRED_CHANNEL_ID", "-100123")
    checker = AsyncMock(return_value=True)
    context, tenant_bot = _private_context(checker=checker)
    reply_text = AsyncMock()
    permission = SimpleNamespace(
        check_access=AsyncMock(return_value=None),
        ensure_user=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(commands, "permission_service", permission)

    await commands.start(_update(reply_text), context)

    checker.assert_awaited_once_with(12345)
    tenant_bot.get_chat_member.assert_not_awaited()
    permission.check_access.assert_awaited_once_with(
        12345,
        "visitor",
        "Visitor",
        True,
    )
    permission.ensure_user.assert_awaited_once()
    reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_entry_via_private_bot_rejects_user_not_in_official_channel(
    monkeypatch,
):
    monkeypatch.setattr("src.utils.REQUIRED_CHANNEL_ID", "-100123")
    checker = AsyncMock(return_value=False)
    context, tenant_bot = _private_context(checker=checker)
    reply_text = AsyncMock()

    async def deny_unjoined(_tg_id, _username, _full_name, is_member):
        assert is_member is False
        raise AccessDeniedError()

    permission = SimpleNamespace(
        check_access=AsyncMock(side_effect=deny_unjoined),
        ensure_user=AsyncMock(),
    )
    monkeypatch.setattr(commands, "permission_service", permission)

    with pytest.raises(AccessDeniedError):
        await commands.start(_update(reply_text), context)

    checker.assert_awaited_once_with(12345)
    tenant_bot.get_chat_member.assert_not_awaited()
    permission.ensure_user.assert_not_awaited()
    reply_text.assert_not_awaited()
