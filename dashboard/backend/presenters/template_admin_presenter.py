import os

from config import MINIO_TEMPLATE_BUCKET
from dashboard.backend.schemas import TemplateContributionResponse
from dashboard.backend.presenters.storage_presenter_utils import build_storage_url


def build_template_preview_object_name(*, contribution) -> str:
    normalized_path = str(contribution.file_path or "").replace("\\", "/").lstrip("/")
    filename = os.path.basename(normalized_path)
    if contribution.is_reviewed:
        if contribution.file_type == "video":
            return f"video_nice/{filename}"
        return f"quick_face/{filename}"
    if normalized_path.startswith(("template-submissions/", "temps/")):
        return normalized_path
    return f"template-submissions/{filename}"


def build_template_preview_url(*, contribution, storage_service) -> str:
    object_name = build_template_preview_object_name(contribution=contribution)
    return build_storage_url(
        storage_service=storage_service,
        object_name=object_name,
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
