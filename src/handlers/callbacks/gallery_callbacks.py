import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.handlers.callback_router import register_callback
from src.handlers.callbacks.gallery_callbacks_browse import (
    display_gallery_sort_page,
)
from src.handlers.callbacks.gallery_callbacks_interactions import (
    handle_gallery_like_dislike_callback as handle_gallery_like_dislike_callback_impl,
    handle_public_share_callback as handle_public_share_callback_impl,
    handle_rate_action as handle_rate_action_impl,
    handle_submit_gallery_callback as handle_submit_gallery_callback_impl,
)
from src.utils import safe_answer_query

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

@register_callback("submit_gallery_")
async def submit_gallery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_submit_gallery_callback_impl(update, context)


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
    try:
        await display_gallery_sort_page(update, context)
    except Exception as e:
        logger.error(f"Error displaying gallery: {e}")
        await safe_answer_query(
            update.callback_query, text="❌ 加载失败，请稍后再试", show_alert=True
        )


@register_callback("gallery_like_")
@register_callback("gallery_dislike_")
async def gallery_like_dislike_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await handle_gallery_like_dislike_callback_impl(update, context)
