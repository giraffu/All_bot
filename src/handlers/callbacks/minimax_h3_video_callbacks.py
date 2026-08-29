import contextlib
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core import user_core
from src.handlers.callback_router import register_callback
from src.services.minimax_h3_extension_service import (
    MiniMaxH3ExtensionError,
    load_minimax_h3_chain_for_internal_user,
    present_minimax_h3_stitched_prompt,
    stitch_minimax_h3_histories_and_create_history,
)
from src.services.tg_task_result_presentation import (
    H3_STITCH_CALLBACK_PREFIX,
    build_result_reply_markup,
    record_result_message_meta,
    resolve_task_id_from_callback_data,
)
from src.utils import (
    robust_edit_reply_markup,
    robust_send_video,
    safe_answer_query,
)

logger = logging.getLogger(__name__)


def _done_markup(query, callback_data: str):
    reply_markup = getattr(getattr(query, "message", None), "reply_markup", None)
    if not reply_markup:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ 已完成拼接", callback_data="noop")
                if button.callback_data == callback_data
                else button
                for button in row
            ]
            for row in reply_markup.inline_keyboard
        ]
    )


@register_callback(H3_STITCH_CALLBACK_PREFIX)
async def stitch_minimax_h3_video_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await safe_answer_query(query, text="🔗 正在免费拼接 H3 视频，请稍候...", cache_time=1)
    task_id = resolve_task_id_from_callback_data(
        query.data,
        H3_STITCH_CALLBACK_PREFIX,
    )
    if not task_id:
        await safe_answer_query(query, text="记录已失效，请重新生成后再试", show_alert=True)
        return
    try:
        internal_user, _ = await user_core.get_or_create_user_by_telegram(
            update.effective_user.id,
            update.effective_user.username,
        )
        histories = await load_minimax_h3_chain_for_internal_user(
            task_id=task_id,
            internal_user_id=internal_user.id,
        )
        stitched = await stitch_minimax_h3_histories_and_create_history(
            histories=histories,
            user_id=internal_user.id,
            source_task_id=task_id,
            source="bot",
        )
        history = stitched.history
        reply_markup = build_result_reply_markup(
            task_type=history.type,
            task_id=history.task_id,
            allow_contribute=history.allow_contribute is not False,
            reply_markup=None,
            result_meta=history.extra_outputs,
        )
        sent = await robust_send_video(
            context.bot,
            update.effective_chat.id,
            stitched.video_bytes,
            caption=f"✅ {stitched.segment_count} 段 H3 视频已免费拼接完成",
            filename="minimax_h3_stitched.mp4",
            reply_markup=reply_markup,
        )
        record_result_message_meta(
            context,
            sent,
            history.type,
            present_minimax_h3_stitched_prompt(history),
            history.task_id,
            result_meta=history.extra_outputs,
        )
        done_markup = _done_markup(query, query.data or "")
        if done_markup is not None:
            with contextlib.suppress(Exception):
                await robust_edit_reply_markup(query.message, reply_markup=done_markup)
    except MiniMaxH3ExtensionError as exc:
        await safe_answer_query(query, text=str(exc), show_alert=True)
    except Exception:
        logger.exception("stitch minimax h3 failed")
        await safe_answer_query(query, text="拼接失败，请稍后再试", show_alert=True)
