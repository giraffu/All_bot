import os

from config import MINIO_TEMPLATE_BUCKET
from dashboard.backend.schemas import TemplateContributionResponse


def build_template_preview_object_name(*, contribution) -> str:
    filename = os.path.basename(contribution.file_path.replace("\\", "/"))
    if contribution.is_reviewed:
        if contribution.file_type == "video":
            return f"video_nice/{filename}"
        return f"quick_face/{filename}"
    return f"temps/{filename}"


def build_template_preview_url(*, contribution, storage_service) -> str:
    object_name = build_template_preview_object_name(contribution=contribution)
    return storage_service.get_presigned_url(
        object_name,
        bucket=MINIO_TEMPLATE_BUCKET,
    )


def build_template_contribution_response(
    *,
    contribution,
    username: str,
    full_name: str,
    storage_service,
) -> TemplateContributionResponse:
    return TemplateContributionResponse(
        id=contribution.id,
        user_id=contribution.user_id,
        username=username,
        full_name=full_name,
        file_path=contribution.file_path,
        file_type=contribution.file_type or "photo",
        is_reviewed=contribution.is_reviewed,
        created_at=contribution.created_at,
        preview_url=build_template_preview_url(
            contribution=contribution,
            storage_service=storage_service,
        ),
    )
