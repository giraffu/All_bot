from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.constants import LTX_DURATION_MULTIPLIER, LTX_RESOLUTION_COST
from src.constants import get_ltx_video_settings_keyboard
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
from src.lora_catalog import (
    VIDEO_LORA_MODELS,
    get_ltx_video_lora_display_name,
    get_video_lora_display_name,
)


TranslateFunc = Callable[..., str]


@dataclass(frozen=True)
class AdvancedVideoSettingsView:
    reply_markup: InlineKeyboardMarkup
    message_text: str
    cost: int
    resolution: str
    duration: int | str


def selected_button_label(label: str, *, selected: bool) -> str:
    return f"✅ {label}" if selected else label


def chunk_buttons(
    buttons: list[InlineKeyboardButton],
    size: int,
) -> list[list[InlineKeyboardButton]]:
    return [buttons[index : index + size] for index in range(0, len(buttons), size)]


def normalize_wan22_view_settings(
    fsm_data: dict[str, object],
    *,
    resolution_key: str,
) -> tuple[str, int]:
    resolution = normalize_wan22_video_v2_resolution_preset(
        str(fsm_data.get(resolution_key) or WAN22_VIDEO_V2_DEFAULT_RESOLUTION_PRESET)
    )
    duration = normalize_wan22_video_v2_duration_seconds(
        fsm_data.get("duration") or WAN22_VIDEO_V2_DEFAULT_DURATION_SECONDS
    )
    return resolution, duration


def apply_wan22_video_settings_callback(
    data: dict[str, object],
    *,
    callback_data: str,
    resolution_prefix: str,
    duration_prefix: str,
    resolution_key: str,
) -> bool:
    if callback_data.startswith(resolution_prefix):
        selected_preset = callback_data.removeprefix(resolution_prefix)
        if selected_preset not in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
            return False
        data[resolution_key] = normalize_wan22_video_v2_resolution_preset(
            selected_preset
        )
        return True

    if callback_data.startswith(duration_prefix):
        data["duration"] = normalize_wan22_video_v2_duration_seconds(
            callback_data.removeprefix(duration_prefix)
        )
        return True

    return False


def apply_ltx_video_settings_callback(
    data: dict[str, object],
    *,
    callback_data: str,
) -> bool:
    if callback_data.startswith("set_ltxres_"):
        data["resolution"] = callback_data.removeprefix("set_ltxres_")
        return True

    if callback_data.startswith("set_ltxdur_"):
        data["duration"] = callback_data.removeprefix("set_ltxdur_")
        return True

    return False


def _build_wan22_cost_resolution_row(
    *,
    selected_resolution: str,
    selected_duration: int,
    lang: str,
    credits_text: str,
    callback_prefix: str,
    selected_prefix: str = "✅ ",
) -> list[InlineKeyboardButton]:
    buttons = []
    for preset_key in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        label = get_wan22_video_v2_resolution_label(preset_key, lang=lang)
        cost_for_preset = get_wan22_video_v2_cost(preset_key, selected_duration)
        text = f"{label} ({cost_for_preset}{credits_text})"
        if preset_key == selected_resolution:
            text = f"{selected_prefix}{text}"
        buttons.append(
            InlineKeyboardButton(text, callback_data=f"{callback_prefix}{preset_key}")
        )
    return buttons


def _build_wan22_duration_row(
    *,
    selected_duration: int,
    lang: str,
    callback_prefix: str,
    selected_prefix: str = "✅ ",
) -> list[InlineKeyboardButton]:
    buttons = []
    for duration_seconds in WAN22_VIDEO_V2_DURATION_SECONDS:
        label = get_wan22_video_v2_duration_label(duration_seconds, lang=lang)
        multiplier_label = get_wan22_video_v2_duration_multiplier_label(
            duration_seconds
        )
        text = f"{label} ({multiplier_label})"
        if duration_seconds == selected_duration:
            text = f"{selected_prefix}{text}"
        buttons.append(
            InlineKeyboardButton(
                text,
                callback_data=f"{callback_prefix}{duration_seconds}",
            )
        )
    return buttons


