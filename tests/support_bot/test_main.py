from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from support_bot.main import (
    CATEGORY_PROMPTS,
    CATEGORY_BY_TEXT,
    FINISH_CALLBACK_PREFIX,
    KEYBOARD,
    MAX_ATTACHMENT_BYTES,
    SUBMISSION_TIMEOUT_SECONDS,
    WELCOME,
    _store_attachment,
    _validate_notification_bot_identity,
    _validate_notification_bot_tokens,
)


def test_support_start_copy_includes_recharge_evidence_guidance():
    assert "付款截图" in WELCOME
    assert "套餐" in WELCOME
    assert "商业合作" in WELCOME
    assert "选择分类后" in WELCOME
    assert "Bot Token" in WELCOME


def test_support_category_buttons_map_to_persisted_categories():
    assert CATEGORY_BY_TEXT == {
        "充值问题": "recharge",
        "Bug反馈": "bug",
        "意见反馈": "suggestion",
        "商业合作": "business",
    }

    assert tuple(tuple(button.text for button in row) for row in KEYBOARD.keyboard) == (
        ("充值问题", "Bug反馈"),
        ("意见反馈", "商业合作"),
    )


def test_each_support_category_prompts_user_to_send_details():
    assert set(CATEGORY_PROMPTS) == {"recharge", "bug", "suggestion", "business"}
    for prompt in CATEGORY_PROMPTS.values():
        assert "请" in prompt
        assert "发送" in prompt


def test_submission_timeout_and_finish_callback_contract():
    assert SUBMISSION_TIMEOUT_SECONDS == 300
    assert FINISH_CALLBACK_PREFIX == "support_finish:"


def test_support_and_notification_bot_tokens_must_be_distinct():
    with pytest.raises(RuntimeError, match="must be different"):
        _validate_notification_bot_tokens(
            support_token="same-token",
            notification_token="same-token",
        )


def test_notification_sender_identity_is_pinned_to_qq_notification_bot():
    _validate_notification_bot_identity(
        SimpleNamespace(username="qq_notification_bot")
    )

    with pytest.raises(RuntimeError, match="expected bot"):
        _validate_notification_bot_identity(SimpleNamespace(username="other_bot"))


@pytest.mark.asyncio
async def test_support_runtime_initializes_outbound_notification_bot_and_dispatcher(
    monkeypatch,
):
    from support_bot import main as support_main

    notification_bot = SimpleNamespace(
        username="qq_notification_bot",
        initialize=AsyncMock(),
        shutdown=AsyncMock(),
        send_message=AsyncMock(),
    )
    job_queue = SimpleNamespace(run_repeating=Mock())
    application = SimpleNamespace(
        bot_data={support_main.NOTIFICATION_BOT_DATA_KEY: notification_bot},
        job_queue=job_queue,
    )
    dispatcher = SimpleNamespace()
    dispatcher_factory = Mock(return_value=dispatcher)
    monkeypatch.setattr(support_main, "init_db", AsyncMock())
    monkeypatch.setattr(
        support_main,
        "SupportNotificationDispatcher",
        dispatcher_factory,
    )

    await support_main._post_init(application)

    notification_bot.initialize.assert_awaited_once()
    dispatcher_factory.assert_called_once()
    assert (
        dispatcher_factory.call_args.kwargs["send_message"]
        == notification_bot.send_message
    )
    assert (
        application.bot_data[support_main.NOTIFICATION_DISPATCHER_DATA_KEY]
        is dispatcher
    )
    job_queue.run_repeating.assert_called_once()

    await support_main._post_shutdown(application)
    notification_bot.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_oversized_support_attachment_is_rejected_before_download():
    message = SimpleNamespace(
        photo=[],
        document=SimpleNamespace(
            file_size=MAX_ATTACHMENT_BYTES + 1,
            file_unique_id="large",
            file_name="large.zip",
            mime_type="application/zip",
        ),
    )
    context = SimpleNamespace(
        bot=SimpleNamespace(
            get_file=lambda *_args: pytest.fail("oversized file must not download")
        )
    )

    attachments, error = await _store_attachment(message, context)

    assert attachments == []
    assert "20MB" in error


