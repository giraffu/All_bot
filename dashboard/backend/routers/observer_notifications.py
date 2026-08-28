from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.backend.auth import TokenData, get_current_user
from dashboard.backend.services.observer_notification_admin_service import (
    ObserverNotificationAdminService,
)
from dashboard.backend.services.support_ticket_admin_service import (
    get_support_ticket_notification_settings_admin,
    update_support_ticket_notification_settings_admin,
)
from src.database.core import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notification-center", tags=["notification_center"])


class NotificationCenterSettingsRequest(BaseModel):
    admin_telegram_user_ids: list[int] = Field(default_factory=list, max_length=20)
    authorized_group_ids: list[int] = Field(default_factory=list, max_length=100)
    support_ticket_user_ids: list[int] = Field(default_factory=list, max_length=20)
    queue_alerts_enabled: bool = True
    queue_total_pending_threshold: int = Field(default=20, ge=1, le=100_000)
    queue_type_pending_threshold: int = Field(default=10, ge=1, le=100_000)
    group_collection_enabled: bool = True
    daily_reports_enabled: bool = False
    weekly_reports_enabled: bool = False
    monthly_reports_enabled: bool = False

    @field_validator("admin_telegram_user_ids", "support_ticket_user_ids")
    @classmethod
    def positive_user_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Telegram user IDs must be positive")
        return list(dict.fromkeys(values))

    @field_validator("authorized_group_ids")
    @classmethod
    def nonzero_group_ids(cls, values: list[int]) -> list[int]:
        if any(value == 0 for value in values):
            raise ValueError("Telegram group IDs must be nonzero")
        return list(dict.fromkeys(values))


def get_observer_notification_service() -> ObserverNotificationAdminService:
    database_url = os.getenv("OBSERVER_DATABASE_URL", "").strip()
    if not database_url:
        raise HTTPException(503, "Observer database is not configured")
    return ObserverNotificationAdminService(database_url)


def _unavailable(exc: Exception) -> HTTPException:
    logger.exception("observer notification center database operation failed")
    return HTTPException(503, "Observer notification center is temporarily unavailable")


@router.get("/settings")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    observer: ObserverNotificationAdminService = Depends(
        get_observer_notification_service
    ),
    _: TokenData = Depends(get_current_user),
):
    try:
        result = await observer.get_settings()
        support = await get_support_ticket_notification_settings_admin(db)
        result["support_ticket_user_ids"] = support["telegram_user_ids"]
        return result
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.put("/settings")
async def update_settings(
    payload: NotificationCenterSettingsRequest,
    db: AsyncSession = Depends(get_db),
    observer: ObserverNotificationAdminService = Depends(
        get_observer_notification_service
    ),
    _: TokenData = Depends(get_current_user),
):
    try:
        result = await observer.update_settings(
            **payload.model_dump(exclude={"support_ticket_user_ids"})
        )
        support = await update_support_ticket_notification_settings_admin(
            db, telegram_user_ids=payload.support_ticket_user_ids
        )
        result["support_ticket_user_ids"] = support["telegram_user_ids"]
        return result
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/reports")
async def get_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    observer: ObserverNotificationAdminService = Depends(
        get_observer_notification_service
    ),
    _: TokenData = Depends(get_current_user),
):
    try:
        return await observer.list_reports(page=page, page_size=page_size)
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.get("/notifications")
async def get_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    observer: ObserverNotificationAdminService = Depends(
        get_observer_notification_service
    ),
    _: TokenData = Depends(get_current_user),
):
    try:
        return await observer.list_notifications(page=page, page_size=page_size)
    except Exception as exc:
        raise _unavailable(exc) from exc
