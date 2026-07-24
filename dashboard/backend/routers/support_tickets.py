from datetime import datetime
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from dashboard.backend.auth import TokenData, get_current_user
from src.database.core import get_db
from src.database.models import SupportMessage, SupportTicket
from src.services.r2_presign import build_r2_presigned_url
from src.services.support_ticket_service import STATUSES, list_tickets

router = APIRouter(prefix="/api/support-tickets", tags=["support_tickets"])


class UpdateTicketRequest(BaseModel):
    status: str = Field(pattern="^(open|processing|resolved|closed)$")
    internal_note: str | None = Field(default=None, max_length=4000)


class ReplyTicketRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    status: str = Field(
        default="processing", pattern="^(open|processing|resolved|closed)$"
    )


def ticket_payload(ticket: SupportTicket) -> dict:
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


def message_payload(message: SupportMessage) -> dict:
    attachments = []
    for item in message.attachments or []:
        item = dict(item)
        item["url"] = (
            build_r2_presigned_url(
                str(item.get("object_key") or ""), expires_hours=0.25
            )
            if item.get("object_key")
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


@router.get("")
async def get_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    status: str | None = None,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    if status and status not in STATUSES:
        raise HTTPException(422, "Invalid status")
    items, total = await list_tickets(
        db, page=page, page_size=page_size, status=status, category=category
    )
    return {
        "items": [ticket_payload(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
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
        **ticket_payload(ticket),
        "messages": [message_payload(message) for message in messages],
    }


@router.patch("/{ticket_id}")
async def update_ticket(
    ticket_id: int,
    payload: UpdateTicketRequest,
    db: AsyncSession = Depends(get_db),
    admin: TokenData = Depends(get_current_user),
):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    ticket.status, ticket.assigned_admin = payload.status, admin.username
    ticket.closed_at = datetime.now() if payload.status == "closed" else None
    if payload.internal_note:
        db.add(
            SupportMessage(
                ticket_id=ticket.id, sender_type="internal", body=payload.internal_note
            )
        )
    await db.commit()
    return ticket_payload(ticket)


@router.post("/{ticket_id}/reply")
async def reply_ticket(
    ticket_id: int,
    payload: ReplyTicketRequest,
    db: AsyncSession = Depends(get_db),
    admin: TokenData = Depends(get_current_user),
):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    token = os.getenv("SUPPORT_BOT_TOKEN")
    if not token:
        raise HTTPException(503, "Support Bot is not configured")
    try:
        async with Bot(token=token) as bot:
            sent = await bot.send_message(
                chat_id=ticket.telegram_user_id, text=payload.body
            )
    except Exception as exc:
        raise HTTPException(502, "Unable to deliver reply") from exc
    ticket.status, ticket.assigned_admin, ticket.last_message_at = (
        payload.status,
        admin.username,
        datetime.now(),
    )
    ticket.closed_at = datetime.now() if payload.status == "closed" else None
    db.add(
        SupportMessage(
            ticket_id=ticket.id,
            sender_type="admin",
            body=payload.body,
            telegram_message_id=sent.message_id,
        )
    )
    await db.commit()
    return ticket_payload(ticket)
