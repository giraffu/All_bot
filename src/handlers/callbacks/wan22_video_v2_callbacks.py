import contextlib
import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.constants import MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO, MODE_WAN22_VIDEO_V2
from src.handlers.callback_router import register_callback
from src.lora_mapping import extract_prompt_lora_context
from src.core.video_billing import resolve_apply_prompt_and_requested_duration
from src.services.task_service_generation_video import (
    process_image_to_video_generation_task as process_image_to_video_task,
)
from src.services.task_service_generation_wan22 import (
    normalize_wan22_video_v2_chain_task_ids,
    process_wan22_video_v2_generation_task as process_wan22_video_v2_task,
)
from src.services.wan22_video_v2_extension_service import (
    Wan22VideoV2ExtensionError,
    build_full_chain_task_ids,
    download_history_input_file_to_fsm_temp,
    download_last_frame_to_fsm_temp,
    load_owned_wan22_history,
    resolve_extension_resolution_preset,
    stitch_history_videos,
)
from src.utils import (
    create_background_task,
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


def _resolve_prev_task_id(meta: dict) -> str:
    return str(meta.get("wan22_prev_task_id") or "").strip()


def _resolve_reusable_history_prompt_and_lora(history, meta: dict) -> tuple[str, str | None, float]:
    prompt, _requested_duration = resolve_apply_prompt_and_requested_duration(
        getattr(history, "type", None),
        getattr(history, "prompt", None),
        getattr(history, "requested_duration", None),
    )
    prompt, parsed_lora_name, parsed_lora_strength = extract_prompt_lora_context(prompt)
    lora_name = str(meta.get("lora_name") or parsed_lora_name or "").strip() or None
    lora_strength = meta.get("lora_strength")
    try:
        normalized_lora_strength = float(lora_strength)
    except (TypeError, ValueError):
        normalized_lora_strength = parsed_lora_strength or 1.0
    return prompt, lora_name, normalized_lora_strength


@register_callback("wan22v2_stitch_chain")
async def stitch_wan22_video_v2_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    callback_data = query.data or ""
    await safe_answer_query(query, text="🔗 正在拼接视频，请稍候...", cache_time=1)

    meta = _resolve_result_message_meta(context, query)
    chain_task_ids = normalize_wan22_video_v2_chain_task_ids(
        meta.get("wan22_chain_task_ids")
    )
    current_task_id = _resolve_current_task_id(meta)
    full_task_ids = build_full_chain_task_ids(
        chain_task_ids=chain_task_ids,
        current_task_id=current_task_id,
    )
    if len(full_task_ids) < 2:
        await safe_answer_query(query, text="至少需要两段视频才能完成拼接", show_alert=True)
        return

    try:
        histories = [
            await load_owned_wan22_history(
                task_id=task_id,
                telegram_user_id=update.effective_user.id,
                username=update.effective_user.username,
            )
            for task_id in full_task_ids
        ]
        await robust_send_message(
            context.bot,
            update.effective_chat.id,
            f"🔗 正在拼接 {len(histories)} 段视频，请稍候...",
        )
        stitched_video = await stitch_history_videos(histories)
        await robust_send_video(
            context.bot,
            update.effective_chat.id,
            stitched_video,
            caption=f"✅ {len(histories)} 段视频已拼接完成",
            filename="wan22_video_v2_stitched.mp4",
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
    current_task_id = _resolve_current_task_id(meta)
    prev_task_id = _resolve_prev_task_id(meta)
    if not prev_task_id or not current_task_id:
        await safe_answer_query(query, text="记录已失效，请重新生成后再试", show_alert=True)
        return

    try:
        prev_history = await load_owned_wan22_history(
            task_id=prev_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        current_history = await load_owned_wan22_history(
            task_id=current_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        start_image_path = await download_last_frame_to_fsm_temp(
            history=prev_history,
            name_hint="wan22_video_v2_regenerate_start",
        )
        images = [start_image_path]
        use_end_frame = bool(meta.get("wan22_use_end_frame"))
        if use_end_frame:
            end_image_path = await download_history_input_file_to_fsm_temp(
                history=current_history,
                index=1,
                name_hint="wan22_video_v2_regenerate_end",
            )
            images.append(end_image_path)

        status_msg = await robust_send_message(
            context.bot,
            update.effective_chat.id,
            "🔁 正在重新生成当前段落，请耐心等待...",
        )
        create_background_task(
            context,
            (
                process_wan22_video_v2_task(
                    context=context,
                    chat_id=update.effective_chat.id,
                    user_id=update.effective_user.id,
                    username=update.effective_user.username,
                    prompt=str(current_history.prompt or "").strip(),
                    negative_prompt=str(meta.get("wan22_negative_prompt") or "").strip(),
                    images=images,
                    use_end_frame=use_end_frame,
                    status_msg_id=getattr(status_msg, "message_id", None),
                    resolution_preset=resolve_extension_resolution_preset(meta),
                    result_meta={
                        "wan22_prev_task_id": prev_task_id,
                        "wan22_chain_task_ids": normalize_wan22_video_v2_chain_task_ids(
                            meta.get("wan22_chain_task_ids")
                        ),
                    },
                    cleanup=True,
                )
                if current_history.type == MODE_WAN22_VIDEO_V2
                else process_image_to_video_task(
                    context=context,
                    chat_id=update.effective_chat.id,
                    user_id=update.effective_user.id,
                    username=update.effective_user.username,
                    prompt=_resolve_reusable_history_prompt_and_lora(current_history, meta)[0],
                    negative_prompt=str(meta.get("wan22_negative_prompt") or "").strip(),
                    images=images,
                    use_end_frame=use_end_frame,
                    status_msg_id=getattr(status_msg, "message_id", None),
                    resolution_preset=resolve_extension_resolution_preset(meta),
                    wan22_prev_task_id=prev_task_id,
                    wan22_chain_task_ids=normalize_wan22_video_v2_chain_task_ids(
                        meta.get("wan22_chain_task_ids")
                    ),
                    task_type=(
                        MODE_IMAGE_TO_VIDEO
                        if current_history.type == MODE_IMAGE_TO_VIDEO
                        else MODE_CUSTOM_VIDEO
                    ),
                    lora_name=_resolve_reusable_history_prompt_and_lora(current_history, meta)[1],
                    lora_strength=_resolve_reusable_history_prompt_and_lora(current_history, meta)[2],
                    cleanup=True,
                )
            ),
        )
    except Wan22VideoV2ExtensionError as exc:
        await safe_answer_query(query, text=str(exc), show_alert=True)
    except Exception as exc:
        logger.error("regenerate wan22_video_v2 failed: %s", exc, exc_info=True)
        await safe_answer_query(query, text="重新生成失败，请稍后再试", show_alert=True)
