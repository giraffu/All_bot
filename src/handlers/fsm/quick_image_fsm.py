import logging
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import ENABLE_PUBLIC_SHARE
from src.constants import (
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_I2I_DRAW,
    MODE_MASTURBATION,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_RANDOM_FACESWAP,
    MODE_UNDRESS,
    TASK_COSTS,
)
from src.handlers.conversation_states import QuickImageState
from src.handlers.prompt_router import GLOBAL_REVERSE_MAP, is_global_menu_command
from src.handlers.fsm.quick_draw_callback_data import (
    QUICK_DRAW_SCENE_CALLBACK_PATTERN,
    parse_quick_draw_scene_callback_data,
)
from src.lora_catalog import get_lora_default_strength
from src.services.task_service_generation_image import process_standard_generation_task as process_generation_task
from src.services.permission_service import permission_service
from src.services.qqcc_draw_chain_service import (
    calculate_qqcc_draw_chain_cost,
    execute_qqcc_draw_scene_chain,
    resolve_qqcc_draw_chain_prompts,
    resolve_qqcc_draw_scene_chain,
    resolve_qqcc_draw_scene_task_type as _resolve_qqcc_draw_scene_task_type,
)
from src.services.qqcc_config_service import (
    get_qqcc_draw_scene,
    has_enabled_qqcc_draw_scenes,
    is_qqcc_main_button_enabled,
    is_qqcc_undress_method_enabled,
    load_runtime_qqcc_config,
    normalize_qqcc_config,
    resolve_qqcc_prompt,
)
from src.services.qqcc_runtime_context import (
    is_qqcc_bot_context as _is_qqcc_bot_context,
    load_qqcc_config_for_context as _load_qqcc_runtime_config_for_context,
)
from src.services.fsm_temp_file_service import (
    cleanup_fsm_temp_files,
    download_telegram_file_to_fsm_temp,
)
from src.services.wan22_video_v2_extension_service import download_output_file_to_fsm_temp
from src.utils import (
    create_background_task,
    load_prompts,
    robust_edit_text,
    robust_reply_text,
)

from src.filters.i18n_filter import I18nFilter
from src.i18n.translator import get_text

logger = logging.getLogger("fsm.quick_image")

QUICK_UNDRESS_LEGACY_CALLBACK = "quick_undress_legacy"
QUICK_UNDRESS_I2I_DRAW_CALLBACK = "quick_undress_i2i_draw"
QQCC_AI_DRAW_TASK_TYPES = (
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
)
DEFAULT_I2I_DRAW_UNDRESS_PROMPT = (
    "全身广角镜头，保持面部五官、脸型、发型、表情和肤色不变，"
    "保持身体姿势不变。将衣服自然移除，生成真实皮肤质感和完整身体，"
    "不要改变人物身份，不要裁剪头部。"
)

# Map button text to mode
QUICK_MODES = {
    "menu.photo_edit_undress": MODE_UNDRESS,
    "menu.photo_edit_masturbation": MODE_MASTURBATION,
    "menu.photo_edit_random_faceswap": MODE_RANDOM_FACESWAP,
    "qqcc.menu.quick_faceswap": MODE_RANDOM_FACESWAP,
}


def _t(context: ContextTypes.DEFAULT_TYPE, key: str, **kwargs) -> str:
    translator = getattr(context, "t", None)
    if callable(translator):
        return translator(key, **kwargs)
    lang = getattr(context, "lang", None)
    if not lang and getattr(context, "user_data", None):
        lang = context.user_data.get("language_code")
    return get_text(key, lang or "zh", **kwargs)


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE, _user_id: int):
    context.user_data.pop("in_conversation", None)
    fsm_data = context.user_data.pop("quick_image_data", {})
    cleanup_fsm_temp_files([fsm_data.get("image_path")])


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


