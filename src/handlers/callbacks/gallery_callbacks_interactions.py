import contextlib
import logging

from sqlalchemy import update as sa_update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import ENABLE_PUBLIC_SHARE, REQUIRED_CHANNEL_ID
from src.constants import FORBIDDEN_WORDS, MODE_NAME_MAP, MODE_RANDOM_FACESWAP
from src.database.core import AsyncSessionLocal
from src.database.models import History
from src.utils import (
    robust_edit_caption,
    robust_edit_reply_markup,
    robust_send_message,
    safe_answer_query,
)

logger = logging.getLogger(__name__)


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