def build_image_to_video_initial_setup_view(
    fsm_data: dict[str, object],
    *,
    lang: str,
    translate_func: TranslateFunc,
    from_compat_alias: bool,
    lora_buttons_per_row: int = 4,
) -> AdvancedVideoSettingsView:
    selected_lora = str(fsm_data.get("lora_name") or "")
    allow_lora_selection = bool(fsm_data.get("allow_lora_selection", True))
    selected_resolution, selected_duration = normalize_wan22_view_settings(
        fsm_data,
        resolution_key="resolution",
    )
    use_end_frame = bool(fsm_data.get("use_end_frame"))
    credits_text = translate_func("app.credits")

    lora_options: Iterable[str] = (
        VIDEO_LORA_MODELS.keys() if allow_lora_selection else ("",)
    )
    lora_buttons = [
        InlineKeyboardButton(
            selected_button_label(
                get_video_lora_display_name(backend_name, lang),
                selected=backend_name == selected_lora,
            ),
            callback_data=f"i2v_setup_lora_{backend_name}",
        )
        for backend_name in lora_options
    ]
    mode_row = [
        InlineKeyboardButton(
            selected_button_label(
                translate_func("fsm.image_to_video.disable_end_frame"),
                selected=not use_end_frame,
            ),
            callback_data="i2v_setup_mode_single",
        ),
        InlineKeyboardButton(
            selected_button_label(
                translate_func("fsm.image_to_video.enable_end_frame"),
                selected=use_end_frame,
            ),
            callback_data="i2v_setup_mode_end",
        ),
    ]
    reply_markup = InlineKeyboardMarkup(
        [
            *chunk_buttons(lora_buttons, lora_buttons_per_row),
            mode_row,
            _build_wan22_cost_resolution_row(
                selected_resolution=selected_resolution,
                selected_duration=selected_duration,
                lang=lang,
                credits_text=credits_text,
                callback_prefix="i2v_setup_res_",
            ),
            _build_wan22_duration_row(
                selected_duration=selected_duration,
                lang=lang,
                callback_prefix="i2v_setup_dur_",
            ),
        ]
    )
    header_key = (
        "fsm.image_to_video.compat_mode_header"
        if from_compat_alias
        else "fsm.image_to_video.mode_header"
    )
    cost = get_wan22_video_v2_cost(selected_resolution, selected_duration)
    message_text = translate_func(
        "fsm.image_to_video.setup_text",
        header=translate_func(header_key),
        model_name=get_video_lora_display_name(selected_lora, lang),
        frame_mode=translate_func(
            "fsm.image_to_video.frame_mode_end"
            if use_end_frame
            else "fsm.image_to_video.frame_mode_single"
        ),
        image_count=2 if use_end_frame else 1,
        resolution=get_wan22_video_v2_resolution_display(
            selected_resolution, lang=lang
        ),
        duration=get_wan22_video_v2_duration_label(selected_duration, lang=lang),
        cost=cost,
    )
    return AdvancedVideoSettingsView(
        reply_markup=reply_markup,
        message_text=message_text,
        cost=cost,
        resolution=selected_resolution,
        duration=selected_duration,
    )


