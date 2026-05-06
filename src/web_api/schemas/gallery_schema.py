from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class GalleryPostResponse(BaseModel):
    id: int
    task_id: str
    media_type: str
    width: Optional[int]
    height: Optional[int]
    duration: Optional[int]
    tags: List[str]
    likes_count: int
    dislikes_count: int
    applied_count: int
    thumbnail_url: str
    media_url: str
    created_at: datetime
    is_active: bool = True
    prompt: Optional[str] = None
    task_type: Optional[str] = None
    
    # User interaction status for current user
    has_liked: bool = False
    has_disliked: bool = False
    author_name: Optional[str] = None

class PaginatedGalleryResponse(BaseModel):
    items: List[GalleryPostResponse]
    total: int
    page: int
    size: int
    pages: int

class ApplyContextResponse(BaseModel):
    post_id: int
    task_id: str
    media_type: str
    prompt: Optional[str]
    lora_name: Optional[str] = None
    input_file: Optional[str]
    input_file_url: Optional[str]
    width: Optional[int]
    height: Optional[int]
    duration: Optional[int]
    task_type: str
