import contextlib
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.handlers.callback_router import register_callback
from src.services.ltx_video_extension_service import (
    LtxVideoExtensionError,
    build_ltx_full_chain_task_ids,
    extract_ltx_history_context,
    load_owned_ltx_history,
    normalize_ltx_video_chain_task_ids,
    stitch_ltx_histories_and_create_history,
)
from src.services.tg_task_result_presentation import (
    LTX_STITCH_CALLBACK_PREFIX,
    build_result_reply_markup,
    record_result_message_meta,
    resolve_task_id_from_callback_data,
    resolve_task_id_from_reply_markup,
)
from src.utils import (
    robust_edit_reply_markup,
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
                new_row.append(InlineKeyboardButton("✅ 已完成拼接", callback_data="noop"))
            else:
                new_row.append(btn)
        keyboard.append(new_row)
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


def _merge_history_context_into_meta(history, meta: dict) -> dict[str, object]:
    return {
        **extract_ltx_history_context(getattr(history, "extra_outputs", None)),
        **meta,
    }


@register_callback("ltx_stitch_chain")
async def stitch_ltx_video_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    callback_data = query.data or ""
    await safe_answer_query(query, text="🔗 正在拼接 LTX 视频，请稍候...", cache_time=1)

    meta = _resolve_result_message_meta(context, query)
    current_task_id = _resolve_callback_task_id(
        meta=meta,
        query=query,
        callback_prefix=LTX_STITCH_CALLBACK_PREFIX,
    )
    if not current_task_id:
        await safe_answer_query(query, text="记录已失效，请重新生成后再试", show_alert=True)
        return

    try:
        current_history = await load_owned_ltx_history(
            task_id=current_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        meta = _merge_history_context_into_meta(current_history, meta)
    except LtxVideoExtensionError as exc:
        await safe_answer_query(query, text=str(exc), show_alert=True)
        return

    chain_task_ids = normalize_ltx_video_chain_task_ids(
        meta.get("ltx_chain_task_ids")
    )
    full_task_ids = build_ltx_full_chain_task_ids(
        chain_task_ids=chain_task_ids,
        current_task_id=current_task_id,
    )
    if len(full_task_ids) < 2:
        await safe_answer_query(query, text="至少需要两段 LTX 视频才能完成拼接", show_alert=True)
        return

    try:
        history_cache = {current_task_id: current_history}
        histories = []
        for task_id in full_task_ids:
            history = history_cache.get(task_id)
            if history is None:
                history = await load_owned_ltx_history(
                    task_id=task_id,
                    telegram_user_id=update.effective_user.id,
                    username=update.effective_user.username,
                )
                history_cache[task_id] = history
            histories.append(history)
        await robust_send_message(
            context.bot,
            update.effective_chat.id,
            f"🔗 正在拼接 {len(histories)} 段 LTX 视频，请稍候...",
        )
        internal_user_id = int(getattr(histories[0], "user_id", 0) or 0)
        if not internal_user_id:
            raise LtxVideoExtensionError("未找到用户信息，无法保存拼接结果。")
        stitched_result = await stitch_ltx_histories_and_create_history(
            histories=histories,
            user_id=internal_user_id,
            source_task_id=current_task_id,
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
            caption=f"✅ {stitched_result.segment_count} 段 LTX 视频已拼接完成",
            filename="ltx_video_stitched.mp4",
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
    except LtxVideoExtensionError as exc:
        await safe_answer_query(query, text=str(exc), show_alert=True)
    except Exception as exc:
        logger.error("stitch ltx_video failed: %s", exc, exc_info=True)
        await safe_answer_query(query, text="拼接失败，请稍后再试", show_alert=True)
