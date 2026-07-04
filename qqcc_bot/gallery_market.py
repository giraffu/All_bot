from __future__ import annotations

import html
import json
import logging
import re
import time
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import MINI_APP_URL, build_versioned_mini_app_url
from src.constants import (
    MODE_CUSTOM_VIDEO,
    MODE_EDIT,
    MODE_FACE_VIDEO_STEP1,
    MODE_FACE_VIDEO_STEP2,
    MODE_I2I_DRAW,
    MODE_I2I_PRO,
    MODE_IMAGE_TO_VIDEO,
    MODE_IMG2IMG_LORA,
    MODE_LTX_VIDEO,
    MODE_LTX_VIDEO_FLF2V,
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_ACTION_TRANSFER_LONG,
    MODE_SCAIL2_FACE_SWAP_V2,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
    MODE_WAN22_VIDEO_V2,
)
from src.core.gallery_core import (
    DuplicateInteractionError,
    GalleryCoreError,
    get_gallery_feed,
    toggle_like,
)
from src.core.user_core import get_or_create_user_by_telegram
from src.database.core import AsyncSessionLocal
from src.handlers.callback_router import register_callback
from src.lora_mapping import translate_tags
from src.services.fsm_temp_file_service import download_telegram_file_to_fsm_temp
from src.services.gallery_browse_service import (
    get_history_for_gallery_post,
    resolve_gallery_media_source,
    send_gallery_media_message,
)
from src.services.gallery_apply_context_service import (
    GalleryApplyContextError,
    build_gallery_apply_context_payload,
    default_should_return_gallery_apply_input_file,
    fetch_gallery_apply_context_entities,
    resolve_history_template_apply_disabled_reason,
)
from src.services.ltx_video_extension_service import (
    extract_ltx_history_context,
    is_ltx_stitched_result,
)
from src.services.task_service_entrypoints_generation import process_i2i_pro_task
from src.services.task_service_entrypoints_specialized import process_ltx_video_task
from src.services.task_service_generation_image import process_standard_generation_task
from src.services.task_service_generation_video import process_image_to_video_generation_task
from src.services.task_service_generation_wan22 import process_wan22_video_v2_generation_task
from src.services.wan22_video_v2_extension_service import (
    extract_wan22_history_context,
    is_wan22_stitched_result,
)
from src.utils import (
    robust_delete_message,
    robust_reply_text,
    robust_send_message,
    safe_answer_query,
)
from src.web_api.common.utils import (
    build_history_apply_context_response,
    build_storage_input_file_url,
    release_read_transaction,
)

logger = logging.getLogger("qqcc_bot.gallery_market")

QQCC_GALLERY_APPLY_SESSION_KEY = "qqcc_gallery_apply"
QQCC_GALLERY_APPLY_SESSION_TTL_SECONDS = 30 * 60

QG_MENU_CALLBACK = "qg:m"
QG_PAGE_PREFIX = "qg:p:"
QG_LIKE_PREFIX = "qg:l:"
QG_DISLIKE_PREFIX = "qg:d:"
QG_APPLY_PREFIX = "qg:a:"

SORT_CODE_TO_SORT_BY = {
    "new": "latest",
    "hot": "absolute_likes",
    "app": "applied",
}


@dataclass(frozen=True)
class MarketTab:
    code: str
    task_type: str | None
    label_key: str


