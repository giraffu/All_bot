from __future__ import annotations

import json

import pytest

from src.services.advanced_video_prompt_task_store import (
    AdvancedVideoPromptDraft,
    AdvancedVideoPromptTaskStore,
)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.sorted_sets = {}

    async def setex(self, key, ttl, value):
        self.values[key] = (ttl, value)

    async def get(self, key):
        item = self.values.get(key)
        return item[1] if item else None

    async def zadd(self, key, mapping):
        self.sorted_sets.setdefault(key, {}).update(mapping)

    async def zrem(self, key, member):
        self.sorted_sets.setdefault(key, {}).pop(member, None)

    async def zrange(self, key, start, end):
        members = sorted(
            self.sorted_sets.get(key, {}),
            key=self.sorted_sets.get(key, {}).get,
        )
        return members[start:] if end == -1 else members[start : end + 1]


def build_draft(**overrides):
    payload = dict(
        token="draft-token",
        internal_user_id=77,
        telegram_user_id=7007,
        username="alice",
        chat_id=99,
        language="zh",
        client_request_id="request-id",
        mode="i2v",
        original_prompt="original",
        duration=10,
        resolution_preset="preview",
        aspect_ratio="source",
        addon_models=(),
        reference_descriptions=(),
        object_keys=("staging/user-uploads/77/start.png",),
        image_suffixes=(".png",),
        generation_cost=20,
        status="submitted",
        created_at=100.0,
        updated_at=100.0,
        optimizer_task_id="optimizer-1",
    )
    payload.update(overrides)
    return AdvancedVideoPromptDraft(**payload)


@pytest.mark.asyncio
async def test_prompt_draft_survives_fsm_cleanup_and_remains_indexed_for_delivery():
    redis = FakeRedis()
    store = AdvancedVideoPromptTaskStore(redis=redis, prefix="test:")
    draft = build_draft()

    await store.save(draft)

    restored = await store.get(draft.token)
    pending = await store.list_pending()

    assert restored == draft
    assert pending == [draft]
    ttl, raw = redis.values["test:bot_prompt_draft:draft-token"]
    assert ttl == 24 * 60 * 60
    assert json.loads(raw)["original_prompt"] == "original"


@pytest.mark.asyncio
async def test_delivered_prompt_draft_stays_actionable_but_leaves_monitor_index():
    redis = FakeRedis()
    store = AdvancedVideoPromptTaskStore(redis=redis, prefix="test:")
    draft = build_draft(status="ready", optimized_prompt="optimized")
    await store.save(draft)

    await store.stop_monitoring(draft.token)

    assert await store.list_pending() == []
    assert (await store.get(draft.token)).optimized_prompt == "optimized"
