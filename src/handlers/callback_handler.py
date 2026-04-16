from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from config import ENABLE_PUBLIC_SHARE, MINIO_TEMPLATE_BUCKET, REQUIRED_CHANNEL_ID, WEBAPP_URL
from src.utils import (
    robust_send_message, robust_edit_text, load_prompts, 
    robust_edit_reply_markup, robust_edit_caption, safe_answer_query,
    is_maintenance_mode, create_background_task
)
from src.handlers.utils import with_db_logging_context
from src.services.task_service import TaskService
from src.services.permission_service import permission_service
from src.services.storage import storage
from src.constants import (
    MODE_UNDRESS, MODE_MASTURBATION, 
    MODE_NAME_MAP, MODE_RANDOM_FACESWAP,
    FORBIDDEN_WORDS, TASK_COSTS,
    get_video_settings_keyboard, RESOLUTION_COST, 
    RESOLUTION_PERMISSIONS, DURATION_PERMISSIONS, 
    DEFAULT_RESOLUTION, DEFAULT_DURATION, DURATION_MULTIPLIER,
    MODE_FACE_VIDEO_STEP1
)
import os
import random
import asyncio
import logging

logger = logging.getLogger(__name__)

@with_db_logging_context
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle callback queries from inline keyboards.
    """
    query = update.callback_query
    
    data = query.data
    
    # Do not answer immediately for public_share_request so we can show alert if needed
    if data != "public_share_request":
        await safe_answer_query(query) # Always answer to stop loading animation
    
    # Ensure user info is up to date
    await permission_service.ensure_user(update)

    if not ENABLE_PUBLIC_SHARE and data in ["public_share_request", "public_share", "public_share_cancel"]:
        await safe_answer_query(query, text="⚠️ 公开功能已关闭", show_alert=True)
        return
    
    if data == "public_share_request":
        # Check forbidden words
        msg_meta = context.bot_data.get(f"msg_meta_{query.message.message_id}", {})
        prompt = msg_meta.get("prompt", "")
        if prompt:
            prompt_lower = prompt.lower()
            for word in FORBIDDEN_WORDS:
                if word.lower() in prompt_lower:
                    await safe_answer_query(
                        query,
                        text=f"⚠️ 您的内容包含违禁词「{word}」，无法公开！",
                        show_alert=True
                    )
                    return
        
        await safe_answer_query(query) # Answer if no forbidden words

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
                InlineKeyboardButton("公开", callback_data="public_share_request")
            ],
            [
                InlineKeyboardButton("👍", callback_data="rate_like"),
                InlineKeyboardButton("👎", callback_data="rate_dislike")
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
                sent = True
            
            if sent:
                if meta and "task_id" in meta:
                    task_id = meta["task_id"]
                    try:
                        from sqlalchemy import update
                        from src.database.core import AsyncSessionLocal
                        from src.database.models import History
                        async with AsyncSessionLocal() as session:
                            await session.execute(
                                update(History).where(History.task_id == task_id).values(is_public=True)
                            )
                            await session.commit()
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).error(f"Error updating is_public: {e}")

            # Feedback to user
            await safe_answer_query(query, text="✅ 已公开并转发至宗门公告栏！", show_alert=True)
            
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
            
    elif data in ["rate_like", "rate_dislike"]:
        msg_id = query.message.message_id
        meta = context.bot_data.get(f"msg_meta_{msg_id}")
        if not meta or "task_id" not in meta:
            await safe_answer_query(query, text="❌ 无法找到对应任务记录", show_alert=True)
            return
            
        task_id = meta["task_id"]
        rating_value = 1 if data == "rate_like" else -1
        
        try:
            from sqlalchemy import update
            from src.database.core import AsyncSessionLocal
            from src.database.models import History
            
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(History).where(History.task_id == task_id).values(rating=rating_value)
                )
                await session.commit()
                
            # Update buttons to reflect choice
            keyboard = []
            for row in query.message.reply_markup.inline_keyboard:
                new_row = []
                for btn in row:
                    if btn.callback_data == "rate_like":
                        text = "✅ 已赞" if rating_value == 1 else "👍"
                        new_row.append(InlineKeyboardButton(text, callback_data="rate_like"))
                    elif btn.callback_data == "rate_dislike":
                        text = "✅ 已踩" if rating_value == -1 else "👎"
                        new_row.append(InlineKeyboardButton(text, callback_data="rate_dislike"))
                    else:
                        new_row.append(btn)
                keyboard.append(new_row)
                
            await robust_edit_reply_markup(query.message, reply_markup=InlineKeyboardMarkup(keyboard))
            
            await safe_answer_query(query, text="感谢您的评价，祝道友修为精进！", show_alert=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error updating rating: {e}")
            await safe_answer_query(query, text="❌ 评价失败，请稍后再试", show_alert=True)
            
    elif data.startswith("submit_gallery_"):
        task_id = data.replace("submit_gallery_", "")
        try:
            from sqlalchemy import select
            from src.database.core import AsyncSessionLocal
            from src.database.models import History, GalleryPost
            from src.core.user_core import get_or_create_user_by_telegram
            from src.constants import MODE_NAME_MAP
            import re
            import json

            internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)

            async with AsyncSessionLocal() as session:
                # Check if already posted
                existing = await session.execute(select(GalleryPost).where(GalleryPost.task_id == task_id))
                if existing.scalar_one_or_none():
                    await safe_answer_query(query, text="⚠️ 您已经投稿过此内容啦！", show_alert=True)
                    return
                
                # Get History
                hist_res = await session.execute(select(History).where(History.task_id == task_id))
                history = hist_res.scalar_one_or_none()
                if not history:
                    await safe_answer_query(query, text="❌ 无法找到对应的任务记录，投稿失败", show_alert=True)
                    return
                
                # Metadata
                media_type = 'video' if query.message.video else 'image'
                width, height, duration = None, None, None
                if media_type == 'video':
                    width = query.message.video.width
                    height = query.message.video.height
                    duration = query.message.video.duration
                elif query.message.photo:
                    photo = query.message.photo[-1]
                    width = photo.width
                    height = photo.height
                
                # Auto Tags
                tags = []
                base_tag = MODE_NAME_MAP.get(history.type, history.type)
                if base_tag:
                    tags.append(f"#{base_tag}")
                
                # Extract LoRA from prompt
                if history.prompt:
                    match = re.search(r"\[模型:\s*(.*?)\]", history.prompt)
                    if match:
                        lora_tag = match.group(1).strip()
                        tags.append(f"#{lora_tag}")
                        
                tags_json = json.dumps(tags, ensure_ascii=False)
                
                new_post = GalleryPost(
                    task_id=task_id,
                    user_id=internal_user.id,
                    media_type=media_type,
                    width=width,
                    height=height,
                    duration=duration,
                    tags=tags_json
                )
                session.add(new_post)
                await session.commit()
                
            tags_str = " ".join(tags)
            await safe_answer_query(query, text=f"🎉 投稿成功！\n已自动添加标签：{tags_str}", show_alert=True)
            
            # Update the button to "✅ 已投稿"
            keyboard = []
            for row in query.message.reply_markup.inline_keyboard:
                new_row = []
                for btn in row:
                    if btn.callback_data == data:
                        new_row.append(InlineKeyboardButton("✅ 已投稿至广场", callback_data="noop"))
                    else:
                        new_row.append(btn)
                keyboard.append(new_row)
            await robust_edit_reply_markup(query.message, reply_markup=InlineKeyboardMarkup(keyboard))
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error submitting to gallery: {e}")
            await safe_answer_query(query, text="❌ 投稿失败，请稍后再试", show_alert=True)
            
    elif data.startswith("gallery_sort_") or data.startswith("gallery_page_"):
        try:
            from sqlalchemy import select, desc
            from src.database.core import AsyncSessionLocal
            from src.database.models import GalleryPost, History, User
            from sqlalchemy.orm import selectinload
            from src.utils import robust_send_photo, robust_send_video, robust_delete_message
            import json

            # parse data: gallery_sort_latest, gallery_page_latest_0
            parts = data.split("_")
            sort_type = parts[2] # latest, likes, applied
            page = int(parts[3]) if len(parts) > 3 else 0
            
            async with AsyncSessionLocal() as session:
                query_stmt = select(GalleryPost).options(selectinload(GalleryPost.user)).where(GalleryPost.is_active == True)
                
                if sort_type == "likes":
                    query_stmt = query_stmt.order_by(desc(GalleryPost.likes_count), desc(GalleryPost.created_at))
                elif sort_type == "applied":
                    query_stmt = query_stmt.order_by(desc(GalleryPost.applied_count), desc(GalleryPost.created_at))
                else:
                    query_stmt = query_stmt.order_by(desc(GalleryPost.created_at))
                    
                query_stmt = query_stmt.offset(page).limit(2)
                result = await session.execute(query_stmt)
                posts = result.scalars().all()
                
                if not posts:
                    if page == 0:
                        await safe_answer_query(query, text="📭 当前排行榜空空如也，快去投稿吧！", show_alert=True)
                    else:
                        await safe_answer_query(query, text="没有更多内容了~", show_alert=True)
                    return
                    
                post = posts[0]
                has_next = len(posts) > 1
                
                hist_res = await session.execute(select(History).where(History.task_id == post.task_id))
                history = hist_res.scalar_one_or_none()
                
                try:
                    tags = json.loads(post.tags)
                except:
                    tags = []
                    
                # Translate LoRA model names in tags
                from src.handlers.fsm.video_lora_fsm import LORA_MODELS
                translated_tags = []
                for tag in tags:
                    # Tag format is usually "#Tag"
                    raw_tag = tag.strip("#")
                    if raw_tag in LORA_MODELS:
                        translated_tags.append(f"#{LORA_MODELS[raw_tag]}")
                    else:
                        translated_tags.append(tag)
                        
                tags_str = " ".join(translated_tags) if translated_tags else "无标签"
                
                spec_str = ""
                if post.media_type == "video":
                    spec_str = f"{post.duration}秒 | {post.width}x{post.height}" if post.duration else "视频"
                else:
                    spec_str = f"图片 | {post.width}x{post.height}" if post.width else "图片"
                    
                import html
                
                author_name = "佚名道友"
                if post.user:
                    author_name = post.user.username or f"道友_{post.user.id}"
                
                caption = (
                    f"🏆 <b>修仙界广场</b>\n\n"
                    f"👤 <b>作者</b>：{html.escape(author_name)}\n"
                    f"📝 <b>提示词</b>：<code>*** 已隐藏（可一键应用体验） ***</code>\n"
                    f"🏷 <b>标签</b>：{html.escape(tags_str)}\n"
                    f"📏 <b>规格</b>：{html.escape(spec_str)}\n\n"
                    f"❤️ {post.likes_count}  |  👎 {post.dislikes_count}  |  🪄 {post.applied_count} 次应用"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton(f"👍 赞 ({post.likes_count})", callback_data=f"gallery_like_{post.id}_{sort_type}_{page}"),
                        InlineKeyboardButton(f"👎 踩 ({post.dislikes_count})", callback_data=f"gallery_dislike_{post.id}_{sort_type}_{page}")
                    ],
                    [
                        InlineKeyboardButton("🪄 一键应用此模板", callback_data=f"gallery_apply_{post.id}")
                    ],
                    [
                        InlineKeyboardButton("⬅️ 上一个", callback_data=f"gallery_page_{sort_type}_{max(0, page-1)}") if page > 0 else InlineKeyboardButton("🚫", callback_data="noop"),
                        InlineKeyboardButton("下一个 ➡️", callback_data=f"gallery_page_{sort_type}_{page+1}") if has_next else InlineKeyboardButton("🚫", callback_data="noop")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

            await safe_answer_query(query, text="正在加载中...")
            
            # Fetch media - Use cached file_id if available to save bandwidth
            cached_file_id = getattr(post, 'telegram_file_id', None)
            output_file = history.output_file if history else None
            media_bytes = None
            
            if not cached_file_id and output_file:
                media_bytes = storage.get_file_bytes(output_file)
                
            if not cached_file_id and not media_bytes:
                await robust_send_message(context.bot, query.message.chat_id, "❌ 抱歉，该文件已失效或被删除。")
                return
                
            # Send new message and delete old one to refresh media
            sent_msg = None
            if post.media_type == "video":
                media_to_send = cached_file_id if cached_file_id else media_bytes
                sent_msg = await robust_send_video(context.bot, query.message.chat_id, video=media_to_send, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            else:
                media_to_send = cached_file_id if cached_file_id else media_bytes
                sent_msg = await robust_send_photo(context.bot, query.message.chat_id, photo=media_to_send, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
                
            # Cache the file_id if it was a new upload
            if sent_msg and not cached_file_id:
                new_file_id = None
                if post.media_type == "video" and sent_msg.video:
                    new_file_id = sent_msg.video.file_id
                elif post.media_type != "video" and sent_msg.photo:
                    new_file_id = sent_msg.photo[-1].file_id
                    
                if new_file_id:
                    async with AsyncSessionLocal() as session:
                        update_post = (await session.execute(select(GalleryPost).where(GalleryPost.id == post.id))).scalar_one_or_none()
                        if update_post:
                            update_post.telegram_file_id = new_file_id
                            await session.commit()
                            
            await robust_delete_message(query.message)
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error displaying gallery: {e}")
            await safe_answer_query(query, text="❌ 加载失败，请稍后再试", show_alert=True)
            
    elif data.startswith("gallery_like_") or data.startswith("gallery_dislike_"):
        try:
            from sqlalchemy import select
            from src.database.core import AsyncSessionLocal
            from src.database.models import GalleryPost, UserInteraction
            from src.core.user_core import get_or_create_user_by_telegram

            action = "like" if data.startswith("gallery_like_") else "dislike"
            parts = data.split("_")
            post_id = int(parts[2])
            sort_type = parts[3]
            page = int(parts[4])

            internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)

            async with AsyncSessionLocal() as session:
                post = (await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))).scalar_one_or_none()
                if not post:
                    await safe_answer_query(query, text="❌ 帖子已失效", show_alert=True)
                    return
                
                # Check duplicate
                existing = (await session.execute(
                    select(UserInteraction)
                    .where(UserInteraction.user_id == internal_user.id)
                    .where(UserInteraction.post_id == post_id)
                    .where(UserInteraction.action_type == action)
                )).scalar_one_or_none()
                
                if existing:
                    await safe_answer_query(query, text=f"⚠️ 您已经{'点过赞' if action == 'like' else '点过踩'}啦！", show_alert=True)
                    return
                    
                interaction = UserInteraction(user_id=internal_user.id, post_id=post.id, action_type=action)
                session.add(interaction)
                
                if action == "like":
                    post.likes_count += 1
                else:
                    post.dislikes_count += 1
                    
                await session.commit()
                
                # Update button text in place
                keyboard = []
                for row in query.message.reply_markup.inline_keyboard:
                    new_row = []
                    for btn in row:
                        if btn.callback_data == data:
                            new_text = f"✅ 已赞 ({post.likes_count})" if action == "like" else f"✅ 已踩 ({post.dislikes_count})"
                            new_row.append(InlineKeyboardButton(new_text, callback_data="noop"))
                        else:
                            new_row.append(btn)
                    keyboard.append(new_row)
                
                await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
                await safe_answer_query(query, text=f"✅ {'点赞' if action == 'like' else '点踩'}成功！", show_alert=False)
                
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error handling like/dislike: {e}")
            await safe_answer_query(query, text="❌ 操作失败，请稍后再试", show_alert=True)
            
    elif data == "random_faceswap_again":
        # Check maintenance mode for generation tasks
        if is_maintenance_mode():
            await robust_send_message(context.bot, query.message.chat_id, "⚠️ 服务器即将运维，暂停生成服务中")
            return

        # Check priority
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)
        priority = await permission_service.calculate_user_priority(internal_user.id)
        if priority <= 0:
            await robust_send_message(context.bot, query.message.chat_id, "⚠️ 道友，您的排队优先级已耗尽（或修为不足），今日已无法再凝聚灵力，请明日再来或提升修为！")
            return

        # "再来一张" (Random FaceSwap Again)
        face_image_path = context.user_data.get('last_face_image')
        if not face_image_path:
            await robust_send_message(context.bot, query.message.chat_id, "❌ 找不到原始人脸图片，请重新发送。")
            return
        
        # Permission check
        cost = TASK_COSTS.get(MODE_RANDOM_FACESWAP, 1)
        if not await permission_service.check_quota(update, context, cost=cost):
            return

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
            
            # Use create_background_task to prevent blocking the callback handler and avoid GC
            create_background_task(
                context,
                TaskService.process_generation_task(
                    context, chat_id, user_id, username, 
                    prompt, swapped_images, task_type="face_swap",
                    reply_markup=reply_markup,
                    cleanup=False # Do not cleanup because we might need the face image again
                )
            )
        except Exception as e:
            await robust_send_message(context.bot, chat_id, f"❌ 任务执行出错：{str(e)}")
    
    elif data == "recharge_stars_menu":
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        keyboard = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days > 0).order_by(MembershipPlan.price_stars.asc()))
            plans = result.scalars().all()
            for plan in plans:
                if getattr(plan, 'price_stars', 0) > 0:
                    keyboard.append([InlineKeyboardButton(f"⭐️ {plan.price_stars} - {plan.name} ({plan.identity_name})", callback_data=f"buy_star_plan_{plan.id}")])
                    
        keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data == "recharge_stars_credit_menu":
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        keyboard = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days == 0).order_by(MembershipPlan.price_stars.asc()))
            plans = result.scalars().all()
            for plan in plans:
                if getattr(plan, 'price_stars', 0) > 0:
                    keyboard.append([InlineKeyboardButton(f"⭐️ {plan.price_stars} Star 直购 {plan.reward_credits} 灵石", callback_data=f"buy_star_plan_{plan.id}")])
                    
        keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data == "recharge_back":
        webapp_url = WEBAPP_URL if 'WEBAPP_URL' in globals() and WEBAPP_URL else "https://pay.aivison.it.com/"
        keyboard = [
            [InlineKeyboardButton("💎 TON月卡套餐", web_app=WebAppInfo(url=webapp_url))],
            [InlineKeyboardButton("⭐️ Star月卡套餐", callback_data="recharge_stars_menu")],
            [InlineKeyboardButton("⭐️ Star直充灵石", callback_data="recharge_stars_credit_menu")],
            [InlineKeyboardButton("¥ 人民币充值月卡", callback_data="recharge_rmb_menu")],
            [InlineKeyboardButton("¥ 人民币直充灵石", callback_data="recharge_rmb_credit_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data == "recharge_rmb_menu":
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        keyboard = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days > 0).order_by(MembershipPlan.price_rmb.asc()))
            plans = result.scalars().all()
            for plan in plans:
                if getattr(plan, 'price_rmb', 0) > 0:
                    keyboard.append([InlineKeyboardButton(f"¥ {plan.price_rmb} - {plan.name} ({plan.identity_name})", callback_data=f"select_rmb_plan_{plan.id}")])
                    
        keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data == "recharge_rmb_credit_menu":
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        keyboard = []
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.is_active == True, MembershipPlan.duration_days == 0).order_by(MembershipPlan.price_rmb.asc()))
            plans = result.scalars().all()
            for plan in plans:
                if getattr(plan, 'price_rmb', 0) > 0:
                    keyboard.append([InlineKeyboardButton(f"¥ {plan.price_rmb} 直购 {plan.reward_credits} 灵石", callback_data=f"select_rmb_plan_{plan.id}")])
                    
        keyboard.append([InlineKeyboardButton("🔙 返回支付方式", callback_data="recharge_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data.startswith("select_rmb_plan_"):
        plan_id = int(data.split("_")[-1])
        keyboard = [
            [
                InlineKeyboardButton("🟦 支付宝付款 (便利)", callback_data=f"buy_rmb_plan_{plan_id}_alipay"),
                InlineKeyboardButton("🟩 微信付款", callback_data=f"buy_rmb_plan_{plan_id}_wxpay")
            ],
            [InlineKeyboardButton("🔙 返回套餐列表", callback_data="recharge_rmb_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_reply_markup(reply_markup=reply_markup)
        except Exception:
            pass

    elif data.startswith("buy_rmb_plan_"):
        import time
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan, Order
        from sqlalchemy import select
        from src.services.rmb_payment_service import RMBPaymentService
        
        parts = data.split("_")
        pay_type = parts[-1]
        plan_id = int(parts[-2])
        tg_id = query.from_user.id
        
        from src.core.user_core import get_or_create_user_by_telegram
        internal_user, _ = await get_or_create_user_by_telegram(tg_id)
        internal_user_id = internal_user.id
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
            plan = result.scalar_one_or_none()
            
            if not plan or getattr(plan, 'price_rmb', 0) <= 0:
                await safe_answer_query(query, text="❌ 找不到该套餐", show_alert=True)
                return
                
            # 尽早响应回调，清除按钮上的 loading，并修改文本提示正在生成订单
            await safe_answer_query(query, text="⏳ 正在为您生成支付链接...")
            
            try:
                await query.message.edit_text(
                    text="⏳ **正在与支付网关建立安全连接，获取专属收银台链接，请稍候...**\n"
                         "_(这通常需要 1~3 秒)_",
                    parse_mode="Markdown",
                    reply_markup=None
                )
            except Exception:
                pass
                
            # 先落库 PENDING 订单
            timestamp = int(time.time())
            out_trade_no = f"RMB_{tg_id}_{plan_id}_{timestamp}"
            
            new_order = Order(
                order_id=out_trade_no,
                telegram_id=internal_user_id,
                plan_id=plan_id,
                original_price=plan.price_rmb,
                final_price=plan.price_rmb,
                status="PENDING",
                tx_hash=out_trade_no
            )
            session.add(new_order)
            await session.commit()
            
            # 动态调整展示名称，避免出现“Star 直购”这种奇怪的名字
            if plan.duration_days == 0:
                # 直充灵石
                display_name = f"{plan.reward_credits} 灵石直充"
            else:
                # 月卡套餐
                display_name = f"{plan.identity_name} ({plan.duration_days}天)"
            
            # 向第三方发起请求
            pay_resp = await RMBPaymentService.create_payment_url(
                out_trade_no=out_trade_no,
                plan_name=display_name,
                amount=float(plan.price_rmb),
                pay_type=pay_type
            )
            
            if pay_resp and pay_resp.get("code") == 1 and pay_resp.get("data") and pay_resp["data"].get("payurl"):
                raw_pay_url = pay_resp["data"]["payurl"]
                
                # 修复易支付网关返回的链接中未进行 URL Encode 的问题
                import urllib.parse
                parsed = urllib.parse.urlparse(raw_pay_url)
                query_dict = urllib.parse.parse_qs(parsed.query)
                # 重新将参数进行标准的 urlencode
                encoded_query = urllib.parse.urlencode(query_dict, doseq=True)
                pay_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, encoded_query, parsed.fragment))
                
                keyboard = [
                    [InlineKeyboardButton("👉 点击前往付款", url=pay_url)],
                    [InlineKeyboardButton("🔙 返回充值菜单", callback_data="recharge_back")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                try:
                    pay_method_text = "🟦 支付宝 (Alipay)" if pay_type == "alipay" else "🟩 微信支付 (WeChat Pay)"
                    await query.message.edit_text(
                        text=f"💎 **合欢宗账房 - {display_name}**\n\n"
                             f"📝 **订单号**：`{out_trade_no}`\n"
                             f"💰 **支付金额**：`¥{plan.price_rmb}`\n"
                             f"💳 **支付方式**：{pay_method_text}\n\n"
                             f"⚠️ **注意事项**：\n"
                             f"• 请点击下方按钮前往安全收银台付款。\n"
                             f"• 支付完成后，大约需要 10-30 秒处理，系统会自动发送到账通知，无需刷新本页面。",
                        parse_mode="Markdown",
                        reply_markup=reply_markup
                    )
                except Exception:
                    pass
            else:
                error_msg = pay_resp.get("msg", "未知错误") if pay_resp else "请求无响应"
                await safe_answer_query(query, text=f"❌ 获取支付链接失败：{error_msg}", show_alert=True)
                
    elif data.startswith("buy_star_plan_"):
        from telegram import LabeledPrice
        import time
        from src.database.core import AsyncSessionLocal
        from src.database.models import MembershipPlan
        from sqlalchemy import select
        
        plan_id = int(data.split("_")[-1])
        user_id = query.from_user.id
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
            plan = result.scalar_one_or_none()
            
        if not plan or getattr(plan, 'price_stars', 0) <= 0:
            await safe_answer_query(query, text="❌ 找不到该套餐", show_alert=True)
            return
            
        # Payload 格式保持和 TON 一致，方便防重放。ORDER:{user_id}:{plan_id}:{timestamp}
        timestamp = int(time.time())
        payload = f"ORDER:{user_id}:{plan_id}:{timestamp}"
        
        title = f"💎 合欢宗账房 - {plan.name} ({plan.identity_name})"
        description = f"{plan.duration_days}天 | 赠 {plan.reward_credits} 永久灵石 | 身份：{plan.identity_name}"
        currency = "XTR"
        prices = [LabeledPrice(f"{plan.name}", plan.price_stars)]
        
        try:
            await context.bot.send_invoice(
                chat_id=query.message.chat_id,
                title=title,
                description=description,
                payload=payload,
                provider_token="",  # Telegram Stars 必须为空
                currency=currency,
                prices=prices
            )
        except Exception as e:
            await safe_answer_query(query, text=f"❌ 发送账单失败：{e}", show_alert=True)