QQCC_MARKET_TABS: tuple[MarketTab, ...] = (
    MarketTab("all", None, "qqcc.market.tabs.all"),
    MarketTab("i2ip", MODE_I2I_PRO, "qqcc.market.tabs.i2i_pro"),
    MarketTab("i2id", MODE_I2I_DRAW, "qqcc.market.tabs.i2i_draw"),
    MarketTab("edit", "edit_group", "qqcc.market.tabs.edit_group"),
    MarketTab("freev2", "free_edit_v2_group", "qqcc.market.tabs.free_edit_v2_group"),
    MarketTab("i2v", "img2video_group", "qqcc.market.tabs.img2video_group"),
    MarketTab("ltx", MODE_LTX_VIDEO, "qqcc.market.tabs.ltx_video"),
    MarketTab("wan22", MODE_WAN22_VIDEO_V2, "qqcc.market.tabs.wan22_video_v2"),
    MarketTab("sca", MODE_SCAIL2_ACTION_TRANSFER, "qqcc.market.tabs.scail2_action_transfer"),
    MarketTab("scr", MODE_SCAIL2_VIDEO_REPLACEMENT, "qqcc.market.tabs.scail2_video_replacement"),
    MarketTab("scf", MODE_SCAIL2_FACE_SWAP_V2, "qqcc.market.tabs.scail2_face_swap_v2"),
)

TAB_BY_CODE = {tab.code: tab for tab in QQCC_MARKET_TABS}
WEB_FALLBACK_TASK_TYPES = {
    MODE_PORNMASTER_FLUX2_MULTI_EDIT,
    MODE_LTX_VIDEO_FLF2V,
    MODE_SCAIL2_ACTION_TRANSFER,
    MODE_SCAIL2_ACTION_TRANSFER_LONG,
    MODE_SCAIL2_VIDEO_REPLACEMENT,
    MODE_SCAIL2_FACE_SWAP_V2,
}
WEB_ONLY_MARKET_TASK_TYPES = {
    "face_video",
    MODE_FACE_VIDEO_STEP1,
    MODE_FACE_VIDEO_STEP2,
    MODE_SCAIL2_FACE_SWAP_V2,
}
NATIVE_IMAGE_TASK_TYPES = {
    MODE_I2I_PRO,
    MODE_EDIT,
    MODE_IMG2IMG_LORA,
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT,
}
NATIVE_VIDEO_TASK_TYPES = {
    MODE_CUSTOM_VIDEO,
    MODE_IMAGE_TO_VIDEO,
    MODE_WAN22_VIDEO_V2,
    MODE_LTX_VIDEO,
}
TASK_TYPE_LABEL_KEYS = {
    MODE_I2I_PRO: "qqcc.market.tabs.i2i_pro",
    MODE_I2I_DRAW: "qqcc.market.tabs.i2i_draw",
    MODE_EDIT: "qqcc.market.tabs.edit_group",
    MODE_IMG2IMG_LORA: "task.mode_img2img_lora",
    MODE_PORNMASTER_FLUX2_SINGLE_EDIT: "qqcc.market.tabs.free_edit_v2_group",
    MODE_PORNMASTER_FLUX2_MULTI_EDIT: "qqcc.market.tabs.free_edit_v2_group",
    "face_video": "task.face_video",
    MODE_FACE_VIDEO_STEP1: "task.mode_face_video_step1",
    MODE_FACE_VIDEO_STEP2: "task.mode_face_video_step2",
    MODE_CUSTOM_VIDEO: "qqcc.market.tabs.img2video_group",
    MODE_IMAGE_TO_VIDEO: "qqcc.market.tabs.img2video_group",
    MODE_LTX_VIDEO: "qqcc.market.tabs.ltx_video",
    MODE_LTX_VIDEO_FLF2V: "qqcc.market.tabs.ltx_video",
    MODE_WAN22_VIDEO_V2: "qqcc.market.tabs.wan22_video_v2",
    MODE_SCAIL2_ACTION_TRANSFER: "qqcc.market.tabs.scail2_action_transfer",
    MODE_SCAIL2_ACTION_TRANSFER_LONG: "qqcc.market.tabs.scail2_action_transfer",
    MODE_SCAIL2_VIDEO_REPLACEMENT: "qqcc.market.tabs.scail2_video_replacement",
    MODE_SCAIL2_FACE_SWAP_V2: "qqcc.market.tabs.scail2_face_swap_v2",
    "edit_group": "qqcc.market.tabs.edit_group",
    "free_edit_v2_group": "qqcc.market.tabs.free_edit_v2_group",
    "img2video_group": "qqcc.market.tabs.img2video_group",
}


