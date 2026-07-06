from __future__ import annotations

import asyncio
import configparser
import fcntl
import functools
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import asyncpg
from fastapi import HTTPException

from .prompt_mart import PROMPT_MART_READY_SQL, PROMPT_MART_STATUS_SQL, PROMPT_NORMALIZATION_VERSION
from .prompt_vectors import (
    DEFAULT_LM_STUDIO_BASE_URL,
    DEFAULT_VECTOR_DATA_DIR,
    DEFAULT_VECTOR_MODEL_ID,
    DEFAULT_VECTOR_MODEL_KEY,
    PROMPT_VECTOR_READY_SQL,
)

_PROMPT_VECTOR_DEFAULT_EXPORTS = (
    DEFAULT_LM_STUDIO_BASE_URL,
    DEFAULT_VECTOR_MODEL_ID,
    DEFAULT_VECTOR_MODEL_KEY,
)

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

MAX_ANALYTICS_DAYS = 360
ALL_TIME_QUERY_DAYS = 36500
PROMPT_ROLLUP_PERIODS = {7, 30, 90, 180, 240, 360}
PROMPT_SLIM_STAGES = {"auto_rejected", "candidate", "manual_keep", "manual_reject", "excellent", "archived"}
PROMPT_SLIM_SOURCE_SCOPES = {"natural", "source_template"}
PROMPT_SLIM_SORTS = {
    "quality_score",
    "uses",
    "users",
    "last_seen",
    "result_likes",
    "result_dislikes",
    "gallery_applies",
    "prompt_unlocks",
    "char_count",
}
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

PROMPT_VECTOR_RESUME_LOG = Path(
    os.getenv(
        "LOCAL_ANALYTICS_VECTOR_RESUME_LOG",
        "/tmp/local_analytics_prompt_vector_resume.log",
    )
)


def _main_override(name: str, original: Any) -> Any | None:
    main_module = sys.modules.get("local_analytics_platform.app.main")
    if main_module is None:
        return None
    value = getattr(main_module, name, original)
    return value if value is not original else None

RMB_TO_USDT = 1.0 / 6.7
TON_TO_USDT = 1.4
STARS_TO_USDT = 0.013

CHECKIN_SPLIT_CTES = """
checkin_enriched as (
    select
        flows.*,
        coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
        coalesce(nullif(u.user_group, ''), '凡人') as user_group,
        (substring(
            coalesce(flows.extra_info, '')
            from '"checkin_base_reward"[[:space:]]*:[[:space:]]*([0-9]+)'
        ))::numeric as logged_checkin_base_reward
    from flows
    left join users u on u.id = flows.user_id
),
checkin_split as (
    select
        *,
        case
            when operation_type = 'checkin' and credit_change > 0 then
                least(
                    credit_change,
                    greatest(
                        0::numeric,
                        coalesce(
                            logged_checkin_base_reward,
                            case
                                when credit_change <= 20 then credit_change
                                when current_identity = '内门弟子' and credit_change - 30 in (10, 12, 15, 20) then credit_change - 30
                                when current_identity = '核心弟子' and credit_change - 40 in (10, 12, 15, 20) then credit_change - 40
                                when current_identity = '真传弟子' and credit_change - 50 in (10, 12, 15, 20) then credit_change - 50
                                when user_group = '元婴期' and credit_change - 20 in (0, 30, 40, 50) then 20
                                when user_group = '金丹期' and credit_change - 15 in (0, 30, 40, 50) then 15
                                when user_group = '筑基期' and credit_change - 12 in (0, 30, 40, 50) then 12
                                when user_group = '练气期' and credit_change - 10 in (0, 30, 40, 50) then 10
                                when credit_change - 30 in (10, 12, 15, 20) then credit_change - 30
                                when credit_change - 40 in (10, 12, 15, 20) then credit_change - 40
                                when credit_change - 50 in (10, 12, 15, 20) then credit_change - 50
                                else least(credit_change, 20)
                            end
                        )
                    )
                )
            else 0::numeric
        end as free_checkin_income
    from checkin_enriched
)
"""

