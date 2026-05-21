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
    build_private_prompt_fallback,
    ensure_user_access_reward,
    get_reply_message,
)
from src.handlers.message_handler_profile import (
    build_checkin_repeat_message,
    build_checkin_success_message,
    build_personal_center_payload,
    build_refuge_checkin_payload,
    build_share_payload,
)
from src.handlers.message_handler_media import (
    handle_media_message,
    handle_photo_idle as media_handle_photo_idle,
    handle_template_contribution as media_handle_template_contribution,
)
from src.handlers.message_handler_menu import (
    build_back_to_main_payload,
    build_gallery_payload,
    build_photo_edit_payload,
    build_queue_status_message,
    build_recharge_payload,
    build_switch_lang_message,
    build_video_edit_payload,
)
from src.handlers.utils import (
    _is_mentioned,
    with_db_logging_context,
    ensure_access_and_reward,
)
from src.services.image_service import image_service
from src.services.permission_service import permission_service
from src.services.task_service import task_service
from src.utils import (
    robust_reply_text,
    create_background_task,
    get_user_channel_status,
    notify_inviter_reward,
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
    if not _is_mentioned(update, context):
        return
    if not await ensure_access_and_reward(update, context):
        return

    return await handle_media_message(
        update,
        context,
        on_template_contribution=_handle_template_contribution,
        on_photo_idle=_handle_photo_idle,
    )


@with_unified_error_handler
@with_db_logging_context
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_mentioned(update, context):
        return
    if not await ensure_access_and_reward(update, context):
        return

    return await handle_media_message(
        update,
        context,
        unsupported_message="⚠️ 当前模式不支持视频处理。",
        on_template_contribution=_handle_template_contribution,
        on_photo_idle=_handle_photo_idle,
    )


@with_unified_error_handler
@with_db_logging_context
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_mentioned(update, context):
        return
    if not await ensure_access_and_reward(update, context):
        return

    return await handle_media_message(
        update,
        context,
        unsupported_message="⚠️ 请发送压缩后的图片或视频格式，不要发送原图/文件。",
        on_template_contribution=_handle_template_contribution,
        on_photo_idle=_handle_photo_idle,
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
    message = get_reply_message(update)
    if not message:
        return
    msg, reply_markup = build_video_edit_payload(context)
    await robust_reply_text(
        message,
        msg,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


@prompt_route("menu.gallery")
async def handle_gallery_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    message = get_reply_message(update)
    if not message:
        return
    msg, _reply_markup = build_gallery_payload()
    await robust_reply_text(
        message,
        msg,
        parse_mode="Markdown",
    )


@prompt_route("menu.back_main")
@prompt_route("menu.main_menu")
async def handle_back_to_main_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    message = get_reply_message(update)
    if not message:
        return
    msg, reply_markup = build_back_to_main_payload(context)
    await robust_reply_text(
        message,
        msg,
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


@prompt_route("menu.recharge")
async def handle_recharge_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    message = get_reply_message(update)
    if not message:
        return
    msg, reply_markup = build_recharge_payload()
    await robust_reply_text(
        message, msg, parse_mode="Markdown", reply_markup=reply_markup
    )


@with_unified_error_handler
@prompt_route("menu.profile")
async def handle_personal_center(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    message = get_reply_message(update)
    if not message:
        return
    if not update.effective_user:
        return
    user = update.effective_user

    is_member = await get_user_channel_status(context.bot, user.id)
    if is_member is not None:
        await permission_service.sync_channel_status(
            user.id, user.username, user.full_name, is_member
        )

    await permission_service.ensure_user(
        user.id, user.username, user.full_name, user.language_code
    )
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name
    invite_link = CHANNEL_INVITE_LINK or "https://t.me/AiVisionAV"

    from src.core.user_facade import get_user_dashboard_info

    dto = await get_user_dashboard_info(user_id, first_name)

    msg, reply_markup = build_personal_center_payload(
        dto,
        invite_link=invite_link,
        web_url="https://web.aivison.it.com/",
    )

    await robust_reply_text(
        message, msg, parse_mode="Markdown", reply_markup=reply_markup
    )


@prompt_route("menu.checkin")
async def handle_checkin(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None
):
    message = get_reply_message(update)
    if not message:
        return
    if REFUGE_GROUP_ID:
        try:
            group_id = (
                int(REFUGE_GROUP_ID)
                if REFUGE_GROUP_ID.lstrip("-").isdigit()
                else REFUGE_GROUP_ID
            )
            member = await context.bot.get_chat_member(
                chat_id=group_id, user_id=update.effective_user.id
            )
            if member.status in ["left", "kicked", "banned"]:
                msg, reply_markup = build_refuge_checkin_payload()
                await robust_reply_text(
                    message,
                    msg,
                    parse_mode="Markdown",
                    reply_markup=reply_markup,
                )
                return
        except Exception as e:
            logger.warning(f"Failed to check refuge group membership: {e}")

    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(update.effective_user.id)
    internal_user_id = internal_user.id

    if not update.effective_user:
        return
    user = update.effective_user

    # 新增逻辑：在签到前强制获取最新频道状态并同步
    is_member = await get_user_channel_status(context.bot, user.id)
    if is_member is not None:
        inviter_id_reward = await permission_service.sync_channel_status(
            user.id, user.username, user.full_name, is_member
        )
        if inviter_id_reward:
            create_background_task(
                context,
                notify_inviter_reward(context.bot, inviter_id_reward, user.full_name),
            )

    (
        success,
        current_credits,
        error_msg,
        total_days,
        reward,
    ) = await permission_service.perform_checkin(user.id, user.username, user.full_name)
    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)

    if success:
        await robust_reply_text(
            message,
            build_checkin_success_message(
                user_group=user_group,
                user_identity=user_identity,
                total_days=total_days,
                reward=reward,
                current_credits=current_credits,
            ),
            parse_mode="Markdown",
        )
    elif error_msg:
        await robust_reply_text(message, error_msg, parse_mode="Markdown")
    else:
        await robust_reply_text(
            message,
            build_checkin_repeat_message(
                user_group=user_group,
                user_identity=user_identity,
                total_days=total_days,
            ),
            parse_mode="Markdown",
        )


@prompt_route("menu.share")
async def handle_share(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None
):
    message = get_reply_message(update)
    if not message:
        return
    if not update.effective_user:
        return
    user_id = update.effective_user.id
    bot_username = context.bot.username or (await context.bot.get_me()).username
    from src.core.user_facade import get_user_dashboard_info

    invite_link = f"https://t.me/{bot_username}?start={user_id}"
    dto = await get_user_dashboard_info(user_id, update.effective_user.first_name)
    msg, reply_markup = build_share_payload(dto, invite_link=invite_link)
    await robust_reply_text(
        message,
        msg,
        parse_mode="Markdown",
        reply_markup=reply_markup,
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
    """Handle language switching."""
    message = get_reply_message(update)
    if not message:
        return
    user = update.effective_user
    if not user:
        return

    # Determine current language
    current_lang = context.user_data.get("language_code")
    if not current_lang:
        from src.services.redis_client import redis_client

        if redis_client and redis_client.redis:
            current_lang = await redis_client.redis.get(
                f"allbot:user_lang:tg:{user.id}"
            )
            if current_lang:
                current_lang = current_lang.decode("utf-8")
    if not current_lang:
        current_lang = user.language_code[:2] if user.language_code else "zh"
        if current_lang not in ["zh", "en"]:
            current_lang = "zh"

    # Toggle language
    new_lang = "en" if current_lang == "zh" else "zh"

    # Update Context
    context.user_data["language_code"] = new_lang

    # Instantiate new Translator
    from src.i18n.translator import I18nTranslator

    context.t = I18nTranslator(new_lang)

    # Update DB and Redis
    from src.database.core import AsyncSessionLocal
    from src.database.models import User
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(
        user.id, user.username, user.full_name
    )

    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, internal_user.id)
        if db_user:
            db_user.language_code = new_lang
            await session.commit()

    from src.services.redis_client import redis_client

    if redis_client and redis_client.redis:
        await redis_client.redis.set(f"allbot:user_lang:{internal_user.id}", new_lang)
        await redis_client.redis.set(f"allbot:user_lang:tg:{user.id}", new_lang)

    # Reply with new keyboard
    from src.i18n.keyboards import get_main_menu_keyboard

    msg = build_switch_lang_message(new_lang)
    await robust_reply_text(message, msg, reply_markup=get_main_menu_keyboard(new_lang))


@prompt_route("menu.queue")
async def handle_queue_status(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = None
):
    message = get_reply_message(update)
    if not message:
        return
    status = await image_service.get_queue_info()
    if status:
        queue_size = status.get("queue_size", 0)
        queue_by_type = status.get("queue_by_type", {})
        msg = build_queue_status_message(
            queue_size,
            queue_by_type,
            context,
            TASK_TYPE_DISPLAY_NAMES,
        )
        await robust_reply_text(message, msg, parse_mode="Markdown")
    else:
        await robust_reply_text(message, "⚠️ 无法获取实时排队数据，请稍后再试。")


from src.handlers.error_handlers import with_unified_error_handler


@with_unified_error_handler
@with_db_logging_context
async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    user = update.effective_user

    await ensure_user_access_reward(context, user)

    message = update.message or update.edited_message
    if not message:
        return
    text = message.text.strip() if message.text else ""
    logger.info(f"handle_prompt received: {text.encode('utf-8')}")
    if not text:
        return

    from src.handlers.prompt_router import GLOBAL_REVERSE_MAP

    route_key = GLOBAL_REVERSE_MAP.get(text)
    if route_key and route_key in prompt_routes:
        return await prompt_routes[route_key](update, context, text)

    chat = message.chat or update.effective_chat
    if chat and chat.type == "private":
        from src.i18n.keyboards import get_main_menu_keyboard

        reply_markup = get_main_menu_keyboard(context.lang)

        await robust_reply_text(
            message,
            build_private_prompt_fallback(context.lang),
            reply_markup=reply_markup,
        )
    return