def _t(context, key: str, **kwargs) -> str:
    translator = getattr(context, "t", None)
    if callable(translator):
        return translator(key, **kwargs)
    return key.format(**kwargs) if kwargs else key


def _translated(context, key: str) -> str | None:
    value = _t(context, key)
    return value if value and value != key else None


def _tab_label(context, tab: MarketTab) -> str:
    return _t(context, tab.label_key)


def build_market_web_apply_url(post_id: int) -> str:
    web_origin = (MINI_APP_URL or "https://web.aivison.it.com/").rstrip("/")
    base_url = f"{web_origin}/gallery?apply_source=gallery&apply_id={post_id}"
    return build_versioned_mini_app_url(base_url=base_url)


def build_qqcc_gallery_market_menu_markup(
    *,
    context,
    sort_code: str = "new",
) -> InlineKeyboardMarkup:
    rows = []
    buttons = [
        InlineKeyboardButton(
            _tab_label(context, tab),
            callback_data=f"{QG_PAGE_PREFIX}{tab.code}:{sort_code}:0",
        )
        for tab in QQCC_MARKET_TABS
    ]
    rows.extend(buttons[index : index + 2] for index in range(0, len(buttons), 2))
    return InlineKeyboardMarkup(rows)


async def open_qqcc_gallery_market_menu(update, context):
    message = update.effective_message
    if not message:
        return None
    await robust_reply_text(
        message,
        f"{_t(context, 'qqcc.market.title')}\n\n{_t(context, 'qqcc.market.hint')}",
        reply_markup=build_qqcc_gallery_market_menu_markup(context=context),
    )
    return None


def parse_qqcc_market_page_callback_data(data: str) -> tuple[str, str, int]:
    try:
        type_code, sort_code, page = data.removeprefix(QG_PAGE_PREFIX).split(":", 2)
        if type_code not in TAB_BY_CODE:
            type_code = "all"
        if sort_code not in SORT_CODE_TO_SORT_BY:
            sort_code = "new"
        return type_code, sort_code, max(0, int(page))
    except Exception:
        return "all", "new", 0


def parse_qqcc_market_reaction_callback_data(data: str, prefix: str) -> tuple[int, str, str, int]:
    post_id, type_code, sort_code, page = data.removeprefix(prefix).split(":", 3)
    if type_code not in TAB_BY_CODE:
        type_code = "all"
    if sort_code not in SORT_CODE_TO_SORT_BY:
        sort_code = "new"
    return int(post_id), type_code, sort_code, max(0, int(page))


def parse_qqcc_market_apply_callback_data(data: str) -> int:
    return int(data.removeprefix(QG_APPLY_PREFIX))


def is_qqcc_gallery_apply_session_expired(session: dict, *, now: float | None = None) -> bool:
    created_at = float(session.get("created_at") or 0)
    return (now or time.time()) - created_at > QQCC_GALLERY_APPLY_SESSION_TTL_SECONDS


async def fetch_qqcc_market_page(
    *,
    type_code: str,
    sort_code: str,
    page: int,
    fetch_gallery_feed_func=get_gallery_feed,
):
    tab = TAB_BY_CODE.get(type_code, TAB_BY_CODE["all"])
    return await fetch_gallery_feed_func(
        page=page + 1,
        size=2,
        task_type=tab.task_type,
        sort_by=SORT_CODE_TO_SORT_BY.get(sort_code, "latest"),
    )


def _parse_tags(post) -> list[str]:
    raw_tags = getattr(post, "tags", None)
    if isinstance(raw_tags, list):
        return raw_tags
    try:
        parsed = json.loads(raw_tags or "[]")
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _author_name(post) -> str:
    user = getattr(post, "user", None)
    if user:
        return getattr(user, "username", None) or getattr(user, "full_name", None) or f"User {user.id}"
    user_id = getattr(post, "user_id", None)
    return f"User {user_id}" if user_id else "匿名修士"


