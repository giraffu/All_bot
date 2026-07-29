import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.constants import MODE_RANDOM_FACESWAP, TASK_COSTS
from src.core.user_core import get_or_create_user_by_telegram
from src.handlers.callback_router import register_callback
from src.services.task_service_generation_image import (
    process_standard_generation_task as process_generation_task,
)
from src.services.permission_service import permission_service
from src.services.qqcc_config_service import (
    is_qqcc_main_button_enabled,
    load_runtime_qqcc_config,
)
from src.services.qqcc_runtime_context import (
    load_qqcc_config_for_context as _load_qqcc_runtime_config_for_context,
)
from src.services.quick_image_submission_service import (
    QuickImageSubmissionPlan,
    QuickImageSubmissionReject,
    QuickImageSubmissionRejectReason,
    build_quick_image_submission_plan,
    list_quick_faceswap_template_files,
    run_quick_image_submission_plan,
)
from src.utils import (
    create_background_task,
    is_maintenance_mode,
    load_prompts,
    robust_send_message,
    safe_answer_query,
)

logger = logging.getLogger(__name__)


async def _load_qqcc_config_for_context(
    context: ContextTypes.DEFAULT_TYPE,
) -> dict | None:
    return await _load_qqcc_runtime_config_for_context(
        context,
        logger=logger,
        load_config_func=load_runtime_qqcc_config,
    )


def _is_qqcc_random_faceswap_enabled(config: dict) -> bool:
    return is_qqcc_main_button_enabled(config, "quick_faceswap")


@register_callback("noop")
async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)


@register_callback("set_")
@register_callback("editlora_select_")
@register_callback("lora_select_")
@register_callback("qvid_mode:")
@register_callback("qvid_start_")
@register_callback("confirm_ltx_video")
async def fsm_fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query, text="该交互步骤已过期或被取消，请重新发送指令。")


@register_callback("random_faceswap_again")
async def random_faceswap_again_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    # ⚠️ 必须在这里补充 answer_query，否则拆分后按钮会一直转圈
    await safe_answer_query(query)

    qqcc_config = await _load_qqcc_config_for_context(context)
    if qqcc_config is not None and not _is_qqcc_random_faceswap_enabled(qqcc_config):
        await robust_send_message(
            context.bot,
            query.message.chat_id,
            "功能暂未开放",
        )
        return

    if is_maintenance_mode():
        await robust_send_message(
            context.bot, query.message.chat_id, "⚠️ 服务器即将运维，暂停生成服务中"
        )
        return

    internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)
    priority = await permission_service.calculate_user_priority(internal_user.id)
    if priority <= 0:
        await robust_send_message(
            context.bot,
            query.message.chat_id,
            "⚠️ 道友，您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来或提升修为！",
        )
        return

    face_image_path = context.user_data.get("last_face_image")
    if not face_image_path:
        await robust_send_message(
            context.bot, query.message.chat_id, "❌ 找不到原始人脸图片，请重新发送。"
        )
        return

    cost = TASK_COSTS.get(MODE_RANDOM_FACESWAP, 2)
    if not update.effective_user:
        return
    user = update.effective_user
    try:
        await permission_service.check_quota(
            user.id, user.username, user.full_name, cost=cost
        )
    except Exception as e:
        from src.core.exceptions import InsufficientCreditsError

        if isinstance(e, InsufficientCreditsError):
            chat_id = update.effective_chat.id
            msg = f"🚫 **灵石不足**\n\n道友当前余额: `{e.current}` 灵石\n本次修炼需要: `{e.cost}` 灵石\n请联系管理员获取更多灵石。"
            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            return
        raise e

    chat_id = query.message.chat_id
    user_id = query.from_user.id
    username = query.from_user.username

    try:
        reply_markup = (
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔄 再来一张", callback_data="random_faceswap_again"
                        )
                    ],
                    [
                        InlineKeyboardButton("👍", callback_data="rate_like"),
                        InlineKeyboardButton("👎", callback_data="rate_dislike"),
                    ],
                ]
            )
            if qqcc_config is None
            else None
        )
        plan = build_quick_image_submission_plan(
            fsm_data={"mode": MODE_RANDOM_FACESWAP, "cost": cost},
            qqcc_config=qqcc_config,
            image_path=face_image_path,
            prompts_config=load_prompts(),
            template_files=list_quick_faceswap_template_files(),
            reply_markup=reply_markup,
        )
        if isinstance(plan, QuickImageSubmissionReject):
            if plan.reason == QuickImageSubmissionRejectReason.NO_TEMPLATE:
                await robust_send_message(
                    context.bot, chat_id, "❌ 系统错误：未找到身体模板。"
                )
            elif plan.reason == QuickImageSubmissionRejectReason.FEATURE_DISABLED:
                await robust_send_message(context.bot, chat_id, "功能暂未开放")
            else:
                await robust_send_message(context.bot, chat_id, "❌ 当前模式不可用。")
            return

        if not isinstance(plan, QuickImageSubmissionPlan):
            await robust_send_message(context.bot, chat_id, "❌ 当前模式不可用。")
            return

        create_background_task(
            context,
            run_quick_image_submission_plan(
                plan=plan,
                context=context,
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                status_msg_id=None,
                process_generation_task_func=process_generation_task,
            ),
        )
    except Exception as e:
        await robust_send_message(context.bot, chat_id, f"❌ 任务执行出错：{str(e)}")
