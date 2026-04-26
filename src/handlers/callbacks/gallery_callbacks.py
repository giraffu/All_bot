from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import json
import os
import logging
from sqlalchemy import select, desc
from sqlalchemy import update as sa_update
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from src.database.core import AsyncSessionLocal
from src.database.models import History, GalleryPost, UserInteraction, User
from src.core.user_core import get_or_create_user_by_telegram
from src.services.redis_client import redis_client
from src.services.storage import storage
from src.utils import (
    robust_send_message, robust_edit_text, robust_edit_reply_markup, 
    robust_edit_caption, safe_answer_query, create_background_task,
    robust_send_photo, robust_send_video, robust_delete_message
)
from config import ENABLE_PUBLIC_SHARE, MINIO_TEMPLATE_BUCKET, REQUIRED_CHANNEL_ID
from src.constants import MODE_NAME_MAP, FORBIDDEN_WORDS, MODE_RANDOM_FACESWAP
from src.handlers.callback_router import register_callback

logger = logging.getLogger(__name__)

@register_callback("public_share")
async def public_share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # 检查全局开关
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

        if query.message.caption and "⚠️ 公开确认" in query.message.caption:
            return
        
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
        
        confirmation_text = (
            "⚠️ **公开确认**\n\n"
            "您确定要公开此内容吗？\n"
            "确认后，该内容将被转发到 **宗门公告栏**，供所有道友瞻仰。"
        )
        
        if query.message.caption:
            if "⚠️ 公开确认" in query.message.caption:
                return
                
            try:
                await robust_edit_caption(
                    query.message,
                    caption=f"{query.message.caption}\n\n{confirmation_text}",
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            except Exception:
                await robust_edit_reply_markup(query.message, reply_markup=reply_markup)
        else:
            await robust_edit_reply_markup(query.message, reply_markup=reply_markup)
        return

    elif data == "public_share_cancel":
        await safe_answer_query(query)
        if query.message.reply_markup:
            first_btn = query.message.reply_markup.inline_keyboard[0][0]
            if first_btn.callback_data == "public_share_request":
                return
        
        if query.message.caption:
            if "⚠️ 公开确认" in query.message.caption:
                original_caption = query.message.caption.split("\n\n⚠️ 公开确认")[0].strip()
                try:
                    await robust_edit_caption(
                        query.message,
                        caption=original_caption,
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        keyboard = [
            [
                InlineKeyboardButton("公开", callback_data="public_share_request")
            ],
            [
                InlineKeyboardButton("👍", callback_data="rate_like"),
                InlineKeyboardButton("👎", callback_data="rate_dislike")
            ]
        ]
        msg_id = query.message.message_id
        meta = context.bot_data.get(f"msg_meta_{msg_id}")
        if meta and meta.get('mode_name') == MODE_NAME_MAP.get(MODE_RANDOM_FACESWAP):
            keyboard[0].append(InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again"))

        await robust_edit_reply_markup(query.message, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    elif data == "public_share":
        await safe_answer_query(query)
        if query.message.caption and "📢 **已同步至宗门公告**" in query.message.caption:
            return
        
        if query.message.reply_markup is None:
            return

        if not REQUIRED_CHANNEL_ID:
            await robust_send_message(context.bot, query.message.chat_id, "❌ 未加入宗门，无法转发。")
            return

        try:
            msg_id = query.message.message_id
            meta = context.bot_data.get(f"msg_meta_{msg_id}")
            
            original_caption = ""
            if query.message.caption:
                original_caption = query.message.caption.split("\n\n⚠️ 公开确认")[0].strip()
            
            final_caption = original_caption
            if meta:
                mode_name = meta.get('mode_name', '未知模式')
                prompt = meta.get('prompt', '无提示词')
                final_caption = f"✨ 模式：{mode_name}\n📝 提示词：{prompt}"
            
            sent = False
            try:
                await context.bot.copy_message(
                    chat_id=REQUIRED_CHANNEL_ID,
                    from_chat_id=query.message.chat_id,
                    message_id=msg_id,
                    caption=final_caption,
                    parse_mode="Markdown"
                )
                sent = True
            except Exception:
                pass
            
            if not sent:
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
                        async with AsyncSessionLocal() as session:
                            await session.execute(
                                sa_update(History).where(History.task_id == task_id).values(is_public=True)
                            )
                            await session.commit()
                    except Exception as e:
                        logger.error(f"Error updating is_public: {e}")

            await safe_answer_query(query, text="✅ 已公开并转发至宗门公告栏！", show_alert=True)
            
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

@register_callback("rate_like")
async def rate_like_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_rate_action(update, context, 1)

@register_callback("rate_dislike")
async def rate_dislike_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_rate_action(update, context, -1)

async def handle_rate_action(update: Update, context: ContextTypes.DEFAULT_TYPE, rating_value: int):
    query = update.callback_query
    msg_id = query.message.message_id
    meta = context.bot_data.get(f"msg_meta_{msg_id}")
    
    if not meta or "task_id" not in meta:
        await safe_answer_query(query, text="❌ 无法找到对应任务记录", show_alert=True)
        return
        
    task_id = meta["task_id"]
    data = query.data
    
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                sa_update(History).where(History.task_id == task_id).values(rating=rating_value)
            )
            await session.commit()
            
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
        logger.error(f"Error updating rating: {e}")
        await safe_answer_query(query, text="❌ 评价失败，请稍后再试", show_alert=True)

@register_callback("submit_gallery_")
async def submit_gallery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    task_id = data.replace("submit_gallery_", "")
    
    try:
        import re
        internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)

        can_submit = await redis_client.check_gallery_submit_limit(internal_user.id, limit=10)
        if not can_submit:
            await safe_answer_query(query, text="⚠️ 您今日的投稿次数已达 10 次上限，请明日再来~", show_alert=True)
            return

        async with AsyncSessionLocal() as session:
            existing = await session.execute(select(GalleryPost).where(GalleryPost.task_id == task_id))
            if existing.scalar_one_or_none():
                await safe_answer_query(query, text="⚠️ 您已经投稿过此内容啦！", show_alert=True)
                return
            
            hist_res = await session.execute(select(History).where(History.task_id == task_id))
            history = hist_res.scalar_one_or_none()
            if not history:
                await safe_answer_query(query, text="❌ 无法找到对应的任务记录，投稿失败", show_alert=True)
                return
            
            if getattr(history, 'allow_contribute', True) is False:
                await safe_answer_query(query, text="⚠️ 这是一键应用他人的模板生成的作品，为了保护原创，暂不支持再次投稿。", show_alert=True)
                return
            
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
            
            tags = []
            base_tag = MODE_NAME_MAP.get(history.type, history.type)
            if base_tag:
                tags.append(f"#{base_tag}")
            
            if history.prompt:
                match = re.search(r"\[模型:\s*(.*?)\]\s*(.*)", history.prompt, re.DOTALL)
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
            
        if history and history.output_file:
            parts = history.output_file.split("/")
            if len(parts) > 1 and parts[0] in ["bot-data", "comfyui-temp"]:
                bucket_name = parts[0]
                object_name = "/".join(parts[1:])
            elif "comfyui-temp" not in history.output_file and "bot-data" not in history.output_file:
                bucket_name = "comfyui-temp" if not "/" in history.output_file else "bot-data"
                object_name = history.output_file
            else:
                bucket_name = "bot-data"
                object_name = history.output_file
            
            r2_object_name = parts[-1]
            create_background_task(
                context,
                storage.async_copy_to_r2(bucket_name, object_name, r2_object_name)
            )

        await redis_client.increment_gallery_submit(internal_user.id)
            
        tags_str = " ".join(tags)
        await safe_answer_query(query, text=f"🎉 投稿成功！\n已自动添加标签：{tags_str}", show_alert=True)
        
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
        logger.error(f"Error submitting to gallery: {e}")
        await safe_answer_query(query, text="❌ 投稿失败，请稍后再试", show_alert=True)

@register_callback("gallery_catmenu_")
async def gallery_catmenu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    parts = data.split("_")
    sort_type = parts[2]
    
    keyboard = [
        [InlineKeyboardButton("🌈 全部", callback_data=f"gallery_sort_{sort_type}_all")],
        [InlineKeyboardButton("💎 高级图生视频", callback_data=f"gallery_sort_{sort_type}_ltxvid")],
        [InlineKeyboardButton("🎭 幻想换脸", callback_data=f"gallery_sort_{sort_type}_i2ipro")],
        [InlineKeyboardButton("🖼️ 自由P图", callback_data=f"gallery_sort_{sort_type}_edit")],
        [InlineKeyboardButton("🎨 图生图(附加模型)", callback_data=f"gallery_sort_{sort_type}_imglora")],
        [InlineKeyboardButton("🎬 自定义图生视频", callback_data=f"gallery_sort_{sort_type}_custvid")],
        [InlineKeyboardButton("🌟 图生视频（附加模型）", callback_data=f"gallery_sort_{sort_type}_vidlora")]
    ]
    await robust_edit_reply_markup(query.message, reply_markup=InlineKeyboardMarkup(keyboard))
    await safe_answer_query(query)

@register_callback("gallery_sort_")
@register_callback("gallery_page_")
async def gallery_sort_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    try:
        parts = data.split("_")
        sort_type = parts[2] 
        
        if len(parts) >= 4 and parts[3] in ['all', 'i2ipro', 'edit', 'custvid', 'vidlora', 'ltxvid', 'imglora']:
            category = parts[3]
            page = int(parts[4]) if len(parts) > 4 else 0
        else:
            category = 'all'
            page = int(parts[3]) if len(parts) > 3 else 0
        
        async with AsyncSessionLocal() as session:
            query_stmt = select(GalleryPost).options(selectinload(GalleryPost.user)).where(GalleryPost.is_active == True)
            
            if category != 'all':
                query_stmt = query_stmt.join(History, GalleryPost.task_id == History.task_id)
                if category == 'i2ipro':
                    query_stmt = query_stmt.where(History.type == 'i2i_pro')
                elif category == 'edit':
                    query_stmt = query_stmt.where(History.type.in_(['edit', 'quick_image']))
                elif category == 'imglora':
                    query_stmt = query_stmt.where(History.type == 'img2img_lora')
                elif category == 'custvid':
                    query_stmt = query_stmt.where(History.type == 'custom_video')
                elif category == 'vidlora':
                    query_stmt = query_stmt.where(History.type == 'video_lora')
                elif category == 'ltxvid':
                    query_stmt = query_stmt.where(History.type == 'ltx_video')
            
            if sort_type == "mine":
                internal_user, _ = await get_or_create_user_by_telegram(update.effective_user.id)
                query_stmt = query_stmt.where(GalleryPost.user_id == internal_user.id).order_by(desc(GalleryPost.created_at))
            elif sort_type == "likes":
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
            except Exception:
                tags = []
                
            from src.handlers.fsm.video_lora_fsm import LORA_MODELS as VIDEO_LORA_MODELS
            from src.handlers.fsm.edit_image_fsm import LORA_MODELS as IMAGE_LORA_MODELS
            
            ALL_LORA_MODELS = {**VIDEO_LORA_MODELS, **IMAGE_LORA_MODELS}
            translated_tags = []
            for tag in tags:
                raw_tag = tag.strip("#")
                if raw_tag in ALL_LORA_MODELS:
                    translated_tags.append(f"#{ALL_LORA_MODELS[raw_tag]}")
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
                    InlineKeyboardButton(f"👍 赞 ({post.likes_count})", callback_data=f"gallery_like_{post.id}_{sort_type}_{category}_{page}"),
                    InlineKeyboardButton(f"👎 踩 ({post.dislikes_count})", callback_data=f"gallery_dislike_{post.id}_{sort_type}_{category}_{page}")
                ],
                [
                    InlineKeyboardButton("🪄 一键应用此模板", callback_data=f"gallery_apply_{post.id}")
                ],
                [
                    InlineKeyboardButton("⬅️ 上一个", callback_data=f"gallery_page_{sort_type}_{category}_{max(0, page-1)}") if page > 0 else InlineKeyboardButton("🚫", callback_data="noop"),
                    InlineKeyboardButton("下一个 ➡️", callback_data=f"gallery_page_{sort_type}_{category}_{page+1}") if has_next else InlineKeyboardButton("🚫", callback_data="noop")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_answer_query(query, text="正在加载中...")
        
        is_test_bot = os.getenv("BOT_TYPE") == "TEST"
        cached_file_id = getattr(post, 'telegram_file_id', None)
        if is_test_bot:
            cached_file_id = None
            
        output_file = history.output_file if history else None
        media_bytes = None
        
        if not cached_file_id and output_file:
            media_bytes = storage.get_file_bytes(output_file)
            
        if not cached_file_id and not media_bytes:
            await robust_send_message(context.bot, query.message.chat_id, "❌ 抱歉，该文件已失效或被删除。")
            return
            
        sent_msg = None
        try:
            if post.media_type == "video":
                media_to_send = cached_file_id if cached_file_id else media_bytes
                sent_msg = await robust_send_video(context.bot, query.message.chat_id, video=media_to_send, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
            else:
                media_to_send = cached_file_id if cached_file_id else media_bytes
                sent_msg = await robust_send_photo(context.bot, query.message.chat_id, photo=media_to_send, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            if cached_file_id and "wrong file identifier" in str(e).lower():
                logger.warning("Cached file_id invalid, falling back to MinIO download...")
                if output_file:
                    media_bytes = storage.get_file_bytes(output_file)
                if not media_bytes:
                    await robust_send_message(context.bot, query.message.chat_id, "❌ 抱歉，该文件已失效或被删除。")
                    return
                if post.media_type == "video":
                    sent_msg = await robust_send_video(context.bot, query.message.chat_id, video=media_bytes, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
                else:
                    sent_msg = await robust_send_photo(context.bot, query.message.chat_id, photo=media_bytes, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
                cached_file_id = None
            else:
                raise e
            
        if sent_msg and not cached_file_id and not is_test_bot:
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
        logger.error(f"Error displaying gallery: {e}")
        await safe_answer_query(query, text="❌ 加载失败，请稍后再试", show_alert=True)

@register_callback("gallery_like_")
@register_callback("gallery_dislike_")
async def gallery_like_dislike_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    action = "like" if data.startswith("gallery_like_") else "dislike"
    parts = data.split("_")
    post_id = int(parts[2])
    
    try:
        internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)

        async with AsyncSessionLocal() as session:
            post = (await session.execute(select(GalleryPost).where(GalleryPost.id == post_id))).scalar_one_or_none()
            if not post:
                await safe_answer_query(query, text="❌ 帖子已失效", show_alert=True)
                return
            
            existing = (await session.execute(
                select(UserInteraction)
                .where(UserInteraction.user_id == internal_user.id)
                .where(UserInteraction.post_id == post_id)
                .where(UserInteraction.action_type.in_(["like", "dislike"]))
            )).scalars().all()
            
            if existing:
                for ex in existing:
                    if ex.action_type == action:
                        await safe_answer_query(query, text=f"⚠️ 您已经{'点过赞' if action == 'like' else '点过踩'}啦！", show_alert=True)
                        return
                await safe_answer_query(query, text="⚠️ 互斥操作：您已经给过评价了！", show_alert=True)
                return
                
            interaction = UserInteraction(user_id=internal_user.id, post_id=post.id, action_type=action)
            session.add(interaction)
            
            if action == "like":
                await session.execute(sa_update(GalleryPost).where(GalleryPost.id == post.id).values(likes_count=GalleryPost.likes_count + 1))
                post.likes_count += 1
            else:
                await session.execute(sa_update(GalleryPost).where(GalleryPost.id == post.id).values(dislikes_count=GalleryPost.dislikes_count + 1))
                post.dislikes_count += 1
                
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                await safe_answer_query(query, text="⚠️ 重复操作：您已经给过评价了！", show_alert=True)
                return
            
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
        logger.error(f"Error handling like/dislike: {e}")
        await safe_answer_query(query, text="❌ 操作失败，请稍后再试", show_alert=True)
