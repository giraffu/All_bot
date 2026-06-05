import contextlib
import logging
import re
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.constants import MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO, MODE_WAN22_VIDEO_V2
from src.filters.i18n_filter import I18nFilter
from src.handlers.conversation_states import Wan22VideoV2State
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.prompt_router import is_global_menu_command
from src.lora_mapping import extract_prompt_lora_context
from src.core.video_billing import resolve_apply_prompt_and_requested_duration
from src.services.task_service_generation_video import (
    process_image_to_video_generation_task as process_image_to_video_task,
)
from src.services.task_service_generation_wan22 import (
    normalize_wan22_video_v2_chain_task_ids,
    process_wan22_video_v2_generation_task as process_wan22_video_v2_task,
)
from src.services.wan22_video_v2_config import (
    WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS,
    WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
    WAN22_VIDEO_V2_DURATION_SECONDS,
    WAN22_VIDEO_V2_RESOLUTION_PRESETS,
    get_wan22_video_v2_cost,
    get_wan22_video_v2_duration_label,
    get_wan22_video_v2_resolution_display,
    get_wan22_video_v2_resolution_label,
    normalize_wan22_video_v2_duration_seconds,
    normalize_wan22_video_v2_resolution_preset,
)
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.services.permission_service import permission_service
from src.services.wan22_video_v2_extension_service import (
    Wan22VideoV2ExtensionError,
    build_full_chain_task_ids,
    download_history_input_file_to_fsm_temp,
    download_last_frame_to_fsm_temp,
    extract_wan22_history_context,
    load_owned_wan22_history,
    resolve_extension_chain_task_ids,
    resolve_extension_resolution_preset,
)
from src.services.tg_task_result_presentation import (
    WAN22_EXTEND_CALLBACK_PREFIX,
    WAN22_REGENERATE_CALLBACK_PREFIX,
    resolve_task_id_from_callback_data,
    resolve_task_id_from_reply_markup,
)
from src.utils import create_background_task, robust_edit_text, robust_reply_text

logger = logging.getLogger("fsm.wan22_video_v2")

WAN22_VIDEO_V2_DATA_KEY = "wan22_video_v2_data"
WAN22_VIDEO_V2_CONVERSATION_TAG = "WAN22_VIDEO_V2"
WAN22_VIDEO_V2_SETTINGS_ACTION_PATTERN = (
    rf"^wan22v2_(submit|res_("
    rf"{'|'.join(re.escape(preset_key) for preset_key in WAN22_VIDEO_V2_RESOLUTION_PRESETS)}"
    rf")|dur_({'|'.join(str(duration) for duration in WAN22_VIDEO_V2_DURATION_SECONDS)}))$"
)
WAN22_VIDEO_V2_SETUP_MODE_SINGLE = "wan22v2_setup_mode_single"
WAN22_VIDEO_V2_SETUP_MODE_END = "wan22v2_setup_mode_end"
WAN22_VIDEO_V2_SETUP_RES_PREFIX = "wan22v2_setup_res_"
WAN22_VIDEO_V2_SETUP_DUR_PREFIX = "wan22v2_setup_dur_"
WAN22_VIDEO_V2_SETUP_CONFIRM = "wan22v2_setup_confirm"
WAN22_VIDEO_V2_SETUP_ACTION_PATTERN = (
    rf"^wan22v2_setup_(mode_(single|end)|res_("
    rf"{'|'.join(re.escape(preset_key) for preset_key in WAN22_VIDEO_V2_RESOLUTION_PRESETS)}"
    rf")|dur_({'|'.join(str(duration) for duration in WAN22_VIDEO_V2_DURATION_SECONDS)})|confirm)$"
)
_t = translate_fsm_text


def _default_negative_prompt_label(context: ContextTypes.DEFAULT_TYPE) -> str:
    lang = getattr(context, "lang", "zh")
    return "Default negative prompt" if lang == "en" else "默认负面提示词"


