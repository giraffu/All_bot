from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import uuid

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import MINIO_BUCKET
from src.domain_config.minimax_h3 import MINIMAX_H3_ADDON_MODELS
from src.domain_config.task_type_registry import is_gallery_supported_task_type
from src.handlers.callback_router import register_callback
from src.services.advanced_video_pro_submission_service import (
    build_advanced_video_pro_submission_plan,
    submit_advanced_video_pro_plan,
)
from src.services.advanced_video_prompt_task_service import (
    cleanup_prompt_draft_objects,
)
from src.services.advanced_video_prompt_task_store import (
    advanced_video_prompt_task_store,
)
from src.services.fsm_temp_file_service import FSM_TEMP_DIR, cleanup_fsm_temp_files
from src.services.permission_service import permission_service
from src.services.storage import storage
from src.utils import create_background_task, safe_answer_query

logger = logging.getLogger("bot.prompt_optimizer.callbacks")


def _token(callback_data: str) -> str:
    return str(callback_data or "").partition(":")[2].strip()


async def _owned_draft(update, context):
    query = update.callback_query
    draft = await advanced_video_prompt_task_store.get(_token(query.data))
    if (
        draft is None
        or int(draft.telegram_user_id) != int(update.effective_user.id)
        or int(draft.chat_id) != int(update.effective_chat.id)
    ):
        await safe_answer_query(
            query,
            text="该提示词结果不存在或不属于当前账号。"
            if getattr(context, "lang", "zh") != "en"
            else "This prompt result is unavailable for the current account.",
            show_alert=True,
        )
        return None
    return draft


def _confirmation_text(draft) -> str:
    addons = "、".join(draft.addon_models) if draft.addon_models else "无"
    if draft.language == "en":
        addons = ", ".join(draft.addon_models) if draft.addon_models else "None"
        return (
            "Confirm generation with the frozen settings:\n"
            f"Mode: {draft.mode}\nDuration: {draft.duration}s\n"
            f"Quality: {draft.resolution_preset}\nEnhancements: {addons}\n"
            f"Cost: {draft.generation_cost} credits"
        )
    return (
        "请确认使用优化提示词生成：\n"
        f"模式：{draft.mode}\n时长：{draft.duration} 秒\n"
        f"画质：{draft.resolution_preset}\n效果增强：{addons}\n"
        f"预计消耗：{draft.generation_cost} 灵石"
    )


@register_callback("avpopt_prepare:")
async def prepare_advanced_video_prompt_generation(update, context):
    query = update.callback_query
    draft = await _owned_draft(update, context)
    if draft is None:
        return
    await safe_answer_query(query)
    if draft.status in {"generation_submitting", "generation_submitted"}:
        await query.message.reply_text(
            "该生成任务已经提交。" if draft.language == "zh" else "This generation task was already submitted."
        )
        return
    if draft.status != "ready" or not draft.optimized_prompt:
        await query.message.reply_text(
            "提示词结果尚不可用。" if draft.language == "zh" else "The prompt result is not ready."
        )
        return
    keyboard = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                "✅ 确认扣费并生成" if draft.language == "zh" else "✅ Confirm and generate",
                callback_data=f"avpopt_confirm:{draft.token}",
            ),
            InlineKeyboardButton(
                "暂不生成" if draft.language == "zh" else "Not now",
                callback_data=f"avpopt_keep:{draft.token}",
            ),
        ]]
    )
    await query.message.reply_text(_confirmation_text(draft), reply_markup=keyboard)


async def _materialize_draft_images(draft) -> list[str]:
    os.makedirs(FSM_TEMP_DIR, exist_ok=True)
    paths: list[str] = []
    try:
        for index, (object_key, suffix) in enumerate(
            zip(draft.object_keys, draft.image_suffixes)
        ):
            path = os.path.join(
                FSM_TEMP_DIR,
                f"{uuid.uuid4().hex}_prompt_draft_{index}{suffix}",
            )
            await asyncio.to_thread(
                storage.client.fget_object,
                MINIO_BUCKET,
                object_key,
                path,
            )
            paths.append(path)
        return paths
    except Exception:
        cleanup_fsm_temp_files(paths)
        raise


