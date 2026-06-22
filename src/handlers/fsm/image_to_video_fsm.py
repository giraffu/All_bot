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

from src.constants import MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.conversation_states import ImageToVideoState
from src.handlers.prompt_router import is_global_menu_command
from src.lora_catalog import VIDEO_LORA_MODELS, get_video_lora_display_name
from src.services.task_service_generation_video import process_image_to_video_generation_task as process_image_to_video_task
from src.domain_config.wan22_aio_video import (
    WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS,
    WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
    WAN22_VIDEO_V2_DURATION_SECONDS,
    WAN22_VIDEO_V2_RESOLUTION_PRESETS,
    get_wan22_video_v2_cost,
    get_wan22_video_v2_duration_label,
    get_wan22_video_v2_duration_multiplier_label,
    get_wan22_video_v2_resolution_display,
    get_wan22_video_v2_resolution_label,
    normalize_wan22_video_v2_duration_seconds,
    normalize_wan22_video_v2_resolution_preset,
)
from src.services.permission_service import permission_service
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import create_background_task, robust_edit_text, robust_reply_text
import contextlib

from src.filters.i18n_filter import I18nFilter

logger = logging.getLogger("fsm.image_to_video")

IMAGE_TO_VIDEO_DATA_KEY = "image_to_video_data"
IMAGE_TO_VIDEO_CONVERSATION_TAG = "IMAGE_TO_VIDEO"
I2V_LORA_BUTTONS_PER_ROW = 4
I2V_SETUP_LORA_PREFIX = "i2v_setup_lora_"
I2V_SETUP_MODE_SINGLE = "i2v_setup_mode_single"
I2V_SETUP_MODE_END = "i2v_setup_mode_end"
I2V_SETUP_RES_PREFIX = "i2v_setup_res_"
I2V_SETUP_DUR_PREFIX = "i2v_setup_dur_"
I2V_SETUP_CONFIRM = "i2v_setup_confirm"
I2V_DURATION_ACTION_VALUES = "|".join(
    str(duration) for duration in WAN22_VIDEO_V2_DURATION_SECONDS
)
I2V_SETUP_ACTION_PATTERN = (
    r"^i2v_setup_(lora_.*|mode_(single|end)|res_("
    + "|".join(WAN22_VIDEO_V2_RESOLUTION_PRESETS.keys())
    + rf")|dur_({I2V_DURATION_ACTION_VALUES})|confirm)$"
)


_t = translate_fsm_text


def _get_image_to_video_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    """Return unified image-to-video FSM state."""
    return context.user_data.get(IMAGE_TO_VIDEO_DATA_KEY)


def _set_image_to_video_data(
    context: ContextTypes.DEFAULT_TYPE, data: dict[str, object]
) -> None:
    context.user_data[IMAGE_TO_VIDEO_DATA_KEY] = data


