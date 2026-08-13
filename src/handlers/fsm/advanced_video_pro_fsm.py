from __future__ import annotations

import os
import uuid
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.core.user_core import get_or_create_user_by_telegram
from src.domain_config.minimax_h3 import MINIMAX_H3_ADDON_MODELS
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
    build_advanced_video_pro_submission_plan,
    submit_advanced_video_pro_plan,
    validate_advanced_video_pro_frame_aspects,
)
from src.services.advanced_video_prompt_optimizer_service import (
    optimize_advanced_video_prompt,
)
from src.services.fsm_temp_file_service import (
    cleanup_fsm_user_data,
    download_telegram_file_to_fsm_temp,
)
from src.services.permission_service import permission_service
from src.utils import create_background_task, robust_edit_text, robust_reply_text

DATA_KEY = "advanced_video_pro_data"
TAG = "ADVANCED_VIDEO_PRO"
MODES = ("t2v", "i2v", "flf2v")
DURATIONS = (5, 10, 15)
PRESETS = ("preview", "small", "standard", "hd")
ASPECTS = ("16:9", "9:16", "1:1", "4:3", "3:4")
PRESET_LABELS = {
    "preview": ("极速（约 512p）", "Fast (approx. 512p)"),
    "small": ("清晰（约 600p）", "Small (approx. 600p)"),
    "standard": ("标准（约 720p）", "Standard (approx. 720p)"),
    "hd": ("高清（约 810p）", "HD (approx. 810p)"),
}


def _lang(context) -> str:
    return "en" if getattr(context, "lang", "zh") == "en" else "zh"


def _text(context, zh: str, en: str) -> str:
    return en if _lang(context) == "en" else zh


def _mode_keyboard(context) -> InlineKeyboardMarkup:
    labels = (
        ("t2v", "文生视频", "Text to Video"),
        ("i2v", "首帧图生视频", "First-frame Video"),
        ("flf2v", "首尾帧视频", "First/Last-frame Video"),
    )
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


def _settings_keyboard(context, data: dict) -> InlineKeyboardMarkup:
    def buttons(prefix: str, values) -> list[InlineKeyboardButton]:
        return [
            InlineKeyboardButton(
                ("✅ " if str(data.get(prefix)) == str(value) else "") + str(value),
                callback_data=f"avp_{prefix}_{value}",
            )
            for value in values
        ]

    preset_buttons = [
        InlineKeyboardButton(
            ("✅ " if data.get("preset") == value else "")
            + _text(context, *PRESET_LABELS[value]),
            callback_data=f"avp_preset_{value}",
        )
        for value in PRESETS
    ]
    rows = [buttons("duration", DURATIONS), preset_buttons[:2], preset_buttons[2:]]
    if data.get("mode") not in {"i2v", "flf2v"}:
        rows.extend([buttons("aspect", ASPECTS[:3]), buttons("aspect", ASPECTS[3:])])
    addon_buttons = [
        InlineKeyboardButton(
            ("✅ " if model_id in data.get("addon_models", []) else "")
            + _text(context, model.label_zh, model.label_en),
            callback_data=f"avp_addon_{model_id}",
        )
        for model_id, model in MINIMAX_H3_ADDON_MODELS.items()
    ]
    none_label = _text(context, "清空 LoRA", "Clear LoRAs")
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    _text(context, "全选 LoRA", "Select all LoRAs"),
                    callback_data="avp_addon_all",
                ),
                InlineKeyboardButton(none_label, callback_data="avp_addon_none"),
            ],
            addon_buttons[:3],
            addon_buttons[3:],
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                _text(context, "确认设置", "Confirm settings"),
                callback_data="avp_settings_done",
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def _settings_text(context, data: dict) -> str:
    aspect = (
        _text(context, "跟随首帧", "Follow first frame")
        if data.get("mode") in {"i2v", "flf2v"}
        else data["aspect"]
    )
    selected = data.get("addon_models", [])
    addon_zh = (
        "、".join(MINIMAX_H3_ADDON_MODELS[item].label_zh for item in selected) or "无"
    )
    addon_en = (
        ", ".join(MINIMAX_H3_ADDON_MODELS[item].label_en for item in selected) or "None"
    )
    summary = _text(
        context,
        f"🎬 *高级图生视频pro*\n\n请选择设置：\n时长：{data['duration']} 秒\n画质：{_text(context, *PRESET_LABELS[data['preset']])}\n比例：{aspect}\n附加模型：{addon_zh}",
        f"🎬 *Advanced Image-to-Video Pro*\n\nChoose settings:\nDuration: {data['duration']}s\nQuality: {_text(context, *PRESET_LABELS[data['preset']])}\nAspect: {aspect}\nAddons: {addon_en}",
    )
    guidance = _addon_guidance_text(context, selected)
    return f"{summary}\n\n{guidance}" if guidance else summary