async def _reply_main_feature_disabled(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    text = _t(context, "system.feature_disabled")
    query = update.callback_query
    if query:
        await robust_edit_text(query.message, text, parse_mode="Markdown")
        return
    message = update.message or update.edited_message
    if message:
        await robust_reply_text(message, text, parse_mode="Markdown")


def _is_qqcc_quick_image_route_enabled(config: dict, route_key: str | None) -> bool:
    if route_key == "qqcc.menu.quick_faceswap":
        return is_qqcc_main_button_enabled(config, "quick_faceswap")
    if route_key == "menu.photo_edit_undress":
        return False
    if route_key == "menu.photo_edit_masturbation":
        return False
    if route_key == "menu.photo_edit_random_faceswap":
        return False
    return False


def _is_qqcc_quick_image_mode_enabled(config: dict, mode: str) -> bool:
    if mode == MODE_UNDRESS:
        return False
    if mode == MODE_I2I_DRAW:
        return False
    if mode == MODE_MASTURBATION:
        return False
    if mode == MODE_RANDOM_FACESWAP:
        return is_qqcc_main_button_enabled(config, "quick_faceswap")
    if mode == MODE_PORNMASTER_FLUX2_SINGLE_EDIT:
        return is_qqcc_main_button_enabled(
            config, "ai_draw"
        ) and has_enabled_qqcc_draw_scenes(config)
    if mode in (MODE_EDIT, MODE_IMG2IMG_LORA):
        return is_qqcc_main_button_enabled(
            config, "ai_draw"
        ) and has_enabled_qqcc_draw_scenes(config)
    return False


def _initialize_quick_image_context(
    context: ContextTypes.DEFAULT_TYPE, *, mode: str, cost: int
) -> None:
    context.user_data["in_conversation"] = f"QUICK_IMAGE_{mode}"
    context.user_data["quick_image_data"] = {
        "mode": mode,
        "cost": cost,
        "image_path": None,
    }


def _build_undress_method_keyboard(
    context: ContextTypes.DEFAULT_TYPE,
    config: dict | None = None,
) -> InlineKeyboardMarkup:
    config = normalize_qqcc_config(config)
    row = []
    if is_qqcc_undress_method_enabled(config, "legacy"):
        row.append(
            InlineKeyboardButton(
                    _t(context, "fsm.quick_image.undress_legacy_button"),
                    callback_data=QUICK_UNDRESS_LEGACY_CALLBACK,
            )
        )
    if is_qqcc_undress_method_enabled(config, "i2i_draw"):
        row.append(
            InlineKeyboardButton(
                    _t(context, "fsm.quick_image.undress_i2i_draw_button"),
                    callback_data=QUICK_UNDRESS_I2I_DRAW_CALLBACK,
            )
        )
    return InlineKeyboardMarkup([row] if row else [])


def _resolve_quick_image_start_message(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str,
    cost: int,
    mode_name: str | None = None,
) -> str:
    if mode == MODE_UNDRESS:
        return _t(context, "fsm.quick_image.undress_start", cost=cost)
    if mode == MODE_MASTURBATION:
        return _t(context, "fsm.quick_image.masturbation_start", cost=cost)
    if mode == MODE_RANDOM_FACESWAP:
        return _t(context, "fsm.quick_image.random_faceswap_start", cost=cost)
    if mode == MODE_I2I_DRAW:
        return _t(context, "fsm.quick_image.undress_i2i_draw_start", cost=cost)
    if mode in QQCC_AI_DRAW_TASK_TYPES:
        return _t(
            context,
            "fsm.quick_image.ai_draw_start",
            cost=cost,
            mode_name=mode_name or _t(context, "qqcc.menu.ai_draw"),
        )
    return _t(context, "fsm.quick_image.undress_start", cost=cost)


def _resolve_image_file_id(message) -> str | None:
    if message.document:
        if not message.document.mime_type.startswith("image/"):
            return None
        return message.document.file_id
    if message.photo:
        return message.photo[-1].file_id
    return None


async def _start_qqcc_draw_scene(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    qqcc_config: dict | None,
    scene_id: str | None,
) -> int:
    query = update.callback_query
    if query:
        await query.answer(
            text=_t(context, "fsm.common.task_initializing"),
            cache_time=2,
        )

    if qqcc_config is None or not is_qqcc_main_button_enabled(
        qqcc_config, "ai_draw"
    ):
        await _reply_qqcc_feature_disabled(update, context)
        return ConversationHandler.END

    scene = get_qqcc_draw_scene(qqcc_config, scene_id)
    if scene is None:
        await _reply_qqcc_feature_disabled(update, context)
        return ConversationHandler.END

    draw_chain = resolve_qqcc_draw_scene_chain(qqcc_config, scene)
    if not draw_chain:
        await _reply_qqcc_feature_disabled(update, context)
        return ConversationHandler.END

    mode = _resolve_qqcc_draw_scene_task_type(draw_chain[0])
    if not _is_qqcc_quick_image_mode_enabled(qqcc_config, mode):
        await _reply_qqcc_feature_disabled(update, context)
        return ConversationHandler.END

    cost = calculate_qqcc_draw_chain_cost(draw_chain)
    _initialize_quick_image_context(
        context,
        mode=mode,
        cost=cost,
    )
    context.user_data["quick_image_data"].update(
        {
            "scene_id": scene["id"],
            "mode_name": scene["name"],
            "prompt_override": scene["prompt"],
            "engine": scene.get("engine"),
            "lora_name": str(scene.get("lora_name") or ""),
        }
    )
    msg = _resolve_quick_image_start_message(
        context,
        mode=MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
        cost=cost,
        mode_name=scene["name"],
    )

    if query and query.message:
        await robust_reply_text(query.message, msg, parse_mode="Markdown")
    else:
        message = update.message or update.edited_message
        if message:
            await robust_reply_text(message, msg, parse_mode="Markdown")
    return QuickImageState.WAIT_IMAGE


async def _validate_quick_image_submission(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    cost: int,
) -> bool:
    from src.core.user_core import get_or_create_user_by_telegram
    from src.core.exceptions import InsufficientCreditsError
    from src.utils import robust_send_message

    message = update.message
    internal_user, _ = await get_or_create_user_by_telegram(user_id)
    priority = await permission_service.calculate_user_priority(internal_user.id)
    if priority <= 0:
        await robust_reply_text(
            message,
            _t(context, "fsm.quick_image.priority_exhausted"),
        )
        _cleanup_context(context, user_id)
        return False

    user = update.effective_user
    if not user:
        return False

    try:
        await permission_service.check_quota(
            user.id, user.username, user.full_name, cost=cost
        )
    except Exception as exc:
        if not isinstance(exc, InsufficientCreditsError):
            raise
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
        _cleanup_context(context, user_id)
        return False
    return True


async def _download_quick_image_input(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    user_id: int,
) -> str | None:
    try:
        new_file = await context.bot.get_file(file_id)
        return await download_telegram_file_to_fsm_temp(
            telegram_file=new_file,
            suffix=".png",
            name_hint="quick_image",
        )
    except Exception as exc:
        logger.error("Error downloading image for FSM user %s: %s", user_id, exc)
        return None


def _build_random_faceswap_reply_markup(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton(
                _t(context, "fsm.quick_image.again_button"),
                callback_data="random_faceswap_again",
            )
        ],
        [
            InlineKeyboardButton("👍", callback_data="rate_like"),
            InlineKeyboardButton("👎", callback_data="rate_dislike"),
        ],
    ]
    if ENABLE_PUBLIC_SHARE:
        keyboard[0].insert(
            0,
            InlineKeyboardButton(
                _t(context, "fsm.quick_image.public_button"),
                callback_data="public_share_request",
            ),
        )
    return InlineKeyboardMarkup(keyboard)


