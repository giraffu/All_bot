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
from src.handlers.message_handler_media_entry import (
    UNSUPPORTED_DOCUMENT_MESSAGE,
    UNSUPPORTED_VIDEO_MESSAGE,
    build_media_update_handler,
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
from src.handlers.message_handler_profile_menu import (
    TASK_TYPE_DISPLAY_NAMES,
    handle_checkin_impl,
    handle_personal_center_impl,
    handle_queue_status_impl,
    handle_share_impl,
    handle_switch_lang_impl,
)
from src.handlers.message_handler_prompt import handle_prompt_impl
from src.handlers.utils import (
    _is_mentioned,
    with_db_logging_context,
    ensure_access_and_reward,
)
from src.utils import (
    robust_reply_text,
)
from src.handlers.error_handlers import with_unified_error_handler
from src.logger import logger

os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR_PENETRATION, exist_ok=True)
os.makedirs(TEMPLATE_DIR_QUICK_FACE, exist_ok=True)
os.makedirs(TEMPLATE_DIR_VIDEO_NICE, exist_ok=True)
os.makedirs(TEMP_TEMPLATE_DIR, exist_ok=True)


async def _handle_photo_idle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await media_handle_photo_idle(update, context)


async def _handle_template_contribution(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    return await media_handle_template_contribution(update, context, logger)


handle_photo = build_media_update_handler(
    handler_name="handle_photo",
    handle_media_entry=handle_media_entry,
    is_mentioned=_is_mentioned,
    ensure_access_and_reward=ensure_access_and_reward,
    on_template_contribution=_handle_template_contribution,
    on_photo_idle=_handle_photo_idle,
    handle_media_message_fn=handle_media_message,
    decorators=(with_db_logging_context, with_unified_error_handler),
)

handle_video = build_media_update_handler(
    handler_name="handle_video",
    handle_media_entry=handle_media_entry,
    unsupported_message=UNSUPPORTED_VIDEO_MESSAGE,
    is_mentioned=_is_mentioned,
    ensure_access_and_reward=ensure_access_and_reward,
    on_template_contribution=_handle_template_contribution,
    on_photo_idle=_handle_photo_idle,
    handle_media_message_fn=handle_media_message,
    decorators=(with_db_logging_context, with_unified_error_handler),
)

handle_document = build_media_update_handler(
    handler_name="handle_document",
    handle_media_entry=handle_media_entry,
    unsupported_message=UNSUPPORTED_DOCUMENT_MESSAGE,
    is_mentioned=_is_mentioned,
    ensure_access_and_reward=ensure_access_and_reward,
    on_template_contribution=_handle_template_contribution,
    on_photo_idle=_handle_photo_idle,
    handle_media_message_fn=handle_media_message,
    decorators=(with_db_logging_context, with_unified_error_handler),
)


async def _dispatch_built_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    build_payload,
    include_context: bool = False,
    ensure_reward: bool = False,
):
    if ensure_reward:
        user = update.effective_user
        if not user:
            return None
        await ensure_user_access_reward(context, user)

    reply_kwargs = {"context": context} if include_context else {}
    return await reply_with_built_payload(
        update,
        reply_text=robust_reply_text,
        build_payload=build_payload,
        **reply_kwargs,
    )


def _build_built_menu_handler(
    *,
    handler_name: str,
    build_payload_ref,
    include_context: bool = False,
    ensure_reward: bool = False,
    decorators: tuple = (),
):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
        return await _dispatch_built_menu_handler(
            update,
            context,
            build_payload=build_payload_ref(),
            include_context=include_context,
            ensure_reward=ensure_reward,
        )

    handler.__name__ = handler_name
    for decorator in decorators:
        handler = decorator(handler)
    handler.__name__ = handler_name
    return handler


handle_photo_edit_menu = _build_built_menu_handler(
    handler_name="handle_photo_edit_menu",
    build_payload_ref=lambda: build_photo_edit_payload,
    include_context=True,
    ensure_reward=True,
    decorators=(prompt_route("menu.photo_edit"), with_unified_error_handler),
)

