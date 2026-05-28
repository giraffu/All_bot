from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

class CommentCreate(BaseModel):
    content: str = Field(max_length=500, min_length=1)

    @field_validator("content")
    @classmethod
    def strip_and_validate_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("评论内容不能为空")
        return stripped

class CommentUserResponse(BaseModel):
    id: int
    author_name: str

class GalleryCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime
    user: CommentUserResponse

class PaginatedCommentResponse(BaseModel):
    items: List[GalleryCommentResponse]
    total: int
    page: int
    size: int
    pages: int

class GallerySubmitRequest(BaseModel):
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None

class GalleryPostResponse(BaseModel):
    id: int
    task_id: str
    media_type: str
    billing_resolution: Optional[str] = None
    width: Optional[int]
    height: Optional[int]
    duration: Optional[int]
    tags: List[str]
    likes_count: int
    dislikes_count: int
    applied_count: int
    comments_count: int = 0
    thumbnail_url: str
    media_url: str
    created_at: datetime
    is_active: bool = True
    prompt: Optional[str] = None
    task_type: Optional[str] = None

    # User interaction status for current user
    has_liked: bool = False
    has_disliked: bool = False
    author_id: Optional[int] = None
    author_name: Optional[str] = None
    author_username: Optional[str] = None
    is_following_author: bool = False


class PaginatedGalleryResponse(BaseModel):
    items: List[GalleryPostResponse]
    total: int
    page: int
    size: int
    pages: int


class ApplyContextResponse(BaseModel):
    post_id: int
    source_post_id: Optional[int] = None
    billing_resolution: Optional[str] = None
    requested_duration: Optional[int] = None
    task_id: str
    media_type: str
    prompt: Optional[str]
    lora_name: Optional[str] = None
    lora_strength: Optional[float] = None
    lora_items: Optional[list[dict]] = None
    input_file: Optional[str]
    input_file_url: Optional[str]
    width: Optional[int]
    height: Optional[int]
    duration: Optional[int]
    task_type: str