async def _submit_confirmed_generation(draft, *, context) -> None:
    local_paths: list[str] = []
    try:
        local_paths = await _materialize_draft_images(draft)
        plan = build_advanced_video_pro_submission_plan(
            mode=draft.mode,
            prompt=draft.optimized_prompt or draft.original_prompt,
            images=local_paths,
            reference_descriptions=draft.reference_descriptions,
            duration=draft.duration,
            resolution_preset=draft.resolution_preset,
            aspect_ratio=draft.aspect_ratio,
            addon_items=[
                {"name": name}
                for name in draft.addon_models
                if name in MINIMAX_H3_ADDON_MODELS
            ],
        )
        await submit_advanced_video_pro_plan(
            plan,
            context=context,
            chat_id=draft.chat_id,
            user_id=draft.telegram_user_id,
            username=draft.username,
            cleanup=True,
            allow_contribute=is_gallery_supported_task_type(plan.task_type),
        )
        await advanced_video_prompt_task_store.save(
            draft.with_updates(status="generation_submitted"),
            monitor=False,
        )
        await cleanup_prompt_draft_objects(draft.object_keys)
    except Exception as exc:
        logger.warning(
            "confirmed prompt generation failed token=%s error_type=%s",
            draft.token,
            type(exc).__name__,
        )
        await advanced_video_prompt_task_store.save(
            draft.with_updates(status="ready", error_code="generation_submit_failed"),
            monitor=False,
        )
        with contextlib.suppress(Exception):
            await context.bot.send_message(
                chat_id=draft.chat_id,
                text=(
                    "生成任务提交失败，提示词结果仍保留，可稍后重试。"
                    if draft.language == "zh"
                    else "Generation submission failed. The prompt result remains available for retry."
                ),
            )
    finally:
        cleanup_fsm_temp_files(local_paths)


@register_callback("avpopt_confirm:")
async def confirm_advanced_video_prompt_generation(update, context):
    query = update.callback_query
    draft = await _owned_draft(update, context)
    if draft is None:
        return
    if draft.status != "ready" or not draft.optimized_prompt:
        await safe_answer_query(
            query,
            text="该任务已经提交或结果已失效。"
            if draft.language == "zh"
            else "This task was already submitted or expired.",
            show_alert=True,
        )
        return
    try:
        await permission_service.check_quota(
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.full_name,
            cost=draft.generation_cost,
        )
    except Exception:
        await safe_answer_query(
            query,
            text=f"余额不足，需要 {draft.generation_cost} 灵石。"
            if draft.language == "zh"
            else f"Insufficient balance. {draft.generation_cost} credits required.",
            show_alert=True,
        )
        return
    submitting = draft.with_updates(status="generation_submitting", error_code=None)
    await advanced_video_prompt_task_store.save(submitting, monitor=False)
    await safe_answer_query(
        query,
        text="已确认，正在提交生成任务。"
        if draft.language == "zh"
        else "Confirmed. Submitting the generation task.",
    )
    with contextlib.suppress(Exception):
        await query.message.edit_reply_markup(reply_markup=None)
    create_background_task(
        context,
        _submit_confirmed_generation(submitting, context=context),
    )


@register_callback("avpopt_keep:")
async def keep_advanced_video_prompt_result(update, context):
    draft = await _owned_draft(update, context)
    if draft is None:
        return
    await safe_answer_query(
        update.callback_query,
        text="结果将保留 24 小时。" if draft.language == "zh" else "The result remains available for 24 hours.",
    )
    with contextlib.suppress(Exception):
        await update.callback_query.message.edit_reply_markup(reply_markup=None)
