import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select

from dashboard.backend.schemas import SiteNoticeListResponse, SiteNoticeResponse
from src.constants import WEB_ACCESS_ALLOWED_GROUPS
from src.database.models import SiteNotice

logger = logging.getLogger("dashboard.site_notice")
ALLOWED_NOTICE_GROUPS = ["凡人", *WEB_ACCESS_ALLOWED_GROUPS]
ALLOWED_NOTICE_IDENTITIES = ["外门弟子", "内门弟子", "核心弟子", "真传弟子"]
DEFAULT_NOTICE_TITLE = "站点通知"


def _normalize_audience(values, *, allowed_values: list[str]) -> list[str]:
    if not values:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in allowed_values or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _normalize_title(raw_title: str | None) -> str:
    title = (raw_title or "").strip()
    return title or DEFAULT_NOTICE_TITLE


def _normalize_content(raw_content: str | None) -> str:
    return (raw_content or "").strip()


def _serialize_notice(notice: SiteNotice) -> SiteNoticeResponse:
    return SiteNoticeResponse(
        id=notice.id,
        title=_normalize_title(getattr(notice, "title", "")),
        content=getattr(notice, "content", "") or "",
        is_active=bool(getattr(notice, "is_active", False)),
        is_pinned=bool(getattr(notice, "is_pinned", False)),
        target_groups=_normalize_audience(
            getattr(notice, "target_groups", []),
            allowed_values=ALLOWED_NOTICE_GROUPS,
        ),
        target_identities=_normalize_audience(
            getattr(notice, "target_identities", []),
            allowed_values=ALLOWED_NOTICE_IDENTITIES,
        ),
        published_at=getattr(notice, "published_at", None),
        created_at=getattr(notice, "created_at", None),
        updated_at=getattr(notice, "updated_at", None),
    )


def _notice_sort_key(notice: SiteNotice) -> tuple[bool, float, float, int]:
    published_at = getattr(notice, "published_at", None)
    updated_at = getattr(notice, "updated_at", None)
    created_at = getattr(notice, "created_at", None)
    published_ts = published_at.timestamp() if published_at else 0.0
    updated_source = updated_at or created_at or published_at
    updated_ts = updated_source.timestamp() if updated_source else 0.0
    return (
        bool(getattr(notice, "is_pinned", False)),
        published_ts,
        updated_ts,
        int(getattr(notice, "id", 0) or 0),
    )


async def _fetch_all_notices(db) -> list[SiteNotice]:
    result = await db.execute(select(SiteNotice).order_by(SiteNotice.id.asc()))
    scalar_result = result.scalars() if hasattr(result, "scalars") else result
    if hasattr(scalar_result, "all"):
        return list(scalar_result.all())
    return list(getattr(scalar_result, "_value", []) or [])


def _visible_admin_notices(notices: list[SiteNotice]) -> list[SiteNotice]:
    filtered = [
        notice
        for notice in notices
        if getattr(notice, "deleted_at", None) is None
    ]
    return sorted(filtered, key=_notice_sort_key, reverse=True)


def _find_notice_by_id(notices: list[SiteNotice], notice_id: int) -> SiteNotice | None:
    for notice in notices:
        if int(getattr(notice, "id", 0) or 0) == notice_id:
            return notice
    return None


def _apply_notice_payload(notice: SiteNotice, payload) -> None:
    title = _normalize_title(getattr(payload, "title", ""))
    content = _normalize_content(getattr(payload, "content", ""))
    should_activate = bool(getattr(payload, "is_active", False) and content)
    was_active = bool(getattr(notice, "is_active", False))

    notice.title = title
    notice.content = content
    notice.is_active = should_activate
    notice.is_pinned = bool(getattr(payload, "is_pinned", False) and should_activate)
    notice.target_groups = _normalize_audience(
        getattr(payload, "target_groups", []),
        allowed_values=ALLOWED_NOTICE_GROUPS,
    )
    notice.target_identities = _normalize_audience(
        getattr(payload, "target_identities", []),
        allowed_values=ALLOWED_NOTICE_IDENTITIES,
    )

    if should_activate and (not was_active or getattr(notice, "published_at", None) is None):
        notice.published_at = datetime.now()


async def list_site_notice_payloads(*, db, logger_override: logging.Logger | None = None):
    active_logger = logger_override or logger
    try:
        notices = await _fetch_all_notices(db)
        return SiteNoticeListResponse(
            items=[_serialize_notice(notice) for notice in _visible_admin_notices(notices)]
        )
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error listing site notices: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def get_site_notice_payload(*, notice_id: int, db, logger_override: logging.Logger | None = None):
    active_logger = logger_override or logger
    try:
        notices = await _fetch_all_notices(db)
        notice = _find_notice_by_id(_visible_admin_notices(notices), notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="Site notice not found")
        return _serialize_notice(notice)
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error getting site notice: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def create_site_notice_payload(*, payload, db, logger_override: logging.Logger | None = None):
    active_logger = logger_override or logger
    try:
        notice = SiteNotice()
        _apply_notice_payload(notice, payload)
        db.add(notice)
        await db.commit()
        await db.refresh(notice)
        return _serialize_notice(notice)
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error creating site notice: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def update_site_notice_payload(
    *,
    notice_id: int,
    payload,
    db,
    logger_override: logging.Logger | None = None,
):
    active_logger = logger_override or logger
    try:
        notices = await _fetch_all_notices(db)
        notice = _find_notice_by_id(_visible_admin_notices(notices), notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="Site notice not found")

        _apply_notice_payload(notice, payload)
        await db.commit()
        await db.refresh(notice)
        return _serialize_notice(notice)
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error updating site notice: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def delete_site_notice_payload(*, notice_id: int, db, logger_override: logging.Logger | None = None):
    active_logger = logger_override or logger
    try:
        notices = await _fetch_all_notices(db)
        notice = _find_notice_by_id(_visible_admin_notices(notices), notice_id)
        if notice is None:
            raise HTTPException(status_code=404, detail="Site notice not found")

        notice.deleted_at = datetime.now()
        notice.is_active = False
        notice.is_pinned = False
        await db.commit()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error deleting site notice: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
