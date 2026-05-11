from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class HistoryItem(BaseModel):
    id: int
    task_id: Optional[str]
    type: Optional[str]
    prompt: Optional[str]
    input_file: Optional[str]
    output_file: Optional[str]
    output_file_url: Optional[str] = None
    created_at: datetime
    allow_contribute: Optional[bool] = True
    source: Optional[str] = "bot"
    is_public: Optional[bool] = False
    is_favorited: Optional[bool] = False

    class Config:
        from_attributes = True


class PaginatedHistory(BaseModel):
    items: List[HistoryItem]
    total: int
    page: int
    size: int


class CheckinResponse(BaseModel):
    success: bool
    current_credits: int
    error_msg: str
    total_days: int
    reward: int