@pytest.mark.asyncio
async def test_support_photo_uses_local_api_download_and_uploads_to_private_r2(
    monkeypatch,
):
    uploaded = {}

    class FakeR2:
        def put_object(self, **kwargs):
            uploaded.update(kwargs)

    async def get_file(file_id):
        assert file_id == "photo-file-id"
        return SimpleNamespace(file_path="/local/photo.jpg")

    async def download_bytes(remote):
        assert remote.file_path == "/local/photo.jpg"
        return b"photo-data"

    from support_bot import main as support_main

    monkeypatch.setattr(support_main, "download_attachment_bytes", download_bytes)
    monkeypatch.setattr(
        support_main,
        "storage",
        SimpleNamespace(
            r2_client=FakeR2(),
            r2_bucket="private-support",
            mark_r2_object_exists=lambda key: uploaded.setdefault("marked", key),
        ),
    )
    message = SimpleNamespace(
        photo=[
            SimpleNamespace(
                file_size=len(b"photo-data"),
                file_unique_id="unique-photo",
                file_id="photo-file-id",
            )
        ],
        document=None,
        from_user=SimpleNamespace(id=123),
        message_id=456,
    )
    context = SimpleNamespace(bot=SimpleNamespace(get_file=get_file))

    attachments, error = await _store_attachment(message, context)

    assert error is None
    assert uploaded["Bucket"] == "private-support"
    assert uploaded["Key"] == "support/123/456/photo-unique-photo.jpg"
    assert uploaded["Body"] == b"photo-data"
    assert uploaded["ContentType"] == "image/jpeg"
    assert attachments == [
        {
            "object_key": "support/123/456/photo-unique-photo.jpg",
            "filename": "photo-unique-photo.jpg",
            "mime_type": "image/jpeg",
            "telegram_file_id": "photo-file-id",
            "size_bytes": len(b"photo-data"),
        }
    ]


@pytest.mark.asyncio
async def test_category_button_selects_ticket_then_prompts_for_content(monkeypatch):
    from support_bot import main as support_main

    message = SimpleNamespace(
        text="商业合作",
        caption=None,
        photo=[],
        document=None,
        from_user=SimpleNamespace(id=123),
        message_id=789,
        date=None,
        chat_id=123,
        reply_text=AsyncMock(),
    )
    monkeypatch.setattr(
        support_main,
        "_store_attachment",
        AsyncMock(side_effect=AssertionError("category selection has no attachment")),
    )
    context = SimpleNamespace(
        user_data={},
        job_queue=SimpleNamespace(
            get_jobs_by_name=lambda _name: (),
            run_once=lambda *_args, **_kwargs: None,
        ),
    )

    await support_main.receive(
        SimpleNamespace(effective_message=message),
        context,
    )

    reply = message.reply_text.await_args.args[0]
    assert "已选择【商业合作】" in reply
    assert "请发送" in reply
    assert "工单 #" not in reply
    assert context.user_data["support_submission"]["category"] == "business"
    assert context.user_data["support_submission"]["messages"] == []


@pytest.mark.asyncio
async def test_content_is_buffered_and_acknowledged_with_finish_button(monkeypatch):
    from support_bot import main as support_main

    message = SimpleNamespace(
        text="功能打不开",
        caption=None,
        photo=[],
        document=None,
        from_user=SimpleNamespace(
            id=123,
            username="tester",
            full_name="Test User",
            language_code="zh",
        ),
        message_id=790,
        date=None,
        chat_id=123,
        reply_text=AsyncMock(),
    )
    context = SimpleNamespace(
        user_data={},
        job_queue=SimpleNamespace(
            get_jobs_by_name=lambda _name: (),
            run_once=lambda *_args, **_kwargs: None,
        ),
    )
    monkeypatch.setattr(
        support_main, "_store_attachment", AsyncMock(return_value=([], None))
    )

    await support_main.receive(SimpleNamespace(effective_message=message), context)

    draft = context.user_data["support_submission"]
    assert draft["category"] == "uncategorized"
    assert draft["messages"][0]["body"] == "功能打不开"
    assert "已记录" in message.reply_text.await_args.args[0]
    markup = message.reply_text.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == (
        f"{FINISH_CALLBACK_PREFIX}{draft['id']}"
    )


