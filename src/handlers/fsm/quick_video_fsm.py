import logging
import os

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
from src.domain_config.wan22_aio_video import get_wan22_video_v2_cost
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
from src.handlers.prompt_router import GLOBAL_REVERSE_MAP
from src.services.permission_service import permission_service
from src.services.qqcc_config_service import (
    VIDEO_DURATION_KEYS,
    VIDEO_RESOLUTION_KEYS,
    get_qqcc_video_scene,
    get_qqcc_prompt_override,
    has_enabled_qqcc_video_scenes,
    is_qqcc_main_button_enabled,
    load_runtime_qqcc_config,
    normalize_qqcc_config,
)
from src.services.task_service_entrypoints_video import process_video_task_template
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

QQCC_BOT_CLIENT_TYPE = "bot:qqcc"

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

QUICK_VIDEO_PROMPT_FALLBACKS = {
    "perfect_video_insert": "missionary sex",
    "doggy_style": "doggy style sex",
    "blowjob": "undress blowjob",
    "undress_tongue": "undress and show tongue",
    "closeup_blowjob": "closeup blowjob sex",
    MODE_CUSTOM_VIDEO: "custom video",
}


_t = translate_fsm_text


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    fsm_data = context.user_data.pop("quick_video_data", {})
    cleanup_fsm_temp_files([fsm_data.get("image_path")])


def _is_qqcc_bot_context(context: ContextTypes.DEFAULT_TYPE) -> bool:
    bot_data = getattr(context, "bot_data", None)
    if bot_data is None:
        application = getattr(context, "application", None)
        bot_data = getattr(application, "bot_data", None)
    return bool(bot_data and bot_data.get("bot_client_type") == QQCC_BOT_CLIENT_TYPE)


async def _load_qqcc_config_for_context(
    context: ContextTypes.DEFAULT_TYPE,
) -> dict | None:
    if not _is_qqcc_bot_context(context):
        return None
    try:
        return await load_runtime_qqcc_config()
    except Exception:
        logger.exception("Failed to load QQCC lazy bot config; using defaults.")
        return normalize_qqcc_config(None)


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


def _is_qqcc_quick_video_route_enabled(config: dict, route_key: str | None) -> bool:
    scene_id = QUICK_VIDEO_LEGACY_ROUTE_SCENE_IDS.get(route_key or "")
    return bool(
        scene_id
        and is_qqcc_main_button_enabled(config, "video_edit")
        and get_qqcc_video_scene(config, scene_id)
    )


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


def _calculate_quick_video_cost(resolution: str, duration: str) -> int:
    return get_wan22_video_v2_cost(resolution, duration)


def _normalize_quick_video_selection(
    *,
    resolution: str,
    duration: str,
) -> tuple[str, str]:
    if resolution == "1024p" and duration == "10s":
        return "720p", "10s"
    return resolution, duration


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


def _normalize_qqcc_quick_video_resolution(
    *,
    resolution: str,
    duration: str,
    allowed_resolutions: list[str],
) -> str | None:
    if duration == "10s":
        allowed_resolutions = [res for res in allowed_resolutions if res != "1024p"]
    if not allowed_resolutions:
        return None
    if resolution not in allowed_resolutions:
        return allowed_resolutions[0]
    return resolution


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
) -> dict[str, str] | None:
    if scene_id:
        return get_qqcc_video_scene(config, scene_id)
    legacy_scene_id = QUICK_VIDEO_LEGACY_ROUTE_SCENE_IDS.get(route_key or "")
    return get_qqcc_video_scene(config, legacy_scene_id)


def _resolve_qqcc_scene_from_fsm_data(
    config: dict,
    fsm_data: dict,
) -> dict[str, str] | None:
    scene = get_qqcc_video_scene(config, fsm_data.get("scene_id"))
    if scene is not None:
        return scene
    legacy_scene_id = QUICK_VIDEO_MODE_CONFIG_KEYS.get(fsm_data.get("mode") or "")
    return get_qqcc_video_scene(config, legacy_scene_id)


def _resolve_qqcc_scene_default_prompt_text(scene: dict[str, str]) -> str:
    return (
        scene.get("prompt")
        or QUICK_VIDEO_PROMPT_FALLBACKS.get(scene.get("prompt_key") or "")
        or QUICK_VIDEO_PROMPT_FALLBACKS[MODE_CUSTOM_VIDEO]
    )


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
        cost=_calculate_quick_video_cost(resolution, duration),
        start_button=_t(context, "fsm.quick_video.start_button"),
    )


