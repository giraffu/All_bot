from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import subprocess

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

from src.domain_config.minimax_h3 import (
    MINIMAX_H3_REFERENCE_VIDEO_ALLOWED_DURATIONS,
    MINIMAX_H3_REFERENCE_VIDEO_DEFAULT_DURATION_SECONDS,
    MINIMAX_H3_REFERENCE_VIDEO_MAX_BYTES,
    MINIMAX_H3_REFERENCE_VIDEO_MAX_DURATION_SECONDS,
    get_minimax_h3_cost,
)
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
from src.services.task_pricing_config_service import resolve_runtime_task_cost
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
REFERENCE_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm"}
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
    uses_source_aspect = data.get("mode") in {"i2v", "flf2v"} or (
        data.get("is_extension") and data.get("mode") == "ref2v"
    )
    if not uses_source_aspect:
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
        reference_audio=bool(data.get("reference_audio")),
        reference_video=bool(data.get("reference_video")),
        reference_video_duration=data.get("reference_video_duration"),
    )


async def _resolve_reference_cost(data: dict) -> int:
    default_cost = _settings_cost(data)
    cost = await resolve_runtime_task_cost(
        task_type=MODE_TASK_TYPES[data["mode"]],
        inputs={
            "duration": data["duration"],
            "resolution_preset": data["preset"],
            "reference_audio": data.get("reference_audio"),
            "reference_video": data.get("reference_video"),
            "reference_video_duration": data.get("reference_video_duration"),
        },
        client_type="bot",
        default_cost=default_cost,
    )
    data["runtime_cost"] = cost
    return cost