@pytest.mark.asyncio
async def test_attachment_failure_keeps_draft_open_without_recording_message(
    monkeypatch,
):
    from support_bot import main as support_main

    draft = {
        "id": "draft-1",
        "category": "bug",
        "messages": [],
        "user": {
            "id": 123,
            "username": "tester",
            "full_name": "Test User",
            "language_code": "zh",
        },
        "chat_id": 123,
    }
    message = SimpleNamespace(
        text=None,
        caption=None,
        photo=[SimpleNamespace()],
        document=None,
        from_user=SimpleNamespace(id=123),
        message_id=791,
        date=None,
        chat_id=123,
        reply_text=AsyncMock(),
    )
    context = SimpleNamespace(user_data={"support_submission": draft}, job_queue=None)
    monkeypatch.setattr(
        support_main,
        "_store_attachment",
        AsyncMock(return_value=([], "附件暂时保存失败，请稍后重新发送。")),
    )

    await support_main.receive(SimpleNamespace(effective_message=message), context)

    assert draft["messages"] == []
    assert "重新发送" in message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_switching_category_finalizes_previous_content_before_new_draft(
    monkeypatch,
):
    from support_bot import main as support_main

    old_draft = {
        "id": "old-draft",
        "category": "bug",
        "messages": [{"body": "old"}],
        "user": {
            "id": 123,
            "username": "tester",
            "full_name": "Test User",
            "language_code": "zh",
        },
        "chat_id": 123,
    }
    message = SimpleNamespace(
        text="意见反馈",
        caption=None,
        photo=[],
        document=None,
        from_user=SimpleNamespace(id=123),
        message_id=792,
        date=None,
        chat_id=123,
        reply_text=AsyncMock(),
    )
    context = SimpleNamespace(
        user_data={"support_submission": old_draft},
        job_queue=SimpleNamespace(
            get_jobs_by_name=lambda _name: (),
            run_once=lambda *_args, **_kwargs: None,
        ),
    )
    finalize = AsyncMock(return_value=SimpleNamespace(id=88))
    monkeypatch.setattr(support_main, "_persist_active_submission", finalize)

    await support_main.receive(SimpleNamespace(effective_message=message), context)

    finalize.assert_awaited_once_with(context)
    assert context.user_data["support_submission"]["category"] == "suggestion"
    replies = [call.args[0] for call in message.reply_text.await_args_list]
    assert any("工单 #88" in reply for reply in replies)
    assert any("已选择【意见反馈】" in reply for reply in replies)


