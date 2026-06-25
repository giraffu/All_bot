from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
STATIC_DIR = ROOT_DIR / "static"

GENERATION_OPERATION_TYPES = [
    "edit",
    "custom_video",
    "img2img_lora",
    "face_swap",
    "image",
    "video_lora",
    "undress",
    "perfect_video_insert",
    "i2i_pro",
    "ltx_video",
    "closeup_blowjob",
    "masturbation",
    "blowjob",
    "undress_tongue",
    "doggy_style",
    "wan22_video_v2",
    "txt2img",
    "i2i_draw",
    "face_video_step1",
    "penetration",
    "scail2_action_transfer",
    "text_to_image",
    "face_video",
    "scail2_video_replacement",
    "fuck",
    "scail2_face_swap_v2",
    "face_show",
    "face_tongue",
    "video_pro",
    "video_edit",
    "video_insert",
    "image_to_video",
]

PROMPT_TAG_RULES = [
    ("人物一致性", ("保持", "一致", "face", "identity", "same person")),
    ("镜头", ("镜头", "camera", "close-up", "pov", "wide shot", "pan")),
    ("动作", ("动作", "movement", "walk", "run", "turn", "pose")),
    ("场景", ("场景", "room", "street", "forest", "studio", "背景")),
    ("风格", ("风格", "style", "anime", "realistic", "cinematic", "photoreal")),
    ("画质", ("高清", "4k", "8k", "quality", "detail", "sharp")),
    ("视频", ("video", "frames", "duration", "秒", "首帧", "尾帧")),
    ("负面词", ("negative", "bad hands", "低质量", "模糊", "畸形")),
    ("模型参数", ("lora", "controlnet", "seed", "cfg", "steps")),
]

MEDIA_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".mp4",
    ".mov",
    ".webm",
    ".avi",
    ".mkv",
)

app = FastAPI(title="AllBot Local Analytics", version="0.1.0")
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _database_url() -> str:
    dsn = os.getenv("LOCAL_ANALYTICS_DATABASE_URL", "").strip()
    if not dsn:
        raise HTTPException(
            status_code=503,
            detail="LOCAL_ANALYTICS_DATABASE_URL is not configured",
        )
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = "postgresql://" + dsn.removeprefix("postgresql+asyncpg://")
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn.removeprefix("postgres://")
    return dsn


def _masked_dsn() -> str | None:
    try:
        parsed = urlsplit(_database_url())
    except HTTPException:
        return None
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user = parsed.username or "postgres"
    netloc = f"{user}:***@{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


async def _pool() -> asyncpg.Pool:
    pool = getattr(app.state, "pool", None)
    if pool is None:
        app.state.pool = await asyncpg.create_pool(
            dsn=_database_url(),
            min_size=1,
            max_size=5,
            command_timeout=60,
        )
        pool = app.state.pool
    return pool


@app.on_event("shutdown")
async def shutdown() -> None:
    pool = getattr(app.state, "pool", None)
    if pool is not None:
        await pool.close()


async def _fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    pool = await _pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction(readonly=True):
                await conn.execute("SET LOCAL statement_timeout = '45s'")
                return await conn.fetch(query, *args)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - returned as API detail.
        raise HTTPException(status_code=500, detail=f"analytics query failed: {type(exc).__name__}") from exc


async def _fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    rows = await _fetch(query, *args)
    return rows[0] if rows else None


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row(record: asyncpg.Record | None) -> dict[str, Any]:
    if record is None:
        return {}
    return {key: _json_value(value) for key, value in dict(record).items()}


def _rows(records: list[asyncpg.Record]) -> list[dict[str, Any]]:
    return [_row(record) for record in records]


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _media_bucket() -> str:
    return os.getenv("LOCAL_ANALYTICS_MEDIA_BUCKET", "user-data-prod-shadow").strip()


