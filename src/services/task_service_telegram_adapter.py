from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class TelegramTaskActorContext:
    chat_id: int
    user_id: int
    username: Optional[str]


def extract_actor_from_update(update: Any) -> TelegramTaskActorContext:
    effective_chat = getattr(update, "effective_chat", None)
    effective_user = getattr(update, "effective_user", None)
    chat_id = getattr(effective_chat, "id", None)
    user_id = getattr(effective_user, "id", None)

    if chat_id is None or user_id is None:
        raise ValueError("Telegram update 缺少有效的 chat_id 或 user_id")

    return TelegramTaskActorContext(
        chat_id=chat_id,
        user_id=user_id,
        username=getattr(effective_user, "username", None),
    )