def _resolve_random_faceswap_submission(
    *,
    prompts_config: dict,
    template_files: list[str],
    image_path: str,
) -> tuple[str, list[str], InlineKeyboardMarkup]:
    random_template = random.choice(template_files)
    template_path = f"template:{random_template}"
    prompt = prompts_config.get("face_swap", "face swap")
    return (
        prompt,
        [template_path, image_path],
        _build_random_faceswap_reply_markup,
    )


async def start_quick_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for single-step quick image flows."""
    user_id = update.effective_user.id
    message = update.message or update.edited_message
    query = update.callback_query
    draw_scene_id = parse_quick_draw_scene_callback_data(
        query.data if query else None
    )
    text = message.text.strip() if message and message.text else ""
    logger.info(
        f"start_quick_image triggered by user {user_id}, text: {text.encode('utf-8')}"
    )

    from src.utils import is_maintenance_mode

    if is_maintenance_mode():
        msg = _t(context, "fsm.common.maintenance")
        if query:
            await query.answer(text=msg, cache_time=2)
            await robust_edit_text(query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg, parse_mode="Markdown")
        return ConversationHandler.END

    if context.user_data.get("in_conversation"):
        msg = _t(context, "fsm.common.conflict")
        if query:
            await query.answer(text=msg, cache_time=2)
            await robust_edit_text(query.message, msg, parse_mode="Markdown")
        else:
            await robust_reply_text(update.message, msg)
        return ConversationHandler.END

    mode = None
    route_key = GLOBAL_REVERSE_MAP.get(text)
    qqcc_config = await _load_qqcc_config_for_context(context)
    if draw_scene_id:
        return await _start_qqcc_draw_scene(
            update,
            context,
            qqcc_config=qqcc_config,
            scene_id=draw_scene_id,
        )
    if qqcc_config is not None and not _is_qqcc_quick_image_route_enabled(
        qqcc_config, route_key
    ):
        await _reply_qqcc_feature_disabled(update, context)
        return ConversationHandler.END

    if qqcc_config is None and route_key in {
        "menu.photo_edit_undress",
        "menu.photo_edit_masturbation",
    }:
        await _reply_main_feature_disabled(update, context)
        return ConversationHandler.END

    if _is_qqcc_bot_context(context) and route_key == "menu.photo_edit_undress":
        context.user_data["in_conversation"] = "QUICK_IMAGE_UNDRESS_CHOICE"
        await robust_reply_text(
            update.message,
            _t(context, "fsm.quick_image.undress_choice_intro"),
            reply_markup=_build_undress_method_keyboard(context, qqcc_config),
            parse_mode="Markdown",
        )
        return QuickImageState.WAIT_UNDRESS_METHOD

    if route_key:
        mode = QUICK_MODES.get(route_key)

    if not mode:
        return ConversationHandler.END

    cost = TASK_COSTS.get(mode, 2)
    _initialize_quick_image_context(context, mode=mode, cost=cost)
    msg = (
        _t(context, "fsm.quick_image.quick_faceswap_start", cost=cost)
        if qqcc_config is not None and route_key == "qqcc.menu.quick_faceswap"
        else _resolve_quick_image_start_message(context, mode=mode, cost=cost)
    )

    await robust_reply_text(update.message, msg, parse_mode="Markdown")
    return QuickImageState.WAIT_IMAGE


async def select_undress_mode(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer(text=_t(context, "fsm.common.task_initializing"), cache_time=2)

    if context.user_data.get("in_conversation") != "QUICK_IMAGE_UNDRESS_CHOICE":
        await robust_edit_text(
            query.message,
            _t(context, "fsm.quick_image.expired_alert"),
            parse_mode="Markdown",
        )
        _cleanup_context(
            context,
            update.effective_user.id if update.effective_user else "Unknown",
        )
        return ConversationHandler.END

    qqcc_config = await _load_qqcc_config_for_context(context)
    if query.data == QUICK_UNDRESS_LEGACY_CALLBACK:
        if qqcc_config is not None and not _is_qqcc_quick_image_mode_enabled(
            qqcc_config, MODE_UNDRESS
        ):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(
                context,
                update.effective_user.id if update.effective_user else "Unknown",
            )
            return ConversationHandler.END
        mode = MODE_UNDRESS
        msg_key = "fsm.quick_image.undress_legacy_start"
    elif query.data == QUICK_UNDRESS_I2I_DRAW_CALLBACK:
        if qqcc_config is not None and not _is_qqcc_quick_image_mode_enabled(
            qqcc_config, MODE_I2I_DRAW
        ):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(
                context,
                update.effective_user.id if update.effective_user else "Unknown",
            )
            return ConversationHandler.END
        mode = MODE_I2I_DRAW
        msg_key = "fsm.quick_image.undress_i2i_draw_start"
    else:
        return QuickImageState.WAIT_UNDRESS_METHOD

    cost = TASK_COSTS.get(mode, 2)
    _initialize_quick_image_context(context, mode=mode, cost=cost)
    await robust_edit_text(
        query.message,
        _t(context, msg_key, cost=cost),
        parse_mode="Markdown",
    )
    return QuickImageState.WAIT_IMAGE


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    fsm_data = context.user_data["quick_image_data"]
    mode = fsm_data["mode"]
    cost = fsm_data["cost"]
    qqcc_config = await _load_qqcc_config_for_context(context)
    qqcc_draw_chain = []
    if qqcc_config is not None and mode in QQCC_AI_DRAW_TASK_TYPES:
        scene = get_qqcc_draw_scene(qqcc_config, fsm_data.get("scene_id"))
        if scene is None:
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        qqcc_draw_chain = resolve_qqcc_draw_scene_chain(qqcc_config, scene)
        if not qqcc_draw_chain:
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        mode = _resolve_qqcc_draw_scene_task_type(qqcc_draw_chain[0])
        if not _is_qqcc_quick_image_mode_enabled(qqcc_config, mode):
            await _reply_qqcc_feature_disabled(update, context)
            _cleanup_context(context, user_id)
            return ConversationHandler.END
        cost = calculate_qqcc_draw_chain_cost(qqcc_draw_chain)
        fsm_data["mode"] = mode
        fsm_data["cost"] = cost
        fsm_data["mode_name"] = scene["name"]
        fsm_data["prompt_override"] = scene["prompt"]
        fsm_data["engine"] = scene.get("engine")
        fsm_data["lora_name"] = str(scene.get("lora_name") or "")
    elif qqcc_config is not None and not _is_qqcc_quick_image_mode_enabled(
        qqcc_config, mode
    ):
        await _reply_qqcc_feature_disabled(update, context)
        _cleanup_context(context, user_id)
        return ConversationHandler.END

    file_id = _resolve_image_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "fsm.common.invalid_image"))
        return QuickImageState.WAIT_IMAGE

    if not await _validate_quick_image_submission(
        update=update,
        context=context,
        user_id=user_id,
        cost=cost,
    ):
        return ConversationHandler.END

    fsm_data["image_path"] = await _download_quick_image_input(
        context=context,
        file_id=file_id,
        user_id=user_id,
    )
    if not fsm_data["image_path"]:
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return QuickImageState.WAIT_IMAGE

    image_path = fsm_data.pop("image_path", None)
    if not image_path:
        return ConversationHandler.END  # Prevent double submit

    submit_status_msg = await robust_reply_text(
        message, _t(context, "fsm.quick_image.submit", cost=cost)
    )
    submit_status_msg_id = getattr(submit_status_msg, "message_id", None)

    if qqcc_config is not None and qqcc_draw_chain:
        qqcc_draw_chain = resolve_qqcc_draw_chain_prompts(qqcc_config, qqcc_draw_chain)

    if mode == MODE_RANDOM_FACESWAP:
        from config import MINIO_TEMPLATE_BUCKET
        from src.services.storage import storage

        prompts_config = load_prompts()
        try:
            template_files = storage.list_objects(
                "quick_face/", bucket=MINIO_TEMPLATE_BUCKET
            )
            template_files = [
                f
                for f in template_files
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]
            if not template_files:
                await robust_reply_text(
                    message, _t(context, "fsm.quick_image.no_template")
                )
                _cleanup_context(context, user_id)
                return ConversationHandler.END

            prompt, swapped_images, reply_markup_builder = _resolve_random_faceswap_submission(
                prompts_config=prompts_config,
                template_files=template_files,
                image_path=image_path,
            )
            if qqcc_config is not None:
                prompt = resolve_qqcc_prompt(
                    qqcc_config,
                    "face_swap",
                    prompts_config,
                    "face swap",
                )
            reply_markup = reply_markup_builder(context)

            # Save face image path globally for "Again" button (outside FSM)
            context.user_data["last_face_image"] = image_path

            create_background_task(
                context,
                process_generation_task(
                    context=context,
                    chat_id=message.chat_id,
                    user_id=user_id,
                    username=update.effective_user.username,
                    prompt=prompt,
                    images=swapped_images,
                    task_type="face_swap",
                    reply_markup=reply_markup,
                    cleanup=False,  # Kept for "Again"
                ),
            )
        except Exception as e:
            logger.error(f"Error in random faceswap FSM: {e}", exc_info=True)
            await robust_reply_text(
                message, _t(context, "fsm.quick_image.system_error", error_msg=str(e))
            )

    else:
        # Single-image quick modes share the same task submission path.
        task_type = mode
        if qqcc_draw_chain:
            create_background_task(
                context,
                execute_qqcc_draw_scene_chain(
                    context=context,
                    chat_id=message.chat_id,
                    user_id=user_id,
                    username=update.effective_user.username,
                    image_path=image_path,
                    chain=qqcc_draw_chain,
                    status_msg_id=submit_status_msg_id,
                    process_generation_task_func=process_generation_task,
                    download_output_file_to_fsm_temp_func=download_output_file_to_fsm_temp,
                    final_send_result=True,
                    final_allow_contribute=True,
                    final_delete_status=True,
                ),
            )
        else:
            if mode in QQCC_AI_DRAW_TASK_TYPES:
                prompt = fsm_data.get("prompt_override", "").strip()
                fallback_prompt = prompt or mode
                prompt = prompt or fallback_prompt
            elif mode == MODE_I2I_DRAW:
                prompts_config = load_prompts()
                prompt_key = "i2i_draw_quick_undress"
                fallback_prompt = DEFAULT_I2I_DRAW_UNDRESS_PROMPT
                if qqcc_config is not None:
                    prompt = resolve_qqcc_prompt(
                        qqcc_config,
                        prompt_key,
                        prompts_config,
                        fallback_prompt,
                    )
                else:
                    prompt = prompts_config.get(prompt_key, fallback_prompt)
            else:
                prompts_config = load_prompts()
                prompt_key = mode
                fallback_prompt = mode
                if qqcc_config is not None:
                    prompt = resolve_qqcc_prompt(
                        qqcc_config,
                        prompt_key,
                        prompts_config,
                        fallback_prompt,
                    )
                else:
                    prompt = prompts_config.get(prompt_key, fallback_prompt)
            lora_name = (
                str(fsm_data.get("lora_name") or "")
                if mode == MODE_IMG2IMG_LORA
                else ""
            )
            task_kwargs = {
                "context": context,
                "chat_id": message.chat_id,
                "user_id": user_id,
                "username": update.effective_user.username,
                "prompt": prompt,
                "images": [image_path],
                "task_type": task_type,
                "cleanup": True,
            }
            if lora_name:
                task_kwargs["lora_name"] = lora_name
                task_kwargs["lora_strength"] = get_lora_default_strength(lora_name)
            create_background_task(
                context,
                process_generation_task(**task_kwargs),
            )

    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def cancel_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id
    msg = _t(context, "fsm.common.cancelled")
    await robust_reply_text(update.message, msg)
    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def timeout_conversation(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user_id = update.effective_user.id if update.effective_user else "Unknown"
    if update and update.message:
        await robust_reply_text(
            update.message,
            _t(context, "fsm.common.timeout"),
        )
    _cleanup_context(context, user_id)
    return ConversationHandler.END


async def unexpected_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text if update.message else ""
    if text and is_global_menu_command(text):
        route_key = GLOBAL_REVERSE_MAP.get(text)
        user_id = update.effective_user.id if update.effective_user else "Unknown"
        _cleanup_context(context, user_id)
        if route_key == "menu.switch_lang" and update.effective_user:
            from src.handlers.message_handler_runtime import toggle_user_language

            reply_text, reply_markup = await toggle_user_language(
                context, update.effective_user
            )
            await robust_reply_text(
                update.message, reply_text, reply_markup=reply_markup
            )
            return ConversationHandler.END
        await robust_reply_text(update.message, _t(context, "system.fsm_exit_hint"))
        return ConversationHandler.END

    await robust_reply_text(update.message, _t(context, "system.fsm_in_progress_hint"))
    return None


def get_quick_image_fsm_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                I18nFilter(
                    [
                        "menu.photo_edit_undress",
                        "menu.photo_edit_masturbation",
                        "menu.photo_edit_random_faceswap",
                        "qqcc.menu.quick_faceswap",
                    ]
                ),
                start_quick_image,
            ),
            CallbackQueryHandler(
                start_quick_image,
                pattern=QUICK_DRAW_SCENE_CALLBACK_PATTERN,
            ),
        ],
        states={
            QuickImageState.WAIT_UNDRESS_METHOD: [
                CallbackQueryHandler(
                    select_undress_mode,
                    pattern=(
                        f"^({QUICK_UNDRESS_LEGACY_CALLBACK}|"
                        f"{QUICK_UNDRESS_I2I_DRAW_CALLBACK})$"
                    ),
                ),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            QuickImageState.WAIT_IMAGE: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, receive_image),
                MessageHandler(
                    (filters.TEXT | filters.COMMAND) & ~filters.Regex(r"^/cancel$"),
                    unexpected_input,
                ),
            ],
            ConversationHandler.TIMEOUT: [
                MessageHandler(filters.ALL, timeout_conversation)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        conversation_timeout=300,
        name="quick_image_fsm",
        persistent=False,
    )