def _media_base_url() -> str:
    return os.getenv("LOCAL_ANALYTICS_MEDIA_PUBLIC_BASE_URL", "").strip().rstrip("/")


def _media_url(key: str | None) -> str | None:
    if not key:
        return None
    base_url = _media_base_url()
    if not base_url:
        return None
    encoded_key = quote(key.lstrip("/"), safe="/:@")
    encoded_bucket = quote(_media_bucket(), safe="")
    if "{key}" in base_url or "{bucket}" in base_url:
        return base_url.replace("{bucket}", encoded_bucket).replace("{key}", encoded_key)
    return f"{base_url}/{encoded_bucket}/{encoded_key}"


def _collapse_text(value: str | None, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit - 1]}..."


def _safe_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text[0] in "[{":
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
    return value


def _extract_refs(value: Any) -> list[str]:
    parsed = _safe_json(value)
    refs: list[str] = []

    def walk(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, dict):
            for key, nested in item.items():
                if key in {"path", "url", "key", "file", "image", "video"}:
                    walk(nested)
                elif isinstance(nested, (dict, list)):
                    walk(nested)
            return
        if isinstance(item, list):
            for nested in item:
                walk(nested)
            return
        if not isinstance(item, str):
            return
        candidate = item.strip()
        if not candidate:
            return
        parts = re.split(r"[\n,;]+", candidate)
        for part in parts:
            clean = part.strip().strip("\"'")
            if not clean:
                continue
            if clean.startswith(("http://", "https://")) or any(clean.lower().endswith(ext) for ext in MEDIA_EXTENSIONS):
                refs.append(clean)

    walk(parsed)
    seen: set[str] = set()
    unique_refs = []
    for ref in refs:
        if ref not in seen:
            unique_refs.append(ref)
            seen.add(ref)
    return unique_refs


def _classify_refs(refs: list[str]) -> dict[str, int]:
    images = 0
    videos = 0
    for ref in refs:
        lower = ref.lower().split("?", 1)[0]
        if lower.endswith((".mp4", ".mov", ".webm", ".avi", ".mkv")):
            videos += 1
        elif lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            images += 1
    return {"images": images, "videos": videos, "total": len(refs)}


def _prompt_tags(prompt: str | None) -> list[str]:
    lower = (prompt or "").lower()
    tags = []
    for label, needles in PROMPT_TAG_RULES:
        if any(needle.lower() in lower for needle in needles):
            tags.append(label)
    return tags[:6]


def _input_requirements(input_refs: list[str], task_type: str | None) -> list[str]:
    media = _classify_refs(input_refs)
    requirements: list[str] = []
    if media["images"]:
        requirements.append(f"{media['images']} 张图片")
    if media["videos"]:
        requirements.append(f"{media['videos']} 个视频")
    task = task_type or ""
    if "video" in task or "ltx" in task or "wan22" in task or "scail2" in task:
        requirements.append("需校验首帧/时长")
    if "face" in task:
        requirements.append("需清晰脸部")
    return requirements or ["无显式输入文件"]


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    row = await _fetchrow("select current_database() as database_name, now() as checked_at")
    return {
        "status": "ok",
        "database": _row(row),
        "database_url": _masked_dsn(),
        "media_bucket": _media_bucket(),
        "media_url_enabled": bool(_media_base_url()),
    }


