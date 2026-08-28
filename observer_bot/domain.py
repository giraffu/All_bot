from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GroupMessage:
    chat_id: int
    message_id: int
    thread_id: int | None
    chat_title: str
    author_user_id: int | None
    author_username: str
    author_display_name: str
    content: str
    sent_at: datetime
    edited_at: datetime | None = None

