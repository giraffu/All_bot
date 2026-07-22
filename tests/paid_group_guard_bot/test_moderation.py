import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from paid_group_guard_bot.config import PaidGroupBotSettings
from paid_group_guard_bot.moderation import (
    PaidGroupModerationConfig,
    evaluate_moderation_decision,
)
from paid_group_guard_bot.moderation_handlers import handle_message_moderation


class _ConfigProvider:
    def __init__(self, config):
        self.config = config

    def load(self):
        return self.config


def _settings(tmp_path, **overrides):
    values = {
        "token": "token",
        "target_chat_id": -100123,
        "decline_unqualified": False,
        "dry_run": False,
        "moderation_config_file": str(tmp_path / "config.json"),
        "moderation_log_file": str(tmp_path / "moderation.jsonl"),
    }
    values.update(overrides)
    return PaidGroupBotSettings(**values)


def _update(
    *,
    chat_id=-100123,
    user_id=777,
    text=None,
    caption=None,
    entities=None,
    caption_entities=None,
):
    user = SimpleNamespace(
        id=user_id,
        username="paid_user",
        full_name="Paid User",
    )
    message = SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        from_user=user,
        message_id=42,
        text=text,
        caption=caption,
        entities=entities or [],
        caption_entities=caption_entities or [],
    )
    return SimpleNamespace(effective_message=message)


def _context(*, status="member", delete_side_effect=None, admin_side_effect=None):
    get_chat_member = AsyncMock(
        side_effect=admin_side_effect,
        return_value=SimpleNamespace(status=status),
    )
    delete_message = AsyncMock(side_effect=delete_side_effect)
    return SimpleNamespace(
        bot=SimpleNamespace(
            get_chat_member=get_chat_member,
            delete_message=delete_message,
        )
    )