def _history_type(history) -> str | None:
    return str(getattr(history, "type", "") or "").strip() or None


def _task_type_label(context, task_type: str | None) -> str:
    normalized = str(task_type or "").strip()
    if not normalized:
        return "unknown"

    explicit_key = TASK_TYPE_LABEL_KEYS.get(normalized)
    if explicit_key:
        explicit_label = _translated(context, explicit_key)
        if explicit_label:
            return explicit_label

    if normalized.startswith("task."):
        direct_label = _translated(context, normalized)
        if direct_label:
            return direct_label
        if normalized.startswith("task.mode_"):
            normalized = normalized.removeprefix("task.mode_")

    explicit_key = TASK_TYPE_LABEL_KEYS.get(normalized)
    if explicit_key:
        explicit_label = _translated(context, explicit_key)
        if explicit_label:
            return explicit_label

    inferred_label = _translated(context, f"task.mode_{normalized}")
    return inferred_label or normalized


def translate_market_tags(tags: list[str], *, context) -> list[str]:
    translated_tags = []
    for tag in tags:
        raw_tag = str(tag or "").strip()
        if not raw_tag:
            continue

        lora_tag = translate_tags([raw_tag])[0]
        if lora_tag != raw_tag:
            translated_tags.append(lora_tag)
            continue

        prefix = "#" if raw_tag.startswith("#") else ""
        tag_body = raw_tag[1:] if prefix else raw_tag
        label = _task_type_label(context, tag_body)
        translated_tags.append(f"{prefix}{label}" if label != tag_body else raw_tag)
    return translated_tags


def _is_stitched_market_history(history) -> bool:
    if history is None:
        return False
    extra_outputs = getattr(history, "extra_outputs", None)
    return is_wan22_stitched_result(extra_outputs) or is_ltx_stitched_result(extra_outputs)


def _is_web_only_market_history(history) -> bool:
    return _history_type(history) in WEB_ONLY_MARKET_TASK_TYPES


def resolve_qqcc_gallery_apply_mode(history) -> tuple[str, str | None]:
    if history is None:
        return "disabled", "missing_history"

    if _is_stitched_market_history(history):
        return "hidden", "stitched_video"

    disabled_reason = resolve_history_template_apply_disabled_reason(history)
    if disabled_reason:
        return "disabled", disabled_reason

    task_type = _history_type(history)
    if task_type in WEB_FALLBACK_TASK_TYPES:
        return "web", None
    if task_type == MODE_WAN22_VIDEO_V2:
        wan22_context = extract_wan22_history_context(getattr(history, "extra_outputs", None))
        if bool(wan22_context.get("wan22_use_end_frame")):
            return "web", None
    if task_type == MODE_LTX_VIDEO:
        ltx_context = extract_ltx_history_context(getattr(history, "extra_outputs", None))
        ltx_mode = str(ltx_context.get("ltx_mode") or "").strip()
        if ltx_mode in {"flf2v", "v2v_audio"}:
            return "web", None

    if task_type in NATIVE_IMAGE_TASK_TYPES or task_type in NATIVE_VIDEO_TASK_TYPES:
        return "native", None
    return "web", None