def build_image_to_video_settings_view(
    fsm_data: dict[str, object],
    *,
    lang: str,
    translate_func: TranslateFunc,
) -> AdvancedVideoSettingsView:
    resolution, duration = normalize_wan22_view_settings(
        fsm_data,
        resolution_key="resolution",
    )
    cost = get_wan22_video_v2_cost(resolution, duration)
    reply_markup = InlineKeyboardMarkup(
        [
            _build_wan22_cost_resolution_row(
                selected_resolution=resolution,
                selected_duration=duration,
                lang=lang,
                credits_text=translate_func("app.credits"),
                callback_prefix="set_res_",
            ),
            _build_wan22_duration_row(
                selected_duration=duration,
                lang=lang,
                callback_prefix="set_dur_",
            ),
        ]
    )
    message_text = translate_func(
        "fsm.image_to_video.settings_text",
        resolution=get_wan22_video_v2_resolution_display(resolution, lang=lang),
        duration=get_wan22_video_v2_duration_label(duration, lang=lang),
        cost=cost,
        model_name=get_video_lora_display_name(
            str(fsm_data.get("lora_name") or ""), lang
        ),
    )
    return AdvancedVideoSettingsView(
        reply_markup=reply_markup,
        message_text=message_text,
        cost=cost,
        resolution=resolution,
        duration=duration,
    )


def build_wan22_initial_setup_view(
    data: dict[str, object],
    *,
    lang: str,
    translate_func: TranslateFunc,
) -> AdvancedVideoSettingsView:
    resolution, duration = normalize_wan22_view_settings(
        data,
        resolution_key="resolution_preset",
    )
    use_end_frame = bool(data.get("use_end_frame"))
    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    selected_button_label(
                        translate_func("fsm.wan22_video_v2.disable_end_frame"),
                        selected=not use_end_frame,
                    ),
                    callback_data="wan22v2_setup_mode_single",
                ),
                InlineKeyboardButton(
                    selected_button_label(
                        translate_func("fsm.wan22_video_v2.enable_end_frame"),
                        selected=use_end_frame,
                    ),
                    callback_data="wan22v2_setup_mode_end",
                ),
            ],
            _build_wan22_cost_resolution_row(
                selected_resolution=resolution,
                selected_duration=duration,
                lang=lang,
                credits_text=translate_func("app.credits"),
                callback_prefix="wan22v2_setup_res_",
            ),
            _build_wan22_duration_row(
                selected_duration=duration,
                lang=lang,
                callback_prefix="wan22v2_setup_dur_",
            ),
        ]
    )
    cost = get_wan22_video_v2_cost(resolution, duration)
    message_text = translate_func(
        "fsm.wan22_video_v2.setup_text",
        frame_mode=translate_func(
            "fsm.wan22_video_v2.frame_mode_end"
            if use_end_frame
            else "fsm.wan22_video_v2.frame_mode_single"
        ),
        image_count=2 if use_end_frame else 1,
        resolution=get_wan22_video_v2_resolution_display(resolution, lang=lang),
        duration=get_wan22_video_v2_duration_label(duration, lang=lang),
        cost=cost,
    )
    return AdvancedVideoSettingsView(
        reply_markup=reply_markup,
        message_text=message_text,
        cost=cost,
        resolution=resolution,
        duration=duration,
    )