handle_video_edit_menu = _build_built_menu_handler(
    handler_name="handle_video_edit_menu",
    build_payload_ref=lambda: build_video_edit_payload,
    include_context=True,
    decorators=(prompt_route("menu.video_edit"),),
)

handle_gallery_menu = _build_built_menu_handler(
    handler_name="handle_gallery_menu",
    build_payload_ref=lambda: build_gallery_payload,
    include_context=True,
    decorators=(prompt_route("menu.gallery"),),
)

handle_back_to_main_menu = _build_built_menu_handler(
    handler_name="handle_back_to_main_menu",
    build_payload_ref=lambda: build_back_to_main_payload,
    include_context=True,
    decorators=(prompt_route("menu.main_menu"), prompt_route("menu.back_main")),
)

handle_recharge_menu = _build_built_menu_handler(
    handler_name="handle_recharge_menu",
    build_payload_ref=lambda: build_recharge_payload,
    include_context=True,
    decorators=(prompt_route("menu.recharge"),),
)


@with_unified_error_handler
@prompt_route("menu.profile")
async def handle_personal_center(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    return await handle_personal_center_impl(
        update,
        reply_text=robust_reply_text,
        context=context,
        build_payload=build_personal_center_reply,
        reply_with_async_payload=reply_with_async_payload,
        invite_link=CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV",
        web_url="https://web.aivison.it.com/",
    )


@prompt_route("menu.checkin")
async def handle_checkin(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None
):
    return await handle_checkin_impl(
        update,
        context,
        refuge_group_id=REFUGE_GROUP_ID,
        get_reply_message=get_reply_message,
        get_checkin_gate_reply=get_checkin_gate_reply,
        build_checkin_reply=build_checkin_reply,
        reply_text=robust_reply_text,
    )


async def _dispatch_async_menu_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    impl,
    build_payload,
    **impl_kwargs,
):
    return await impl(
        update,
        context=context,
        build_payload=build_payload,
        reply_with_async_payload=reply_with_async_payload,
        reply_text=robust_reply_text,
        **impl_kwargs,
    )


def _build_async_menu_handler(
    *,
    handler_name: str,
    route_keys: tuple[str, ...],
    impl_ref,
    build_payload_ref,
    decorators: tuple = (),
    **impl_kwargs,
):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None):
        return await _dispatch_async_menu_handler(
            update,
            context,
            impl=impl_ref(),
            build_payload=build_payload_ref(),
            **impl_kwargs,
        )

    handler.__name__ = handler_name
    for route_key in route_keys:
        handler = prompt_route(route_key)(handler)
    for decorator in decorators:
        handler = decorator(handler)
    handler.__name__ = handler_name
    return handler


handle_share = _build_async_menu_handler(
    handler_name="handle_share",
    route_keys=("menu.share",),
    impl_ref=lambda: handle_share_impl,
    build_payload_ref=lambda: build_share_reply,
)

handle_switch_lang = _build_async_menu_handler(
    handler_name="handle_switch_lang",
    route_keys=("menu.switch_lang",),
    impl_ref=lambda: handle_switch_lang_impl,
    build_payload_ref=lambda: toggle_user_language,
)

handle_queue_status = _build_async_menu_handler(
    handler_name="handle_queue_status",
    route_keys=("menu.queue",),
    impl_ref=lambda: handle_queue_status_impl,
    build_payload_ref=lambda: get_queue_status_reply,
    task_type_display_names=TASK_TYPE_DISPLAY_NAMES,
)

@with_unified_error_handler
@with_db_logging_context
async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_prompt_impl(
        update,
        context,
        prompt_routes=prompt_routes,
        ensure_user_access_reward=ensure_user_access_reward,
        extract_prompt_message_text=extract_prompt_message_text,
        dispatch_prompt_route=dispatch_prompt_route,
        reply_private_prompt_fallback=reply_private_prompt_fallback,
        reply_text=robust_reply_text,
        logger=logger,
    )
