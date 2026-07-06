from typing import Any

from src.web_api.schemas.gallery_schema import PaginatedGalleryResponse


def build_paginated_gallery_response(
    *,
    items: list[Any],
    total: int,
    page: int,
    size: int,
) -> PaginatedGalleryResponse:
    pages = (total + size - 1) // size
    return PaginatedGalleryResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )
