from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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
    
    # User interaction status for current user
    has_liked: bool = False
    has_disliked: bool = False

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
    input_file: Optional[str]
    input_file_url: Optional[str]
    width: Optional[int]
    height: Optional[int]
    duration: Optional[int]
    task_type: str
