from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.core.exceptions import InsufficientCreditsError
from src.handlers.callback_router import register_callback
from src.services.fsm_temp_file_service import cleanup_fsm_temp_files
from src.services.permission_service import permission_service
from src.services.qqcc_regenerate_metadata import (
    QQCC_REGENERATE_CALLBACK_PREFIX,
    QQCC_REGENERATE_KIND_QUICK_IMAGE,
    QQCC_REGENERATE_KIND_QUICK_VIDEO,
)
from src.services.qqcc_regeneration_service import (
    QQCCRegenerationError,
    QQCCRegenerationSubmission,
    prepare_qqcc_regeneration_submission,
)
from src.services.qqcc_runtime_context import load_qqcc_config_for_context
from src.services.quick_image_submission_service import run_quick_image_submission_plan
from src.services.quick_video_submission_service import run_quick_video_submission_plan
from src.services.tg_task_result_presentation import resolve_task_id_from_callback_data
from src.utils import create_background_task, robust_send_message, safe_answer_query

logger = logging.getLogger("qqcc_bot.regeneration")


def _resolve_result_message_meta(context, query) -> dict:
    message = getattr(query, "message", None)
    message_id = getattr(message, "message_id", None)
    if message_id is None:
        return {}
    bot_data = getattr(context, "bot_data", {}) or {}
    return bot_data.get(f"msg_meta_{message_id}", {}) or {}


async def _run_submission(
    *,
    submission: QQCCRegenerationSubmission,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int,
    username: str | None,
    status_msg_id: int | None,
) -> None:
    if submission.kind == QQCC_REGENERATE_KIND_QUICK_IMAGE:
        await run_quick_image_submission_plan(
            plan=submission.plan,
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            status_msg_id=status_msg_id,
        )
        return
    if submission.kind == QQCC_REGENERATE_KIND_QUICK_VIDEO:
        await run_quick_video_submission_plan(
            plan=submission.plan,
            context=context,
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            image_path=submission.image_path,
            status_msg_id=status_msg_id,
        )


@register_callback(QQCC_REGENERATE_CALLBACK_PREFIX)
async def regenerate_qqcc_result_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    user = update.effective_user
    chat = update.effective_chat
    if query is None or user is None or chat is None:
        return

    await safe_answer_query(query, text="🔁 正在重新生成...", cache_time=1)
    task_id = resolve_task_id_from_callback_data(
        getattr(query, "data", None),
        QQCC_REGENERATE_CALLBACK_PREFIX,
    )
    if not task_id:
        await safe_answer_query(query, text="记录已失效，请重新生成后再试", show_alert=True)
        return

    submission: QQCCRegenerationSubmission | None = None
    try:
        submission = await prepare_qqcc_regeneration_submission(
            task_id=task_id,
            telegram_user_id=user.id,
            username=user.username,
            message_meta=_resolve_result_message_meta(context, query),
            load_config_func=lambda: load_qqcc_config_for_context(
                context,
                logger=logger,
            ),
        )
        await permission_service.check_quota(
            user.id,
            user.username,
            user.full_name,
            cost=submission.total_cost,
        )
        status_msg = await robust_send_message(
            context.bot,
            chat.id,
            f"🔁 正在重新生成{submission.display_mode_name}，请耐心等待...",
        )
        create_background_task(
            context,
            _run_submission(
                submission=submission,
                context=context,
                chat_id=chat.id,
                user_id=user.id,
                username=user.username,
                status_msg_id=getattr(status_msg, "message_id", None),
            ),
        )
    except InsufficientCreditsError as exc:
        if submission is not None:
            cleanup_fsm_temp_files([submission.image_path])
        await safe_answer_query(
            query,
            text=f"灵石不足：当前 {exc.current}，需要 {exc.cost}",
            show_alert=True,
        )
    except QQCCRegenerationError as exc:
        if submission is not None:
            cleanup_fsm_temp_files([submission.image_path])
        await safe_answer_query(query, text=str(exc), show_alert=True)
    except Exception as exc:
        if submission is not None:
            cleanup_fsm_temp_files([submission.image_path])
        logger.exception("Failed to regenerate QQCC result: %s", exc)
        await safe_answer_query(query, text="重新生成失败，请稍后再试", show_alert=True)
