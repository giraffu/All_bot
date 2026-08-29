from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

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


GalleryReportReason = Literal["children", "gore", "gross", "other"]


class GalleryReportCreate(BaseModel):
    reason: GalleryReportReason


class GalleryReportSubmitResponse(BaseModel):
    status: str
    report_id: int


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
    prompt_model: Optional[Dict[str, Any]] = None
    prompt_unlocked: bool = False
    prompt_unlockable: bool = False
    prompt_is_masked: bool = False
    prompt_unlock_price: int = 1
    task_type: Optional[str] = None
    result_meta: Dict[str, Any] = Field(default_factory=dict)
    input_file: Optional[str] = None
    input_file_url: Optional[str] = None
    input_files: List[str] = Field(default_factory=list)
    input_file_urls: List[str] = Field(default_factory=list)
    template_apply_supported: bool = True
    template_apply_disabled_reason: Optional[str] = None

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


class PromptUnlockResponse(BaseModel):
    post_id: int
    prompt: str
    prompt_model: Optional[Dict[str, Any]] = None
    prompt_unlocked: bool = True
    prompt_unlockable: bool = False
    prompt_is_masked: bool = False
    prompt_unlock_price: int = 1
    current_credits: int
    already_unlocked: bool = False


class ApplyContextResponse(BaseModel):
    post_id: int
    source_post_id: Optional[int] = None
    billing_resolution: Optional[str] = None
    requested_duration: Optional[int] = None
    required_image_count: Optional[int] = None
    resolution_preset: Optional[str] = None
    aspect_ratio: Optional[str] = None
    task_id: str
    media_type: str
    prompt: Optional[str]
    prompt_model: Optional[Dict[str, Any]] = None
    negative_prompt: Optional[str] = None
    lora_name: Optional[str] = None
    lora_strength: Optional[float] = None
    lora_items: Optional[list[dict]] = None
    reference_audio_ref: Optional[Dict[str, Any]] = None
    reference_audio_url: Optional[str] = None
    input_file: Optional[str]
    input_file_url: Optional[str]
    input_files: List[str] = Field(default_factory=list)
    input_file_urls: List[str] = Field(default_factory=list)
    width: Optional[int]
    height: Optional[int]
    duration: Optional[int]
    task_type: str