def _resolve_quick_video_mode_submission(mode: str) -> tuple[str, str] | None:
    video_modes = {
        MODE_PERFECT_VIDEO_INSERT: ("perfect_video_insert", "missionary sex"),
        MODE_DOGGY_STYLE: ("doggy_style", "doggy style sex"),
        MODE_BLOWJOB: ("blowjob", "undress blowjob"),
        MODE_UNDRESS_TONGUE: ("undress_tongue", "undress and show tongue"),
        MODE_CLOSEUP_BLOWJOB: ("closeup_blowjob", "closeup blowjob sex"),
    }
    return video_modes.get(mode)


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
        mode = MODE_CUSTOM_VIDEO
        mode_name = scene["name"]
        scene_prompt = scene.get("prompt", "")
        prompt_key = scene.get("prompt_key") or MODE_CUSTOM_VIDEO
        quick_video_data.update(
            {
                "mode": mode,
                "scene_id": scene["id"],
                "mode_name": mode_name,
                "prompt_override": scene_prompt or None,
                "default_prompt_key": prompt_key,
                "default_prompt_text": _resolve_qqcc_scene_default_prompt_text(scene),
                "duration": scene["duration"],
            }
        )

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
        qqcc_scene = _resolve_qqcc_scene_from_fsm_data(qqcc_config, fsm_data)
        if (
            not _is_qqcc_quick_video_mode_enabled(qqcc_config, mode)
            or qqcc_scene is None
        ):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        fsm_data["duration"] = qqcc_scene["duration"]

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
        res = _normalize_qqcc_quick_video_resolution(
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
        qqcc_scene = _resolve_qqcc_scene_from_fsm_data(qqcc_config, fsm_data)
        if (
            not _is_qqcc_quick_video_mode_enabled(qqcc_config, fsm_data.get("mode"))
            or qqcc_scene is None
        ):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        fsm_data["duration"] = qqcc_scene["duration"]

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
        normalized_res = _normalize_qqcc_quick_video_resolution(
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
    user_id = query.from_user.id

    fsm_data = context.user_data.get("quick_video_data", {})
    if not fsm_data:
        return ConversationHandler.END

    qqcc_config = await _load_qqcc_config_for_context(context)
    qqcc_scene = None
    if qqcc_config is not None:
        qqcc_scene = _resolve_qqcc_scene_from_fsm_data(qqcc_config, fsm_data)
        if (
            not _is_qqcc_quick_video_mode_enabled(qqcc_config, fsm_data.get("mode"))
            or qqcc_scene is None
        ):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        fsm_data["duration"] = qqcc_scene["duration"]
        fsm_data["mode_name"] = qqcc_scene["name"]
        scene_prompt = qqcc_scene.get("prompt", "")
        fsm_data["prompt_override"] = scene_prompt or None
        fsm_data["default_prompt_key"] = qqcc_scene.get("prompt_key") or MODE_CUSTOM_VIDEO
        fsm_data["default_prompt_text"] = _resolve_qqcc_scene_default_prompt_text(
            qqcc_scene
        )

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        logger.warning(
            f"user={user_id} image_path missing or already consumed in quick_video"
        )
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.quick_video.already_submitted"), show_alert=True)
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    res, dur = _normalize_quick_video_selection(
        resolution=fsm_data["resolution"],
        duration=fsm_data["duration"],
    )
    if qqcc_config is not None:
        allowed_resolutions, _allowed_durations, _group, _identity = (
            await _resolve_quick_video_allowed_settings(
                context=context,
                user_id=user_id,
                qqcc_config=qqcc_config,
            )
        )
        res = _normalize_qqcc_quick_video_resolution(
            resolution=res,
            duration=dur,
            allowed_resolutions=allowed_resolutions,
        )
        if res is None:
            await _reply_qqcc_feature_disabled(update, context)
            if image_path and os.path.exists(image_path):
                with contextlib.suppress(OSError):
                    os.remove(image_path)
            _cleanup_context(context, user_id)
            return ConversationHandler.END

    mode = fsm_data["mode"]
    fsm_data["resolution"] = res
    fsm_data["duration"] = dur
    cost = _calculate_quick_video_cost(res, dur)

    # Keep the selected settings in context so the background task can resolve them.
    # until they are refactored to take params directly
    context.user_data["custom_video_resolution"] = res
    context.user_data["custom_video_duration"] = dur
    context.user_data["mode"] = mode

    if not update.effective_user:
        return ConversationHandler.END
    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id, user.username, user.full_name, cost=cost
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
            if image_path and os.path.exists(image_path):
                with contextlib.suppress(OSError):
                    os.remove(image_path)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        raise e

    await robust_edit_text(
        query.message, _t(context, "fsm.quick_video.submit", cost=cost)
    )

    mode_submission = _resolve_quick_video_mode_submission(mode)
    if qqcc_config is not None:
        default_prompt_key = fsm_data.get("default_prompt_key") or MODE_CUSTOM_VIDEO
        default_prompt_text = fsm_data.get("default_prompt_text") or "custom video"
        prompt_override = fsm_data.get("prompt_override")
        create_background_task(
            context,
            process_video_task_template(
                context=context,
                mode=MODE_CUSTOM_VIDEO,
                default_prompt_key=default_prompt_key,
                default_prompt_text=default_prompt_text,
                prompt_override=prompt_override,
                display_mode_name_override=fsm_data.get("mode_name"),
                image_path=image_path,
                cleanup=True,
                allow_contribute=True,
                chat_id=query.message.chat_id,
                user_id=user_id,
                username=update.effective_user.username,
                status_msg_id=query.message.message_id,
            ),
        )
    elif mode_submission:
        default_prompt_key, default_prompt_text = mode_submission
        prompt_override = (
            get_qqcc_prompt_override(qqcc_config, default_prompt_key)
            if qqcc_config is not None
            else None
        )
        create_background_task(
            context,
            process_video_task_template(
                context=context,
                mode=mode,
                default_prompt_key=default_prompt_key,
                default_prompt_text=default_prompt_text,
                prompt_override=prompt_override,
                image_path=image_path,
                cleanup=True,
                allow_contribute=True,
                chat_id=query.message.chat_id,
                user_id=user_id,
                username=update.effective_user.username,
                status_msg_id=query.message.message_id,
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
