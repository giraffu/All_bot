from __future__ import annotations

import html
from collections.abc import Callable, Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def author_name(post) -> str:
    user = getattr(post, "user", None)
    if user:
        return getattr(user, "username", None) or getattr(user, "full_name", None) or f"User {user.id}"
    user_id = getattr(post, "user_id", None)
    return f"User {user_id}" if user_id else "匿名修士"


def build_market_menu_markup(
    *,
    context,
    tabs: Iterable,
    sort_code: str,
    page_prefix: str,
    tab_label_func: Callable,
) -> InlineKeyboardMarkup:
    rows = []
    buttons = [
        InlineKeyboardButton(
            tab_label_func(context, tab),
            callback_data=f"{page_prefix}{tab.code}:{sort_code}:0",
        )
        for tab in tabs
    ]
    rows.extend(buttons[index : index + 2] for index in range(0, len(buttons), 2))
    return InlineKeyboardMarkup(rows)


def build_post_caption(
    *,
    post,
    history,
    translated_tags: list[str],
    context,
    translate_func: Callable,
    history_type_func: Callable,
    task_type_label_func: Callable,
) -> str:
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

    task_type = history_type_func(history) or getattr(post, "task_type", None) or "unknown"
    task_type_label = task_type_label_func(context, task_type)
    return (
        f"<b>{html.escape(translate_func(context, 'qqcc.market.title'))}</b>\n\n"
        f"<b>作者</b>：{html.escape(author_name(post))}\n"
        f"<b>类型</b>：{html.escape(task_type_label)}\n"
        f"<b>提示词</b>：<code>*** 已隐藏，可一键应用体验 ***</code>\n"
        f"<b>标签</b>：{html.escape(tags)}\n"
        f"<b>规格</b>：{html.escape(spec)}\n\n"
        f"赞 {getattr(post, 'likes_count', 0)} | "
        f"踩 {getattr(post, 'dislikes_count', 0)} | "
        f"应用 {getattr(post, 'applied_count', 0)}"
    )


def build_market_apply_row(
    *,
    post,
    history,
    apply_prefix: str,
    resolve_apply_mode_func: Callable,
    is_web_only_history_func: Callable,
    build_web_apply_url_func: Callable[[int], str],
) -> list[InlineKeyboardButton]:
    apply_mode, _reason = resolve_apply_mode_func(history)
    if apply_mode == "native":
        return [
            InlineKeyboardButton("一键应用", callback_data=f"{apply_prefix}{post.id}"),
            InlineKeyboardButton("Web应用", url=build_web_apply_url_func(post.id)),
        ]
    if apply_mode == "web":
        apply_row = []
        if not is_web_only_history_func(history):
            apply_row.append(
                InlineKeyboardButton("一键应用", callback_data=f"{apply_prefix}{post.id}")
            )
        apply_row.append(
            InlineKeyboardButton("Web应用", url=build_web_apply_url_func(post.id))
        )
        return apply_row
    if apply_mode == "hidden":
        return []
    return [InlineKeyboardButton("不可应用", callback_data="noop")]


def build_market_post_markup(
    *,
    post,
    history,
    type_code: str,
    sort_code: str,
    page: int,
    has_next: bool,
    apply_row: list[InlineKeyboardButton],
    page_prefix: str,
    like_prefix: str,
    dislike_prefix: str,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"赞 ({getattr(post, 'likes_count', 0)})",
                callback_data=f"{like_prefix}{post.id}:{type_code}:{sort_code}:{page}",
            ),
            InlineKeyboardButton(
                f"踩 ({getattr(post, 'dislikes_count', 0)})",
                callback_data=f"{dislike_prefix}{post.id}:{type_code}:{sort_code}:{page}",
            ),
        ],
    ]
    if apply_row:
        rows.append(apply_row)
    rows.extend(
        [
            [
                InlineKeyboardButton("最新", callback_data=f"{page_prefix}{type_code}:new:0"),
                InlineKeyboardButton("热门", callback_data=f"{page_prefix}{type_code}:hot:0"),
                InlineKeyboardButton("常用", callback_data=f"{page_prefix}{type_code}:app:0"),
            ],
            [
                (
                    InlineKeyboardButton(
                        "上一个",
                        callback_data=f"{page_prefix}{type_code}:{sort_code}:{max(0, page - 1)}",
                    )
                    if page > 0
                    else InlineKeyboardButton("分类", callback_data="qg:m")
                ),
                (
                    InlineKeyboardButton(
                        "下一个",
                        callback_data=f"{page_prefix}{type_code}:{sort_code}:{page + 1}",
                    )
                    if has_next
                    else InlineKeyboardButton("分类", callback_data="qg:m")
                ),
            ],
        ]
    )
    return InlineKeyboardMarkup(rows)
