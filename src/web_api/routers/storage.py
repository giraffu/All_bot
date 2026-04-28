import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from config import MINIO_BUCKET
from src.database.models import User
from src.services.storage import storage
from src.web_api.dependencies import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/presigned-url")
async def get_presigned_upload_url(
    filename: str = Query(..., description="The original name of the file to be uploaded"),
    content_type: str = Query(..., description="The MIME type of the file (e.g. image/jpeg, video/mp4)"),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a presigned URL for direct file upload to MinIO.
    This avoids routing large files (especially videos) through the BFF memory.
    """
    if not filename or not content_type:
        raise HTTPException(status_code=400, detail="Filename and content_type are required")
        
    # Generate a unique object key
    ext = filename.split(".")[-1] if "." in filename else ""
    date_str = datetime.now().strftime("%Y%m%d")
    unique_id = str(uuid.uuid4())[:8]
    
    # Structure: web_uploads/user_id/YYYYMMDD_uuid.ext
    object_key = f"web_uploads/{current_user.id}/{date_str}_{unique_id}.{ext}" if ext else f"web_uploads/{current_user.id}/{date_str}_{unique_id}"
    
    try:
        upload_url = storage.get_presigned_put_url(
            object_key, 
            expires_minutes=15, 
            bucket=MINIO_BUCKET,
            content_type=content_type
        )
        
        if not upload_url:
            raise HTTPException(status_code=500, detail="Failed to generate upload URL")
            
        return {
            "upload_url": upload_url,
            "object_key": f"{MINIO_BUCKET}/{object_key}", # Prefix with bucket for core services compatibility
            "expires_in_minutes": 15
        }
    except Exception as e:
        logger.error(f"Error generating presigned URL for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error generating URL")
