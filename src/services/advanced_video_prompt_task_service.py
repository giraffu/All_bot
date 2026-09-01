from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import MINIO_BUCKET
from shared.r2_retention_contract import build_staged_user_upload_key
from src.services.advanced_video_prompt_optimizer_service import (
    submit_advanced_video_prompt_task,
)
from src.services.advanced_video_prompt_task_store import (
    AdvancedVideoPromptDraft,
    AdvancedVideoPromptTaskStore,
    advanced_video_prompt_task_store,
)
from src.services.storage import storage
from src.web_api.services.prompt_result_store import get_owned_prompt_result
from src.web_api.services.task_runtime_api_service import (
    get_task_status_payload_for_user,
)

logger = logging.getLogger("bot.prompt_optimizer")
DELIVERY_POLL_SECONDS = 2.0
TELEGRAM_RESULT_CHUNK_SIZE = 3500


async def _default_upload_object(path: str, object_key: str) -> bool:
    return bool(await asyncio.to_thread(storage.upload_file, path, object_key))


async def _default_remove_object(object_key: str) -> None:
    await asyncio.to_thread(storage.client.remove_object, MINIO_BUCKET, object_key)


async def cleanup_prompt_draft_objects(
    object_keys: tuple[str, ...] | list[str],
    *,
    remove_object: Callable[[str], Awaitable[None]] = _default_remove_object,
) -> None:
    for object_key in object_keys:
        with contextlib.suppress(Exception):
            await remove_object(object_key)


async def start_advanced_video_prompt_task(
    *,
    token: str,
    internal_user_id: int,
    telegram_user_id: int,
    username: str | None,
    chat_id: int,
    language: str,
    client_request_id: str,
    mode: str,
    original_prompt: str,
    image_paths: list[str],
    duration: int,
    resolution_preset: str,
    aspect_ratio: str,
    addon_models: list[str],
    reference_descriptions: list[str],
    generation_cost: int,
    main_model: str = "10eros_bf16",
    addon_items: list[dict[str, Any]] | None = None,
    save_draft=None,
    upload_object: Callable[[str, str], Awaitable[bool]] = _default_upload_object,
    submit_optimizer=None,
    now: Callable[[], float] = time.time,
) -> AdvancedVideoPromptDraft:
    save_draft = save_draft or advanced_video_prompt_task_store.save
    submit_optimizer = submit_optimizer or submit_advanced_video_prompt_task
    timestamp = now()
    object_keys = tuple(
        build_staged_user_upload_key(
            user_id=internal_user_id,
            upload_id=f"botprompt-{token}-{index}",
            filename=Path(path).name,
        )
        for index, path in enumerate(image_paths)
    )
    draft = AdvancedVideoPromptDraft(
        token=token,
        internal_user_id=int(internal_user_id),
        telegram_user_id=int(telegram_user_id),
        username=username,
        chat_id=int(chat_id),
        language="en" if language == "en" else "zh",
        client_request_id=client_request_id,
        mode=mode,
        original_prompt=original_prompt,
        duration=int(duration),
        resolution_preset=resolution_preset,
        aspect_ratio=aspect_ratio,
        addon_models=tuple(addon_models),
        reference_descriptions=tuple(reference_descriptions),
        object_keys=object_keys,
        image_suffixes=tuple(Path(path).suffix or ".jpg" for path in image_paths),
        generation_cost=int(generation_cost),
        main_model=str(main_model or "10eros_bf16"),
        addon_items=tuple(dict(item) for item in (addon_items or [])),
        status="staging",
        created_at=timestamp,
        updated_at=timestamp,
    )
    await save_draft(draft, monitor=True)
    try:
        for path, object_key in zip(image_paths, object_keys):
            if not await upload_object(path, object_key):
                raise RuntimeError("prompt media staging failed")
        draft = draft.with_updates(status="submitting")
        await save_draft(draft, monitor=True)
        task_id = await submit_optimizer(
            internal_user_id=internal_user_id,
            username=username,
            mode=mode,
            prompt=original_prompt,
            object_keys=object_keys,
            duration_seconds=duration,
            client_request_id=client_request_id,
        )
        draft = draft.with_updates(status="submitted", optimizer_task_id=str(task_id))
        await save_draft(draft, monitor=True)
        return draft
    except Exception:
        await cleanup_prompt_draft_objects(object_keys)
        failed = draft.with_updates(status="failed", error_code="submission_failed")
        await save_draft(failed, monitor=False)
        raise


def _split_result_text(text: str) -> list[str]:
    normalized = str(text or "").strip()
    return [
        normalized[index : index + TELEGRAM_RESULT_CHUNK_SIZE]
        for index in range(0, len(normalized), TELEGRAM_RESULT_CHUNK_SIZE)
    ] or [""]


