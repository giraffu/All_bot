from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.auth import TokenData, get_current_user
from dashboard.backend.services.support_ticket_admin_service import (
    SupportTicketAdminError,
    get_support_ticket_admin,
    list_support_tickets_admin,
    reply_support_ticket_admin,
    update_support_ticket_admin,
)
from src.database.core import get_db

router = APIRouter(prefix="/api/support-tickets", tags=["support_tickets"])


class UpdateTicketRequest(BaseModel):
    status: str = Field(pattern="^(open|processing|resolved|closed)$")
    internal_note: str | None = Field(default=None, max_length=4000)


class ReplyTicketRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    status: str = Field(
        default="processing", pattern="^(open|processing|resolved|closed)$"
    )


ERRORS = {
    "invalid_status": (422, "Invalid status"),
    "ticket_not_found": (404, "Ticket not found"),
    "support_bot_not_configured": (503, "Support Bot is not configured"),
    "reply_delivery_failed": (502, "Unable to deliver reply"),
}


def _map_service_error(exc: SupportTicketAdminError) -> HTTPException:
    status_code, detail = ERRORS.get(exc.code, (500, "Support ticket operation failed"))
    return HTTPException(status_code, detail)


@router.get("")
async def get_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    status: str | None = None,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    try:
        return await list_support_tickets_admin(
            db, page=page, page_size=page_size, status=status, category=category
        )
    except SupportTicketAdminError as exc:
        raise _map_service_error(exc) from exc


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    _: TokenData = Depends(get_current_user),
):
    try:
        return await get_support_ticket_admin(db, ticket_id=ticket_id)
    except SupportTicketAdminError as exc:
        raise _map_service_error(exc) from exc


@router.patch("/{ticket_id}")
async def update_ticket(
    ticket_id: int,
    payload: UpdateTicketRequest,
    db: AsyncSession = Depends(get_db),
    admin: TokenData = Depends(get_current_user),
):
    try:
        return await update_support_ticket_admin(
            db,
            ticket_id=ticket_id,
            status=payload.status,
            internal_note=payload.internal_note,
            admin_username=admin.username,
        )
    except SupportTicketAdminError as exc:
        raise _map_service_error(exc) from exc


@router.post("/{ticket_id}/reply")
async def reply_ticket(
    ticket_id: int,
    payload: ReplyTicketRequest,
    db: AsyncSession = Depends(get_db),
    admin: TokenData = Depends(get_current_user),
):
    try:
        return await reply_support_ticket_admin(
            db,
            ticket_id=ticket_id,
            body=payload.body,
            status=payload.status,
            admin_username=admin.username,
        )
    except SupportTicketAdminError as exc:
        raise _map_service_error(exc) from exc
