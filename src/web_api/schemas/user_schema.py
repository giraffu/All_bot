from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class HistoryItem(BaseModel):
    id: int
    task_id: Optional[str]
    type: Optional[str]
    prompt: Optional[str]
    input_file: Optional[str]
    output_file: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class PaginatedHistory(BaseModel):
    items: List[HistoryItem]
    total: int
    page: int
    size: int
