from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CreditLedgerItem(BaseModel):
    id: int
    operation_type: str
    direction: Literal["income", "expense"]
    credit_change: int
    current_balance: int
    created_at: datetime
    display_context: dict[str, Any] = Field(default_factory=dict)


class CreditLedgerResponse(BaseModel):
    items: list[CreditLedgerItem]
    total: int
    page: int
    page_size: int
    total_pages: int
