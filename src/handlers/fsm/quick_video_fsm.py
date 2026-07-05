import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.constants import (
    DURATION_MULTIPLIER,
    DURATION_PERMISSIONS,
    DEFAULT_DURATION,
    DEFAULT_RESOLUTION,
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_CUSTOM_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
    RESOLUTION_COST,
    RESOLUTION_PERMISSIONS,
    get_video_settings_keyboard,
)
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.conversation_states import QuickVideoState
from src.handlers.fsm.quick_video_callback_data import (
    QUICK_VIDEO_ENTRY_CALLBACK_PATTERN,
    QUICK_VIDEO_MODE_KEYS,
    parse_quick_video_mode_callback_data,
    parse_quick_video_scene_callback_data,
)
from src.handlers.message_handler_menu import reply_with_lazy_bot_payload
from src.handlers.prompt_router import GLOBAL_REVERSE_MAP
from src.services.permission_service import permission_service
from src.services.qqcc_config_service import (
    VIDEO_DURATION_KEYS,
    VIDEO_RESOLUTION_KEYS,
    get_qqcc_video_scene,
    has_enabled_qqcc_video_scenes,
    is_qqcc_main_button_enabled,
    load_runtime_qqcc_config,
)
from src.services.qqcc_runtime_context import (
    load_qqcc_config_for_context as _load_qqcc_runtime_config_for_context,
)
from src.services.quick_video_submission_service import (
    QuickVideoSubmissionReject,
    build_quick_video_submission_plan,
    calculate_quick_video_cost,
    normalize_qqcc_quick_video_resolution,
    resolve_qqcc_video_scene_from_fsm_data,
    resolve_qqcc_video_scene_task_type,
    run_quick_video_submission_plan,
)
from src.services.task_service_generation_image import (
    process_standard_generation_task as process_generation_task,
)
from src.services.task_service_entrypoints_video import process_video_task_template
from src.services.wan22_video_v2_extension_service import download_output_file_to_fsm_temp
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import (
    create_background_task,
    robust_edit_text,
    robust_reply_text,
    safe_answer_query,
)
import contextlib

from src.filters.i18n_filter import I18nFilter

logger = logging.getLogger("fsm.quick_video")

QUICK_VIDEO_MODES = {
    "menu.video_edit_missionary": MODE_PERFECT_VIDEO_INSERT,
    "menu.video_edit_doggy": MODE_DOGGY_STYLE,
    "menu.video_edit_blowjob": MODE_BLOWJOB,
    "menu.video_edit_undress_tongue": MODE_UNDRESS_TONGUE,
    "menu.video_edit_closeup_blowjob": MODE_CLOSEUP_BLOWJOB,
}

QUICK_VIDEO_ROUTE_CONFIG_KEYS = {
    "menu.video_edit_missionary": "missionary",
    "menu.video_edit_doggy": "doggy",
    "menu.video_edit_blowjob": "blowjob",
    "menu.video_edit_undress_tongue": "undress_tongue",
    "menu.video_edit_closeup_blowjob": "closeup_blowjob",
}

QUICK_VIDEO_LEGACY_ROUTE_SCENE_IDS = QUICK_VIDEO_ROUTE_CONFIG_KEYS

QUICK_VIDEO_MODE_CONFIG_KEYS = {
    MODE_PERFECT_VIDEO_INSERT: "missionary",
    MODE_DOGGY_STYLE: "doggy",
    MODE_BLOWJOB: "blowjob",
    MODE_UNDRESS_TONGUE: "undress_tongue",
    MODE_CLOSEUP_BLOWJOB: "closeup_blowjob",
}

_t = translate_fsm_text


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    fsm_data = context.user_data.pop("quick_video_data", {})
    cleanup_fsm_temp_files(
        [fsm_data.get("image_path"), fsm_data.get("end_image_path")]
    )


async def _load_qqcc_config_for_context(
    context: ContextTypes.DEFAULT_TYPE,
) -> dict | None:
    return await _load_qqcc_runtime_config_for_context(
        context,
        logger=logger,
        load_config_func=load_runtime_qqcc_config,
    )


