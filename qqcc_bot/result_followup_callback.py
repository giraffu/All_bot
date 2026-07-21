"""Follow a QQCC AI-draw result into another draw or a video scene."""

from __future__ import annotations

import secrets

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.exceptions import InsufficientCreditsError
from src.handlers.callback_router import register_callback
from src.services.fsm_temp_file_service import cleanup_fsm_temp_files
from src.services.permission_service import permission_service
from src.services.qqcc_config_service import (
    get_enabled_qqcc_ai_video_scenes,
    get_enabled_qqcc_draw_scenes,
    get_enabled_qqcc_video_scenes,
)
from src.services.qqcc_regenerate_metadata import QQCC_RESULT_FOLLOWUP_CALLBACK_PREFIX
from src.services.qqcc_regeneration_service import (
    QQCCRegenerationError,
    download_history_input_file_to_fsm_temp,
    load_owned_qqcc_regenerable_history,
    resolve_allowed_quick_video_resolutions,
)
from src.services.qqcc_runtime_context import load_qqcc_config_for_context
from src.services.quick_image_submission_service import (
    QuickImageSubmissionReject,
    build_quick_image_submission_plan,
    run_quick_image_submission_plan,
)
from src.services.quick_video_submission_service import (
    QuickVideoSubmissionReject,
    build_quick_video_submission_plan,
    run_quick_video_submission_plan,
)
from src.services.wan22_video_v2_extension_service import download_output_file_to_fsm_temp
from src.services.tg_task_result_presentation import resolve_task_id_from_callback_data
from src.utils import create_background_task, robust_reply_text, robust_send_message, safe_answer_query


_FOLLOWUP_KEY = "qqcc_result_followups"


def _scene_keyboard(*, token: str, scenes: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            str(scene["name"]),
            callback_data=f"{QQCC_RESULT_FOLLOWUP_CALLBACK_PREFIX}:s:{token}:{scene['id']}",
        )
        for scene in scenes
    ]
    return InlineKeyboardMarkup([buttons[index : index + 3] for index in range(0, len(buttons), 3)])


async def _load_seed(*, action: str, task_id: str, user, context) -> str:
    history = await load_owned_qqcc_regenerable_history(
        task_id=task_id, telegram_user_id=user.id, username=user.username
    )
    if action == "t":
        return await download_history_input_file_to_fsm_temp(
            history=history, index=0, name_hint="qqcc_followup_original"
        )
    output_file = str(getattr(history, "output_file", "") or "")
    if not output_file:
        raise QQCCRegenerationError("这条记录缺少可复用的生成图片。")
    return await download_output_file_to_fsm_temp(
        output_file=output_file, suffix=".png", name_hint="qqcc_followup_result"
    )


@register_callback(QQCC_RESULT_FOLLOWUP_CALLBACK_PREFIX)
async def qqcc_result_followup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query, user, chat = update.callback_query, update.effective_user, update.effective_chat
    if query is None or user is None or chat is None:
        return
    parts = str(query.data or "").split(":")
    if len(parts) < 3 or parts[0] != QQCC_RESULT_FOLLOWUP_CALLBACK_PREFIX:
        return
    action = parts[1]
    if action in {"t", "m", "v"}:
        task_id = resolve_task_id_from_callback_data(query.data, f"{QQCC_RESULT_FOLLOWUP_CALLBACK_PREFIX}:{action}")
        try:
            seed = await _load_seed(action=action, task_id=task_id, user=user, context=context)
            config = await load_qqcc_config_for_context(context)
            scenes = (
                get_enabled_qqcc_draw_scenes(config) if action == "t"
                else get_enabled_qqcc_video_scenes(config) if action == "m"
                else get_enabled_qqcc_ai_video_scenes(config)
            )
            if not scenes:
                raise QQCCRegenerationError("功能暂未开放或没有可用场景。")
            previous = context.user_data.pop(_FOLLOWUP_KEY, {})
            cleanup_fsm_temp_files([value.get("image_path") for value in previous.values() if isinstance(value, dict)])
            token = secrets.token_urlsafe(6)
            context.user_data[_FOLLOWUP_KEY] = {token: {"action": action, "image_path": seed}}
            labels = {"t": "请选择新的 AI 绘图主题", "m": "请选择 AI 动图场景", "v": "请选择 AI 视频场景"}
            await safe_answer_query(query)
            await robust_reply_text(query.message, labels[action], reply_markup=_scene_keyboard(token=token, scenes=scenes))
        except QQCCRegenerationError as exc:
            await safe_answer_query(query, text=str(exc), show_alert=True)
        except Exception:
            await safe_answer_query(query, text="暂时无法复用这张图片，请稍后再试", show_alert=True)
        return
    if action != "s" or len(parts) != 4:
        await safe_answer_query(query, text="操作已失效，请重新选择", show_alert=True)
        return
    pending = context.user_data.get(_FOLLOWUP_KEY, {}).pop(parts[2], None)
    if not pending:
        await safe_answer_query(query, text="操作已失效，请重新选择", show_alert=True)
        return
    image_path, source_action = pending["image_path"], pending["action"]
    try:
        config = await load_qqcc_config_for_context(context)
        if source_action == "t":
            plan = build_quick_image_submission_plan(
                fsm_data={"mode": "pornmaster_flux2_single_edit", "scene_id": parts[3], "scene_kind": "draw"},
                qqcc_config=config, image_path=image_path,
            )
        else:
            allowed = await resolve_allowed_quick_video_resolutions(telegram_user_id=user.id, username=user.username)
            plan = build_quick_video_submission_plan(
                fsm_data={"scene_id": parts[3], "scene_kind": "ai_video" if source_action == "v" else "video", "resolution": "512p", "duration": "5s"},
                qqcc_config=config, allowed_resolutions=allowed,
            )
        if isinstance(plan, (QuickImageSubmissionReject, QuickVideoSubmissionReject)):
            raise QQCCRegenerationError("场景已变更或暂未开放。")
        await permission_service.check_quota(user.id, user.username, user.full_name, cost=plan.total_cost)
        status = await robust_send_message(context.bot, chat.id, "正在生成，请耐心等待...")
        await safe_answer_query(query, text="任务已提交")
        if source_action == "t":
            create_background_task(context, run_quick_image_submission_plan(plan=plan, context=context, chat_id=chat.id, user_id=user.id, username=user.username, status_msg_id=status.message_id))
        else:
            create_background_task(context, run_quick_video_submission_plan(plan=plan, context=context, chat_id=chat.id, user_id=user.id, username=user.username, image_path=image_path, status_msg_id=status.message_id))
    except InsufficientCreditsError as exc:
        cleanup_fsm_temp_files([image_path])
        await safe_answer_query(query, text=f"灵石不足：当前 {exc.current}，需要 {exc.cost}", show_alert=True)
    except Exception:
        cleanup_fsm_temp_files([image_path])
        await safe_answer_query(query, text="任务提交失败，请稍后再试", show_alert=True)