def _settings_text(context, data: dict) -> str:
    uses_source_aspect = data.get("mode") in {"i2v", "flf2v"} or (
        data.get("is_extension") and data.get("mode") == "ref2v"
    )
    aspect = (
        _text(context, "跟随首帧", "Follow first frame")
        if uses_source_aspect
        else data["aspect"]
    )
    mode = data.get("mode")
    if data.get("is_extension") and mode == "ref2v":
        direct_action_zh = (
            "上一段尾帧已锁定为新视频起始帧；点击“发送提示词”后输入新提示词即可生成。"
        )
        direct_action_en = (
            "The previous tail frame is locked as the new video's first frame. "
            "Tap Send prompt and enter a new prompt to generate."
        )
    elif mode == "t2v":
        direct_action_zh = "直接发送提示词后立即生成，无需再次确认。"
        direct_action_en = (
            "Send the prompt to generate immediately; no confirmation is needed."
        )
    elif mode == "ref2v":
        direct_action_zh = (
            "参考模式会自动识别素材：可发送 1–4 张图片、1 段音频、1 段视频；"
            "至少需要图片或视频。默认定价：图片按基础价，音频 ×1.10；视频按开头 "
            "3/5/10/15 秒分别 ×1.40/1.60/2.20/2.80，组合使用时连乘并向上取整。"
        )
        direct_action_en = (
            "Reference mode auto-detects media: send 1–4 images, one audio file, "
            "and one video; at least an image or video is required. Images use the "
            "default base price, audio is ×1.10, and a 3/5/10/15s video clip is "
            "×1.40/1.60/2.20/2.80. Combined multipliers are rounded up."
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


def _extract_video(update: Update) -> tuple[str | None, str, int | None, float | None]:
    message = update.message
    video = getattr(message, "video", None)
    if video:
        return video.file_id, ".mp4", video.file_size, video.duration
    document = getattr(message, "document", None)
    if document and str(document.mime_type or "").startswith("video/"):
        suffix = Path(document.file_name or "").suffix.lower()
        return (
            document.file_id,
            suffix if suffix in REFERENCE_VIDEO_SUFFIXES else ".mp4",
            document.file_size,
            None,
        )
    return None, ".mp4", None, None


def _probe_reference_video_duration(path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError("ffprobe failed")
    return float(json.loads(result.stdout.decode("utf-8"))["format"]["duration"])


def _reference_keyboard(context, data: dict) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    allowed_durations = tuple(data.get("reference_video_allowed_durations") or ())
    if data.get("reference_video") and allowed_durations:
        selected = data.get("reference_video_duration")
        rows.append(
            [
                InlineKeyboardButton(
                    ("✅ " if selected == duration else "")
                    + _text(
                        context,
                        f"视频开头 {duration} 秒",
                        f"First {duration}s of video",
                    ),
                    callback_data=f"avp_refvideo_duration_{duration}",
                )
                for duration in allowed_durations
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                _text(
                    context,
                    "完成参考内容，填写提示词",
                    "Finish references and enter prompt",
                ),
                callback_data="avp_refs_done",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def _reference_prompt_guidance(context, data: dict) -> str:
    tags: list[str] = []
    image_count = len(data.get("images") or [])
    if image_count:
        picture_tags = (
            "<Picture 1>"
            if image_count == 1
            else f"<Picture 1>…<Picture {image_count}>"
        )
        tags.append(
            _text(
                context,
                f"{picture_tags} 描述对应人物、场景或风格",
                f"use {picture_tags} for the matching character, scene, or style",
            )
        )
    if data.get("reference_video"):
        tags.append(
            _text(
                context,
                "<Video 1> 描述动作或镜头参考",
                "use <Video 1> for motion or camera reference",
            )
        )
    if data.get("reference_audio"):
        tags.append(
            _text(
                context,
                "<Audio 1> 描述声音用途",
                "use <Audio 1> to describe the audio's role",
            )
        )
    if not tags:
        return ""
    return _text(context, "提示词中可用：", "In the prompt, ") + "；".join(tags) + "。"


async def _reference_progress_text(context, data: dict) -> str:
    cost = await _resolve_reference_cost(data)
    image_count = len(data.get("images") or [])
    audio_count = int(bool(data.get("reference_audio")))
    video_count = int(bool(data.get("reference_video")))
    video_selection = (
        _text(
            context,
            f" · 视频取开头 {data['reference_video_duration']} 秒",
            f" · first {data['reference_video_duration']}s of video",
        )
        if video_count
        else ""
    )
    guidance = _reference_prompt_guidance(context, data)
    return _with_cancel_hint(
        context,
        _text(
            context,
            f"已收到：图片 {image_count}/4 · 音频 {audio_count}/1 · 视频 {video_count}/1{video_selection}\n"
            f"当前预计：{cost} 灵石\n"
            f"还可发送：{4 - image_count} 张图片、{1 - audio_count} 段音频、{1 - video_count} 段视频\n"
            f"{guidance}\n继续发送参考内容，或点击下方按钮填写提示词。",
            f"Received: images {image_count}/4 · audio {audio_count}/1 · video {video_count}/1{video_selection}\n"
            f"Current estimate: {cost} credits\n"
            f"Remaining: {4 - image_count} image(s), {1 - audio_count} audio file, {1 - video_count} video\n"
            f"{guidance}\nSend more reference media, or use the button below to enter the prompt.",
        ),
    )


def _reference_mode_request_text(context) -> str:
    return _with_cancel_hint(
        context,
        _text(
            context,
            "已进入参考模式，请直接发送图片、音频或视频，系统会自动识别。"
            "图片最多 4 张，音频和视频各 1 段；至少需要图片或视频。",
            "Reference mode is ready. Send images, audio, or video and the bot will "
            "detect the type automatically. Up to four images and one audio/video "
            "file each are accepted; at least an image or video is required.",
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
        "reference_video": None,
        "reference_video_duration": None,
        "reference_video_allowed_durations": (),
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
    data["images"] = list(data.get("images") or [])
    _apply_runtime_profile(data)
    context.user_data["in_conversation"] = TAG
    context.user_data[DATA_KEY] = data
    await robust_reply_text(
        query.message,
        (
            _text(
                context,
                "已锁定上一段尾帧作为新视频起始帧。",
                "The previous segment's tail frame is locked as the new video's first frame.",
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
            "首尾帧续写已取消，已切换为尾帧锚定续写。",
            "First/last-frame continuation is no longer available. Switched to tail-frame anchored continuation.",
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
    data["images"] = [data["extension_start_frame"]]
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
        if mode == "ref2v":
            await robust_edit_text(query.message, _reference_mode_request_text(context))
            return AdvancedVideoProState.WAIT_MEDIA
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
    if data.get("is_extension") and data.get("mode") == "ref2v":
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "上一段尾帧已经作为起始帧，无需再上传参考图，请直接发送提示词。",
                    "The previous tail frame is already the first-frame anchor. Send the prompt directly; no additional reference image is needed.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_SETTINGS
    if data.get("mode") == "ref2v" and len(data.get("images") or []) >= 4:
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "参考图片已满 4 张，可继续发送音频或视频，或填写提示词。",
                    "All four reference-image slots are filled. Send audio/video or enter the prompt.",
                ),
            ),
            reply_markup=_reference_keyboard(context, data),
        )
        return AdvancedVideoProState.WAIT_MEDIA
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
        await robust_reply_text(
            update.message,
            await _reference_progress_text(context, data),
            reply_markup=_reference_keyboard(context, data),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    await robust_reply_text(
        update.message, _prompt_request_text(context, data, media_received=True)
    )
    return AdvancedVideoProState.WAIT_PROMPT


async def reference_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data.get(DATA_KEY)
    if not data:
        return ConversationHandler.END
    if query.data == "avp_refs_more":
        await robust_edit_text(
            query.message,
            _reference_mode_request_text(context),
            reply_markup=_reference_keyboard(context, data),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    if not data.get("images") and not data.get("reference_video"):
        await robust_edit_text(
            query.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "参考音频不能单独生成，请至少再发送 1 张图片或 1 段视频。",
                    "Audio cannot be the only reference. Send at least one image or one video.",
                ),
            ),
            reply_markup=_reference_keyboard(context, data),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    guidance = _reference_prompt_guidance(context, data)
    await robust_edit_text(
        query.message,
        _with_cancel_hint(
            context,
            _text(
                context,
                f"参考内容已就绪。{guidance}\n\n请输入视频提示词。",
                f"References are ready. {guidance}\n\nSend the video prompt.",
            ),
        ),
    )
    return AdvancedVideoProState.WAIT_PROMPT


async def receive_reference_audio(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = context.user_data.get(DATA_KEY)
    if not data:
        return ConversationHandler.END
    if data.get("mode") != "ref2v":
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "请先选择参考图生视频模式。",
                    "Choose Reference-to-Video mode first.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_SETTINGS
    if data.get("reference_audio"):
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "已收到 1 段参考音频，不能继续添加。",
                    "One reference audio file is already attached.",
                ),
            ),
            reply_markup=_reference_keyboard(context, data),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    file_id, suffix = _extract_audio(update)
    if not file_id:
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "请发送有效音频。",
                    "Send a valid audio file.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    telegram_file = await context.bot.get_file(file_id)
    data["reference_audio"] = await download_telegram_file_to_fsm_temp(
        telegram_file=telegram_file,
        suffix=suffix,
        name_hint="advanced_video_pro_voice",
    )
    await robust_reply_text(
        update.message,
        await _reference_progress_text(context, data),
        reply_markup=_reference_keyboard(context, data),
    )
    return AdvancedVideoProState.WAIT_MEDIA


async def receive_reference_video(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    data = context.user_data.get(DATA_KEY)
    if not data:
        return ConversationHandler.END
    if data.get("mode") != "ref2v":
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "请先选择参考图生视频模式。",
                    "Choose Reference-to-Video mode first.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_SETTINGS
    if data.get("reference_video"):
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "已收到 1 段参考视频，不能继续添加。",
                    "One reference video is already attached.",
                ),
            ),
            reply_markup=_reference_keyboard(context, data),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    file_id, suffix, file_size, telegram_duration = _extract_video(update)
    if not file_id:
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(context, "请发送有效视频。", "Send a valid video."),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    if file_size and file_size > MINIMAX_H3_REFERENCE_VIDEO_MAX_BYTES:
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "参考视频不能超过 40 MB。",
                    "Reference video must be at most 40 MB.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    if (
        telegram_duration
        and telegram_duration > MINIMAX_H3_REFERENCE_VIDEO_MAX_DURATION_SECONDS
    ):
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "参考视频不能超过 40 秒。",
                    "Reference video must be at most 40 seconds.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    if telegram_duration and telegram_duration < min(
        MINIMAX_H3_REFERENCE_VIDEO_ALLOWED_DURATIONS
    ):
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "参考视频至少需要 3 秒。",
                    "Reference video must be at least 3 seconds.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    path: str | None = None
    try:
        telegram_file = await context.bot.get_file(file_id)
        path = await download_telegram_file_to_fsm_temp(
            telegram_file=telegram_file,
            suffix=suffix,
            name_hint="advanced_video_pro_reference_video",
        )
        if Path(path).stat().st_size > MINIMAX_H3_REFERENCE_VIDEO_MAX_BYTES:
            raise ValueError("too_large")
        source_duration = float(telegram_duration or 0)
        if not source_duration:
            source_duration = await asyncio.to_thread(
                _probe_reference_video_duration, path
            )
        if source_duration > MINIMAX_H3_REFERENCE_VIDEO_MAX_DURATION_SECONDS:
            raise ValueError("too_long")
        allowed_durations = tuple(
            duration
            for duration in MINIMAX_H3_REFERENCE_VIDEO_ALLOWED_DURATIONS
            if duration <= source_duration
        )
        if not allowed_durations:
            raise ValueError("too_short")
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        if path:
            Path(path).unlink(missing_ok=True)
        logger.warning("Failed to prepare H3 reference video: %s", exc)
        await robust_reply_text(
            update.message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "无法读取该视频，请换一个文件。",
                    "Could not read that video. Try another file.",
                ),
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    except ValueError as exc:
        if path:
            Path(path).unlink(missing_ok=True)
        messages = {
            "too_large": (
                "参考视频不能超过 40 MB。",
                "Reference video must be at most 40 MB.",
            ),
            "too_long": (
                "参考视频不能超过 40 秒。",
                "Reference video must be at most 40 seconds.",
            ),
            "too_short": (
                "参考视频至少需要 3 秒。",
                "Reference video must be at least 3 seconds.",
            ),
        }
        zh, en = messages.get(
            str(exc), ("无法读取该视频。", "Could not read that video.")
        )
        await robust_reply_text(
            update.message,
            _with_cancel_hint(context, _text(context, zh, en)),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    data["reference_video"] = path
    data["reference_video_allowed_durations"] = allowed_durations
    data["reference_video_duration"] = (
        MINIMAX_H3_REFERENCE_VIDEO_DEFAULT_DURATION_SECONDS
        if MINIMAX_H3_REFERENCE_VIDEO_DEFAULT_DURATION_SECONDS in allowed_durations
        else allowed_durations[0]
    )
    await robust_reply_text(
        update.message,
        await _reference_progress_text(context, data),
        reply_markup=_reference_keyboard(context, data),
    )
    return AdvancedVideoProState.WAIT_MEDIA


async def reference_video_duration_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    data = context.user_data.get(DATA_KEY)
    if not data or not data.get("reference_video"):
        await query.answer()
        return ConversationHandler.END
    try:
        duration = int(str(query.data or "").removeprefix("avp_refvideo_duration_"))
    except ValueError:
        await query.answer()
        return AdvancedVideoProState.WAIT_MEDIA
    if duration not in tuple(data.get("reference_video_allowed_durations") or ()):
        await query.answer(
            _text(
                context, "该片段超过原视频时长。", "That clip exceeds the source video."
            ),
            show_alert=True,
        )
        return AdvancedVideoProState.WAIT_MEDIA
    await query.answer()
    data["reference_video_duration"] = duration
    await robust_edit_text(
        query.message,
        await _reference_progress_text(context, data),
        reply_markup=_reference_keyboard(context, data),
    )
    return AdvancedVideoProState.WAIT_MEDIA


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
            reference_video_duration=data.get("reference_video_duration"),
            reference_audio=data.get("reference_audio"),
            duration=data["duration"],
            resolution_preset=data["preset"],
            aspect_ratio=(
                "source" if data["mode"] in {"i2v", "flf2v"} else data["aspect"]
            ),
            main_model=data.get("main_model", "10eros_bf16"),
            addon_items=list(data.get("addon_items", [])),
            execution_task_type=data.get("minimax_h3_execution_task_type"),
        )
    except AdvancedVideoProSubmissionError as exc:
        await robust_reply_text(message, _with_cancel_hint(context, str(exc)))
        return AdvancedVideoProState.WAIT_PROMPT
    displayed_cost = int(data.get("runtime_cost", plan.cost))
    has_displayed_runtime_cost = "runtime_cost" in data
    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id,
            user.username,
            user.full_name,
            cost=displayed_cost,
            task_type=None if has_displayed_runtime_cost else plan.task_type,
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
                    f"余额不足，需要 {displayed_cost} 点。",
                    f"Insufficient balance. {displayed_cost} credits required.",
                ),
            )
            _clear(context)
            return ConversationHandler.END
        raise
    await robust_reply_text(
        message,
        _text(
            context,
            f"任务已提交，预计消耗 {displayed_cost} 点。",
            f"Task submitted. Estimated cost: {displayed_cost} credits.",
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
                False
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
            cost_override=(displayed_cost if has_displayed_runtime_cost else None),
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
        is_reference_mode = bool(data and data.get("mode") == "ref2v")
        await robust_reply_text(
            update.effective_message,
            _with_cancel_hint(
                context,
                _text(
                    context,
                    "请直接发送图片、音频或视频。"
                    if is_reference_mode
                    else "请直接发送图片。",
                    "Send an image, audio file, or video directly."
                    if is_reference_mode
                    else "Send the image directly.",
                ),
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
                    filters.VOICE | filters.AUDIO | filters.Document.AUDIO,
                    receive_reference_audio,
                ),
                MessageHandler(
                    filters.VIDEO | filters.Document.VIDEO,
                    receive_reference_video,
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    receive_settings_prompt,
                ),
            ],
            AdvancedVideoProState.WAIT_MEDIA: [
                CallbackQueryHandler(
                    reference_video_duration_callback,
                    pattern=r"^avp_refvideo_duration_",
                ),
                CallbackQueryHandler(reference_callback, pattern=r"^avp_refs_"),
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(
                    filters.VOICE | filters.AUDIO | filters.Document.AUDIO,
                    receive_reference_audio,
                ),
                MessageHandler(
                    filters.VIDEO | filters.Document.VIDEO,
                    receive_reference_video,
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
