import json
import logging
import os

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.database.models import GalleryPost, History
from src.handlers.callback_router import register_callback
from src.handlers.callbacks.gallery_callbacks_interactions import (
    handle_public_share_callback as handle_public_share_callback_impl,
    handle_rate_action as handle_rate_action_impl,
)
from src.lora_mapping import translate_tags
from src.services.storage import storage
from src.utils import (
    create_background_task,
    robust_delete_message,
    robust_edit_reply_markup,
    robust_send_photo,
    robust_send_video,
    safe_answer_query,
)
import contextlib

logger = logging.getLogger(__name__)

# Legacy note:
# The old TG "修仙市集" browsing/apply experience is no longer a usable product
# path. Keep this module focused on browsing/interactions only.


@register_callback("public_share")
async def public_share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_public_share_callback_impl(update, context)


@register_callback("rate_like")
async def rate_like_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_rate_action(update, context, 1)


@register_callback("rate_dislike")
async def rate_dislike_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_rate_action(update, context, -1)


async def handle_rate_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE, rating_value: int
):
    await handle_rate_action_impl(update, context, rating_value)


from src.core.gallery_core import (
    DuplicateInteractionError,
    GalleryCoreError,
    get_gallery_feed,
    process_submit_to_gallery_result,
    toggle_like,
)


class DummyBackgroundTasks:
    def __init__(self, context):
        self.context = context

    def add_task(self, func, *args, **kwargs):
        create_background_task(self.context, func(*args, **kwargs))