async def deliver_advanced_video_prompt_result(
    draft: AdvancedVideoPromptDraft,
    *,
    result_text: str,
    bot,
    store: AdvancedVideoPromptTaskStore = advanced_video_prompt_task_store,
    now: Callable[[], float] = time.time,
) -> AdvancedVideoPromptDraft:
    completed_at = now()
    chunks = _split_result_text(result_text)
    message_ids: list[int] = []
    for index, chunk in enumerate(chunks):
        is_last = index == len(chunks) - 1
        if index == 0:
            prefix = (
                "✨ 提示词优化完成\n\n"
                if draft.language == "zh"
                else "✨ Prompt optimization complete\n\n"
            )
        else:
            prefix = ""
        suffix = ""
        reply_markup = None
        if is_last:
            elapsed = max(0.0, completed_at - draft.created_at)
            suffix = (
                f"\n\n总耗时 {elapsed:.1f} 秒。可继续使用其他功能，结果会保留 24 小时。"
                if draft.language == "zh"
                else f"\n\nElapsed {elapsed:.1f}s. This result remains available for 24 hours."
            )
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🎬 使用此提示词生成"
                            if draft.language == "zh"
                            else "🎬 Generate with this prompt",
                            callback_data=f"avpopt_prepare:{draft.token}",
                        )
                    ]
                ]
            )
        sent = await bot.send_message(
            chat_id=draft.chat_id,
            text=f"{prefix}{chunk}{suffix}",
            reply_markup=reply_markup,
        )
        if getattr(sent, "message_id", None) is not None:
            message_ids.append(int(sent.message_id))
    ready = draft.with_updates(
        status="ready",
        optimized_prompt=str(result_text).strip(),
        completed_at=completed_at,
        delivered_message_ids=tuple(message_ids),
    )
    await store.save(ready, monitor=False)
    await store.stop_monitoring(draft.token)
    return ready


async def process_advanced_video_prompt_draft(
    draft: AdvancedVideoPromptDraft,
    *,
    bot,
    store: AdvancedVideoPromptTaskStore = advanced_video_prompt_task_store,
    get_result=get_owned_prompt_result,
    get_status=get_task_status_payload_for_user,
    now: Callable[[], float] = time.time,
) -> None:
    if draft.status in {"staging", "submitting"} or not draft.optimizer_task_id:
        if now() - draft.updated_at > 120:
            failed = draft.with_updates(
                status="failed", error_code="interrupted_submission"
            )
            await store.save(failed, monitor=False)
            await store.stop_monitoring(draft.token)
            await cleanup_prompt_draft_objects(draft.object_keys)
        return
    result = await get_result(draft.optimizer_task_id, draft.internal_user_id)
    if result and str(result.get("result_text") or "").strip():
        await deliver_advanced_video_prompt_result(
            draft,
            result_text=str(result["result_text"]),
            bot=bot,
            store=store,
            now=now,
        )
        return
    if result and result.get("status") == "failed":
        text = (
            "提示词优化失败，原提示词已保留；本次优化费用会按任务状态自动退回。"
            if draft.language == "zh"
            else "Prompt optimization failed. The original prompt was preserved and the optimizer charge will be refunded automatically."
        )
        await bot.send_message(chat_id=draft.chat_id, text=text)
        failed = draft.with_updates(
            status="failed", completed_at=now(), error_code="optimizer_failed"
        )
        await store.save(failed, monitor=False)
        await store.stop_monitoring(draft.token)
        await cleanup_prompt_draft_objects(draft.object_keys)
        return
    with contextlib.suppress(Exception):
        status = await get_status(
            task_id=draft.optimizer_task_id,
            user_id=draft.internal_user_id,
        )
        changes: dict[str, Any] = {}
        if status.get("status") == "running" and draft.running_at is None:
            changes["running_at"] = now()
        queue_pos = status.get("queue_pos")
        if queue_pos is not None:
            changes["queue_position"] = int(queue_pos)
        if changes:
            await store.save(draft.with_updates(**changes), monitor=True)


async def run_advanced_video_prompt_delivery_loop(
    application,
    *,
    store: AdvancedVideoPromptTaskStore = advanced_video_prompt_task_store,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    while True:
        try:
            for draft in await store.list_pending():
                try:
                    await process_advanced_video_prompt_draft(
                        draft,
                        bot=application.bot,
                        store=store,
                    )
                except Exception:
                    logger.exception(
                        "prompt draft delivery failed token=%s status=%s",
                        draft.token,
                        draft.status,
                    )
        except Exception:
            logger.exception("prompt draft monitor scan failed")
        await sleep(DELIVERY_POLL_SECONDS)
