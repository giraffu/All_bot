from src.constants import MODE_IMAGE_TO_VIDEO
from src.handlers.message_handler_menu import (
    build_switch_lang_message,
    build_queue_status_message,
    build_user_queue_tasks_section,
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
from src.services.language_runtime_service import (
    normalize_supported_language_code as _normalize_supported_language_code,
    toggle_user_language_runtime,
)
from src.utils import (
    create_background_task,
    get_user_channel_status,
    notify_inviter_reward,
)
normalize_supported_language_code = _normalize_supported_language_code


def _normalize_queue_task_type_for_display(task_type: str | None) -> str:
    if task_type in {"video_edit", "custom_video", MODE_IMAGE_TO_VIDEO, "image_to_video"}:
        return "img2video_group"
    return str(task_type or "")


def _normalize_queue_type_counts_for_display(queue_by_type: dict | None) -> dict[str, int]:
    raw_counts = queue_by_type or {}
    normalized_counts: dict[str, int] = {}

    for task_type, count in raw_counts.items():
        normalized_task_type = _normalize_queue_task_type_for_display(task_type)
        normalized_counts[normalized_task_type] = (
            normalized_counts.get(normalized_task_type, 0) + int(count)
        )

    return normalized_counts


def _format_queue_rank(raw_queue_pos) -> int | str | None:
    if raw_queue_pos is None:
        return None
    try:
        return int(raw_queue_pos) + 1
    except (TypeError, ValueError):
        return raw_queue_pos


def _build_user_task_status_text(status_data: dict | None, context) -> str:
    if not status_data:
        return context.t("profile.my_tasks_status_submitting")

    state = str(status_data.get("status") or "").lower()
    if state == "pending":
        queue_pos = _format_queue_rank(status_data.get("queue_pos"))
        if queue_pos is not None:
            return context.t("profile.my_tasks_status_pending_position", queue_pos=queue_pos)
        return context.t("profile.my_tasks_status_pending")
    if state == "running":
        return context.t("profile.my_tasks_status_running")
    if state == "done":
        return context.t("profile.my_tasks_status_done")
    if state == "error":
        return context.t("profile.my_tasks_status_error")
    if state == "cancelled":
        return context.t("profile.my_tasks_status_cancelled")
    return context.t("profile.my_tasks_status_unknown")


async def _build_user_queue_tasks_for_display(user, context) -> list[dict]:
    from src.core.task_core import get_system_task_stats
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user.id)
    active_tasks, _ = await get_system_task_stats()
    if not active_tasks:
        return []

    user_tasks = [
        {"registry_task_id": task_id, **task}
        for task_id, task in active_tasks.items()
        if task.get("user_id") == internal_user.id
    ]
    if not user_tasks:
        return []

    user_tasks.sort(
        key=lambda task: (
            float(task.get("created_at") or 0),
            str(task.get("registry_task_id") or ""),
        )
    )

    display_tasks: list[dict] = []
    for task in user_tasks[:3]:
        backend_task_id = task.get("backend_task_id")
        status_data = (
            await image_service.get_task_status(backend_task_id) if backend_task_id else None
        )
        display_tasks.append(
            {
                "task_type": _normalize_queue_task_type_for_display(
                    task.get("task_type") or task.get("type")
                ),
                "status_text": _build_user_task_status_text(status_data, context),
            }
        )
    return display_tasks


async def toggle_user_language(context, user) -> tuple[str, object]:
    result = await toggle_user_language_runtime(
        telegram_user=user,
        cached_language_code=context.user_data.get("language_code"),
    )
    context.user_data["language_code"] = result.new_lang
    context.lang = result.new_lang
    context.t = result.translator
    return build_switch_lang_message(result.new_lang), result.reply_markup


async def get_queue_status_reply(
    context,
    task_type_display_names: dict[str, str],
    *,
    user,
    unavailable_message: str | None = None,
) -> str:
    unavailable_message = unavailable_message or context.t("system.queue_unavailable")
    status = await image_service.get_queue_info()
    if not status:
        return unavailable_message

    base_message = build_queue_status_message(
        status.get("queue_size", 0),
        _normalize_queue_type_counts_for_display(status.get("queue_by_type", {})),
        context,
        task_type_display_names,
    )
    user_tasks_section = build_user_queue_tasks_section(
        await _build_user_queue_tasks_for_display(user, context),
        context,
        task_type_display_names,
    )
    return f"{base_message}{user_tasks_section}"


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
            return build_refuge_checkin_payload(context.lang)
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
            lang=context.lang,
        )
    if error_msg:
        return error_msg
    return build_checkin_repeat_message(
        user_group=user_group,
        user_identity=user_identity,
        total_days=total_days,
        lang=context.lang,
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
        lang=context.lang,
    )


async def build_share_reply(context, user) -> tuple[str, object]:
    bot_username = context.bot.username
    if not bot_username:
        bot_username = (await context.bot.get_me()).username

    from src.core.user_facade import get_user_dashboard_info

    invite_link = f"https://t.me/{bot_username}?start={user.id}"
    dto = await get_user_dashboard_info(user.id, user.first_name)
    return build_share_payload(dto, invite_link=invite_link, lang=context.lang)
