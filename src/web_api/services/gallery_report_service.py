from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, GalleryReport
from src.web_api.common.utils import call_with_optional_db


def _gallery_report_error(code: str) -> dict:
    return {"code": code}


async def create_gallery_report_payload(
    *,
    post_id: int,
    report,
    current_user,
    db,
) -> dict:
    post = await db.get(GalleryPost, post_id)
    if not post or not post.is_active:
        raise HTTPException(
            status_code=404,
            detail=_gallery_report_error("GALLERY_REPORT_POST_UNAVAILABLE"),
        )

    new_report = GalleryReport(
        post_id=post.id,
        reporter_user_id=current_user.id,
        post_author_user_id=post.user_id,
        post_task_id=post.task_id,
        reason=report.reason,
        status="pending",
    )

    try:
        db.add(new_report)
        await db.flush()
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=_gallery_report_error("GALLERY_REPORT_DUPLICATE"),
        ) from exc
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=_gallery_report_error("GALLERY_REPORT_CREATE_FAILED"),
        )

    return {"status": "ok", "report_id": new_report.id}


async def create_gallery_report_api_payload(
    *,
    post_id: int,
    report,
    current_user,
    db=None,
    session_factory=None,
    service_fn=None,
) -> dict:
    return await call_with_optional_db(
        db=db,
        service_fn=service_fn or create_gallery_report_payload,
        session_factory=session_factory or AsyncSessionLocal,
        post_id=post_id,
        report=report,
        current_user=current_user,
    )