def build_wan22_settings_view(
    data: dict[str, object],
    *,
    lang: str,
    translate_func: TranslateFunc,
    is_legacy_context: bool,
) -> AdvancedVideoSettingsView:
    resolution, duration = normalize_wan22_view_settings(
        data,
        resolution_key="resolution_preset",
    )
    resolution_buttons = []
    for preset_key in WAN22_VIDEO_V2_RESOLUTION_PRESETS:
        label = get_wan22_video_v2_resolution_label(preset_key, lang=lang)
        if resolution == preset_key:
            label = f"• {label}"
        resolution_buttons.append(
            InlineKeyboardButton(label, callback_data=f"wan22v2_res_{preset_key}")
        )
    duration_buttons = []
    for duration_seconds in WAN22_VIDEO_V2_DURATION_SECONDS:
        label = get_wan22_video_v2_duration_label(duration_seconds, lang=lang)
        multiplier_label = get_wan22_video_v2_duration_multiplier_label(
            duration_seconds
        )
        label = f"{label} ({multiplier_label})"
        if duration == duration_seconds:
            label = f"• {label}"
        duration_buttons.append(
            InlineKeyboardButton(label, callback_data=f"wan22v2_dur_{duration_seconds}")
        )
    reply_markup = InlineKeyboardMarkup(
        [
            resolution_buttons,
            duration_buttons,
            [
                InlineKeyboardButton(
                    translate_func("fsm.wan22_video_v2.submit_button"),
                    callback_data="wan22v2_submit",
                )
            ],
        ]
    )
    cost = get_wan22_video_v2_cost(resolution, duration)
    status_yes = translate_func("fsm.wan22_video_v2.status_yes")
    status_no = translate_func("fsm.wan22_video_v2.status_no")
    negative_prompt = str(data.get("negative_prompt") or "").strip()
    settings_key = (
        "fsm.wan22_video_v2.legacy_settings_text"
        if is_legacy_context
        else "fsm.wan22_video_v2.settings_text"
    )
    message_text = translate_func(
        settings_key,
        use_end_frame=status_yes if data.get("use_end_frame") else status_no,
        end_frame_ready=(
            status_yes
            if (not data.get("use_end_frame") or data.get("end_image_path"))
            else status_no
        ),
        prompt=str(data.get("prompt") or "").strip() or "-",
        negative_prompt=negative_prompt
        or ("Default negative prompt" if lang == "en" else "默认负面提示词"),
        resolution_preset=get_wan22_video_v2_resolution_display(
            resolution,
            lang=lang,
        ),
        duration=get_wan22_video_v2_duration_label(duration, lang=lang),
        cost=cost,
    )
    return AdvancedVideoSettingsView(
        reply_markup=reply_markup,
        message_text=message_text,
        cost=cost,
        resolution=resolution,
        duration=duration,
    )


def build_ltx_lora_summary_text(
    lora_items: list[dict[str, Any]],
    *,
    lang: str,
    translate_func: TranslateFunc,
    empty_key: str | None = None,
) -> str:
    if not lora_items:
        empty_name = get_ltx_video_lora_display_name("", lang)
        if empty_key:
            return translate_func(empty_key, model_name=empty_name)
        return f"当前附加模型: {empty_name}"

    display_items = ", ".join(
        f"{get_ltx_video_lora_display_name(str(item['name']), lang)}({float(item['strength']):.2f})"
        for item in lora_items
    )
    return f"当前附加模型: {display_items}"


def _ltx_mode_label(mode: str, lang: str = "zh") -> str:
    if lang == "en":
        return {
            "flf2v": "Start/end frames",
            "v2v_audio": "Video audio",
        }.get(mode, "Single start frame")
    return {
        "flf2v": "首尾帧",
        "v2v_audio": "视频配音",
    }.get(mode, "单首帧")


def _ltx_setup_mode_label(
    mode: str,
    lang: str,
    *,
    is_extension: bool,
) -> str:
    if not is_extension:
        return _ltx_mode_label(mode, lang)
    if lang == "en":
        return {"flf2v": "Add end frame"}.get(mode, "Direct continuation")
    return {"flf2v": "添加终止帧"}.get(mode, "直接续写")


