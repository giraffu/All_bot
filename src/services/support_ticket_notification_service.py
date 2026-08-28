from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
import logging
from typing import Any

from sqlalchemy import delete, select

from src.database.models import SupportNotificationRecipient, SupportTicket

logger = logging.getLogger(__name__)

MAX_NOTIFICATION_RECIPIENTS = 20
TELEGRAM_MESSAGE_LIMIT = 4096
CATEGORY_LABELS = {
    "recharge": "充值问题",
    "bug": "Bug反馈",
    "suggestion": "意见反馈",
    "business": "商业合作",
    "uncategorized": "未分类",
}


async def list_support_notification_recipient_ids(db) -> list[int]:
    result = await db.execute(
        select(SupportNotificationRecipient).order_by(
            SupportNotificationRecipient.telegram_user_id
        )
    )
    return [int(item.telegram_user_id) for item in result.scalars().all()]


async def replace_support_notification_recipient_ids(
    db,
    telegram_user_ids: Sequence[int],
) -> list[int]:
    normalized: list[int] = []
    for raw_user_id in telegram_user_ids:
        if isinstance(raw_user_id, bool):
            raise ValueError("telegram user ID must be a positive integer")
        user_id = int(raw_user_id)
        if user_id <= 0:
            raise ValueError("telegram user ID must be a positive integer")
        normalized.append(user_id)
    normalized = sorted(set(normalized))
    if len(normalized) > MAX_NOTIFICATION_RECIPIENTS:
        raise ValueError(
            f"at most {MAX_NOTIFICATION_RECIPIENTS} notification recipients are allowed"
        )

    await db.execute(delete(SupportNotificationRecipient))
    db.add_all(
        [
            SupportNotificationRecipient(telegram_user_id=user_id)
            for user_id in normalized
        ]
    )
    await db.commit()
    return normalized


def build_support_ticket_notification(
    *,
    ticket: SupportTicket,
    messages: Sequence[dict[str, Any]],
) -> str:
    category = CATEGORY_LABELS.get(ticket.category, ticket.category)
    sender = ticket.full_name or (
        f"@{ticket.username}" if ticket.username else str(ticket.telegram_user_id)
    )
    lines = [
        f"新客服工单 #{ticket.id}",
        f"分类：{category}",
        f"用户：{sender}（TG {ticket.telegram_user_id}）",
        "",
        "提交内容：",
    ]
    for index, message in enumerate(messages, start=1):
        body = str(message.get("body") or "").strip()
        attachments = list(message.get("attachments") or [])
        content_parts = []
        if body:
            content_parts.append(body)
        for attachment in attachments:
            filename = str(attachment.get("filename") or "附件")
            content_parts.append(f"[附件] {filename}")
        if content_parts:
            lines.append(f"{index}. " + "\n".join(content_parts))

    text = "\n".join(lines)
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return text
    suffix = "\n…（内容过长，请到管理后台查看完整工单）"
    return text[: TELEGRAM_MESSAGE_LIMIT - len(suffix)] + suffix


async def notify_support_ticket_submission(
    db,
    *,
    ticket: SupportTicket,
    messages: Sequence[dict[str, Any]],
    send_message: Callable[..., Awaitable[Any]],
) -> None:
    recipient_ids = await list_support_notification_recipient_ids(db)
    if not recipient_ids:
        return
    text = build_support_ticket_notification(ticket=ticket, messages=messages)
    for recipient_id in recipient_ids:
        try:
            await send_message(chat_id=recipient_id, text=text)
        except Exception:
            logger.warning(
                "support ticket notification delivery failed: ticket_id=%s recipient_id=%s",
                ticket.id,
                recipient_id,
                exc_info=True,
            )
