from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.handlers.callbacks import advanced_video_prompt_callbacks as callbacks
from src.services.advanced_video_prompt_task_store import AdvancedVideoPromptDraft


def build_draft(**changes):
    payload = dict(
        token="draft-token",
        internal_user_id=77,
        telegram_user_id=7007,
        username="alice",
        chat_id=99,
        language="zh",
        client_request_id="request-id",
        mode="t2v",
        original_prompt="original",
        duration=5,
        resolution_preset="preview",
        aspect_ratio="16:9",
        addon_models=(),
        reference_descriptions=(),
        object_keys=(),
        image_suffixes=(),
        generation_cost=9,
        status="ready",
        created_at=100.0,
        updated_at=110.0,
        optimizer_task_id="optimizer-1",
        optimized_prompt="optimized",
    )
    payload.update(changes)
    return AdvancedVideoPromptDraft(**payload)


def build_update(callback_data):
    message = SimpleNamespace(
        reply_text=AsyncMock(),
        edit_reply_markup=AsyncMock(),
    )
    return SimpleNamespace(
        callback_query=SimpleNamespace(
            data=callback_data, message=message, answer=AsyncMock()
        ),
        effective_user=SimpleNamespace(
            id=7007,
            username="alice",
            full_name="Alice",
        ),
        effective_chat=SimpleNamespace(id=99),
    )


@pytest.mark.asyncio
async def test_result_action_requires_explicit_second_confirmation(monkeypatch):
    draft = build_draft()
    monkeypatch.setattr(
        callbacks.advanced_video_prompt_task_store,
        "get",
        AsyncMock(return_value=draft),
    )
    monkeypatch.setattr(callbacks, "safe_answer_query", AsyncMock())
    update = build_update("avpopt_prepare:draft-token")

    await callbacks.prepare_advanced_video_prompt_generation(
        update,
        SimpleNamespace(lang="zh"),
    )

    text = update.callback_query.message.reply_text.await_args.args[0]
    keyboard = update.callback_query.message.reply_text.await_args.kwargs[
        "reply_markup"
    ]
    assert "预计消耗：9 灵石" in text
    assert keyboard.inline_keyboard[0][0].callback_data == "avpopt_confirm:draft-token"


@pytest.mark.asyncio
async def test_confirm_claims_draft_before_background_submission(monkeypatch):
    current = build_draft()

    async def get(_token):
        return current

    async def save(draft, *, monitor):
        nonlocal current
        current = draft

    monkeypatch.setattr(callbacks.advanced_video_prompt_task_store, "get", get)
    monkeypatch.setattr(callbacks.advanced_video_prompt_task_store, "save", save)
    monkeypatch.setattr(callbacks.permission_service, "check_quota", AsyncMock())
    monkeypatch.setattr(callbacks, "safe_answer_query", AsyncMock())
    captured = []
    monkeypatch.setattr(
        callbacks,
        "create_background_task",
        lambda _context, coroutine: captured.append(coroutine),
    )
    update = build_update("avpopt_confirm:draft-token")
    context = SimpleNamespace(lang="zh")

    await callbacks.confirm_advanced_video_prompt_generation(update, context)
    await callbacks.confirm_advanced_video_prompt_generation(update, context)

    assert current.status == "generation_submitting"
    assert len(captured) == 1
    captured[0].close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "image_paths", "allow_contribute"),
    [
        ("t2v", [], False),
        ("i2v", ["start.png"], True),
        ("flf2v", ["start.png", "end.png"], True),
        ("ref2v", ["person.png", "reference.png"], True),
    ],
)
async def test_optimized_h3_generation_preserves_gallery_eligibility(
    monkeypatch,
    mode,
    image_paths,
    allow_contribute,
):
    draft = build_draft(
        mode=mode,
        object_keys=tuple(f"staged-{index}" for index, _path in enumerate(image_paths)),
        image_suffixes=tuple(".png" for _path in image_paths),
    )
    submit = AsyncMock()
    monkeypatch.setattr(
        callbacks,
        "_materialize_draft_images",
        AsyncMock(return_value=image_paths),
    )
    monkeypatch.setattr(callbacks, "submit_advanced_video_pro_plan", submit)
    monkeypatch.setattr(
        callbacks.advanced_video_prompt_task_store,
        "save",
        AsyncMock(),
    )
    monkeypatch.setattr(
        callbacks,
        "cleanup_prompt_draft_objects",
        AsyncMock(),
    )
    monkeypatch.setattr(callbacks, "cleanup_fsm_temp_files", Mock())

    await callbacks._submit_confirmed_generation(
        draft,
        context=SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
    )

    assert submit.await_args.kwargs["allow_contribute"] is allow_contribute


@pytest.mark.asyncio
async def test_optimized_h3_generation_preserves_admin_addon_strengths(monkeypatch):
    draft = build_draft(
        addon_models=("deepthroat",),
        addon_items=({"name": "deepthroat", "strength": 1.25},),
    )
    submit = AsyncMock()
    monkeypatch.setattr(
        callbacks, "_materialize_draft_images", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(callbacks, "submit_advanced_video_pro_plan", submit)
    monkeypatch.setattr(callbacks.advanced_video_prompt_task_store, "save", AsyncMock())
    monkeypatch.setattr(callbacks, "cleanup_prompt_draft_objects", AsyncMock())
    monkeypatch.setattr(callbacks, "cleanup_fsm_temp_files", Mock())

    await callbacks._submit_confirmed_generation(
        draft,
        context=SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock())),
    )

    plan = submit.await_args.args[0]
    assert plan.addon_items == ({"name": "deepthroat", "strength": 1.25},)
