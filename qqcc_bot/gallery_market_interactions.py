from __future__ import annotations

import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.gallery_core import (
    DuplicateInteractionError,
    GalleryCoreError,
    toggle_like,
)
from src.core.user_core import get_or_create_user_by_telegram
from src.utils import safe_answer_query

logger = logging.getLogger("qqcc_bot.gallery_market.interactions")

QG_LIKE_PREFIX = "qg:l:"
QG_DISLIKE_PREFIX = "qg:d:"
SORT_CODE_TO_SORT_BY = {
    "new": "latest",
    "hot": "absolute_likes",
    "app": "applied",
}


def parse_market_reaction_callback_data(
    data: str,
    prefix: str,
    *,
    known_type_codes: set[str],
) -> tuple[int, str, str, int]:
    post_id, type_code, sort_code, page = data.removeprefix(prefix).split(":", 3)
    if type_code not in known_type_codes:
        type_code = "all"
    if sort_code not in SORT_CODE_TO_SORT_BY:
        sort_code = "new"
    return int(post_id), type_code, sort_code, max(0, int(page))


def replace_caption_count(
    caption: str,
    *,
    likes_count: int,
    dislikes_count: int,
) -> str:
    caption = re.sub(r"赞 \d+", f"赞 {likes_count}", caption)
    return re.sub(r"踩 \d+", f"踩 {dislikes_count}", caption)


async def handle_market_reaction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    action: str,
    known_type_codes: set[str],
    get_or_create_user_func=get_or_create_user_by_telegram,
    toggle_like_func=toggle_like,
):
    query = update.callback_query
    prefix = QG_LIKE_PREFIX if action == "like" else QG_DISLIKE_PREFIX
    try:
        post_id, type_code, sort_code, page = parse_market_reaction_callback_data(
            query.data,
            prefix,
            known_type_codes=known_type_codes,
        )
        internal_user, _ = await get_or_create_user_func(query.from_user.id)
        result = await toggle_like_func(internal_user.id, post_id, action)
        likes_count = int(result.get("likes_count", 0))
        dislikes_count = int(result.get("dislikes_count", 0))

        keyboard = []
        for row in query.message.reply_markup.inline_keyboard:
            next_row = []
            for button in row:
                if button.callback_data and button.callback_data.startswith(QG_LIKE_PREFIX):
                    next_row.append(
                        InlineKeyboardButton(
                            f"赞 ({likes_count})",
                            callback_data=(
                                f"{QG_LIKE_PREFIX}{post_id}:{type_code}:{sort_code}:{page}"
                            ),
                        )
                    )
                elif button.callback_data and button.callback_data.startswith(QG_DISLIKE_PREFIX):
                    next_row.append(
                        InlineKeyboardButton(
                            f"踩 ({dislikes_count})",
                            callback_data=(
                                f"{QG_DISLIKE_PREFIX}{post_id}:{type_code}:{sort_code}:{page}"
                            ),
                        )
                    )
                else:
                    next_row.append(button)
            keyboard.append(next_row)

        caption = query.message.caption_html or query.message.caption or ""
        if caption:
            await query.message.edit_caption(
                caption=replace_caption_count(
                    caption,
                    likes_count=likes_count,
                    dislikes_count=dislikes_count,
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

        state = result.get("action_state")
        if action == "like":
            text = "已取消点赞" if state == "canceled" else "点赞成功"
        else:
            text = "已取消点踩" if state == "canceled" else "点踩成功"
        await safe_answer_query(query, text=text)
    except DuplicateInteractionError as exc:
        await safe_answer_query(query, text=str(exc), show_alert=True)
    except GalleryCoreError as exc:
        await safe_answer_query(query, text=str(exc), show_alert=True)
    except Exception:
        logger.exception("Failed to handle QQCC market reaction.")
        await safe_answer_query(query, text="操作失败，请稍后再试", show_alert=True)
