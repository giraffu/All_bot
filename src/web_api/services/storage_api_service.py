import logging
import uuid
from datetime import datetime

from fastapi import HTTPException

from config import MINIO_BUCKET
from src.services.storage import storage

logger = logging.getLogger(__name__)


def build_presigned_upload_object_key(*, user_id: int, filename: str, now=None) -> str:
    now = now or datetime.now()
    ext = filename.split(".")[-1] if "." in filename else ""
    date_str = now.strftime("%Y%m%d")
    unique_id = str(uuid.uuid4())[:8]

    if ext:
        return f"web_uploads/{user_id}/{date_str}_{unique_id}.{ext}"
    return f"web_uploads/{user_id}/{date_str}_{unique_id}"


async def get_presigned_upload_url_payload(
    *,
    filename: str,
    content_type: str,
    current_user,
    get_presigned_put_url_func=None,
) -> dict:
    if not filename or not content_type:
        raise HTTPException(
            status_code=400,
            detail="Filename and content_type are required",
        )

    object_key = build_presigned_upload_object_key(
        user_id=current_user.id,
        filename=filename,
    )
    get_presigned_put_url_func = (
        get_presigned_put_url_func or storage.get_presigned_put_url
    )

    try:
        upload_url = get_presigned_put_url_func(
            object_key,
            expires_minutes=15,
            bucket=MINIO_BUCKET,
            content_type=content_type,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error generating presigned URL for user %s: %s",
            current_user.id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error generating URL",
        ) from exc

    if not upload_url:
        raise HTTPException(status_code=500, detail="Failed to generate upload URL")

    return {
        "upload_url": upload_url,
        "object_key": f"{MINIO_BUCKET}/{object_key}",
        "expires_in_minutes": 15,
    }