def _build_post_caption(*, post, history, translated_tags: list[str], context) -> str:
    tags = " ".join(translated_tags) if translated_tags else "无标签"
    if getattr(post, "media_type", None) == "video":
        spec = (
            f"{getattr(post, 'duration', None)}秒 | {getattr(post, 'width', '')}x{getattr(post, 'height', '')}"
            if getattr(post, "duration", None)
            else "视频"
        )
    else:
        spec = (
            f"图片 | {getattr(post, 'width', '')}x{getattr(post, 'height', '')}"
            if getattr(post, "width", None)
            else "图片"
        )

    task_type = _history_type(history) or getattr(post, "task_type", None) or "unknown"
    task_type_label = _task_type_label(context, task_type)
    return (
        f"<b>{html.escape(_t(context, 'qqcc.market.title'))}</b>\n\n"
        f"<b>作者</b>：{html.escape(_author_name(post))}\n"
        f"<b>类型</b>：{html.escape(task_type_label)}\n"
        f"<b>提示词</b>：<code>*** 已隐藏，可一键应用体验 ***</code>\n"
        f"<b>标签</b>：{html.escape(tags)}\n"
        f"<b>规格</b>：{html.escape(spec)}\n\n"
        f"赞 {getattr(post, 'likes_count', 0)} | "
        f"踩 {getattr(post, 'dislikes_count', 0)} | "
        f"应用 {getattr(post, 'applied_count', 0)}"
    )


def build_qqcc_market_apply_row(*, post, history) -> list[InlineKeyboardButton]:
    apply_mode, _reason = resolve_qqcc_gallery_apply_mode(history)
    if apply_mode == "native":
        return [
            InlineKeyboardButton("一键应用", callback_data=f"{QG_APPLY_PREFIX}{post.id}"),
            InlineKeyboardButton("Web应用", url=build_market_web_apply_url(post.id)),
        ]
    if apply_mode == "web":
        apply_row = []
        if not _is_web_only_market_history(history):
            apply_row.append(
                InlineKeyboardButton("一键应用", callback_data=f"{QG_APPLY_PREFIX}{post.id}")
            )
        apply_row.append(
            InlineKeyboardButton("Web应用", url=build_market_web_apply_url(post.id))
        )
        return apply_row
    if apply_mode == "hidden":
        return []
    return [InlineKeyboardButton("不可应用", callback_data="noop")]


