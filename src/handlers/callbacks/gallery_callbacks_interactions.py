import contextlib
import logging
import re

from sqlalchemy import update as sa_update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from config import ENABLE_PUBLIC_SHARE, REQUIRED_CHANNEL_ID
from src.constants import FORBIDDEN_WORDS, MODE_NAME_MAP, MODE_RANDOM_FACESWAP
from src.handlers.callback_router import register_callback
from src.core.gallery_core import (
    DuplicateInteractionError,
    GalleryCoreError,
    process_submit_to_gallery_result,
    toggle_like,
)
from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.database.models import History
from src.utils import (
    create_background_task,
    robust_edit_caption,
    robust_edit_reply_markup,
    robust_send_message,
    safe_answer_query,
)

logger = logging.getLogger(__name__)


class DummyBackgroundTasks:
    def __init__(self, context):
        self.context = context

    def add_task(self, func, *args, **kwargs):
        create_background_task(self.context, func(*args, **kwargs))


def _extract_gallery_submit_media_metadata(query) -> tuple[str, int | None, int | None, int | None]:
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
    return media_type, width, height, duration


def _build_gallery_submit_reply_markup(query, callback_data: str) -> InlineKeyboardMarkup:
    keyboard = []
    for row in query.message.reply_markup.inline_keyboard:
        new_row = []
        for btn in row:
            if btn.callback_data == callback_data:
                new_row.append(
                    InlineKeyboardButton("✅ 已投稿至广场", callback_data="noop")
                )
            else:
                new_row.append(btn)
        keyboard.append(new_row)
    return InlineKeyboardMarkup(keyboard)


def _build_gallery_reaction_reply_markup(
    *,
    inline_keyboard,
    post_id: int,
    action: str,
    action_state: str | None,
    likes_count: int,
    dislikes_count: int,
    sort_type: str,
    category: str,
    page: str,
) -> InlineKeyboardMarkup:
    keyboard = []
    for row in inline_keyboard:
        new_row = []
        for btn in row:
            if btn.callback_data and btn.callback_data.startswith(f"gallery_like_{post_id}"):
                if action_state == "canceled":
                    new_text = f"👍 赞 ({likes_count})"
                else:
                    new_text = (
                        f"✅ 已赞 ({likes_count})" if action == "like" else f"👍 赞 ({likes_count})"
                    )
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
                    new_text = (
                        f"✅ 已踩 ({dislikes_count})"
                        if action == "dislike"
                        else f"👎 踩 ({dislikes_count})"
                    )
                new_row.append(
                    InlineKeyboardButton(
                        new_text,
                        callback_data=f"gallery_dislike_{post_id}_{sort_type}_{category}_{page}",
                    )
                )
            else:
                new_row.append(btn)
        keyboard.append(new_row)
    return InlineKeyboardMarkup(keyboard)


async def handle_submit_gallery_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    data = query.data
    task_id = data.replace("submit_gallery_", "")

    try:
        internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)
        _media_type, width, height, duration = _extract_gallery_submit_media_metadata(
            query
        )

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
            await safe_answer_query(query, text=f"🎉 {result['message']}", show_alert=True)
        except GalleryCoreError as exc:
            await safe_answer_query(query, text=f"⚠️ {str(exc)}", show_alert=True)
            return

        await robust_edit_reply_markup(
            query.message,
            reply_markup=_build_gallery_submit_reply_markup(query, data),
        )

    except Exception as exc:
        logger.error(f"Gallery submit error: {exc}", exc_info=True)
        await safe_answer_query(query, text="❌ 投稿失败，请稍后再试", show_alert=True)