@app.get("/api/overview")
async def overview(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    days = _clamp(days, 1, 365)
    metrics = await _fetchrow(
        """
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        )
        select
            current_database() as database_name,
            (select count(*) from users)::bigint as total_users,
            (select count(*) from users, bounds where created_at >= bounds.since)::bigint as new_users,
            (select count(*) from users, bounds where last_activity >= bounds.since)::bigint as active_users,
            (select count(*) from history)::bigint as total_history,
            (select count(*) from history, bounds where created_at >= bounds.since)::bigint as recent_history,
            (select count(*) from orders where lower(status) = 'success')::bigint as successful_orders,
            (select count(distinct internal_user_id) from orders where lower(status) = 'success' and payment_channel in ('RMB', 'TON', 'XTR'))::bigint as paying_users,
            (select coalesce(sum(final_price), 0) from orders, bounds where lower(status) = 'success' and payment_channel = 'RMB' and coalesce(paid_at, updated_at, created_at) >= bounds.since) as recent_rmb_amount,
            (select coalesce(sum(final_price), 0) from orders, bounds where lower(status) = 'success' and payment_channel = 'TON' and coalesce(paid_at, updated_at, created_at) >= bounds.since) as recent_ton_amount,
            (select coalesce(sum(final_price), 0) from orders, bounds where lower(status) = 'success' and payment_channel = 'XTR' and coalesce(paid_at, updated_at, created_at) >= bounds.since) as recent_stars_amount,
            (select count(*) from gallery_posts where is_active is true)::bigint as active_gallery_posts,
            (select count(*) from gallery_prompt_unlocks, bounds where created_at >= bounds.since)::bigint as recent_prompt_unlocks,
            (select max(created_at) from history) as latest_history_at,
            (select max(coalesce(paid_at, updated_at, created_at)) from orders where lower(status) = 'success') as latest_order_at
        """,
        days,
    )
    daily = await _fetch(
        """
        with days as (
            select generate_series(
                current_date - (($1::int - 1) * interval '1 day'),
                current_date,
                interval '1 day'
            )::date as day
        ),
        user_daily as (
            select created_at::date as day, count(*)::bigint as new_users
            from users
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        history_daily as (
            select created_at::date as day, count(*)::bigint as generations, count(distinct user_id)::bigint as creators
            from history
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        order_daily as (
            select coalesce(paid_at, updated_at, created_at)::date as day,
                   count(*) filter (where lower(status) = 'success')::bigint as orders,
                   coalesce(sum(final_price) filter (where lower(status) = 'success' and payment_channel = 'RMB'), 0) as rmb_amount
            from orders
            where coalesce(paid_at, updated_at, created_at) >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        )
        select to_char(days.day, 'YYYY-MM-DD') as day,
               coalesce(user_daily.new_users, 0)::bigint as new_users,
               coalesce(history_daily.generations, 0)::bigint as generations,
               coalesce(history_daily.creators, 0)::bigint as creators,
               coalesce(order_daily.orders, 0)::bigint as orders,
               coalesce(order_daily.rmb_amount, 0) as rmb_amount
        from days
        left join user_daily using (day)
        left join history_daily using (day)
        left join order_daily using (day)
        order by days.day
        """,
        days,
    )
    return {
        "days": days,
        "source": {
            "database_url": _masked_dsn(),
            "media_bucket": _media_bucket(),
            "media_url_enabled": bool(_media_base_url()),
        },
        "metrics": _row(metrics),
        "daily": _rows(daily),
    }


@app.get("/api/finance")
async def finance(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    days = _clamp(days, 1, 365)
    summary = await _fetchrow(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            count(*) filter (where lower(status) = 'success')::bigint as success_orders,
            count(*) filter (where lower(status) != 'success')::bigint as non_success_orders,
            count(distinct internal_user_id) filter (where lower(status) = 'success' and payment_channel in ('RMB', 'TON', 'XTR'))::bigint as real_payers,
            coalesce(sum(final_price) filter (where lower(status) = 'success' and payment_channel = 'RMB'), 0) as rmb_amount,
            coalesce(sum(final_price) filter (where lower(status) = 'success' and payment_channel = 'TON'), 0) as ton_amount,
            coalesce(sum(final_price) filter (where lower(status) = 'success' and payment_channel = 'XTR'), 0) as stars_amount,
            coalesce(avg(final_price) filter (where lower(status) = 'success' and payment_channel = 'RMB'), 0) as rmb_avg_order,
            count(*) filter (where lower(status) = 'success' and (payment_channel is null or payment_channel not in ('RMB', 'TON', 'XTR')))::bigint as internal_success_orders
        from orders, bounds
        where coalesce(paid_at, updated_at, created_at) >= bounds.since
        """,
        days,
    )
    channels = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            coalesce(o.payment_channel, 'INTERNAL') as channel,
            count(*) filter (where lower(o.status) = 'success')::bigint as success_orders,
            count(*) filter (where lower(o.status) != 'success')::bigint as non_success_orders,
            count(distinct o.internal_user_id) filter (where lower(o.status) = 'success')::bigint as payers,
            coalesce(sum(o.final_price) filter (where lower(o.status) = 'success'), 0) as amount,
            coalesce(avg(o.final_price) filter (where lower(o.status) = 'success'), 0) as avg_order_amount,
            coalesce(sum(mp.reward_credits) filter (where lower(o.status) = 'success'), 0)::bigint as plan_reward_credits,
            min(coalesce(o.paid_at, o.updated_at, o.created_at)) filter (where lower(o.status) = 'success') as first_paid_at,
            max(coalesce(o.paid_at, o.updated_at, o.created_at)) filter (where lower(o.status) = 'success') as last_paid_at
        from orders o
        left join membership_plans mp on mp.id = o.plan_id,
        bounds
        where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        group by 1
        order by success_orders desc, amount desc
        """,
        days,
    )
    first_purchase = await _fetchrow(
        """
        with first_success as (
            select distinct on (internal_user_id)
                   internal_user_id,
                   plan_id,
                   payment_channel,
                   final_price,
                   coalesce(paid_at, updated_at, created_at) as first_paid_at
            from orders
            where lower(status) = 'success'
              and payment_channel in ('RMB', 'TON', 'XTR')
              and internal_user_id is not null
            order by internal_user_id, coalesce(paid_at, updated_at, created_at)
        ),
        bounds as (select now() - ($1::int * interval '1 day') as since),
        recent_first as (
            select fs.*, u.created_at as registered_at
            from first_success fs
            join users u on u.id = fs.internal_user_id
            where fs.first_paid_at >= (select since from bounds)
        )
        select
            count(*)::bigint as first_purchase_users,
            coalesce(avg(extract(epoch from (first_paid_at - registered_at)) / 3600), 0) as avg_hours_to_first_purchase,
            coalesce(percentile_cont(0.5) within group (order by extract(epoch from (first_paid_at - registered_at)) / 3600), 0) as median_hours_to_first_purchase,
            count(*) filter (where first_paid_at - registered_at <= interval '24 hours')::bigint as first_day_payers
        from recent_first
        """,
        days,
    )
    segments = await _fetch(
        """
        with paid_users as (
            select internal_user_id,
                   count(*)::bigint as orders,
                   coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) as rmb_amount,
                   max(coalesce(paid_at, updated_at, created_at)) as last_paid_at
            from orders
            where lower(status) = 'success'
              and payment_channel in ('RMB', 'TON', 'XTR')
              and internal_user_id is not null
            group by internal_user_id
        )
        select
            case
                when orders = 1 then '首充用户'
                when orders between 2 and 3 then '轻复购'
                when orders between 4 and 9 then '稳定复购'
                else '高频付费'
            end as segment,
            count(*)::bigint as users,
            sum(orders)::bigint as orders,
            coalesce(sum(rmb_amount), 0) as rmb_amount,
            coalesce(avg(rmb_amount), 0) as avg_rmb_per_user,
            max(last_paid_at) as latest_paid_at
        from paid_users
        group by 1
        order by min(orders)
        """
    )
    return {
        "days": days,
        "summary": _row(summary),
        "channels": _rows(channels),
        "first_purchase": _row(first_purchase),
        "segments": _rows(segments),
    }


@app.get("/api/generation")
async def generation(days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    days = _clamp(days, 1, 365)
    summary = await _fetchrow(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            count(*)::bigint as generations,
            count(distinct user_id)::bigint as creators,
            count(*) filter (where source = 'web')::bigint as web_generations,
            count(*) filter (where source = 'bot')::bigint as bot_generations,
            count(*) filter (where output_file is not null or extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
            count(*) filter (where is_favorited is true)::bigint as favorited_records,
            count(*) filter (where is_public is true)::bigint as public_records,
            coalesce(avg(duration) filter (where duration is not null), 0) as avg_duration,
            coalesce(avg(width) filter (where width is not null), 0) as avg_width,
            coalesce(avg(height) filter (where height is not null), 0) as avg_height
        from history, bounds
        where created_at >= bounds.since
        """,
        days,
    )
    by_type = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            coalesce(h.type, 'unknown') as task_type,
            count(*)::bigint as generations,
            count(distinct h.user_id)::bigint as creators,
            count(*) filter (where h.output_file is not null or h.extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
            count(*) filter (where h.input_file is not null and h.input_file <> '')::bigint as with_input,
            count(*) filter (where h.is_favorited is true)::bigint as favorited_records,
            count(distinct gp.id) filter (where gp.is_active is true)::bigint as gallery_posts,
            coalesce(sum(gp.likes_count) filter (where gp.is_active is true), 0)::bigint as likes,
            coalesce(sum(gp.applied_count) filter (where gp.is_active is true), 0)::bigint as applies,
            coalesce(avg(h.duration) filter (where h.duration is not null), 0) as avg_duration
        from history h
        left join gallery_posts gp on gp.task_id = h.task_id,
        bounds
        where h.created_at >= bounds.since
        group by 1
        order by generations desc
        limit 50
        """,
        days,
    )
    credits = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            operation_type as task_type,
            count(*)::bigint as debit_events,
            abs(coalesce(sum(credit_change), 0))::bigint as credits_spent,
            coalesce(avg(abs(credit_change)), 0) as avg_credits_per_event
        from user_logs, bounds
        where created_at >= bounds.since
          and credit_change < 0
          and operation_type = any($2::text[])
        group by operation_type
        order by credits_spent desc
        limit 50
        """,
        days,
        GENERATION_OPERATION_TYPES,
    )
    hourly = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            extract(hour from created_at)::int as hour,
            count(*)::bigint as generations,
            count(distinct user_id)::bigint as creators
        from history, bounds
        where created_at >= bounds.since
        group by 1
        order by 1
        """,
        days,
    )
    return {
        "days": days,
        "summary": _row(summary),
        "by_type": _rows(by_type),
        "credits": _rows(credits),
        "hourly": _rows(hourly),
    }


@app.get("/api/prompts")
async def prompts(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(80, ge=1, le=200),
    task_type: str | None = Query(None),
) -> dict[str, Any]:
    days = _clamp(days, 1, 365)
    limit = _clamp(limit, 1, 200)
    sample_limit = max(limit * 100, 20000)
    rows = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        recent_history as (
            select id, task_id, user_id, type, prompt, input_file, output_file, extra_outputs,
                   created_at, source, is_favorited, width, height, duration
            from history, bounds
            where created_at >= bounds.since
              and prompt is not null
              and length(trim(prompt)) > 8
              and ($4::text is null or type = $4::text)
            order by created_at desc
            limit $3::int
        ),
        unlock_counts as (
            select post_id, count(*)::bigint as unlocks
            from gallery_prompt_unlocks
            group by post_id
        )
        select
            h.id,
            h.task_id,
            h.user_id,
            h.type as task_type,
            h.prompt,
            h.input_file,
            h.output_file,
            h.extra_outputs,
            h.created_at,
            h.source,
            h.is_favorited,
            h.width,
            h.height,
            h.duration,
            gp.id as post_id,
            coalesce(gp.likes_count, 0)::bigint as likes,
            coalesce(gp.applied_count, 0)::bigint as applies,
            coalesce(gp.comments_count, 0)::bigint as comments,
            coalesce(uc.unlocks, 0)::bigint as prompt_unlocks,
            (
                case when h.output_file is not null or h.extra_outputs::text not in ('{}', 'null', '') then 8 else 0 end
                + case when h.is_favorited is true then 10 else 0 end
                + case when gp.id is not null then 14 else 0 end
                + coalesce(gp.likes_count, 0) * 2
                + coalesce(gp.applied_count, 0) * 5
                + coalesce(gp.comments_count, 0) * 2
                + coalesce(uc.unlocks, 0) * 8
            )::bigint as prompt_score
        from recent_history h
        left join gallery_posts gp on gp.task_id = h.task_id and gp.is_active is true
        left join unlock_counts uc on uc.post_id = gp.id
        order by prompt_score desc, h.created_at desc
        limit $2::int
        """,
        days,
        limit,
        sample_limit,
        task_type,
    )
    candidates = []
    tag_counts: dict[str, int] = {}
    for record in rows:
        item = _row(record)
        input_refs = _extract_refs(item.get("input_file"))
        output_refs = _extract_refs(item.get("output_file")) + _extract_refs(item.get("extra_outputs"))
        tags = _prompt_tags(item.get("prompt"))
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        item["prompt_preview"] = _collapse_text(item.pop("prompt", None), 260)
        item["input_refs"] = input_refs[:6]
        item["output_refs"] = output_refs[:6]
        item["media"] = {
            "input": _classify_refs(input_refs),
            "output": _classify_refs(output_refs),
        }
        item["tags"] = tags
        item["input_requirements"] = _input_requirements(input_refs, item.get("task_type"))
        item["primary_output_url"] = _media_url(output_refs[0]) if output_refs else None
        candidates.append(item)
    return {
        "days": days,
        "limit": limit,
        "task_type": task_type,
        "tag_summary": [
            {"tag": tag, "count": count}
            for tag, count in sorted(tag_counts.items(), key=lambda pair: pair[1], reverse=True)
        ],
        "candidates": candidates,
    }


@app.get("/api/media-audit")
async def media_audit(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=300),
) -> dict[str, Any]:
    days = _clamp(days, 1, 365)
    limit = _clamp(limit, 1, 300)
    rows = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            id,
            task_id,
            user_id,
            type as task_type,
            input_file,
            output_file,
            extra_outputs,
            created_at,
            source,
            width,
            height,
            duration
        from history, bounds
        where created_at >= bounds.since
          and (
              input_file is not null
              or output_file is not null
              or extra_outputs::text not in ('{}', 'null', '')
          )
        order by created_at desc
        limit $2::int
        """,
        days,
        limit,
    )
    records = []
    totals = {"input_refs": 0, "output_refs": 0, "images": 0, "videos": 0, "with_output": 0}
    for record in rows:
        item = _row(record)
        input_refs = _extract_refs(item.pop("input_file", None))
        output_refs = _extract_refs(item.pop("output_file", None)) + _extract_refs(item.pop("extra_outputs", None))
        input_media = _classify_refs(input_refs)
        output_media = _classify_refs(output_refs)
        totals["input_refs"] += input_media["total"]
        totals["output_refs"] += output_media["total"]
        totals["images"] += input_media["images"] + output_media["images"]
        totals["videos"] += input_media["videos"] + output_media["videos"]
        if output_refs:
            totals["with_output"] += 1
        item["input_refs"] = input_refs[:8]
        item["output_refs"] = output_refs[:8]
        item["media"] = {"input": input_media, "output": output_media}
        item["primary_output_url"] = _media_url(output_refs[0]) if output_refs else None
        records.append(item)
    return {
        "days": days,
        "limit": limit,
        "media_bucket": _media_bucket(),
        "media_url_enabled": bool(_media_base_url()),
        "totals": totals,
        "records": records,
    }
