from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, replace
from typing import Any

from config import REDIS_PREFIX
from src.services.redis_client import redis_client

PROMPT_DRAFT_TTL_SECONDS = 24 * 60 * 60
PROMPT_DRAFT_SCHEMA_VERSION = "allbot.bot_prompt_draft.v1"


@dataclass(frozen=True, slots=True)
class AdvancedVideoPromptDraft:
    token: str
    internal_user_id: int
    telegram_user_id: int
    username: str | None
    chat_id: int
    language: str
    client_request_id: str
    mode: str
    original_prompt: str
    duration: int
    resolution_preset: str
    aspect_ratio: str
    addon_models: tuple[str, ...]
    reference_descriptions: tuple[str, ...]
    object_keys: tuple[str, ...]
    image_suffixes: tuple[str, ...]
    generation_cost: int
    status: str
    created_at: float
    updated_at: float
    optimizer_task_id: str | None = None
    optimized_prompt: str | None = None
    queue_position: int | None = None
    running_at: float | None = None
    completed_at: float | None = None
    delivered_message_ids: tuple[int, ...] = ()
    error_code: str | None = None
    main_model: str = "10eros"
    addon_items: tuple[dict[str, Any], ...] = ()
    schema_version: str = PROMPT_DRAFT_SCHEMA_VERSION

    def with_updates(self, **changes: Any) -> "AdvancedVideoPromptDraft":
        changes.setdefault("updated_at", time.time())
        return replace(self, **changes)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str | bytes) -> "AdvancedVideoPromptDraft":
        payload = json.loads(raw)
        if payload.get("schema_version") != PROMPT_DRAFT_SCHEMA_VERSION:
            raise ValueError("unsupported prompt draft schema")
        for key in (
            "addon_models",
            "addon_items",
            "reference_descriptions",
            "object_keys",
            "image_suffixes",
            "delivered_message_ids",
        ):
            payload[key] = tuple(payload.get(key) or ())
        return cls(**payload)


class AdvancedVideoPromptTaskStore:
    def __init__(self, *, redis=None, prefix: str = REDIS_PREFIX) -> None:
        self.redis = redis or redis_client.redis
        self.prefix = prefix

    def _draft_key(self, token: str) -> str:
        return f"{self.prefix}bot_prompt_draft:{token}"

    @property
    def _pending_key(self) -> str:
        return f"{self.prefix}bot_prompt_drafts:pending"

    async def save(
        self,
        draft: AdvancedVideoPromptDraft,
        *,
        monitor: bool = True,
    ) -> None:
        await self.redis.setex(
            self._draft_key(draft.token),
            PROMPT_DRAFT_TTL_SECONDS,
            draft.to_json(),
        )
        if monitor:
            await self.redis.zadd(self._pending_key, {draft.token: draft.created_at})
        else:
            await self.stop_monitoring(draft.token)

    async def get(self, token: str) -> AdvancedVideoPromptDraft | None:
        raw = await self.redis.get(self._draft_key(token))
        return AdvancedVideoPromptDraft.from_json(raw) if raw else None

    async def list_pending(self) -> list[AdvancedVideoPromptDraft]:
        tokens = await self.redis.zrange(self._pending_key, 0, -1)
        drafts: list[AdvancedVideoPromptDraft] = []
        for raw_token in tokens:
            token = raw_token.decode() if isinstance(raw_token, bytes) else str(raw_token)
            draft = await self.get(token)
            if draft is None:
                await self.stop_monitoring(token)
                continue
            drafts.append(draft)
        return drafts

    async def stop_monitoring(self, token: str) -> None:
        await self.redis.zrem(self._pending_key, token)


advanced_video_prompt_task_store = AdvancedVideoPromptTaskStore()
