from __future__ import annotations

import logging
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from src.domain_config.minimax_h3 import get_minimax_h3_cost
from src.domain_config.task_type_registry import is_gallery_supported_task_type
from src.filters.i18n_filter import I18nFilter
from src.handlers.conversation_states import AdvancedVideoProState
from src.handlers.fsm.fsm_shared import (
    handle_standard_fsm_cancel,
    handle_standard_fsm_timeout,
    handle_standard_fsm_unexpected_input,
    translate_fsm_text,
)
from src.handlers.prompt_router import is_global_menu_command
from src.services.advanced_video_pro_submission_service import (
    AdvancedVideoProSubmissionError,
    MODE_TASK_TYPES,
    build_advanced_video_pro_submission_plan,
    submit_advanced_video_pro_plan,
    validate_advanced_video_pro_frame_aspects,
)
from src.services.advanced_video_entry_policy import minimax_h3_ref2v_enabled
from src.services.feature_entry_visibility_service import (
    load_advanced_video_pro_profiles,
)
from src.services.fsm_temp_file_service import (
    cleanup_fsm_user_data,
    download_telegram_file_to_fsm_temp,
)
from src.services.permission_service import permission_service
from src.services.minimax_h3_extension_service import (
    MiniMaxH3ExtensionError,
    prepare_minimax_h3_extension_fsm_data,
)
from src.services.tg_task_result_presentation import (
    H3_EXTEND_CALLBACK_PREFIX,
    resolve_task_id_from_callback_data,
)
from src.utils import create_background_task, robust_edit_text, robust_reply_text

DATA_KEY = "advanced_video_pro_data"
TAG = "ADVANCED_VIDEO_PRO"
logger = logging.getLogger("fsm.advanced_video_pro")
MODES = ("t2v", "i2v", "flf2v", "ref2v")
DURATIONS = (5, 10, 15)
PRESETS = ("preview", "small", "standard", "hd")
ASPECTS = ("16:9", "9:16", "1:1", "4:3", "3:4")
PRESET_LABELS = {
    "preview": ("极速（约 512p）", "Fast (approx. 512p)"),
    "small": ("清晰（约 600p）", "Small (approx. 600p)"),
    "standard": ("标准（约 720p）", "Standard (approx. 720p)"),
    "hd": ("高清（约 810p）", "HD (approx. 810p)"),
}
CANCEL_HINT_ZH = "如果要切换功能，请发送 /cancel。"
CANCEL_HINT_EN = "To switch features, send /cancel."


def _lang(context) -> str:
    return "en" if getattr(context, "lang", "zh") == "en" else "zh"


def _text(context, zh: str, en: str) -> str:
    return en if _lang(context) == "en" else zh


def _with_cancel_hint(context, text: str) -> str:
    return f"{text.rstrip()}\n\n{_text(context, CANCEL_HINT_ZH, CANCEL_HINT_EN)}"


def _mode_keyboard(context) -> InlineKeyboardMarkup:
    labels = [
        ("t2v", "文生视频", "Text to Video"),
        ("i2v", "首帧图生视频", "First-frame Video"),
        ("flf2v", "首尾帧视频", "First/Last-frame Video"),
    ]
    if minimax_h3_ref2v_enabled():
        labels.append(("ref2v", "参考图生视频", "Reference-to-Video"))
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _text(context, zh, en), callback_data=f"avp_mode_{mode}"
                )
            ]
            for mode, zh, en in labels
        ]
    )


def _apply_runtime_profile(data: dict) -> None:
    profile = data.get("runtime_profiles", {}).get(data.get("mode"), {})
    data["main_model"] = str(profile.get("main_model") or "10eros_bf16")
    data["addon_items"] = [
        dict(item) for item in profile.get("addon_items", []) if isinstance(item, dict)
    ]


