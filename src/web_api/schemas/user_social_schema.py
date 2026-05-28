from typing import List, Optional

from pydantic import BaseModel

from src.web_api.schemas.gallery_schema import GalleryPostResponse


class PublicUserSummary(BaseModel):
    id: int
    author_name: str
    username: Optional[str] = None
    user_group: str
    current_identity: str
    checkin_count: int = 0
    total_public_posts: int = 0
    followers_count: int = 0
    following_count: int = 0
    is_following: bool = False
    is_self: bool = False


class PublicUserProfileResponse(BaseModel):
    user: PublicUserSummary
    recent_posts: List[GalleryPostResponse]


class FollowingListResponse(BaseModel):
    items: List[PublicUserSummary]
    total: int


class FollowActionResponse(BaseModel):
    success: bool = True
    is_following: bool