def _get_data(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return context.user_data.get(WAN22_VIDEO_V2_DATA_KEY)


def _set_data(context: ContextTypes.DEFAULT_TYPE, data: dict[str, object]) -> None:
    context.user_data[WAN22_VIDEO_V2_DATA_KEY] = data


def _pop_data(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.user_data.pop(WAN22_VIDEO_V2_DATA_KEY, {}) or {}


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("in_conversation", None)
    data = _pop_data(context)
    cleanup_fsm_temp_files(
        [
            data.get("start_image_path"),
            data.get("end_image_path"),
        ]
    )


def _release_context_without_files(context: ContextTypes.DEFAULT_TYPE) -> dict:
    context.user_data.pop("in_conversation", None)
    return _pop_data(context)


def _resolve_submit_images(data: dict[str, Any]) -> list[str]:
    images = [str(data["start_image_path"])]
    if data.get("use_end_frame") and data.get("end_image_path"):
        images.append(str(data["end_image_path"]))
    return images


def _build_chain_result_meta(data: dict[str, Any]) -> dict[str, Any] | None:
    if not data.get("extension_prev_task_id"):
        return None
    return {
        "wan22_prev_task_id": str(data["extension_prev_task_id"]),
        "wan22_chain_task_ids": normalize_wan22_video_v2_chain_task_ids(
            data.get("chain_task_ids")
        ),
    }


def _resolve_legacy_lora_strength(data: dict[str, Any]) -> float:
    try:
        return float(data.get("lora_strength"))
    except (TypeError, ValueError):
        return 1.0


def _is_legacy_image_to_video_context(data: dict[str, Any] | dict[str, object]) -> bool:
    extension_task_type = str(data.get("extension_task_type") or MODE_WAN22_VIDEO_V2)
    return extension_task_type != MODE_WAN22_VIDEO_V2


def _resolve_reusable_history_prompt_and_lora(
    history,
    meta: dict,
) -> tuple[str, str | None, float]:
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


def _normalize_selected_duration(data: dict[str, object]) -> int:
    selected_duration = normalize_wan22_video_v2_duration_seconds(
        data.get("duration") or WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS
    )
    data["duration"] = selected_duration
    return selected_duration


def _resolve_history_duration_seconds(history, meta: dict) -> int:
    return normalize_wan22_video_v2_duration_seconds(
        meta.get("wan22_duration_seconds")
        or getattr(history, "requested_duration", None)
        or getattr(history, "duration", None)
    )


def _resolve_callback_task_id(
    *,
    meta: dict,
    query,
    callback_prefix: str,
) -> str:
    task_id = resolve_task_id_from_callback_data(
        getattr(query, "data", None),
        callback_prefix,
    )
    if task_id:
        return task_id
    task_id = str(meta.get("task_id") or "").strip()
    if task_id:
        return task_id
    message = getattr(query, "message", None)
    return resolve_task_id_from_reply_markup(getattr(message, "reply_markup", None))


def _merge_history_context_into_meta(history, meta: dict) -> dict[str, object]:
    return {
        **extract_wan22_history_context(getattr(history, "extra_outputs", None)),
        **meta,
    }


async def _reply_callback_notice(update: Update, text: str) -> None:
    query = update.callback_query
    target_message = query.message if query else update.effective_message
    if target_message:
        await robust_reply_text(target_message, text, parse_mode="Markdown")


def _build_submit_generation_task(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user,
    data: dict[str, Any],
    images: list[str],
    resolution_preset: str,
):
    prompt = str(data.get("prompt") or "").strip()
    negative_prompt = str(data.get("negative_prompt") or "").strip()
    use_end_frame = bool(data.get("use_end_frame"))
    extension_task_type = str(data.get("extension_task_type") or MODE_WAN22_VIDEO_V2)
    duration_seconds = _normalize_selected_duration(data)

    if extension_task_type == MODE_WAN22_VIDEO_V2:
        return process_wan22_video_v2_task(
            context=context,
            chat_id=update.effective_chat.id,
            user_id=user.id,
            username=user.username,
            prompt=prompt,
            negative_prompt=negative_prompt,
            images=images,
            use_end_frame=use_end_frame,
            resolution_preset=resolution_preset,
            duration=duration_seconds,
            result_meta=_build_chain_result_meta(data),
            cleanup=True,
        )

    return process_image_to_video_task(
        context=context,
        chat_id=update.effective_chat.id,
        user_id=user.id,
        username=user.username,
        prompt=prompt,
        negative_prompt=negative_prompt,
        images=images,
        use_end_frame=use_end_frame,
        resolution_preset=resolution_preset,
        duration=duration_seconds,
        wan22_prev_task_id=(
            str(data["extension_prev_task_id"])
            if data.get("extension_prev_task_id")
            else None
        ),
        wan22_chain_task_ids=normalize_wan22_video_v2_chain_task_ids(
            data.get("chain_task_ids")
        ),
        task_type=(
            MODE_IMAGE_TO_VIDEO
            if extension_task_type == MODE_IMAGE_TO_VIDEO
            else MODE_CUSTOM_VIDEO
        ),
        lora_name=str(data.get("lora_name") or "").strip() or None,
        lora_strength=_resolve_legacy_lora_strength(data),
        cleanup=True,
    )


def _build_end_frame_choice_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.enable_end_frame"),
                    callback_data="wan22v2_end_frame_yes",
                ),
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.disable_end_frame"),
                    callback_data="wan22v2_end_frame_no",
                ),
            ]
        ]
    )