def _settings_keyboard(context, data: dict) -> InlineKeyboardMarkup:
    def buttons(prefix: str, values) -> list[InlineKeyboardButton]:
        return [
            InlineKeyboardButton(
                ("✅ " if str(data.get(prefix)) == str(value) else "") + str(value),
                callback_data=f"avp_{prefix}_{value}",
            )
            for value in values
        ]

    duration_buttons = [
        InlineKeyboardButton(
            ("✅ " if data.get("duration") == value else "")
            + _text(
                context,
                f"{value}秒 · {_settings_cost(data, duration=value)}灵石",
                f"{value}s · {_settings_cost(data, duration=value)} credits",
            ),
            callback_data=f"avp_duration_{value}",
        )
        for value in DURATIONS
    ]
    preset_buttons = [
        InlineKeyboardButton(
            ("✅ " if data.get("preset") == value else "")
            + _text(
                context,
                f"{PRESET_LABELS[value][0]} · {_settings_cost(data, preset=value)}灵石",
                f"{PRESET_LABELS[value][1]} · {_settings_cost(data, preset=value)} credits",
            ),
            callback_data=f"avp_preset_{value}",
        )
        for value in PRESETS
    ]
    rows = [duration_buttons, preset_buttons[:2], preset_buttons[2:]]
    if data.get("mode") not in {"i2v", "flf2v"}:
        rows.extend([buttons("aspect", ASPECTS[:3]), buttons("aspect", ASPECTS[3:])])
    if data.get("is_extension") and data.get("mode") == "ref2v":
        rows.append(
            [
                InlineKeyboardButton(
                    _text(context, "发送提示词", "Send prompt"),
                    callback_data="avp_settings_done",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


def _settings_cost(
    data: dict, *, duration: int | None = None, preset: str | None = None
) -> int:
    return get_minimax_h3_cost(
        MODE_TASK_TYPES[data["mode"]],
        duration=data["duration"] if duration is None else duration,
        resolution_preset=data["preset"] if preset is None else preset,
    )


def _settings_text(context, data: dict) -> str:
    aspect = (
        _text(context, "跟随首帧", "Follow first frame")
        if data.get("mode") in {"i2v", "flf2v"}
        else data["aspect"]
    )
    mode = data.get("mode")
    if data.get("is_extension") and mode == "ref2v":
        direct_action_zh = (
            "点击“发送提示词”后输入新提示词即可生成；也可直接发送 1–4 张参考图，"
            "继续原有的参考图、可选语音和提示词流程。"
        )
        direct_action_en = (
            "Tap Send prompt and enter a new prompt to generate, or send 1–4 "
            "reference images to continue through the existing image, optional "
            "voice, and prompt flow."
        )
    elif mode == "t2v":
        direct_action_zh = "直接发送提示词后立即生成，无需再次确认。"
        direct_action_en = (
            "Send the prompt to generate immediately; no confirmation is needed."
        )
    elif mode == "ref2v":
        direct_action_zh = (
            "发送 1–4 张参考图；完成参考图后可上传 1 个主角参考语音，再填写提示词生成。"
        )
        direct_action_en = (
            "Send 1–4 reference images. After finishing the images, you may upload "
            "one main-character voice reference before entering the prompt."
        )
    else:
        direct_action_zh = "无需确认设置；发送图片并填写提示词后立即生成。"
        direct_action_en = (
            "No settings confirmation is needed. Send the image and prompt to "
            "generate immediately."
        )
    cost = _settings_cost(data)
    return _with_cancel_hint(
        context,
        _text(
            context,
            f"🎬 *高级图生视频pro*\n\n请选择设置：\n时长：{data['duration']} 秒\n画质：{_text(context, *PRESET_LABELS[data['preset']])}\n比例：{aspect}\n预计消耗：{cost} 灵石\n\n{direct_action_zh}",
            f"🎬 *Advanced Image-to-Video Pro*\n\nChoose settings:\nDuration: {data['duration']}s\nQuality: {_text(context, *PRESET_LABELS[data['preset']])}\nAspect: {aspect}\nEstimated cost: {cost} credits\n\n{direct_action_en}",
        ),
    )


def _prompt_request_text(context, data: dict, *, media_received: bool = False) -> str:
    intro = _text(
        context,
        "图片已收到，请输入视频提示词。" if media_received else "请输入视频提示词。",
        "Image received. Send the video prompt."
        if media_received
        else "Send the video prompt.",
    )
    return _with_cancel_hint(context, intro)


def _extract_image(update: Update) -> tuple[str | None, str]:
    message = update.message
    if message and message.photo:
        return message.photo[-1].file_id, ".jpg"
    document = getattr(message, "document", None)
    if document and str(document.mime_type or "").startswith("image/"):
        return document.file_id, Path(
            document.file_name or "image.jpg"
        ).suffix or ".jpg"
    return None, ".jpg"


def _extract_audio(update: Update) -> tuple[str | None, str]:
    message = update.message
    voice = getattr(message, "voice", None)
    if voice:
        return voice.file_id, ".ogg"
    audio = getattr(message, "audio", None)
    if audio:
        return audio.file_id, Path(audio.file_name or "voice.m4a").suffix or ".m4a"
    document = getattr(message, "document", None)
    if document and str(document.mime_type or "").startswith("audio/"):
        return document.file_id, Path(
            document.file_name or "voice.m4a"
        ).suffix or ".m4a"
    return None, ".m4a"


def _reference_audio_request(context) -> tuple[str, InlineKeyboardMarkup]:
    return (
        _with_cancel_hint(
            context,
            _text(
                context,
                "可选：上传一段主角参考语音（仅 1 个文件），或点击跳过。",
                "Optional: upload one main-character voice reference, or skip.",
            ),
        ),
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        _text(context, "跳过参考语音", "Skip voice reference"),
                        callback_data="avp_audio_skip",
                    )
                ]
            ]
        ),
    )