def _pop_image_to_video_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Pop unified image-to-video FSM state."""
    return context.user_data.pop(IMAGE_TO_VIDEO_DATA_KEY, {}) or {}


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    pending_files = _pop_image_to_video_data(context)
    cleanup_fsm_temp_files(
        [pending_files.get("image_path"), pending_files.get("end_image_path")]
    )


def _get_lora_display_name(lora_name: str | None, *, lang: str = "zh") -> str:
    normalized_name = lora_name or ""
    return get_video_lora_display_name(normalized_name, lang)


def _selected_button_label(label: str, *, selected: bool) -> str:
    return f"✅ {label}" if selected else label


def _chunk_buttons(
    buttons: list[InlineKeyboardButton], size: int
) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + size] for i in range(0, len(buttons), size)]


def _get_frame_mode_label(
    context: ContextTypes.DEFAULT_TYPE, use_end_frame: bool
) -> str:
    key = (
        "fsm.image_to_video.frame_mode_end"
        if use_end_frame
        else "fsm.image_to_video.frame_mode_single"
    )
    return _t(context, key)


def _normalize_selected_duration(fsm_data: dict[str, object]) -> int:
    selected_duration = normalize_wan22_video_v2_duration_seconds(
        fsm_data.get("duration") or WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS
    )
    fsm_data["duration"] = selected_duration
    return selected_duration


def _build_lora_selection_keyboard(lang: str = "zh") -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            get_video_lora_display_name(backend_name, lang),
            callback_data=f"lora_select_{backend_name}",
        )
        for backend_name in VIDEO_LORA_MODELS.keys()
    ]
    keyboard = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(keyboard)


def _build_initial_setup_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    fsm_data: dict[str, object],
) -> InlineKeyboardMarkup:
    lang = getattr(context, "lang", "zh")
    selected_lora = str(fsm_data.get("lora_name") or "")
    allow_lora_selection = bool(fsm_data.get("allow_lora_selection", True))
    selected_resolution = normalize_wan22_video_v2_resolution_preset(
        str(fsm_data.get("resolution") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET)
    )
    fsm_data["resolution"] = selected_resolution
    selected_duration = _normalize_selected_duration(fsm_data)
    use_end_frame = bool(fsm_data.get("use_end_frame"))
    credits_text = _t(context, "app.credits")

    lora_options = (
        VIDEO_LORA_MODELS.keys()
        if allow_lora_selection
        else ("",)
    )
    lora_buttons = [
        InlineKeyboardButton(
            _selected_button_label(
                get_video_lora_display_name(backend_name, lang),
                selected=backend_name == selected_lora,
            ),
            callback_data=f"{I2V_SETUP_LORA_PREFIX}{backend_name}",
        )
        for backend_name in lora_options
    ]
    mode_row = [
        InlineKeyboardButton(
            _selected_button_label(
                _t(context, "fsm.image_to_video.disable_end_frame"),
                selected=not use_end_frame,
            ),
            callback_data=I2V_SETUP_MODE_SINGLE,
        ),
        InlineKeyboardButton(
            _selected_button_label(
                _t(context, "fsm.image_to_video.enable_end_frame"),
                selected=use_end_frame,
            ),
            callback_data=I2V_SETUP_MODE_END,
        ),
    ]
    resolution_row = []
    for preset_key in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        label = get_wan22_video_v2_resolution_label(preset_key, lang=lang)
        cost_for_preset = get_wan22_video_v2_cost(preset_key, selected_duration)
        resolution_row.append(
            InlineKeyboardButton(
                _selected_button_label(
                    f"{label} ({cost_for_preset}{credits_text})",
                    selected=preset_key == selected_resolution,
                ),
                callback_data=f"{I2V_SETUP_RES_PREFIX}{preset_key}",
            )
        )
    duration_row = []
    for duration_seconds in WAN22_VIDEO_V2_DURATION_SECONDS:
        label = get_wan22_video_v2_duration_label(duration_seconds, lang=lang)
        multiplier_label = get_wan22_video_v2_duration_multiplier_label(
            duration_seconds
        )
        duration_row.append(
            InlineKeyboardButton(
                _selected_button_label(
                    f"{label} ({multiplier_label})",
                    selected=duration_seconds == selected_duration,
                ),
                callback_data=f"{I2V_SETUP_DUR_PREFIX}{duration_seconds}",
            )
        )

    return InlineKeyboardMarkup(
        [
            *_chunk_buttons(lora_buttons, I2V_LORA_BUTTONS_PER_ROW),
            mode_row,
            resolution_row,
            duration_row,
        ]
    )


def _build_end_frame_choice_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _t(context, "fsm.image_to_video.enable_end_frame"),
                    callback_data="i2v_end_frame_yes",
                ),
                InlineKeyboardButton(
                    _t(context, "fsm.image_to_video.disable_end_frame"),
                    callback_data="i2v_end_frame_no",
                ),
            ]
        ]
    )


def _build_image_request_text(
    lora_name: str | None,
    *,
    from_compat_alias: bool,
    lang: str = "zh",
    use_end_frame: bool = False,
    resolution: str | None = None,
    duration: object | None = None,
) -> str:
    lora_display_name = get_video_lora_display_name(lora_name or "", lang)
    from src.i18n.translator import get_text

    header = get_text("fsm.image_to_video.mode_header", lang)
    if from_compat_alias:
        header = get_text("fsm.image_to_video.compat_mode_header", lang)
    frame_mode = get_text(
        (
            "fsm.image_to_video.frame_mode_end"
            if use_end_frame
            else "fsm.image_to_video.frame_mode_single"
        ),
        lang,
    )
    image_count = 2 if use_end_frame else 1
    settings_lines = [
        get_text(
            "fsm.image_to_video.current_lora",
            lang,
            model_name=lora_display_name,
        ),
        get_text(
            "fsm.image_to_video.current_frame_mode",
            lang,
            frame_mode=frame_mode,
            image_count=image_count,
        ),
    ]
    if resolution:
        settings_lines.append(
            get_text(
                "fsm.image_to_video.current_resolution",
                lang,
                resolution=get_wan22_video_v2_resolution_display(
                    resolution, lang=lang
                ),
            )
        )
    settings_lines.append(
        get_text(
            "fsm.image_to_video.current_duration",
            lang,
            duration=get_wan22_video_v2_duration_label(duration, lang=lang),
        )
    )
    image_note_key = (
        "fsm.image_to_video.image_note_end_frame"
        if use_end_frame
        else "fsm.image_to_video.image_note"
    )
    image_note_text = get_text(image_note_key, lang)

    return (
        f"{header}\n\n"
        f"{chr(10).join(settings_lines)}\n\n"
        f"{get_text('fsm.image_to_video.send_image', lang)}\n"
        f"{image_note_text}\n\n"
        "随时可以发送 /cancel 退出流程。"
    )


def _build_initial_setup_message(
    context: ContextTypes.DEFAULT_TYPE,
    fsm_data: dict[str, object],
    *,
    from_compat_alias: bool,
) -> str:
    lang = getattr(context, "lang", "zh")
    header_key = (
        "fsm.image_to_video.compat_mode_header"
        if from_compat_alias
        else "fsm.image_to_video.mode_header"
    )
    resolution = normalize_wan22_video_v2_resolution_preset(
        str(fsm_data.get("resolution") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET)
    )
    fsm_data["resolution"] = resolution
    duration = _normalize_selected_duration(fsm_data)
    use_end_frame = bool(fsm_data.get("use_end_frame"))
    cost = _compute_video_generation_cost(resolution, duration)
    return _t(
        context,
        "fsm.image_to_video.setup_text",
        header=_t(context, header_key),
        model_name=_get_lora_display_name(fsm_data.get("lora_name"), lang=lang),
        frame_mode=_get_frame_mode_label(context, use_end_frame),
        image_count=2 if use_end_frame else 1,
        resolution=get_wan22_video_v2_resolution_display(resolution, lang=lang),
        duration=get_wan22_video_v2_duration_label(duration, lang=lang),
        cost=cost,
    )


def _build_settings_message(
    fsm_data: dict[str, object], cost: int, *, lang: str = "zh"
) -> str:
    resolution = get_wan22_video_v2_resolution_display(
        str(fsm_data["resolution"]),
        lang=lang,
    )
    duration = get_wan22_video_v2_duration_label(
        _normalize_selected_duration(fsm_data),
        lang=lang,
    )
    lora_display_name = _get_lora_display_name(fsm_data.get("lora_name"), lang=lang)

    from src.i18n.translator import get_text

    return get_text(
        "fsm.image_to_video.settings_text",
        lang,
        resolution=resolution,
        duration=duration,
        cost=cost,
        model_name=lora_display_name,
    )


def _build_submit_message(lora_name: str | None, cost: int, *, lang: str = "zh") -> str:
    from src.i18n.translator import get_text

    key = "fsm.image_to_video.submit_plain" if not lora_name else "fsm.image_to_video.submit_lora"
    return get_text(key, lang, cost=cost)


def _build_prompt_request_text(
    context: ContextTypes.DEFAULT_TYPE,
    fsm_data: dict[str, object],
    *,
    received_key: str,
) -> str:
    lang = getattr(context, "lang", "zh")
    resolution = normalize_wan22_video_v2_resolution_preset(
        str(fsm_data.get("resolution") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET)
    )
    fsm_data["resolution"] = resolution
    duration = _normalize_selected_duration(fsm_data)
    cost = _compute_video_generation_cost(resolution, duration)
    prompt_text = _t(
        context,
        "fsm.image_to_video.prompt_request_text",
        resolution=get_wan22_video_v2_resolution_display(resolution, lang=lang),
        frame_mode=_get_frame_mode_label(
            context, bool(fsm_data.get("use_end_frame"))
        ),
        duration=get_wan22_video_v2_duration_label(duration, lang=lang),
        cost=cost,
        model_name=_get_lora_display_name(fsm_data.get("lora_name"), lang=lang),
    )
    return f"{_t(context, received_key)}\n\n{prompt_text}"


def _compute_video_generation_cost(resolution: str, duration: object) -> int:
    return get_wan22_video_v2_cost(resolution, duration)


def _resolve_image_to_video_task_type(context: ContextTypes.DEFAULT_TYPE) -> str:
    return (
        MODE_CUSTOM_VIDEO
        if context.user_data.get("in_conversation") == "CUSTOM_VIDEO"
        else MODE_IMAGE_TO_VIDEO
    )


async def _load_video_generation_access_profile(
    *,
    user_id: int,
) -> tuple[int, str, str]:
    from src.core.user_core import get_or_create_user_by_telegram

    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    internal_user_id = internal_user.id
    user_group = await permission_service.get_user_group(internal_user_id)
    user_identity = await permission_service.get_user_identity(internal_user_id)
    return internal_user_id, user_group, user_identity


async def _build_video_settings_view_model(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    fsm_data: dict[str, object],
) -> tuple[InlineKeyboardMarkup, int, str]:
    lang = getattr(context, "lang", "zh")
    resolution = normalize_wan22_video_v2_resolution_preset(
        str(fsm_data["resolution"])
    )
    fsm_data["resolution"] = resolution
    duration = _normalize_selected_duration(fsm_data)
    from src.i18n.translator import get_text

    credits_text = get_text("app.credits", lang)
    row = []
    for preset_key in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        label = get_wan22_video_v2_resolution_label(preset_key, lang=lang)
        cost_for_preset = get_wan22_video_v2_cost(preset_key, duration)
        text = f"{label} ({cost_for_preset}{credits_text})"
        if preset_key == resolution:
            text = f"✅ {text}"
        row.append(
            InlineKeyboardButton(text, callback_data=f"set_res_{preset_key}")
        )
    duration_row = []
    for duration_seconds in WAN22_VIDEO_V2_DURATION_SECONDS:
        label = get_wan22_video_v2_duration_label(duration_seconds, lang=lang)
        multiplier_label = get_wan22_video_v2_duration_multiplier_label(
            duration_seconds
        )
        text = f"{label} ({multiplier_label})"
        if duration_seconds == duration:
            text = f"✅ {text}"
        duration_row.append(
            InlineKeyboardButton(text, callback_data=f"set_dur_{duration_seconds}")
        )
    reply_markup = InlineKeyboardMarkup([row, duration_row])
    cost = _compute_video_generation_cost(resolution, duration)
    msg_text = _build_settings_message(
        fsm_data, cost, lang=getattr(context, "lang", "zh")
    )
    return reply_markup, cost, msg_text


async def _send_start_message(
    update: Update,
    message_text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    query = update.callback_query
    if query:
        await robust_edit_text(
            query.message,
            message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return

    if update.message:
        await robust_reply_text(
            update.message,
            message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )


def _initialize_image_to_video_context(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    conversation_tag: str,
    preset_lora_name: str | None = None,
    allow_lora_selection: bool = True,
) -> None:
    context.user_data["in_conversation"] = conversation_tag
    data = {
        "resolution": WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
        "duration": WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS,
        "image_path": None,
        "end_image_path": None,
        "use_end_frame": False,
        "lora_name": preset_lora_name,
        "allow_lora_selection": allow_lora_selection,
    }
    _set_image_to_video_data(context, data)


async def _start_image_to_video_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    conversation_tag: str = IMAGE_TO_VIDEO_CONVERSATION_TAG,
    preset_lora_name: str | None = None,
    allow_lora_selection: bool = True,
    skip_lora_selection: bool = False,
) -> int:
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        msg = _t(context, "fsm.common.maintenance")
        if update.callback_query:
            await robust_edit_text(
                update.callback_query.message, msg, parse_mode="Markdown"
            )
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        msg = _t(context, "fsm.common.conflict")
        if update.message:
            await robust_reply_text(update.message, msg)
        elif update.callback_query:
            await robust_edit_text(update.callback_query.message, msg)
        return ConversationHandler.END

    _initialize_image_to_video_context(
        context,
        conversation_tag=conversation_tag,
        preset_lora_name=preset_lora_name,
        allow_lora_selection=allow_lora_selection,
    )

    if skip_lora_selection:
        fsm_data = _get_image_to_video_data(context) or {}
        await _send_start_message(
            update,
            _build_image_request_text(
                preset_lora_name,
                from_compat_alias=conversation_tag == "CUSTOM_VIDEO",
                lang=getattr(context, "lang", "zh"),
                use_end_frame=bool(fsm_data.get("use_end_frame")),
                resolution=str(fsm_data.get("resolution") or ""),
                duration=fsm_data.get("duration"),
            ),
        )
        return ImageToVideoState.WAIT_IMAGE

    fsm_data = _get_image_to_video_data(context) or {}
    from_compat_alias = conversation_tag == "CUSTOM_VIDEO"
    await _send_start_message(
        update,
        _build_initial_setup_message(
            context,
            fsm_data,
            from_compat_alias=from_compat_alias,
        ),
        reply_markup=_build_initial_setup_keyboard(context, fsm_data),
    )
    return ImageToVideoState.WAIT_LORA_SELECTION


async def start_image_to_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Preferred entry point for the unified image-to-video flow."""
    return await _start_image_to_video_flow(
        update,
        context,
        conversation_tag=IMAGE_TO_VIDEO_CONVERSATION_TAG,
    )


