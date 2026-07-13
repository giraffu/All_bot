from datetime import datetime

from pydantic import BaseModel, Field


class SiteNoticeItemResponse(BaseModel):
    id: int
    title: str = ""
    content: str
    is_active: bool
    is_pinned: bool = False
    published_at: datetime | None = None
    updated_at: datetime | None = None


class SiteNoticeResponse(BaseModel):
    featured_notice: SiteNoticeItemResponse | None = None
    notices: list[SiteNoticeItemResponse] = Field(default_factory=list)
