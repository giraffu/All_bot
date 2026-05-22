import os

from telegram import Update
from telegram.ext import ContextTypes

from config import CHANNEL_INVITE_LINK, REFUGE_GROUP_ID
from src.constants import (
    TEMP_TEMPLATE_DIR,
    TEMPLATE_DIR_PENETRATION,
    TEMPLATE_DIR_QUICK_FACE,
    TEMPLATE_DIR_VIDEO_NICE,
    TMP_DIR,
)
from src.handlers.prompt_router import prompt_route, prompt_routes
from src.handlers.message_handler_common import (
    dispatch_prompt_route,
    ensure_user_access_reward,
    extract_prompt_message_text,
    get_reply_message,
    reply_private_prompt_fallback,
)
from src.handlers.message_handler_media import (
    handle_media_entry,
    handle_media_message,
    handle_photo_idle as media_handle_photo_idle,
    handle_template_contribution as media_handle_template_contribution,
)
from src.handlers.message_handler_menu import (
    build_back_to_main_payload,
    build_gallery_payload,
    build_photo_edit_payload,
    build_recharge_payload,
    build_video_edit_payload,
    reply_with_async_payload,
    reply_with_built_payload,
)
from src.handlers.message_handler_runtime import (
    build_checkin_reply,
    build_personal_center_reply,
    build_share_reply,
    get_checkin_gate_reply,
    get_queue_status_reply,
    toggle_user_language,
)
from src.handlers.utils import (
    _is_mentioned,
    with_db_logging_context,
    ensure_access_and_reward,
)
from src.services.task_service import task_service
from src.utils import (
    robust_reply_text,
)
from src.handlers.error_handlers import with_unified_error_handler
from src.logger import logger

# Re-exporting for compatibility if needed, but preferred to import from constants/utils
process_generation_task = task_service.process_generation_task

os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR_PENETRATION, exist_ok=True)
os.makedirs(TEMPLATE_DIR_QUICK_FACE, exist_ok=True)
os.makedirs(TEMPLATE_DIR_VIDEO_NICE, exist_ok=True)
os.makedirs(TEMP_TEMPLATE_DIR, exist_ok=True)


@with_unified_error_handler
@with_db_logging_context
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_media_entry(
        update,
        context,
        is_mentioned=_is_mentioned,
        ensure_access_and_reward=ensure_access_and_reward,
        on_template_contribution=_handle_template_contribution,
        on_photo_idle=_handle_photo_idle,
        handle_media_message_fn=handle_media_message,
    )


@with_unified_error_handler
@with_db_logging_context
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_media_entry(
        update,
        context,
        unsupported_message="⚠️ 当前模式不支持视频处理。",
        is_mentioned=_is_mentioned,
        ensure_access_and_reward=ensure_access_and_reward,
        on_template_contribution=_handle_template_contribution,
        on_photo_idle=_handle_photo_idle,
        handle_media_message_fn=handle_media_message,
    )


@with_unified_error_handler
@with_db_logging_context
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_media_entry(
        update,
        context,
        unsupported_message="⚠️ 请发送压缩后的图片或视频格式，不要发送原图/文件。",
        is_mentioned=_is_mentioned,
        ensure_access_and_reward=ensure_access_and_reward,
        on_template_contribution=_handle_template_contribution,
        on_photo_idle=_handle_photo_idle,
        handle_media_message_fn=handle_media_message,
    )


async def _handle_photo_idle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await media_handle_photo_idle(update, context)


