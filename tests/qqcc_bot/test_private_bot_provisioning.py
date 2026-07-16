from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.ext import ConversationHandler

from qqcc_bot import commands, keyboards
from qqcc_bot.private_bot_fsm import (
    _owner_webapp_url,
    private_bot_group_redirect,
    receive_private_bot_token,
    start_private_bot_provisioning,
)
from src.services.private_qqcc_bot_service import PrivateBotProvisionResult
from src.services.qqcc_config_service import normalize_qqcc_config


@pytest.fixture(autouse=True)
def _enable_private_bot_config(monkeypatch):
    monkeypatch.setattr(
        "qqcc_bot.private_bot_fsm.load_runtime_qqcc_config",
        AsyncMock(return_value=normalize_qqcc_config(None)),
    )


def _keyboard_texts(markup):
    return [[button.text for button in row] for row in markup.keyboard]


def test_private_bot_entry_is_only_rendered_by_official_qqcc_bot():
    official = _keyboard_texts(
        keyboards.get_qqcc_main_menu_keyboard(
            "zh",
            include_private_bot_entry=True,
        )
    )
    tenant = _keyboard_texts(
        keyboards.get_qqcc_main_menu_keyboard(
            "zh",
            include_private_bot_entry=False,
        )
    )

    assert ["私有bot"] in official
    assert ["私有bot"] not in tenant


def test_private_bot_entry_is_hidden_until_rollout_gate_is_enabled():
    context = SimpleNamespace(
        lang="zh",
        bot_data={
            "bot_client_type": "bot:qqcc",
            "private_bot_provisioning_enabled": False,
        },
    )

    texts = _keyboard_texts(commands._main_menu_keyboard(context, None))

    assert ["私有bot"] not in texts


def test_private_bot_entry_is_hidden_when_admin_menu_switch_is_off():
    config = normalize_qqcc_config({"main_buttons": {"private_bot": False}})

    texts = _keyboard_texts(
        keyboards.get_qqcc_main_menu_keyboard(
            "zh",
            config,
            include_private_bot_entry=True,
        )
    )

    assert ["私有bot"] not in texts


@pytest.mark.asyncio
async def test_stale_private_bot_entry_is_blocked_when_admin_switch_is_off(
    monkeypatch,
):
    monkeypatch.setattr(
        "qqcc_bot.private_bot_fsm.load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {"main_buttons": {"private_bot": False}}
            )
        ),
    )
    resolve_owner = AsyncMock()
    monkeypatch.setattr("qqcc_bot.private_bot_fsm._resolve_owner", resolve_owner)
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="private"),
    )
    context = SimpleNamespace(
        user_data={},
        t=lambda key, **_kwargs: {
            "qqcc.feature_disabled": "功能暂未开放",
        }.get(key, key),
    )

    result = await start_private_bot_provisioning(update, context)

    assert result == ConversationHandler.END
    resolve_owner.assert_not_awaited()
    message.reply_text.assert_awaited_once_with("功能暂未开放")


@pytest.mark.asyncio
async def test_stale_group_private_bot_entry_uses_disabled_reply_when_switch_is_off(
    monkeypatch,
):
    monkeypatch.setattr(
        "qqcc_bot.private_bot_fsm.load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {"main_buttons": {"private_bot": False}}
            )
        ),
    )
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_message=message)
    context = SimpleNamespace(
        t=lambda key, **_kwargs: {
            "qqcc.feature_disabled": "功能暂未开放",
        }.get(key, key),
    )

    result = await private_bot_group_redirect(update, context)

    assert result == ConversationHandler.END
    message.reply_text.assert_awaited_once_with("功能暂未开放")


@pytest.mark.asyncio
async def test_in_progress_private_bot_token_is_not_provisioned_after_switch_off(
    monkeypatch,
):
    monkeypatch.setattr(
        "qqcc_bot.private_bot_fsm.load_runtime_qqcc_config",
        AsyncMock(
            return_value=normalize_qqcc_config(
                {"main_buttons": {"private_bot": False}}
            )
        ),
    )
    message = SimpleNamespace(
        text="123:super-secret-token",
        delete=AsyncMock(),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="private"),
    )
    context = SimpleNamespace(
        user_data={"private_bot_owner_id": 42},
        t=lambda key, **_kwargs: {
            "qqcc.feature_disabled": "功能暂未开放",
        }.get(key, key),
    )
    provision = AsyncMock()

    result = await receive_private_bot_token(
        update,
        context,
        provision_func=provision,
    )

    assert result == ConversationHandler.END
    message.delete.assert_awaited_once_with()
    provision.assert_not_awaited()
    assert "private_bot_owner_id" not in context.user_data
    message.reply_text.assert_awaited_once_with("功能暂未开放")


def test_owner_ticket_uses_browser_fragment_and_requires_expected_host(monkeypatch):
    monkeypatch.setenv(
        "PRIVATE_QQCC_BOT_OWNER_WEBAPP_URL",
        "https://private.example.test/manage?source=telegram",
    )
    monkeypatch.setenv("PRIVATE_QQCC_BOT_OWNER_HOST", "private.example.test")

    url = _owner_webapp_url("one-time-secret-ticket")

    assert url == (
        "https://private.example.test/manage?source=telegram"
        "#ticket=one-time-secret-ticket"
    )
    assert "ticket=" not in url.split("#", 1)[0]

    monkeypatch.setenv("PRIVATE_QQCC_BOT_OWNER_HOST", "other.example.test")
    assert _owner_webapp_url("one-time-secret-ticket") is None