def _selected_button_label(label: str, *, selected: bool) -> str:
    return f"✅ {label}" if selected else label


def _get_frame_mode_label(
    context: ContextTypes.DEFAULT_TYPE,
    use_end_frame: bool,
) -> str:
    key = (
        "fsm.wan22_video_v2.frame_mode_end"
        if use_end_frame
        else "fsm.wan22_video_v2.frame_mode_single"
    )
    return _t(context, key)


def _normalize_selected_resolution(data: dict[str, object]) -> str:
    selected_resolution = normalize_wan22_video_v2_resolution_preset(
        str(data.get("resolution_preset") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET)
    )
    data["resolution_preset"] = selected_resolution
    return selected_resolution


def _build_initial_setup_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    data: dict[str, object],
) -> InlineKeyboardMarkup:
    lang = getattr(context, "lang", "zh")
    selected_resolution = _normalize_selected_resolution(data)
    selected_duration = _normalize_selected_duration(data)
    use_end_frame = bool(data.get("use_end_frame"))
    credits_text = _t(context, "app.credits")
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
                callback_data=f"{WAN22_VIDEO_V2_SETUP_RES_PREFIX}{preset_key}",
            )
        )
    duration_row = []
    for duration_seconds in WAN22_VIDEO_V2_DURATION_SECONDS:
        label = get_wan22_video_v2_duration_label(duration_seconds, lang=lang)
        cost_for_duration = get_wan22_video_v2_cost(
            selected_resolution,
            duration_seconds,
        )
        duration_row.append(
            InlineKeyboardButton(
                _selected_button_label(
                    f"{label} ({cost_for_duration}{credits_text})",
                    selected=duration_seconds == selected_duration,
                ),
                callback_data=f"{WAN22_VIDEO_V2_SETUP_DUR_PREFIX}{duration_seconds}",
            )
        )

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _selected_button_label(
                        _t(context, "fsm.wan22_video_v2.disable_end_frame"),
                        selected=not use_end_frame,
                    ),
                    callback_data=WAN22_VIDEO_V2_SETUP_MODE_SINGLE,
                ),
                InlineKeyboardButton(
                    _selected_button_label(
                        _t(context, "fsm.wan22_video_v2.enable_end_frame"),
                        selected=use_end_frame,
                    ),
                    callback_data=WAN22_VIDEO_V2_SETUP_MODE_END,
                ),
            ],
            resolution_row,
            duration_row,
            [
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.setup_confirm"),
                    callback_data=WAN22_VIDEO_V2_SETUP_CONFIRM,
                )
            ],
        ]
    )


def _build_initial_setup_message(
    context: ContextTypes.DEFAULT_TYPE,
    data: dict[str, object],
) -> str:
    lang = getattr(context, "lang", "zh")
    resolution = _normalize_selected_resolution(data)
    duration = _normalize_selected_duration(data)
    use_end_frame = bool(data.get("use_end_frame"))
    return _t(
        context,
        "fsm.wan22_video_v2.setup_text",
        frame_mode=_get_frame_mode_label(context, use_end_frame),
        image_count=2 if use_end_frame else 1,
        resolution=get_wan22_video_v2_resolution_display(resolution, lang=lang),
        duration=get_wan22_video_v2_duration_label(duration, lang=lang),
        cost=get_wan22_video_v2_cost(resolution, duration),
    )


def _build_start_image_request_message(
    context: ContextTypes.DEFAULT_TYPE,
    data: dict[str, object],
) -> str:
    lang = getattr(context, "lang", "zh")
    resolution = _normalize_selected_resolution(data)
    duration = _normalize_selected_duration(data)
    use_end_frame = bool(data.get("use_end_frame"))
    note_key = (
        "fsm.wan22_video_v2.start_note_end_frame"
        if use_end_frame
        else "fsm.wan22_video_v2.start_note_single"
    )
    return _t(
        context,
        "fsm.wan22_video_v2.send_start_after_setup",
        frame_mode=_get_frame_mode_label(context, use_end_frame),
        image_count=2 if use_end_frame else 1,
        resolution=get_wan22_video_v2_resolution_display(resolution, lang=lang),
        duration=get_wan22_video_v2_duration_label(duration, lang=lang),
        cost=get_wan22_video_v2_cost(resolution, duration),
        note=_t(context, note_key),
    )


