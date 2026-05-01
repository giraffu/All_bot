import logging
import random

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import MINIO_TEMPLATE_BUCKET
from src.constants import MODE_RANDOM_FACESWAP, TASK_COSTS
from src.core.user_core import get_or_create_user_by_telegram
from src.handlers.callback_router import register_callback
from src.services.permission_service import permission_service
from src.services.storage import storage
from src.services.task_service import TaskService
from src.utils import (
    create_background_task,
    is_maintenance_mode,
    load_prompts,
    robust_send_message,
    safe_answer_query,
)

logger = logging.getLogger(__name__)

@register_callback("noop")
async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)

@register_callback("set_")
@register_callback("editlora_select_")
@register_callback("lora_select_")
@register_callback("qvid_start_")
async def fsm_fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query, text="该交互步骤已过期或被取消，请重新发送指令。")

@register_callback("random_faceswap_again")
async def random_faceswap_again_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    # ⚠️ 必须在这里补充 answer_query，否则拆分后按钮会一直转圈
    await safe_answer_query(query)
    
    if is_maintenance_mode():
        await robust_send_message(context.bot, query.message.chat_id, "⚠️ 服务器即将运维，暂停生成服务中")
        return

    internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)
    priority = await permission_service.calculate_user_priority(internal_user.id)
    if priority <= 0:
        await robust_send_message(context.bot, query.message.chat_id, "⚠️ 道友，您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来或提升修为！")
        return

    face_image_path = context.user_data.get('last_face_image')
    if not face_image_path:
        await robust_send_message(context.bot, query.message.chat_id, "❌ 找不到原始人脸图片，请重新发送。")
        return
    
    cost = TASK_COSTS.get(MODE_RANDOM_FACESWAP, 1)
    if not update.effective_user: return
    user = update.effective_user
    try:
        await permission_service.check_quota(user.id, user.username, user.full_name, cost=cost)
    except Exception as e:
        from src.core.exceptions import InsufficientCreditsError
        if isinstance(e, InsufficientCreditsError):
            chat_id = update.effective_chat.id
            msg = f"🚫 **灵石不足**\n\n道友当前余额: `{e.current}` 灵石\n本次修炼需要: `{e.cost}` 灵石\n请联系管理员获取更多灵石。"
            from src.utils import robust_send_message
            await robust_send_message(context.bot, chat_id, msg, parse_mode="Markdown")
            return
        raise e

    chat_id = query.message.chat_id
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.full_name
    prompts_config = load_prompts()

    try:
        template_files = storage.list_objects("quick_face/", bucket=MINIO_TEMPLATE_BUCKET)
        template_files = [f for f in template_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
        
        if not template_files:
            await robust_send_message(context.bot, chat_id, "❌ 系统错误：未找到身体模板。")
            return

        random_template = random.choice(template_files)
        template_path = f"template:{random_template}"
        
        prompt = prompts_config.get("face_swap", "face swap")
        swapped_images = [template_path, face_image_path] 
        
        reply_markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again")
            ],
            [
                InlineKeyboardButton("👍", callback_data="rate_like"),
                InlineKeyboardButton("👎", callback_data="rate_dislike")
            ]
        ])
        
        create_background_task(
            context,
            TaskService.process_generation_task(
                context, chat_id, user_id, username, 
                prompt, swapped_images, task_type="face_swap",
                reply_markup=reply_markup,
                cleanup=False
            )
        )
    except Exception as e:
        await robust_send_message(context.bot, chat_id, f"❌ 任务执行出错：{str(e)}")