async def _handle_template_contribution(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    return await media_handle_template_contribution(update, context, logger)


@with_unified_error_handler
@prompt_route("menu.photo_edit")
async def handle_photo_edit_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    message = get_reply_message(update)
    if not message:
        return
    if not update.effective_user:
        return
    user = update.effective_user
    await ensure_user_access_reward(context, user)
    msg, reply_markup = build_photo_edit_payload(context)
    await robust_reply_text(
        message,
        msg,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


@prompt_route("menu.video_edit")
async def handle_video_edit_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    return await reply_with_built_payload(
        update,
        reply_text=robust_reply_text,
        build_payload=build_video_edit_payload,
        context=context,
    )


@prompt_route("menu.gallery")
async def handle_gallery_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    return await reply_with_built_payload(
        update,
        reply_text=robust_reply_text,
        build_payload=build_gallery_payload,
    )


@prompt_route("menu.back_main")
@prompt_route("menu.main_menu")
async def handle_back_to_main_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    return await reply_with_built_payload(
        update,
        reply_text=robust_reply_text,
        build_payload=build_back_to_main_payload,
        context=context,
    )


@prompt_route("menu.recharge")
async def handle_recharge_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    return await reply_with_built_payload(
        update,
        reply_text=robust_reply_text,
        build_payload=build_recharge_payload,
    )


@with_unified_error_handler
@prompt_route("menu.profile")
async def handle_personal_center(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    user = update.effective_user
    if not user:
        return
    invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"
    return await reply_with_async_payload(
        update,
        reply_text=robust_reply_text,
        build_payload=build_personal_center_reply,
        context=context,
        user=user,
        invite_link=invite_link,
        web_url="https://web.aivison.it.com/",
    )


@prompt_route("menu.checkin")
async def handle_checkin(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None
):
    message = get_reply_message(update)
    if not message:
        return
    gate_reply = await get_checkin_gate_reply(update, context, REFUGE_GROUP_ID)
    if gate_reply:
        if gate_reply[0] == "__warning__":
            logger.warning(f"Failed to check refuge group membership: {gate_reply[1]}")
        else:
            msg, reply_markup = gate_reply
            await robust_reply_text(
                message,
                msg,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
            return

    msg = await build_checkin_reply(update, context)
    if not msg:
        return
    await robust_reply_text(message, msg, parse_mode="Markdown")


@prompt_route("menu.share")
async def handle_share(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None
):
    user = update.effective_user
    if not user:
        return
    return await reply_with_async_payload(
        update,
        reply_text=robust_reply_text,
        build_payload=build_share_reply,
        context=context,
        user=user,
    )


TASK_TYPE_DISPLAY_NAMES = {
    "img2img": "task.img2img",
    "img2img_lora": "task.img2img_lora",
    "i2i_pro": "task.i2i_pro",
    "face_swap": "task.face_swap",
    "video_insert": "task.video_insert",
    "video_edit": "task.video_edit",
    "face_video": "task.face_video",
    "ltx_video": "task.ltx_video",
    "t2i-pornmaster-turbo": "task.t2i_pornmaster_turbo",
    "custom_video": "task.custom_video",
    "video_lora": "task.video_lora",
}


@prompt_route("menu.switch_lang")
async def handle_switch_lang(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None
):
    user = update.effective_user
    if not user:
        return
    return await reply_with_async_payload(
        update,
        reply_text=robust_reply_text,
        build_payload=toggle_user_language,
        parse_mode=None,
        context=context,
        user=user,
    )


@prompt_route("menu.queue")
async def handle_queue_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None
):
    return await reply_with_async_payload(
        update,
        reply_text=robust_reply_text,
        build_payload=get_queue_status_reply,
        context=context,
        task_type_display_names=TASK_TYPE_DISPLAY_NAMES,
    )


from src.handlers.error_handlers import with_unified_error_handler


@with_unified_error_handler
@with_db_logging_context
async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user = update.effective_user

    await ensure_user_access_reward(context, user)

    message, text = extract_prompt_message_text(update)
    if not message:
        return
    logger.info(f"handle_prompt received: {text.encode('utf-8')}")
    if not text:
        return

    from src.handlers.prompt_router import GLOBAL_REVERSE_MAP

    route_matched, routed = await dispatch_prompt_route(
        update,
        context,
        text,
        prompt_routes=prompt_routes,
        reverse_map=GLOBAL_REVERSE_MAP,
    )
    if route_matched:
        return routed

    return await reply_private_prompt_fallback(
        message,
        lang=context.lang,
        reply_text=robust_reply_text,
    )