def build_ltx_initial_setup_view(
    fsm_data: dict[str, object],
    *,
    lang: str,
    translate_func: TranslateFunc,
    lora_items: list[dict[str, Any]],
) -> AdvancedVideoSettingsView:
    current_mode = str(fsm_data.get("ltx_mode") or "i2v")
    is_extension = bool(fsm_data.get("is_extension"))
    resolution = str(fsm_data.get("resolution") or "1280x704")
    duration = str(fsm_data.get("duration") or "5s")
    mode_row = [
        InlineKeyboardButton(
            f"{'✅ ' if current_mode == 'i2v' else ''}{_ltx_setup_mode_label('i2v', lang, is_extension=is_extension)}",
            callback_data="ltx_mode_i2v",
        ),
        InlineKeyboardButton(
            f"{'✅ ' if current_mode == 'flf2v' else ''}{_ltx_setup_mode_label('flf2v', lang, is_extension=is_extension)}",
            callback_data="ltx_mode_flf2v",
        ),
    ]
    settings_markup = get_ltx_video_settings_keyboard(
        "default",
        "外门弟子",
        resolution,
        duration,
        lang,
    )
    keyboard = [mode_row]
    keyboard.extend([list(row) for row in settings_markup.inline_keyboard])
    multiplier = LTX_DURATION_MULTIPLIER.get(duration, 1.0)
    cost = int(LTX_RESOLUTION_COST.get(resolution, 10) * multiplier)
    mode_label = _ltx_setup_mode_label(
        current_mode,
        lang,
        is_extension=is_extension,
    )
    lora_text = build_ltx_lora_summary_text(
        lora_items,
        lang=lang,
        translate_func=translate_func,
        empty_key="fsm.image_to_video.current_lora",
    )
    if is_extension and lang == "en":
        setup_text = (
            "Loaded the previous segment's last frame as the new start frame.\n"
            "Adjust quality and duration if needed.\n"
            f"Mode: {mode_label}\n"
            f"Quality: {resolution} | Duration: {duration} | Cost: {cost}\n\n"
            "Send a text prompt to continue directly, or send an image to use it "
            "as this segment's end frame."
        )
    elif is_extension:
        setup_text = (
            "已载入上一段尾帧作为新的起始帧。\n"
            "可按需调整清晰度和时长。\n"
            f"方式：{mode_label}\n"
            f"清晰度：{resolution} | 时长：{duration} | 消耗灵石：{cost}\n\n"
            "直接发送提示词即可续写；如需添加终止帧，直接发送终止帧图片即可。"
        )
    elif lang == "en":
        setup_text = (
            "Choose mode, quality and duration first.\n"
            f"Mode: {mode_label}\n"
            f"Quality: {resolution} | Duration: {duration} | Cost: {cost}\n\n"
            "Send the start-frame image to confirm these settings and continue.\n"
            "In start/end mode, send the end-frame image after the start frame."
        )
    else:
        setup_text = (
            "请先选择生成模式、清晰度和时长。\n"
            f"模式：{mode_label}\n"
            f"清晰度：{resolution} | 时长：{duration} | 消耗灵石：{cost}\n\n"
            "请直接发送起始帧图片，发送后即确认当前设置并进入下一步。\n"
            "首尾帧模式下，收到起始帧后还会继续要求发送终止帧。"
        )
    return AdvancedVideoSettingsView(
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_text=f"{lora_text}\n\n{setup_text}",
        cost=cost,
        resolution=resolution,
        duration=duration,
    )


def build_ltx_prompt_settings_view(
    fsm_data: dict[str, object],
    *,
    lang: str,
    translate_func: TranslateFunc,
    user_group: str,
    user_identity: str,
    lora_items: list[dict[str, Any]],
) -> AdvancedVideoSettingsView:
    resolution = str(fsm_data.get("resolution") or "1280x704")
    duration = str(fsm_data.get("duration") or "5s")
    reply_markup = get_ltx_video_settings_keyboard(
        user_group,
        user_identity,
        resolution,
        duration,
        lang,
    )
    cost = int(
        LTX_RESOLUTION_COST.get(resolution, 10)
        * LTX_DURATION_MULTIPLIER.get(duration, 1.0)
    )
    message = translate_func(
        "fsm.ltx_video.settings_text_english_prompt",
        resolution=resolution,
        duration=duration,
        cost=cost,
    )
    lora_text = build_ltx_lora_summary_text(
        lora_items,
        lang=lang,
        translate_func=translate_func,
        empty_key="fsm.image_to_video.current_lora",
    )
    return AdvancedVideoSettingsView(
        reply_markup=reply_markup,
        message_text=f"{message}\n\n{lora_text}",
        cost=cost,
        resolution=resolution,
        duration=duration,
    )