def _clear(context, *, preserve_paths: bool = False) -> None:
    if preserve_paths:
        context.user_data.pop(DATA_KEY, None)
        context.user_data.pop("in_conversation", None)
    else:
        cleanup_fsm_user_data(context.user_data)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from src.utils import is_maintenance_mode

    if is_maintenance_mode() or context.user_data.get("in_conversation"):
        await robust_reply_text(
            update.effective_message,
            _text(
                context,
                "当前暂时无法开始新任务。",
                "A new task cannot be started right now.",
            ),
        )
        return ConversationHandler.END
    try:
        runtime_profiles = await load_advanced_video_pro_profiles()
    except Exception:
        logger.exception("Failed to load Advanced Video Pro runtime profiles")
        await robust_reply_text(
            update.effective_message,
            _text(
                context,
                "高级图生视频 Pro 配置暂时不可用，请稍后重试。",
                "Advanced Image-to-Video Pro settings are temporarily unavailable. Try again later.",
            ),
        )
        return ConversationHandler.END
    context.user_data["in_conversation"] = TAG
    context.user_data[DATA_KEY] = {
        "mode": None,
        "duration": 5,
        "preset": "preview",
        "aspect": "16:9",
        "images": [],
        "reference_descriptions": [],
        "reference_audio": None,
        "runtime_profiles": runtime_profiles,
    }
    await robust_reply_text(
        update.effective_message,
        _with_cancel_hint(
            context,
            _text(
                context,
                "🎬 *高级图生视频pro*\n\n请选择生成模式：",
                "🎬 *Advanced Image-to-Video Pro*\n\nChoose a generation mode:",
            ),
        ),
        reply_markup=_mode_keyboard(context),
        parse_mode="Markdown",
    )
    return AdvancedVideoProState.WAIT_SETTINGS