def build_qqcc_market_post_markup(
    *,
    post,
    history,
    type_code: str,
    sort_code: str,
    page: int,
    has_next: bool,
) -> InlineKeyboardMarkup:
    apply_row = build_qqcc_market_apply_row(post=post, history=history)
    rows = [
        [
            InlineKeyboardButton(
                f"赞 ({getattr(post, 'likes_count', 0)})",
                callback_data=f"{QG_LIKE_PREFIX}{post.id}:{type_code}:{sort_code}:{page}",
            ),
            InlineKeyboardButton(
                f"踩 ({getattr(post, 'dislikes_count', 0)})",
                callback_data=f"{QG_DISLIKE_PREFIX}{post.id}:{type_code}:{sort_code}:{page}",
            ),
        ],
    ]
    if apply_row:
        rows.append(apply_row)
    rows.extend(
        [
            [
                InlineKeyboardButton("最新", callback_data=f"{QG_PAGE_PREFIX}{type_code}:new:0"),
                InlineKeyboardButton("热门", callback_data=f"{QG_PAGE_PREFIX}{type_code}:hot:0"),
                InlineKeyboardButton("常用", callback_data=f"{QG_PAGE_PREFIX}{type_code}:app:0"),
            ],
            [
                (
                    InlineKeyboardButton(
                        "上一个",
                        callback_data=f"{QG_PAGE_PREFIX}{type_code}:{sort_code}:{max(0, page - 1)}",
                    )
                    if page > 0
                    else InlineKeyboardButton("分类", callback_data=QG_MENU_CALLBACK)
                ),
                (
                    InlineKeyboardButton(
                        "下一个",
                        callback_data=f"{QG_PAGE_PREFIX}{type_code}:{sort_code}:{page + 1}",
                    )
                    if has_next
                    else InlineKeyboardButton("分类", callback_data=QG_MENU_CALLBACK)
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(rows)


async def display_qqcc_market_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    session_factory=AsyncSessionLocal,
    fetch_gallery_feed_func=get_gallery_feed,
):
    query = update.callback_query
    await safe_answer_query(query, text=_t(context, "qqcc.market.loading"))
    type_code, sort_code, page = parse_qqcc_market_page_callback_data(query.data)
    try:
        posts, _total = await fetch_qqcc_market_page(
            type_code=type_code,
            sort_code=sort_code,
            page=page,
            fetch_gallery_feed_func=fetch_gallery_feed_func,
        )
        if not posts:
            await safe_answer_query(query, text=_t(context, "qqcc.market.empty"), show_alert=True)
            return

        post = posts[0]
        has_next = len(posts) > 1
        async with session_factory() as session:
            history = await get_history_for_gallery_post(post=post, session=session)

        caption = _build_post_caption(
            post=post,
            history=history,
            translated_tags=translate_market_tags(_parse_tags(post), context=context),
            context=context,
        )
        reply_markup = build_qqcc_market_post_markup(
            post=post,
            history=history,
            type_code=type_code,
            sort_code=sort_code,
            page=page,
            has_next=has_next,
        )
        media_source = await resolve_gallery_media_source(post=post, history=history)
        sent_msg = await send_gallery_media_message(
            context=context,
            chat_id=query.message.chat_id,
            post=post,
            caption=caption,
            reply_markup=reply_markup,
            media_source=media_source,
            session_factory=session_factory,
        )
        if sent_msg:
            await robust_delete_message(query.message)
    except Exception:
        logger.exception("Failed to display QQCC gallery market page.")
        await safe_answer_query(query, text=_t(context, "qqcc.market.load_failed"), show_alert=True)


def _replace_caption_count(caption: str, *, likes_count: int, dislikes_count: int) -> str:
    caption = re.sub(r"赞 \d+", f"赞 {likes_count}", caption)
    return re.sub(r"踩 \d+", f"踩 {dislikes_count}", caption)


async def _handle_market_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE, *, action: str):
    query = update.callback_query
    prefix = QG_LIKE_PREFIX if action == "like" else QG_DISLIKE_PREFIX
    try:
        post_id, type_code, sort_code, page = parse_qqcc_market_reaction_callback_data(query.data, prefix)
        internal_user, _ = await get_or_create_user_by_telegram(query.from_user.id)
        result = await toggle_like(internal_user.id, post_id, action)
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
                            callback_data=f"{QG_LIKE_PREFIX}{post_id}:{type_code}:{sort_code}:{page}",
                        )
                    )
                elif button.callback_data and button.callback_data.startswith(QG_DISLIKE_PREFIX):
                    next_row.append(
                        InlineKeyboardButton(
                            f"踩 ({dislikes_count})",
                            callback_data=f"{QG_DISLIKE_PREFIX}{post_id}:{type_code}:{sort_code}:{page}",
                        )
                    )
                else:
                    next_row.append(button)
            keyboard.append(next_row)

        caption = query.message.caption_html or query.message.caption or ""
        if caption:
            await query.message.edit_caption(
                caption=_replace_caption_count(
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


def _is_native_apply_context(context_payload) -> bool:
    task_type = context_payload.task_type
    if task_type in NATIVE_IMAGE_TASK_TYPES:
        return True
    if task_type in {MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO, MODE_WAN22_VIDEO_V2}:
        return True
    if task_type == MODE_LTX_VIDEO:
        return len(context_payload.input_files or []) <= 1
    return False


async def _load_apply_context_or_mode(post_id: int):
    async with AsyncSessionLocal() as db:
        post, history = await fetch_gallery_apply_context_entities(db=db, post_id=post_id)
        if not post or post.is_active is False:
            raise GalleryApplyContextError(status_code=404, detail="帖子不存在或已失效")
        if not history:
            raise GalleryApplyContextError(status_code=404, detail="未找到原任务详情")
        apply_mode, reason = resolve_qqcc_gallery_apply_mode(history)
        if apply_mode in {"disabled", "hidden"}:
            raise GalleryApplyContextError(status_code=400, detail=reason or "apply_disabled")
        if apply_mode == "web":
            return None, "web"
        apply_context = await build_gallery_apply_context_payload(
            post_id=post_id,
            db=db,
            build_history_apply_context_response_fn=build_history_apply_context_response,
            should_return_apply_input_file=default_should_return_gallery_apply_input_file,
            build_input_file_url=build_storage_input_file_url,
            release_read_transaction_fn=release_read_transaction,
            post=post,
            history=history,
        )
        if not _is_native_apply_context(apply_context):
            return None, "web"
        return apply_context, "native"


@register_callback(QG_MENU_CALLBACK)
async def handle_qqcc_market_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer_query(query)
    await query.message.reply_text(
        f"{_t(context, 'qqcc.market.title')}\n\n{_t(context, 'qqcc.market.hint')}",
        reply_markup=build_qqcc_gallery_market_menu_markup(context=context),
    )


@register_callback(QG_PAGE_PREFIX)
async def handle_qqcc_market_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await display_qqcc_market_page(update, context)


@register_callback(QG_LIKE_PREFIX)
async def handle_qqcc_market_like_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_market_reaction(update, context, action="like")


@register_callback(QG_DISLIKE_PREFIX)
async def handle_qqcc_market_dislike_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_market_reaction(update, context, action="dislike")


@register_callback(QG_APPLY_PREFIX)
async def handle_qqcc_market_apply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        post_id = parse_qqcc_market_apply_callback_data(query.data)
        apply_context, mode = await _load_apply_context_or_mode(post_id)
        if mode == "web":
            await safe_answer_query(query, text=_t(context, "qqcc.market.apply_web"), show_alert=True)
            await robust_send_message(
                context.bot,
                query.message.chat_id,
                _t(context, "qqcc.market.apply_web"),
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Web应用", url=build_market_web_apply_url(post_id))]]
                ),
            )
            return

        context.user_data[QQCC_GALLERY_APPLY_SESSION_KEY] = {
            **apply_context.model_dump(),
            "created_at": time.time(),
        }
        await safe_answer_query(query, text=_t(context, "qqcc.market.apply_loaded"))
        await robust_send_message(
            context.bot,
            query.message.chat_id,
            _t(context, "qqcc.market.apply_loaded"),
        )
    except GalleryApplyContextError as exc:
        await safe_answer_query(
            query,
            text=f"{_t(context, 'qqcc.market.apply_disabled')} {exc.detail}",
            show_alert=True,
        )
    except Exception:
        logger.exception("Failed to load QQCC market apply context.")
        await safe_answer_query(query, text=_t(context, "qqcc.market.apply_submit_failed"), show_alert=True)


def _resolve_image_file_id(message) -> str | None:
    if getattr(message, "photo", None):
        return message.photo[-1].file_id
    document = getattr(message, "document", None)
    if document and str(getattr(document, "mime_type", "") or "").startswith("image/"):
        return document.file_id
    return None


async def _download_market_apply_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    message = update.effective_message
    file_id = _resolve_image_file_id(message)
    if not file_id:
        await robust_reply_text(message, _t(context, "qqcc.market.invalid_image"))
        return None
    try:
        telegram_file = await context.bot.get_file(file_id)
        return await download_telegram_file_to_fsm_temp(
            telegram_file=telegram_file,
            suffix=".png",
            name_hint="qqcc_gallery_apply",
        )
    except Exception:
        logger.exception("Failed to download QQCC market apply image.")
        await robust_reply_text(message, _t(context, "fsm.common.download_image_failed"))
        return None


async def submit_qqcc_gallery_apply_session(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    session: dict,
):
    user = update.effective_user
    chat_id = update.effective_chat.id
    task_type = str(session.get("task_type") or "")
    prompt = str(session.get("prompt") or "")
    negative_prompt = str(session.get("negative_prompt") or "")
    source_post_id = session.get("source_post_id") or session.get("post_id")
    lora_name = session.get("lora_name")
    lora_strength = session.get("lora_strength") or 1.0
    requested_duration = session.get("requested_duration") or session.get("duration")
    billing_resolution = session.get("billing_resolution")

    if task_type == MODE_I2I_PRO:
        return await process_i2i_pro_task(
            context=context,
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            prompt=prompt,
            images=[image_path],
            allow_contribute=False,
            source_post_id=source_post_id,
        )
    if task_type in NATIVE_IMAGE_TASK_TYPES:
        return await process_standard_generation_task(
            context=context,
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            prompt=prompt,
            images=[image_path],
            is_video=False,
            task_type=task_type,
            lora_name=lora_name,
            lora_strength=lora_strength,
            allow_contribute=False,
            source_post_id=source_post_id,
        )
    if task_type in {MODE_CUSTOM_VIDEO, MODE_IMAGE_TO_VIDEO}:
        return await process_image_to_video_generation_task(
            context=context,
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            prompt=prompt,
            negative_prompt=negative_prompt,
            images=[image_path],
            resolution=billing_resolution,
            duration=requested_duration,
            task_type=task_type,
            lora_name=lora_name,
            lora_strength=lora_strength,
            allow_contribute=False,
            source_post_id=source_post_id,
        )
    if task_type == MODE_WAN22_VIDEO_V2:
        return await process_wan22_video_v2_generation_task(
            context=context,
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            prompt=prompt,
            negative_prompt=negative_prompt,
            images=[image_path],
            use_end_frame=False,
            resolution_preset=billing_resolution,
            duration=requested_duration,
            allow_contribute=False,
            source_post_id=source_post_id,
        )
    if task_type == MODE_LTX_VIDEO:
        sentinel = object()
        previous_resolution = context.user_data.get("ltx_video_resolution", sentinel)
        previous_duration = context.user_data.get("ltx_video_duration", sentinel)
        try:
            if session.get("width") and session.get("height"):
                context.user_data["ltx_video_resolution"] = (
                    f"{session['width']}x{session['height']}"
                )
            if requested_duration:
                context.user_data["ltx_video_duration"] = f"{requested_duration}s"
            return await process_ltx_video_task(
                update=update,
                context=context,
                prompt=prompt,
                image_path=image_path,
                ltx_mode="i2v",
                lora_items=session.get("lora_items"),
                allow_contribute=False,
                source_post_id=source_post_id,
            )
        finally:
            if previous_resolution is sentinel:
                context.user_data.pop("ltx_video_resolution", None)
            else:
                context.user_data["ltx_video_resolution"] = previous_resolution
            if previous_duration is sentinel:
                context.user_data.pop("ltx_video_duration", None)
            else:
                context.user_data["ltx_video_duration"] = previous_duration
    raise ValueError(f"Unsupported QQCC gallery apply task type: {task_type}")


async def handle_qqcc_gallery_apply_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = context.user_data.get(QQCC_GALLERY_APPLY_SESSION_KEY)
    message = update.effective_message
    if not session:
        return None
    if is_qqcc_gallery_apply_session_expired(session):
        context.user_data.pop(QQCC_GALLERY_APPLY_SESSION_KEY, None)
        await robust_reply_text(message, _t(context, "qqcc.market.apply_expired"))
        return None

    image_path = await _download_market_apply_image(update, context)
    if not image_path:
        return None

    try:
        context.user_data.pop(QQCC_GALLERY_APPLY_SESSION_KEY, None)
        await submit_qqcc_gallery_apply_session(
            update=update,
            context=context,
            image_path=image_path,
            session=session,
        )
    except Exception:
        logger.exception("Failed to submit QQCC market apply task.")
        await robust_reply_text(message, _t(context, "qqcc.market.apply_submit_failed"))
    return None
