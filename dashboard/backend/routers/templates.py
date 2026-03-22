from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List
import logging
import os
from src.database.core import get_db
from src.database.models import TemplateContribution, User
from dashboard.backend.schemas import TemplateContributionResponse
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET

router = APIRouter(prefix="/api/templates", tags=["templates"])
logger = logging.getLogger("dashboard.templates")

@router.get("/contributions", response_model=List[TemplateContributionResponse])
async def get_template_contributions(db: AsyncSession = Depends(get_db)):
    """Get all template contributions with user info"""
    try:
        stmt = (
            select(TemplateContribution, User.username, User.full_name)
            .join(User, TemplateContribution.user_id == User.id)
            .order_by(desc(TemplateContribution.created_at))
        )
        result = await db.execute(stmt)
        
        contributions = []
        for row in result:
            contribution = row[0]
            username = row[1]
            full_name = row[2]
            
            filename = os.path.basename(contribution.file_path.replace('\\', '/'))
            
            if contribution.is_reviewed:
                if contribution.file_type == 'video':
                    obj_name = f"video_nice/{filename}"
                else:
                    obj_name = f"quick_face/{filename}"
                preview_url = storage.get_presigned_url(obj_name, bucket=MINIO_TEMPLATE_BUCKET)
            else:
                obj_name = f"temps/{filename}"
                preview_url = storage.get_presigned_url(obj_name, bucket=MINIO_TEMPLATE_BUCKET)

            res = TemplateContributionResponse(
                id=contribution.id,
                user_id=contribution.user_id,
                username=username,
                full_name=full_name,
                file_path=contribution.file_path,
                file_type=contribution.file_type or "photo",
                is_reviewed=contribution.is_reviewed,
                created_at=contribution.created_at,
                preview_url=preview_url
            )
            contributions.append(res)
            
        return contributions
    except Exception as e:
        logger.error(f"Error getting contributions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/contributions/{contribution_id}/approve")
async def approve_contribution(contribution_id: int, db: AsyncSession = Depends(get_db)):
    """Approve a contribution: move in MinIO and mark as reviewed"""
    try:
        stmt = select(TemplateContribution).where(TemplateContribution.id == contribution_id)
        result = await db.execute(stmt)
        contribution = result.scalar_one_or_none()
        
        if not contribution:
            raise HTTPException(status_code=404, detail="Contribution not found")
            
        filename = os.path.basename(contribution.file_path.replace('\\', '/'))
        source_obj = f"temps/{filename}"
        
        if contribution.file_type == 'video':
            target_obj = f"video_nice/{filename}"
        else:
            target_obj = f"quick_face/{filename}"
            
        try:
            from minio.commonconfig import CopySource
            storage.client.copy_object(
                MINIO_TEMPLATE_BUCKET,
                target_obj,
                CopySource(MINIO_TEMPLATE_BUCKET, source_obj)
            )
            storage.client.remove_object(MINIO_TEMPLATE_BUCKET, source_obj)
        except Exception as se:
            logger.warning(f"Failed to move in MinIO: {se}")
        
        contribution.is_reviewed = True
        contribution.file_path = str(target_obj)
        
        reward_amount = 20 if contribution.file_type == 'video' else 10
        user_stmt = select(User).where(User.id == contribution.user_id)
        user_result = await db.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        if user:
            user.credits += reward_amount
            user.approved_contributions = (user.approved_contributions or 0) + 1
            
        await db.commit()
        
        return {"status": "ok", "message": f"Contribution approved, moved to template library, and {reward_amount} credits awarded"}
    except Exception as e:
        logger.error(f"Error approving contribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/contributions/{contribution_id}")
async def delete_contribution(contribution_id: int, db: AsyncSession = Depends(get_db)):
    """Reject/Delete a contribution: delete from MinIO and database record"""
    try:
        stmt = select(TemplateContribution).where(TemplateContribution.id == contribution_id)
        result = await db.execute(stmt)
        contribution = result.scalar_one_or_none()
        
        if not contribution:
            raise HTTPException(status_code=404, detail="Contribution not found")
            
        filename = os.path.basename(contribution.file_path.replace('\\', '/'))
        bucket = MINIO_TEMPLATE_BUCKET
        
        if contribution.is_reviewed:
            obj_name = f"video_nice/{filename}" if contribution.file_type == 'video' else f"quick_face/{filename}"
        else:
            obj_name = f"temps/{filename}"
            
        try:
            storage.client.remove_object(bucket, obj_name)
        except Exception as se:
            logger.warning(f"Failed to delete from MinIO: {se}")
            
        from sqlalchemy import delete
        await db.execute(delete(TemplateContribution).where(TemplateContribution.id == contribution_id))
        await db.commit()
        
        return {"status": "ok", "message": "Contribution deleted"}
    except Exception as e:
        logger.error(f"Error deleting contribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))