def _build_settings_keyboard(
    context: ContextTypes.DEFAULT_TYPE, data: dict[str, object]
) -> InlineKeyboardMarkup:
    current_resolution = str(
        data.get("resolution_preset") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    )
    lang = getattr(context, "lang", "zh")
    current_duration = _normalize_selected_duration(data)
    resolution_buttons = []
    for preset_key in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        label = get_wan22_video_v2_resolution_label(preset_key, lang=lang)
        if current_resolution == preset_key:
            label = f"• {label}"
        resolution_buttons.append(
            InlineKeyboardButton(
                label,
                callback_data=f"wan22v2_res_{preset_key}",
            )
        )
    duration_buttons = []
    for duration_seconds in WAN22_VIDEO_V2_DURATION_SECONDS:
        label = get_wan22_video_v2_duration_label(duration_seconds, lang=lang)
        if current_duration == duration_seconds:
            label = f"• {label}"
        duration_buttons.append(
            InlineKeyboardButton(
                label,
                callback_data=f"wan22v2_dur_{duration_seconds}",
            )
        )

    return InlineKeyboardMarkup(
        [
            resolution_buttons,
            duration_buttons,
            [
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.submit_button"),
                    callback_data="wan22v2_submit",
                )
            ],
        ]
    )


def _build_skip_negative_prompt_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.skip_negative_prompt"),
                    callback_data="wan22v2_skip_negative_prompt",
                )
            ]
        ]
    )


def _build_use_original_prompt_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _t(context, "fsm.wan22_video_v2.use_original_prompt"),
                    callback_data="wan22v2_use_original_prompt",
                )
            ]
        ]
    )


def _build_settings_message(
    context: ContextTypes.DEFAULT_TYPE, data: dict[str, object]
) -> str:
    lang = getattr(context, "lang", "zh")
    status_yes = _t(context, "fsm.wan22_video_v2.status_yes")
    status_no = _t(context, "fsm.wan22_video_v2.status_no")
    negative_prompt = str(data.get("negative_prompt") or "").strip()
    resolution_preset = str(
        data.get("resolution_preset") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    )
    resolution_display = get_wan22_video_v2_resolution_display(
        resolution_preset,
        lang=lang,
    )
    duration = _normalize_selected_duration(data)
    cost = get_wan22_video_v2_cost(resolution_preset, duration)
    settings_key = (
        "fsm.wan22_video_v2.legacy_settings_text"
        if _is_legacy_image_to_video_context(data)
        else "fsm.wan22_video_v2.settings_text"
    )
    return _t(
        context,
        settings_key,
        use_end_frame=status_yes if data.get("use_end_frame") else status_no,
        end_frame_ready=(
            status_yes
            if (not data.get("use_end_frame") or data.get("end_image_path"))
            else status_no
        ),
        prompt=str(data.get("prompt") or "").strip() or "-",
        negative_prompt=negative_prompt or _default_negative_prompt_label(context),
        resolution_preset=resolution_display,
        duration=get_wan22_video_v2_duration_label(duration, lang=lang),
        cost=cost,
    )