async def start_extension(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if context.user_data.get("in_conversation"):
        await robust_reply_text(
            query.message,
            _text(context, "请先结束当前操作。", "Finish the current action first."),
        )
        return ConversationHandler.END
    task_id = resolve_task_id_from_callback_data(
        query.data,
        H3_EXTEND_CALLBACK_PREFIX,
    )
    if not task_id:
        await robust_reply_text(
            query.message,
            _text(
                context,
                "记录已失效，请重新生成后再试。",
                "This record expired. Generate it again.",
            ),
        )
        return ConversationHandler.END
    try:
        runtime_profiles = await load_advanced_video_pro_profiles()
        seed = await prepare_minimax_h3_extension_fsm_data(
            prev_task_id=task_id,
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
        )
    except MiniMaxH3ExtensionError as exc:
        await robust_reply_text(query.message, f"❌ {exc}")
        return ConversationHandler.END
    except Exception:
        logger.exception("Failed to prepare H3 extension")
        await robust_reply_text(
            query.message,
            _text(
                context,
                "扩展参考加载失败，请稍后重试。",
                "Failed to load the extension reference. Try again later.",
            ),
        )
        return ConversationHandler.END
    data = seed.fsm_data
    data["runtime_profiles"] = runtime_profiles
    data["mode"] = "ref2v"
    data["images"] = []
    _apply_runtime_profile(data)
    context.user_data["in_conversation"] = TAG
    context.user_data[DATA_KEY] = data
    await robust_reply_text(
        query.message,
        (
            _text(
                context,
                "已载入上一段末尾约 5 秒作为视频参考。",
                "The final five seconds of the previous segment are loaded as a video reference.",
            )
            + "\n\n"
            + _settings_text(context, data)
        ),
        reply_markup=_settings_keyboard(context, data),
        parse_mode="Markdown",
    )
    return AdvancedVideoProState.WAIT_SETTINGS


async def extension_mode_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    requested_mode = str(query.data or "").removeprefix("h3ext_mode_")
    legacy_first_last = requested_mode == "flf2v"
    await query.answer(
        _text(
            context,
            "首尾帧续写已取消，已切换为视频参考续写。",
            "First/last-frame continuation is no longer available. Switched to video-reference continuation.",
        )
        if legacy_first_last
        else None,
        show_alert=legacy_first_last,
    )
    data = context.user_data.get(DATA_KEY)
    if not data or not data.get("is_extension"):
        return ConversationHandler.END
    if requested_mode not in {"ref2v", "flf2v"}:
        return AdvancedVideoProState.WAIT_SETTINGS
    mode = "ref2v"
    data["mode"] = mode
    data["images"] = []
    _apply_runtime_profile(data)
    guidance = _text(
        context,
        "可调整时长和画质，然后直接发送新提示词。",
        "Adjust duration and quality, then send a new prompt.",
    )
    await robust_edit_text(
        query.message,
        f"{_settings_text(context, data)}\n\n🔒 {guidance}",
        reply_markup=_settings_keyboard(context, data),
        parse_mode="Markdown",
    )
    return AdvancedVideoProState.WAIT_SETTINGS


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.get(DATA_KEY)
    if not data:
        await query.answer(
            _text(
                context,
                "操作已过期，请重新进入。",
                "This action expired. Please reopen it.",
            ),
            show_alert=True,
        )
        return ConversationHandler.END
    value = str(query.data or "")
    if value.startswith("avp_mode_"):
        mode = value.removeprefix("avp_mode_")
        if mode in MODES and (mode != "ref2v" or minimax_h3_ref2v_enabled()):
            data["mode"] = mode
            _apply_runtime_profile(data)
    elif value.startswith("avp_duration_"):
        duration = int(value.removeprefix("avp_duration_"))
        if duration in DURATIONS:
            data["duration"] = duration
    elif value.startswith("avp_preset_"):
        preset = value.removeprefix("avp_preset_")
        if preset in PRESETS:
            data["preset"] = preset
    elif value.startswith("avp_aspect_"):
        aspect = value.removeprefix("avp_aspect_")
        if aspect in ASPECTS:
            data["aspect"] = aspect
    elif value == "avp_settings_done" and data.get("mode"):
        mode = data["mode"]
        if mode == "t2v" or (data.get("is_extension") and mode == "ref2v"):
            await robust_edit_text(query.message, _prompt_request_text(context, data))
            return AdvancedVideoProState.WAIT_PROMPT
        await robust_edit_text(
            query.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "请上传第一张参考图片。",
                    "Upload the first reference image.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    await robust_edit_text(
        query.message,
        _settings_text(context, data),
        reply_markup=_settings_keyboard(context, data),
        parse_mode="Markdown",
    )
    return AdvancedVideoProState.WAIT_SETTINGS


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data.get(DATA_KEY)
    if not data:
        return ConversationHandler.END
    if data.get("mode") not in {"i2v", "flf2v", "ref2v"}:
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "请先选择图生视频模式。",
                    "Choose an image-to-video mode first.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_SETTINGS
    file_id, suffix = _extract_image(update)
    if not file_id:
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(context, "请上传有效图片。", "Upload a valid image."),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    telegram_file = await context.bot.get_file(file_id)
    path = await download_telegram_file_to_fsm_temp(
        telegram_file=telegram_file, suffix=suffix, name_hint="advanced_video_pro"
    )
    data["images"].append(path)
    mode = data["mode"]
    if mode == "flf2v" and len(data["images"]) < 2:
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "起始帧已收到，请上传终止帧。",
                    "Start frame received. Upload the end frame.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    if mode == "flf2v":
        try:
            validate_advanced_video_pro_frame_aspects(data["images"])
        except AdvancedVideoProSubmissionError as exc:
            data["images"].pop()
            Path(path).unlink(missing_ok=True)
            await robust_reply_text(
                update.message, _with_cancel_hint(context, str(exc))
            )
            return AdvancedVideoProState.WAIT_MEDIA
    if mode == "ref2v":
        count = len(data["images"])
        if count >= 4:
            text, keyboard = _reference_audio_request(context)
            await robust_reply_text(update.message, text, reply_markup=keyboard)
            return AdvancedVideoProState.WAIT_REFERENCE_AUDIO
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        _text(context, "继续添加参考图", "Add another reference"),
                        callback_data="avp_refs_more",
                    )
                ],
                [
                    InlineKeyboardButton(
                        _text(
                            context,
                            "完成参考图，下一步添加语音",
                            "Finish images, add voice next",
                        ),
                        callback_data="avp_refs_done",
                    )
                ],
            ]
        )
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    f"已收到 {count} 张参考图。可继续添加，最多 4 张。完成选图后进入可选参考语音步骤。",
                    f"Received {count} reference image(s). You may add up to 4. Finish the images to continue to the optional voice-reference step.",
                ),
            ),
            reply_markup=keyboard,
        )
        return AdvancedVideoProState.WAIT_REFERENCE_DESCRIPTION
    await robust_reply_text(
        update.message, _prompt_request_text(context, data, media_received=True)
    )
    return AdvancedVideoProState.WAIT_PROMPT


