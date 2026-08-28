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
    def __init__(self, bot, *, runtime_config_provider, repository):
        self._bot = bot
        self._runtime_config_provider = runtime_config_provider
        self._repository = repository

    async def send_admins(self, text: str, *, event_type: str = "observer_notification") -> None:
        runtime_config = await self._runtime_config_provider.get()
        admin_chat_ids = runtime_config.admin_chat_ids
        if not admin_chat_ids:
            await self._repository.log_notification(
                event_type=event_type,
                destination_chat_id=None,
                status="skipped",
                content_preview=text,
                error_type="no_enabled_recipient",
            )
            return
        failures = 0
        for chat_id in sorted(admin_chat_ids):
            try:
                for chunk in split_telegram_text(text):
                    await self._bot.send_message(chat_id=chat_id, text=chunk)
                await self._repository.log_notification(
                    event_type=event_type,
                    destination_chat_id=chat_id,
                    status="sent",
                    content_preview=text,
                )
            except Exception as exc:
                failures += 1
                logger.exception("observer notification failed chat_id=%s", chat_id)
                await self._repository.log_notification(
                    event_type=event_type,
                    destination_chat_id=chat_id,
                    status="failed",
                    content_preview=text,
                    error_type=type(exc).__name__,
                )
        if failures == len(admin_chat_ids):
            raise RuntimeError("observer notification failed for every administrator")
