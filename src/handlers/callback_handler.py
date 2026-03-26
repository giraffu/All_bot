from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import REQUIRED_CHANNEL_ID
from src.utils import (
    robust_send_message, robust_edit_text, load_prompts, 
    robust_edit_reply_markup, robust_edit_caption
)
from src.handlers.utils import with_db_logging_context
from src.constants import (
    MODE_UNDRESS, MODE_MASTURBATION, 
    MODE_NAME_MAP, MODE_RANDOM_FACESWAP,
    FORBIDDEN_WORDS
)
from src.services.task_service import TaskService
from src.services.permission_service import permission_service
import os
import random
import asyncio

@with_db_logging_context
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle callback queries from inline keyboards.
    """
    query = update.callback_query
    
    data = query.data
    
    # Do not answer immediately for public_share_request so we can show alert if needed
    if data != "public_share_request":
        await query.answer() # Always answer to stop loading animation
    
    # Ensure user info is up to date
    await permission_service.ensure_user(update)
    
    if data == "public_share_request":
        # Check forbidden words
        msg_meta = context.bot_data.get(f"msg_meta_{query.message.message_id}", {})
        prompt = msg_meta.get("prompt", "")
        if prompt:
            prompt_lower = prompt.lower()
            for word in FORBIDDEN_WORDS:
                if word.lower() in prompt_lower:
                    await query.answer(
                        text=f"⚠️ 您的内容包含违禁词「{word}」，无法公开！",
                        show_alert=True
                    )
                    return
        
        await query.answer() # Answer if no forbidden words

        # Show confirmation menu
        # Check if already in confirmation state
        if query.message.caption and "⚠️ 公开确认" in query.message.caption:
            return
        
        # Check if markup is already the confirmation markup
        # If no caption, we check the first button text
        if not query.message.caption and query.message.reply_markup:
            first_btn = query.message.reply_markup.inline_keyboard[0][0]
            if first_btn.callback_data == "public_share":
                return

        keyboard = [
            [
                InlineKeyboardButton("✅ 确认公开", callback_data="public_share"),
                InlineKeyboardButton("❌ 取消", callback_data="public_share_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Explain what happens
        confirmation_text = (
            "⚠️ **公开确认**\n\n"
            "您确定要公开此内容吗？\n"
            "确认后，该内容将被转发到 **宗门公告栏**，供所有道友瞻仰。"
        )
        
        # We use robust_edit_reply_markup but also need to change text if possible
        # However, for images/videos, we can only edit the caption.
        if query.message.caption:
            # Check for rendered text (no **)
            if "⚠️ 公开确认" in query.message.caption:
                return # Already showing confirmation
                
            try:
                await robust_edit_caption(
                    query.message,
                    caption=f"{query.message.caption}\n\n{confirmation_text}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception:
                # Fallback if editing caption fails
                await robust_edit_reply_markup(query.message, reply_markup=reply_markup)
        else:
            await robust_edit_reply_markup(query.message, reply_markup=reply_markup)
        return

    elif data == "public_share_cancel":
        # Check if already in cancelled state (original keyboard)
        # If the first button is "public_share_request", it's already in original state.
        if query.message.reply_markup:
            first_btn = query.message.reply_markup.inline_keyboard[0][0]
            if first_btn.callback_data == "public_share_request":
                return
        
        # Restore original caption (remove confirmation text)
        if query.message.caption:
            if "⚠️ 公开确认" not in query.message.caption:
                # Caption doesn't have confirmation, maybe already restored
                pass
            else:
                original_caption = query.message.caption.split("\n\n⚠️ 公开确认")[0].strip()
                try:
                    await robust_edit_caption(
                        query.message,
                        caption=original_caption,
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        # Restore original keyboard
        keyboard = [
            [
                InlineKeyboardButton("公开", callback_data="public_share_request"),
                InlineKeyboardButton("私密", callback_data="private_keep")
            ]
        ]
        # Some modes might have "🔄 再来一张"
        msg_id = query.message.message_id
        meta = context.bot_data.get(f"msg_meta_{msg_id}")
        if meta and meta.get('mode_name') == MODE_NAME_MAP.get(MODE_RANDOM_FACESWAP):
            keyboard[0].append(InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again"))

        await robust_edit_reply_markup(query.message, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data == "public_share":
        # Check if already shared
        if query.message.caption and "📢 **已同步至宗门公告**" in query.message.caption:
            return
        
        # Check if markup is already None
        if query.message.reply_markup is None:
            return

        # Forward to channel
        if not REQUIRED_CHANNEL_ID:
            await robust_send_message(context.bot, query.message.chat_id, "❌ 未加入宗门，无法转发。")
            return

        try:
            msg_id = query.message.message_id
            meta = context.bot_data.get(f"msg_meta_{msg_id}")
            
            # Extract clean caption (remove confirmation text if exists)
            # Use split without ** because Telegram rendered text doesn't have it
            original_caption = ""
            if query.message.caption:
                original_caption = query.message.caption.split("\n\n⚠️ 公开确认")[0].strip()
            
            # Reconstruct caption from meta if available, else use original_caption
            final_caption = original_caption
            if meta:
                mode_name = meta.get('mode_name', '未知模式')
                prompt = meta.get('prompt', '无提示词')
                final_caption = f"✨ 模式：{mode_name}\n📝 提示词：{prompt}"
            
            sent = False
            try:
                # Use copy_message with clean caption
                await context.bot.copy_message(
                    chat_id=REQUIRED_CHANNEL_ID,
                    from_chat_id=query.message.chat_id,
                    message_id=msg_id,
                    caption=final_caption,
                    parse_mode="Markdown"
                )
                sent = True
            except Exception:
                # Fallback to forward_message if copy fails, but we should try to edit it after?
                # No, better to just use forward_message as absolute last resort
                pass
            
            if not sent:
                # Last resort fallback
                await context.bot.forward_message(
                    chat_id=REQUIRED_CHANNEL_ID,
                    from_chat_id=query.message.chat_id,
                    message_id=query.message.message_id
                )
            
            # Feedback to user
            await query.answer("✅ 已公开并转发至宗门公告栏！", show_alert=True)
            
            # Update the original message to remove buttons and show status
            try:
                await robust_edit_caption(
                    query.message,
                    caption=f"{original_caption}\n\n📢 **已同步至宗门公告**",
                    reply_markup=None,
                    parse_mode="Markdown"
                )
            except Exception:
                await robust_edit_reply_markup(query.message, reply_markup=None)
            
        except Exception as e:
            await robust_send_message(context.bot, query.message.chat_id, f"❌ 转发失败: {e}")
            
    elif data == "private_keep":
        # User chose private, do nothing (just answered query)
        pass
    
    elif data == "random_faceswap_again":
        # Check maintenance mode for generation tasks
        from src.utils import is_maintenance_mode
        if is_maintenance_mode():
            await robust_send_message(context.bot, query.message.chat_id, "⚠️ 服务器即将运维，暂停生成服务中")
            return

        # Check priority
        priority = await permission_service.calculate_user_priority(query.from_user.id)
        if priority <= 0:
            await robust_send_message(context.bot, query.message.chat_id, "⚠️ 道友，您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来或提升修为！")
            return

        # "再来一张" (Random FaceSwap Again)
        face_image_path = context.user_data.get('last_face_image')
        if not face_image_path:
            await robust_send_message(context.bot, query.message.chat_id, "❌ 找不到原始人脸图片，请重新发送。")
            return
        
        # Permission check
        if not await permission_service.check_quota(update, context, cost=2):
            return

        chat_id = query.message.chat_id
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.full_name
        prompts_config = load_prompts()

        try:
            from config import MINIO_TEMPLATE_BUCKET
            from src.services.storage import storage
            
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
                    InlineKeyboardButton("公开", callback_data="public_share_request"),
                    InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again")
                ]
            ])
            
            await TaskService.process_generation_task(
                context, chat_id, user_id, username, 
                prompt, swapped_images, task_type="face_swap",
                reply_markup=reply_markup,
                cleanup=False # Do not cleanup because we might need the face image again
            )
        except Exception as e:
            await robust_send_message(context.bot, chat_id, f"❌ 任务执行出错：{str(e)}")
    
    elif data == "batch_cancel":
        # Cancel Batch
        # Stop Timeout Task if exists
        if 'batch_timeout_task' in context.user_data:
             context.user_data['batch_timeout_task'].cancel()
        
        # Cleanup
        batch_images = context.user_data.get('batch_images', [])
        for p in batch_images:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        context.user_data['batch_images'] = []
        context.user_data.pop('batch_confirm_msg_id', None)
        
        await robust_edit_text(query.message, "🚫 **已停止任务，所有图片已清除**")
        
    elif data == "batch_confirm":
        # Check maintenance mode for generation tasks
        from src.utils import is_maintenance_mode
        if is_maintenance_mode():
            await robust_edit_text(query.message, "⚠️ 服务器即将运维，暂停生成服务中")
            return

        # Check priority
        priority = await permission_service.calculate_user_priority(query.from_user.id)
        if priority <= 0:
            await robust_edit_text(query.message, "⚠️ 道友，您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来或提升修为！")
            return

        # Confirm Batch
        # Stop Timeout Task
        if 'batch_timeout_task' in context.user_data:
             context.user_data['batch_timeout_task'].cancel()
        context.user_data.pop('batch_confirm_msg_id', None)

        # Use pop to ensure we only process this batch once even if double clicked
        batch_images = context.user_data.pop('batch_images', [])
        if not batch_images:
            # Check if we are already processing (optional, but good for UX)
            # If batch_images is empty, it might be because it's already being processed
            # or it was cancelled/timed out.
            return
            
        await robust_edit_text(query.message, f"🚀 **开始处理 {len(batch_images)} 个任务...**")
        
        mode = context.user_data.get('mode')
        prompts_config = load_prompts()
        
        # Prepare params
        chat_id = query.message.chat_id
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.full_name
        status_msg_id = query.message.message_id
        
        # Iterate
        total_count = len(batch_images)
        processed = 0
        
        # Logic specific to modes
        prompt = "undress"
        is_video = False
        task_type = "image"
        
        if mode == MODE_UNDRESS:
            prompt = prompts_config.get("undress", "undress")
            task_type = "undress"
        elif mode == MODE_MASTURBATION:
            prompt = prompts_config.get("masturbation", "masturbation")
            task_type = "masturbation"
        
        for img_path in batch_images:
            # Update Progress
            await robust_edit_text(query.message, f"🚀 **正在处理第 {processed+1}/{total_count} 个任务...**")
            
            # One by one
            await TaskService.process_generation_task(context, chat_id, user_id, username, prompt, [img_path], is_video=is_video, status_msg_id=status_msg_id, delete_status=False, task_type=task_type)
            processed += 1
            
            # Delay to prevent backend overload (422)
            await asyncio.sleep(2)
        
        # Done
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
        except Exception:
            pass

    elif data.startswith("set_res_") or data.startswith("set_dur_"):
        is_res = data.startswith("set_res_")
        new_val = data.replace("set_res_", "") if is_res else data.replace("set_dur_", "")
        from src.constants import get_video_settings_keyboard, RESOLUTION_COST, RESOLUTION_PERMISSIONS, DURATION_PERMISSIONS, DEFAULT_RESOLUTION, DEFAULT_DURATION, DURATION_MULTIPLIER
        
        user_group = await permission_service.get_user_group(query.from_user.id)
        user_identity = await permission_service.get_user_identity(query.from_user.id)
        
        if is_res:
            group_allowed = RESOLUTION_PERMISSIONS.get(user_group, ["512p"])
            identity_allowed = RESOLUTION_PERMISSIONS.get(user_identity, ["512p"])
        else:
            group_allowed = DURATION_PERMISSIONS.get(user_group, ["5s"])
            identity_allowed = DURATION_PERMISSIONS.get(user_identity, ["5s"])
        
        # Merge allowed values (take union and unique)
        allowed = list(set(group_allowed + identity_allowed))
        
        if new_val not in allowed:
            await query.answer(f"❌ 境界或身份不足，无法选择 {new_val}！", show_alert=True)
            return

        if is_res and new_val == "1024p":
            current_dur = context.user_data.get('custom_video_duration', DEFAULT_DURATION)
            if current_dur == "10s":
                await query.answer("❌ 无法同时选择 1024p 和 10s，请先降低时长！", show_alert=True)
                return
        elif not is_res and new_val == "10s":
            current_res = context.user_data.get('custom_video_resolution', DEFAULT_RESOLUTION)
            if current_res == "1024p":
                await query.answer("❌ 无法同时选择 1024p 和 10s，请先降低分辨率！", show_alert=True)
                return

        if is_res:
            context.user_data['custom_video_resolution'] = new_val
        else:
            context.user_data['custom_video_duration'] = new_val
            
        current_res = context.user_data.get('custom_video_resolution', DEFAULT_RESOLUTION)
        current_dur = context.user_data.get('custom_video_duration', DEFAULT_DURATION)
        
        # Determine highest allowed set for keyboard
        reply_markup = get_video_settings_keyboard(user_group, user_identity, current_res, current_dur)
        
        base_cost = RESOLUTION_COST.get(current_res, 6)
        multiplier = DURATION_MULTIPLIER.get(current_dur, 1.0)
        cost = int(base_cost * multiplier)
        
        try:
            # Try to update the text message as well if it exists
            if query.message.text:
                import re
                new_text = re.sub(r"(⚙️ 当前(?:自定义)?视频画质：).*? \| 时长：.*? \| 消耗灵石：\d+(?=\n|$)", f"\\g<1>{current_res} | 时长：{current_dur} | 消耗灵石：{cost}", query.message.text)
                # Fallback for old messages without cost string
                if new_text == query.message.text:
                     new_text = re.sub(r"(⚙️ 当前(?:自定义)?视频画质：).*? \| 时长：.*?(?=\n|$)", f"\\g<1>{current_res} | 时长：{current_dur} | 消耗灵石：{cost}", query.message.text)
                await query.message.edit_text(new_text, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await robust_edit_reply_markup(query.message, reply_markup=reply_markup)
        except Exception:
            pass
            
        await query.answer(f"已切换至 {current_res} ({current_dur})，灵石消耗 {cost}", show_alert=False)