def _addon_guidance_text(context, selected: list[str]) -> str:
    models = [
        MINIMAX_H3_ADDON_MODELS[item]
        for item in selected
        if item in MINIMAX_H3_ADDON_MODELS
    ]
    if not models:
        return ""
    title = _text(
        context,
        "提示词与强度建议（触发词会自动添加，无需重复输入）：",
        "Prompt and strength guidance (trigger words are added automatically):",
    )
    lines = [title]
    separator = "：" if _lang(context) == "zh" else ": "
    for model in models:
        strength_hint = (
            model.strength_hint_en if _lang(context) == "en" else model.strength_hint_zh
        )
        prompt_guide = (
            model.prompt_guide_en if _lang(context) == "en" else model.prompt_guide_zh
        )
        label = model.label_en if _lang(context) == "en" else model.label_zh
        lines.append(
            f"• {label} — {_text(context, '建议强度', 'Recommended strength')}"
            f"{separator}{strength_hint}\n  {prompt_guide}"
        )
    return "\n".join(lines)


def _prompt_request_text(context, data: dict, *, media_received: bool = False) -> str:
    intro = _text(
        context,
        "图片已收到，请输入视频提示词。" if media_received else "请输入视频提示词。",
        "Image received. Send the video prompt."
        if media_received
        else "Send the video prompt.",
    )
    guidance = _addon_guidance_text(context, data.get("addon_models", []))
    return f"{intro}\n\n{guidance}" if guidance else intro


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


