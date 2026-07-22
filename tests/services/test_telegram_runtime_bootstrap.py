from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from telegram import ChatMember, ChatMemberRestricted, File, Poll
from telegram.request import HTTPXRequest

from src.services import telegram_runtime_bootstrap as runtime


def test_telegram_runtime_urls_fail_closed_and_accept_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_API_BASE_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_FILE_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="TELEGRAM_API_BASE_URL"):
        runtime.resolve_telegram_api_base_url()
    with pytest.raises(RuntimeError, match="TELEGRAM_FILE_BASE_URL"):
        runtime.resolve_telegram_file_base_url()

    monkeypatch.setenv("TELEGRAM_API_BASE_URL", "http://local-api:8081/")
    monkeypatch.setenv("TELEGRAM_FILE_BASE_URL", "http://local-file:8082/")

    assert runtime.resolve_telegram_api_base_url() == "http://local-api:8081"
    assert runtime.resolve_telegram_file_base_url() == "http://local-file:8082"
    assert runtime.build_telegram_bot_base_url() == "http://local-api:8081/bot"


@pytest.mark.parametrize(
    "value",
    [
        "telegram-api.internal:8081",
        "ftp://telegram.example.com",
        "file:///tmp/telegram",
        "http:///missing-host",
    ],
)
def test_telegram_api_base_url_rejects_invalid_urls(monkeypatch, value):
    monkeypatch.setenv("TELEGRAM_API_BASE_URL", value)

    with pytest.raises(RuntimeError, match="TELEGRAM_API_BASE_URL"):
        runtime.resolve_telegram_api_base_url()


def test_build_telegram_httpx_request_uses_expected_timeouts():
    request = runtime.build_telegram_httpx_request(
        connect_timeout=11.0,
        read_timeout=22.0,
        write_timeout=33.0,
        connection_pool_size=44,
    )

    assert isinstance(request, HTTPXRequest)
    assert request.read_timeout == 22.0


def test_install_telegram_runtime_patches_is_idempotent_and_adds_poll_default(
    monkeypatch,
):
    original_file_download = File.download_to_drive
    original_poll_de_json = Poll.de_json
    original_restricted_member_de_json = ChatMemberRestricted.de_json
    captured = {}

    def fake_poll_de_json(data, bot=None):
        captured.update(data)
        return data

    monkeypatch.setattr(runtime, "_PATCHES_INSTALLED", False)
    monkeypatch.setattr(runtime, "_ORIGINAL_POLL_DE_JSON", fake_poll_de_json)

    try:
        runtime.install_telegram_runtime_patches()
        first_download_patch = File.download_to_drive
        first_poll_patch = Poll.__dict__["de_json"]

        runtime.install_telegram_runtime_patches()

        assert File.download_to_drive is first_download_patch
        assert Poll.__dict__["de_json"] is first_poll_patch

        Poll.de_json({"id": "poll-id"}, bot=None)
        assert captured["members_only"] is False
    finally:
        File.download_to_drive = original_file_download
        Poll.de_json = original_poll_de_json
        ChatMemberRestricted.de_json = original_restricted_member_de_json
        runtime._PATCHES_INSTALLED = False


@pytest.mark.skipif(
    not hasattr(ChatMemberRestricted, "can_react_to_messages"),
    reason="requires python-telegram-bot 22.8",
)
def test_install_telegram_runtime_patches_accepts_legacy_restricted_member_payload(
    monkeypatch,
):
    original_de_json = ChatMemberRestricted.de_json
    payload = {
        "status": "restricted",
        "user": {"id": 1, "is_bot": True, "first_name": "Main Bot"},
        "is_member": True,
        "can_change_info": False,
        "can_invite_users": True,
        "can_pin_messages": False,
        "can_send_messages": True,
        "can_send_polls": True,
        "can_send_other_messages": True,
        "can_add_web_page_previews": True,
        "can_manage_topics": False,
        "until_date": 0,
        "can_send_audios": True,
        "can_send_documents": True,
        "can_send_photos": True,
        "can_send_videos": True,
        "can_send_video_notes": True,
        "can_send_voice_notes": True,
        "can_edit_tag": False,
    }

    monkeypatch.setattr(runtime, "_PATCHES_INSTALLED", False)

    try:
        runtime.install_telegram_runtime_patches()

        member = ChatMember.de_json(payload)

        assert isinstance(member, ChatMemberRestricted)
        assert member.can_react_to_messages is True
        assert "can_react_to_messages" not in payload
    finally:
        ChatMemberRestricted.de_json = original_de_json
        runtime._PATCHES_INSTALLED = False


@pytest.mark.asyncio
async def test_inject_bot_language_context_uses_context_then_native_language(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.services.redis_client.redis_client",
        SimpleNamespace(redis=None),
    )
    logger = SimpleNamespace(info=MagicMock(), warning=MagicMock())
    context = SimpleNamespace(user_data={"language_code": "en"})
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123, language_code="zh-CN"),
        callback_query=None,
    )

    lang = await runtime.inject_bot_language_context(
        update,
        context,
        logger=logger,
    )

    assert lang == "en"
    assert context.lang == "en"
    assert callable(context.t)


@pytest.mark.asyncio
async def test_inject_bot_language_context_falls_back_to_native_language(
    monkeypatch,
):
    monkeypatch.setattr(
        "src.services.redis_client.redis_client",
        SimpleNamespace(redis=None),
    )
    logger = SimpleNamespace(info=MagicMock(), warning=MagicMock())
    context = SimpleNamespace(user_data={})
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=123, language_code="en-US"),
        callback_query=SimpleNamespace(data="noop"),
    )

    lang = await runtime.inject_bot_language_context(
        update,
        context,
        logger=logger,
        callback_log_label="test callback",
    )

    assert lang == "en"
    assert context.user_data["language_code"] == "en"
    assert logger.info.call_args.args == ("test callback: %s", "noop")
