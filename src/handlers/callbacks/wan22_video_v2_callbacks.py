import contextlib
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.handlers.callback_router import register_callback
from src.services.task_service_generation_video import (
    process_image_to_video_generation_task as process_image_to_video_task,
)
from src.services.task_service_generation_wan22 import (
    process_wan22_video_v2_generation_task as process_wan22_video_v2_task,
)
from src.services.advanced_video_submission_service import (
    AdvancedVideoSubmissionReject,
    build_wan22_video_v2_submission_plan,
    create_wan22_video_v2_submission_task,
)
from src.services.wan22_video_v2_extension_service import (
    Wan22VideoV2ExtensionError,
    Wan22VideoV2MissingPreviousSegmentError,
    build_wan22_stitch_plan,
    prepare_wan22_regeneration_fsm_data,
    stitch_histories_and_create_history,
)
from src.services.tg_task_result_presentation import (
    WAN22_REGENERATE_CALLBACK_PREFIX,
    WAN22_STITCH_CALLBACK_PREFIX,
    build_result_reply_markup,
    record_result_message_meta,
    resolve_task_id_from_callback_data,
    resolve_task_id_from_reply_markup,
)
from src.utils import (
    create_background_task,
    robust_edit_reply_markup,
    robust_reply_text,
    robust_send_message,
    robust_send_video,
    safe_answer_query,
)

logger = logging.getLogger(__name__)


def _build_stitch_done_markup(query, callback_data: str):
    if not query.message.reply_markup:
        return None
    keyboard = []
    for row in query.message.reply_markup.inline_keyboard:
        new_row = []
        for btn in row:
            if btn.callback_data == callback_data:
                from telegram import InlineKeyboardButton

                new_row.append(InlineKeyboardButton("✅ 已完成拼接", callback_data="noop"))
            else:
                new_row.append(btn)
        keyboard.append(new_row)
    from telegram import InlineKeyboardMarkup

    return InlineKeyboardMarkup(keyboard)


def _resolve_result_message_meta(context, query) -> dict:
    if not query.message:
        return {}
    return context.bot_data.get(f"msg_meta_{query.message.message_id}", {}) or {}


def _resolve_current_task_id(meta: dict) -> str:
    return str(meta.get("task_id") or "").strip()


def _resolve_callback_task_id(*, meta: dict, query, callback_prefix: str) -> str:
    task_id = resolve_task_id_from_callback_data(
        getattr(query, "data", None),
        callback_prefix,
    )
    if task_id:
        return task_id
    task_id = _resolve_current_task_id(meta)
    if task_id:
        return task_id
    message = getattr(query, "message", None)
    return resolve_task_id_from_reply_markup(getattr(message, "reply_markup", None))


async def _reply_callback_notice(query, text: str) -> None:
    if getattr(query, "message", None):
        await robust_reply_text(query.message, text)


@register_callback("wan22v2_stitch_chain")
async def stitch_wan22_video_v2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    callback_data = query.data or ""
    await safe_answer_query(query, text="🔗 正在拼接视频，请稍候...", cache_time=1)

    meta = _resolve_result_message_meta(context, query)
    current_task_id = _resolve_callback_task_id(
        meta=meta,
        query=query,
        callback_prefix=WAN22_STITCH_CALLBACK_PREFIX,
    )
    if not current_task_id:
        await safe_answer_query(query, text="记录已失效，请重新生成后再试", show_alert=True)
        return

    try:
        stitch_plan = await build_wan22_stitch_plan(
            current_task_id=current_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
            message_meta=meta,
        )
        await robust_send_message(
            context.bot,
            update.effective_chat.id,
            f"🔗 正在拼接 {len(stitch_plan.histories)} 段视频，请稍候...",
        )
        stitched_result = await stitch_histories_and_create_history(
            histories=stitch_plan.histories,
            user_id=stitch_plan.internal_user_id,
            source_task_id=stitch_plan.source_task_id,
            source="bot",
        )
        reply_markup = build_result_reply_markup(
            task_type=stitched_result.task_type,
            task_id=stitched_result.task_id,
            allow_contribute=stitched_result.allow_contribute,
            reply_markup=None,
            result_meta=stitched_result.extra_outputs,
        )
        sent_msg = await robust_send_video(
            context.bot,
            update.effective_chat.id,
            stitched_result.video_bytes,
            caption=f"✅ {stitched_result.segment_count} 段视频已拼接完成",
            filename="wan22_video_v2_stitched.mp4",
            reply_markup=reply_markup,
        )
        record_result_message_meta(
            context,
            sent_msg,
            stitched_result.task_type,
            stitched_result.prompt,
            stitched_result.task_id,
            result_meta=stitched_result.extra_outputs,
        )
        done_markup = _build_stitch_done_markup(query, callback_data)
        if done_markup is not None:
            with contextlib.suppress(Exception):
                await robust_edit_reply_markup(query.message, reply_markup=done_markup)
    except Wan22VideoV2ExtensionError as exc:
        await safe_answer_query(query, text=str(exc), show_alert=True)
    except Exception as exc:
        logger.error("stitch wan22_video_v2 failed: %s", exc, exc_info=True)
        await safe_answer_query(query, text="拼接失败，请稍后再试", show_alert=True)


@register_callback("wan22v2_regenerate")
async def regenerate_wan22_video_v2_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    await safe_answer_query(query, text="🔁 正在重新提交本段视频...", cache_time=1)

    meta = _resolve_result_message_meta(context, query)
    current_task_id = _resolve_callback_task_id(
        meta=meta,
        query=query,
        callback_prefix=WAN22_REGENERATE_CALLBACK_PREFIX,
    )
    if not current_task_id:
        await _reply_callback_notice(query, "记录已失效，请重新生成后再试")
        return

    try:
        seed = await prepare_wan22_regeneration_fsm_data(
            current_task_id=current_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
            message_meta=meta,
        )

        status_msg = await robust_send_message(
            context.bot,
            update.effective_chat.id,
            "🔁 正在重新生成当前段落，请耐心等待...",
        )
        submission_plan = build_wan22_video_v2_submission_plan(data=seed.fsm_data)
        if isinstance(submission_plan, AdvancedVideoSubmissionReject):
            await safe_answer_query(query, text="重新生成失败，请稍后再试", show_alert=True)
            return
        create_background_task(
            context,
            create_wan22_video_v2_submission_task(
                plan=submission_plan,
                context=context,
                chat_id=update.effective_chat.id,
                user_id=update.effective_user.id,
                username=update.effective_user.username,
                process_wan22_video_v2_task_func=process_wan22_video_v2_task,
                process_image_to_video_task_func=process_image_to_video_task,
                status_msg_id=getattr(status_msg, "message_id", None),
            ),
        )
    except Wan22VideoV2MissingPreviousSegmentError:
        await _reply_callback_notice(query, "记录已失效，请重新生成后再试")
    except Wan22VideoV2ExtensionError as exc:
        await safe_answer_query(query, text=str(exc), show_alert=True)
    except Exception as exc:
        logger.error("regenerate wan22_video_v2 failed: %s", exc, exc_info=True)
        await safe_answer_query(query, text="重新生成失败，请稍后再试", show_alert=True)