def _database_url() -> str:
    override = _main_override("_database_url", _database_url)
    if override is not None:
        return override()
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


_pool_instance: asyncpg.Pool | None = None


async def _pool() -> asyncpg.Pool:
    global _pool_instance
    if _pool_instance is None:
        try:
            max_size = int(os.getenv("LOCAL_ANALYTICS_DB_POOL_MAX_SIZE", "5"))
        except ValueError:
            max_size = 5
        max_size = max(1, max_size)
        _pool_instance = await asyncpg.create_pool(
            dsn=_database_url(),
            min_size=1,
            max_size=max_size,
            command_timeout=60,
        )
    return _pool_instance


async def close_pool() -> None:
    global _pool_instance
    if _pool_instance is not None:
        await _pool_instance.close()
        _pool_instance = None


async def _fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    override = _main_override("_fetch", _fetch)
    if override is not None:
        return await override(query, *args)
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
    override = _main_override("_fetchrow", _fetchrow)
    if override is not None:
        return await override(query, *args)
    rows = await _fetch(query, *args)
    return rows[0] if rows else None


async def _gather_limited(limit: int, *coroutines: Any) -> tuple[Any, ...]:
    semaphore = asyncio.Semaphore(max(1, limit))

    async def run(coroutine: Any) -> Any:
        async with semaphore:
            return await coroutine

    return await asyncio.gather(*(run(coroutine) for coroutine in coroutines))


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


def _clamp_days(value: int) -> int:
    if value <= 0:
        return 0
    return _clamp(value, 1, MAX_ANALYTICS_DAYS)


def _query_days(days: int) -> int:
    return ALL_TIME_QUERY_DAYS if days <= 0 else days


def _resolve_user_profile_period(
    days: int,
    start_date: date | None,
    end_date: date | None,
) -> tuple[int, int, date | None, date | None]:
    days = _clamp_days(days)
    if start_date is None and end_date is None:
        return days, _query_days(days), None, None
    if start_date is None or end_date is None:
        raise HTTPException(status_code=400, detail="start_date and end_date must be provided together")
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    selected_days = (end_date - start_date).days + 1
    if selected_days > MAX_ANALYTICS_DAYS:
        raise HTTPException(status_code=400, detail=f"date range cannot exceed {MAX_ANALYTICS_DAYS} days")
    return selected_days, selected_days, start_date, end_date


def _chart_days(days: int) -> int:
    return MAX_ANALYTICS_DAYS if days <= 0 else days


def _parse_compare_dates(value: str) -> list[str]:
    raw_dates = [item.strip() for item in (value or "").split(",") if item.strip()]
    if not raw_dates:
        raise HTTPException(status_code=400, detail="dates is required")
    if len(raw_dates) > 3:
        raise HTTPException(status_code=400, detail="dates supports at most 3 values")

    parsed: list[str] = []
    seen: set[str] = set()
    for raw in raw_dates:
        try:
            normalized = date.fromisoformat(raw).isoformat()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid date: {raw}") from exc
        if normalized not in seen:
            parsed.append(normalized)
            seen.add(normalized)
    return parsed


