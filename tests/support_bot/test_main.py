from types import SimpleNamespace

import pytest

from support_bot.main import (
    CATEGORY_BY_TEXT,
    MAX_ATTACHMENT_BYTES,
    WELCOME,
    _store_attachment,
)


def test_support_start_copy_includes_recharge_evidence_guidance():
    assert "付款截图" in WELCOME
    assert "套餐" in WELCOME
    assert "Bot Token" in WELCOME


def test_support_category_buttons_map_to_persisted_categories():
    assert CATEGORY_BY_TEXT == {
        "充值问题": "recharge",
        "Bug反馈": "bug",
        "意见反馈": "suggestion",
    }


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
