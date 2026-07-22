from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from support_bot.main import (
    CATEGORY_PROMPTS,
    CATEGORY_BY_TEXT,
    KEYBOARD,
    MAX_ATTACHMENT_BYTES,
    WELCOME,
    _store_attachment,
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

    class SessionContext:
        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, *_args):
            return None

    message = SimpleNamespace(
        text="商业合作",
        caption=None,
        photo=[],
        document=None,
        from_user=SimpleNamespace(id=123),
        message_id=789,
        reply_text=AsyncMock(),
    )
    select_category = AsyncMock(return_value=SimpleNamespace(id=99))
    monkeypatch.setattr(support_main, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(support_main, "select_ticket_category", select_category)
    monkeypatch.setattr(
        support_main,
        "add_user_message",
        AsyncMock(side_effect=AssertionError("category selection is not a message")),
    )
    monkeypatch.setattr(
        support_main,
        "_store_attachment",
        AsyncMock(side_effect=AssertionError("category selection has no attachment")),
    )

    await support_main.receive(
        SimpleNamespace(effective_message=message),
        SimpleNamespace(),
    )

    select_category.assert_awaited_once()
    reply = message.reply_text.await_args.args[0]
    assert "已选择【商业合作】" in reply
    assert "请发送" in reply
    assert "工单 #99" in reply