def _metric_number(row: dict[str, Any], key: str) -> float:
    value = row.get(key, 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _credit_health_flags(summary: dict[str, Any], health: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if _metric_number(health, "non_paid_grant_ratio") >= 60:
        flags.append("非付费发放占比较高")
    if _metric_number(health, "refund_to_generation_ratio") >= 10:
        flags.append("退款补偿占生成消耗偏高")
    if _metric_number(summary, "balance_burn_days") >= 90:
        flags.append("当前余额可消耗天数偏长")
    if _metric_number(health, "top_income_user_share") >= 8:
        flags.append("收入集中度偏高")
    if _metric_number(health, "checkin_pressure_ratio") >= 45:
        flags.append("签到发放压力偏高")
    if _metric_number(health, "expense_coverage_ratio") < 50 and _metric_number(summary, "gross_income") > 0:
        flags.append("支出消耗不足")
    if _metric_number(summary, "internal_transfer_income") or _metric_number(summary, "internal_transfer_expense"):
        flags.append("Gallery 解锁为内部转移，已单独标记")
    return flags or ["收支结构暂未触发高风险规则"]


def _finance_health_flags(health: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if _metric_number(health, "success_rate") < 70:
        flags.append("成功率偏低")
    if _metric_number(health, "pending_ratio") >= 15:
        flags.append("处理中订单占比偏高")
    if _metric_number(health, "failure_rate") >= 15:
        flags.append("失败订单占比偏高")
    if _metric_number(health, "top_payer_share") >= 35:
        flags.append("头部付费集中度偏高")
    if _metric_number(health, "internal_success_ratio") >= 10:
        flags.append("内部/赠送订单占比偏高")
    if _metric_number(health, "credits_per_usdt") >= 120:
        flags.append("每 USDT 发放灵石偏高")
    return flags or ["充值结构暂未触发高风险规则"]


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


PROMPT_ZERO_WIDTH_CHARS = "".join(
    chr(codepoint)
    for codepoint in (
        8203,
        8204,
        8205,
        8206,
        8207,
        8234,
        8235,
        8236,
        8237,
        8238,
        8288,
        65279,
    )
)
PROMPT_ZERO_WIDTH_TRANSLATION = str.maketrans("", "", PROMPT_ZERO_WIDTH_CHARS)
PROMPT_LEADING_METADATA_RE = re.compile(r"^(\s*\[[^\]]*\]\s*)+")
PROMPT_SPACED_PUNCTUATION_RE = re.compile(r"\s*([,.;:!?()\[\]{}<>，。！？、；：（）【】《》])\s*")
PROMPT_REPEATED_PUNCTUATION_RE = re.compile(r"([,.;:!?，。！？、；：])\1+")


def _normalize_prompt_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = text.translate(PROMPT_ZERO_WIDTH_TRANSLATION)
    text = re.sub(r"\s+", " ", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cc")
    text = PROMPT_LEADING_METADATA_RE.sub("", text)
    text = PROMPT_SPACED_PUNCTUATION_RE.sub(r"\1", text)
    text = PROMPT_REPEATED_PUNCTUATION_RE.sub(r"\1", text)
    return text.strip()


def _prompts_ini_candidates() -> list[Path]:
    configured = os.getenv("LOCAL_ANALYTICS_PROMPTS_INI", "").strip()
    if configured:
        return [Path(configured)]
    return [
        ROOT_DIR / "prompts.ini",
        ROOT_DIR.parent / "prompts.ini",
        Path("prompts.ini"),
    ]


@functools.lru_cache(maxsize=1)
def _builtin_prompt_templates() -> list[tuple[str, str]]:
    config = configparser.ConfigParser()
    loaded = False
    for path in _prompts_ini_candidates():
        if path.exists():
            config.read(path, encoding="utf-8")
            loaded = True
            break
    if not loaded or "prompts" not in config:
        return []

    templates: list[tuple[str, str]] = []
    for key, value in config["prompts"].items():
        normalized = _normalize_prompt_text(value)
        if not normalized or key == "negative_prompt":
            continue
        templates.append((key, normalized))
    return templates


def _builtin_prompt_template_args() -> tuple[list[str], list[str]]:
    templates = _builtin_prompt_templates()
    return [key for key, _ in templates], [prompt for _, prompt in templates]


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


def _prompt_scope_label(row: dict[str, Any]) -> str:
    if _metric_number(row, "derived_uses") >= _metric_number(row, "uses") and _metric_number(row, "uses") > 0:
        return "一键应用衍生"
    if _metric_number(row, "builtin_template_uses") > 0:
        return "内置模板"
    if _metric_number(row, "source_template_posts") > 0:
        return "源模板"
    return "自然输入"


def _enrich_prompt_group(record: asyncpg.Record) -> dict[str, Any]:
    item = _row(record)
    prompt = item.pop("prompt", None)
    item["prompt"] = prompt or ""
    item["prompt_preview"] = _collapse_text(prompt, 260)
    item["scope_label"] = _prompt_scope_label(item)
    return item


def _enrich_prompt_slim_row(record: asyncpg.Record) -> dict[str, Any]:
    item = _row(record)
    item["prompt"] = item.get("prompt") or ""
    item["prompt_preview"] = _collapse_text(item.get("prompt"), 260)
    item["raw_prompt_preview"] = _collapse_text(item.get("raw_prompt_representative"), 220)
    item["task_type_counts"] = _safe_json(item.get("task_type_counts")) or {}
    item["source_counts"] = _safe_json(item.get("source_counts")) or {}
    return item


async def _prompt_mart_status_or_error() -> dict[str, Any]:
    mart_ready = _row(await _fetchrow(PROMPT_MART_READY_SQL))
    if not mart_ready.get("ready"):
        raise HTTPException(
            status_code=503,
            detail="prompt mart is not built; run python -m app.refresh_prompt_mart --full",
        )
    mart_status = _row(await _fetchrow(PROMPT_MART_STATUS_SQL))
    if mart_status.get("normalization_version") != PROMPT_NORMALIZATION_VERSION:
        raise HTTPException(
            status_code=503,
            detail=(
                "prompt mart normalization version mismatch; run "
                "python -m app.refresh_prompt_mart --full --statement-timeout-ms 3600000"
            ),
        )
    return mart_status


async def _prompt_slim_ready_or_error() -> None:
    slim_ready = _row(
        await _fetchrow("select to_regclass('public.analytics_prompt_slim_candidates') is not null as ready")
    )
    if not slim_ready.get("ready"):
        raise HTTPException(
            status_code=503,
            detail="prompt slim table is not built; run python -m app.refresh_prompt_slim_table",
        )


async def _prompt_vector_tables_ready() -> bool:
    ready = _row(await _fetchrow(PROMPT_VECTOR_READY_SQL))
    return bool(ready.get("ready"))


def _prompt_vector_data_dir() -> str:
    return os.getenv("LOCAL_ANALYTICS_VECTOR_DATA_DIR", DEFAULT_VECTOR_DATA_DIR)


def _prompt_vector_lock_path() -> Path:
    return Path(_prompt_vector_data_dir()) / ".refresh_prompt_vectors.lock"


def _is_prompt_vector_refresh_lock_held() -> bool:
    override = _main_override(
        "_is_prompt_vector_refresh_lock_held",
        _is_prompt_vector_refresh_lock_held,
    )
    if override is not None:
        return bool(override())
    lock_path = _prompt_vector_lock_path()
    if not lock_path.exists():
        return False
    with lock_path.open("a", encoding="utf-8") as handle:
        locked = False
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            locked = True
        finally:
            if not locked:
                fcntl.flock(handle, fcntl.LOCK_UN)
        return locked


_prompt_vector_resume_process: Any | None = None
_prompt_vector_resume_started_at: str | None = None
_prompt_vector_resume_last_exit: dict[str, Any] | None = None


def set_prompt_vector_resume_process(process: Any) -> None:
    global _prompt_vector_resume_process
    global _prompt_vector_resume_started_at
    global _prompt_vector_resume_last_exit
    _prompt_vector_resume_process = process
    _prompt_vector_resume_started_at = datetime.now().isoformat()
    _prompt_vector_resume_last_exit = None


def _process_returncode(process: Any) -> int | None:
    poll = getattr(process, "poll", None)
    if callable(poll):
        return poll()
    return getattr(process, "returncode", None)


def _active_prompt_vector_resume_process() -> Any | None:
    global _prompt_vector_resume_process
    global _prompt_vector_resume_last_exit
    process = _prompt_vector_resume_process
    if process is None:
        return None
    return_code = _process_returncode(process)
    if return_code is None:
        return process
    _prompt_vector_resume_last_exit = {
        "pid": process.pid,
        "returncode": return_code,
        "finished_at": datetime.now().isoformat(),
    }
    _prompt_vector_resume_process = None
    return None


def _prompt_vector_resume_status() -> dict[str, Any]:
    process = _active_prompt_vector_resume_process()
    lock_held = _is_prompt_vector_refresh_lock_held()
    return {
        "running": bool(process) or lock_held,
        "lock_held": lock_held,
        "pid": process.pid if process else None,
        "started_at": _prompt_vector_resume_started_at if process else None,
        "last_exit": _prompt_vector_resume_last_exit,
        "log_path": str(PROMPT_VECTOR_RESUME_LOG),
    }


PROMPT_GROUPS_CTE = """
with bounds as (select now() - ($1::int * interval '1 day') as since),
unlock_counts as (
    select post_id, count(*)::bigint as unlocks
    from gallery_prompt_unlocks
    group by post_id
),
gallery_by_task as (
    select
        gp.task_id,
        min(gp.id) as post_id,
        count(*)::bigint as post_count,
        coalesce(sum(gp.likes_count), 0)::bigint as likes,
        coalesce(sum(gp.dislikes_count), 0)::bigint as dislikes,
        coalesce(sum(gp.comments_count), 0)::bigint as comments,
        coalesce(sum(gp.applied_count), 0)::bigint as applies,
        coalesce(sum(coalesce(uc.unlocks, 0)), 0)::bigint as prompt_unlocks
    from gallery_posts gp
    left join unlock_counts uc on uc.post_id = gp.id
    where gp.is_active is true
      and gp.task_id is not null
    group by gp.task_id
),
raw_prompts as (
    select
        o.history_id as id,
        o.task_id,
        o.user_id,
        coalesce(o.task_type, 'unknown') as task_type,
        o.prompt as normalized_prompt,
        coalesce(nullif(o.raw_prompt, ''), o.prompt) as raw_prompt,
        o.char_count,
        o.created_at,
        o.is_favorited,
        o.is_public,
        o.allow_contribute,
        o.builtin_template_key,
        gp.post_id,
        coalesce(gp.post_count, 0)::bigint as post_count,
        coalesce(gp.likes, 0)::bigint as likes,
        coalesce(gp.dislikes, 0)::bigint as dislikes,
        coalesce(gp.comments, 0)::bigint as comments,
        coalesce(gp.applies, 0)::bigint as applies,
        coalesce(gp.prompt_unlocks, 0)::bigint as prompt_unlocks
    from analytics_prompt_occurrence o
    left join gallery_by_task gp on gp.task_id = o.task_id,
    bounds
    where o.created_at >= bounds.since
      and ($2::text is null or o.task_type = $2::text)
),
filtered_before_scope as (
    select *
    from raw_prompts
    where ($4::text is null or lower(normalized_prompt) like $4::text)
),
excluded_counts as (
    select
        case
            when $3::text = 'natural'
            then count(*) filter (where allow_contribute is false)::bigint
            else 0::bigint
        end as derived_records_excluded,
        case
            when $3::text = 'natural'
            then count(*) filter (
                where allow_contribute is distinct from false
                  and builtin_template_key is not null
            )::bigint
            else 0::bigint
        end as builtin_template_records_excluded
    from filtered_before_scope
),
scoped_prompts as (
    select *
    from filtered_before_scope
    where $3::text = 'all'
       or ($3::text = 'natural' and allow_contribute is distinct from false and builtin_template_key is null)
       or ($3::text = 'derived' and allow_contribute is false)
       or ($3::text = 'source_template' and post_id is not null and allow_contribute is distinct from false and builtin_template_key is null)
       or ($3::text = 'builtin_template' and builtin_template_key is not null and allow_contribute is distinct from false)
),
prompt_groups as (
    select
        md5(normalized_prompt) as prompt_hash,
        min(normalized_prompt) as prompt,
        max(char_count)::int as char_count,
        count(*)::bigint as uses,
        count(distinct user_id)::bigint as users,
        count(distinct raw_prompt)::bigint as variant_count,
        array_remove(array_agg(distinct task_type order by task_type), null) as task_types,
        min(created_at) as first_seen,
        max(created_at) as last_seen,
        count(*) filter (where is_favorited is true)::bigint as favorite_records,
        count(*) filter (where is_public is true)::bigint as public_records,
        coalesce(sum(post_count), 0)::bigint as gallery_posts,
        coalesce(sum(likes), 0)::bigint as likes,
        coalesce(sum(dislikes), 0)::bigint as dislikes,
        coalesce(sum(comments), 0)::bigint as comments,
        coalesce(sum(applies), 0)::bigint as applies,
        coalesce(sum(prompt_unlocks), 0)::bigint as prompt_unlocks,
        count(*) filter (where allow_contribute is false)::bigint as derived_uses,
        count(*) filter (where builtin_template_key is not null and allow_contribute is distinct from false)::bigint as builtin_template_uses,
        array_remove(array_agg(distinct builtin_template_key order by builtin_template_key), null) as builtin_template_keys,
        coalesce(sum(post_count) filter (
            where post_id is not null
              and allow_contribute is distinct from false
              and builtin_template_key is null
        ), 0)::bigint as source_template_posts,
        round(
            (
                ln(count(*) + 1) * 8
                + ln(count(distinct user_id) + 1) * 14
                + count(*) filter (where is_favorited is true) * 8
                + coalesce(sum(post_count), 0) * 10
                + coalesce(sum(likes), 0) * 2
                - coalesce(sum(dislikes), 0)
                + coalesce(sum(comments), 0) * 2
                + coalesce(sum(applies), 0) * 5
                + coalesce(sum(prompt_unlocks), 0) * 8
            )::numeric,
            2
        ) as value_score
    from scoped_prompts
    group by md5(normalized_prompt)
    having count(*) >= $6::int
       and count(distinct user_id) >= $5::int
)
"""


PROMPT_GROUPS_ROLLUP_CTE = """
with filtered_before_scope as (
    select *
    from analytics_prompt_rollup_stats
    where period_days = $1::int
      and ($2::text is null or $2::text = any(task_types))
      and (
          $3::text = 'all'
          or scope_key = $3::text
          or ($3::text = 'natural' and scope_key in ('natural', 'derived', 'builtin_template'))
      )
      and ($4::text is null or lower(prompt) like $4::text)
),
excluded_counts as (
    select
        case
            when $3::text = 'natural'
            then coalesce(sum(uses) filter (where scope_key = 'derived'), 0)::bigint
            else 0::bigint
        end as derived_records_excluded,
        case
            when $3::text = 'natural'
            then coalesce(sum(uses) filter (where scope_key = 'builtin_template'), 0)::bigint
            else 0::bigint
        end as builtin_template_records_excluded
    from filtered_before_scope
),
prompt_groups as (
    select *
    from filtered_before_scope
    where scope_key = $3::text
      and uses >= $6::int
      and users >= $5::int
)
"""


PROMPT_GROUPS_ALLTIME_CTE = """
with filtered_before_scope as (
    select *
    from analytics_prompt_group_stats
    where $1::int = 0
      and ($2::text is null or $2::text = any(task_types))
      and (
          $3::text = 'all'
          or scope_key = $3::text
          or ($3::text = 'natural' and scope_key in ('natural', 'derived', 'builtin_template'))
      )
      and ($4::text is null or lower(prompt) like $4::text)
),
excluded_counts as (
    select
        case
            when $3::text = 'natural'
            then coalesce(sum(uses) filter (where scope_key = 'derived'), 0)::bigint
            else 0::bigint
        end as derived_records_excluded,
        case
            when $3::text = 'natural'
            then coalesce(sum(uses) filter (where scope_key = 'builtin_template'), 0)::bigint
            else 0::bigint
        end as builtin_template_records_excluded
    from filtered_before_scope
),
prompt_groups as (
    select *
    from filtered_before_scope
    where scope_key = $3::text
      and uses >= $6::int
      and users >= $5::int
)
"""




__all__ = [name for name in globals() if not name.startswith("__")]