def _read_events(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.asyncio
async def test_message_moderation_ignores_unexpected_group(tmp_path):
    settings = _settings(tmp_path)
    context = _context()

    await handle_message_moderation(
        _update(chat_id=-100999, text="https://spam.example"),
        context,
        settings=settings,
        config_provider=_ConfigProvider(PaidGroupModerationConfig()),
    )

    context.bot.get_chat_member.assert_not_awaited()
    context.bot.delete_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_moderation_keeps_admin_message(tmp_path):
    settings = _settings(tmp_path)
    context = _context(status="administrator")

    await handle_message_moderation(
        _update(text="https://spam.example"),
        context,
        settings=settings,
        config_provider=_ConfigProvider(PaidGroupModerationConfig()),
    )

    context.bot.delete_message.assert_not_awaited()
    assert _read_events(tmp_path / "moderation.jsonl") == []


@pytest.mark.asyncio
async def test_message_moderation_skips_admin_lookup_for_clean_message(tmp_path):
    settings = _settings(tmp_path)
    context = _context(status="member")

    await handle_message_moderation(
        _update(text="normal group chat"),
        context,
        settings=settings,
        config_provider=_ConfigProvider(PaidGroupModerationConfig()),
    )

    context.bot.get_chat_member.assert_not_awaited()
    context.bot.delete_message.assert_not_awaited()
    assert _read_events(tmp_path / "moderation.jsonl") == []


@pytest.mark.asyncio
async def test_message_moderation_deletes_non_admin_link_and_logs(tmp_path):
    settings = _settings(tmp_path)
    context = _context(status="member")

    await handle_message_moderation(
        _update(text="look at https://spam.example/x"),
        context,
        settings=settings,
        config_provider=_ConfigProvider(PaidGroupModerationConfig()),
    )

    context.bot.delete_message.assert_awaited_once_with(
        chat_id=-100123,
        message_id=42,
    )
    events = _read_events(tmp_path / "moderation.jsonl")
    assert len(events) == 1
    assert events[0]["action"] == "deleted"
    assert events[0]["reason"] == "link"
    assert events[0]["user_id"] == 777
    assert "https://spam.example/x" in events[0]["matched_value"]


@pytest.mark.asyncio
async def test_message_moderation_allows_configured_domain(tmp_path):
    settings = _settings(tmp_path)
    context = _context(status="member")

    await handle_message_moderation(
        _update(text="official https://web.aivison.it.com/path"),
        context,
        settings=settings,
        config_provider=_ConfigProvider(
            PaidGroupModerationConfig(allowed_domains=("aivison.it.com",))
        ),
    )

    context.bot.delete_message.assert_not_awaited()
    assert _read_events(tmp_path / "moderation.jsonl") == []


@pytest.mark.asyncio
async def test_message_moderation_deletes_caption_forbidden_word(tmp_path):
    settings = _settings(tmp_path)
    context = _context(status="member")

    await handle_message_moderation(
        _update(caption="这里有违禁词"),
        context,
        settings=settings,
        config_provider=_ConfigProvider(
            PaidGroupModerationConfig(
                block_links=False,
                forbidden_words=("违禁词",),
            )
        ),
    )

    context.bot.delete_message.assert_awaited_once()
    events = _read_events(tmp_path / "moderation.jsonl")
    assert events[0]["reason"] == "forbidden_word"
    assert events[0]["matched_value"] == "违禁词"


@pytest.mark.asyncio
async def test_message_moderation_detects_text_link_entity(tmp_path):
    settings = _settings(tmp_path)
    context = _context(status="member")
    entity = SimpleNamespace(type="text_link", url="https://spam.example")

    await handle_message_moderation(
        _update(text="click me", entities=[entity]),
        context,
        settings=settings,
        config_provider=_ConfigProvider(PaidGroupModerationConfig()),
    )

    context.bot.delete_message.assert_awaited_once()
    events = _read_events(tmp_path / "moderation.jsonl")
    assert events[0]["reason"] == "link"
    assert events[0]["matched_value"] == "https://spam.example"


@pytest.mark.asyncio
async def test_message_moderation_dry_run_logs_without_delete(tmp_path):
    settings = _settings(tmp_path)
    context = _context(status="member")

    await handle_message_moderation(
        _update(text="www.spam.example"),
        context,
        settings=settings,
        config_provider=_ConfigProvider(PaidGroupModerationConfig(dry_run=True)),
    )

    context.bot.delete_message.assert_not_awaited()
    events = _read_events(tmp_path / "moderation.jsonl")
    assert events[0]["action"] == "dry_run"


@pytest.mark.asyncio
async def test_message_moderation_delete_failure_is_logged_without_raising(tmp_path):
    settings = _settings(tmp_path)
    context = _context(
        status="member", delete_side_effect=RuntimeError("no permission")
    )

    await handle_message_moderation(
        _update(text="t.me/spam"),
        context,
        settings=settings,
        config_provider=_ConfigProvider(PaidGroupModerationConfig()),
    )

    events = _read_events(tmp_path / "moderation.jsonl")
    assert events[0]["action"] == "delete_failed"
    assert events[0]["error"] == "no permission"


@pytest.mark.asyncio
async def test_message_moderation_admin_check_failure_is_fail_open(tmp_path):
    settings = _settings(tmp_path)
    context = _context(admin_side_effect=RuntimeError("api unavailable"))

    await handle_message_moderation(
        _update(text="https://spam.example"),
        context,
        settings=settings,
        config_provider=_ConfigProvider(PaidGroupModerationConfig()),
    )

    context.bot.delete_message.assert_not_awaited()
    assert _read_events(tmp_path / "moderation.jsonl") == []


def test_evaluate_moderation_decision_matches_case_insensitive_words():
    decision = evaluate_moderation_decision(
        config=PaidGroupModerationConfig(
            block_links=False,
            forbidden_words=("SpamWord",),
        ),
        text="contains spamword",
    )

    assert decision.should_delete is True
    assert decision.reason == "forbidden_word"
    assert decision.matched_value == "SpamWord"
