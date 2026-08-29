from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select

from src.database.models import SupportMessage, SupportTicket, User
from src.services.support_ticket_notification_service import (
    enqueue_support_ticket_notifications,
)

CATEGORIES = {"recharge", "bug", "suggestion", "business", "uncategorized"}
STATUSES = {"open", "processing", "resolved", "closed"}


async def finalize_ticket_submission(
    session,
    *,
    telegram_user_id: int,
    username: str | None,
    full_name: str | None,
    language_code: str | None,
    category: str,
    messages: Sequence[dict[str, Any]],
) -> SupportTicket:
    """Persist one completed support submission as a new ticket."""

    if not messages:
        raise ValueError("support submission requires at least one message")
    if category not in CATEGORIES:
        category = "uncategorized"
    user = (
        await session.execute(select(User).where(User.telegram_id == telegram_user_id))
    ).scalar_one_or_none()
    ticket = SupportTicket(
        telegram_user_id=telegram_user_id,
        internal_user_id=user.id if user else None,
        category=category,
        username=username,
        full_name=full_name,
        language_code=language_code,
        last_message_at=messages[-1]["created_at"],
    )
    session.add(ticket)
    await session.flush()
    for message in messages:
        session.add(
            SupportMessage(
                ticket_id=ticket.id,
                sender_type="user",
                body=message.get("body"),
                telegram_message_id=message.get("telegram_message_id"),
                attachments=list(message.get("attachments") or []),
                created_at=message["created_at"],
            )
        )
    await enqueue_support_ticket_notifications(
        session,
        ticket=ticket,
        messages=messages,
    )
    await session.commit()
    return ticket


async def list_tickets(
    session, *, page: int, page_size: int, status: str | None, category: str | None
):
    query = select(SupportTicket)
    if status:
        query = query.where(SupportTicket.status == status)
    if category:
        query = query.where(SupportTicket.category == category)
    total = (
        await session.execute(select(func.count()).select_from(query.subquery()))
    ).scalar_one()
    items = (
        (
            await session.execute(
                query.order_by(
                    (SupportTicket.status == "open").desc(),
                    SupportTicket.last_message_at.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return items, total