@pytest.mark.asyncio
async def test_same_category_button_keeps_current_submission(monkeypatch):
    from support_bot import main as support_main

    draft = {
        "id": "same-draft",
        "category": "bug",
        "messages": [{"body": "existing"}],
        "user": {"id": 123},
        "chat_id": 123,
    }
    message = SimpleNamespace(
        text="Bug反馈",
        caption=None,
        photo=[],
        document=None,
        from_user=SimpleNamespace(id=123),
        message_id=793,
        date=None,
        chat_id=123,
        reply_text=AsyncMock(),
    )
    context = SimpleNamespace(
        user_data={"support_submission": draft},
        job_queue=SimpleNamespace(
            get_jobs_by_name=lambda _name: (),
            run_once=lambda *_args, **_kwargs: None,
        ),
    )
    persist = AsyncMock()
    monkeypatch.setattr(support_main, "_persist_active_submission", persist)

    await support_main.receive(SimpleNamespace(effective_message=message), context)

    persist.assert_not_awaited()
    assert context.user_data["support_submission"] is draft
    assert "仍在进行" in message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_finish_callback_answers_and_submits_active_draft(monkeypatch):
    from support_bot import main as support_main

    draft = {
        "id": "finish-draft",
        "category": "recharge",
        "messages": [{"body": "payment"}],
        "user": {"id": 123},
        "chat_id": 123,
    }
    query = SimpleNamespace(
        data=f"{FINISH_CALLBACK_PREFIX}{draft['id']}",
        answer=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace(user_data={"support_submission": draft})
    persist = AsyncMock(return_value=SimpleNamespace(id=91))
    monkeypatch.setattr(support_main, "_persist_active_submission", persist)

    await support_main.finish_submission(
        SimpleNamespace(callback_query=query),
        context,
    )

    query.answer.assert_awaited_once()
    persist.assert_awaited_once_with(context)
    assert "工单 #91 已提交" in query.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_stale_finish_callback_is_idempotent(monkeypatch):
    from support_bot import main as support_main

    query = SimpleNamespace(
        data=f"{FINISH_CALLBACK_PREFIX}old-draft",
        answer=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )
    context = SimpleNamespace(user_data={})
    persist = AsyncMock()
    monkeypatch.setattr(support_main, "_persist_active_submission", persist)

    await support_main.finish_submission(
        SimpleNamespace(callback_query=query),
        context,
    )

    query.answer.assert_awaited_once()
    persist.assert_not_awaited()
    assert "已结束" in query.message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_empty_submission_timeout_discards_without_ticket(monkeypatch):
    from support_bot import main as support_main

    draft = {
        "id": "empty-draft",
        "category": "business",
        "messages": [],
        "user": {"id": 123},
        "chat_id": 123,
    }
    context = SimpleNamespace(
        user_data={"support_submission": draft},
        job=SimpleNamespace(data={"submission_id": draft["id"]}),
        job_queue=None,
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    persist = AsyncMock()
    monkeypatch.setattr(support_main, "_persist_active_submission", persist)

    await support_main._timeout_submission(context)

    persist.assert_not_awaited()
    assert "support_submission" not in context.user_data
    assert "没有收到" in context.bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_content_timeout_submits_ticket(monkeypatch):
    from support_bot import main as support_main

    draft = {
        "id": "timed-draft",
        "category": "suggestion",
        "messages": [{"body": "idea"}],
        "user": {"id": 123},
        "chat_id": 123,
    }
    context = SimpleNamespace(
        user_data={"support_submission": draft},
        job=SimpleNamespace(data={"submission_id": draft["id"]}),
        job_queue=None,
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    monkeypatch.setattr(
        support_main,
        "_persist_active_submission",
        AsyncMock(return_value=SimpleNamespace(id=92)),
    )

    await support_main._timeout_submission(context)

    assert "工单 #92" in context.bot.send_message.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_database_failure_preserves_active_draft(monkeypatch):
    from support_bot import main as support_main

    class SessionContext:
        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, *_args):
            return None

    draft = {
        "id": "retry-draft",
        "category": "bug",
        "messages": [{"body": "error"}],
        "user": {
            "id": 123,
            "username": None,
            "full_name": None,
            "language_code": None,
        },
        "chat_id": 123,
        "finalizing": False,
    }
    context = SimpleNamespace(
        user_data={"support_submission": draft},
        job_queue=None,
    )
    monkeypatch.setattr(support_main, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(
        support_main,
        "finalize_ticket_submission",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await support_main._persist_active_submission(context)

    assert context.user_data["support_submission"] is draft
    assert draft["finalizing"] is False


@pytest.mark.asyncio
async def test_persisted_submission_returns_without_synchronous_telegram_delivery(
    monkeypatch,
):
    from support_bot import main as support_main

    session = SimpleNamespace()

    class SessionContext:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_args):
            return None

    draft = {
        "id": "notify-draft",
        "category": "bug",
        "messages": [{"body": "页面打不开", "attachments": []}],
        "user": {
            "id": 123,
            "username": "reporter",
            "full_name": "Report User",
            "language_code": "zh",
        },
        "chat_id": 123,
        "finalizing": False,
    }
    context = SimpleNamespace(
        user_data={"support_submission": draft},
        job_queue=None,
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    ticket = SimpleNamespace(id=96)
    finalize = AsyncMock(return_value=ticket)
    monkeypatch.setattr(support_main, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(support_main, "finalize_ticket_submission", finalize)

    result = await support_main._persist_active_submission(context)

    assert result is ticket
    context.bot.send_message.assert_not_awaited()
    assert "support_submission" not in context.user_data


@pytest.mark.asyncio
async def test_content_is_not_acknowledged_while_submission_is_finalizing(monkeypatch):
    from support_bot import main as support_main

    draft = {
        "id": "busy-draft",
        "category": "bug",
        "messages": [{"body": "existing"}],
        "user": {"id": 123},
        "chat_id": 123,
        "finalizing": True,
    }
    message = SimpleNamespace(
        text="late content",
        caption=None,
        photo=[],
        document=None,
        from_user=SimpleNamespace(id=123),
        message_id=794,
        date=None,
        chat_id=123,
        reply_text=AsyncMock(),
    )
    context = SimpleNamespace(user_data={"support_submission": draft})
    store_attachment = AsyncMock()
    monkeypatch.setattr(support_main, "_store_attachment", store_attachment)

    await support_main.receive(SimpleNamespace(effective_message=message), context)

    store_attachment.assert_not_awaited()
    assert draft["messages"] == [{"body": "existing"}]
    assert "重新发送" in message.reply_text.await_args.args[0]