async def handle_gallery_like_dislike_callback(
    update: Update,
    _context: ContextTypes.DEFAULT_TYPE,
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
        except DuplicateInteractionError as exc:
            await safe_answer_query(query, text=f"⚠️ {str(exc)}", show_alert=True)
            return
        except GalleryCoreError as exc:
            await safe_answer_query(query, text=f"❌ {str(exc)}", show_alert=True)
            return

        likes_count = result["likes_count"]
        dislikes_count = result["dislikes_count"]
        action_state = result.get("action_state")
        toast_text = (
            "✅ 已取消点赞"
            if action == "like" and action_state == "canceled"
            else "✅ 已取消点踩"
            if action == "dislike" and action_state == "canceled"
            else "✅ 点赞成功！"
            if action == "like"
            else "✅ 点踩成功！"
        )

        reply_markup = _build_gallery_reaction_reply_markup(
            inline_keyboard=query.message.reply_markup.inline_keyboard,
            post_id=post_id,
            action=action,
            action_state=action_state,
            likes_count=likes_count,
            dislikes_count=dislikes_count,
            sort_type=sort_type,
            category=category,
            page=page,
        )

        caption_html = query.message.caption_html if query.message.caption_html else ""
        if caption_html:
            caption_html = re.sub(r"❤️ \d+(?=\s*\|)", f"❤️ {likes_count}", caption_html)
            caption_html = re.sub(r"👎 \d+(?=\s*\|)", f"👎 {dislikes_count}", caption_html)
            await query.message.edit_caption(
                caption=caption_html,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        else:
            await query.message.edit_reply_markup(reply_markup=reply_markup)

        await safe_answer_query(query, text=toast_text, show_alert=False)

    except BadRequest as exc:
        error_msg = str(exc).lower()
        if "message to edit not found" in error_msg or "message is not modified" in error_msg:
            logger.warning(f"Like/Dislike callback skipped editing: {exc}")
            await safe_answer_query(
                query,
                text=toast_text if "toast_text" in locals() else "✅ 操作成功！",
                show_alert=False,
            )
        else:
            logger.error(f"BadRequest handling like/dislike: {exc}")
            await safe_answer_query(query, text="❌ 操作失败，请稍后再试", show_alert=True)
    except Exception as exc:
        logger.error(f"Error handling like/dislike: {exc}")
        await safe_answer_query(query, text="❌ 操作失败，请稍后再试", show_alert=True)


async def handle_public_share_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    data = query.data

    if not ENABLE_PUBLIC_SHARE and data in [
        "public_share_request",
        "public_share",
        "public_share_cancel",
    ]:
        await safe_answer_query(query, text="⚠️ 公开功能已关闭", show_alert=True)
        return

    if data == "public_share_request":
        msg_meta = context.bot_data.get(f"msg_meta_{query.message.message_id}", {})
        prompt = msg_meta.get("prompt", "")
        if prompt:
            prompt_lower = prompt.lower()
            for word in FORBIDDEN_WORDS:
                if word.lower() in prompt_lower:
                    await safe_answer_query(
                        query,
                        text=f"⚠️ 您的内容包含违禁词「{word}」，无法公开！",
                        show_alert=True,
                    )
                    return

        await safe_answer_query(query)

        if query.message.caption and "⚠️ 公开确认" in query.message.caption:
            return

        if not query.message.caption and query.message.reply_markup:
            first_btn = query.message.reply_markup.inline_keyboard[0][0]
            if first_btn.callback_data == "public_share":
                return

        keyboard = [
            [
                InlineKeyboardButton("✅ 确认公开", callback_data="public_share"),
                InlineKeyboardButton("❌ 取消", callback_data="public_share_cancel"),
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
                    parse_mode="Markdown",
                )
            except Exception:
                await robust_edit_reply_markup(query.message, reply_markup=reply_markup)
        else:
            await robust_edit_reply_markup(query.message, reply_markup=reply_markup)
        return

    if data == "public_share_cancel":
        await safe_answer_query(query)
        if query.message.reply_markup:
            first_btn = query.message.reply_markup.inline_keyboard[0][0]
            if first_btn.callback_data == "public_share_request":
                return

        if query.message.caption and "⚠️ 公开确认" in query.message.caption:
            original_caption = query.message.caption.split("\n\n⚠️ 公开确认")[0].strip()
            with contextlib.suppress(Exception):
                await robust_edit_caption(
                    query.message, caption=original_caption, parse_mode="Markdown"
                )

        keyboard = [
            [InlineKeyboardButton("公开", callback_data="public_share_request")],
            [
                InlineKeyboardButton("👍", callback_data="rate_like"),
                InlineKeyboardButton("👎", callback_data="rate_dislike"),
            ],
        ]
        msg_id = query.message.message_id
        meta = context.bot_data.get(f"msg_meta_{msg_id}")
        if meta and meta.get("mode_name") == MODE_NAME_MAP.get(MODE_RANDOM_FACESWAP):
            keyboard[0].append(
                InlineKeyboardButton("🔄 再来一张", callback_data="random_faceswap_again")
            )

        await robust_edit_reply_markup(
            query.message, reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if data == "public_share":
        await safe_answer_query(query)
        if query.message.caption and "📢 **已同步至宗门公告**" in query.message.caption:
            return

        if query.message.reply_markup is None:
            return

        if not REQUIRED_CHANNEL_ID:
            await robust_send_message(
                context.bot, query.message.chat_id, "❌ 未加入宗门，无法转发。"
            )
            return

        try:
            msg_id = query.message.message_id
            meta = context.bot_data.get(f"msg_meta_{msg_id}")

            original_caption = ""
            if query.message.caption:
                original_caption = query.message.caption.split("\n\n⚠️ 公开确认")[0].strip()

            final_caption = original_caption
            if meta:
                mode_name = meta.get("mode_name", "未知模式")
                prompt = meta.get("prompt", "无提示词")
                final_caption = f"✨ 模式：{mode_name}\n📝 提示词：{prompt}"

            sent = False
            try:
                await context.bot.copy_message(
                    chat_id=REQUIRED_CHANNEL_ID,
                    from_chat_id=query.message.chat_id,
                    message_id=msg_id,
                    caption=final_caption,
                    parse_mode="Markdown",
                )
                sent = True
            except Exception as exc:
                logger.warning(
                    "gallery copy_message fallback to forward_message for msg_id=%s: %s",
                    msg_id,
                    exc,
                )

            if not sent:
                await context.bot.forward_message(
                    chat_id=REQUIRED_CHANNEL_ID,
                    from_chat_id=query.message.chat_id,
                    message_id=query.message.message_id,
                )
                sent = True

            if sent and meta and "task_id" in meta:
                task_id = meta["task_id"]
                try:
                    async with AsyncSessionLocal() as session:
                        await session.execute(
                            sa_update(History)
                            .where(History.task_id == task_id)
                            .values(is_public=True)
                        )
                        await session.commit()
                except Exception as e:
                    logger.error(f"Error updating is_public: {e}")

            await safe_answer_query(
                query, text="✅ 已公开并转发至宗门公告栏！", show_alert=True
            )

            try:
                await robust_edit_caption(
                    query.message,
                    caption=f"{original_caption}\n\n📢 **已同步至宗门公告**",
                    reply_markup=None,
                    parse_mode="Markdown",
                )
            except Exception:
                await robust_edit_reply_markup(query.message, reply_markup=None)

        except Exception as e:
            await robust_send_message(
                context.bot, query.message.chat_id, f"❌ 转发失败: {e}"
            )


async def handle_rate_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE, rating_value: int
):
    query = update.callback_query
    msg_id = query.message.message_id
    meta = context.bot_data.get(f"msg_meta_{msg_id}")

    if not meta or "task_id" not in meta:
        await safe_answer_query(query, text="❌ 无法找到对应任务记录", show_alert=True)
        return

    task_id = meta["task_id"]

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(
                sa_update(History)
                .where(History.task_id == task_id)
                .values(rating=rating_value)
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
                    new_row.append(
                        InlineKeyboardButton(text, callback_data="rate_dislike")
                    )
                else:
                    new_row.append(btn)
            keyboard.append(new_row)

        await robust_edit_reply_markup(
            query.message, reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await safe_answer_query(
            query, text="感谢您的评价，祝道友修为精进！", show_alert=False
        )
    except Exception as e:
        logger.error(f"Error updating rating: {e}")
        await safe_answer_query(query, text="❌ 评价失败，请稍后再试", show_alert=True)


@register_callback("public_share")
async def public_share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_public_share_callback(update, context)


@register_callback("rate_like")
async def rate_like_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_rate_action(update, context, 1)


@register_callback("rate_dislike")
async def rate_dislike_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_rate_action(update, context, -1)


@register_callback("submit_gallery_")
async def submit_gallery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_submit_gallery_callback(update, context)


@register_callback("gallery_like_")
@register_callback("gallery_dislike_")
async def gallery_like_dislike_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await handle_gallery_like_dislike_callback(update, context)
