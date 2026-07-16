from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class HistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: Optional[str]
    type: Optional[str]
    prompt: Optional[str]
    prompt_model: Optional[Dict[str, Any]] = None
    input_file: Optional[str]
    output_file: Optional[str]
    input_file_urls: List[str] = Field(default_factory=list)
    billing_resolution: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None
    requested_duration: Optional[int] = None
    output_file_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    extra_outputs: Dict[str, Any] = Field(default_factory=dict)
    result_meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    allow_contribute: Optional[bool] = True
    source: Optional[str] = "bot"
    is_public: Optional[bool] = False
    is_favorited: Optional[bool] = False


class PaginatedHistory(BaseModel):
    items: List[HistoryItem]
    total: int
    page: int
    size: int


class Wan22HistoryChainResponse(BaseModel):
    current_task_id: str
    items: List[HistoryItem]


class LtxHistoryChainResponse(BaseModel):
    current_task_id: str
    items: List[HistoryItem]


class CheckinResponse(BaseModel):
    success: bool
    current_credits: int
    error_msg: str
    total_days: int
    reward: int


class PreferencesUpdate(BaseModel):
    language_code: str
