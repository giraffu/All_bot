from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from typing import Optional, List
import logging
import os
from src.database.core import get_db
from src.database.models import History, User
from dashboard.backend.schemas import HistoryListResponse, HistoryResponse
from src.services.storage import storage
from config import MINIO_TEMPLATE_BUCKET

router = APIRouter(prefix="/api/history", tags=["history"])
logger = logging.getLogger("dashboard.history")

@router.get("/all", response_model=HistoryListResponse)
async def get_all_history(page: int = 1, page_size: int = 20, type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Get all history with pagination and optional type filter"""
    try:
        offset = (page - 1) * page_size
        
        count_stmt = (
            select(func.count(History.id))
            .join(User, History.user_id == User.id)
        )
        
        stmt = (
            select(History, User.username, User.full_name)
            .join(User, History.user_id == User.id)
            .order_by(desc(History.created_at))
        )

        if type and type != "all":
            count_stmt = count_stmt.where(History.type == type)
            stmt = stmt.where(History.type == type)
        
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        stmt = stmt.offset(offset).limit(page_size)
        result = await db.execute(stmt)
        
        items = []
        for row in result:
            history = row[0]
            username = row[1]
            full_name = row[2]
            
            item_dict = {c.name: getattr(history, c.name) for c in history.__table__.columns}
            item_dict["username"] = username
            item_dict["full_name"] = full_name
            
            if history.input_file:
                urls = []
                for f in history.input_file.split('|'):
                    if f.startswith('template:'):
                        template_path = f[9:]
                        urls.append(storage.get_presigned_url(template_path, bucket=MINIO_TEMPLATE_BUCKET))
                    else:
                        basename = os.path.basename(f.replace('\\', '/'))
                        obj_name = f"{history.user_id}/input_images/{basename}"
                        urls.append(storage.get_presigned_url(obj_name))
                item_dict['input_file_url'] = '|'.join(urls)
                
            if history.output_file:
                basename = os.path.basename(history.output_file)
                obj_name = f"{history.user_id}/output_images/{basename}"
                item_dict['output_file_url'] = storage.get_presigned_url(obj_name)
            
            items.append(item_dict)
            
        return {"items": items, "total": total}
    except Exception as e:
        logger.error(f"Error getting all history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{user_id}", response_model=List[HistoryResponse])
async def get_user_history(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get history for a specific user"""
    try:
        stmt = select(History).where(History.user_id == user_id).order_by(desc(History.created_at)).limit(100)
        result = await db.execute(stmt)
        history = result.scalars().all()
        
        items = []
        for h in history:
            item_dict = {c.name: getattr(h, c.name) for c in h.__table__.columns}
            
            if h.input_file:
                urls = []
                for f in h.input_file.split('|'):
                    if f.startswith('template:'):
                        template_path = f[9:]
                        urls.append(storage.get_presigned_url(template_path, bucket=MINIO_TEMPLATE_BUCKET))
                    else:
                        basename = os.path.basename(f.replace('\\', '/'))
                        obj_name = f"{h.user_id}/input_images/{basename}"
                        urls.append(storage.get_presigned_url(obj_name))
                item_dict['input_file_url'] = '|'.join(urls)
                
            if h.output_file:
                basename = os.path.basename(h.output_file)
                obj_name = f"{h.user_id}/output_images/{basename}"
                item_dict['output_file_url'] = storage.get_presigned_url(obj_name)
                
            items.append(item_dict)
            
        return items
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