async def _send_or_edit_message(
    update: Update,
    message_text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    query = update.callback_query
    if query:
        target_message = query.message
        # Result callbacks can come from media messages; those cannot be edited as text.
        if getattr(target_message, "text", None):
            await robust_edit_text(
                target_message,
                message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        else:
            await robust_reply_text(
                target_message,
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


async def _ask_for_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = _get_data(context) or {}
    original_prompt = str(data.get("prefill_prompt") or "").strip()
    if original_prompt:
        await _send_or_edit_message(
            update,
            _t(
                context,
                "fsm.wan22_video_v2.regenerate_prompt",
                prompt=original_prompt,
            ),
            reply_markup=_build_use_original_prompt_keyboard(context),
        )
        return Wan22VideoV2State.WAIT_PROMPT

    await _send_or_edit_message(update, _t(context, "fsm.wan22_video_v2.send_prompt"))
    return Wan22VideoV2State.WAIT_PROMPT


async def _ask_for_negative_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    await _send_or_edit_message(
        update,
        _t(context, "fsm.wan22_video_v2.send_negative_prompt"),
        reply_markup=_build_skip_negative_prompt_keyboard(context),
    )
    return Wan22VideoV2State.WAIT_NEGATIVE_PROMPT


async def _show_settings(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = _get_data(context) or {}
    await _send_or_edit_message(
        update,
        _build_settings_message(context, data),
        reply_markup=_build_settings_keyboard(context, data),
    )
    return Wan22VideoV2State.WAIT_SETTINGS


def _extract_image_file_id(message) -> str | None:
    if message.document:
        mime_type = message.document.mime_type or ""
        if not mime_type.startswith("image/"):
            return None
        return message.document.file_id
    if message.photo:
        return message.photo[-1].file_id
    return None


async def _download_image_to_temp(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    file_id: str,
    name_hint: str,
) -> str:
    telegram_file = await context.bot.get_file(file_id)
    return await download_telegram_file_to_fsm_temp(
        telegram_file=telegram_file,
        suffix=".png",
        name_hint=name_hint,
    )


async def start_wan22_video_v2(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        msg = _t(context, "fsm.common.maintenance")
        await _send_or_edit_message(update, msg)
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        await _send_or_edit_message(update, _t(context, "fsm.common.conflict"))
        return ConversationHandler.END

    context.user_data["in_conversation"] = WAN22_VIDEO_V2_CONVERSATION_TAG
    _set_data(
        context,
        {
            "start_image_path": None,
            "end_image_path": None,
            "use_end_frame": False,
            "resolution_preset": WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET,
            "duration": WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS,
            "prompt": "",
            "negative_prompt": "",
            "extension_task_type": MODE_WAN22_VIDEO_V2,
        },
    )
    data = _get_data(context) or {}
    await _send_or_edit_message(
        update,
        _build_initial_setup_message(context, data),
        reply_markup=_build_initial_setup_keyboard(context, data),
    )
    return Wan22VideoV2State.WAIT_SETUP


async def start_wan22_video_v2_extension(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    if context.user_data.get("in_conversation"):
        await _reply_callback_notice(update, _t(context, "fsm.common.conflict"))
        return ConversationHandler.END

    meta = (
        context.bot_data.get(f"msg_meta_{query.message.message_id}", {})
        if query and query.message
        else {}
    )
    base_task_id = _resolve_callback_task_id(
        meta=meta,
        query=query,
        callback_prefix=WAN22_EXTEND_CALLBACK_PREFIX,
    )
    if not base_task_id:
        await _reply_callback_notice(update, _t(context, "fsm.wan22_video_v2.expired_alert"))
        return ConversationHandler.END
    try:
        history = await load_owned_wan22_history(
            task_id=base_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        meta = _merge_history_context_into_meta(history, meta)
        start_image_path = await download_last_frame_to_fsm_temp(history=history)
    except Wan22VideoV2ExtensionError as exc:
        target_message = query.message if query else update.effective_message
        if target_message:
            with contextlib.suppress(Exception):
                await robust_reply_text(target_message, f"❌ {exc}")
        return ConversationHandler.END
    except Exception as exc:
        logger.error("prepare wan22_video_v2 extension failed: %s", exc)
        target_message = query.message if query else update.effective_message
        if target_message:
            with contextlib.suppress(Exception):
                await robust_reply_text(
                    target_message,
                    f"❌ {_t(context, 'fsm.common.download_image_failed')}",
                )
        return ConversationHandler.END

    context.user_data["in_conversation"] = WAN22_VIDEO_V2_CONVERSATION_TAG
    _set_data(
        context,
        {
            "start_image_path": start_image_path,
            "end_image_path": None,
            "use_end_frame": False,
            "resolution_preset": resolve_extension_resolution_preset(meta),
            "duration": _resolve_history_duration_seconds(history, meta),
            "prompt": "",
            "negative_prompt": "",
            "extension_prev_task_id": base_task_id,
            "extension_task_type": history.type,
            "lora_name": str(meta.get("lora_name") or "").strip(),
            "lora_strength": meta.get("lora_strength"),
            "chain_task_ids": build_full_chain_task_ids(
                chain_task_ids=resolve_extension_chain_task_ids(meta),
                current_task_id=base_task_id,
            ),
        },
    )
    await _send_or_edit_message(
        update,
        _t(
            context,
            "fsm.wan22_video_v2.extension_start",
            resolution_preset=get_wan22_video_v2_resolution_label(
                str(
                    context.user_data[WAN22_VIDEO_V2_DATA_KEY]["resolution_preset"]
                ),
                lang=getattr(context, "lang", "zh"),
            ),
        ),
        reply_markup=_build_end_frame_choice_keyboard(context),
    )
    return Wan22VideoV2State.WAIT_END_FRAME_CHOICE


async def start_wan22_video_v2_regeneration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    if query:
        with contextlib.suppress(Exception):
            await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    if context.user_data.get("in_conversation"):
        await _reply_callback_notice(update, _t(context, "fsm.common.conflict"))
        return ConversationHandler.END

    meta = (
        context.bot_data.get(f"msg_meta_{query.message.message_id}", {})
        if query and query.message
        else {}
    )
    current_task_id = _resolve_callback_task_id(
        meta=meta,
        query=query,
        callback_prefix=WAN22_REGENERATE_CALLBACK_PREFIX,
    )
    if not current_task_id:
        await _reply_callback_notice(update, _t(context, "fsm.wan22_video_v2.expired_alert"))
        return ConversationHandler.END

    try:
        current_history = await load_owned_wan22_history(
            task_id=current_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        meta = _merge_history_context_into_meta(current_history, meta)
        prev_task_id = str(meta.get("wan22_prev_task_id") or "").strip()
        if not prev_task_id:
            await _reply_callback_notice(
                update,
                _t(context, "fsm.wan22_video_v2.expired_alert"),
            )
            return ConversationHandler.END
        prev_history = await load_owned_wan22_history(
            task_id=prev_task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        start_image_path = await download_last_frame_to_fsm_temp(
            history=prev_history,
            name_hint="wan22_video_v2_regenerate_start",
        )
        use_end_frame = bool(meta.get("wan22_use_end_frame"))
        end_image_path = None
        if use_end_frame:
            end_image_path = await download_history_input_file_to_fsm_temp(
                history=current_history,
                index=1,
                name_hint="wan22_video_v2_regenerate_end",
            )
    except Wan22VideoV2ExtensionError as exc:
        target_message = query.message if query else update.effective_message
        if target_message:
            with contextlib.suppress(Exception):
                await robust_reply_text(target_message, f"❌ {exc}")
        return ConversationHandler.END
    except Exception as exc:
        logger.error("prepare wan22_video_v2 regeneration failed: %s", exc)
        target_message = query.message if query else update.effective_message
        if target_message:
            with contextlib.suppress(Exception):
                await robust_reply_text(
                    target_message,
                    f"❌ {_t(context, 'fsm.common.download_image_failed')}",
                )
        return ConversationHandler.END

    if current_history.type == MODE_WAN22_VIDEO_V2:
        prompt = str(current_history.prompt or "").strip()
        lora_name = None
        lora_strength = None
    else:
        prompt, lora_name, lora_strength = _resolve_reusable_history_prompt_and_lora(
            current_history,
            meta,
        )

    context.user_data["in_conversation"] = WAN22_VIDEO_V2_CONVERSATION_TAG
    _set_data(
        context,
        {
            "start_image_path": start_image_path,
            "end_image_path": end_image_path,
            "use_end_frame": use_end_frame,
            "resolution_preset": resolve_extension_resolution_preset(meta),
            "duration": _resolve_history_duration_seconds(current_history, meta),
            "prompt": prompt,
            "prefill_prompt": prompt,
            "negative_prompt": str(meta.get("wan22_negative_prompt") or "").strip(),
            "extension_prev_task_id": prev_task_id,
            "extension_task_type": current_history.type,
            "lora_name": lora_name,
            "lora_strength": lora_strength,
            "chain_task_ids": normalize_wan22_video_v2_chain_task_ids(
                meta.get("wan22_chain_task_ids")
            ),
        },
    )
    return await _ask_for_prompt(update, context)


async def handle_initial_setup_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = _get_data(context)
    if not data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    callback_data = query.data or ""
    if callback_data == WAN22_VIDEO_V2_SETUP_MODE_SINGLE:
        data["use_end_frame"] = False
        data["end_image_path"] = None
    elif callback_data == WAN22_VIDEO_V2_SETUP_MODE_END:
        data["use_end_frame"] = True
        data["end_image_path"] = None
    elif callback_data.startswith(WAN22_VIDEO_V2_SETUP_RES_PREFIX):
        data["resolution_preset"] = normalize_wan22_video_v2_resolution_preset(
            callback_data.removeprefix(WAN22_VIDEO_V2_SETUP_RES_PREFIX)
        )
    elif callback_data.startswith(WAN22_VIDEO_V2_SETUP_DUR_PREFIX):
        data["duration"] = normalize_wan22_video_v2_duration_seconds(
            callback_data.removeprefix(WAN22_VIDEO_V2_SETUP_DUR_PREFIX)
        )
    elif callback_data == WAN22_VIDEO_V2_SETUP_CONFIRM:
        await robust_edit_text(
            query.message,
            _build_start_image_request_message(context, data),
            parse_mode="Markdown",
        )
        return Wan22VideoV2State.WAIT_START_IMAGE
    else:
        return Wan22VideoV2State.WAIT_SETUP

    await robust_edit_text(
        query.message,
        _build_initial_setup_message(context, data),
        reply_markup=_build_initial_setup_keyboard(context, data),
        parse_mode="Markdown",
    )
    return Wan22VideoV2State.WAIT_SETUP


async def receive_start_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    data = _get_data(context)
    if not data:
        await robust_reply_text(message, _t(context, "fsm.common.expired_cleaned"))
        return ConversationHandler.END

    file_id = _extract_image_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return Wan22VideoV2State.WAIT_START_IMAGE

    try:
        data["start_image_path"] = await _download_image_to_temp(
            context,
            file_id=file_id,
            name_hint="wan22_video_v2_start",
        )
    except Exception as exc:
        logger.error("download start image failed for wan22_video_v2: %s", exc)
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return Wan22VideoV2State.WAIT_START_IMAGE

    data["end_image_path"] = None
    if data.get("use_end_frame"):
        await robust_reply_text(
            message,
            _t(context, "fsm.wan22_video_v2.send_end_image"),
            parse_mode="Markdown",
        )
        return Wan22VideoV2State.WAIT_END_IMAGE

    await robust_reply_text(
        message,
        _t(context, "fsm.wan22_video_v2.start_image_received"),
        parse_mode="Markdown",
    )
    return await _ask_for_prompt(update, context)


async def choose_end_frame_mode(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = _get_data(context)
    if not data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    use_end_frame = query.data == "wan22v2_end_frame_yes"
    data["use_end_frame"] = use_end_frame
    data["end_image_path"] = None

    if use_end_frame:
        await robust_edit_text(
            query.message,
            _t(context, "fsm.wan22_video_v2.send_end_image"),
            parse_mode="Markdown",
        )
        return Wan22VideoV2State.WAIT_END_IMAGE

    await robust_edit_text(
        query.message,
        _t(context, "fsm.wan22_video_v2.single_frame_confirmed"),
        parse_mode="Markdown",
    )
    return await _ask_for_prompt(update, context)


async def receive_end_image(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    data = _get_data(context)
    if not data:
        await robust_reply_text(message, _t(context, "fsm.common.expired_cleaned"))
        return ConversationHandler.END

    file_id = _extract_image_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return Wan22VideoV2State.WAIT_END_IMAGE

    try:
        data["end_image_path"] = await _download_image_to_temp(
            context,
            file_id=file_id,
            name_hint="wan22_video_v2_end",
        )
    except Exception as exc:
        logger.error("download end image failed for wan22_video_v2: %s", exc)
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return Wan22VideoV2State.WAIT_END_IMAGE

    await robust_reply_text(message, _t(context, "fsm.wan22_video_v2.end_image_received"))
    return await _ask_for_prompt(update, context)


async def receive_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    prompt = (message.text or "").strip()
    if is_global_menu_command(prompt):
        return await unexpected_input(update, context)

    data = _get_data(context)
    if not data:
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    data["prompt"] = prompt
    return await _ask_for_negative_prompt(update, context)


async def use_original_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = _get_data(context)
    if not data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    data["prompt"] = str(
        data.get("prompt") or data.get("prefill_prompt") or ""
    ).strip()
    return await _ask_for_negative_prompt(update, context)


async def receive_negative_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.message
    negative_prompt = (message.text or "").strip()
    if is_global_menu_command(negative_prompt):
        return await unexpected_input(update, context)

    data = _get_data(context)
    if not data:
        await robust_reply_text(message, _t(context, "fsm.common.already_submitted"))
        return ConversationHandler.END

    data["negative_prompt"] = negative_prompt
    return await _show_settings(update, context)


async def skip_negative_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = _get_data(context)
    if not data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    data["negative_prompt"] = ""
    return await _show_settings(update, context)


async def handle_settings_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)
    data = _get_data(context)
    if not data:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    callback_data = query.data or ""
    if callback_data.startswith("wan22v2_res_"):
        selected_preset = callback_data.removeprefix("wan22v2_res_")
        if selected_preset in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
            data["resolution_preset"] = selected_preset
    elif callback_data.startswith("wan22v2_dur_"):
        data["duration"] = normalize_wan22_video_v2_duration_seconds(
            callback_data.removeprefix("wan22v2_dur_")
        )

    if callback_data == "wan22v2_submit":
        return await submit_generation(update, context)

    await robust_edit_text(
        query.message,
        _build_settings_message(context, data),
        reply_markup=_build_settings_keyboard(context, data),
        parse_mode="Markdown",
    )
    return Wan22VideoV2State.WAIT_SETTINGS


async def submit_generation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    user = update.effective_user
    data = _get_data(context)
    if not data or not user:
        if query:
            with contextlib.suppress(Exception):
                await query.answer(_t(context, "fsm.wan22_video_v2.expired_alert"), show_alert=True)
        return ConversationHandler.END

    start_image_path = data.get("start_image_path")
    if not start_image_path:
        if query:
            with contextlib.suppress(Exception):
                await query.answer(_t(context, "fsm.common.missing_image_resend"), show_alert=True)
        _cleanup_context(context)
        return ConversationHandler.END

    if data.get("use_end_frame") and not data.get("end_image_path"):
        if query:
            with contextlib.suppress(Exception):
                await query.answer(_t(context, "fsm.wan22_video_v2.missing_end_image"), show_alert=True)
        return Wan22VideoV2State.WAIT_SETTINGS

    resolution_preset = str(
        data.get("resolution_preset") or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET
    )
    duration = _normalize_selected_duration(data)
    cost = get_wan22_video_v2_cost(resolution_preset, duration)

    try:
        await permission_service.check_quota(
            user.id,
            user.username,
            user.full_name,
            cost=cost,
        )
    except Exception as exc:
        from src.core.exceptions import InsufficientCreditsError
        from src.utils import robust_send_message

        if isinstance(exc, InsufficientCreditsError):
            await robust_send_message(
                context.bot,
                update.effective_chat.id,
                _t(
                    context,
                    "fsm.common.insufficient_credits",
                    current=exc.current,
                    cost=exc.cost,
                ),
                parse_mode="Markdown",
            )
            _cleanup_context(context)
            return ConversationHandler.END
        raise exc

    images = _resolve_submit_images(data)

    if query:
        with contextlib.suppress(Exception):
            submitting_key = (
                "fsm.wan22_video_v2.submitting_legacy"
                if _is_legacy_image_to_video_context(data)
                else "fsm.wan22_video_v2.submitting"
            )
            await robust_edit_text(
                query.message,
                _t(context, submitting_key, cost=cost),
                parse_mode="Markdown",
            )

    task_coro = _build_submit_generation_task(
        update=update,
        context=context,
        user=user,
        data=data,
        images=images,
        resolution_preset=resolution_preset,
    )
    create_background_task(context, task_coro)
    _release_context_without_files(context)
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_cancel(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await handle_standard_fsm_timeout(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_standard_fsm_unexpected_input(
        update,
        context,
        cleanup_func=lambda: _cleanup_context(context),
        translate_func=_t,
        reply_text_func=robust_reply_text,
    )


def get_wan22_video_v2_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("wan22_video_v2", start_wan22_video_v2),
            MessageHandler(I18nFilter("menu.wan22_video_v2"), start_wan22_video_v2),
            CallbackQueryHandler(
                start_wan22_video_v2, pattern="^fsm_start_wan22_video_v2$"
            ),
            CallbackQueryHandler(
                start_wan22_video_v2_extension,
                pattern=rf"^{WAN22_EXTEND_CALLBACK_PREFIX}(?::.+)?$",
            ),
            CallbackQueryHandler(
                start_wan22_video_v2_regeneration,
                pattern=rf"^{WAN22_REGENERATE_CALLBACK_PREFIX}(?::.+)?$",
            ),
        ],
        states={
            Wan22VideoV2State.WAIT_SETUP: [
                CallbackQueryHandler(
                    handle_initial_setup_action,
                    pattern=WAN22_VIDEO_V2_SETUP_ACTION_PATTERN,
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            Wan22VideoV2State.WAIT_START_IMAGE: [
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE, receive_start_image
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            Wan22VideoV2State.WAIT_END_FRAME_CHOICE: [
                CallbackQueryHandler(
                    choose_end_frame_mode,
                    pattern="^wan22v2_end_frame_(yes|no)$",
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            Wan22VideoV2State.WAIT_END_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_end_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            Wan22VideoV2State.WAIT_PROMPT: [
                CallbackQueryHandler(
                    use_original_prompt,
                    pattern="^wan22v2_use_original_prompt$",
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_prompt,
                ),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            Wan22VideoV2State.WAIT_NEGATIVE_PROMPT: [
                CallbackQueryHandler(
                    skip_negative_prompt, pattern="^wan22v2_skip_negative_prompt$"
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    receive_negative_prompt,
                ),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            Wan22VideoV2State.WAIT_SETTINGS: [
                CallbackQueryHandler(
                    handle_settings_action,
                    pattern=WAN22_VIDEO_V2_SETTINGS_ACTION_PATTERN,
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, unexpected_input),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="wan22_video_v2_fsm",
        persistent=False,
    )
