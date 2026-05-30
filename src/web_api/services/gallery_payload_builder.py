from src.web_api.schemas.gallery_schema import PaginatedGalleryResponse


def build_paginated_gallery_response(
    *,
    items,
    total: int,
    page: int,
    size: int,
    response_cls=PaginatedGalleryResponse,
) -> PaginatedGalleryResponse:
    pages = (total + size - 1) // size
    return response_cls(items=items, total=total, page=page, size=size, pages=pages)