async def start_custom_video(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Legacy /custom_video entry point backed by the unified image-to-video flow."""
    return await _start_image_to_video_flow(
        update,
        context,
        conversation_tag="CUSTOM_VIDEO",
        preset_lora_name="",
        allow_lora_selection=False,
    )


async def handle_initial_setup_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    callback_data = query.data or ""

    fsm_data = _get_image_to_video_data(context) or {}
    if not fsm_data:
        await query.edit_message_text(_t(context, "fsm.image_to_video.expired_alert"))
        return ConversationHandler.END

    if callback_data.startswith(I2V_SETUP_LORA_PREFIX):
        fsm_data["lora_name"] = (
            callback_data.removeprefix(I2V_SETUP_LORA_PREFIX)
            if fsm_data.get("allow_lora_selection", True)
            else ""
        )
    elif callback_data == I2V_SETUP_MODE_SINGLE:
        fsm_data["use_end_frame"] = False
        fsm_data["end_image_path"] = None
    elif callback_data == I2V_SETUP_MODE_END:
        fsm_data["use_end_frame"] = True
        fsm_data["end_image_path"] = None
    elif callback_data.startswith(I2V_SETUP_RES_PREFIX):
        fsm_data["resolution"] = normalize_wan22_video_v2_resolution_preset(
            callback_data.removeprefix(I2V_SETUP_RES_PREFIX)
        )
    elif callback_data.startswith(I2V_SETUP_DUR_PREFIX):
        fsm_data["duration"] = normalize_wan22_video_v2_duration_seconds(
            callback_data.removeprefix(I2V_SETUP_DUR_PREFIX)
        )
    elif callback_data == I2V_SETUP_CONFIRM:
        await robust_edit_text(
            query.message,
            _build_image_request_text(
                fsm_data.get("lora_name"),
                from_compat_alias=context.user_data.get("in_conversation")
                == "CUSTOM_VIDEO",
                lang=getattr(context, "lang", "zh"),
                use_end_frame=bool(fsm_data.get("use_end_frame")),
                resolution=str(fsm_data.get("resolution") or ""),
                duration=fsm_data.get("duration"),
            ),
            parse_mode="Markdown",
        )
        return ImageToVideoState.WAIT_IMAGE
    else:
        return ImageToVideoState.WAIT_LORA_SELECTION

    await robust_edit_text(
        query.message,
        _build_initial_setup_message(
            context,
            fsm_data,
            from_compat_alias=context.user_data.get("in_conversation")
            == "CUSTOM_VIDEO",
        ),
        reply_markup=_build_initial_setup_keyboard(context, fsm_data),
        parse_mode="Markdown",
    )
    return ImageToVideoState.WAIT_LORA_SELECTION


async def handle_lora_selection(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = query.data

    if not data.startswith("lora_select_"):
        return ImageToVideoState.WAIT_LORA_SELECTION

    lora_name = data.replace("lora_select_", "")
    fsm_data = _get_image_to_video_data(context) or {}
    if not fsm_data:
        await query.edit_message_text(_t(context, "fsm.image_to_video.expired_alert"))
        return ConversationHandler.END

    fsm_data["lora_name"] = (
        lora_name if fsm_data.get("allow_lora_selection", True) else ""
    )

    await robust_edit_text(
        query.message,
        _build_initial_setup_message(
            context,
            fsm_data,
            from_compat_alias=context.user_data.get("in_conversation")
            == "CUSTOM_VIDEO",
        ),
        reply_markup=_build_initial_setup_keyboard(context, fsm_data),
        parse_mode="Markdown",
    )
    return ImageToVideoState.WAIT_LORA_SELECTION


async def receive_initial_setup_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    fsm_data = _get_image_to_video_data(context)
    if not fsm_data:
        await robust_reply_text(update.message, _t(context, "fsm.common.expired_cleaned"))
        return ConversationHandler.END
    return await receive_image(update, context)


async def _download_image_message(
    *,
    message,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    name_hint: str,
) -> str | None:
    if message.document:
        if not message.document.mime_type.startswith("image/"):
            await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
            return None
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return None

    try:
        new_file = await context.bot.get_file(file_id)
        return await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint=name_hint,
        )
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return None


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = _get_image_to_video_data(context)
    if not fsm_data:
        await robust_reply_text(
            message, _t(context, "fsm.common.expired_cleaned")
        )
        return ConversationHandler.END

    local_path = await _download_image_message(
        message=message,
        context=context,
        user_id=user_id,
        name_hint="image_to_video_start",
    )
    if not local_path:
        return ImageToVideoState.WAIT_IMAGE

    fsm_data["image_path"] = local_path
    fsm_data["end_image_path"] = None

    if fsm_data.get("use_end_frame"):
        await robust_reply_text(
            message,
            _t(context, "fsm.image_to_video.send_end_image"),
            parse_mode="Markdown",
        )
        return ImageToVideoState.WAIT_END_IMAGE

    await robust_reply_text(
        message,
        _build_prompt_request_text(
            context,
            fsm_data,
            received_key="fsm.image_to_video.start_image_received",
        ),
        parse_mode="Markdown",
    )
    return ImageToVideoState.WAIT_SETTINGS_AND_PROMPT


async def choose_end_frame_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    fsm_data = _get_image_to_video_data(context) or {}
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.image_to_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    use_end_frame = query.data == "i2v_end_frame_yes"
    fsm_data["use_end_frame"] = use_end_frame

    if use_end_frame:
        with contextlib.suppress(Exception):
            await robust_edit_text(
                query.message,
                _t(context, "fsm.image_to_video.send_end_image"),
                parse_mode="Markdown",
            )
        await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
        return ImageToVideoState.WAIT_END_IMAGE

    fsm_data["end_image_path"] = None
    reply_markup, _cost, msg_text = await _build_video_settings_view_model(
        context=context,
        user_id=query.from_user.id,
        fsm_data=fsm_data,
    )
    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    return ImageToVideoState.WAIT_SETTINGS_AND_PROMPT


async def receive_end_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = _get_image_to_video_data(context)
    if not fsm_data:
        await robust_reply_text(
            message, _t(context, "fsm.common.expired_cleaned")
        )
        return ConversationHandler.END

    local_path = await _download_image_message(
        message=message,
        context=context,
        user_id=user_id,
        name_hint="image_to_video_end",
    )
    if not local_path:
        return ImageToVideoState.WAIT_END_IMAGE

    fsm_data["end_image_path"] = local_path
    fsm_data["use_end_frame"] = True

    await robust_reply_text(
        message,
        _build_prompt_request_text(
            context,
            fsm_data,
            received_key="fsm.image_to_video.end_image_received",
        ),
        parse_mode="Markdown",
    )
    return ImageToVideoState.WAIT_SETTINGS_AND_PROMPT


async def process_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings change via inline keyboard"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    fsm_data = _get_image_to_video_data(context) or {}
    if not fsm_data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.image_to_video.expired_alert"), show_alert=True)
        return ConversationHandler.END

    if data.startswith("set_res_"):
        fsm_data["resolution"] = normalize_wan22_video_v2_resolution_preset(
            data.removeprefix("set_res_")
        )
    elif data.startswith("set_dur_"):
        fsm_data["duration"] = normalize_wan22_video_v2_duration_seconds(
            data.removeprefix("set_dur_")
        )

    reply_markup, _cost, msg_text = await _build_video_settings_view_model(
        context=context,
        user_id=user_id,
        fsm_data=fsm_data,
    )

    with contextlib.suppress(Exception):
        await robust_edit_text(
            query.message, msg_text, reply_markup=reply_markup, parse_mode="Markdown"
        )

    await query.answer(text="⏳ 任务初始化中...", cache_time=2)
    return ImageToVideoState.WAIT_SETTINGS_AND_PROMPT


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    prompt = message.text.strip()

    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    fsm_data = _get_image_to_video_data(context)
    if not fsm_data:
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    res = normalize_wan22_video_v2_resolution_preset(str(fsm_data["resolution"]))
    dur = _normalize_selected_duration(fsm_data)
    lora_name = fsm_data["lora_name"]

    cost = _compute_video_generation_cost(res, dur)

    image_path = fsm_data.get("image_path")
    if not image_path:
        logger.warning(
            f"user={user_id} image_path missing before submit in image_to_video"
        )
        await robust_reply_text(message, _t(context, "fsm.common.missing_image_resend"))
        _cleanup_context(context, user_id)
        return ConversationHandler.END

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
                "fsm.common.insufficient_credits", current=e.current, cost=e.cost
            )
            from src.utils import robust_send_message

            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        raise e

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        logger.warning(
            f"user={user_id} image_path consumed by another request before submit in image_to_video"
        )
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        _cleanup_context(context, user_id)
        return ConversationHandler.END
    end_image_path = fsm_data.pop("end_image_path", None)
    use_end_frame = bool(fsm_data.get("use_end_frame") and end_image_path)
    submit_images = [image_path]
    if use_end_frame:
        submit_images.append(end_image_path)

    await robust_reply_text(
        message, _build_submit_message(lora_name, cost, lang=getattr(context, "lang", "zh"))
    )

    task_type = _resolve_image_to_video_task_type(context)
    create_background_task(
        context,
        process_image_to_video_task(
            context=context,
            chat_id=message.chat_id,
            user_id=user_id,
            username=update.effective_user.username,
            prompt=prompt,
            images=submit_images,
            resolution=res,
            duration=dur,
            use_end_frame=use_end_frame,
            resolution_preset=res,
            task_type=task_type,
            cleanup=True,
            lora_name=lora_name,
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
        reply_text_func=robust_reply_text,
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


def _build_image_to_video_fsm_handler(
    *,
    entry_points: list,
    handler_name: str,
) -> ConversationHandler:
    return ConversationHandler(
        entry_points=entry_points,
        states={
            ImageToVideoState.WAIT_LORA_SELECTION: [
                CallbackQueryHandler(
                    handle_initial_setup_selection,
                    pattern=I2V_SETUP_ACTION_PATTERN,
                ),
                CallbackQueryHandler(handle_lora_selection, pattern="^lora_select_"),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE,
                    receive_initial_setup_image,
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            ImageToVideoState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            ImageToVideoState.WAIT_END_FRAME_CHOICE: [
                CallbackQueryHandler(
                    choose_end_frame_mode,
                    pattern="^i2v_end_frame_(yes|no)$",
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, unexpected_input
                ),
            ],
            ImageToVideoState.WAIT_END_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_end_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            ImageToVideoState.WAIT_SETTINGS_AND_PROMPT: [
                CallbackQueryHandler(process_settings, pattern=r"^set_(res|dur)_"),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_prompt,
                ),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, unexpected_input
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name=handler_name,
        persistent=False,
    )


def get_image_to_video_fsm_handler() -> ConversationHandler:
    return _build_image_to_video_fsm_handler(
        entry_points=[
            CommandHandler("image_to_video", start_image_to_video),
            CommandHandler("video_lora", start_image_to_video),
            CommandHandler("custom_video", start_custom_video),
            MessageHandler(I18nFilter("menu.video_lora"), start_image_to_video),
            MessageHandler(I18nFilter("menu.custom_video"), start_custom_video),
            CallbackQueryHandler(
                start_image_to_video, pattern="^fsm_start_image_to_video$"
            ),
            CallbackQueryHandler(
                start_image_to_video, pattern="^fsm_start_video_lora$"
            ),
            CallbackQueryHandler(
                start_custom_video, pattern="^fsm_start_custom_video$"
            ),
        ],
        handler_name="image_to_video_fsm",
    )