async def _reply_qqcc_feature_disabled(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    text = _t(context, "qqcc.feature_disabled")
    query = update.callback_query
    if query:
        await robust_edit_text(query.message, text, parse_mode="Markdown")
        return
    message = update.message or update.edited_message
    if message:
        await robust_reply_text(message, text, parse_mode="Markdown")


def _is_qqcc_quick_video_mode_enabled(config: dict, mode: str | None) -> bool:
    return bool(
        mode
        and is_qqcc_main_button_enabled(config, "video_edit")
        and has_enabled_qqcc_video_scenes(config)
    )


def _resolve_quick_video_file_id(message) -> str | None:
    if message.document:
        if not message.document.mime_type.startswith("image/"):
            return None
        return message.document.file_id
    if message.photo:
        return message.photo[-1].file_id
    return None


async def _resolve_quick_video_allowed_settings(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    qqcc_config: dict | None,
) -> tuple[list[str], list[str], str, str]:
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    user_group = await permission_service.get_user_group(internal_user.id)
    user_identity = await permission_service.get_user_identity(internal_user.id)

    group_res_allowed = RESOLUTION_PERMISSIONS.get(user_group, ["512p"])
    identity_res_allowed = RESOLUTION_PERMISSIONS.get(user_identity, ["512p"])
    allowed_resolutions = [
        res
        for res in VIDEO_RESOLUTION_KEYS
        if res in set(group_res_allowed + identity_res_allowed)
    ]

    group_dur_allowed = DURATION_PERMISSIONS.get(user_group, ["5s"])
    identity_dur_allowed = DURATION_PERMISSIONS.get(user_identity, ["5s"])
    allowed_durations = [
        dur
        for dur in VIDEO_DURATION_KEYS
        if dur in set(group_dur_allowed + identity_dur_allowed)
    ]

    return allowed_resolutions, allowed_durations, user_group, user_identity


def _normalize_allowed_quick_video_settings(
    *,
    resolution: str,
    duration: str,
    allowed_resolutions: list[str],
    allowed_durations: list[str],
) -> tuple[str | None, str | None]:
    if not allowed_resolutions or not allowed_durations:
        return None, None

    if resolution not in allowed_resolutions:
        resolution = allowed_resolutions[0]
    if duration not in allowed_durations:
        duration = allowed_durations[0]

    if resolution == "1024p" and duration == "10s":
        if "720p" in allowed_resolutions:
            resolution = "720p"
        elif "8s" in allowed_durations:
            duration = "8s"
        else:
            resolution = allowed_resolutions[0]
            duration = allowed_durations[0]
    return resolution, duration


def _strip_menu_prefix(text: str) -> str:
    text = (text or "").strip()
    first_token, _, rest = text.partition(" ")
    if rest and not any(char.isalnum() for char in first_token):
        return rest.strip()
    return text


def _resolve_quick_video_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> tuple[str | None, str, object | None, str | None, str | None]:
    query = update.callback_query
    if query:
        scene_id = parse_quick_video_scene_callback_data(query.data)
        if scene_id:
            return None, "", getattr(query, "message", None), None, scene_id
        route_key = parse_quick_video_mode_callback_data(query.data)
        mode = QUICK_VIDEO_MODES.get(route_key) if route_key else None
        mode_name = _strip_menu_prefix(_t(context, route_key)) if route_key else ""
        return mode, mode_name, getattr(query, "message", None), route_key, None

    message = update.message or update.edited_message
    text = message.text.strip() if message and message.text else ""
    route_key = GLOBAL_REVERSE_MAP.get(text)
    mode = QUICK_VIDEO_MODES.get(route_key) if route_key else None
    return mode, _strip_menu_prefix(text), message, route_key, None


def _resolve_qqcc_scene_from_entry(
    config: dict,
    *,
    scene_id: str | None,
    route_key: str | None,
) -> dict[str, object] | None:
    if scene_id:
        return get_qqcc_video_scene(config, scene_id)
    legacy_scene_id = QUICK_VIDEO_LEGACY_ROUTE_SCENE_IDS.get(route_key or "")
    return get_qqcc_video_scene(config, legacy_scene_id)


def _sync_qqcc_scene_to_quick_video_data(
    fsm_data: dict,
    scene: dict[str, object],
    *,
    include_scene_id: bool = False,
    include_prompt_details: bool = False,
) -> str:
    mode = resolve_qqcc_video_scene_task_type(scene)
    fsm_data.update(
        {
            "mode": mode,
            "duration": scene["duration"],
            "engine": scene.get("engine"),
            "lora_name": str(scene.get("lora_name") or ""),
            "end_frame_draw_scene_id": str(scene.get("end_frame_draw_scene_id") or ""),
        }
    )
    if include_scene_id:
        fsm_data["scene_id"] = scene["id"]
    if include_prompt_details:
        scene_prompt = str(scene.get("prompt", "")).strip()
        fsm_data.update(
            {
                "mode_name": str(scene["name"]),
                "prompt_override": scene_prompt,
                "default_prompt_key": MODE_CUSTOM_VIDEO,
                "default_prompt_text": scene_prompt,
            }
        )
    return mode


async def _build_quick_video_settings_markup(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    resolution: str,
    duration: str,
    qqcc_config: dict | None = None,
) -> InlineKeyboardMarkup:
    if qqcc_config is None:
        (
            _allowed_resolutions,
            _allowed_durations,
            user_group,
            user_identity,
        ) = await _resolve_quick_video_allowed_settings(
            context=context,
            user_id=user_id,
            qqcc_config=None,
        )
        reply_markup = get_video_settings_keyboard(
            user_group, user_identity, resolution, duration, context.lang
        )
        keyboard = list(reply_markup.inline_keyboard)
    else:
        allowed_resolutions, allowed_durations, _user_group, _user_identity = (
            await _resolve_quick_video_allowed_settings(
                context=context,
                user_id=user_id,
                qqcc_config=qqcc_config,
            )
        )
        credits_text = _t(context, "app.credits")
        keyboard = []
        res_row = []
        visible_resolutions = [
            res
            for res in allowed_resolutions
            if not (res == "1024p" and duration == "10s")
        ]
        for res in visible_resolutions:
            base_cost = RESOLUTION_COST.get(res, 6)
            multiplier = DURATION_MULTIPLIER.get(duration, 1.0)
            display_text = f"{res} ({int(base_cost * multiplier)}{credits_text})"
            text = f"✅ {display_text}" if res == resolution else display_text
            res_row.append(InlineKeyboardButton(text, callback_data=f"set_res_{res}"))
        if res_row:
            keyboard.append(res_row)

    keyboard.append(
        [
            InlineKeyboardButton(
                _t(context, "fsm.quick_video.start_button"),
                callback_data="qvid_start_generation",
            )
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def _build_quick_video_settings_text(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    resolution: str,
    duration: str,
) -> str:
    return _t(
        context,
        "fsm.quick_video.settings_text",
        resolution=resolution,
        duration=duration,
        cost=calculate_quick_video_cost(resolution, duration),
        start_button=_t(context, "fsm.quick_video.start_button"),
    )


async def start_quick_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 懒人动图 (单步图生视频)"""
    query = update.callback_query
    if query:
        await safe_answer_query(query)
    mode, mode_name, reply_message, route_key, scene_id = _resolve_quick_video_entry(
        update, context
    )

    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        msg = _t(context, "fsm.common.maintenance")
        if query:
            await robust_edit_text(query.message, msg, parse_mode="Markdown")
        elif reply_message:
            await robust_reply_text(reply_message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        msg = _t(context, "fsm.common.conflict")
        if reply_message:
            await robust_reply_text(reply_message, msg)
        return ConversationHandler.END

    qqcc_config = await _load_qqcc_config_for_context(context)
    if qqcc_config is None and (mode or route_key or scene_id):
        await reply_with_lazy_bot_payload(
            update,
            context,
            reply_text_func=robust_reply_text,
            edit_text_func=robust_edit_text,
        )
        return ConversationHandler.END

    quick_video_data = {
        "mode": mode,
        "resolution": DEFAULT_RESOLUTION,
        "duration": DEFAULT_DURATION,
        "image_path": None,
    }
    if qqcc_config is not None:
        scene = _resolve_qqcc_scene_from_entry(
            qqcc_config,
            scene_id=scene_id,
            route_key=route_key,
        )
        if (
            not is_qqcc_main_button_enabled(qqcc_config, "video_edit")
            or scene is None
        ):
            await _reply_qqcc_feature_disabled(update, context)
            return ConversationHandler.END
        mode = _sync_qqcc_scene_to_quick_video_data(
            quick_video_data,
            scene,
            include_scene_id=True,
            include_prompt_details=True,
        )
        mode_name = str(quick_video_data["mode_name"])

    if not mode or not reply_message:
        return ConversationHandler.END

    context.user_data["in_conversation"] = f"QUICK_VIDEO_{mode}"
    context.user_data["quick_video_data"] = quick_video_data

    msg = _t(context, "fsm.quick_video.start", mode_name=mode_name)
    await robust_reply_text(reply_message, msg, parse_mode="Markdown")
    return QuickVideoState.WAIT_IMAGE


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data["quick_video_data"]
    mode = fsm_data.get("mode")
    qqcc_config = await _load_qqcc_config_for_context(context)
    qqcc_scene = None
    if qqcc_config is not None:
        qqcc_scene = resolve_qqcc_video_scene_from_fsm_data(qqcc_config, fsm_data)
        if (
            not _is_qqcc_quick_video_mode_enabled(qqcc_config, mode)
            or qqcc_scene is None
        ):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        _sync_qqcc_scene_to_quick_video_data(fsm_data, qqcc_scene)

    file_id = _resolve_quick_video_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return QuickVideoState.WAIT_IMAGE

    try:
        new_file = await context.bot.get_file(file_id)
        local_path = await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="quick_video",
        )
        fsm_data["image_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return QuickVideoState.WAIT_IMAGE

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
    if qqcc_config is not None:
        allowed_resolutions, _allowed_durations, _group, _identity = (
            await _resolve_quick_video_allowed_settings(
                context=context,
                user_id=user_id,
                qqcc_config=qqcc_config,
            )
        )
        res = normalize_qqcc_quick_video_resolution(
            resolution=res,
            duration=dur,
            allowed_resolutions=allowed_resolutions,
        )
        if res is None:
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        fsm_data["resolution"] = res
    reply_markup = await _build_quick_video_settings_markup(
        context=context,
        user_id=user_id,
        resolution=res,
        duration=dur,
        qqcc_config=qqcc_config,
    )

    await robust_reply_text(
        message,
        _build_quick_video_settings_text(
            context=context,
            resolution=res,
            duration=dur,
        ),
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    return QuickVideoState.WAIT_SETTINGS


async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    fsm_data = context.user_data.get("quick_video_data", {})
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.quick_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    qqcc_config = await _load_qqcc_config_for_context(context)
    qqcc_scene = None
    if qqcc_config is not None:
        qqcc_scene = resolve_qqcc_video_scene_from_fsm_data(qqcc_config, fsm_data)
        if (
            not _is_qqcc_quick_video_mode_enabled(qqcc_config, fsm_data.get("mode"))
            or qqcc_scene is None
        ):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        _sync_qqcc_scene_to_quick_video_data(fsm_data, qqcc_scene)

    if data == "qvid_start_generation":
        await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
        return await start_generation(update, context)

    allowed_resolutions: list[str] | None = None
    allowed_durations: list[str] | None = None
    if qqcc_config is not None:
        allowed_resolutions, _allowed_durations, _group, _identity = (
            await _resolve_quick_video_allowed_settings(
                context=context,
                user_id=user_id,
                qqcc_config=qqcc_config,
            )
        )
        allowed_resolutions = [
            res
            for res in allowed_resolutions
            if not (res == "1024p" and fsm_data.get("duration") == "10s")
        ]
        if not allowed_resolutions:
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END

    if data.startswith("set_res_"):
        new_res = data.split("_")[2]
        if allowed_resolutions is not None and new_res not in allowed_resolutions:
            await query.answer(_t(context, "qqcc.feature_disabled"), show_alert=True)
            return QuickVideoState.WAIT_SETTINGS
        if new_res == "1024p" and fsm_data.get("duration") == "10s":
            fsm_data["duration"] = "8s"
            with contextlib.suppress(Exception):
                await query.answer(
                    _t(context, "fsm.quick_video.res_dur_conflict"), show_alert=True
                )
        fsm_data["resolution"] = new_res
    elif data.startswith("set_dur_"):
        if qqcc_config is not None:
            await query.answer(_t(context, "qqcc.feature_disabled"), show_alert=True)
            return QuickVideoState.WAIT_SETTINGS
        new_dur = data.split("_")[2]
        if allowed_durations is not None and new_dur not in allowed_durations:
            await query.answer(_t(context, "qqcc.feature_disabled"), show_alert=True)
            return QuickVideoState.WAIT_SETTINGS
        if new_dur == "10s" and fsm_data.get("resolution") == "1024p":
            fsm_data["resolution"] = "720p"
            with contextlib.suppress(Exception):
                await query.answer(
                    _t(context, "fsm.quick_video.dur_res_conflict"), show_alert=True
                )
        fsm_data["duration"] = new_dur

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
    if allowed_resolutions is not None:
        normalized_res = normalize_qqcc_quick_video_resolution(
            resolution=res,
            duration=dur,
            allowed_resolutions=allowed_resolutions,
        )
        if normalized_res is None:
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        res = normalized_res
        fsm_data["resolution"] = res
    elif allowed_durations is not None:
        normalized_res, normalized_dur = _normalize_allowed_quick_video_settings(
            resolution=res,
            duration=dur,
            allowed_resolutions=allowed_resolutions or [],
            allowed_durations=allowed_durations,
        )
        if normalized_res is None or normalized_dur is None:
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        res = normalized_res
        dur = normalized_dur
        fsm_data["resolution"] = res
        fsm_data["duration"] = dur

    reply_markup = await _build_quick_video_settings_markup(
        context=context,
        user_id=user_id,
        resolution=res,
        duration=dur,
        qqcc_config=qqcc_config,
    )

    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message,
            _build_quick_video_settings_text(
                context=context,
                resolution=res,
                duration=dur,
            ),
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )

    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    return QuickVideoState.WAIT_SETTINGS


async def start_generation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        from src.utils import safe_answer_query

        await safe_answer_query(query, text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    if query is None:
        return ConversationHandler.END
    user_id = query.from_user.id

    fsm_data = context.user_data.get("quick_video_data", {})
    if not fsm_data:
        return ConversationHandler.END

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        logger.warning(
            f"user={user_id} image_path missing or already consumed in quick_video"
        )
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.quick_video.already_submitted"), show_alert=True)
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    qqcc_config = await _load_qqcc_config_for_context(context)
    allowed_resolutions: list[str] | None = None
    if qqcc_config is not None:
        allowed_resolutions, _allowed_durations, _group, _identity = (
            await _resolve_quick_video_allowed_settings(
                context=context,
                user_id=user_id,
                qqcc_config=qqcc_config,
            )
        )

    plan = build_quick_video_submission_plan(
        fsm_data=fsm_data,
        qqcc_config=qqcc_config,
        allowed_resolutions=allowed_resolutions,
    )
    if isinstance(plan, QuickVideoSubmissionReject):
        if qqcc_config is not None:
            await _reply_qqcc_feature_disabled(update, context)
        cleanup_fsm_temp_files([image_path])
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    # Keep the selected settings in context so the background task can resolve them.
    # until they are refactored to take params directly
    context.user_data["custom_video_resolution"] = plan.resolution
    context.user_data["custom_video_duration"] = plan.duration
    context.user_data["mode"] = plan.mode

    if not update.effective_user:
        cleanup_fsm_temp_files([image_path])
        _cleanup_context(context, user_id)
        return ConversationHandler.END
    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id, user.username, user.full_name, cost=plan.total_cost
        )
    except Exception as e:
        from src.core.exceptions import InsufficientCreditsError

        if isinstance(e, InsufficientCreditsError):
            chat_id = update.effective_chat.id
            msg = _t(
                context,
                "fsm.common.insufficient_credits",
                current=e.current,
                cost=e.cost,
            )
            from src.utils import robust_send_message

            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            cleanup_fsm_temp_files([image_path])
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        raise e

    await robust_edit_text(
        query.message, _t(context, "fsm.quick_video.submit", cost=plan.total_cost)
    )

    create_background_task(
        context,
        run_quick_video_submission_plan(
            plan=plan,
            context=context,
            chat_id=query.message.chat_id,
            user_id=user_id,
            username=update.effective_user.username,
            image_path=image_path,
            status_msg_id=query.message.message_id,
            process_video_task_template_func=process_video_task_template,
            process_generation_task_func=process_generation_task,
            download_output_file_to_fsm_temp_func=download_output_file_to_fsm_temp,
            cleanup_temp_files_func=cleanup_fsm_temp_files,
        ),
    )

    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_cancel(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(
            context, update.effective_user.id if update.effective_user else 0
        ),
        translate_func=_t,
        prefer_edit_callback=True,
        reply_text_func=robust_reply_text,
        edit_text_func=robust_edit_text,
    )


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_timeout(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(
            context, update.effective_user.id if update.effective_user else 0
        ),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_standard_fsm_unexpected_input(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(
            context, update.effective_user.id if update.effective_user else 0
        ),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


def get_quick_video_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                I18nFilter(list(QUICK_VIDEO_MODE_KEYS)),
                start_quick_video,
            ),
            CallbackQueryHandler(
                start_quick_video,
                pattern=QUICK_VIDEO_ENTRY_CALLBACK_PATTERN,
            ),
        ],
        states={
            QuickVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            QuickVideoState.WAIT_SETTINGS: [
                CallbackQueryHandler(
                    process_settings, pattern="^set_(res|dur)_|^qvid_start_generation$"
                ),
                MessageHandler(
                    filters.ALL & ~filters.Regex(r"^/cancel$"), unexpected_input
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="quick_video_fsm",
        persistent=False,
    )
