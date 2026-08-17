from fastapi import APIRouter, Depends, Query

from src.database.models import User
from src.web_api.dependencies import get_current_user
from src.web_api.services.storage_api_service import (
    get_owned_upload_preview_url_payload,
    get_presigned_upload_url_payload,
)

router = APIRouter()


@router.get("/presigned-url")
async def get_presigned_upload_url(
    filename: str = Query(
        ..., description="The original name of the file to be uploaded"
    ),
    content_type: str = Query(
        ..., description="The MIME type of the file (e.g. image/jpeg, video/mp4)"
    ),
    current_user: User = Depends(get_current_user),
):
    """
    Generate a presigned URL for direct file upload to MinIO.
    This avoids routing large files (especially videos) through the BFF memory.
    """
    return await get_presigned_upload_url_payload(
        filename=filename,
        content_type=content_type,
        current_user=current_user,
    )


@router.get("/preview-url")
async def get_owned_upload_preview_url(
    object_key: str = Query(..., description="Owned staged upload object key"),
    current_user: User = Depends(get_current_user),
):
    return await get_owned_upload_preview_url_payload(
        object_key=object_key,
        current_user=current_user,
    )
