from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from src.database.models import SupportMessage, SupportTicket
from src.services.r2_presign import build_r2_presigned_url
from src.services.support_ticket_service import STATUSES, list_tickets


class SupportTicketAdminError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _ticket_payload(ticket: SupportTicket) -> dict:
    return {
        "id": ticket.id,
        "telegram_user_id": ticket.telegram_user_id,
        "internal_user_id": ticket.internal_user_id,
        "category": ticket.category,
        "status": ticket.status,
        "username": ticket.username,
        "full_name": ticket.full_name,
        "assigned_admin": ticket.assigned_admin,
        "created_at": ticket.created_at,
        "last_message_at": ticket.last_message_at,
        "closed_at": ticket.closed_at,
    }


def _message_payload(message: SupportMessage) -> dict:
    attachments = []
    for raw_item in message.attachments or []:
        item = dict(raw_item)
        object_key = str(item.get("object_key") or "")
        item["url"] = (
            build_r2_presigned_url(object_key, expires_hours=0.25)
            if object_key
            else ""
        )
        attachments.append(item)
    return {
        "id": message.id,
        "sender_type": message.sender_type,
        "body": message.body,
        "attachments": attachments,
        "created_at": message.created_at,
    }


async def list_support_tickets_admin(
    db: AsyncSession,
    *,
    page: int,
    page_size: int,
    status: str | None,
    category: str | None,
) -> dict:
    if status and status not in STATUSES:
        raise SupportTicketAdminError("invalid_status")
    items, total = await list_tickets(
        db,
        page=page,
        page_size=page_size,
        status=status,
        category=category,
    )
    return {
        "items": [_ticket_payload(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_support_ticket_admin(db: AsyncSession, *, ticket_id: int) -> dict:
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise SupportTicketAdminError("ticket_not_found")
    messages = (
        (
            await db.execute(
                select(SupportMessage)
                .where(SupportMessage.ticket_id == ticket_id)
                .order_by(SupportMessage.created_at, SupportMessage.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        **_ticket_payload(ticket),
        "messages": [_message_payload(message) for message in messages],
    }


async def update_support_ticket_admin(
    db: AsyncSession,
    *,
    ticket_id: int,
    status: str,
    internal_note: str | None,
    admin_username: str,
) -> dict:
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise SupportTicketAdminError("ticket_not_found")
    ticket.status, ticket.assigned_admin = status, admin_username
    ticket.closed_at = datetime.now() if status == "closed" else None
    if internal_note:
        db.add(
            SupportMessage(
                ticket_id=ticket.id,
                sender_type="internal",
                body=internal_note,
            )
        )
    await db.commit()
    return _ticket_payload(ticket)


async def _send_telegram_reply(chat_id: int, body: str) -> int:
    token = os.getenv("SUPPORT_BOT_TOKEN")
    if not token:
        raise SupportTicketAdminError("support_bot_not_configured")
    try:
        async with Bot(token=token) as bot:
            sent = await bot.send_message(chat_id=chat_id, text=body)
    except SupportTicketAdminError:
        raise
    except Exception as exc:
        raise SupportTicketAdminError("reply_delivery_failed") from exc
    return int(sent.message_id)


async def reply_support_ticket_admin(
    db: AsyncSession,
    *,
    ticket_id: int,
    body: str,
    status: str,
    admin_username: str,
    send_reply: Callable[[int, str], Awaitable[int]] = _send_telegram_reply,
) -> dict:
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise SupportTicketAdminError("ticket_not_found")
    telegram_message_id = await send_reply(ticket.telegram_user_id, body)
    now = datetime.now()
    ticket.status, ticket.assigned_admin, ticket.last_message_at = (
        status,
        admin_username,
        now,
    )
    ticket.closed_at = now if status == "closed" else None
    db.add(
        SupportMessage(
            ticket_id=ticket.id,
            sender_type="admin",
            body=body,
            telegram_message_id=telegram_message_id,
        )
    )
    await db.commit()
    return _ticket_payload(ticket)