async def receive_reference_description(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = context.user_data.get(DATA_KEY)
    description = str(update.message.text or "").strip()
    if not data or not description:
        return AdvancedVideoProState.WAIT_REFERENCE_DESCRIPTION
    data["reference_descriptions"].append(description)
    count = len(data["images"])
    rows = [
        [
            InlineKeyboardButton(
                _text(
                    context,
                    "完成参考图，下一步添加语音",
                    "Finish images, add voice next",
                ),
                callback_data="avp_refs_done",
            )
        ]
    ]
    if count < 4:
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    _text(context, "继续添加角色", "Add another character"),
                    callback_data="avp_refs_more",
                )
            ],
        )
    keyboard = InlineKeyboardMarkup(rows)
    await robust_reply_text(
        update.message,
        _with_cancel_hint(
            context,
            _text(
                context,
                f"已添加 {count} 个角色。完成后进入可选参考语音步骤。",
                f"{count} character(s) added. Finish to continue to the optional voice-reference step.",
            ),
        ),
        reply_markup=keyboard,
    )
    return AdvancedVideoProState.WAIT_REFERENCE_DESCRIPTION


async def reference_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.get(DATA_KEY)
    if not data:
        return ConversationHandler.END
    if query.data == "avp_refs_more" and len(data["images"]) < 4:
        await robust_edit_text(
            query.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "请上传下一张参考图。",
                    "Upload the next reference image.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    text, keyboard = _reference_audio_request(context)
    await robust_edit_text(query.message, text, reply_markup=keyboard)
    return AdvancedVideoProState.WAIT_REFERENCE_AUDIO


async def reference_audio_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.get(DATA_KEY)
    if not data:
        return ConversationHandler.END
    await robust_edit_text(query.message, _prompt_request_text(context, data))
    return AdvancedVideoProState.WAIT_PROMPT


async def receive_reference_audio(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = context.user_data.get(DATA_KEY)
    if not data or data.get("mode") != "ref2v":
        return ConversationHandler.END
    file_id, suffix = _extract_audio(update)
    if not file_id:
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "请上传有效音频，或点击跳过。",
                    "Upload valid audio, or skip.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_REFERENCE_AUDIO
    telegram_file = await context.bot.get_file(file_id)
    data["reference_audio"] = await download_telegram_file_to_fsm_temp(
        telegram_file=telegram_file,
        suffix=suffix,
        name_hint="advanced_video_pro_voice",
    )
    await robust_reply_text(
        update.message,
        _with_cancel_hint(
            context,
            _text(
                context,
                "主角参考语音已添加。建议在提示词中包含 <Audio 1> 来说明该语音的用途（可选，不影响提交）。\n\n请输入视频提示词。",
                "Main-character voice reference added. Consider including <Audio 1> in the prompt to describe its role (optional; submission is not blocked).\n\nSend the video prompt.",
            ),
        ),
    )
    return AdvancedVideoProState.WAIT_PROMPT


async def _submit_generation(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict
) -> int:
    message = update.effective_message
    prompt = str(data.get("prompt") or "").strip()
    try:
        plan = build_advanced_video_pro_submission_plan(
            mode=data["mode"],
            prompt=prompt,
            images=data["images"],
            reference_descriptions=data["reference_descriptions"],
            reference_video=data.get("reference_video"),
            reference_audio=data.get("reference_audio"),
            duration=data["duration"],
            resolution_preset=data["preset"],
            aspect_ratio=(
                "source" if data["mode"] in {"i2v", "flf2v"} else data["aspect"]
            ),
            main_model=data.get("main_model", "10eros_bf16"),
            addon_items=list(data.get("addon_items", [])),
        )
    except AdvancedVideoProSubmissionError as exc:
        await robust_reply_text(message, _with_cancel_hint(context, str(exc)))
        return AdvancedVideoProState.WAIT_PROMPT
    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id,
            user.username,
            user.full_name,
            cost=plan.cost,
            task_type=plan.task_type,
            client_type=(getattr(context, "bot_data", None) or {}).get(
                "bot_client_type", "bot"
            ),
        )
    except Exception as exc:
        from src.core.exceptions import InsufficientCreditsError

        if isinstance(exc, InsufficientCreditsError):
            await robust_reply_text(
                message,
                _text(
                    context,
                    f"余额不足，需要 {plan.cost} 点。",
                    f"Insufficient balance. {plan.cost} credits required.",
                ),
            )
            _clear(context)
            return ConversationHandler.END
        raise
    await robust_reply_text(
        message,
        _text(
            context,
            f"任务已提交，预计消耗 {plan.cost} 点。",
            f"Task submitted. Estimated cost: {plan.cost} credits.",
        ),
    )
    create_background_task(
        context,
        submit_advanced_video_pro_plan(
            plan,
            context=context,
            chat_id=update.effective_chat.id,
            user_id=user.id,
            username=user.username,
            cleanup=True,
            allow_contribute=(
                bool(data.get("extension_allow_contribute"))
                if data.get("is_extension")
                else is_gallery_supported_task_type(plan.task_type)
            ),
            result_meta=(
                {
                    "minimax_h3_prev_task_id": data.get("extension_prev_task_id"),
                    "minimax_h3_chain_task_ids": list(
                        data.get("minimax_h3_chain_task_ids") or []
                    ),
                }
                if data.get("is_extension")
                else None
            ),
        ),
    )
    _clear(context, preserve_paths=True)
    return ConversationHandler.END


async def receive_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if is_global_menu_command(update.message.text or ""):
        return await cancel(update, context)
    data = context.user_data.get(DATA_KEY)
    prompt = str(update.message.text or "").strip()
    if not data or not prompt:
        return AdvancedVideoProState.WAIT_PROMPT
    data["prompt"] = prompt
    return await _submit_generation(update, context, data)


async def receive_settings_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = context.user_data.get(DATA_KEY)
    if not data or (
        data.get("mode") != "t2v"
        and not (data.get("is_extension") and data.get("mode") == "ref2v")
    ):
        await robust_reply_text(
            update.effective_message,
            _with_cancel_hint(
                context,
                _text(context, "请直接发送图片。", "Send the image directly."),
            ),
        )
        return AdvancedVideoProState.WAIT_SETTINGS
    return await receive_prompt(update, context)


async def legacy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer(
        _text(
            context,
            "旧设置已失效，请重新进入高级图生视频pro。",
            "Old settings expired. Reopen Advanced Image-to-Video Pro.",
        ),
        show_alert=True,
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_standard_fsm_cancel(
        update,
        context,
        cleanup_func=lambda: _clear(context),
        translate_func=translate_fsm_text,
        reply_text_func=robust_reply_text,
    )


async def timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_standard_fsm_timeout(
        update,
        context,
        cleanup_func=lambda: _clear(context),
        translate_func=translate_fsm_text,
        reply_text_func=robust_reply_text,
    )


async def unexpected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await handle_standard_fsm_unexpected_input(
        update,
        context,
        cleanup_func=lambda: _clear(context),
        translate_func=translate_fsm_text,
        reply_text_func=robust_reply_text,
    )


def get_advanced_video_pro_fsm_handler(
    *, include_ltx_compatibility_routes: bool = True
) -> ConversationHandler:
    legacy_pattern = r"^(ltx_mode_|set_ltx|ltx_setup_confirm|toggle_ltx_lora_|done_ltx_lora|clear_ltx_lora|skip_ltx_lora)"
    entry_points = [
        CommandHandler("advanced_video_pro", start),
        MessageHandler(I18nFilter("menu.advanced_video_pro"), start),
        CallbackQueryHandler(legacy_callback, pattern=r"^avp_prompt_"),
        CallbackQueryHandler(
            start_extension,
            pattern=rf"^{H3_EXTEND_CALLBACK_PREFIX}(?::.+)?$",
        ),
    ]
    if include_ltx_compatibility_routes:
        entry_points.extend(
            [
                CommandHandler("ltx_video", start),
                CallbackQueryHandler(start, pattern=r"^fsm_start_ltx_video$"),
                CallbackQueryHandler(legacy_callback, pattern=legacy_pattern),
            ]
        )
    return ConversationHandler(
        entry_points=entry_points,
        states={
            AdvancedVideoProState.WAIT_SETTINGS: [
                CallbackQueryHandler(extension_mode_callback, pattern=r"^h3ext_mode_"),
                CallbackQueryHandler(settings_callback, pattern=r"^avp_"),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE,
                    receive_image,
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_settings_prompt,
                ),
            ],
            AdvancedVideoProState.WAIT_MEDIA: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image)
            ],
            AdvancedVideoProState.WAIT_REFERENCE_DESCRIPTION: [
                CallbackQueryHandler(reference_callback, pattern=r"^avp_refs_"),
            ],
            AdvancedVideoProState.WAIT_REFERENCE_AUDIO: [
                CallbackQueryHandler(
                    reference_audio_callback, pattern=r"^avp_audio_skip$"
                ),
                MessageHandler(
                    filters.VOICE | filters.AUDIO | filters.Document.AUDIO,
                    receive_reference_audio,
                ),
            ],
            AdvancedVideoProState.WAIT_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt)
            ],
            ConversationHandler.TIMEOUT: [TypeHandler(Update, timeout)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.ALL, unexpected),
        ],
        conversation_timeout=300,
        name="advanced_video_pro_fsm",
        persistent=False,
    )