def _optimizer_enabled() -> bool:
    return os.getenv(
        "MINIMAX_H3_PROMPT_OPTIMIZER_ENABLED", "false"
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _prompt_action_keyboard(
    context, *, can_restore: bool = False
) -> InlineKeyboardMarkup:
    rows = []
    if _optimizer_enabled():
        rows.append(
            [
                InlineKeyboardButton(
                    _text(
                        context,
                        "✨ 优化提示词（1灵石）",
                        "✨ Optimize prompt (1 credit)",
                    ),
                    callback_data="avp_prompt_optimize",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                _text(
                    context, "🎬 使用当前提示词生成", "🎬 Generate with current prompt"
                ),
                callback_data="avp_prompt_generate",
            )
        ]
    )
    if can_restore:
        rows.append(
            [
                InlineKeyboardButton(
                    _text(context, "↩️ 恢复原提示词", "↩️ Restore original prompt"),
                    callback_data="avp_prompt_restore",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


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
    context.user_data["in_conversation"] = TAG
    context.user_data[DATA_KEY] = {
        "mode": None,
        "duration": 5,
        "preset": "preview",
        "aspect": "16:9",
        "images": [],
        "reference_descriptions": [],
        "addon_models": [],
    }
    await robust_reply_text(
        update.effective_message,
        _text(
            context,
            "🎬 *高级图生视频pro*\n\n请选择生成模式：",
            "🎬 *Advanced Image-to-Video Pro*\n\nChoose a generation mode:",
        ),
        reply_markup=_mode_keyboard(context),
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
        if mode in MODES:
            data["mode"] = mode
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
    elif value.startswith("avp_addon_"):
        addon = value.removeprefix("avp_addon_")
        selected = data.setdefault("addon_models", [])
        if addon == "none":
            selected.clear()
        elif addon == "all":
            data["addon_models"] = list(MINIMAX_H3_ADDON_MODELS)
        elif addon in MINIMAX_H3_ADDON_MODELS:
            selected.remove(addon) if addon in selected else selected.append(addon)
    elif value == "avp_settings_done" and data.get("mode"):
        mode = data["mode"]
        if mode == "t2v":
            await robust_edit_text(query.message, _prompt_request_text(context, data))
            return AdvancedVideoProState.WAIT_PROMPT
        await robust_edit_text(
            query.message,
            _text(
                context, "请上传第一张参考图片。", "Upload the first reference image."
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
    file_id, suffix = _extract_image(update)
    if not file_id:
        await robust_reply_text(
            update.message, _text(context, "请上传有效图片。", "Upload a valid image.")
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
            _text(
                context,
                "起始帧已收到，请上传终止帧。",
                "Start frame received. Upload the end frame.",
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    if mode == "flf2v":
        try:
            validate_advanced_video_pro_frame_aspects(data["images"])
        except AdvancedVideoProSubmissionError as exc:
            data["images"].pop()
            Path(path).unlink(missing_ok=True)
            await robust_reply_text(update.message, str(exc))
            return AdvancedVideoProState.WAIT_MEDIA
    if mode == "ref2v":
        await robust_reply_text(
            update.message,
            _text(
                context,
                "请描述该角色的身份与外观。",
                "Describe this character's identity and appearance.",
            ),
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
                _text(context, "完成并填写提示词", "Finish and enter prompt"),
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
        _text(context, f"已添加 {count} 个角色。", f"{count} character(s) added."),
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
            _text(
                context,
                "请上传下一张角色参考图。",
                "Upload the next character reference.",
            ),
        )
        return AdvancedVideoProState.WAIT_MEDIA
    await robust_edit_text(query.message, _prompt_request_text(context, data))
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
            duration=data["duration"],
            resolution_preset=data["preset"],
            aspect_ratio=(
                "source" if data["mode"] in {"i2v", "flf2v"} else data["aspect"]
            ),
            addon_items=[{"name": name} for name in data.get("addon_models", [])],
        )
    except AdvancedVideoProSubmissionError as exc:
        await robust_reply_text(message, str(exc))
        return AdvancedVideoProState.WAIT_CONFIRMATION
    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id, user.username, user.full_name, cost=plan.cost
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
            allow_contribute=False,
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
    data["original_prompt"] = prompt
    data["prompt"] = prompt
    data["optimizer_pending"] = False
    await robust_reply_text(
        update.effective_message,
        _text(
            context,
            f"已保存提示词：\n\n{prompt}\n\n请选择优化后再生成，或直接生成。",
            f"Prompt saved:\n\n{prompt}\n\nOptimize it first or generate directly.",
        ),
        reply_markup=_prompt_action_keyboard(context),
    )
    return AdvancedVideoProState.WAIT_CONFIRMATION


async def _run_prompt_optimization(
    *,
    context,
    message,
    data: dict,
    request_token: str,
    telegram_user_id: int,
    username: str | None,
    client_request_id: str,
) -> None:
    try:
        internal_user, _ = await get_or_create_user_by_telegram(
            telegram_user_id,
            username=username,
        )
        optimized = await optimize_advanced_video_prompt(
            internal_user_id=internal_user.id,
            username=username,
            mode=data["mode"],
            prompt=data["original_prompt"],
            images=list(data.get("images", [])),
            duration_seconds=int(data["duration"]),
            addon_items=[{"name": name} for name in data.get("addon_models", [])],
            client_request_id=client_request_id,
        )
    except Exception as exc:
        current = context.user_data.get(DATA_KEY)
        if current is data and data.get("optimizer_request_token") == request_token:
            data["optimizer_pending"] = False
            await robust_edit_text(
                message,
                _text(
                    context,
                    f"提示词优化失败：{exc}\n\n原提示词已保留。",
                    f"Prompt optimization failed: {exc}\n\nThe original prompt was preserved.",
                ),
                reply_markup=_prompt_action_keyboard(context),
            )
        return
    current = context.user_data.get(DATA_KEY)
    if current is not data or data.get("optimizer_request_token") != request_token:
        return
    data["prompt"] = optimized
    data["optimizer_pending"] = False
    await robust_edit_text(
        message,
        _text(
            context,
            f"✨ 提示词优化完成：\n\n{optimized}\n\n请确认后生成。",
            f"✨ Prompt optimization complete:\n\n{optimized}\n\nReview it before generating.",
        ),
        reply_markup=_prompt_action_keyboard(context, can_restore=True),
    )


async def prompt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
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
    if query.data == "avp_prompt_generate":
        if data.get("optimizer_pending"):
            await query.answer(
                _text(
                    context,
                    "提示词仍在优化中。",
                    "Prompt optimization is still running.",
                ),
                show_alert=True,
            )
            return AdvancedVideoProState.WAIT_CONFIRMATION
        await query.answer()
        return await _submit_generation(update, context, data)
    await query.answer()
    if query.data == "avp_prompt_optimize":
        if not _optimizer_enabled():
            await robust_edit_text(
                query.message,
                _text(
                    context,
                    "当前环境未开放提示词优化。",
                    "Prompt optimization is not enabled here.",
                ),
                reply_markup=_prompt_action_keyboard(context),
            )
            return AdvancedVideoProState.WAIT_CONFIRMATION
        if data.get("optimizer_pending"):
            return AdvancedVideoProState.WAIT_CONFIRMATION
        user = update.effective_user
        request_token = uuid.uuid4().hex
        client_request_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "|".join(
                    [
                        "allbot-minimax-h3-prompt",
                        str(user.id),
                        str(update.effective_chat.id),
                        str(data.get("mode")),
                        str(data.get("duration")),
                        str(data.get("original_prompt")),
                        ",".join(str(path) for path in data.get("images", [])),
                        ",".join(data.get("addon_models", [])),
                    ]
                ),
            )
        )
        data["optimizer_pending"] = True
        data["optimizer_request_token"] = request_token
        await robust_edit_text(
            query.message,
            _text(
                context,
                "✨ 正在优化提示词，请稍候……",
                "✨ Optimizing prompt, please wait…",
            ),
        )
        create_background_task(
            context,
            _run_prompt_optimization(
                context=context,
                message=query.message,
                data=data,
                request_token=request_token,
                telegram_user_id=user.id,
                username=user.username,
                client_request_id=client_request_id,
            ),
        )
        return AdvancedVideoProState.WAIT_CONFIRMATION
    if query.data == "avp_prompt_restore":
        data["prompt"] = data.get("original_prompt", data.get("prompt", ""))
        await robust_edit_text(
            query.message,
            _text(context, "已恢复原提示词。", "Original prompt restored."),
            reply_markup=_prompt_action_keyboard(context),
        )
        return AdvancedVideoProState.WAIT_CONFIRMATION
    return AdvancedVideoProState.WAIT_CONFIRMATION


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


def get_advanced_video_pro_fsm_handler() -> ConversationHandler:
    legacy_pattern = r"^(ltx_mode_|set_ltx|ltx_setup_confirm|toggle_ltx_lora_|done_ltx_lora|clear_ltx_lora|skip_ltx_lora)"
    return ConversationHandler(
        entry_points=[
            CommandHandler("advanced_video_pro", start),
            CommandHandler("ltx_video", start),
            MessageHandler(I18nFilter("menu.ltx_video"), start),
            CallbackQueryHandler(start, pattern=r"^fsm_start_ltx_video$"),
            CallbackQueryHandler(legacy_callback, pattern=legacy_pattern),
        ],
        states={
            AdvancedVideoProState.WAIT_SETTINGS: [
                CallbackQueryHandler(settings_callback, pattern=r"^avp_")
            ],
            AdvancedVideoProState.WAIT_MEDIA: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image)
            ],
            AdvancedVideoProState.WAIT_REFERENCE_DESCRIPTION: [
                CallbackQueryHandler(reference_callback, pattern=r"^avp_refs_"),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_reference_description
                ),
            ],
            AdvancedVideoProState.WAIT_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_prompt)
            ],
            AdvancedVideoProState.WAIT_CONFIRMATION: [
                CallbackQueryHandler(prompt_callback, pattern=r"^avp_prompt_")
            ],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.ALL, unexpected),
        ],
        conversation_timeout=300,
        name="advanced_video_pro_fsm",
        persistent=False,
    )
