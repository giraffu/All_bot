import logging

from fastapi import HTTPException
from sqlalchemy import delete, desc, select

from config import MINIO_TEMPLATE_BUCKET
from dashboard.backend.presenters.template_admin_presenter import (
    build_template_contribution_response,
    build_template_preview_object_name,
)
from src.database.models import TemplateContribution, User
from src.services.storage import storage

logger = logging.getLogger("dashboard.templates")


async def get_template_contributions_payload(
    *,
    db,
    storage_service=None,
    logger_override: logging.Logger | None = None,
) -> list:
    active_logger = logger_override or logger
    if storage_service is None:
        storage_service = storage

    try:
        stmt = (
            select(TemplateContribution, User.username, User.full_name)
            .join(User, TemplateContribution.user_id == User.id)
            .order_by(desc(TemplateContribution.created_at))
        )
        result = await db.execute(stmt)
        return [
            build_template_contribution_response(
                contribution=row[0],
                username=row[1],
                full_name=row[2],
                storage_service=storage_service,
            )
            for row in result
        ]
    except Exception as exc:
        active_logger.error(f"Error getting contributions: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def approve_contribution_payload(
    *,
    contribution_id: int,
    db,
    storage_service=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if storage_service is None:
        storage_service = storage

    try:
        result = await db.execute(
            select(TemplateContribution).where(TemplateContribution.id == contribution_id)
        )
        contribution = result.scalar_one_or_none()
        if not contribution:
            raise HTTPException(status_code=404, detail="Contribution not found")

        source_obj = build_template_preview_object_name(
            contribution=type(
                "TempContribution",
                (),
                {
                    "file_path": contribution.file_path,
                    "is_reviewed": False,
                    "file_type": contribution.file_type,
                },
            )()
        )
        target_obj = build_template_preview_object_name(
            contribution=type(
                "ReviewedContribution",
                (),
                {
                    "file_path": contribution.file_path,
                    "is_reviewed": True,
                    "file_type": contribution.file_type,
                },
            )()
        )

        try:
            from minio.commonconfig import CopySource

            storage_service.client.copy_object(
                MINIO_TEMPLATE_BUCKET,
                target_obj,
                CopySource(MINIO_TEMPLATE_BUCKET, source_obj),
            )
            storage_service.client.remove_object(MINIO_TEMPLATE_BUCKET, source_obj)
        except Exception as storage_exc:
            active_logger.warning(f"Failed to move in MinIO: {storage_exc}")

        contribution.is_reviewed = True
        contribution.file_path = str(target_obj)

        reward_amount = 20 if contribution.file_type == "video" else 10
        user_result = await db.execute(select(User).where(User.id == contribution.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.credits += reward_amount
            user.approved_contributions = (user.approved_contributions or 0) + 1

        await db.commit()
        return {
            "status": "ok",
            "message": f"Contribution approved, moved to template library, and {reward_amount} credits awarded",
        }
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error approving contribution: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


async def delete_contribution_payload(
    *,
    contribution_id: int,
    db,
    storage_service=None,
    logger_override: logging.Logger | None = None,
) -> dict:
    active_logger = logger_override or logger
    if storage_service is None:
        storage_service = storage

    try:
        result = await db.execute(
            select(TemplateContribution).where(TemplateContribution.id == contribution_id)
        )
        contribution = result.scalar_one_or_none()
        if not contribution:
            raise HTTPException(status_code=404, detail="Contribution not found")

        obj_name = build_template_preview_object_name(contribution=contribution)
        try:
            storage_service.client.remove_object(MINIO_TEMPLATE_BUCKET, obj_name)
        except Exception as storage_exc:
            active_logger.warning(f"Failed to delete from MinIO: {storage_exc}")

        await db.execute(
            delete(TemplateContribution).where(TemplateContribution.id == contribution_id)
        )
        await db.commit()
        return {"status": "ok", "message": "Contribution deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        active_logger.error(f"Error deleting contribution: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
