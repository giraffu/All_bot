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
    DURATION_PERMISSIONS,
    DEFAULT_DURATION,
    DEFAULT_RESOLUTION,
    MODE_BLOWJOB,
    MODE_CLOSEUP_BLOWJOB,
    MODE_CUSTOM_VIDEO,
    MODE_LTX_VIDEO,
    MODE_DOGGY_STYLE,
    MODE_PERFECT_VIDEO_INSERT,
    MODE_UNDRESS_TONGUE,
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
    QUICK_REF2V_TEMPLATE_CALLBACK_PATTERN,
    build_quick_ref2v_template_callback_data,
    parse_quick_video_mode_callback_data,
    parse_quick_video_scene_callback_data,
    parse_quick_video_v1_scene_callback_data,
    parse_quick_ai_video_scene_callback_data,
    parse_quick_ref2v_template_callback_data,
)
from src.handlers.fsm.quick_draw_callback_data import QUICK_DRAW_SCENE_CALLBACK_PATTERN
from src.handlers.message_handler_menu import reply_with_lazy_bot_payload
from src.handlers.prompt_router import GLOBAL_REVERSE_MAP
from src.services.permission_service import permission_service
from src.services.qqcc_config_service import (
    VIDEO_DURATION_KEYS,
    VIDEO_RESOLUTION_KEYS,
    get_qqcc_copywriting_override,
    get_qqcc_video_scene,
    get_qqcc_ai_video_scene,
    get_qqcc_draw_scene,
    has_enabled_qqcc_video_scenes,
    has_enabled_qqcc_ai_video_scenes,
    is_qqcc_main_button_enabled,
    load_runtime_qqcc_config,
    project_qqcc_config_for_scene_version,
    render_qqcc_copywriting,
)
from src.services.qqcc_demo_media_service import (
    send_qqcc_ref2v_reference_templates,
    send_qqcc_scene_demo_media,
)
from src.services.qqcc_runtime_context import (
    get_private_qqcc_bot_id,
    is_qqcc_bot_context,
    load_qqcc_config_for_context as _load_qqcc_runtime_config_for_context,
    run_qqcc_interaction_io,
)
from src.services.qqcc_scene_billing_service import resolve_qqcc_scene_fixed_credit_cost
from src.services.quick_video_submission_service import (
    QuickVideoSubmissionReject,
    QuickVideoSubmissionRejectReason,
    QuickVideoSettingsReject,
    build_quick_video_settings_update,
    build_quick_video_submission_plan,
    calculate_quick_video_cost,
    resolve_qqcc_video_scene_from_fsm_data,
    resolve_qqcc_ai_video_scene_from_fsm_data,
    resolve_qqcc_video_scene_task_type,
    run_quick_video_submission_plan,
)
from src.services.qqcc_video_frame_adapter import QqccVideoFrameAdaptationError
from src.services.task_service_generation_image import (
    process_standard_generation_task as process_generation_task,
)
from src.services.task_service_entrypoints_video import process_video_task_template
from src.services.wan22_video_v2_extension_service import (
    download_output_file_to_fsm_temp,
)
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.utils import (
    create_background_task,
    robust_edit_text,
    robust_reply_text,
    robust_send_message,
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


def _quick_video_temp_paths(fsm_data: dict) -> list[str]:
    return [
        str(path)
        for path in (
            fsm_data.get("image_path"),
            fsm_data.get("end_image_path"),
            fsm_data.get("selected_reference_image_path"),
        )
        if path
    ]


async def _run_quick_video_submission_with_error_notice(
    *, context, chat_id: int, submission
):
    try:
        await submission
    except QqccVideoFrameAdaptationError as exc:
        logger.warning("QQCC video frame adaptation failed: %s", exc)
        await robust_send_message(
            context.bot,
            chat_id,
            _t(context, "fsm.common.image_processing_failed"),
        )


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    fsm_data = context.user_data.pop("quick_video_data", {})
    cleanup_fsm_temp_files(_quick_video_temp_paths(fsm_data))
    draw_fsm_data = context.user_data.pop("quick_image_data", {})
    cleanup_fsm_temp_files([draw_fsm_data.get("image_path")])


def _replace_pending_quick_video_context(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Clear only a pending video upload before a QQCC scene switch."""
    user_data = context.user_data
    if not str(user_data.get("in_conversation") or "").startswith("QUICK_VIDEO_"):
        return False
    video_data = user_data.pop("quick_video_data", {})
    user_data.pop("in_conversation", None)
    cleanup_fsm_temp_files(
        _quick_video_temp_paths(video_data) if isinstance(video_data, dict) else []
    )
    return True


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


def _is_qqcc_quick_video_mode_enabled(
    config: dict,
    mode: str | None,
    *,
    scene_version: str = "v2",
) -> bool:
    return bool(
        mode
        and is_qqcc_main_button_enabled(
            config,
            "video_edit_v1" if scene_version == "v1" else "video_edit_v2",
        )
        and has_enabled_qqcc_video_scenes(config)
    )


def _is_qqcc_ai_video_mode_enabled(config: dict, mode: str | None) -> bool:
    return bool(
        mode == MODE_LTX_VIDEO
        and is_qqcc_main_button_enabled(config, "ai_video")
        and has_enabled_qqcc_ai_video_scenes(config)
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


def _strip_menu_prefix(text: str) -> str:
    text = (text or "").strip()
    first_token, _, rest = text.partition(" ")
    if rest and not any(char.isalnum() for char in first_token):
        return rest.strip()
    return text


def _resolve_quick_video_entry(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> tuple[str | None, str, object | None, str | None, str | None, str]:
    query = update.callback_query
    if query:
        ai_video_scene_id = parse_quick_ai_video_scene_callback_data(query.data)
        if ai_video_scene_id:
            return (
                MODE_LTX_VIDEO,
                "",
                getattr(query, "message", None),
                None,
                ai_video_scene_id,
                "ai_video",
            )
        scene_id = parse_quick_video_scene_callback_data(query.data)
        if scene_id:
            return None, "", getattr(query, "message", None), None, scene_id, "video"
        scene_id = parse_quick_video_v1_scene_callback_data(query.data)
        if scene_id:
            return None, "", getattr(query, "message", None), None, scene_id, "video_v1"
        route_key = parse_quick_video_mode_callback_data(query.data)
        mode = QUICK_VIDEO_MODES.get(route_key) if route_key else None
        mode_name = _strip_menu_prefix(_t(context, route_key)) if route_key else ""
        return (
            mode,
            mode_name,
            getattr(query, "message", None),
            route_key,
            None,
            "video",
        )

    message = update.message or update.edited_message
    text = message.text.strip() if message and message.text else ""
    route_key = GLOBAL_REVERSE_MAP.get(text)
    mode = QUICK_VIDEO_MODES.get(route_key) if route_key else None
    return mode, _strip_menu_prefix(text), message, route_key, None, "video"


def _resolve_qqcc_scene_from_entry(
    config: dict,
    *,
    scene_id: str | None,
    route_key: str | None,
    scene_kind: str,
) -> dict[str, object] | None:
    if scene_kind == "ai_video":
        return get_qqcc_ai_video_scene(config, scene_id)
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
    scene_kind: str = "video",
) -> str:
    mode = (
        MODE_LTX_VIDEO
        if scene_kind == "ai_video"
        else resolve_qqcc_video_scene_task_type(scene)
    )
    fsm_data.update(
        {
            "mode": mode,
            "duration": scene["duration"],
            "resolution": str(
                scene.get("resolution")
                or ("1280x704" if scene_kind == "ai_video" else "720p")
            ),
            "engine": scene.get("engine"),
            "lora_name": str(scene.get("lora_name") or ""),
            "lora_items": list(scene.get("lora_items") or []),
            "end_frame_draw_scene_id": str(scene.get("end_frame_draw_scene_id") or ""),
            "scene_kind": scene_kind,
        }
    )
    if scene_kind == "ai_video":
        fsm_data.update(
            {
                "ai_video_mode": str(scene.get("mode") or "i2v"),
                "reference_images": list(scene.get("reference_images") or []),
                "reference_image_names": list(
                    scene.get("reference_image_names") or []
                ),
                "reference_image_telegram_file_ids": list(
                    scene.get("reference_image_telegram_file_ids") or []
                ),
                "aspect_ratio": str(scene.get("aspect_ratio") or "16:9"),
            }
        )
    fixed_credit_cost = resolve_qqcc_scene_fixed_credit_cost(scene)
    if fixed_credit_cost is None:
        fsm_data.pop("credit_cost", None)
    else:
        fsm_data["credit_cost"] = fixed_credit_cost
    if scene_kind != "ai_video":
        fsm_data.pop("ai_video_mode", None)
        fsm_data.pop("reference_images", None)
        fsm_data.pop("reference_image_names", None)
        fsm_data.pop("reference_image_telegram_file_ids", None)
        fsm_data.pop("aspect_ratio", None)
        fsm_data.pop("lora_items", None)
        fsm_data.pop("scene_kind", None)
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


def _build_ref2v_template_markup(scene: dict[str, object]) -> InlineKeyboardMarkup:
    reference_names = list(scene.get("reference_image_names") or [])
    reference_images = list(scene.get("reference_images") or [])
    buttons = [
        InlineKeyboardButton(
            f"替换：{reference_names[index] or f'模板 {index + 1}'}",
            callback_data=build_quick_ref2v_template_callback_data(
                str(scene["id"]), index
            ),
        )
        for index in range(len(reference_images))
    ]
    return InlineKeyboardMarkup(
        [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    )


def _build_ref2v_scene_prompt(
    *, scene: dict[str, object], selected_name: str, replacement_confirmed: bool = False
) -> str:
    scene_name = str(scene.get("name") or "AI视频")
    if replacement_confirmed:
        status = f"✅ 已使用你发送的图片替换【{selected_name}】模板。"
        action = (
            "现在请发送女性人物图片（正面、脸部清晰），"
            "我会使用当前模板生成视频。"
        )
    else:
        status = f"✅ 当前默认模板【{selected_name}】。"
        action = (
            "你可以直接发送女性人物图片（正面、脸部清晰），"
            "我会使用当前模板生成视频。"
        )
    return (
        f"🎞️ {'已更新' if replacement_confirmed else '已切换到'}【{scene_name}】场景。\n\n"
        f"{status}\n\n"
        f"{action}\n\n"
        "如需更换参考模板，点击下方“替换：模板名称”按钮，然后发送新的模板图片；"
        "模板替换完成后，我会再次提示你发送女性人物图片。\n\n"
        "随时可以发送 /cancel 退出流程。"
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
        keyboard = []

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
    fixed_credit_cost: int | None = None,
) -> str:
    return _t(
        context,
        "fsm.quick_video.settings_text",
        resolution=resolution,
        duration=duration,
        cost=(
            fixed_credit_cost
            if fixed_credit_cost is not None
            else calculate_quick_video_cost(resolution, duration)
        ),
        start_button=_t(context, "fsm.quick_video.start_button"),
    )


async def start_quick_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for 懒人动图 (单步图生视频)"""
    query = update.callback_query
    if query:
        await safe_answer_query(query)
    mode, mode_name, reply_message, route_key, scene_id, scene_kind = (
        _resolve_quick_video_entry(update, context)
    )

    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        msg = _t(context, "fsm.common.maintenance")
        if query:
            await robust_edit_text(query.message, msg, parse_mode="Markdown")
        elif reply_message:
            await robust_reply_text(reply_message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if query and (scene_id or route_key) and is_qqcc_bot_context(context):
        from src.handlers.fsm.quick_image_fsm import (
            _replace_pending_quick_image_context,
        )

        _replace_pending_quick_video_context(context)
        _replace_pending_quick_image_context(context)

    if context.user_data.get("in_conversation"):
        msg = _t(context, "fsm.common.conflict")
        if reply_message:
            await robust_reply_text(reply_message, msg)
        return ConversationHandler.END

    qqcc_config = await _load_qqcc_config_for_context(context)
    scene_version = "v1" if scene_kind == "video_v1" else "v2"
    if scene_kind == "video_v1" and qqcc_config is not None:
        qqcc_config = project_qqcc_config_for_scene_version(
            qqcc_config, family="video", version=scene_version
        )
        scene_kind = "video"
    if qqcc_config is None and (mode or route_key or scene_id):
        await reply_with_lazy_bot_payload(
            update,
            context,
            reply_text_func=robust_reply_text,
            edit_text_func=robust_edit_text,
        )
        return ConversationHandler.END

    scene = None
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
            scene_kind=scene_kind,
        )
        feature_enabled = (
            is_qqcc_main_button_enabled(qqcc_config, "ai_video")
            if scene_kind == "ai_video"
            else is_qqcc_main_button_enabled(
                qqcc_config,
                "video_edit_v1" if scene_version == "v1" else "video_edit_v2",
            )
        )
        if not feature_enabled or scene is None:
            await _reply_qqcc_feature_disabled(update, context)
            return ConversationHandler.END
        mode = _sync_qqcc_scene_to_quick_video_data(
            quick_video_data,
            scene,
            include_scene_id=True,
            include_prompt_details=True,
            scene_kind=scene_kind,
        )
        if scene_kind == "video":
            quick_video_data["scene_version"] = scene_version
        mode_name = str(quick_video_data["mode_name"])

    if not mode or not reply_message:
        return ConversationHandler.END

    context.user_data["in_conversation"] = f"QUICK_VIDEO_{mode}"
    context.user_data["quick_video_data"] = quick_video_data

    msg = _t(context, "fsm.quick_video.start", mode_name=mode_name)
    if scene is not None and qqcc_config is not None:
        msg = (
            render_qqcc_copywriting(
                get_qqcc_copywriting_override(
                    qqcc_config,
                    "ai_video_scene_start"
                    if scene_kind == "ai_video"
                    else "video_scene_start",
                ),
                str(scene.get("name") or mode_name),
                cost=resolve_qqcc_scene_fixed_credit_cost(scene),
            )
            or msg
        )
    if scene is not None:
        private_bot_id = get_private_qqcc_bot_id(context)
        demo_kwargs = {"private_bot_id": private_bot_id} if private_bot_id else {}
        await send_qqcc_scene_demo_media(
            message=reply_message,
            bot=context.bot,
            scene_kind=(
                "video_v1"
                if quick_video_data.get("scene_version") == "v1"
                else scene_kind
            ),
            scene=scene,
            **demo_kwargs,
        )
    is_ref2v_scene = bool(
        scene_kind == "ai_video" and str((scene or {}).get("mode") or "") == "ref2v"
    )
    if is_ref2v_scene and scene is not None:
        reference_images = list(scene.get("reference_images") or [])
        reference_names = list(scene.get("reference_image_names") or [])
        if reference_images:
            quick_video_data["selected_reference_image"] = reference_images[0]
            quick_video_data["selected_reference_name"] = str(
                (reference_names[0] if reference_names else "") or "模板 1"
            )
        gallery_awaitable = send_qqcc_ref2v_reference_templates(
            message=reply_message,
            bot=context.bot,
            scene=scene,
        )
        if is_qqcc_bot_context(context):
            await run_qqcc_interaction_io(
                gallery_awaitable,
                operation="quick_video_ref2v_template_gallery",
                logger=logger,
            )
        else:
            await gallery_awaitable
    reply_markup = None
    if is_ref2v_scene and scene is not None:
        selected_name = str(quick_video_data.get("selected_reference_name") or "模板 1")
        reply_markup = _build_ref2v_template_markup(scene)
        msg = _build_ref2v_scene_prompt(
            scene=scene,
            selected_name=selected_name,
        )
    if scene is not None and qqcc_config is not None:
        draw_config = project_qqcc_config_for_scene_version(
            qqcc_config,
            family="draw",
            version=str(quick_video_data.get("scene_version") or "v2"),
        )
        jump_scene = get_qqcc_draw_scene(
            draw_config, str(scene.get("jump_draw_scene_id") or "")
        )
        is_v1 = quick_video_data.get("scene_version") == "v1"
        draw_button_key = "ai_draw_v1" if is_v1 else "ai_draw_v2"
        if jump_scene is not None and is_qqcc_main_button_enabled(
            draw_config, draw_button_key
        ):
            from src.handlers.fsm.quick_draw_callback_data import (
                build_quick_draw_scene_callback_data,
                build_quick_draw_v1_scene_callback_data,
            )

            jump_row = [InlineKeyboardButton(
                    f"先去 AI绘图{'V1' if is_v1 else 'V2'}生成「{jump_scene['name']}」",
                    callback_data=(
                        build_quick_draw_v1_scene_callback_data(jump_scene["id"])
                        if is_v1
                        else build_quick_draw_scene_callback_data(jump_scene["id"])
                    ),
                )]
            existing_rows = list(reply_markup.inline_keyboard) if reply_markup else []
            reply_markup = InlineKeyboardMarkup([*existing_rows, jump_row])
    reply_awaitable = robust_reply_text(
        reply_message, msg, reply_markup=reply_markup, parse_mode="Markdown"
    )
    if is_qqcc_bot_context(context):
        await run_qqcc_interaction_io(
            reply_awaitable,
            operation="quick_video_scene_prompt",
            logger=logger,
        )
    else:
        await reply_awaitable
    return QuickVideoState.WAIT_IMAGE


async def select_ref2v_template(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    parsed = parse_quick_ref2v_template_callback_data(
        getattr(query, "data", None)
    )
    if query is None or parsed is None:
        return ConversationHandler.END
    await safe_answer_query(query)
    scene_id, template_index = parsed
    fsm_data = context.user_data.get("quick_video_data")
    if not isinstance(fsm_data, dict) or fsm_data.get("scene_id") != scene_id:
        await safe_answer_query(
            query, text="模板选择已失效，请重新进入场景", show_alert=True
        )
        return ConversationHandler.END
    qqcc_config = await _load_qqcc_config_for_context(context)
    scene = (
        get_qqcc_ai_video_scene(qqcc_config, scene_id)
        if qqcc_config is not None
        else None
    )
    if (
        scene is None
        or str(scene.get("mode") or "") != "ref2v"
        or not is_qqcc_main_button_enabled(qqcc_config, "ai_video")
    ):
        await _reply_qqcc_feature_disabled(update, context)
        _cleanup_context(context, getattr(update.effective_user, "id", 0))
        return ConversationHandler.END
    references = list(scene.get("reference_images") or [])
    names = list(scene.get("reference_image_names") or [])
    if template_index >= len(references):
        await safe_answer_query(
            query, text="模板已更新，请重新选择", show_alert=True
        )
        return QuickVideoState.WAIT_IMAGE
    _sync_qqcc_scene_to_quick_video_data(fsm_data, scene, scene_kind="ai_video")
    selected_name = str(
        names[template_index] if template_index < len(names) else f"模板 {template_index + 1}"
    )
    fsm_data["pending_reference_template_index"] = template_index
    fsm_data["pending_reference_template_name"] = selected_name
    await robust_edit_text(
        query.message,
        f"🖼️ 请发送用于替换【{selected_name}】的模板图片。\n\n"
        "这张图片只会替换当前场景的参考模板，不会直接开始生成视频。\n"
        "替换完成后，我会重新发送场景提示，再等待女性人物图片。\n\n"
        "随时可以发送 /cancel 退出流程。",
        reply_markup=_build_ref2v_template_markup(scene),
    )
    return QuickVideoState.WAIT_REFERENCE_TEMPLATE_UPLOAD


async def receive_ref2v_template_replacement(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id if update.effective_user else 0
    message = update.message or update.edited_message
    fsm_data = context.user_data.get("quick_video_data")
    if not isinstance(fsm_data, dict):
        await robust_reply_text(message, _t(context, "fsm.common.expired_cleaned"))
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    template_index = fsm_data.get("pending_reference_template_index")
    if not isinstance(template_index, int):
        await robust_reply_text(message, "模板替换步骤已失效，请重新进入场景。")
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    qqcc_config = await _load_qqcc_config_for_context(context)
    scene_id = str(fsm_data.get("scene_id") or "")
    scene = (
        get_qqcc_ai_video_scene(qqcc_config, scene_id)
        if qqcc_config is not None
        else None
    )
    if (
        scene is None
        or str(scene.get("mode") or "") != "ref2v"
        or not is_qqcc_main_button_enabled(qqcc_config, "ai_video")
    ):
        await _reply_qqcc_feature_disabled(update, context)
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    references = list(scene.get("reference_images") or [])
    names = list(scene.get("reference_image_names") or [])
    if template_index >= len(references):
        await robust_reply_text(message, "模板配置已更新，请重新进入场景。")
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    file_id = _resolve_quick_video_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return QuickVideoState.WAIT_REFERENCE_TEMPLATE_UPLOAD
    try:
        local_path = await _download_quick_video_input(
            context=context,
            file_id=file_id,
        )
    except Exception as exc:
        logger.error("Failed to download REF2V replacement user=%s: %s", user_id, exc)
        local_path = None
    if not local_path:
        await robust_reply_text(
            message, _t(context, "fsm.common.download_image_failed")
        )
        return QuickVideoState.WAIT_REFERENCE_TEMPLATE_UPLOAD

    previous_reference_path = fsm_data.get("selected_reference_image_path")
    if previous_reference_path:
        cleanup_fsm_temp_files([previous_reference_path])
    _sync_qqcc_scene_to_quick_video_data(fsm_data, scene, scene_kind="ai_video")
    selected_name = str(
        (names[template_index] if template_index < len(names) else "")
        or f"模板 {template_index + 1}"
    )
    fsm_data["selected_reference_image"] = references[template_index]
    fsm_data["selected_reference_name"] = selected_name
    fsm_data["selected_reference_image_path"] = local_path
    fsm_data.pop("pending_reference_template_index", None)
    fsm_data.pop("pending_reference_template_name", None)

    await robust_reply_text(
        message,
        _build_ref2v_scene_prompt(
            scene=scene,
            selected_name=selected_name,
            replacement_confirmed=True,
        ),
        reply_markup=_build_ref2v_template_markup(scene),
    )
    return QuickVideoState.WAIT_IMAGE


async def jump_to_qqcc_draw_scene(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Replace a pending video upload with the selected QQCC draw-scene flow."""
    from src.handlers.fsm.quick_image_fsm import start_quick_image
    from src.handlers.conversation_states import QuickImageState

    _replace_pending_quick_video_context(context)
    result = await start_quick_image(update, context)
    if result == QuickImageState.WAIT_IMAGE:
        # The video ConversationHandler remains the active owner of the next
        # upload, so receive_image delegates to the initialized draw flow.
        return QuickVideoState.WAIT_IMAGE
    return ConversationHandler.END


async def _download_quick_video_input(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
) -> str | None:
    async def download() -> str:
        new_file = await context.bot.get_file(file_id)
        return await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="quick_video",
        )

    download_awaitable = download()
    if is_qqcc_bot_context(context):
        return await run_qqcc_interaction_io(
            download_awaitable,
            operation="quick_video_download",
            logger=logger,
        )
    return await download_awaitable


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if str(context.user_data.get("in_conversation") or "").startswith(
        "QUICK_IMAGE_"
    ) and context.user_data.get("quick_image_data"):
        from src.handlers.fsm.quick_image_fsm import receive_image as receive_quick_image

        video_data = context.user_data.pop("quick_video_data", {})
        cleanup_fsm_temp_files(_quick_video_temp_paths(video_data))
        return await receive_quick_image(update, context)

    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data.get("quick_video_data")
    if not isinstance(fsm_data, dict) or not fsm_data:
        await robust_reply_text(message, _t(context, "fsm.common.expired_cleaned"))
        _cleanup_context(context, user_id)
        return ConversationHandler.END
    mode = fsm_data.get("mode")
    qqcc_config = await _load_qqcc_config_for_context(context)
    if qqcc_config is not None:
        qqcc_config = project_qqcc_config_for_scene_version(
            qqcc_config, family="video", version=str(fsm_data.get("scene_version") or "v2")
        )
    qqcc_scene = None
    if qqcc_config is not None:
        scene_kind = str(fsm_data.get("scene_kind") or "video")
        qqcc_scene = (
            resolve_qqcc_ai_video_scene_from_fsm_data(qqcc_config, fsm_data)
            if scene_kind == "ai_video"
            else resolve_qqcc_video_scene_from_fsm_data(qqcc_config, fsm_data)
        )
        if (
            not (
                _is_qqcc_ai_video_mode_enabled(qqcc_config, mode)
                if scene_kind == "ai_video"
                else _is_qqcc_quick_video_mode_enabled(
                    qqcc_config,
                    mode,
                    scene_version=str(fsm_data.get("scene_version") or "v2"),
                )
            )
            or qqcc_scene is None
        ):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        _sync_qqcc_scene_to_quick_video_data(
            fsm_data, qqcc_scene, scene_kind=scene_kind
        )

    file_id = _resolve_quick_video_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return QuickVideoState.WAIT_IMAGE

    try:
        local_path = await _download_quick_video_input(
            context=context,
            file_id=file_id,
        )
        if not local_path:
            await robust_reply_text(
                message, _t(context, "fsm.common.download_image_failed")
            )
            return QuickVideoState.WAIT_IMAGE
        fsm_data["image_path"] = local_path
    except Exception as e:
        logger.error(f"Error downloading image for FSM user {user_id}: {e}")
        await robust_reply_text(
            message, _t(context, "fsm.common.download_image_failed")
        )
        return QuickVideoState.WAIT_IMAGE

    if str(fsm_data.get("scene_kind") or "") == "ai_video":
        return await start_generation(update, context)

    res = fsm_data["resolution"]
    dur = fsm_data["duration"]
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
            fixed_credit_cost=resolve_qqcc_scene_fixed_credit_cost(fsm_data),
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
            await query.answer(
                _t(context, "fsm.quick_video.expired_alert"), show_alert=True
            )
        return ConversationHandler.END

    qqcc_config = await _load_qqcc_config_for_context(context)
    if qqcc_config is not None:
        qqcc_config = project_qqcc_config_for_scene_version(
            qqcc_config, family="video", version=str(fsm_data.get("scene_version") or "v2")
        )
    qqcc_scene = None
    if qqcc_config is not None:
        qqcc_scene = resolve_qqcc_video_scene_from_fsm_data(qqcc_config, fsm_data)
        if (
            not _is_qqcc_quick_video_mode_enabled(
                qqcc_config,
                fsm_data.get("mode"),
                scene_version=str(fsm_data.get("scene_version") or "v2"),
            )
            or qqcc_scene is None
        ):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        _sync_qqcc_scene_to_quick_video_data(fsm_data, qqcc_scene)

    if data == "qvid_start_generation":
        await query.answer(
            text=_t(context, "fsm.common.task_initializing"), cache_time=2
        )
        return await start_generation(update, context)

    if qqcc_config is not None:
        await query.answer(_t(context, "qqcc.feature_disabled"), show_alert=True)
        return QuickVideoState.WAIT_SETTINGS

    settings_update = build_quick_video_settings_update(
        callback_data=data,
        resolution=str(fsm_data.get("resolution") or ""),
        duration=str(fsm_data.get("duration") or ""),
        qqcc_config_present=qqcc_config is not None,
        allowed_resolutions=None,
        allowed_durations=None,
    )
    if isinstance(settings_update, QuickVideoSettingsReject):
        if settings_update.reason == QuickVideoSubmissionRejectReason.FEATURE_DISABLED:
            await query.answer(_t(context, "qqcc.feature_disabled"), show_alert=True)
            return QuickVideoState.WAIT_SETTINGS
        await _reply_qqcc_feature_disabled(update, context)
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    if settings_update.alert_key:
        with contextlib.suppress(Exception):
            await query.answer(_t(context, settings_update.alert_key), show_alert=True)
    fsm_data["resolution"] = settings_update.resolution
    fsm_data["duration"] = settings_update.duration
    res = settings_update.resolution
    dur = settings_update.duration

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
                fixed_credit_cost=resolve_qqcc_scene_fixed_credit_cost(fsm_data),
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

        await safe_answer_query(
            query, text=_t(context, "fsm.common.task_initializing"), cache_time=2
        )
    user_id = (
        query.from_user.id
        if query is not None
        else update.effective_user.id
        if update.effective_user
        else 0
    )

    fsm_data = context.user_data.get("quick_video_data", {})
    if not fsm_data:
        return ConversationHandler.END

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        logger.warning(
            f"user={user_id} image_path missing or already consumed in quick_video"
        )
        if query is not None:
            with contextlib.suppress(Exception):
                await query.answer(
                    _t(context, "fsm.quick_video.already_submitted"), show_alert=True
                )
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    qqcc_config = await _load_qqcc_config_for_context(context)
    if qqcc_config is not None:
        qqcc_config = project_qqcc_config_for_scene_version(
            qqcc_config, family="video", version=str(fsm_data.get("scene_version") or "v2")
        )
    plan = build_quick_video_submission_plan(
        fsm_data=fsm_data,
        qqcc_config=qqcc_config,
        allowed_resolutions=None,
    )
    selected_reference_image_path = fsm_data.pop(
        "selected_reference_image_path", None
    )
    submission_temp_paths = [
        str(path) for path in (image_path, selected_reference_image_path) if path
    ]
    if isinstance(plan, QuickVideoSubmissionReject):
        if qqcc_config is not None:
            await _reply_qqcc_feature_disabled(update, context)
        cleanup_fsm_temp_files(submission_temp_paths)
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    if not update.effective_user:
        cleanup_fsm_temp_files(submission_temp_paths)
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
            cleanup_fsm_temp_files(submission_temp_paths)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        raise e

    status_message = query.message if query is not None else None
    if status_message is not None:
        status_awaitable = robust_edit_text(
            status_message, _t(context, "fsm.quick_video.submit", cost=plan.total_cost)
        )
        if is_qqcc_bot_context(context):
            await run_qqcc_interaction_io(
                status_awaitable,
                operation="quick_video_submit_status",
                logger=logger,
            )
        else:
            await status_awaitable
    else:
        status_awaitable = robust_reply_text(
            update.message,
            _t(context, "fsm.quick_video.submit", cost=plan.total_cost),
        )
        if is_qqcc_bot_context(context):
            status_message = await run_qqcc_interaction_io(
                status_awaitable,
                operation="quick_video_submit_status",
                logger=logger,
            )
        else:
            status_message = await status_awaitable

    create_background_task(
        context,
        _run_quick_video_submission_with_error_notice(
            context=context,
            chat_id=update.effective_chat.id,
            submission=run_quick_video_submission_plan(
                plan=plan,
                context=context,
                chat_id=update.effective_chat.id,
                user_id=user_id,
                username=update.effective_user.username,
                image_path=image_path,
                status_msg_id=getattr(status_message, "message_id", None),
                process_video_task_template_func=process_video_task_template,
                process_generation_task_func=process_generation_task,
                download_output_file_to_fsm_temp_func=download_output_file_to_fsm_temp,
                cleanup_temp_files_func=cleanup_fsm_temp_files,
            ),
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
            QuickVideoState.WAIT_REFERENCE_TEMPLATE_UPLOAD: [
                CallbackQueryHandler(
                    start_quick_video,
                    pattern=QUICK_VIDEO_ENTRY_CALLBACK_PATTERN,
                ),
                CallbackQueryHandler(
                    select_ref2v_template,
                    pattern=QUICK_REF2V_TEMPLATE_CALLBACK_PATTERN,
                ),
                MessageHandler(
                    filters.PHOTO | filters.Document.IMAGE,
                    receive_ref2v_template_replacement,
                ),
                MessageHandler(
                    filters.ALL & ~filters.Regex(r"^/cancel$"), unexpected_input
                ),
            ],
            QuickVideoState.WAIT_IMAGE: [
                CallbackQueryHandler(
                    start_quick_video,
                    pattern=QUICK_VIDEO_ENTRY_CALLBACK_PATTERN,
                ),
                CallbackQueryHandler(
                    jump_to_qqcc_draw_scene,
                    pattern=QUICK_DRAW_SCENE_CALLBACK_PATTERN,
                ),
                CallbackQueryHandler(
                    select_ref2v_template,
                    pattern=QUICK_REF2V_TEMPLATE_CALLBACK_PATTERN,
                ),
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
