from __future__ import annotations

from datetime import datetime
from sqlalchemy import select, func

from src.database.models import SupportMessage, SupportTicket, User

ACTIVE_STATUSES = ("open", "processing", "resolved")
CATEGORIES = {"recharge", "bug", "suggestion", "uncategorized"}
STATUSES = {*ACTIVE_STATUSES, "closed"}


async def get_or_create_ticket(
    session, *, telegram_user, category: str
) -> SupportTicket:
    if category not in CATEGORIES:
        category = "uncategorized"
    ticket = (
        await session.execute(
            select(SupportTicket)
            .where(
                SupportTicket.telegram_user_id == telegram_user.id,
                SupportTicket.status.in_(ACTIVE_STATUSES),
            )
            .order_by(SupportTicket.last_message_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    user = (
        await session.execute(select(User).where(User.telegram_id == telegram_user.id))
    ).scalar_one_or_none()
    if ticket is None:
        ticket = SupportTicket(
            telegram_user_id=telegram_user.id,
            internal_user_id=user.id if user else None,
            category=category,
            username=telegram_user.username,
            full_name=telegram_user.full_name,
            language_code=telegram_user.language_code,
        )
        session.add(ticket)
        await session.flush()
    elif category != "uncategorized":
        ticket.category = category
    return ticket


async def add_user_message(
    session,
    *,
    telegram_user,
    telegram_message_id: int,
    body: str | None,
    attachments: list[dict],
    category: str = "uncategorized",
) -> SupportTicket:
    ticket = await get_or_create_ticket(
        session, telegram_user=telegram_user, category=category
    )
    session.add(
        SupportMessage(
            ticket_id=ticket.id,
            sender_type="user",
            body=body,
            telegram_message_id=telegram_message_id,
            attachments=attachments,
        )
    )
    ticket.last_message_at = datetime.now()
    if ticket.status == "resolved":
        ticket.status = "open"
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
