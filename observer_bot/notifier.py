from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def split_telegram_text(text: str, *, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
        if remaining.startswith("\n"):
            remaining = remaining[1:]
    return chunks


class TelegramAdminNotifier:
    def __init__(self, bot, admin_chat_ids: frozenset[int]):
        self._bot = bot
        self._admin_chat_ids = admin_chat_ids

    async def send_admins(self, text: str) -> None:
        failures = 0
        for chat_id in sorted(self._admin_chat_ids):
            try:
                for chunk in split_telegram_text(text):
                    await self._bot.send_message(chat_id=chat_id, text=chunk)
            except Exception:
                failures += 1
                logger.exception("observer notification failed chat_id=%s", chat_id)
        if failures == len(self._admin_chat_ids):
            raise RuntimeError("observer notification failed for every administrator")
