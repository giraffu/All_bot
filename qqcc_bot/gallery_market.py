from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from qqcc_bot import gallery_market_apply as apply_service
from qqcc_bot import gallery_market_interactions as interaction_service
from qqcc_bot import gallery_market_view as view_service
from qqcc_bot.gallery_market_apply import (
    NATIVE_IMAGE_TASK_TYPES,
    NATIVE_VIDEO_TASK_TYPES,
    QQCC_GALLERY_APPLY_SESSION_KEY,
)
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
from src.core.gallery_core import get_gallery_feed
from src.database.core import AsyncSessionLocal
from src.handlers.callback_router import register_callback
from src.lora_mapping import translate_tags
from src.services.fsm_temp_file_service import cleanup_fsm_temp_files
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
from src.services.gallery_apply_context_presenter import (
    build_history_apply_context_response,
    build_storage_input_file_url,
    release_read_transaction,
)

logger = logging.getLogger("qqcc_bot.gallery_market")

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
    return view_service.build_market_menu_markup(
        context=context,
        tabs=QQCC_MARKET_TABS,
        sort_code=sort_code,
        page_prefix=QG_PAGE_PREFIX,
        tab_label_func=_tab_label,
    )


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
    return apply_service.is_qqcc_gallery_apply_session_expired(session, now=now)


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
    return view_service.author_name(post)


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
    return view_service.build_post_caption(
        post=post,
        history=history,
        translated_tags=translated_tags,
        context=context,
        translate_func=_t,
        history_type_func=_history_type,
        task_type_label_func=_task_type_label,
    )


def build_qqcc_market_apply_row(*, post, history) -> list[InlineKeyboardButton]:
    return view_service.build_market_apply_row(
        post=post,
        history=history,
        apply_prefix=QG_APPLY_PREFIX,
        resolve_apply_mode_func=resolve_qqcc_gallery_apply_mode,
        is_web_only_history_func=_is_web_only_market_history,
        build_web_apply_url_func=build_market_web_apply_url,
    )


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
    return view_service.build_market_post_markup(
        post=post,
        history=history,
        type_code=type_code,
        sort_code=sort_code,
        page=page,
        has_next=has_next,
        apply_row=apply_row,
        page_prefix=QG_PAGE_PREFIX,
        like_prefix=QG_LIKE_PREFIX,
        dislike_prefix=QG_DISLIKE_PREFIX,
    )


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
    return interaction_service.replace_caption_count(
        caption,
        likes_count=likes_count,
        dislikes_count=dislikes_count,
    )


async def _handle_market_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE, *, action: str):
    await interaction_service.handle_market_reaction(
        update,
        context,
        action=action,
        known_type_codes=set(TAB_BY_CODE),
    )


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
    return apply_service.resolve_image_file_id(message)


async def _download_market_apply_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return await apply_service.download_market_apply_image(update, context)


async def submit_qqcc_gallery_apply_session(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_path: str,
    session: dict,
):
    return await apply_service.submit_qqcc_gallery_apply_session(
        update=update,
        context=context,
        image_path=image_path,
        session=session,
        process_i2i_pro_task_func=process_i2i_pro_task,
        process_standard_generation_task_func=process_standard_generation_task,
        process_image_to_video_generation_task_func=process_image_to_video_generation_task,
        process_wan22_video_v2_generation_task_func=process_wan22_video_v2_generation_task,
        process_ltx_video_task_func=process_ltx_video_task,
    )


async def handle_qqcc_gallery_apply_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await apply_service.handle_qqcc_gallery_apply_media(
        update,
        context,
        download_image_func=_download_market_apply_image,
        submit_session_func=submit_qqcc_gallery_apply_session,
        cleanup_temp_files_func=cleanup_fsm_temp_files,
        reply_text_func=robust_reply_text,
        is_session_expired_func=is_qqcc_gallery_apply_session_expired,
    )