@pytest.mark.asyncio
async def test_private_bot_token_message_is_deleted_and_never_echoed(monkeypatch):
    delete = AsyncMock()
    reply_text = AsyncMock()
    message = SimpleNamespace(
        text="123:super-secret-token",
        delete=delete,
        reply_text=reply_text,
    )
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="private"),
        effective_user=SimpleNamespace(
            id=1001,
            username="owner",
            full_name="Owner",
            language_code="zh",
        ),
    )
    context = SimpleNamespace(
        user_data={"private_bot_owner_id": 42},
        lang="zh",
        t=lambda key, **_kwargs: key,
    )
    provision = AsyncMock(
        return_value=PrivateBotProvisionResult(
            private_bot_id=7,
            telegram_bot_id=123,
            telegram_username="tenant_bot",
            runtime_status="active",
            created=True,
        )
    )
    management_markup = SimpleNamespace()

    result = await receive_private_bot_token(
        update,
        context,
        provision_func=provision,
        management_markup_func=AsyncMock(return_value=management_markup),
    )

    assert result == ConversationHandler.END
    delete.assert_awaited_once_with()
    assert provision.await_args.kwargs["token"] == "123:super-secret-token"
    response_text = reply_text.await_args.args[0]
    assert "super-secret-token" not in response_text
    assert reply_text.await_args.kwargs["reply_markup"] is management_markup
    assert "private_bot_owner_id" not in context.user_data


@pytest.mark.asyncio
async def test_ticket_outage_does_not_turn_successful_provision_into_failure():
    message = SimpleNamespace(
        text="123:super-secret-token",
        delete=AsyncMock(),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="private"),
        effective_user=SimpleNamespace(id=1001),
    )
    context = SimpleNamespace(
        user_data={"private_bot_owner_id": 42},
        lang="zh",
        t=lambda key, **_kwargs: key,
    )
    provision = AsyncMock(
        return_value=PrivateBotProvisionResult(
            private_bot_id=7,
            telegram_bot_id=123,
            telegram_username="tenant_bot",
            runtime_status="active",
            created=True,
        )
    )

    await receive_private_bot_token(
        update,
        context,
        provision_func=provision,
        management_markup_func=AsyncMock(side_effect=ConnectionError("redis down")),
    )

    assert message.reply_text.await_args.args[0] == "qqcc.private_bot.activated"
    assert message.reply_text.await_args.kwargs["reply_markup"] is None


@pytest.mark.asyncio
async def test_token_is_deleted_before_owner_lookup_and_unexpected_errors_are_sanitized(
    monkeypatch,
    caplog,
):
    events = []
    token = "123:must-never-appear"

    async def _delete():
        events.append("delete")
        raise RuntimeError("cannot delete")

    async def _resolve_owner(_update):
        events.append("owner")
        return None

    reply_text = AsyncMock()
    message = SimpleNamespace(text=token, delete=_delete, reply_text=reply_text)
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="private"),
        effective_user=SimpleNamespace(
            id=1001,
            username="owner",
            full_name="Owner",
            language_code="zh",
        ),
    )
    context = SimpleNamespace(
        user_data={},
        lang="zh",
        t=lambda key, **_kwargs: key,
    )
    monkeypatch.setattr("qqcc_bot.private_bot_fsm._resolve_owner", _resolve_owner)

    await receive_private_bot_token(update, context)

    assert events == ["delete", "owner"]
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    response_text = reply_text.await_args.args[0]
    assert token not in rendered
    assert token not in response_text
    assert "qqcc.private_bot.token_delete_warning" in response_text


@pytest.mark.asyncio
async def test_unexpected_provision_error_does_not_log_token(caplog):
    token = "123:must-never-appear"
    message = SimpleNamespace(
        text=token,
        delete=AsyncMock(),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="private"),
        effective_user=SimpleNamespace(),
    )
    context = SimpleNamespace(
        user_data={"private_bot_owner_id": 42},
        lang="zh",
        t=lambda key, **_kwargs: key,
    )

    await receive_private_bot_token(
        update,
        context,
        provision_func=AsyncMock(side_effect=RuntimeError(f"failed for {token}")),
    )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in rendered
    assert token not in message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_group_chat_never_consumes_or_processes_private_bot_token():
    token = "123:must-not-be-consumed"
    message = SimpleNamespace(
        text=token,
        delete=AsyncMock(),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="group"),
        effective_user=SimpleNamespace(),
    )
    context = SimpleNamespace(
        user_data={"private_bot_owner_id": 42},
        lang="zh",
        t=lambda key, **_kwargs: key,
    )
    provision = AsyncMock()

    await receive_private_bot_token(
        update,
        context,
        provision_func=provision,
    )

    provision.assert_not_awaited()
    message.delete.assert_not_awaited()
    assert token not in message.reply_text.await_args.args[0]
    assert "private_chat_only" in message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_group_entry_never_resolves_owner_or_issues_management_ticket(monkeypatch):
    resolve_owner = AsyncMock()
    monkeypatch.setattr("qqcc_bot.private_bot_fsm._resolve_owner", resolve_owner)
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=SimpleNamespace(type="supergroup"),
    )
    context = SimpleNamespace(
        user_data={},
        t=lambda key, **_kwargs: key,
    )

    result = await start_private_bot_provisioning(update, context)

    assert result == ConversationHandler.END
    resolve_owner.assert_not_awaited()
    assert "private_chat_only" in message.reply_text.await_args.args[0]
