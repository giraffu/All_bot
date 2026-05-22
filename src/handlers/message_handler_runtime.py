from src.handlers.message_handler_menu import (
    build_queue_status_message,
    build_switch_lang_message,
)
from src.handlers.message_handler_profile import (
    build_checkin_repeat_message,
    build_checkin_success_message,
    build_personal_center_payload,
    build_refuge_checkin_payload,
    build_share_payload,
)
from src.services.permission_service import permission_service
from src.services.image_service import image_service
from src.utils import (
    create_background_task,
    get_user_channel_status,
    notify_inviter_reward,
)


def normalize_supported_language_code(language_code: str | None) -> str:
    if not language_code:
        return "zh"
    normalized = language_code[:2]
    return normalized if normalized in {"zh", "en"} else "zh"


async def toggle_user_language(context, user) -> tuple[str, object]:
    current_lang = context.user_data.get("language_code")
    redis_client = None

    if not current_lang:
        from src.services.redis_client import redis_client as _redis_client

        redis_client = _redis_client
        if redis_client and redis_client.redis:
            current_lang = await redis_client.redis.get(f"allbot:user_lang:tg:{user.id}")
            if current_lang:
                current_lang = current_lang.decode("utf-8")

    current_lang = normalize_supported_language_code(
        current_lang or getattr(user, "language_code", None)
    )
    new_lang = "en" if current_lang == "zh" else "zh"

    context.user_data["language_code"] = new_lang

    from src.i18n.translator import I18nTranslator

    context.t = I18nTranslator(new_lang)

    from src.core.user_core import get_or_create_user_by_telegram
    from src.database.core import AsyncSessionLocal
    from src.database.models import User

    internal_user, _ = await get_or_create_user_by_telegram(
        user.id, user.username, user.full_name
    )

    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, internal_user.id)
        if db_user:
            db_user.language_code = new_lang
            await session.commit()

    if redis_client is None:
        from src.services.redis_client import redis_client as _redis_client

        redis_client = _redis_client

    if redis_client and redis_client.redis:
        await redis_client.redis.set(f"allbot:user_lang:{internal_user.id}", new_lang)
        await redis_client.redis.set(f"allbot:user_lang:tg:{user.id}", new_lang)

    from src.i18n.keyboards import get_main_menu_keyboard

    return build_switch_lang_message(new_lang), get_main_menu_keyboard(new_lang)


async def get_queue_status_reply(
    context,
    task_type_display_names: dict[str, str],
    *,
    unavailable_message: str = "⚠️ 无法获取实时排队数据，请稍后再试。",
) -> str:
    status = await image_service.get_queue_info()
    if not status:
        return unavailable_message

    return build_queue_status_message(
        status.get("queue_size", 0),
        status.get("queue_by_type", {}),
        context,
        task_type_display_names,
    )


def normalize_telegram_group_id(group_id: str | int | None) -> str | int | None:
    if group_id is None:
        return None
    if isinstance(group_id, str) and group_id.lstrip("-").isdigit():
        return int(group_id)
    return group_id


async def get_checkin_gate_reply(update, context, refuge_group_id) -> tuple[str, object] | None:
    if not refuge_group_id or not update.effective_user:
        return None

    try:
        member = await context.bot.get_chat_member(
            chat_id=normalize_telegram_group_id(refuge_group_id),
            user_id=update.effective_user.id,
        )
        if member.status in ["left", "kicked", "banned"]:
            return build_refuge_checkin_payload()
    except Exception as exc:
        return ("__warning__", exc)
    return None


async def build_checkin_reply(update, context) -> str:
    user = update.effective_user
    if not user:
        return ""

    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user.id)
    internal_user_id = internal_user.id

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
        return build_checkin_success_message(
            user_group=user_group,
            user_identity=user_identity,
            total_days=total_days,
            reward=reward,
            current_credits=current_credits,
        )
    if error_msg:
        return error_msg
    return build_checkin_repeat_message(
        user_group=user_group,
        user_identity=user_identity,
        total_days=total_days,
    )


async def build_personal_center_reply(
    context,
    user,
    *,
    invite_link: str,
    web_url: str,
) -> tuple[str, object]:
    is_member = await get_user_channel_status(context.bot, user.id)
    if is_member is not None:
        await permission_service.sync_channel_status(
            user.id, user.username, user.full_name, is_member
        )

    await permission_service.ensure_user(
        user.id, user.username, user.full_name, user.language_code
    )

    from src.core.user_facade import get_user_dashboard_info

    dto = await get_user_dashboard_info(user.id, user.first_name)
    return build_personal_center_payload(
        dto,
        invite_link=invite_link,
        web_url=web_url,
    )


async def build_share_reply(context, user) -> tuple[str, object]:
    bot_username = context.bot.username
    if not bot_username:
        bot_username = (await context.bot.get_me()).username

    from src.core.user_facade import get_user_dashboard_info

    invite_link = f"https://t.me/{bot_username}?start={user.id}"
    dto = await get_user_dashboard_info(user.id, user.first_name)
    return build_share_payload(dto, invite_link=invite_link)