@register_callback("submit_gallery_")
async def submit_gallery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    task_id = data.replace("submit_gallery_", "")

    try:
        internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)

        media_type = "video" if query.message.video else "image"
        width, height, duration = None, None, None
        if media_type == "video":
            width = query.message.video.width
            height = query.message.video.height
            duration = query.message.video.duration
        elif query.message.photo:
            photo = query.message.photo[-1]
            width = photo.width
            height = photo.height

        bg_tasks = DummyBackgroundTasks(context)
        try:
            outcome = await process_submit_to_gallery_result(
                user_id=internal_user.id,
                task_id=task_id,
                width=width,
                height=height,
                duration=duration,
            )
            for effect_func, effect_args in outcome.side_effects:
                bg_tasks.add_task(effect_func, *effect_args)
            result = outcome.payload
            await safe_answer_query(
                query, text=f"🎉 {result['message']}", show_alert=True
            )
        except GalleryCoreError as e:
            await safe_answer_query(query, text=f"⚠️ {str(e)}", show_alert=True)
            return

        keyboard = []
        for row in query.message.reply_markup.inline_keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data == data:
                    new_row.append(
                        InlineKeyboardButton("✅ 已投稿至广场", callback_data="noop")
                    )
                else:
                    new_row.append(btn)
            keyboard.append(new_row)
        await robust_edit_reply_markup(
            query.message, reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Gallery submit error: {e}", exc_info=True)
        await safe_answer_query(query, text="❌ 投稿失败，请稍后再试", show_alert=True)


@register_callback("gallery_catmenu_")
async def gallery_catmenu_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    parts = data.split("_")
    sort_type = parts[2]

    keyboard = [
        [
            InlineKeyboardButton(
                "🌈 全部", callback_data=f"gallery_sort_{sort_type}_all"
            )
        ],
        [
            InlineKeyboardButton(
                "💎 高级图生视频", callback_data=f"gallery_sort_{sort_type}_ltxvid"
            )
        ],
        [
            InlineKeyboardButton(
                "🎭 幻想换脸", callback_data=f"gallery_sort_{sort_type}_i2ipro"
            )
        ],
        [
            InlineKeyboardButton(
                "🖼️ 自由P图", callback_data=f"gallery_sort_{sort_type}_edit"
            )
        ],
        [
            InlineKeyboardButton(
                "🎨 图生图(附加模型)", callback_data=f"gallery_sort_{sort_type}_imglora"
            )
        ],
        [
            InlineKeyboardButton(
                "🎬 自定义图生视频", callback_data=f"gallery_sort_{sort_type}_custvid"
            )
        ],
        [
            InlineKeyboardButton(
                "🌟 图生视频（附加模型）",
                callback_data=f"gallery_sort_{sort_type}_vidlora",
            )
        ],
    ]
    await robust_edit_reply_markup(
        query.message, reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await safe_answer_query(query)


@register_callback("gallery_sort_")
@register_callback("gallery_page_")
async def gallery_sort_page_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    with contextlib.suppress(Exception):
        await query.answer()
    data = query.data

    try:
        parts = data.split("_")
        sort_type = parts[2]

        if len(parts) >= 4 and parts[3] in [
            "all",
            "i2ipro",
            "edit",
            "custvid",
            "vidlora",
            "ltxvid",
            "imglora",
        ]:
            category = parts[3]
            page = int(parts[4]) if len(parts) > 4 else 0
        else:
            category = "all"
            page = int(parts[3]) if len(parts) > 3 else 0

        internal_user_id = None
        if sort_type == "mine":
            internal_user, _ = await get_or_create_user_by_telegram(
                update.effective_user.id
            )
            internal_user_id = internal_user.id

        # Use page + 1 since get_gallery_feed expects 1-based page, but bot uses 0-based page
        # And size 2 because bot fetches current and next to check has_next
        posts, _total = await get_gallery_feed(
            page=page + 1,
            size=2,
            category=category if category != "all" else None,
            sort_by=sort_type,
            user_id=internal_user_id,
        )

        if not posts:
            if page == 0:
                await safe_answer_query(
                    query, text="📭 当前排行榜空空如也，快去投稿吧！", show_alert=True
                )
            else:
                await safe_answer_query(query, text="没有更多内容了~", show_alert=True)
            return

        post = posts[0]
        has_next = len(posts) > 1

        async with AsyncSessionLocal() as session:
            hist_res = await session.execute(
                select(History).where(History.task_id == post.task_id)
            )
            history = hist_res.scalars().first()

            try:
                tags = json.loads(post.tags)
            except Exception:
                tags = []

            translated_tags = translate_tags(tags)

            tags_str = " ".join(translated_tags) if translated_tags else "无标签"

            spec_str = ""
            if post.media_type == "video":
                spec_str = (
                    f"{post.duration}秒 | {post.width}x{post.height}"
                    if post.duration
                    else "视频"
                )
            else:
                spec_str = (
                    f"图片 | {post.width}x{post.height}" if post.width else "图片"
                )

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
                    InlineKeyboardButton(
                        f"👍 赞 ({post.likes_count})",
                        callback_data=f"gallery_like_{post.id}_{sort_type}_{category}_{page}",
                    ),
                    InlineKeyboardButton(
                        f"👎 踩 ({post.dislikes_count})",
                        callback_data=f"gallery_dislike_{post.id}_{sort_type}_{category}_{page}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ 上一个",
                        callback_data=f"gallery_page_{sort_type}_{category}_{max(0, page - 1)}",
                    )
                    if page > 0
                    else InlineKeyboardButton("🚫", callback_data="noop"),
                    InlineKeyboardButton(
                        "下一个 ➡️",
                        callback_data=f"gallery_page_{sort_type}_{category}_{page + 1}",
                    )
                    if has_next
                    else InlineKeyboardButton("🚫", callback_data="noop"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_answer_query(query, text="正在加载中...")

        is_test_bot = os.getenv("BOT_TYPE") == "TEST"
        cached_file_id = getattr(post, "telegram_file_id", None)
        if is_test_bot:
            cached_file_id = None

        output_file = history.output_file if history else None
        media_bytes = None

        if not cached_file_id and output_file:
            media_bytes = storage.get_file_bytes(output_file)

        if not cached_file_id and not media_bytes:
            await robust_send_message(
                context.bot, query.message.chat_id, "❌ 抱歉，该文件已失效或被删除。"
            )
            return

        sent_msg = None
        try:
            if post.media_type == "video":
                media_to_send = cached_file_id if cached_file_id else media_bytes
                sent_msg = await robust_send_video(
                    context.bot,
                    query.message.chat_id,
                    video=media_to_send,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            else:
                media_to_send = cached_file_id if cached_file_id else media_bytes
                sent_msg = await robust_send_photo(
                    context.bot,
                    query.message.chat_id,
                    photo=media_to_send,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
        except Exception as e:
            if cached_file_id and "wrong file identifier" in str(e).lower():
                logger.warning(
                    "Cached file_id invalid, falling back to MinIO download..."
                )
                if output_file:
                    media_bytes = storage.get_file_bytes(output_file)
                if not media_bytes:
                    await robust_send_message(
                        context.bot,
                        query.message.chat_id,
                        "❌ 抱歉，该文件已失效或被删除。",
                    )
                    return
                if post.media_type == "video":
                    sent_msg = await robust_send_video(
                        context.bot,
                        query.message.chat_id,
                        video=media_bytes,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                    )
                else:
                    sent_msg = await robust_send_photo(
                        context.bot,
                        query.message.chat_id,
                        photo=media_bytes,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="HTML",
                    )
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
                    update_post = (
                        await session.execute(
                            select(GalleryPost).where(GalleryPost.id == post.id)
                        )
                    ).scalar_one_or_none()
                    if update_post:
                        update_post.telegram_file_id = new_file_id
                        await session.commit()

        await robust_delete_message(query.message)

    except Exception as e:
        logger.error(f"Error displaying gallery: {e}")
        await safe_answer_query(query, text="❌ 加载失败，请稍后再试", show_alert=True)


@register_callback("gallery_like_")
@register_callback("gallery_dislike_")
async def gallery_like_dislike_callback(
    update: Update, _context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    data = query.data
    action = "like" if data.startswith("gallery_like_") else "dislike"
    parts = data.split("_")
    post_id = int(parts[2])
    sort_type = parts[3] if len(parts) > 3 else "latest"
    category = parts[4] if len(parts) > 4 else "all"
    page = parts[5] if len(parts) > 5 else "1"

    try:
        internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)

        try:
            result = await toggle_like(internal_user.id, post_id, action)
        except DuplicateInteractionError as e:
            await safe_answer_query(query, text=f"⚠️ {str(e)}", show_alert=True)
            return
        except GalleryCoreError as e:
            await safe_answer_query(query, text=f"❌ {str(e)}", show_alert=True)
            return

        likes_count = result["likes_count"]
        dislikes_count = result["dislikes_count"]
        action_state = result.get("action_state")

        if action_state == "canceled":
            toast_text = "✅ 已取消点赞" if action == "like" else "✅ 已取消点踩"
        else:
            toast_text = "✅ 点赞成功！" if action == "like" else "✅ 点踩成功！"

        keyboard = []
        for row in query.message.reply_markup.inline_keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data and btn.callback_data.startswith(
                    f"gallery_like_{post_id}"
                ):
                    if action_state == "canceled":
                        new_text = f"👍 赞 ({likes_count})"
                    else:
                        if action == "like":
                            new_text = f"✅ 已赞 ({likes_count})"
                        else:
                            new_text = f"👍 赞 ({likes_count})"
                    new_row.append(
                        InlineKeyboardButton(
                            new_text,
                            callback_data=f"gallery_like_{post_id}_{sort_type}_{category}_{page}",
                        )
                    )
                elif btn.callback_data and btn.callback_data.startswith(
                    f"gallery_dislike_{post_id}"
                ):
                    if action_state == "canceled":
                        new_text = f"👎 踩 ({dislikes_count})"
                    else:
                        if action == "dislike":
                            new_text = f"✅ 已踩 ({dislikes_count})"
                        else:
                            new_text = f"👎 踩 ({dislikes_count})"
                    new_row.append(
                        InlineKeyboardButton(
                            new_text,
                            callback_data=f"gallery_dislike_{post_id}_{sort_type}_{category}_{page}",
                        )
                    )
                else:
                    new_row.append(btn)
            keyboard.append(new_row)

        caption_html = query.message.caption_html if query.message.caption_html else ""
        if caption_html:
            import re

            caption_html = re.sub(r"❤️ \d+(?=\s*\|)", f"❤️ {likes_count}", caption_html)
            caption_html = re.sub(
                r"👎 \d+(?=\s*\|)", f"👎 {dislikes_count}", caption_html
            )
            await query.message.edit_caption(
                caption=caption_html,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        await safe_answer_query(query, text=toast_text, show_alert=False)

    except BadRequest as e:
        error_msg = str(e).lower()
        if (
            "message to edit not found" in error_msg
            or "message is not modified" in error_msg
        ):
            logger.warning(f"Like/Dislike callback skipped editing: {e}")
            await safe_answer_query(
                query,
                text=toast_text if "toast_text" in locals() else "✅ 操作成功！",
                show_alert=False,
            )
        else:
            logger.error(f"BadRequest handling like/dislike: {e}")
            await safe_answer_query(
                query, text="❌ 操作失败，请稍后再试", show_alert=True
            )
    except Exception as e:
        logger.error(f"Error handling like/dislike: {e}")
        await safe_answer_query(query, text="❌ 操作失败，请稍后再试", show_alert=True)
