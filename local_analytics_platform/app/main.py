from __future__ import annotations

import configparser
import fcntl
import functools
import json
import math
import os
import re
import subprocess
import sys
import unicodedata
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

from .prompt_graph import (
    PROMPT_GRAPH_ALGORITHM_VERSION,
    PROMPT_GRAPH_LAYOUT_ALGORITHM,
    PROMPT_GRAPH_READY_SQL,
)
from .prompt_mart import PROMPT_MART_READY_SQL, PROMPT_MART_STATUS_SQL, PROMPT_NORMALIZATION_VERSION
from .prompt_scenes import (
    DEFAULT_CANDIDATES_PER_SCENE,
    PROMPT_SCENE_ALGORITHM_VERSION,
    PROMPT_SCENE_READY_SQL,
)
from .prompt_vectors import (
    DEFAULT_LM_STUDIO_BASE_URL,
    DEFAULT_DUPLICATE_THRESHOLD,
    DEFAULT_SIMILAR_THRESHOLD,
    DEFAULT_VECTOR_DATA_DIR,
    DEFAULT_VECTOR_MODEL_ID,
    DEFAULT_VECTOR_MODEL_KEY,
    PROMPT_VECTOR_READY_SQL,
)
from .user_profile_analytics import (
    get_user_profile_detail,
    get_user_profile_groups,
    get_user_profile_users,
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
PROMPT_VECTOR_SORTS = {
    "member_count",
    "quality_score",
    "total_uses",
    "similarity",
    "refreshed_at",
}
PROMPT_SCENE_SORTS = {
    "member_count",
    "candidate_count",
    "quality_score",
    "total_uses",
    "similarity",
    "refreshed_at",
}
PROMPT_SCENE_CONFIDENCE_BANDS = {"all", "high", "medium", "low"}
PROMPT_GRAPH_LEVELS = {"scene", "micro"}
PROMPT_GRAPH_EDGE_TYPES = {"all", "similarity", "centroid_bridge", "scene_micro"}

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


def _enrich_prompt_vector_cluster(record: asyncpg.Record) -> dict[str, Any]:
    item = _row(record)
    prompt = item.get("representative_prompt") or item.get("prompt") or ""
    item["representative_prompt"] = prompt
    item["representative_preview"] = _collapse_text(prompt, 240)
    return item


def _enrich_prompt_vector_member(record: asyncpg.Record) -> dict[str, Any]:
    item = _row(record)
    item["prompt"] = item.get("prompt") or ""
    item["prompt_preview"] = _collapse_text(item.get("prompt"), 260)
    item["raw_prompt_preview"] = _collapse_text(item.get("raw_prompt_representative"), 180)
    return item


def _enrich_prompt_scene(record: asyncpg.Record) -> dict[str, Any]:
    item = _row(record)
    item.pop("centroid_f16", None)
    prompt = item.get("representative_prompt") or item.get("prompt") or ""
    item["representative_prompt"] = prompt
    item["representative_preview"] = _collapse_text(prompt, 240)
    item["display_label"] = item.get("manual_label") or item["representative_preview"]
    return item


def _enrich_prompt_scene_member(record: asyncpg.Record) -> dict[str, Any]:
    item = _row(record)
    item["prompt"] = item.get("prompt") or ""
    item["prompt_preview"] = _collapse_text(item.get("prompt"), 260)
    item["raw_prompt_preview"] = _collapse_text(item.get("raw_prompt_representative"), 180)
    return item


def _enrich_prompt_graph_node(record: asyncpg.Record) -> dict[str, Any]:
    item = _row(record)
    community_id = item.get("community_id")
    label = item.get("label") or item.get("representative_prompt") or community_id or ""
    item["id"] = community_id
    item["name"] = _collapse_text(label, 80)
    item["label"] = label
    item["representative_preview"] = _collapse_text(item.get("representative_prompt"), 220)
    item["symbol_size"] = max(8, min(42, 6 + math.log1p(float(item.get("member_count") or 0)) * 3))
    return item


def _enrich_prompt_graph_edge(record: asyncpg.Record) -> dict[str, Any]:
    item = _row(record)
    item["source"] = item.get("source_community_id")
    item["target"] = item.get("target_community_id")
    item["value"] = item.get("weight")
    return item


def _enrich_prompt_graph_member(record: asyncpg.Record) -> dict[str, Any]:
    item = _row(record)
    item["prompt"] = item.get("prompt") or ""
    item["prompt_preview"] = _collapse_text(item.get("prompt"), 260)
    item["raw_prompt_preview"] = _collapse_text(item.get("raw_prompt_representative"), 180)
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


async def _prompt_scene_tables_ready() -> bool:
    ready = _row(await _fetchrow(PROMPT_SCENE_READY_SQL))
    return bool(ready.get("ready"))


async def _prompt_graph_tables_ready() -> bool:
    ready = _row(await _fetchrow(PROMPT_GRAPH_READY_SQL))
    return bool(ready.get("ready"))


def _prompt_vector_data_dir() -> str:
    return os.getenv("LOCAL_ANALYTICS_VECTOR_DATA_DIR", DEFAULT_VECTOR_DATA_DIR)


def _prompt_vector_lock_path() -> Path:
    return Path(_prompt_vector_data_dir()) / ".refresh_prompt_vectors.lock"


def _is_prompt_vector_refresh_lock_held() -> bool:
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


def _active_prompt_vector_resume_process() -> subprocess.Popen | None:
    process = getattr(app.state, "prompt_vector_resume_process", None)
    if process is None:
        return None
    return_code = process.poll()
    if return_code is None:
        return process
    app.state.prompt_vector_resume_last_exit = {
        "pid": process.pid,
        "returncode": return_code,
        "finished_at": datetime.now().isoformat(),
    }
    app.state.prompt_vector_resume_process = None
    return None


def _prompt_vector_resume_status() -> dict[str, Any]:
    process = _active_prompt_vector_resume_process()
    lock_held = _is_prompt_vector_refresh_lock_held()
    return {
        "running": bool(process) or lock_held,
        "lock_held": lock_held,
        "pid": process.pid if process else None,
        "started_at": getattr(app.state, "prompt_vector_resume_started_at", None) if process else None,
        "last_exit": getattr(app.state, "prompt_vector_resume_last_exit", None),
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


@app.get("/api/user-analytics")
async def user_analytics(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(12, ge=1, le=50),
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    chart_days = _chart_days(days)
    limit = _clamp(limit, 1, 50)
    summary = await _fetchrow(
        """
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        successful_order_users as (
            select distinct internal_user_id as user_id
            from orders
            where status = 'SUCCESS'
              and internal_user_id is not null
        ),
        real_success_payers as (
            select distinct internal_user_id as user_id
            from orders
            where status = 'SUCCESS'
              and coalesce(final_price, 0) > 0
              and payment_channel in ('RMB', 'TON', 'XTR')
              and internal_user_id is not null
        ),
        low_trust_free_tier_users as (
            select users.*
            from users
            left join successful_order_users on successful_order_users.user_id = users.id
            where coalesce(users.checkin_count, 0) > 7
              and successful_order_users.user_id is null
        ),
        referred_real_success_orders as (
            select orders.*
            from orders
            join referrals on referrals.invitee_id = orders.internal_user_id
            where orders.status = 'SUCCESS'
              and coalesce(orders.final_price, 0) > 0
              and orders.payment_channel in ('RMB', 'TON', 'XTR')
              and orders.internal_user_id is not null
        ),
        low_trust_referral_edges as (
            select
                referrals.inviter_id,
                referrals.invitee_id,
                invitees.is_channel_member,
                coalesce(invitees.generation_count, 0) as invitee_generation_count,
                (
                    coalesce(invitees.checkin_count, 0) > 7
                    and invitee_success.user_id is null
                ) as invitee_is_low_trust_free_tier
            from referrals
            join low_trust_free_tier_users inviters on inviters.id = referrals.inviter_id
            left join users invitees on invitees.id = referrals.invitee_id
            left join successful_order_users invitee_success on invitee_success.user_id = referrals.invitee_id
        ),
        low_trust_referred_real_success_orders as (
            select orders.*
            from orders
            join low_trust_referral_edges edges on edges.invitee_id = orders.internal_user_id
            where orders.status = 'SUCCESS'
              and coalesce(orders.final_price, 0) > 0
              and orders.payment_channel in ('RMB', 'TON', 'XTR')
              and orders.internal_user_id is not null
        ),
        inviter_recharge_rates as (
            select
                referrals.inviter_id,
                count(distinct referrals.invitee_id)::numeric as referral_relations,
                count(distinct real_success_payers.user_id)::numeric as recharged_invitees_count,
                round(
                    case
                        when count(distinct referrals.invitee_id) > 0
                        then count(distinct real_success_payers.user_id)::numeric
                            / count(distinct referrals.invitee_id)::numeric * 100
                        else 0
                    end,
                    2
                )::numeric as invitee_recharge_rate
            from referrals
            left join real_success_payers on real_success_payers.user_id = referrals.invitee_id
            group by referrals.inviter_id
        ),
        affiliate_ledger as (
            select
                coalesce(sum(amount_usdt) filter (where direction = 'IN'), 0)::numeric as total_commission_usdt,
                coalesce(sum(amount_usdt) filter (where direction = 'OUT'), 0)::numeric as spent_commission_usdt,
                coalesce(sum(case
                    when direction = 'IN' then amount_usdt
                    when direction = 'OUT' then -amount_usdt
                    else 0
                end), 0)::numeric as available_balance_usdt
            from affiliate_transactions
            where status = 'SUCCESS'
        )
        select
            count(*)::bigint as total_users,
            count(*) filter (where created_at >= bounds.since)::bigint as new_users,
            count(*) filter (where last_activity >= bounds.since)::bigint as active_users,
            count(*) filter (where is_channel_member is true)::bigint as channel_members,
            count(*) filter (where hashed_password is not null)::bigint as password_users,
            count(*) filter (where is_submission_banned is true)::bigint as submission_banned_users,
            count(*) filter (where coalesce(generation_count, 0) > 0)::bigint as generation_users,
            (select count(*) from real_success_payers)::bigint as paying_users,
            (
                select count(*)
                from real_success_payers
                join users payer_users on payer_users.id = real_success_payers.user_id
                where payer_users.is_channel_member is true
            )::bigint as paying_channel_members,
            (
                select count(*)
                from real_success_payers
                join users payer_users on payer_users.id = real_success_payers.user_id
                where coalesce(payer_users.generation_count, 0) > 0
            )::bigint as paying_generation_users,
            (
                select count(*)
                from real_success_payers
                join users payer_users on payer_users.id = real_success_payers.user_id
                join bounds payer_bounds on true
                where payer_users.last_activity >= payer_bounds.since
            )::bigint as active_paying_users,
            round(
                case
                    when count(*) > 0
                    then (select count(*) from real_success_payers)::numeric / count(*)::numeric * 100
                    else 0
                end,
                2
            )::numeric as recharge_rate_total_users,
            round(
                case
                    when count(*) filter (where is_channel_member is true) > 0
                    then (
                        select count(*)
                        from real_success_payers
                        join users payer_users on payer_users.id = real_success_payers.user_id
                        where payer_users.is_channel_member is true
                    )::numeric / (count(*) filter (where is_channel_member is true))::numeric * 100
                    else 0
                end,
                2
            )::numeric as recharge_rate_channel_members,
            round(
                case
                    when count(*) filter (where coalesce(generation_count, 0) > 0) > 0
                    then (
                        select count(*)
                        from real_success_payers
                        join users payer_users on payer_users.id = real_success_payers.user_id
                        where coalesce(payer_users.generation_count, 0) > 0
                    )::numeric / (count(*) filter (where coalesce(generation_count, 0) > 0))::numeric * 100
                    else 0
                end,
                2
            )::numeric as recharge_rate_generation_users,
            round(
                case
                    when count(*) filter (where last_activity >= bounds.since) > 0
                    then (
                        select count(*)
                        from real_success_payers
                        join users payer_users on payer_users.id = real_success_payers.user_id
                        join bounds payer_bounds on true
                        where payer_users.last_activity >= payer_bounds.since
                    )::numeric / (count(*) filter (where last_activity >= bounds.since))::numeric * 100
                    else 0
                end,
                2
            )::numeric as recharge_rate_active_users,
            coalesce((
                select round(avg(invitee_recharge_rate), 2)
                from inviter_recharge_rates
            ), 0)::numeric as avg_inviter_invitee_recharge_rate,
            (select count(*) from inviter_recharge_rates)::bigint as inviter_recharge_rate_sample_size,
            coalesce(sum(coalesce(credits, 0)), 0)::bigint as total_credits,
            coalesce(
                sum(coalesce(credits, 0)) filter (
                    where coalesce(generation_count, 0) > 0
                       or last_activity >= bounds.since
                ),
                0
            )::bigint as active_credits,
            (select count(*) from low_trust_free_tier_users)::bigint as low_trust_free_tier_users,
            (
                select count(*)
                from low_trust_free_tier_users, bounds as low_trust_bounds
                where last_activity >= low_trust_bounds.since
            )::bigint as low_trust_active_users,
            (select count(*) from low_trust_free_tier_users where coalesce(generation_count, 0) > 0)::bigint as low_trust_generation_users,
            (select coalesce(sum(coalesce(credits, 0)), 0) from low_trust_free_tier_users)::bigint as low_trust_total_credits,
            (select count(distinct inviter_id) from low_trust_referral_edges)::bigint as low_trust_inviters_count,
            (
                select count(distinct invitee_id)
                from low_trust_referral_edges
                where invitee_is_low_trust_free_tier is false
            )::bigint as low_trust_non_low_trust_invitees_count,
            (
                select count(distinct internal_user_id)
                from low_trust_referred_real_success_orders
            )::bigint as low_trust_recharged_invitees_count,
            (select count(*) from referrals)::bigint as referral_relations,
            (select count(distinct inviter_id) from referrals)::bigint as inviters_count,
            (
                select count(distinct referrals.invitee_id)
                from referrals
                join users invitees on invitees.id = referrals.invitee_id
                where invitees.is_channel_member is true
            )::bigint as invitee_channel_members,
            (
                select count(distinct referrals.invitee_id)
                from referrals
                join users invitees on invitees.id = referrals.invitee_id
                where coalesce(invitees.generation_count, 0) > 0
            )::bigint as invitee_generation_users,
            (select count(distinct internal_user_id) from referred_real_success_orders)::bigint as recharged_invitees_count,
            (select count(*) from referred_real_success_orders)::bigint as invitee_recharge_orders,
            coalesce((
                select sum(final_price) from referred_real_success_orders where payment_channel = 'RMB'
            ), 0)::numeric as invitee_recharge_total_rmb,
            coalesce((
                select sum(final_price) from referred_real_success_orders where payment_channel = 'TON'
            ), 0)::numeric as invitee_recharge_total_ton,
            coalesce((
                select sum(final_price) from referred_real_success_orders where payment_channel = 'XTR'
            ), 0)::numeric as invitee_recharge_total_stars,
            coalesce((
                select
                    sum(case
                        when payment_channel = 'RMB' then final_price * $2::numeric
                        when payment_channel = 'TON' then final_price * $3::numeric
                        when payment_channel = 'XTR' then final_price * $4::numeric
                        else 0
                    end)
                from referred_real_success_orders
            ), 0)::numeric as invitee_recharge_total_usdt,
            (select total_commission_usdt from affiliate_ledger)::numeric as affiliate_total_commission_usdt,
            (select spent_commission_usdt from affiliate_ledger)::numeric as affiliate_spent_commission_usdt,
            (select available_balance_usdt from affiliate_ledger)::numeric as affiliate_available_balance_usdt
        from users, bounds
        """,
        query_days,
        RMB_TO_USDT,
        TON_TO_USDT,
        STARS_TO_USDT,
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
        channel_member_daily as (
            select created_at::date as day, count(*)::bigint as new_channel_members
            from users
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
              and is_channel_member is true
            group by 1
        ),
        first_generation_daily as (
            select first_day as day, count(*)::bigint as new_generation_users
            from (
                select user_id, min(created_at)::date as first_day
                from history
                where user_id is not null
                group by user_id
            ) first_generations
            where first_day >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        active_daily as (
            select created_at::date as day, count(distinct user_id)::bigint as active_users
            from history
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        checkin_daily as (
            select checkin_date::date as day, count(*)::bigint as checkins
            from checkin_history
            where checkin_date >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        )
        select
            to_char(days.day, 'YYYY-MM-DD') as day,
            coalesce(user_daily.new_users, 0)::bigint as new_users,
            coalesce(channel_member_daily.new_channel_members, 0)::bigint as new_channel_members,
            coalesce(first_generation_daily.new_generation_users, 0)::bigint as new_generation_users,
            coalesce(active_daily.active_users, 0)::bigint as active_users,
            coalesce(checkin_daily.checkins, 0)::bigint as checkins
        from days
        left join user_daily using (day)
        left join channel_member_daily using (day)
        left join first_generation_daily using (day)
        left join active_daily using (day)
        left join checkin_daily using (day)
        order by days.day
        """,
        chart_days,
    )
    identity = await _fetch(
        """
        with grouped as (
            select
                coalesce(nullif(current_identity, ''), '外门弟子') as identity_label,
                count(*)::bigint as users
            from users
            group by 1
        )
        select identity_label as label, users as count
        from grouped
        order by case identity_label
            when '外门弟子' then 1
            when '内门弟子' then 2
            when '核心弟子' then 3
            when '真传弟子' then 4
            else 99
        end, identity_label
        """
    )
    user_group = await _fetch(
        """
        with grouped as (
            select
                coalesce(nullif(user_group, ''), '凡人') as user_group_label,
                count(*)::bigint as users
            from users
            group by 1
        )
        select user_group_label as label, users as count
        from grouped
        order by case user_group_label
            when '凡人' then 1
            when '练气期' then 2
            when '筑基期' then 3
            when '金丹期' then 4
            when '元婴期' then 5
            else 99
        end, user_group_label
        """
    )
    credit_holding = await _fetch(
        """
        with bucketed as (
            select case
                when coalesce(credits, 0) <= 0 then '0'
                when coalesce(credits, 0) between 1 and 10 then '1-10'
                when coalesce(credits, 0) between 11 and 50 then '11-50'
                when coalesce(credits, 0) between 51 and 100 then '51-100'
                when coalesce(credits, 0) between 101 and 500 then '101-500'
                when coalesce(credits, 0) between 501 and 1000 then '501-1000'
                when coalesce(credits, 0) between 1001 and 5000 then '1001-5000'
                else '5000+'
            end as credit_bucket
            from users
        )
        select credit_bucket as label, count(*)::bigint as count
        from bucketed
        group by 1
        order by case credit_bucket
            when '0' then 1
            when '1-10' then 2
            when '11-50' then 3
            when '51-100' then 4
            when '101-500' then 5
            when '501-1000' then 6
            when '1001-5000' then 7
            else 8
        end
        """
    )
    generation_count = await _fetch(
        """
        with bucketed as (
            select case
                when coalesce(generation_count, 0) <= 0 then '0'
                when coalesce(generation_count, 0) = 1 then '1'
                when coalesce(generation_count, 0) = 2 then '2'
                when coalesce(generation_count, 0) = 3 then '3'
                when coalesce(generation_count, 0) = 4 then '4'
                when coalesce(generation_count, 0) = 5 then '5'
                when coalesce(generation_count, 0) between 6 and 10 then '6-10'
                when coalesce(generation_count, 0) between 11 and 20 then '11-20'
                when coalesce(generation_count, 0) between 21 and 50 then '21-50'
                when coalesce(generation_count, 0) between 51 and 100 then '51-100'
                when coalesce(generation_count, 0) between 101 and 200 then '101-200'
                when coalesce(generation_count, 0) between 201 and 500 then '201-500'
                when coalesce(generation_count, 0) between 501 and 1000 then '501-1000'
                else '1000+'
            end as generation_bucket
            from users
        )
        select generation_bucket as label, count(*)::bigint as count
        from bucketed
        group by 1
        order by case generation_bucket
            when '0' then 1
            when '1' then 2
            when '2' then 3
            when '3' then 4
            when '4' then 5
            when '5' then 6
            when '6-10' then 7
            when '11-20' then 8
            when '21-50' then 9
            when '51-100' then 10
            when '101-200' then 11
            when '201-500' then 12
            when '501-1000' then 13
            else 14
        end
        """
    )
    activity_segments = await _fetch(
        """
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        bucketed as (
            select case
                when last_activity >= now() - interval '1 day' then '24h 活跃'
                when last_activity >= now() - interval '7 day' then '7天活跃'
                when last_activity >= bounds.since then '近周期活跃'
                when last_activity is null then '从未活跃'
                else '沉睡用户'
            end as activity_segment
            from users, bounds
        )
        select activity_segment as label, count(*)::bigint as count
        from bucketed
        group by 1
        order by case activity_segment
            when '24h 活跃' then 1
            when '7天活跃' then 2
            when '近周期活跃' then 3
            when '沉睡用户' then 4
            else 5
        end
        """,
        query_days,
    )
    generation_rank = await _fetch(
        """
        select
            'generation_rank' as leaderboard,
            id,
            username,
            full_name,
            coalesce(nullif(current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(user_group, ''), '凡人') as user_group,
            coalesce(generation_count, 0)::bigint as generation_count,
            coalesce(credits, 0)::bigint as credits,
            coalesce(referral_count, 0)::bigint as referral_count,
            coalesce(checkin_count, 0)::bigint as checkin_count,
            last_activity,
            created_at,
            is_channel_member,
            is_submission_banned
        from users
        order by coalesce(generation_count, 0) desc, id desc
        limit $1::int
        """,
        limit,
    )
    credits_rank = await _fetch(
        """
        select
            'credits_rank' as leaderboard,
            id,
            username,
            full_name,
            coalesce(nullif(current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(user_group, ''), '凡人') as user_group,
            coalesce(generation_count, 0)::bigint as generation_count,
            coalesce(credits, 0)::bigint as credits,
            coalesce(referral_count, 0)::bigint as referral_count,
            coalesce(checkin_count, 0)::bigint as checkin_count,
            last_activity,
            created_at,
            is_channel_member,
            is_submission_banned
        from users
        order by coalesce(credits, 0) desc, id desc
        limit $1::int
        """,
        limit,
    )
    referrals_rank = await _fetch(
        """
        with inviter_recharge as (
            select
                referrals.inviter_id,
                count(distinct referrals.invitee_id)::bigint as referral_relations,
                count(distinct referrals.invitee_id) filter (
                    where invitees.is_channel_member is true
                )::bigint as invitee_channel_members,
                count(distinct referrals.invitee_id) filter (
                    where coalesce(invitees.generation_count, 0) > 0
                )::bigint as invitee_generation_users,
                count(distinct orders.internal_user_id) filter (
                    where orders.id is not null
                )::bigint as recharged_invitees_count,
                round(
                    case
                        when count(distinct referrals.invitee_id) > 0
                        then count(distinct orders.internal_user_id) filter (where orders.id is not null)::numeric
                            / count(distinct referrals.invitee_id)::numeric * 100
                        else 0
                    end,
                    2
                )::numeric as invitee_recharge_rate,
                count(orders.id)::bigint as invitee_recharge_orders,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'RMB'), 0)::numeric as invitee_recharge_total_rmb,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'TON'), 0)::numeric as invitee_recharge_total_ton,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'XTR'), 0)::numeric as invitee_recharge_total_stars,
                coalesce(sum(case
                    when orders.payment_channel = 'RMB' then orders.final_price * $2::numeric
                    when orders.payment_channel = 'TON' then orders.final_price * $3::numeric
                    when orders.payment_channel = 'XTR' then orders.final_price * $4::numeric
                    else 0
                end), 0)::numeric as invitee_recharge_total_usdt
            from referrals
            left join users invitees on invitees.id = referrals.invitee_id
            left join orders on orders.internal_user_id = referrals.invitee_id
                and orders.status = 'SUCCESS'
                and coalesce(orders.final_price, 0) > 0
                and orders.payment_channel in ('RMB', 'TON', 'XTR')
            group by referrals.inviter_id
        ),
        affiliate_ledger as (
            select
                user_id,
                coalesce(sum(amount_usdt) filter (where direction = 'IN'), 0)::numeric as affiliate_total_commission_usdt,
                coalesce(sum(amount_usdt) filter (where direction = 'OUT'), 0)::numeric as affiliate_spent_commission_usdt,
                coalesce(sum(case
                    when direction = 'IN' then amount_usdt
                    when direction = 'OUT' then -amount_usdt
                    else 0
                end), 0)::numeric as affiliate_available_balance_usdt
            from affiliate_transactions
            where status = 'SUCCESS'
            group by user_id
        )
        select
            'referrals_rank' as leaderboard,
            users.id,
            users.username,
            users.full_name,
            coalesce(nullif(users.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(users.user_group, ''), '凡人') as user_group,
            coalesce(users.generation_count, 0)::bigint as generation_count,
            coalesce(users.credits, 0)::bigint as credits,
            coalesce(inviter_recharge.referral_relations, users.referral_count, 0)::bigint as referral_count,
            coalesce(inviter_recharge.referral_relations, users.referral_count, 0)::bigint as referral_relations,
            coalesce(inviter_recharge.invitee_channel_members, 0)::bigint as invitee_channel_members,
            coalesce(inviter_recharge.invitee_generation_users, 0)::bigint as invitee_generation_users,
            coalesce(inviter_recharge.recharged_invitees_count, 0)::bigint as recharged_invitees_count,
            coalesce(inviter_recharge.invitee_recharge_rate, 0)::numeric as invitee_recharge_rate,
            coalesce(inviter_recharge.invitee_recharge_orders, 0)::bigint as invitee_recharge_orders,
            coalesce(inviter_recharge.invitee_recharge_total_rmb, 0)::numeric as invitee_recharge_total_rmb,
            coalesce(inviter_recharge.invitee_recharge_total_ton, 0)::numeric as invitee_recharge_total_ton,
            coalesce(inviter_recharge.invitee_recharge_total_stars, 0)::numeric as invitee_recharge_total_stars,
            coalesce(inviter_recharge.invitee_recharge_total_usdt, 0)::numeric as invitee_recharge_total_usdt,
            coalesce(affiliate_ledger.affiliate_total_commission_usdt, 0)::numeric as affiliate_total_commission_usdt,
            coalesce(affiliate_ledger.affiliate_spent_commission_usdt, 0)::numeric as affiliate_spent_commission_usdt,
            coalesce(affiliate_ledger.affiliate_available_balance_usdt, 0)::numeric as affiliate_available_balance_usdt,
            coalesce(users.checkin_count, 0)::bigint as checkin_count,
            users.last_activity,
            users.created_at,
            users.is_channel_member,
            users.is_submission_banned
        from users
        join inviter_recharge on inviter_recharge.inviter_id = users.id
        left join affiliate_ledger on affiliate_ledger.user_id = users.id
        order by
            coalesce(inviter_recharge.recharged_invitees_count, 0) desc,
            coalesce(inviter_recharge.invitee_recharge_total_usdt, 0) desc,
            coalesce(inviter_recharge.referral_relations, users.referral_count, 0) desc,
            users.id desc
        limit $1::int
        """,
        limit,
        RMB_TO_USDT,
        TON_TO_USDT,
        STARS_TO_USDT,
    )
    low_trust_rank = await _fetch(
        """
        with successful_order_users as (
            select distinct internal_user_id as user_id
            from orders
            where status = 'SUCCESS'
              and internal_user_id is not null
        ),
        low_trust_users as (
            select users.*
            from users
            left join successful_order_users on successful_order_users.user_id = users.id
            where coalesce(users.checkin_count, 0) > 7
              and successful_order_users.user_id is null
        ),
        invitee_rollup as (
            select
                referrals.inviter_id,
                count(distinct referrals.invitee_id)::bigint as referral_relations,
                count(distinct referrals.invitee_id) filter (
                    where not (
                        coalesce(invitees.checkin_count, 0) > 7
                        and invitee_success.user_id is null
                    )
                )::bigint as non_low_trust_invitees_count,
                round(
                    case
                        when count(distinct referrals.invitee_id) > 0
                        then count(distinct referrals.invitee_id) filter (
                            where not (
                                coalesce(invitees.checkin_count, 0) > 7
                                and invitee_success.user_id is null
                            )
                        )::numeric / count(distinct referrals.invitee_id)::numeric * 100
                        else 0
                    end,
                    2
                )::numeric as non_low_trust_invitee_rate,
                count(distinct referrals.invitee_id) filter (
                    where coalesce(invitees.checkin_count, 0) > 7
                      and invitee_success.user_id is null
                )::bigint as low_trust_invitees_count,
                count(distinct referrals.invitee_id) filter (
                    where invitees.is_channel_member is true
                )::bigint as invitee_channel_members,
                count(distinct referrals.invitee_id) filter (
                    where coalesce(invitees.generation_count, 0) > 0
                )::bigint as invitee_generation_users,
                count(distinct orders.internal_user_id) filter (
                    where orders.id is not null
                )::bigint as recharged_invitees_count,
                round(
                    case
                        when count(distinct referrals.invitee_id) > 0
                        then count(distinct orders.internal_user_id) filter (where orders.id is not null)::numeric
                            / count(distinct referrals.invitee_id)::numeric * 100
                        else 0
                    end,
                    2
                )::numeric as invitee_recharge_rate,
                count(orders.id)::bigint as invitee_recharge_orders,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'RMB'), 0)::numeric as invitee_recharge_total_rmb,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'TON'), 0)::numeric as invitee_recharge_total_ton,
                coalesce(sum(orders.final_price) filter (where orders.payment_channel = 'XTR'), 0)::numeric as invitee_recharge_total_stars,
                coalesce(sum(case
                    when orders.payment_channel = 'RMB' then orders.final_price * $2::numeric
                    when orders.payment_channel = 'TON' then orders.final_price * $3::numeric
                    when orders.payment_channel = 'XTR' then orders.final_price * $4::numeric
                    else 0
                end), 0)::numeric as invitee_recharge_total_usdt
            from referrals
            left join users invitees on invitees.id = referrals.invitee_id
            left join successful_order_users invitee_success on invitee_success.user_id = referrals.invitee_id
            left join orders on orders.internal_user_id = referrals.invitee_id
                and orders.status = 'SUCCESS'
                and coalesce(orders.final_price, 0) > 0
                and orders.payment_channel in ('RMB', 'TON', 'XTR')
            group by referrals.inviter_id
        )
        select
            'low_trust_rank' as leaderboard,
            low_trust_users.id,
            low_trust_users.username,
            low_trust_users.full_name,
            coalesce(nullif(low_trust_users.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(low_trust_users.user_group, ''), '凡人') as user_group,
            coalesce(low_trust_users.generation_count, 0)::bigint as generation_count,
            coalesce(low_trust_users.credits, 0)::bigint as credits,
            coalesce(invitee_rollup.referral_relations, low_trust_users.referral_count, 0)::bigint as referral_count,
            coalesce(invitee_rollup.referral_relations, low_trust_users.referral_count, 0)::bigint as referral_relations,
            coalesce(invitee_rollup.non_low_trust_invitees_count, 0)::bigint as non_low_trust_invitees_count,
            coalesce(invitee_rollup.non_low_trust_invitee_rate, 0)::numeric as non_low_trust_invitee_rate,
            coalesce(invitee_rollup.low_trust_invitees_count, 0)::bigint as low_trust_invitees_count,
            coalesce(invitee_rollup.invitee_channel_members, 0)::bigint as invitee_channel_members,
            coalesce(invitee_rollup.invitee_generation_users, 0)::bigint as invitee_generation_users,
            coalesce(invitee_rollup.recharged_invitees_count, 0)::bigint as recharged_invitees_count,
            coalesce(invitee_rollup.invitee_recharge_rate, 0)::numeric as invitee_recharge_rate,
            coalesce(invitee_rollup.invitee_recharge_orders, 0)::bigint as invitee_recharge_orders,
            coalesce(invitee_rollup.invitee_recharge_total_rmb, 0)::numeric as invitee_recharge_total_rmb,
            coalesce(invitee_rollup.invitee_recharge_total_ton, 0)::numeric as invitee_recharge_total_ton,
            coalesce(invitee_rollup.invitee_recharge_total_stars, 0)::numeric as invitee_recharge_total_stars,
            coalesce(invitee_rollup.invitee_recharge_total_usdt, 0)::numeric as invitee_recharge_total_usdt,
            coalesce(low_trust_users.checkin_count, 0)::bigint as checkin_count,
            low_trust_users.last_activity,
            low_trust_users.created_at,
            low_trust_users.is_channel_member,
            low_trust_users.is_submission_banned,
            true as is_low_trust_free_tier
        from low_trust_users
        left join invitee_rollup on invitee_rollup.inviter_id = low_trust_users.id
        order by
            coalesce(invitee_rollup.non_low_trust_invitees_count, 0) desc,
            coalesce(invitee_rollup.recharged_invitees_count, 0) desc,
            coalesce(invitee_rollup.invitee_recharge_total_usdt, 0) desc,
            coalesce(invitee_rollup.invitee_generation_users, 0) desc,
            coalesce(invitee_rollup.invitee_channel_members, 0) desc,
            coalesce(low_trust_users.checkin_count, 0) desc,
            low_trust_users.id desc
        limit $1::int
        """,
        limit,
        RMB_TO_USDT,
        TON_TO_USDT,
        STARS_TO_USDT,
    )
    recent_active_rank = await _fetch(
        """
        select
            'recent_active_rank' as leaderboard,
            id,
            username,
            full_name,
            coalesce(nullif(current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(user_group, ''), '凡人') as user_group,
            coalesce(generation_count, 0)::bigint as generation_count,
            coalesce(credits, 0)::bigint as credits,
            coalesce(referral_count, 0)::bigint as referral_count,
            coalesce(checkin_count, 0)::bigint as checkin_count,
            last_activity,
            created_at,
            is_channel_member,
            is_submission_banned
        from users
        order by last_activity desc nulls last, id desc
        limit $1::int
        """,
        limit,
    )
    return {
        "days": days,
        "limit": limit,
        "summary": _row(summary),
        "daily": _rows(daily),
        "distributions": {
            "identity": _rows(identity),
            "user_group": _rows(user_group),
            "credit_holding": _rows(credit_holding),
            "generation_count": _rows(generation_count),
            "activity_segments": _rows(activity_segments),
        },
        "leaderboards": {
            "generation": _rows(generation_rank),
            "credits": _rows(credits_rank),
            "referrals": _rows(referrals_rank),
            "low_trust": _rows(low_trust_rank),
            "recent_active": _rows(recent_active_rank),
        },
    }


@app.get("/api/user-analytics/users")
async def user_analytics_users(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    page: int = Query(1, ge=1, le=10000),
    size: int = Query(25, ge=1, le=100),
    search: str = Query(""),
    segment: str = Query("all"),
    sort: str = Query("last_activity"),
    dimension: str = Query(""),
    group_key: str = Query(""),
) -> dict[str, Any]:
    days, query_days, resolved_start_date, resolved_end_date = _resolve_user_profile_period(
        days,
        start_date,
        end_date,
    )
    return await get_user_profile_users(
        fetch=_fetch,
        fetchrow=_fetchrow,
        days=days,
        query_days=query_days,
        page=page,
        size=size,
        search=search,
        segment=segment,
        sort=sort,
        dimension=dimension or None,
        group_key=group_key,
        rmb_to_usdt=RMB_TO_USDT,
        ton_to_usdt=TON_TO_USDT,
        stars_to_usdt=STARS_TO_USDT,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
    )


@app.get("/api/user-analytics/groups")
async def user_analytics_groups(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    dimension: str = Query("payer"),
    segment: str = Query("all"),
    search: str = Query(""),
    sort: str = Query("users"),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    days, query_days, resolved_start_date, resolved_end_date = _resolve_user_profile_period(
        days,
        start_date,
        end_date,
    )
    return await get_user_profile_groups(
        fetch=_fetch,
        days=days,
        query_days=query_days,
        dimension=dimension,
        segment=segment,
        search=search,
        sort=sort,
        limit=limit,
        rmb_to_usdt=RMB_TO_USDT,
        ton_to_usdt=TON_TO_USDT,
        stars_to_usdt=STARS_TO_USDT,
        start_date=resolved_start_date,
        end_date=resolved_end_date,
    )


@app.get("/api/user-analytics/users/{user_id}")
async def user_analytics_user_detail(
    user_id: int,
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
) -> dict[str, Any]:
    days = _clamp_days(days)
    return await get_user_profile_detail(
        fetch=_fetch,
        fetchrow=_fetchrow,
        user_id=user_id,
        days=days,
        query_days=_query_days(days),
        rmb_to_usdt=RMB_TO_USDT,
        ton_to_usdt=TON_TO_USDT,
        stars_to_usdt=STARS_TO_USDT,
    )


@app.get("/api/credit-flow-analytics")
async def credit_flow_analytics(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(12, ge=1, le=50),
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    chart_days = _chart_days(days)
    limit = _clamp(limit, 1, 50)
    summary_row = await _fetchrow(
        f"""
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        flows as (
            select
                user_id,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs, bounds
            where created_at >= bounds.since
        ),
        {CHECKIN_SPLIT_CTES},
        summary as (
            select
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as gross_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as gross_expense,
                coalesce(sum(credit_change), 0)::bigint as net_change,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'recharge'), 0)::bigint as paid_recharge_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as checkin_income,
                coalesce(sum(free_checkin_income) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as free_checkin_income,
                coalesce(sum(greatest(credit_change - free_checkin_income, 0)) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as identity_checkin_bonus_income,
                coalesce(sum(credit_change) filter (
                    where credit_change > 0
                      and (
                        operation_type in ('checkin', 'welcome_bonus', 'affiliate_credits_redeem')
                        or operation_type like 'referral_reward%'
                      )
                ), 0)::bigint as non_paid_grant_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'refund%'), 0)::bigint as refund_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = any($2::text[])), 0))::bigint as generation_expense,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'gallery_prompt_unlock_reward'), 0)::bigint as internal_transfer_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = 'gallery_prompt_unlock_purchase'), 0))::bigint as internal_transfer_expense
            from checkin_split
        ),
        balances as (
            select coalesce(sum(coalesce(credits, 0)), 0)::bigint as current_total_credits
            from users
        )
        select
            summary.gross_income,
            summary.gross_expense,
            summary.net_change,
            summary.paid_recharge_income,
            summary.checkin_income,
            summary.free_checkin_income,
            summary.identity_checkin_bonus_income,
            summary.non_paid_grant_income,
            summary.refund_income,
            summary.generation_expense,
            balances.current_total_credits,
            round(summary.gross_expense::numeric / greatest($1::numeric, 1), 2) as avg_daily_expense,
            case
                when summary.gross_expense <= 0 then 0
                else round(balances.current_total_credits::numeric / (summary.gross_expense::numeric / greatest($1::numeric, 1)), 2)
            end as balance_burn_days,
            summary.internal_transfer_income,
            summary.internal_transfer_expense
        from summary, balances
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    daily = await _fetch(
        f"""
        with days as (
            select generate_series(
                current_date - (($1::int - 1) * interval '1 day'),
                current_date,
                interval '1 day'
            )::date as day
        ),
        flows as (
            select
                created_at::date as day,
                user_id,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
        ),
        {CHECKIN_SPLIT_CTES},
        daily_logs as (
            select
                day,
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as expense,
                coalesce(sum(credit_change), 0)::bigint as net_change,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'recharge'), 0)::bigint as recharge_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as checkin_income,
                coalesce(sum(free_checkin_income) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as free_checkin_income,
                coalesce(sum(greatest(credit_change - free_checkin_income, 0)) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as identity_checkin_bonus_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = any($2::text[])), 0))::bigint as generation_expense,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'refund%'), 0)::bigint as refund_income
            from checkin_split
            group by 1
        )
        select
            'credit_flow_daily' as row_type,
            to_char(days.day, 'YYYY-MM-DD') as day,
            coalesce(daily_logs.income, 0)::bigint as income,
            coalesce(daily_logs.expense, 0)::bigint as expense,
            coalesce(daily_logs.net_change, 0)::bigint as net_change,
            coalesce(daily_logs.recharge_income, 0)::bigint as recharge_income,
            coalesce(daily_logs.checkin_income, 0)::bigint as checkin_income,
            coalesce(daily_logs.free_checkin_income, 0)::bigint as free_checkin_income,
            coalesce(daily_logs.identity_checkin_bonus_income, 0)::bigint as identity_checkin_bonus_income,
            coalesce(daily_logs.generation_expense, 0)::bigint as generation_expense,
            coalesce(daily_logs.refund_income, 0)::bigint as refund_income
        from days
        left join daily_logs using (day)
        order by days.day
        """,
        chart_days,
        GENERATION_OPERATION_TYPES,
    )
    daily_categories = await _fetch(
        f"""
        with days as (
            select generate_series(
                current_date - (($1::int - 1) * interval '1 day'),
                current_date,
                interval '1 day'
            )::date as day
        ),
        category_order(category, direction, sort_order) as (
            values
                ('充值/套餐发放', 'income', 1),
                ('免费签到', 'income', 2),
                ('身份加成签到', 'income', 3),
                ('注册欢迎', 'income', 4),
                ('邀请奖励', 'income', 5),
                ('返佣兑换', 'income', 6),
                ('退款/补偿', 'income', 7),
                ('Gallery 解锁收入', 'income', 8),
                ('后台调整', 'income', 9),
                ('其他收入', 'income', 10),
                ('生成/消费支出', 'expense', 20),
                ('Gallery 解锁支出', 'expense', 21),
                ('后台调整', 'expense', 22),
                ('其他支出', 'expense', 23)
        ),
        flows as (
            select
                created_at::date as day,
                user_id,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
              and credit_change <> 0
        ),
        {CHECKIN_SPLIT_CTES},
        classified as (
            select
                day,
                user_id,
                free_checkin_income as credit_change,
                'income' as direction,
                '免费签到' as category
            from checkin_split
            where credit_change > 0
              and operation_type = 'checkin'
              and free_checkin_income > 0

            union all

            select
                day,
                user_id,
                greatest(credit_change - free_checkin_income, 0) as credit_change,
                'income' as direction,
                '身份加成签到' as category
            from checkin_split
            where credit_change > 0
              and operation_type = 'checkin'
              and greatest(credit_change - free_checkin_income, 0) > 0

            union all

            select
                day,
                user_id,
                credit_change,
                case when credit_change > 0 then 'income' else 'expense' end as direction,
                case
                    when credit_change > 0 and operation_type = 'recharge' then '充值/套餐发放'
                    when credit_change > 0 and operation_type = 'welcome_bonus' then '注册欢迎'
                    when credit_change > 0 and operation_type like 'referral_reward%' then '邀请奖励'
                    when credit_change > 0 and operation_type = 'affiliate_credits_redeem' then '返佣兑换'
                    when credit_change > 0 and operation_type like 'refund%' then '退款/补偿'
                    when credit_change > 0 and operation_type = 'gallery_prompt_unlock_reward' then 'Gallery 解锁收入'
                    when credit_change > 0 and operation_type = 'admin_update' then '后台调整'
                    when credit_change > 0 then '其他收入'
                    when credit_change < 0 and operation_type = any($2::text[]) then '生成/消费支出'
                    when credit_change < 0 and operation_type = 'gallery_prompt_unlock_purchase' then 'Gallery 解锁支出'
                    when credit_change < 0 and operation_type = 'admin_update' then '后台调整'
                    else '其他支出'
                end as category
            from checkin_split
            where credit_change <> 0
              and not (credit_change > 0 and operation_type = 'checkin')
        ),
        grouped as (
            select
                day,
                category,
                direction,
                count(*)::bigint as events,
                count(distinct user_id)::bigint as users,
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as expense,
                coalesce(sum(credit_change), 0)::bigint as net_change
            from classified
            group by 1, 2, 3
        )
        select
            'credit_flow_daily_category' as row_type,
            to_char(days.day, 'YYYY-MM-DD') as day,
            category_order.category,
            category_order.direction,
            coalesce(grouped.events, 0)::bigint as events,
            coalesce(grouped.users, 0)::bigint as users,
            coalesce(grouped.income, 0)::bigint as income,
            coalesce(grouped.expense, 0)::bigint as expense,
            coalesce(grouped.net_change, 0)::bigint as net_change
        from days
        cross join category_order
        left join grouped
          on grouped.day = days.day
         and grouped.category = category_order.category
         and grouped.direction = category_order.direction
        where coalesce(grouped.events, 0) > 0
        order by days.day, category_order.sort_order
        """,
        chart_days,
        GENERATION_OPERATION_TYPES,
    )
    categories = await _fetch(
        f"""
        with category_order(category, direction, sort_order) as (
            values
                ('充值/套餐发放', 'income', 1),
                ('免费签到', 'income', 2),
                ('身份加成签到', 'income', 3),
                ('注册欢迎', 'income', 4),
                ('邀请奖励', 'income', 5),
                ('返佣兑换', 'income', 6),
                ('退款/补偿', 'income', 7),
                ('Gallery 解锁收入', 'income', 8),
                ('后台调整', 'income', 9),
                ('其他收入', 'income', 10),
                ('生成/消费支出', 'expense', 20),
                ('Gallery 解锁支出', 'expense', 21),
                ('后台调整', 'expense', 22),
                ('其他支出', 'expense', 23)
        ),
        bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        flows as (
            select
                user_id,
                created_at,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change <> 0
        ),
        {CHECKIN_SPLIT_CTES},
        classified as (
            select
                user_id,
                free_checkin_income as credit_change,
                'income' as direction,
                '免费签到' as category
            from checkin_split
            where credit_change > 0
              and operation_type = 'checkin'
              and free_checkin_income > 0

            union all

            select
                user_id,
                greatest(credit_change - free_checkin_income, 0) as credit_change,
                'income' as direction,
                '身份加成签到' as category
            from checkin_split
            where credit_change > 0
              and operation_type = 'checkin'
              and greatest(credit_change - free_checkin_income, 0) > 0

            union all

            select
                user_id,
                credit_change,
                case when credit_change > 0 then 'income' else 'expense' end as direction,
                case
                    when credit_change > 0 and operation_type = 'recharge' then '充值/套餐发放'
                    when credit_change > 0 and operation_type = 'welcome_bonus' then '注册欢迎'
                    when credit_change > 0 and operation_type like 'referral_reward%' then '邀请奖励'
                    when credit_change > 0 and operation_type = 'affiliate_credits_redeem' then '返佣兑换'
                    when credit_change > 0 and operation_type like 'refund%' then '退款/补偿'
                    when credit_change > 0 and operation_type = 'gallery_prompt_unlock_reward' then 'Gallery 解锁收入'
                    when credit_change > 0 and operation_type = 'admin_update' then '后台调整'
                    when credit_change > 0 then '其他收入'
                    when credit_change < 0 and operation_type = any($2::text[]) then '生成/消费支出'
                    when credit_change < 0 and operation_type = 'gallery_prompt_unlock_purchase' then 'Gallery 解锁支出'
                    when credit_change < 0 and operation_type = 'admin_update' then '后台调整'
                    else '其他支出'
                end as category
            from checkin_split
            where credit_change <> 0
              and not (credit_change > 0 and operation_type = 'checkin')
        ),
        grouped as (
            select
                category,
                direction,
                count(*)::bigint as events,
                count(distinct user_id)::bigint as users,
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as expense,
                coalesce(sum(credit_change), 0)::bigint as net_change
            from classified
            group by 1, 2
        )
        select
            'credit_flow_category' as row_type,
            category_order.category,
            category_order.direction,
            coalesce(grouped.events, 0)::bigint as events,
            coalesce(grouped.users, 0)::bigint as users,
            coalesce(grouped.income, 0)::bigint as income,
            coalesce(grouped.expense, 0)::bigint as expense,
            coalesce(grouped.net_change, 0)::bigint as net_change
        from category_order
        left join grouped
          on grouped.category = category_order.category
         and grouped.direction = category_order.direction
        order by category_order.sort_order
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    composition_identity = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        income_logs as (
            select user_id, credit_change
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change > 0
        )
        select
            'composition_identity' as row_type,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as label,
            count(distinct income_logs.user_id)::bigint as users,
            count(*)::bigint as events,
            coalesce(sum(income_logs.credit_change), 0)::bigint as income
        from income_logs
        left join users u on u.id = income_logs.user_id
        group by 2
        order by income desc, users desc, label
        limit 20
        """,
        query_days,
    )
    composition_group = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        income_logs as (
            select user_id, credit_change
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change > 0
        )
        select
            'composition_user_group' as row_type,
            coalesce(nullif(u.user_group, ''), '凡人') as label,
            count(distinct income_logs.user_id)::bigint as users,
            count(*)::bigint as events,
            coalesce(sum(income_logs.credit_change), 0)::bigint as income
        from income_logs
        left join users u on u.id = income_logs.user_id
        group by 2
        order by income desc, users desc, label
        limit 20
        """,
        query_days,
    )
    composition_channel = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        income_logs as (
            select user_id, credit_change
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change > 0
        )
        select
            'composition_channel_member' as row_type,
            case when u.is_channel_member is true then '入宗门' else '未入宗门' end as label,
            count(distinct income_logs.user_id)::bigint as users,
            count(*)::bigint as events,
            coalesce(sum(income_logs.credit_change), 0)::bigint as income
        from income_logs
        left join users u on u.id = income_logs.user_id
        group by 2
        order by income desc, users desc, label
        """,
        query_days,
    )
    composition_payer = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        paid_users as (
            select distinct internal_user_id
            from orders
            where lower(status) = 'success'
              and payment_channel in ('RMB', 'TON', 'XTR')
              and internal_user_id is not null
        ),
        income_logs as (
            select user_id, credit_change
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change > 0
        )
        select
            'composition_payer' as row_type,
            case when paid_users.internal_user_id is null then '未付费用户' else '付费用户' end as label,
            count(distinct income_logs.user_id)::bigint as users,
            count(*)::bigint as events,
            coalesce(sum(income_logs.credit_change), 0)::bigint as income
        from income_logs
        left join paid_users on paid_users.internal_user_id = income_logs.user_id
        group by 2
        order by income desc, users desc, label
        """,
        query_days,
    )
    health_row = await _fetchrow(
        f"""
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        flows as (
            select
                user_id,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs, bounds
            where created_at >= bounds.since
        ),
        {CHECKIN_SPLIT_CTES},
        summary as (
            select
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::numeric as gross_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::numeric as gross_expense,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'recharge'), 0)::numeric as paid_recharge_income,
                coalesce(sum(credit_change) filter (
                    where credit_change > 0
                      and (
                        operation_type in ('checkin', 'welcome_bonus', 'affiliate_credits_redeem')
                        or operation_type like 'referral_reward%'
                      )
                ), 0)::numeric as non_paid_grant_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'refund%'), 0)::numeric as refund_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = any($2::text[])), 0))::numeric as generation_expense,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::numeric as checkin_income
            from checkin_split
        ),
        top_income as (
            select coalesce(max(user_income), 0)::numeric as top_user_income
            from (
                select user_id, sum(credit_change) as user_income
                from checkin_split
                where credit_change > 0
                group by user_id
            ) ranked
        )
        select
            'credit_flow_health' as row_type,
            round(case when gross_income > 0 then paid_recharge_income / gross_income * 100 else 0 end, 2) as paid_recharge_ratio,
            round(case when gross_income > 0 then non_paid_grant_income / gross_income * 100 else 0 end, 2) as non_paid_grant_ratio,
            round(case when generation_expense > 0 then refund_income / generation_expense * 100 else 0 end, 2) as refund_to_generation_ratio,
            round(case when gross_income > 0 then gross_expense / gross_income * 100 else 0 end, 2) as expense_coverage_ratio,
            round(case when gross_income > 0 then top_user_income / gross_income * 100 else 0 end, 2) as top_income_user_share,
            round(case when gross_income > 0 then checkin_income / gross_income * 100 else 0 end, 2) as checkin_pressure_ratio
        from summary, top_income
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    risk_users = await _fetch(
        f"""
        with bounds as (
            select now() - ($1::int * interval '1 day') as since
        ),
        flows as (
            select
                user_id,
                created_at,
                current_balance,
                coalesce(operation_type, '') as operation_type,
                coalesce(credit_change, 0)::numeric as credit_change,
                extra_info
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change <> 0
        ),
        {CHECKIN_SPLIT_CTES},
        user_flow as (
            select
                user_id,
                count(*)::bigint as events,
                coalesce(sum(credit_change) filter (where credit_change > 0), 0)::bigint as income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0), 0))::bigint as expense,
                coalesce(sum(credit_change), 0)::bigint as net_change,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as checkin_income,
                coalesce(sum(free_checkin_income) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as free_checkin_income,
                coalesce(sum(greatest(credit_change - free_checkin_income, 0)) filter (where credit_change > 0 and operation_type = 'checkin'), 0)::bigint as identity_checkin_bonus_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'referral_reward%'), 0)::bigint as referral_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type like 'refund%'), 0)::bigint as refund_income,
                coalesce(sum(credit_change) filter (where credit_change > 0 and operation_type = 'recharge'), 0)::bigint as recharge_income,
                abs(coalesce(sum(credit_change) filter (where credit_change < 0 and operation_type = any($2::text[])), 0))::bigint as generation_expense,
                (array_agg(current_balance order by created_at desc))[1] as latest_balance
            from checkin_split
            group by user_id
        ),
        scored as (
            select
                coalesce(u.id, user_flow.user_id) as id,
                u.username,
                u.full_name,
                coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
                coalesce(nullif(u.user_group, ''), '凡人') as user_group,
                u.is_channel_member,
                coalesce(u.credits, user_flow.latest_balance, 0)::bigint as current_balance,
                user_flow.events,
                user_flow.income,
                user_flow.expense,
                user_flow.net_change,
                user_flow.checkin_income,
                user_flow.free_checkin_income,
                user_flow.identity_checkin_bonus_income,
                user_flow.referral_income,
                user_flow.refund_income,
                user_flow.recharge_income,
                user_flow.generation_expense,
                (
                    case when user_flow.checkin_income >= 300 and user_flow.generation_expense <= 30 then 40 else 0 end
                    + case when user_flow.referral_income >= 100 then 30 else 0 end
                    + case when user_flow.refund_income >= 50 and user_flow.refund_income >= greatest(user_flow.generation_expense * 0.2, 1) then 30 else 0 end
                    + case when user_flow.income >= 500 and user_flow.recharge_income = 0 and user_flow.generation_expense < user_flow.income * 0.25 then 25 else 0 end
                    + case when coalesce(u.credits, user_flow.latest_balance, 0) >= 500 and user_flow.generation_expense <= 50 then 20 else 0 end
                    + case when user_flow.net_change >= 300 then 15 else 0 end
                )::bigint as risk_score,
                array_remove(array[
                    case when user_flow.checkin_income >= 300 and user_flow.generation_expense <= 30 then '签到高且低消耗' end,
                    case when user_flow.referral_income >= 100 then '邀请奖励集中' end,
                    case when user_flow.refund_income >= 50 and user_flow.refund_income >= greatest(user_flow.generation_expense * 0.2, 1) then '退款补偿偏高' end,
                    case when user_flow.income >= 500 and user_flow.recharge_income = 0 and user_flow.generation_expense < user_flow.income * 0.25 then '非付费净增高' end,
                    case when coalesce(u.credits, user_flow.latest_balance, 0) >= 500 and user_flow.generation_expense <= 50 then '高余额低消耗' end,
                    case when user_flow.net_change >= 300 then '周期净增较高' end
                ], null::text) as risk_reasons
            from user_flow
            left join users u on u.id = user_flow.user_id
        )
        select
            'risk_user_rank' as row_type,
            id,
            username,
            full_name,
            current_identity,
            user_group,
            is_channel_member,
            current_balance,
            events,
            income,
            expense,
            net_change,
            checkin_income,
            free_checkin_income,
            identity_checkin_bonus_income,
            referral_income,
            refund_income,
            recharge_income,
            generation_expense,
            risk_score,
            risk_reasons
        from scored
        where risk_score > 0
        order by risk_score desc, net_change desc, income desc, id desc
        limit $3::int
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
        limit,
    )
    summary = _row(summary_row)
    health = _row(health_row)
    health["flags"] = _credit_health_flags(summary, health)
    return {
        "days": days,
        "limit": limit,
        "summary": summary,
        "daily": _rows(daily),
        "daily_categories": _rows(daily_categories),
        "categories": _rows(categories),
        "composition": {
            "identity": _rows(composition_identity),
            "user_group": _rows(composition_group),
            "channel_member": _rows(composition_channel),
            "payer": _rows(composition_payer),
        },
        "health": health,
        "risk_users": _rows(risk_users),
    }


@app.get("/api/overview")
async def overview(days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS)) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    chart_days = _chart_days(days)
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
        query_days,
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
        chart_days,
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
async def finance(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(12, ge=1, le=50),
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    chart_days = _chart_days(days)
    limit = _clamp(limit, 1, 50)
    summary = await _fetchrow(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                o.*,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                lower(coalesce(o.status, '')) as status_lower,
                coalesce(mp.reward_credits, 0) as reward_credits,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        ),
        first_real_success as (
            select
                internal_user_id,
                min(coalesce(paid_at, updated_at, created_at)) as first_paid_at
            from orders
            where lower(coalesce(status, '')) = 'success'
              and payment_channel in ('RMB', 'TON', 'XTR')
              and coalesce(tx_hash, '') not like 'manual_%'
              and coalesce(order_id, '') not like 'GIFT:%'
              and internal_user_id is not null
            group by internal_user_id
        )
        select
            'finance_summary' as row_type,
            count(*) filter (where status_lower = 'success')::bigint as success_orders,
            count(*) filter (where status_lower = 'pending')::bigint as pending_orders,
            count(*) filter (where status_lower = 'failed')::bigint as failed_orders,
            count(*) filter (where status_lower != 'success')::bigint as non_success_orders,
            count(distinct bounded.internal_user_id) filter (where real_success)::bigint as real_payers,
            count(distinct bounded.internal_user_id) filter (where real_success and first_real_success.first_paid_at >= (select since from bounds))::bigint as new_payers,
            count(distinct bounded.internal_user_id) filter (where real_success and first_real_success.first_paid_at < (select since from bounds))::bigint as repeat_payers,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
            round(coalesce(
                sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0
            ) * {RMB_TO_USDT}
            + coalesce(
                sum(final_price) filter (where real_success and payment_channel = 'TON'), 0
            ) * {TON_TO_USDT}
            + coalesce(
                sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0
            ) * {STARS_TO_USDT}, 2) as usdt_amount,
            coalesce(avg(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_avg_order,
            coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
            count(*) filter (where status_lower = 'success' and not real_success)::bigint as internal_success_orders,
            case
                when count(distinct bounded.internal_user_id) filter (where real_success) = 0 then 0
                else round((
                    coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}
                ) / count(distinct bounded.internal_user_id) filter (where real_success), 2)
            end as arppu_usdt,
            case
                when count(*) = 0 then 0
                else round((count(*) filter (where status_lower = 'success'))::numeric / count(*)::numeric * 100, 2)
            end as success_rate,
            max(order_time) filter (where status_lower = 'success') as latest_success_at
        from bounded
        left join first_real_success on first_real_success.internal_user_id = bounded.internal_user_id
        """,
        query_days,
    )
    daily = await _fetch(
        f"""
        with days as (
            select generate_series(
                current_date - (($1::int - 1) * interval '1 day'),
                current_date,
                interval '1 day'
            )::date as day
        ),
        bounded as (
            select
                coalesce(o.paid_at, o.updated_at, o.created_at)::date as day,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(mp.identity_name, '') as identity_name,
                coalesce(mp.duration_days, 0) as duration_days,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= current_date - (($1::int - 1) * interval '1 day')
        ),
        daily_orders as (
            select
                day,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}, 2) as rmb_usdt_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}, 2) as ton_usdt_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as stars_usdt_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
                count(*) filter (where status_lower = 'success')::bigint as success_orders,
                count(distinct internal_user_id) filter (where real_success)::bigint as payers,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
                count(*) filter (where status_lower = 'success' and identity_name like '%内门%')::bigint as inner_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%核心%')::bigint as core_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%真传%')::bigint as true_disciples,
                count(*) filter (where status_lower = 'success' and duration_days = 0)::bigint as pure_credit_orders
            from bounded
            group by 1
        )
        select
            'finance_daily' as row_type,
            to_char(days.day, 'YYYY-MM-DD') as day,
            coalesce(daily_orders.rmb_amount, 0) as rmb_amount,
            coalesce(daily_orders.ton_amount, 0) as ton_amount,
            coalesce(daily_orders.stars_amount, 0) as stars_amount,
            coalesce(daily_orders.rmb_usdt_amount, 0) as rmb_usdt_amount,
            coalesce(daily_orders.ton_usdt_amount, 0) as ton_usdt_amount,
            coalesce(daily_orders.stars_usdt_amount, 0) as stars_usdt_amount,
            coalesce(daily_orders.usdt_amount, 0) as usdt_amount,
            coalesce(daily_orders.success_orders, 0)::bigint as success_orders,
            coalesce(daily_orders.payers, 0)::bigint as payers,
            coalesce(daily_orders.plan_reward_credits, 0)::bigint as plan_reward_credits,
            coalesce(daily_orders.inner_disciples, 0)::bigint as inner_disciples,
            coalesce(daily_orders.core_disciples, 0)::bigint as core_disciples,
            coalesce(daily_orders.true_disciples, 0)::bigint as true_disciples,
            coalesce(daily_orders.pure_credit_orders, 0)::bigint as pure_credit_orders
        from days
        left join daily_orders using (day)
        order by days.day
        """,
        chart_days,
    )
    hourly = await _fetch(
        """
        with hours as (
            select generate_series(0, 23)::int as hour
        ),
        bounded as (
            select
                extract(hour from coalesce(o.paid_at, o.updated_at, o.created_at))::int as hour,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(mp.identity_name, '') as identity_name,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= now() - ($1::int * interval '1 day')
        ),
        hourly_orders as (
            select
                hour,
                count(*) filter (where status_lower = 'success')::bigint as success_orders,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
                count(*) filter (where status_lower = 'success' and identity_name like '%内门%')::bigint as inner_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%核心%')::bigint as core_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%真传%')::bigint as true_disciples
            from bounded
            group by 1
        )
        select
            'finance_hourly' as row_type,
            hours.hour,
            coalesce(hourly_orders.success_orders, 0)::bigint as success_orders,
            coalesce(hourly_orders.plan_reward_credits, 0)::bigint as plan_reward_credits,
            coalesce(hourly_orders.rmb_amount, 0) as rmb_amount,
            coalesce(hourly_orders.ton_amount, 0) as ton_amount,
            coalesce(hourly_orders.stars_amount, 0) as stars_amount,
            coalesce(hourly_orders.inner_disciples, 0)::bigint as inner_disciples,
            coalesce(hourly_orders.core_disciples, 0)::bigint as core_disciples,
            coalesce(hourly_orders.true_disciples, 0)::bigint as true_disciples
        from hours
        left join hourly_orders using (hour)
        order by hours.hour
        """,
        query_days,
    )
    channels = await _fetch(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                case
                    when o.payment_channel in ('RMB', 'TON', 'XTR')
                     and coalesce(o.tx_hash, '') not like 'manual_%'
                     and coalesce(o.order_id, '') not like 'GIFT:%'
                    then o.payment_channel
                    else 'INTERNAL'
                end as channel,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        )
        select
            'finance_channels' as row_type,
            channel,
            count(*) filter (where status_lower = 'success')::bigint as success_orders,
            count(*) filter (where status_lower = 'pending')::bigint as pending_orders,
            count(*) filter (where status_lower = 'failed')::bigint as failed_orders,
            count(*) filter (where status_lower != 'success')::bigint as non_success_orders,
            count(distinct internal_user_id) filter (where real_success)::bigint as payers,
            coalesce(sum(final_price) filter (where real_success), 0) as amount,
            round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
            coalesce(avg(final_price) filter (where real_success), 0) as avg_order_amount,
            coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
            min(order_time) filter (where status_lower = 'success') as first_paid_at,
            max(order_time) filter (where status_lower = 'success') as last_paid_at
        from bounded
        group by 1, 2
        order by usdt_amount desc, success_orders desc, channel
        """,
        query_days,
    )
    plans = await _fetch(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                o.*,
                lower(coalesce(o.status, '')) as status_lower,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                coalesce(mp.name, '未知套餐') as plan_name,
                coalesce(mp.identity_name, '未知身份') as identity_name,
                coalesce(mp.duration_days, 0) as duration_days,
                coalesce(mp.reward_credits, 0) as reward_credits,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        )
        select
            'finance_plans' as row_type,
            plan_id,
            plan_name,
            identity_name,
            duration_days,
            max(reward_credits)::bigint as configured_reward_credits,
            count(*)::bigint as all_orders,
            count(*) filter (where status_lower = 'success')::bigint as success_orders,
            count(distinct internal_user_id) filter (where real_success)::bigint as payers,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
            coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
            round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
            coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
            case
                when count(*) = 0 then 0
                else round((count(*) filter (where status_lower = 'success'))::numeric / count(*)::numeric * 100, 2)
            end as success_rate,
            min(order_time) filter (where status_lower = 'success') as first_paid_at,
            max(order_time) filter (where status_lower = 'success') as last_paid_at
        from bounded
        group by plan_id, plan_name, identity_name, duration_days
        order by usdt_amount desc, success_orders desc, plan_id desc
        """,
        query_days,
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
              and coalesce(tx_hash, '') not like 'manual_%'
              and coalesce(order_id, '') not like 'GIFT:%'
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
            'finance_first_purchase' as row_type,
            count(*)::bigint as first_purchase_users,
            coalesce(avg(extract(epoch from (first_paid_at - registered_at)) / 3600), 0) as avg_hours_to_first_purchase,
            coalesce(percentile_cont(0.5) within group (order by extract(epoch from (first_paid_at - registered_at)) / 3600), 0) as median_hours_to_first_purchase,
            count(*) filter (where first_paid_at - registered_at <= interval '24 hours')::bigint as first_day_payers
        from recent_first
        """,
        query_days,
    )
    segments = await _fetch(
        f"""
        with paid_users as (
            select
                internal_user_id,
                count(*)::bigint as orders,
                coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) as rmb_amount,
                round(coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
                max(coalesce(paid_at, updated_at, created_at)) as last_paid_at
            from orders
            where lower(status) = 'success'
              and payment_channel in ('RMB', 'TON', 'XTR')
              and coalesce(tx_hash, '') not like 'manual_%'
              and coalesce(order_id, '') not like 'GIFT:%'
              and internal_user_id is not null
            group by internal_user_id
        )
        select
            'finance_segments' as row_type,
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
            coalesce(sum(usdt_amount), 0) as usdt_amount,
            coalesce(avg(usdt_amount), 0) as avg_usdt_per_user,
            max(last_paid_at) as latest_paid_at
        from paid_users
        group by 1, 2
        order by min(orders)
        """
    )
    invitation = await _fetchrow(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        invited_success as (
            select o.*
            from orders o
            join referrals r on r.invitee_id = o.internal_user_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
              and lower(coalesce(o.status, '')) = 'success'
              and o.payment_channel in ('RMB', 'TON', 'XTR')
              and coalesce(o.tx_hash, '') not like 'manual_%'
              and coalesce(o.order_id, '') not like 'GIFT:%'
        )
        select
            'finance_invitation' as row_type,
            count(distinct internal_user_id)::bigint as invitee_payers,
            count(*)::bigint as orders,
            coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) as rmb_amount,
            coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) as ton_amount,
            coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) as stars_amount,
            round(coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount
        from invited_success
        """,
        query_days,
    )
    health_row = await _fetchrow(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                o.*,
                lower(coalesce(o.status, '')) as status_lower,
                coalesce(mp.reward_credits, 0) as reward_credits,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        ),
        payer_usdt as (
            select
                internal_user_id,
                coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) * {STARS_TO_USDT} as usdt_amount
            from bounded
            where real_success
            group by internal_user_id
        ),
        totals as (
            select
                count(*)::numeric as all_orders,
                count(*) filter (where status_lower = 'success')::numeric as success_orders,
                count(*) filter (where status_lower = 'pending')::numeric as pending_orders,
                count(*) filter (where status_lower = 'failed')::numeric as failed_orders,
                count(*) filter (where status_lower = 'success' and not real_success)::numeric as internal_success_orders,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::numeric as plan_reward_credits,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT} as usdt_amount
            from bounded
        )
        select
            'finance_health' as row_type,
            round(case when all_orders > 0 then success_orders / all_orders * 100 else 0 end, 2) as success_rate,
            pending_orders::bigint as pending_orders,
            round(case when all_orders > 0 then pending_orders / all_orders * 100 else 0 end, 2) as pending_ratio,
            round(case when all_orders > 0 then failed_orders / all_orders * 100 else 0 end, 2) as failure_rate,
            round(case when usdt_amount > 0 then coalesce((select max(usdt_amount) from payer_usdt), 0) / usdt_amount * 100 else 0 end, 2) as top_payer_share,
            round(case when success_orders > 0 then internal_success_orders / success_orders * 100 else 0 end, 2) as internal_success_ratio,
            round(case when usdt_amount > 0 then plan_reward_credits / usdt_amount else 0 end, 2) as credits_per_usdt
        from totals
        """,
        query_days,
    )
    top_payers = await _fetch(
        f"""
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        real_success as (
            select
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                coalesce(mp.reward_credits, 0) as reward_credits
            from orders o
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
              and lower(coalesce(o.status, '')) = 'success'
              and o.payment_channel in ('RMB', 'TON', 'XTR')
              and coalesce(o.tx_hash, '') not like 'manual_%'
              and coalesce(o.order_id, '') not like 'GIFT:%'
              and o.internal_user_id is not null
        )
        select
            'finance_top_payers' as row_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            count(*)::bigint as orders,
            coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) as rmb_amount,
            coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) as ton_amount,
            coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) as stars_amount,
            round(coalesce(sum(final_price) filter (where payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'TON'), 0) * {TON_TO_USDT}
                + coalesce(sum(final_price) filter (where payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
            coalesce(sum(reward_credits), 0)::bigint as plan_reward_credits,
            max(order_time) as latest_paid_at
        from real_success
        join users u on u.id = real_success.internal_user_id
        group by u.id, u.username, u.full_name, u.current_identity, u.user_group
        order by usdt_amount desc, orders desc, u.id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    recent_orders = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        bounded as (
            select
                o.id,
                o.order_id,
                o.business_order_id,
                o.internal_user_id,
                u.username,
                u.full_name,
                coalesce(mp.name, '未知套餐') as plan_name,
                coalesce(mp.identity_name, '未知身份') as identity_name,
                o.payment_channel,
                o.status,
                o.final_price,
                coalesce(mp.reward_credits, 0)::bigint as reward_credits,
                o.paid_at,
                o.created_at,
                coalesce(o.paid_at, o.updated_at, o.created_at) as order_time,
                (
                    coalesce(o.payment_channel, '') not in ('RMB', 'TON', 'XTR')
                    or coalesce(o.tx_hash, '') like 'manual_%'
                    or coalesce(o.order_id, '') like 'GIFT:%'
                ) as is_internal_order
            from orders o
            left join users u on u.id = o.internal_user_id
            left join membership_plans mp on mp.id = o.plan_id,
            bounds
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= bounds.since
        )
        select
            'finance_recent_orders' as row_type,
            id,
            order_id,
            business_order_id,
            internal_user_id,
            username,
            full_name,
            plan_name,
            identity_name,
            payment_channel,
            status,
            final_price,
            reward_credits,
            paid_at,
            created_at,
            order_time,
            is_internal_order
        from bounded
        order by order_time desc nulls last, id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    health = _row(health_row)
    health["flags"] = _finance_health_flags(health)
    return {
        "days": days,
        "limit": limit,
        "summary": _row(summary),
        "daily": _rows(daily),
        "hourly": _rows(hourly),
        "channels": _rows(channels),
        "plans": _rows(plans),
        "first_purchase": _row(first_purchase),
        "segments": _rows(segments),
        "invitation": _row(invitation),
        "health": health,
        "top_payers": _rows(top_payers),
        "recent_orders": _rows(recent_orders),
    }


@app.get("/api/finance/hourly-comparison")
async def finance_hourly_comparison(
    dates: str = Query(..., description="Comma-separated YYYY-MM-DD values, max 3"),
) -> dict[str, Any]:
    compare_dates = _parse_compare_dates(dates)
    hourly = await _fetch(
        f"""
        with selected_dates as (
            select unnest($1::text[]) as selected_date
        ),
        hours as (
            select generate_series(0, 23)::int as hour
        ),
        grid as (
            select selected_dates.selected_date, hours.hour
            from selected_dates
            cross join hours
        ),
        bounded as (
            select
                to_char(coalesce(o.paid_at, o.updated_at, o.created_at)::date, 'YYYY-MM-DD') as selected_date,
                extract(hour from coalesce(o.paid_at, o.updated_at, o.created_at))::int as hour,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(mp.identity_name, '') as identity_name,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id
            where to_char(coalesce(o.paid_at, o.updated_at, o.created_at)::date, 'YYYY-MM-DD') = any($1::text[])
        ),
        hourly_orders as (
            select
                selected_date,
                hour,
                count(*) filter (where status_lower = 'success')::bigint as success_orders,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
                count(*) filter (where status_lower = 'success' and identity_name like '%内门%')::bigint as inner_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%核心%')::bigint as core_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%真传%')::bigint as true_disciples
            from bounded
            group by 1, 2
        )
        select
            'finance_hourly_comparison' as row_type,
            grid.selected_date as date,
            grid.hour,
            coalesce(hourly_orders.success_orders, 0)::bigint as success_orders,
            coalesce(hourly_orders.plan_reward_credits, 0)::bigint as plan_reward_credits,
            coalesce(hourly_orders.rmb_amount, 0) as rmb_amount,
            coalesce(hourly_orders.ton_amount, 0) as ton_amount,
            coalesce(hourly_orders.stars_amount, 0) as stars_amount,
            coalesce(hourly_orders.usdt_amount, 0) as usdt_amount,
            coalesce(hourly_orders.inner_disciples, 0)::bigint as inner_disciples,
            coalesce(hourly_orders.core_disciples, 0)::bigint as core_disciples,
            coalesce(hourly_orders.true_disciples, 0)::bigint as true_disciples
        from grid
        left join hourly_orders
          on hourly_orders.selected_date = grid.selected_date
         and hourly_orders.hour = grid.hour
        order by array_position($1::text[], grid.selected_date), grid.hour
        """,
        compare_dates,
    )
    return {"dates": compare_dates, "hourly": _rows(hourly)}


@app.get("/api/finance/hourly-cumulative")
async def finance_hourly_cumulative(
    days: int = Query(30, ge=1, le=MAX_ANALYTICS_DAYS),
) -> dict[str, Any]:
    days = _clamp(days, 1, MAX_ANALYTICS_DAYS)
    hourly = await _fetch(
        f"""
        with hours as (
            select generate_series(0, 23)::int as hour
        ),
        bounded as (
            select
                extract(hour from coalesce(o.paid_at, o.updated_at, o.created_at))::int as hour,
                lower(coalesce(o.status, '')) as status_lower,
                o.internal_user_id,
                o.payment_channel,
                o.final_price,
                coalesce(mp.reward_credits, 0) as reward_credits,
                coalesce(mp.identity_name, '') as identity_name,
                (
                    lower(coalesce(o.status, '')) = 'success'
                    and o.payment_channel in ('RMB', 'TON', 'XTR')
                    and coalesce(o.tx_hash, '') not like 'manual_%'
                    and coalesce(o.order_id, '') not like 'GIFT:%'
                ) as real_success
            from orders o
            left join membership_plans mp on mp.id = o.plan_id
            where coalesce(o.paid_at, o.updated_at, o.created_at) >= now() - ($1::int * interval '1 day')
        ),
        hourly_orders as (
            select
                hour,
                count(*) filter (where status_lower = 'success')::bigint as success_orders,
                coalesce(sum(reward_credits) filter (where status_lower = 'success'), 0)::bigint as plan_reward_credits,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) as rmb_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) as ton_amount,
                coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) as stars_amount,
                round(coalesce(sum(final_price) filter (where real_success and payment_channel = 'RMB'), 0) * {RMB_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'TON'), 0) * {TON_TO_USDT}
                    + coalesce(sum(final_price) filter (where real_success and payment_channel = 'XTR'), 0) * {STARS_TO_USDT}, 2) as usdt_amount,
                count(*) filter (where status_lower = 'success' and identity_name like '%内门%')::bigint as inner_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%核心%')::bigint as core_disciples,
                count(*) filter (where status_lower = 'success' and identity_name like '%真传%')::bigint as true_disciples
            from bounded
            group by 1
        )
        select
            'finance_hourly_cumulative' as row_type,
            hours.hour,
            coalesce(hourly_orders.success_orders, 0)::bigint as success_orders,
            coalesce(hourly_orders.plan_reward_credits, 0)::bigint as plan_reward_credits,
            coalesce(hourly_orders.rmb_amount, 0) as rmb_amount,
            coalesce(hourly_orders.ton_amount, 0) as ton_amount,
            coalesce(hourly_orders.stars_amount, 0) as stars_amount,
            coalesce(hourly_orders.usdt_amount, 0) as usdt_amount,
            coalesce(hourly_orders.inner_disciples, 0)::bigint as inner_disciples,
            coalesce(hourly_orders.core_disciples, 0)::bigint as core_disciples,
            coalesce(hourly_orders.true_disciples, 0)::bigint as true_disciples
        from hours
        left join hourly_orders using (hour)
        order by hours.hour
        """,
        days,
    )
    return {"days": days, "hourly": _rows(hourly)}


@app.get("/api/generation")
async def generation(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(12, ge=1, le=50),
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    chart_days = _chart_days(days)
    limit = _clamp(limit, 1, 50)
    summary = await _fetchrow(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        recent_history as (
            select *
            from history, bounds
            where created_at >= bounds.since
        ),
        gallery_for_history as (
            select gp.*
            from gallery_posts gp
            where gp.is_active is true
              and exists (
                  select 1
                  from recent_history h
                  where h.task_id = gp.task_id
              )
        ),
        history_stats as (
            select
                count(*)::bigint as generations,
                count(distinct user_id)::bigint as creators,
                count(*) filter (where source = 'web')::bigint as web_generations,
                count(*) filter (where source = 'bot')::bigint as bot_generations,
                count(*) filter (where output_file is not null or extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
                count(*) filter (where input_file is not null and input_file <> '')::bigint as with_input_records,
                count(*) filter (where is_favorited is true)::bigint as favorited_records,
                count(*) filter (where is_public is true)::bigint as public_records,
                coalesce(avg(duration) filter (where duration is not null), 0) as avg_duration,
                coalesce(avg(width) filter (where width is not null), 0) as avg_width,
                coalesce(avg(height) filter (where height is not null), 0) as avg_height,
                max(created_at) as latest_generation_at
            from recent_history
        ),
        gallery_stats as (
            select
                count(*)::bigint as gallery_posts,
                coalesce(sum(likes_count), 0)::bigint as likes,
                coalesce(sum(dislikes_count), 0)::bigint as dislikes,
                coalesce(sum(comments_count), 0)::bigint as comments,
                coalesce(sum(applied_count), 0)::bigint as applies
            from gallery_for_history
        ),
        unlock_stats as (
            select count(*)::bigint as prompt_unlocks
            from gallery_prompt_unlocks, bounds
            where created_at >= bounds.since
        ),
        credit_stats as (
            select
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent,
                count(*)::bigint as debit_events
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change < 0
              and operation_type = any($2::text[])
        ),
        worker_stats as (
            select
                count(*) filter (where lower(status) = 'success')::bigint as worker_successes,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures,
                coalesce(avg(duration) filter (where lower(status) = 'success'), 0) as avg_worker_duration,
                coalesce(percentile_cont(0.95) within group (order by duration) filter (where lower(status) = 'success'), 0) as p95_worker_duration
            from worker_logs, bounds
            where start_time >= bounds.since
        )
        select
            'generation_summary' as row_type,
            (select count(*) from history)::bigint as total_generations,
            history_stats.generations,
            history_stats.creators,
            history_stats.web_generations,
            history_stats.bot_generations,
            history_stats.result_records,
            round(case when history_stats.generations > 0 then history_stats.result_records::numeric / history_stats.generations * 100 else 0 end, 2) as result_rate,
            history_stats.with_input_records,
            round(case when history_stats.generations > 0 then history_stats.with_input_records::numeric / history_stats.generations * 100 else 0 end, 2) as input_rate,
            history_stats.favorited_records,
            round(case when history_stats.generations > 0 then history_stats.favorited_records::numeric / history_stats.generations * 100 else 0 end, 2) as favorite_rate,
            history_stats.public_records,
            round(case when history_stats.generations > 0 then history_stats.public_records::numeric / history_stats.generations * 100 else 0 end, 2) as public_rate,
            gallery_stats.gallery_posts,
            round(case when history_stats.generations > 0 then gallery_stats.gallery_posts::numeric / history_stats.generations * 100 else 0 end, 2) as gallery_rate,
            gallery_stats.likes,
            gallery_stats.dislikes,
            gallery_stats.comments,
            gallery_stats.applies,
            unlock_stats.prompt_unlocks,
            credit_stats.credits_spent,
            round(case when history_stats.generations > 0 then credit_stats.credits_spent::numeric / history_stats.generations else 0 end, 2) as avg_credits_per_generation,
            worker_stats.worker_successes,
            worker_stats.worker_failures,
            round(case when worker_stats.worker_successes + worker_stats.worker_failures > 0 then worker_stats.worker_failures::numeric / (worker_stats.worker_successes + worker_stats.worker_failures) * 100 else 0 end, 2) as worker_failure_rate,
            worker_stats.avg_worker_duration,
            worker_stats.p95_worker_duration,
            history_stats.latest_generation_at,
            history_stats.avg_duration,
            history_stats.avg_width,
            history_stats.avg_height
        from history_stats, gallery_stats, unlock_stats, credit_stats, worker_stats
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
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
        history_daily as (
            select
                created_at::date as day,
                count(*)::bigint as generations,
                count(distinct user_id)::bigint as creators,
                count(*) filter (where source = 'web')::bigint as web_generations,
                count(*) filter (where source = 'bot')::bigint as bot_generations,
                count(*) filter (where output_file is not null or extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
                count(*) filter (where is_public is true)::bigint as public_records,
                count(*) filter (where is_favorited is true)::bigint as favorited_records
            from history
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        gallery_daily as (
            select
                h.created_at::date as day,
                count(distinct gp.id)::bigint as gallery_posts
            from history h
            join gallery_posts gp on gp.task_id = h.task_id and gp.is_active is true
            where h.created_at >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        ),
        credit_daily as (
            select
                created_at::date as day,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent
            from user_logs
            where created_at >= current_date - (($1::int - 1) * interval '1 day')
              and credit_change < 0
              and operation_type = any($2::text[])
            group by 1
        ),
        worker_daily as (
            select
                start_time::date as day,
                count(*) filter (where lower(status) = 'success')::bigint as worker_successes,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures
            from worker_logs
            where start_time >= current_date - (($1::int - 1) * interval '1 day')
            group by 1
        )
        select
            'generation_daily' as row_type,
            to_char(days.day, 'YYYY-MM-DD') as day,
            coalesce(history_daily.generations, 0)::bigint as generations,
            coalesce(history_daily.creators, 0)::bigint as creators,
            coalesce(history_daily.web_generations, 0)::bigint as web_generations,
            coalesce(history_daily.bot_generations, 0)::bigint as bot_generations,
            coalesce(history_daily.result_records, 0)::bigint as result_records,
            coalesce(history_daily.public_records, 0)::bigint as public_records,
            coalesce(history_daily.favorited_records, 0)::bigint as favorited_records,
            coalesce(gallery_daily.gallery_posts, 0)::bigint as gallery_posts,
            coalesce(credit_daily.credits_spent, 0)::bigint as credits_spent,
            coalesce(worker_daily.worker_successes, 0)::bigint as worker_successes,
            coalesce(worker_daily.worker_failures, 0)::bigint as worker_failures
        from days
        left join history_daily using (day)
        left join gallery_daily using (day)
        left join credit_daily using (day)
        left join worker_daily using (day)
        order by days.day
        """,
        chart_days,
        GENERATION_OPERATION_TYPES,
    )
    by_type = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        h_type as (
            select
                coalesce(h.type, 'unknown') as task_type,
                count(*)::bigint as generations,
                count(distinct h.user_id)::bigint as creators,
                count(*) filter (where h.output_file is not null or h.extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
                count(*) filter (where h.input_file is not null and h.input_file <> '')::bigint as with_input,
                count(*) filter (where h.is_favorited is true)::bigint as favorited_records,
                count(*) filter (where h.is_public is true)::bigint as public_records,
                coalesce(avg(h.duration) filter (where h.duration is not null), 0) as avg_duration
            from history h, bounds
            where h.created_at >= bounds.since
            group by 1
        ),
        gallery_type as (
            select
                coalesce(h.type, 'unknown') as task_type,
                count(distinct gp.id)::bigint as gallery_posts,
                coalesce(sum(gp.likes_count), 0)::bigint as likes,
                coalesce(sum(gp.dislikes_count), 0)::bigint as dislikes,
                coalesce(sum(gp.comments_count), 0)::bigint as comments,
                coalesce(sum(gp.applied_count), 0)::bigint as applies
            from history h
            join gallery_posts gp on gp.task_id = h.task_id and gp.is_active is true,
            bounds
            where h.created_at >= bounds.since
            group by 1
        ),
        credit_type as (
            select
                operation_type as task_type,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change < 0
              and operation_type = any($2::text[])
            group by 1
        ),
        worker_type as (
            select
                coalesce(task_type, 'unknown') as task_type,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures,
                count(*) filter (where lower(status) in ('success', 'failed'))::bigint as worker_events,
                coalesce(avg(duration) filter (where lower(status) = 'success'), 0) as avg_worker_duration
            from worker_logs, bounds
            where start_time >= bounds.since
            group by 1
        ),
        type_keys as (
            select task_type from h_type
            union
            select task_type from credit_type
            union
            select task_type from worker_type
        )
        select
            'generation_by_type' as row_type,
            type_keys.task_type,
            coalesce(h_type.generations, 0)::bigint as generations,
            coalesce(h_type.creators, 0)::bigint as creators,
            coalesce(h_type.result_records, 0)::bigint as result_records,
            round(case when coalesce(h_type.generations, 0) > 0 then h_type.result_records::numeric / h_type.generations * 100 else 0 end, 2) as result_rate,
            coalesce(h_type.with_input, 0)::bigint as with_input,
            round(case when coalesce(h_type.generations, 0) > 0 then h_type.with_input::numeric / h_type.generations * 100 else 0 end, 2) as input_rate,
            coalesce(h_type.favorited_records, 0)::bigint as favorited_records,
            round(case when coalesce(h_type.generations, 0) > 0 then h_type.favorited_records::numeric / h_type.generations * 100 else 0 end, 2) as favorite_rate,
            coalesce(h_type.public_records, 0)::bigint as public_records,
            round(case when coalesce(h_type.generations, 0) > 0 then h_type.public_records::numeric / h_type.generations * 100 else 0 end, 2) as public_rate,
            coalesce(gallery_type.gallery_posts, 0)::bigint as gallery_posts,
            round(case when coalesce(h_type.generations, 0) > 0 then coalesce(gallery_type.gallery_posts, 0)::numeric / h_type.generations * 100 else 0 end, 2) as gallery_rate,
            coalesce(gallery_type.likes, 0)::bigint as likes,
            coalesce(gallery_type.dislikes, 0)::bigint as dislikes,
            coalesce(gallery_type.comments, 0)::bigint as comments,
            coalesce(gallery_type.applies, 0)::bigint as applies,
            coalesce(credit_type.credits_spent, 0)::bigint as credits_spent,
            round(case when coalesce(h_type.generations, 0) > 0 then coalesce(credit_type.credits_spent, 0)::numeric / h_type.generations else 0 end, 2) as avg_credits_per_generation,
            coalesce(worker_type.worker_failures, 0)::bigint as worker_failures,
            round(case when coalesce(worker_type.worker_events, 0) > 0 then worker_type.worker_failures::numeric / worker_type.worker_events * 100 else 0 end, 2) as worker_failure_rate,
            coalesce(worker_type.avg_worker_duration, 0) as avg_worker_duration,
            coalesce(h_type.avg_duration, 0) as avg_duration
        from type_keys
        left join h_type using (task_type)
        left join gallery_type using (task_type)
        left join credit_type using (task_type)
        left join worker_type using (task_type)
        order by generations desc
        limit 50
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    credits = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            'generation_credits' as row_type,
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
        query_days,
        GENERATION_OPERATION_TYPES,
    )
    hourly = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            'generation_hourly' as row_type,
            extract(hour from created_at)::int as hour,
            count(*)::bigint as generations,
            count(distinct user_id)::bigint as creators
        from history, bounds
        where created_at >= bounds.since
        group by 2
        order by 2
        """,
        query_days,
    )
    source_mix = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since)
        select
            'generation_source_mix' as row_type,
            case
                when source = 'web' then 'Web'
                when source = 'bot' then 'Bot'
                else '未知来源'
            end as label,
            coalesce(source, 'unknown') as source,
            count(*)::bigint as count,
            count(distinct user_id)::bigint as creators
        from history, bounds
        where created_at >= bounds.since
        group by 2, 3
        order by count desc
        """,
        query_days,
    )
    quality_segments = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        recent_history as (
            select *
            from history, bounds
            where created_at >= bounds.since
        ),
        gallery_tasks as (
            select distinct task_id
            from gallery_posts
            where is_active is true
        )
        select 'generation_quality_segments' as row_type, '有输出' as label,
               count(*) filter (where output_file is not null or extra_outputs::text not in ('{}', 'null', ''))::bigint as count
        from recent_history
        union all
        select 'generation_quality_segments', '无输出',
               count(*) filter (where output_file is null and coalesce(extra_outputs::text, 'null') in ('{}', 'null', ''))::bigint
        from recent_history
        union all
        select 'generation_quality_segments', '有输入',
               count(*) filter (where input_file is not null and input_file <> '')::bigint
        from recent_history
        union all
        select 'generation_quality_segments', '公开',
               count(*) filter (where is_public is true)::bigint
        from recent_history
        union all
        select 'generation_quality_segments', '收藏',
               count(*) filter (where is_favorited is true)::bigint
        from recent_history
        union all
        select 'generation_quality_segments', 'Gallery 投稿',
               count(*) filter (where exists (select 1 from gallery_tasks where gallery_tasks.task_id = recent_history.task_id))::bigint
        from recent_history
        """,
        query_days,
    )
    generation_leaderboard = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        user_generation as (
            select
                h.user_id,
                count(distinct h.id)::bigint as generations,
                count(distinct h.id) filter (where h.output_file is not null or h.extra_outputs::text not in ('{}', 'null', ''))::bigint as result_records,
                count(distinct gp.id) filter (where gp.is_active is true)::bigint as gallery_posts,
                max(h.created_at) as last_generation_at
            from history h
            left join gallery_posts gp on gp.task_id = h.task_id,
            bounds
            where h.created_at >= bounds.since
              and h.user_id is not null
            group by h.user_id
        )
        select
            'generation_user_rank' as row_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            user_generation.generations,
            user_generation.result_records,
            user_generation.gallery_posts,
            user_generation.last_generation_at
        from user_generation
        join users u on u.id = user_generation.user_id
        order by user_generation.generations desc, u.id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    credit_leaderboard = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        user_credits as (
            select
                user_id,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent,
                count(*)::bigint as debit_events,
                coalesce(avg(abs(credit_change)), 0) as avg_credits_per_event
            from user_logs, bounds
            where created_at >= bounds.since
              and credit_change < 0
              and operation_type = any($2::text[])
              and user_id is not null
            group by user_id
        )
        select
            'generation_credit_user_rank' as row_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            user_credits.credits_spent,
            user_credits.debit_events,
            user_credits.avg_credits_per_event,
            u.credits as current_balance
        from user_credits
        join users u on u.id = user_credits.user_id
        order by user_credits.credits_spent desc, u.id desc
        limit $3::int
        """,
        query_days,
        GENERATION_OPERATION_TYPES,
        limit,
    )
    gallery_leaderboard = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        user_gallery as (
            select
                gp.user_id,
                count(*)::bigint as gallery_posts,
                coalesce(sum(gp.likes_count), 0)::bigint as likes,
                coalesce(sum(gp.dislikes_count), 0)::bigint as dislikes,
                coalesce(sum(gp.comments_count), 0)::bigint as comments,
                coalesce(sum(gp.applied_count), 0)::bigint as applies,
                max(gp.created_at) as latest_post_at
            from gallery_posts gp, bounds
            where gp.created_at >= bounds.since
              and gp.is_active is true
              and gp.user_id is not null
            group by gp.user_id
        )
        select
            'generation_gallery_user_rank' as row_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            user_gallery.gallery_posts,
            user_gallery.likes,
            user_gallery.dislikes,
            user_gallery.comments,
            user_gallery.applies,
            (user_gallery.gallery_posts * 8 + user_gallery.likes * 2 - user_gallery.dislikes + user_gallery.comments * 2 + user_gallery.applies * 5)::bigint as signal_score,
            user_gallery.latest_post_at
        from user_gallery
        join users u on u.id = user_gallery.user_id
        order by signal_score desc, u.id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    recent_high_signal = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        recent as (
            select
                h.id as history_id,
                h.task_id,
                coalesce(h.type, 'unknown') as task_type,
                h.user_id,
                h.is_favorited,
                h.is_public,
                h.created_at,
                gp.media_type,
                coalesce(gp.likes_count, 0)::bigint as likes,
                coalesce(gp.dislikes_count, 0)::bigint as dislikes,
                coalesce(gp.comments_count, 0)::bigint as comments,
                coalesce(gp.applied_count, 0)::bigint as applies,
                (
                    case when h.is_favorited is true then 10 else 0 end
                    + case when h.is_public is true then 6 else 0 end
                    + case when gp.id is not null then 12 else 0 end
                    + coalesce(gp.likes_count, 0) * 2
                    - coalesce(gp.dislikes_count, 0)
                    + coalesce(gp.comments_count, 0) * 2
                    + coalesce(gp.applied_count, 0) * 5
                )::bigint as signal_score
            from history h
            left join gallery_posts gp on gp.task_id = h.task_id and gp.is_active is true,
            bounds
            where h.created_at >= bounds.since
        )
        select
            'generation_recent_high_signal' as row_type,
            recent.history_id,
            recent.task_id,
            recent.task_type,
            u.id,
            u.username,
            u.full_name,
            coalesce(nullif(u.current_identity, ''), '外门弟子') as current_identity,
            coalesce(nullif(u.user_group, ''), '凡人') as user_group,
            recent.media_type,
            recent.likes,
            recent.dislikes,
            recent.comments,
            recent.applies,
            recent.is_favorited,
            recent.is_public,
            recent.created_at,
            recent.signal_score
        from recent
        left join users u on u.id = recent.user_id
        where recent.signal_score > 0
        order by recent.signal_score desc, recent.created_at desc, recent.history_id desc
        limit $2::int
        """,
        query_days,
        limit,
    )
    return {
        "days": days,
        "limit": limit,
        "summary": _row(summary),
        "daily": _rows(daily),
        "by_type": _rows(by_type),
        "credits": _rows(credits),
        "hourly": _rows(hourly),
        "source_mix": _rows(source_mix),
        "quality_segments": _rows(quality_segments),
        "leaderboards": {
            "generation": _rows(generation_leaderboard),
            "credits": _rows(credit_leaderboard),
            "gallery": _rows(gallery_leaderboard),
        },
        "recent_high_signal": _rows(recent_high_signal),
    }


@app.get("/api/generation/hourly-comparison")
async def generation_hourly_comparison(
    dates: str = Query(..., description="Comma-separated YYYY-MM-DD values, max 3"),
) -> dict[str, Any]:
    compare_dates = _parse_compare_dates(dates)
    hourly = await _fetch(
        """
        with selected_dates as (
            select unnest($1::text[]) as selected_date
        ),
        hours as (
            select generate_series(0, 23)::int as hour
        ),
        grid as (
            select selected_dates.selected_date, hours.hour
            from selected_dates
            cross join hours
        ),
        history_hourly as (
            select
                to_char(created_at::date, 'YYYY-MM-DD') as selected_date,
                extract(hour from created_at)::int as hour,
                count(*)::bigint as generations,
                count(distinct user_id)::bigint as creators,
                count(*) filter (where source = 'web')::bigint as web_generations,
                count(*) filter (where source = 'bot')::bigint as bot_generations
            from history
            where to_char(created_at::date, 'YYYY-MM-DD') = any($1::text[])
            group by 1, 2
        ),
        credit_hourly as (
            select
                to_char(created_at::date, 'YYYY-MM-DD') as selected_date,
                extract(hour from created_at)::int as hour,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent
            from user_logs
            where to_char(created_at::date, 'YYYY-MM-DD') = any($1::text[])
              and credit_change < 0
              and operation_type = any($2::text[])
            group by 1, 2
        ),
        worker_hourly as (
            select
                to_char(start_time::date, 'YYYY-MM-DD') as selected_date,
                extract(hour from start_time)::int as hour,
                count(*) filter (where lower(status) = 'success')::bigint as worker_successes,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures
            from worker_logs
            where to_char(start_time::date, 'YYYY-MM-DD') = any($1::text[])
            group by 1, 2
        )
        select
            'generation_hourly_comparison' as row_type,
            grid.selected_date as date,
            grid.hour,
            coalesce(history_hourly.generations, 0)::bigint as generations,
            coalesce(history_hourly.creators, 0)::bigint as creators,
            coalesce(history_hourly.web_generations, 0)::bigint as web_generations,
            coalesce(history_hourly.bot_generations, 0)::bigint as bot_generations,
            coalesce(credit_hourly.credits_spent, 0)::bigint as credits_spent,
            coalesce(worker_hourly.worker_successes, 0)::bigint as worker_successes,
            coalesce(worker_hourly.worker_failures, 0)::bigint as worker_failures
        from grid
        left join history_hourly
          on history_hourly.selected_date = grid.selected_date
         and history_hourly.hour = grid.hour
        left join credit_hourly
          on credit_hourly.selected_date = grid.selected_date
         and credit_hourly.hour = grid.hour
        left join worker_hourly
          on worker_hourly.selected_date = grid.selected_date
         and worker_hourly.hour = grid.hour
        order by array_position($1::text[], grid.selected_date), grid.hour
        """,
        compare_dates,
        GENERATION_OPERATION_TYPES,
    )
    return {"dates": compare_dates, "hourly": _rows(hourly)}


@app.get("/api/generation/hourly-cumulative")
async def generation_hourly_cumulative(
    days: int = Query(30, ge=1, le=MAX_ANALYTICS_DAYS),
) -> dict[str, Any]:
    days = _clamp(days, 1, MAX_ANALYTICS_DAYS)
    hourly = await _fetch(
        """
        with hours as (
            select generate_series(0, 23)::int as hour
        ),
        history_hourly as (
            select
                extract(hour from created_at)::int as hour,
                count(*)::bigint as generations,
                count(distinct user_id)::bigint as creators,
                count(*) filter (where source = 'web')::bigint as web_generations,
                count(*) filter (where source = 'bot')::bigint as bot_generations
            from history
            where created_at >= now() - ($1::int * interval '1 day')
            group by 1
        ),
        credit_hourly as (
            select
                extract(hour from created_at)::int as hour,
                abs(coalesce(sum(credit_change), 0))::bigint as credits_spent
            from user_logs
            where created_at >= now() - ($1::int * interval '1 day')
              and credit_change < 0
              and operation_type = any($2::text[])
            group by 1
        ),
        worker_hourly as (
            select
                extract(hour from start_time)::int as hour,
                count(*) filter (where lower(status) = 'success')::bigint as worker_successes,
                count(*) filter (where lower(status) = 'failed')::bigint as worker_failures
            from worker_logs
            where start_time >= now() - ($1::int * interval '1 day')
            group by 1
        )
        select
            'generation_hourly_cumulative' as row_type,
            hours.hour,
            coalesce(history_hourly.generations, 0)::bigint as generations,
            coalesce(history_hourly.creators, 0)::bigint as creators,
            coalesce(history_hourly.web_generations, 0)::bigint as web_generations,
            coalesce(history_hourly.bot_generations, 0)::bigint as bot_generations,
            coalesce(credit_hourly.credits_spent, 0)::bigint as credits_spent,
            coalesce(worker_hourly.worker_successes, 0)::bigint as worker_successes,
            coalesce(worker_hourly.worker_failures, 0)::bigint as worker_failures
        from hours
        left join history_hourly using (hour)
        left join credit_hourly using (hour)
        left join worker_hourly using (hour)
        order by hours.hour
        """,
        days,
        GENERATION_OPERATION_TYPES,
    )
    return {"days": days, "hourly": _rows(hourly)}


@app.get("/api/generation/type-comparison")
async def generation_type_comparison(
    dates: str = Query(..., description="Comma-separated YYYY-MM-DD values, max 3"),
) -> dict[str, Any]:
    compare_dates = _parse_compare_dates(dates)
    type_rows = await _fetch(
        """
        select
            'generation_type_comparison' as row_type,
            to_char(created_at::date, 'YYYY-MM-DD') as date,
            coalesce(type, 'unknown') as task_type,
            count(*)::bigint as generations,
            count(distinct user_id)::bigint as creators
        from history
        where to_char(created_at::date, 'YYYY-MM-DD') = any($1::text[])
        group by 2, 3
        order by array_position($1::text[], to_char(created_at::date, 'YYYY-MM-DD')), generations desc, task_type
        """,
        compare_dates,
    )
    return {"dates": compare_dates, "types": _rows(type_rows)}


@app.get("/api/prompts")
async def prompts(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(80, ge=1, le=100),
    page: int = Query(1, ge=1, le=10000),
    task_type: str | None = Query(None),
    template_scope: str = Query("natural"),
    q: str | None = Query(None),
    min_users: int = Query(1, ge=1, le=100000),
    min_uses: int = Query(1, ge=1, le=100000),
    sort: str = Query("value_score"),
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
    limit = _clamp(limit, 1, 100)
    page = _clamp(page, 1, 10000)
    min_users = _clamp(min_users, 1, 100000)
    min_uses = _clamp(min_uses, 1, 100000)
    template_scope = (template_scope or "natural").strip()
    if template_scope not in {"natural", "source_template", "builtin_template", "derived", "all"}:
        raise HTTPException(status_code=400, detail="invalid template_scope")
    sort = (sort or "value_score").strip()
    if sort not in {"value_score", "uses", "users", "last_seen", "likes", "applies", "prompt_unlocks", "char_count"}:
        raise HTTPException(status_code=400, detail="invalid prompt sort")
    mart_status = await _prompt_mart_status_or_error()
    search = (q or "").strip()
    normalized_search = _normalize_prompt_text(search)
    search_pattern = f"%{normalized_search}%" if normalized_search else None
    task_filter = (task_type or "").strip() or None
    offset = (page - 1) * limit
    use_alltime_stats = task_filter is None and days == 0
    use_rollup_stats = task_filter is None and days in PROMPT_ROLLUP_PERIODS
    groups_cte = (
        PROMPT_GROUPS_ALLTIME_CTE
        if use_alltime_stats
        else PROMPT_GROUPS_ROLLUP_CTE
        if use_rollup_stats
        else PROMPT_GROUPS_CTE
    )
    group_days = query_days if not (use_alltime_stats or use_rollup_stats) else days
    common_args = (
        group_days,
        task_filter,
        template_scope,
        search_pattern,
        min_users,
        min_uses,
    )
    summary = _row(
        await _fetchrow(
            f"""
            {groups_cte}
            select
                'prompt_summary' as row_type,
                coalesce(sum(uses), 0)::bigint as prompt_records,
                count(*)::bigint as distinct_prompts,
                count(*) filter (where uses > 1)::bigint as repeated_prompts,
                count(*) filter (where users > 1)::bigint as multi_user_prompts,
                round(coalesce(avg(char_count), 0)::numeric, 2) as avg_chars,
                coalesce(percentile_cont(0.5) within group (order by char_count), 0)::numeric as median_chars,
                (select derived_records_excluded from excluded_counts) as derived_records_excluded,
                (select builtin_template_records_excluded from excluded_counts) as builtin_template_records_excluded,
                count(*) filter (where value_score >= 80 and users > 1)::bigint as high_value_prompts
            from prompt_groups
            """,
            *common_args,
        )
    )
    group_records = await _fetch(
        f"""
        {groups_cte}
        select
            'prompt_groups_page' as row_type,
            prompt_hash,
            prompt,
            char_count,
            uses,
            users,
            variant_count,
            task_types,
            first_seen,
            last_seen,
            favorite_records,
            public_records,
            gallery_posts,
            likes,
            dislikes,
            comments,
            applies,
            prompt_unlocks,
            derived_uses,
            builtin_template_uses,
            builtin_template_keys,
            source_template_posts,
            value_score
        from prompt_groups
        order by
            case when $7::text = 'value_score' then value_score end desc,
            case when $7::text = 'uses' then uses end desc,
            case when $7::text = 'users' then users end desc,
            case when $7::text = 'last_seen' then last_seen end desc,
            case when $7::text = 'likes' then likes end desc,
            case when $7::text = 'applies' then applies end desc,
            case when $7::text = 'prompt_unlocks' then prompt_unlocks end desc,
            case when $7::text = 'char_count' then char_count end desc,
            value_score desc,
            last_seen desc,
            prompt_hash desc
        limit $8::int
        offset $9::int
        """,
        *common_args,
        sort,
        limit,
        offset,
    )
    length_distribution = await _fetch(
        f"""
        {groups_cte}
        select
            'prompt_length_distribution' as row_type,
            bucket.label,
            count(*)::bigint as count
        from prompt_groups
        cross join lateral (
            select
                case
                    when char_count <= 40 then '1-40 字'
                    when char_count <= 80 then '41-80 字'
                    when char_count <= 160 then '81-160 字'
                    when char_count <= 320 then '161-320 字'
                    else '320+ 字'
                end as label,
                case
                    when char_count <= 40 then 1
                    when char_count <= 80 then 2
                    when char_count <= 160 then 3
                    when char_count <= 320 then 4
                    else 5
                end as sort_order
        ) bucket
        group by bucket.label, bucket.sort_order
        order by bucket.sort_order
        """,
        *common_args,
    )
    task_type_distribution = await _fetch(
        f"""
        {groups_cte}
        select
            'prompt_task_type_distribution' as row_type,
            coalesce(task_type, 'unknown') as label,
            count(*)::bigint as count
        from prompt_groups, unnest(task_types) as task_type
        group by task_type
        order by count desc, label
        limit 20
        """,
        *common_args,
    )
    reuse_distribution = await _fetch(
        f"""
        {groups_cte}
        select
            'prompt_reuse_distribution' as row_type,
            segment.label,
            count(*)::bigint as count
        from prompt_groups
        cross join lateral (
            select
                case
                    when users > 1 and uses > 1 then '多人复用'
                    when uses > 1 then '单人重复'
                    else '一次性'
                end as label,
                case
                    when users > 1 and uses > 1 then 1
                    when uses > 1 then 2
                    else 3
                end as sort_order
        ) segment
        group by segment.label, segment.sort_order
        order by segment.sort_order
        """,
        *common_args,
    )
    template_scope_distribution = await _fetch(
        f"""
        {groups_cte}
        select
            'prompt_template_scope_distribution' as row_type,
            segment.label,
            count(*)::bigint as count
        from prompt_groups
        cross join lateral (
            select
                case
                    when derived_uses >= uses and uses > 0 then '一键应用衍生'
                    when builtin_template_uses > 0 then '内置模板'
                    when source_template_posts > 0 then '源模板'
                    else '自然输入'
                end as label,
                case
                    when derived_uses >= uses and uses > 0 then 4
                    when source_template_posts > 0 then 3
                    when builtin_template_uses > 0 then 2
                    else 1
                end as sort_order
        ) segment
        group by segment.label, segment.sort_order
        order by segment.sort_order
        """,
        *common_args,
    )
    sample_limit = max(limit * 100, 20000)
    rows = await _fetch(
        """
        with bounds as (select now() - ($1::int * interval '1 day') as since),
        recent_history as (
            select o.history_id as id, o.task_id, o.user_id, o.task_type as type, o.prompt,
                   coalesce(nullif(o.raw_prompt, ''), o.prompt) as raw_prompt,
                   o.input_file, o.output_file, o.extra_outputs, o.created_at, o.source,
                   o.is_favorited, o.width, o.height, o.duration, o.allow_contribute,
                   o.builtin_template_key
            from analytics_prompt_occurrence o
            cross join bounds
            where o.created_at >= bounds.since
              and ($4::text is null or o.task_type = $4::text)
              and (
                  $5::text = 'all'
                  or ($5::text = 'natural' and o.allow_contribute is distinct from false and o.builtin_template_key is null)
                  or ($5::text = 'derived' and o.allow_contribute is false)
                  or ($5::text = 'builtin_template' and o.allow_contribute is distinct from false and o.builtin_template_key is not null)
                  or (
                      $5::text = 'source_template'
                      and o.allow_contribute is distinct from false
                      and o.builtin_template_key is null
                      and exists (
                          select 1
                          from gallery_posts source_gp
                          where source_gp.task_id = o.task_id
                            and source_gp.is_active is true
                      )
                  )
              )
            order by o.created_at desc
            limit $3::int
        ),
        unlock_counts as (
            select post_id, count(*)::bigint as unlocks
            from gallery_prompt_unlocks
            group by post_id
        )
        select
            'prompt_candidates_legacy' as row_type,
            h.id,
            h.task_id,
            h.user_id,
            h.type as task_type,
            h.raw_prompt as prompt,
            h.input_file,
            h.output_file,
            h.extra_outputs,
            h.created_at,
            h.source,
            h.is_favorited,
            h.allow_contribute,
            h.builtin_template_key,
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
        query_days,
        limit,
        sample_limit,
        task_filter,
        template_scope,
    )
    candidates = []
    for record in rows:
        item = _row(record)
        input_refs = _extract_refs(item.get("input_file"))
        output_refs = _extract_refs(item.get("output_file")) + _extract_refs(item.get("extra_outputs"))
        item["prompt_preview"] = _collapse_text(item.pop("prompt", None), 260)
        item["input_refs"] = input_refs[:6]
        item["output_refs"] = output_refs[:6]
        item["media"] = {
            "input": _classify_refs(input_refs),
            "output": _classify_refs(output_refs),
        }
        item["input_requirements"] = _input_requirements(input_refs, item.get("task_type"))
        item["primary_output_url"] = _media_url(output_refs[0]) if output_refs else None
        candidates.append(item)
    prompt_groups = []
    for record in group_records:
        item = _enrich_prompt_group(record)
        prompt_groups.append(item)
    total_groups = int(summary.get("distinct_prompts") or 0)
    return {
        "days": days,
        "limit": limit,
        "page": page,
        "task_type": task_filter,
        "template_scope": template_scope,
        "query": search,
        "min_users": min_users,
        "min_uses": min_uses,
        "sort": sort,
        "mart": mart_status,
        "summary": summary,
        "distributions": {
            "length": _rows(length_distribution),
            "task_type": _rows(task_type_distribution),
            "reuse": _rows(reuse_distribution),
            "template_scope": _rows(template_scope_distribution),
        },
        "prompt_groups": prompt_groups,
        "pagination": {
            "page": page,
            "limit": limit,
            "total_groups": total_groups,
            "has_next": offset + limit < total_groups,
        },
        "candidates": candidates,
    }


@app.get("/api/prompts/{prompt_hash}/variants")
async def prompt_variants(
    prompt_hash: str,
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    task_type: str | None = Query(None),
    template_scope: str = Query("natural"),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    days = _clamp_days(days)
    limit = _clamp(limit, 1, 100)
    task_filter = (task_type or "").strip() or None
    template_scope = (template_scope or "natural").strip()
    if template_scope not in {"natural", "source_template", "builtin_template", "derived", "all"}:
        raise HTTPException(status_code=400, detail="invalid template_scope")
    mart_status = await _prompt_mart_status_or_error()
    rows = await _fetch(
        """
        with scoped as (
            select
                coalesce(nullif(o.raw_prompt, ''), o.prompt) as raw_prompt,
                o.user_id,
                coalesce(o.task_type, 'unknown') as task_type,
                o.created_at
            from analytics_prompt_occurrence o
            where o.prompt_hash = $1::text
              and ($2::int = 0 or o.created_at >= now() - ($2::int * interval '1 day'))
              and ($3::text is null or o.task_type = $3::text)
              and (
                  $4::text = 'all'
                  or ($4::text = 'natural' and o.allow_contribute is distinct from false and o.builtin_template_key is null)
                  or ($4::text = 'derived' and o.allow_contribute is false)
                  or ($4::text = 'builtin_template' and o.allow_contribute is distinct from false and o.builtin_template_key is not null)
                  or (
                      $4::text = 'source_template'
                      and o.allow_contribute is distinct from false
                      and o.builtin_template_key is null
                      and exists (
                          select 1
                          from gallery_posts source_gp
                          where source_gp.task_id = o.task_id
                            and source_gp.is_active is true
                      )
                  )
              )
        ),
        variants as (
            select
                raw_prompt,
                count(*)::bigint as uses,
                count(distinct user_id)::bigint as users,
                array_remove(array_agg(distinct task_type order by task_type), null) as task_types,
                min(created_at) as first_seen,
                max(created_at) as last_seen
            from scoped
            group by raw_prompt
        )
        select raw_prompt, uses, users, task_types, first_seen, last_seen
        from variants
        order by uses desc, last_seen desc, raw_prompt
        limit $5::int
        """,
        prompt_hash,
        days,
        task_filter,
        template_scope,
        limit,
    )
    variants = []
    for record in rows:
        item = _row(record)
        item["raw_preview"] = _collapse_text(item.get("raw_prompt"), 220)
        variants.append(item)
    return {
        "prompt_hash": prompt_hash,
        "days": days,
        "task_type": task_filter,
        "template_scope": template_scope,
        "limit": limit,
        "mart": mart_status,
        "variants": variants,
    }


@app.get("/api/prompt-slim")
async def prompt_slim(
    limit: int = Query(50, ge=1, le=100),
    page: int = Query(1, ge=1, le=10000),
    quality_stage: str = Query("all"),
    task_type: str | None = Query(None),
    source_scope: str | None = Query(None),
    reason: str | None = Query(None),
    q: str | None = Query(None),
    min_users: int = Query(1, ge=1, le=100000),
    min_uses: int = Query(1, ge=1, le=100000),
    sort: str = Query("quality_score"),
) -> dict[str, Any]:
    limit = _clamp(limit, 1, 100)
    page = _clamp(page, 1, 10000)
    min_users = _clamp(min_users, 1, 100000)
    min_uses = _clamp(min_uses, 1, 100000)
    stage_filter = (quality_stage or "all").strip()
    if stage_filter != "all" and stage_filter not in PROMPT_SLIM_STAGES:
        raise HTTPException(status_code=400, detail="invalid prompt slim quality_stage")
    task_filter = (task_type or "").strip() or None
    source_filter = (source_scope or "").strip() or None
    if source_filter == "all":
        source_filter = None
    if source_filter is not None and source_filter not in PROMPT_SLIM_SOURCE_SCOPES:
        raise HTTPException(status_code=400, detail="invalid prompt slim source_scope")
    reason_filter = (reason or "").strip() or None
    if reason_filter == "all":
        reason_filter = None
    sort = (sort or "quality_score").strip()
    if sort not in PROMPT_SLIM_SORTS:
        raise HTTPException(status_code=400, detail="invalid prompt slim sort")
    search = (q or "").strip()
    normalized_search = _normalize_prompt_text(search)
    search_pattern = f"%{normalized_search}%" if normalized_search else None
    offset = (page - 1) * limit
    await _prompt_slim_ready_or_error()
    filtered_cte = """
        with filtered as (
            select *
            from analytics_prompt_slim_candidates
            where ($1::text = 'all' or quality_stage = $1::text)
              and ($2::text is null or $2::text = any(task_types))
              and ($3::text is null or $3::text = any(source_scopes))
              and ($4::text is null or $4::text = any(low_quality_reasons))
              and ($5::text is null or prompt like $5::text)
              and users >= $6::int
              and uses >= $7::int
        )
    """
    common_args = (
        stage_filter,
        task_filter,
        source_filter,
        reason_filter,
        search_pattern,
        min_users,
        min_uses,
    )
    summary = _row(
        await _fetchrow(
            f"""
            {filtered_cte}
            select
                'slim_summary' as row_type,
                count(*)::bigint as slim_prompts,
                count(*) filter (where quality_stage = 'candidate')::bigint as candidate_prompts,
                count(*) filter (where quality_stage = 'auto_rejected')::bigint as auto_rejected_prompts,
                count(*) filter (where quality_stage = 'manual_keep')::bigint as manual_keep_prompts,
                count(*) filter (where quality_stage = 'manual_reject')::bigint as manual_reject_prompts,
                count(*) filter (where quality_stage = 'excellent')::bigint as excellent_prompts,
                count(*) filter (where quality_stage = 'archived')::bigint as archived_prompts,
                coalesce(sum(uses), 0)::bigint as uses,
                coalesce(sum(users), 0)::bigint as user_refs,
                round(coalesce(avg(char_count), 0)::numeric, 2) as avg_chars,
                coalesce(percentile_cont(0.5) within group (order by char_count), 0)::numeric as median_chars,
                coalesce(sum(result_likes), 0)::bigint as result_likes,
                coalesce(sum(result_dislikes), 0)::bigint as result_dislikes,
                coalesce(sum(gallery_likes), 0)::bigint as gallery_likes,
                coalesce(sum(gallery_dislikes), 0)::bigint as gallery_dislikes,
                coalesce(sum(gallery_applies), 0)::bigint as gallery_applies,
                coalesce(sum(prompt_unlocks), 0)::bigint as prompt_unlocks,
                max(refreshed_at) as latest_refreshed_at
            from filtered
            """,
            *common_args,
        )
    )
    rows = await _fetch(
        f"""
        {filtered_cte}
        select
            'prompt_slim_rows' as row_type,
            prompt_hash,
            normalization_version,
            prompt,
            raw_prompt_representative,
            variant_count,
            char_count,
            uses,
            users,
            coalesce(array_length(using_user_ids, 1), 0)::int as using_user_count,
            using_user_ids[1:20] as using_user_ids_sample,
            first_seen,
            last_seen,
            task_types,
            task_type_counts,
            source_scopes,
            source_counts,
            result_likes,
            result_dislikes,
            coalesce(array_length(result_like_user_ids, 1), 0)::int as result_like_user_count,
            result_like_user_ids[1:20] as result_like_user_ids_sample,
            coalesce(array_length(result_dislike_user_ids, 1), 0)::int as result_dislike_user_count,
            result_dislike_user_ids[1:20] as result_dislike_user_ids_sample,
            gallery_posts,
            gallery_likes,
            gallery_dislikes,
            gallery_comments,
            gallery_applies,
            coalesce(array_length(gallery_apply_user_ids, 1), 0)::int as gallery_apply_user_count,
            gallery_apply_user_ids[1:20] as gallery_apply_user_ids_sample,
            prompt_unlocks,
            coalesce(array_length(prompt_unlock_user_ids, 1), 0)::int as prompt_unlock_user_count,
            prompt_unlock_user_ids[1:20] as prompt_unlock_user_ids_sample,
            quality_score,
            positive_signal_score,
            negative_signal_score,
            quality_stage,
            low_quality_reasons,
            rule_version,
            review_note,
            reviewed_by,
            reviewed_at,
            refreshed_at
        from filtered
        order by
            case when $8::text = 'quality_score' then quality_score end desc,
            case when $8::text = 'uses' then uses end desc,
            case when $8::text = 'users' then users end desc,
            case when $8::text = 'last_seen' then last_seen end desc,
            case when $8::text = 'result_likes' then result_likes end desc,
            case when $8::text = 'result_dislikes' then result_dislikes end desc,
            case when $8::text = 'gallery_applies' then gallery_applies end desc,
            case when $8::text = 'prompt_unlocks' then prompt_unlocks end desc,
            case when $8::text = 'char_count' then char_count end desc,
            quality_score desc,
            last_seen desc,
            prompt_hash desc
        limit $9::int
        offset $10::int
        """,
        *common_args,
        sort,
        limit,
        offset,
    )
    stage_distribution = await _fetch(
        f"""
        {filtered_cte}
        select 'prompt_slim_stage_distribution' as row_type, quality_stage as label, count(*)::bigint as count
        from filtered
        group by quality_stage
        order by count desc, label
        """,
        *common_args,
    )
    reason_distribution = await _fetch(
        f"""
        {filtered_cte}
        select 'prompt_slim_reason_distribution' as row_type, reason_label as label, count(*)::bigint as count
        from filtered
        cross join lateral (
            select unnest(low_quality_reasons) as reason_label
            union all
            select '无' where cardinality(low_quality_reasons) = 0
        ) reasons
        group by reason_label
        order by count desc, label
        """,
        *common_args,
    )
    task_type_distribution = await _fetch(
        f"""
        {filtered_cte}
        select 'prompt_slim_task_type_distribution' as row_type, task_type as label, count(*)::bigint as count
        from filtered, unnest(task_types) as task_type
        group by task_type
        order by count desc, label
        limit 30
        """,
        *common_args,
    )
    source_distribution = await _fetch(
        f"""
        {filtered_cte}
        select 'prompt_slim_source_distribution' as row_type, source_scope as label, count(*)::bigint as count
        from filtered, unnest(source_scopes) as source_scope
        group by source_scope
        order by count desc, label
        """,
        *common_args,
    )
    length_distribution = await _fetch(
        f"""
        {filtered_cte}
        select
            'prompt_slim_length_distribution' as row_type,
            bucket.label,
            count(*)::bigint as count
        from filtered
        cross join lateral (
            select
                case
                    when char_count <= 12 then '1-12 字'
                    when char_count <= 20 then '13-20 字'
                    when char_count <= 40 then '21-40 字'
                    when char_count <= 80 then '41-80 字'
                    when char_count <= 160 then '81-160 字'
                    when char_count <= 320 then '161-320 字'
                    else '320+ 字'
                end as label,
                case
                    when char_count <= 12 then 1
                    when char_count <= 20 then 2
                    when char_count <= 40 then 3
                    when char_count <= 80 then 4
                    when char_count <= 160 then 5
                    when char_count <= 320 then 6
                    else 7
                end as sort_order
        ) bucket
        group by bucket.label, bucket.sort_order
        order by bucket.sort_order
        """,
        *common_args,
    )
    prompt_rows = [_enrich_prompt_slim_row(record) for record in rows]
    total = int(summary.get("slim_prompts") or 0)
    return {
        "limit": limit,
        "page": page,
        "quality_stage": stage_filter,
        "task_type": task_filter,
        "source_scope": source_filter or "all",
        "reason": reason_filter or "all",
        "query": search,
        "min_users": min_users,
        "min_uses": min_uses,
        "sort": sort,
        "summary": summary,
        "distributions": {
            "stage": _rows(stage_distribution),
            "reason": _rows(reason_distribution),
            "task_type": _rows(task_type_distribution),
            "source_scope": _rows(source_distribution),
            "length": _rows(length_distribution),
        },
        "rows": prompt_rows,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": offset + limit < total,
        },
    }


@app.post("/api/prompt-vectors/resume")
async def resume_prompt_vector_embeddings(
    batch_size: int = Query(8, ge=1, le=128),
    statement_timeout_ms: int = Query(3_600_000, ge=60_000, le=24 * 60 * 60 * 1000),
    model_id: str = Query(DEFAULT_VECTOR_MODEL_ID),
    model_key: str = Query(DEFAULT_VECTOR_MODEL_KEY),
    base_url: str = Query(DEFAULT_LM_STUDIO_BASE_URL),
    task_type: str | None = Query(None),
) -> dict[str, Any]:
    if _active_prompt_vector_resume_process() is not None or _is_prompt_vector_refresh_lock_held():
        return {
            "status": "running",
            "message": "已有向量化任务在运行",
            "resume": _prompt_vector_resume_status(),
        }

    command = [
        sys.executable,
        "-m",
        "app.refresh_prompt_vectors",
        "--embed-only",
        "--batch-size",
        str(batch_size),
        "--statement-timeout-ms",
        str(statement_timeout_ms),
        "--model-id",
        model_id,
        "--model-key",
        model_key,
        "--base-url",
        base_url,
        "--data-dir",
        _prompt_vector_data_dir(),
    ]
    task_filter = (task_type or "").strip()
    if task_filter:
        command.extend(["--task-type", task_filter])

    PROMPT_VECTOR_RESUME_LOG.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LOCAL_ANALYTICS_DATABASE_URL"] = _database_url()
    try:
        with PROMPT_VECTOR_RESUME_LOG.open("ab") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=str(ROOT_DIR),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except Exception as exc:  # pragma: no cover - surfaced to the UI.
        raise HTTPException(status_code=500, detail=f"failed to start prompt vector refresh: {type(exc).__name__}") from exc

    app.state.prompt_vector_resume_process = process
    app.state.prompt_vector_resume_started_at = datetime.now().isoformat()
    app.state.prompt_vector_resume_last_exit = None
    return {
        "status": "started",
        "message": "已开始续跑缺失向量",
        "pid": process.pid,
        "log_path": str(PROMPT_VECTOR_RESUME_LOG),
    }


@app.get("/api/prompt-vectors")
async def prompt_vectors(
    limit: int = Query(40, ge=1, le=100),
    page: int = Query(1, ge=1, le=10000),
    task_type: str | None = Query(None),
    min_size: int = Query(2, ge=2, le=1000),
    min_similarity: float = Query(DEFAULT_DUPLICATE_THRESHOLD, ge=0, le=1),
    q: str | None = Query(None),
    sort: str = Query("member_count"),
    model_id: str = Query(DEFAULT_VECTOR_MODEL_ID),
) -> dict[str, Any]:
    limit = _clamp(limit, 1, 100)
    page = _clamp(page, 1, 10000)
    min_size = _clamp(min_size, 2, 1000)
    task_filter = (task_type or "").strip() or None
    sort = (sort or "member_count").strip()
    if sort not in PROMPT_VECTOR_SORTS:
        raise HTTPException(status_code=400, detail="invalid prompt vector sort")
    search = (q or "").strip()
    normalized_search = _normalize_prompt_text(search)
    search_pattern = f"%{normalized_search}%" if normalized_search else None
    offset = (page - 1) * limit

    if not await _prompt_vector_tables_ready():
        return {
            "ready": False,
            "message": (
                "prompt vector tables are not built; run "
                "python -m app.refresh_prompt_vectors --limit 1000 for a pilot"
            ),
            "model": {
                "model_id": model_id,
                "model_key": DEFAULT_VECTOR_MODEL_KEY,
                "normalization_version": PROMPT_NORMALIZATION_VERSION,
                "duplicate_threshold": DEFAULT_DUPLICATE_THRESHOLD,
                "similar_threshold": DEFAULT_SIMILAR_THRESHOLD,
            },
            "summary": {
                "candidate_count": 0,
                "embedded_count": 0,
                "embedding_coverage": 0,
                "edge_count": 0,
                "duplicate_edge_count": 0,
                "similar_edge_count": 0,
                "cluster_count": 0,
                "clustered_prompts": 0,
            },
            "distributions": {"task_type": [], "cluster_size": [], "band": []},
            "clusters": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "has_next": False},
            "resume": _prompt_vector_resume_status(),
        }

    state_prefix = f"{model_id}:{PROMPT_NORMALIZATION_VERSION}:"
    state_rows = await _fetch(
        """
        select key, value, updated_at
        from analytics_prompt_vector_state
        where key like $1::text
        order by key
        """,
        f"{state_prefix}%",
    )
    vector_state: dict[str, Any] = {}
    state_updated_at = None
    for row in state_rows:
        key = str(row["key"])[len(state_prefix) :]
        value = row["value"]
        try:
            vector_state[key] = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            vector_state[key] = value
        if row["updated_at"] and (state_updated_at is None or row["updated_at"] > state_updated_at):
            state_updated_at = row["updated_at"]

    summary = _row(
        await _fetchrow(
            """
            select
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_slim_candidates
                    where quality_stage = 'candidate'
                      and normalization_version = $2::text
                ), 0)::bigint as candidate_count,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_embeddings
                    where model_id = $1::text
                      and normalization_version = $2::text
                      and status = 'embedded'
                ), 0)::bigint as embedded_count,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_similarity_edges
                    where model_id = $1::text
                      and normalization_version = $2::text
                ), 0)::bigint as edge_count,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_similarity_edges
                    where model_id = $1::text
                      and normalization_version = $2::text
                      and band = 'duplicate'
                ), 0)::bigint as duplicate_edge_count,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_similarity_edges
                    where model_id = $1::text
                      and normalization_version = $2::text
                      and band = 'similar'
                ), 0)::bigint as similar_edge_count,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_similarity_clusters
                    where model_id = $1::text
                      and normalization_version = $2::text
                ), 0)::bigint as cluster_count,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_similarity_members m
                    join analytics_prompt_similarity_clusters c on c.cluster_id = m.cluster_id
                    where c.model_id = $1::text
                      and c.normalization_version = $2::text
                ), 0)::bigint as clustered_prompts,
                (
                    select max(refreshed_at)
                    from analytics_prompt_similarity_clusters
                    where model_id = $1::text
                      and normalization_version = $2::text
                ) as latest_refreshed_at
            """,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
        )
    )
    candidate_count = float(summary.get("candidate_count") or 0)
    embedded_count = float(summary.get("embedded_count") or 0)
    summary["embedding_coverage"] = round((embedded_count / candidate_count * 100) if candidate_count else 0, 2)

    filtered_cte = """
        with filtered as (
            select
                c.*,
                coalesce(s.uses, 0)::bigint as representative_uses,
                coalesce(s.users, 0)::bigint as representative_users,
                coalesce(s.result_likes, 0)::bigint as representative_result_likes,
                coalesce(s.result_dislikes, 0)::bigint as representative_result_dislikes,
                coalesce(s.gallery_applies, 0)::bigint as representative_gallery_applies,
                coalesce(s.prompt_unlocks, 0)::bigint as representative_prompt_unlocks,
                s.char_count,
                s.last_seen
            from analytics_prompt_similarity_clusters c
            left join analytics_prompt_slim_candidates s on s.prompt_hash = c.representative_hash
            where c.model_id = $1::text
              and c.normalization_version = $2::text
              and ($3::text is null or c.task_type = $3::text)
              and c.member_count >= $4::int
              and c.min_similarity >= $5::numeric
              and ($6::text is null or c.representative_prompt like $6::text)
        )
    """
    common_args = (
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        task_filter,
        min_size,
        min_similarity,
        search_pattern,
    )
    total_row = _row(
        await _fetchrow(
            f"""
            {filtered_cte}
            select count(*)::bigint as total
            from filtered
            """,
            *common_args,
        )
    )
    rows = await _fetch(
        f"""
        {filtered_cte}
        select
            cluster_id,
            model_id,
            normalization_version,
            task_type,
            representative_hash,
            representative_prompt,
            member_count,
            duplicate_edge_count,
            min_similarity,
            avg_similarity,
            max_similarity,
            total_uses,
            total_users,
            quality_score,
            representative_uses,
            representative_users,
            representative_result_likes,
            representative_result_dislikes,
            representative_gallery_applies,
            representative_prompt_unlocks,
            char_count,
            last_seen,
            refreshed_at
        from filtered
        order by
            case when $7::text = 'member_count' then member_count end desc,
            case when $7::text = 'quality_score' then quality_score end desc,
            case when $7::text = 'total_uses' then total_uses end desc,
            case when $7::text = 'similarity' then avg_similarity end desc,
            case when $7::text = 'refreshed_at' then refreshed_at end desc,
            member_count desc,
            quality_score desc,
            avg_similarity desc,
            cluster_id
        limit $8::int
        offset $9::int
        """,
        *common_args,
        sort,
        limit,
        offset,
    )
    task_distribution = await _fetch(
        """
        select task_type as label, count(*)::bigint as count
        from analytics_prompt_similarity_clusters
        where model_id = $1::text
          and normalization_version = $2::text
        group by task_type
        order by count desc, label
        limit 40
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
    )
    size_distribution = await _fetch(
        """
        select bucket.label, count(*)::bigint as count
        from analytics_prompt_similarity_clusters c
        cross join lateral (
            select
                case
                    when member_count = 2 then '2 条'
                    when member_count <= 5 then '3-5 条'
                    when member_count <= 10 then '6-10 条'
                    when member_count <= 20 then '11-20 条'
                    else '20+ 条'
                end as label,
                case
                    when member_count = 2 then 1
                    when member_count <= 5 then 2
                    when member_count <= 10 then 3
                    when member_count <= 20 then 4
                    else 5
                end as sort_order
        ) bucket
        where c.model_id = $1::text
          and c.normalization_version = $2::text
        group by bucket.label, bucket.sort_order
        order by bucket.sort_order
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
    )
    band_distribution = await _fetch(
        """
        select band as label, count(*)::bigint as count
        from analytics_prompt_similarity_edges
        where model_id = $1::text
          and normalization_version = $2::text
        group by band
        order by count desc, label
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
    )
    total = int(total_row.get("total") or 0)
    return {
        "ready": True,
        "model": {
            "model_id": model_id,
            "model_key": vector_state.get("model_key") or DEFAULT_VECTOR_MODEL_KEY,
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
            "embedding_dim": vector_state.get("embedding_dim"),
            "index_dir": vector_state.get("index_dir"),
            "last_success_at": vector_state.get("last_success_at"),
            "last_error": vector_state.get("last_error"),
            "state_updated_at": _json_value(state_updated_at),
            "duplicate_threshold": DEFAULT_DUPLICATE_THRESHOLD,
            "similar_threshold": DEFAULT_SIMILAR_THRESHOLD,
        },
        "limit": limit,
        "page": page,
        "task_type": task_filter,
        "min_size": min_size,
        "min_similarity": min_similarity,
        "query": search,
        "sort": sort,
        "summary": summary,
        "distributions": {
            "task_type": _rows(task_distribution),
            "cluster_size": _rows(size_distribution),
            "band": _rows(band_distribution),
        },
        "clusters": [_enrich_prompt_vector_cluster(record) for record in rows],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": offset + limit < total,
        },
        "resume": _prompt_vector_resume_status(),
    }


@app.get("/api/prompt-vectors/clusters/{cluster_id}")
async def prompt_vector_cluster_detail(
    cluster_id: str,
    model_id: str = Query(DEFAULT_VECTOR_MODEL_ID),
) -> dict[str, Any]:
    if not await _prompt_vector_tables_ready():
        raise HTTPException(status_code=503, detail="prompt vector tables are not built")
    cluster = await _fetchrow(
        """
        select
            c.*,
            coalesce(s.uses, 0)::bigint as representative_uses,
            coalesce(s.users, 0)::bigint as representative_users,
            s.char_count,
            s.first_seen,
            s.last_seen
        from analytics_prompt_similarity_clusters c
        left join analytics_prompt_slim_candidates s on s.prompt_hash = c.representative_hash
        where c.cluster_id = $1::text
          and c.model_id = $2::text
          and c.normalization_version = $3::text
        """,
        cluster_id,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
    )
    if cluster is None:
        raise HTTPException(status_code=404, detail="prompt vector cluster not found")
    members = await _fetch(
        """
        select
            m.cluster_id,
            m.prompt_hash,
            m.task_type,
            m.similarity_to_representative,
            m.is_representative,
            m.member_rank,
            s.prompt,
            s.raw_prompt_representative,
            s.variant_count,
            s.char_count,
            s.uses,
            s.users,
            s.result_likes,
            s.result_dislikes,
            s.gallery_likes,
            s.gallery_dislikes,
            s.gallery_applies,
            s.prompt_unlocks,
            s.quality_score,
            s.positive_signal_score,
            s.negative_signal_score,
            s.source_scopes,
            s.first_seen,
            s.last_seen
        from analytics_prompt_similarity_members m
        left join analytics_prompt_slim_candidates s on s.prompt_hash = m.prompt_hash
        where m.cluster_id = $1::text
        order by m.member_rank, m.prompt_hash
        """,
        cluster_id,
    )
    return {
        "model_id": model_id,
        "normalization_version": PROMPT_NORMALIZATION_VERSION,
        "cluster": _enrich_prompt_vector_cluster(cluster),
        "members": [_enrich_prompt_vector_member(record) for record in members],
    }


@app.get("/api/prompt-scenes")
async def prompt_scenes(
    limit: int = Query(40, ge=1, le=100),
    page: int = Query(1, ge=1, le=10000),
    task_type: str | None = Query(None),
    min_size: int = Query(1, ge=1, le=1_000_000),
    confidence_band: str = Query("all"),
    q: str | None = Query(None),
    sort: str = Query("member_count"),
    model_id: str = Query(DEFAULT_VECTOR_MODEL_ID),
) -> dict[str, Any]:
    limit = _clamp(limit, 1, 100)
    page = _clamp(page, 1, 10000)
    min_size = _clamp(min_size, 1, 1_000_000)
    task_filter = (task_type or "").strip() or None
    confidence_filter = (confidence_band or "all").strip()
    if confidence_filter not in PROMPT_SCENE_CONFIDENCE_BANDS:
        raise HTTPException(status_code=400, detail="invalid prompt scene confidence band")
    sort = (sort or "member_count").strip()
    if sort not in PROMPT_SCENE_SORTS:
        raise HTTPException(status_code=400, detail="invalid prompt scene sort")
    search = (q or "").strip()
    normalized_search = _normalize_prompt_text(search)
    search_pattern = f"%{normalized_search}%" if normalized_search else None
    offset = (page - 1) * limit

    if not await _prompt_scene_tables_ready():
        return {
            "ready": False,
            "message": "prompt semantic scenes are not built; run python -m app.refresh_prompt_scenes",
            "model": {
                "model_id": model_id,
                "model_key": DEFAULT_VECTOR_MODEL_KEY,
                "normalization_version": PROMPT_NORMALIZATION_VERSION,
                "algorithm_version": PROMPT_SCENE_ALGORITHM_VERSION,
                "candidates_per_scene": DEFAULT_CANDIDATES_PER_SCENE,
            },
            "summary": {
                "candidate_count": 0,
                "embedded_count": 0,
                "embedding_coverage": 0,
                "scene_count": 0,
                "scene_members": 0,
                "top_candidates": 0,
            },
            "distributions": {"task_type": [], "scene_size": [], "confidence": []},
            "scenes": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "has_next": False},
        }

    state_prefix = f"{model_id}:{PROMPT_NORMALIZATION_VERSION}:{PROMPT_SCENE_ALGORITHM_VERSION}:"
    state_rows = await _fetch(
        """
        select key, value, updated_at
        from analytics_prompt_semantic_scene_state
        where key like $1::text
        order by key
        """,
        f"{state_prefix}%",
    )
    scene_state: dict[str, Any] = {}
    state_updated_at = None
    for row in state_rows:
        key = str(row["key"])[len(state_prefix) :]
        value = row["value"]
        try:
            scene_state[key] = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            scene_state[key] = value
        if row["updated_at"] and (state_updated_at is None or row["updated_at"] > state_updated_at):
            state_updated_at = row["updated_at"]

    summary = _row(
        await _fetchrow(
            """
            select
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_slim_candidates
                    where quality_stage = 'candidate'
                      and normalization_version = $2::text
                ), 0)::bigint as candidate_count,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_embeddings
                    where model_id = $1::text
                      and normalization_version = $2::text
                      and status = 'embedded'
                ), 0)::bigint as embedded_count,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_semantic_scenes
                    where model_id = $1::text
                      and normalization_version = $2::text
                      and algorithm_version = $3::text
                ), 0)::bigint as scene_count,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_semantic_scene_members m
                    join analytics_prompt_semantic_scenes s on s.scene_id = m.scene_id
                    where s.model_id = $1::text
                      and s.normalization_version = $2::text
                      and s.algorithm_version = $3::text
                ), 0)::bigint as scene_members,
                coalesce((
                    select count(*)::bigint
                    from analytics_prompt_semantic_scene_members m
                    join analytics_prompt_semantic_scenes s on s.scene_id = m.scene_id
                    where s.model_id = $1::text
                      and s.normalization_version = $2::text
                      and s.algorithm_version = $3::text
                      and m.candidate_rank is not null
                ), 0)::bigint as top_candidates,
                (
                    select max(refreshed_at)
                    from analytics_prompt_semantic_scenes
                    where model_id = $1::text
                      and normalization_version = $2::text
                      and algorithm_version = $3::text
                ) as latest_refreshed_at
            """,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_SCENE_ALGORITHM_VERSION,
        )
    )
    candidate_count = float(summary.get("candidate_count") or 0)
    embedded_count = float(summary.get("embedded_count") or 0)
    summary["embedding_coverage"] = round((embedded_count / candidate_count * 100) if candidate_count else 0, 2)

    filtered_cte = """
        with filtered as (
            select
                c.*,
                coalesce(s.uses, 0)::bigint as representative_uses,
                coalesce(s.users, 0)::bigint as representative_users,
                coalesce(s.result_likes, 0)::bigint as representative_result_likes,
                coalesce(s.result_dislikes, 0)::bigint as representative_result_dislikes,
                coalesce(s.gallery_applies, 0)::bigint as representative_gallery_applies,
                coalesce(s.prompt_unlocks, 0)::bigint as representative_prompt_unlocks,
                s.char_count,
                s.last_seen
            from analytics_prompt_semantic_scenes c
            left join analytics_prompt_slim_candidates s on s.prompt_hash = c.representative_hash
            where c.model_id = $1::text
              and c.normalization_version = $2::text
              and c.algorithm_version = $3::text
              and ($4::text is null or c.task_type = $4::text)
              and c.member_count >= $5::int
              and ($6::text is null or coalesce(c.manual_label, '') like $6::text or c.representative_prompt like $6::text)
              and (
                  $7::text = 'all'
                  or exists (
                      select 1
                      from analytics_prompt_semantic_scene_members m
                      where m.scene_id = c.scene_id
                        and m.confidence_band = $7::text
                  )
              )
        )
    """
    common_args = (
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_SCENE_ALGORITHM_VERSION,
        task_filter,
        min_size,
        search_pattern,
        confidence_filter,
    )
    total_row = _row(
        await _fetchrow(
            f"""
            {filtered_cte}
            select count(*)::bigint as total
            from filtered
            """,
            *common_args,
        )
    )
    rows = await _fetch(
        f"""
        {filtered_cte}
        select
            scene_id,
            model_id,
            normalization_version,
            algorithm_version,
            task_type,
            representative_hash,
            representative_prompt,
            manual_label,
            member_count,
            candidate_count,
            high_confidence_count,
            medium_confidence_count,
            low_confidence_count,
            min_similarity,
            avg_similarity,
            max_similarity,
            total_uses,
            total_users,
            quality_score,
            representative_uses,
            representative_users,
            representative_result_likes,
            representative_result_dislikes,
            representative_gallery_applies,
            representative_prompt_unlocks,
            char_count,
            last_seen,
            refreshed_at
        from filtered
        order by
            case when $8::text = 'member_count' then member_count end desc,
            case when $8::text = 'candidate_count' then candidate_count end desc,
            case when $8::text = 'quality_score' then quality_score end desc,
            case when $8::text = 'total_uses' then total_uses end desc,
            case when $8::text = 'similarity' then avg_similarity end desc,
            case when $8::text = 'refreshed_at' then refreshed_at end desc,
            member_count desc,
            quality_score desc,
            avg_similarity desc,
            scene_id
        limit $9::int
        offset $10::int
        """,
        *common_args,
        sort,
        limit,
        offset,
    )
    task_distribution = await _fetch(
        """
        select task_type as label, count(*)::bigint as count
        from analytics_prompt_semantic_scenes
        where model_id = $1::text
          and normalization_version = $2::text
          and algorithm_version = $3::text
        group by task_type
        order by count desc, label
        limit 40
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_SCENE_ALGORITHM_VERSION,
    )
    size_distribution = await _fetch(
        """
        select bucket.label, count(*)::bigint as count
        from analytics_prompt_semantic_scenes c
        cross join lateral (
            select
                case
                    when member_count = 1 then '1 条'
                    when member_count <= 10 then '2-10 条'
                    when member_count <= 50 then '11-50 条'
                    when member_count <= 200 then '51-200 条'
                    else '200+ 条'
                end as label,
                case
                    when member_count = 1 then 1
                    when member_count <= 10 then 2
                    when member_count <= 50 then 3
                    when member_count <= 200 then 4
                    else 5
                end as sort_order
        ) bucket
        where c.model_id = $1::text
          and c.normalization_version = $2::text
          and c.algorithm_version = $3::text
        group by bucket.label, bucket.sort_order
        order by bucket.sort_order
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_SCENE_ALGORITHM_VERSION,
    )
    confidence_distribution = await _fetch(
        """
        select m.confidence_band as label, count(*)::bigint as count
        from analytics_prompt_semantic_scene_members m
        join analytics_prompt_semantic_scenes s on s.scene_id = m.scene_id
        where s.model_id = $1::text
          and s.normalization_version = $2::text
          and s.algorithm_version = $3::text
        group by m.confidence_band
        order by count desc, label
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_SCENE_ALGORITHM_VERSION,
    )
    total = int(total_row.get("total") or 0)
    return {
        "ready": True,
        "model": {
            "model_id": model_id,
            "model_key": scene_state.get("model_key") or DEFAULT_VECTOR_MODEL_KEY,
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
            "algorithm_version": PROMPT_SCENE_ALGORITHM_VERSION,
            "target_scene_count": scene_state.get("target_scene_count"),
            "candidates_per_scene": scene_state.get("candidates_per_scene") or DEFAULT_CANDIDATES_PER_SCENE,
            "last_success_at": scene_state.get("last_success_at"),
            "state_updated_at": _json_value(state_updated_at),
        },
        "limit": limit,
        "page": page,
        "task_type": task_filter,
        "min_size": min_size,
        "confidence_band": confidence_filter,
        "query": search,
        "sort": sort,
        "summary": summary,
        "distributions": {
            "task_type": _rows(task_distribution),
            "scene_size": _rows(size_distribution),
            "confidence": _rows(confidence_distribution),
        },
        "scenes": [_enrich_prompt_scene(record) for record in rows],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": offset + limit < total,
        },
    }


@app.get("/api/prompt-scenes/{scene_id}")
async def prompt_scene_detail(
    scene_id: str,
    model_id: str = Query(DEFAULT_VECTOR_MODEL_ID),
    limit: int = Query(DEFAULT_CANDIDATES_PER_SCENE, ge=1, le=100),
) -> dict[str, Any]:
    if not await _prompt_scene_tables_ready():
        raise HTTPException(status_code=503, detail="prompt semantic scenes are not built")
    limit = _clamp(limit, 1, 100)
    scene = await _fetchrow(
        """
        select
            c.*,
            coalesce(s.uses, 0)::bigint as representative_uses,
            coalesce(s.users, 0)::bigint as representative_users,
            s.char_count,
            s.first_seen,
            s.last_seen
        from analytics_prompt_semantic_scenes c
        left join analytics_prompt_slim_candidates s on s.prompt_hash = c.representative_hash
        where c.scene_id = $1::text
          and c.model_id = $2::text
          and c.normalization_version = $3::text
          and c.algorithm_version = $4::text
        """,
        scene_id,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_SCENE_ALGORITHM_VERSION,
    )
    if scene is None:
        raise HTTPException(status_code=404, detail="prompt semantic scene not found")
    members = await _fetch(
        """
        select
            m.scene_id,
            m.prompt_hash,
            m.task_type,
            m.similarity_to_scene,
            m.confidence_band,
            m.member_rank,
            m.candidate_rank,
            s.prompt,
            s.raw_prompt_representative,
            s.variant_count,
            s.char_count,
            s.uses,
            s.users,
            s.result_likes,
            s.result_dislikes,
            s.gallery_likes,
            s.gallery_dislikes,
            s.gallery_applies,
            s.prompt_unlocks,
            s.quality_score,
            s.positive_signal_score,
            s.negative_signal_score,
            s.source_scopes,
            s.first_seen,
            s.last_seen
        from analytics_prompt_semantic_scene_members m
        left join analytics_prompt_slim_candidates s on s.prompt_hash = m.prompt_hash
        where m.scene_id = $1::text
          and m.candidate_rank is not null
        order by m.candidate_rank, m.member_rank, m.prompt_hash
        limit $2::int
        """,
        scene_id,
        limit,
    )
    return {
        "model_id": model_id,
        "normalization_version": PROMPT_NORMALIZATION_VERSION,
        "algorithm_version": PROMPT_SCENE_ALGORITHM_VERSION,
        "candidate_limit": limit,
        "scene": _enrich_prompt_scene(scene),
        "candidates": [_enrich_prompt_scene_member(record) for record in members],
    }


@app.get("/api/prompt-graph")
async def prompt_graph(
    level: str = Query("scene"),
    task_type: str | None = Query(None),
    min_size: int = Query(1, ge=1, le=1_000_000),
    q: str | None = Query(None),
    edge_type: str = Query("all"),
    limit: int = Query(40, ge=1, le=500),
    model_id: str = Query(DEFAULT_VECTOR_MODEL_ID),
) -> dict[str, Any]:
    level = (level or "scene").strip()
    if level not in PROMPT_GRAPH_LEVELS:
        raise HTTPException(status_code=400, detail="invalid prompt graph level")
    edge_filter = (edge_type or "all").strip()
    if edge_filter not in PROMPT_GRAPH_EDGE_TYPES:
        raise HTTPException(status_code=400, detail="invalid prompt graph edge type")
    limit = _clamp(limit, 1, 500)
    min_size = _clamp(min_size, 1, 1_000_000)
    task_filter = (task_type or "").strip() or None
    search = (q or "").strip()
    search_pattern = f"%{_normalize_prompt_text(search)}%" if search else None

    if not await _prompt_graph_tables_ready():
        return {
            "ready": False,
            "message": "prompt graph is not built; run python -m app.refresh_prompt_graph",
            "model": {
                "model_id": model_id,
                "model_key": DEFAULT_VECTOR_MODEL_KEY,
                "normalization_version": PROMPT_NORMALIZATION_VERSION,
                "algorithm_version": PROMPT_GRAPH_ALGORITHM_VERSION,
                "layout_algorithm": PROMPT_GRAPH_LAYOUT_ALGORITHM,
            },
            "summary": {
                "candidate_count": 0,
                "node_count": 0,
                "embedded_count": 0,
                "scene_count": 0,
                "micro_count": 0,
                "singleton_count": 0,
                "no_scene_count": 0,
                "community_count": 0,
                "edge_count": 0,
                "centroid_bridge_count": 0,
                "embedding_coverage": 0,
            },
            "task_summary": {
                "candidate_count": 0,
                "node_count": 0,
                "scene_count": 0,
                "micro_count": 0,
                "singleton_count": 0,
                "no_scene_count": 0,
                "edge_count": 0,
            },
            "selected_task_type": None,
            "available_task_types": [],
            "distributions": {"task_type": [], "node_status": [], "community_type": []},
            "graph": {"nodes": [], "edges": []},
            "pagination": {"limit": limit, "total": 0},
        }

    state_prefix = f"{model_id}:{PROMPT_NORMALIZATION_VERSION}:{PROMPT_GRAPH_ALGORITHM_VERSION}:"
    state_rows = await _fetch(
        """
        select key, value, updated_at
        from analytics_prompt_graph_state
        where key like $1::text
        order by key
        """,
        f"{state_prefix}%",
    )
    graph_state: dict[str, Any] = {}
    state_updated_at = None
    for row in state_rows:
        key = str(row["key"])[len(state_prefix) :]
        value = row["value"]
        try:
            graph_state[key] = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            graph_state[key] = value
        if row["updated_at"] and (state_updated_at is None or row["updated_at"] > state_updated_at):
            state_updated_at = row["updated_at"]

    summary = _row(
        await _fetchrow(
            """
            select
                coalesce((select count(*)::bigint from analytics_prompt_slim_candidates where quality_stage = 'candidate' and normalization_version = $2::text), 0)::bigint as candidate_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text), 0)::bigint as node_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and has_embedding), 0)::bigint as embedded_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_communities where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and community_type = 'scene'), 0)::bigint as scene_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_communities where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and community_type = 'micro'), 0)::bigint as micro_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and node_status = 'singleton'), 0)::bigint as singleton_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and node_status = 'no_scene'), 0)::bigint as no_scene_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_communities where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text), 0)::bigint as community_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_community_edges where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text), 0)::bigint as edge_count,
                0::bigint as centroid_bridge_count,
                (select max(refreshed_at) from analytics_prompt_graph_communities where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text) as latest_refreshed_at
            """,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_GRAPH_ALGORITHM_VERSION,
        )
    )
    candidate_count = float(summary.get("candidate_count") or 0)
    embedded_count = float(summary.get("embedded_count") or 0)
    summary["embedding_coverage"] = round((embedded_count / candidate_count * 100) if candidate_count else 0, 2)

    available_task_types = await _fetch(
        """
        select task_type as label, count(*)::bigint as count
        from analytics_prompt_graph_nodes
        where model_id = $1::text
          and normalization_version = $2::text
          and algorithm_version = $3::text
        group by task_type
        order by count desc, label
        limit 80
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    selected_task_type = task_filter or (str(available_task_types[0]["label"]) if available_task_types else None)
    task_summary = _row(
        await _fetchrow(
            """
            select
                coalesce((select count(*)::bigint from analytics_prompt_slim_candidates where quality_stage = 'candidate' and normalization_version = $2::text and $4::text = any(task_types)), 0)::bigint as candidate_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and task_type = $4::text), 0)::bigint as node_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_communities where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and community_type = 'scene' and task_type = $4::text), 0)::bigint as scene_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_communities where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and community_type = 'micro' and task_type = $4::text), 0)::bigint as micro_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and task_type = $4::text and node_status = 'singleton'), 0)::bigint as singleton_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_nodes where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and task_type = $4::text and node_status = 'no_scene'), 0)::bigint as no_scene_count,
                coalesce((select count(*)::bigint from analytics_prompt_graph_community_edges where model_id = $1::text and normalization_version = $2::text and algorithm_version = $3::text and source_task_type = $4::text and target_task_type = $4::text), 0)::bigint as edge_count
            """,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_GRAPH_ALGORITHM_VERSION,
            selected_task_type,
        )
    )

    nodes = await _fetch(
        """
        select
            c.community_id,
            c.community_type,
            c.task_type,
            c.label,
            c.representative_hash,
            c.representative_prompt,
            c.member_count,
            c.micro_count,
            c.singleton_count,
            c.no_scene_count,
            c.quality_score,
            c.total_uses,
            c.total_users,
            c.avg_similarity,
            c.refreshed_at,
            l.x,
            l.y,
            l.radius
        from analytics_prompt_graph_communities c
        join analytics_prompt_graph_layout l
          on l.community_id = c.community_id
         and l.model_id = c.model_id
         and l.normalization_version = c.normalization_version
         and l.algorithm_version = c.algorithm_version
         and l.layout_algorithm = 'pca-v1'
        where c.model_id = $1::text
          and c.normalization_version = $2::text
          and c.algorithm_version = $3::text
          and c.community_type = $4::text
          and c.task_type = $5::text
          and c.member_count >= $6::int
          and ($7::text is null or c.label like $7::text or c.representative_prompt like $7::text)
        order by c.member_count desc, c.quality_score desc, c.community_id
        limit $8::int
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
        level,
        selected_task_type,
        min_size,
        search_pattern,
        limit,
    )
    node_ids = [str(row["community_id"]) for row in nodes]
    edges = (
        await _fetch(
            """
            select
                source_community_id,
                target_community_id,
                edge_type,
                weight,
                prompt_edge_count,
                duplicate_edge_count,
                similar_edge_count,
                avg_similarity,
                max_similarity
            from analytics_prompt_graph_community_edges
            where model_id = $1::text
              and normalization_version = $2::text
              and algorithm_version = $3::text
              and source_community_id = any($4::text[])
              and target_community_id = any($4::text[])
              and source_task_type = $6::text
              and target_task_type = $6::text
              and ($5::text = 'all' or edge_type = $5::text)
            order by weight desc, prompt_edge_count desc
            limit 2000
            """,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_GRAPH_ALGORITHM_VERSION,
            node_ids,
            edge_filter,
            selected_task_type,
        )
        if node_ids
        else []
    )
    task_distribution = await _fetch(
        """
        select task_type as label, count(*)::bigint as count
        from analytics_prompt_graph_communities
        where model_id = $1::text
          and normalization_version = $2::text
          and algorithm_version = $3::text
          and community_type = $4::text
        group by task_type
        order by count desc, label
        limit 40
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
        level,
    )
    node_status_distribution = await _fetch(
        """
        select node_status as label, count(*)::bigint as count
        from analytics_prompt_graph_nodes
        where model_id = $1::text
          and normalization_version = $2::text
          and algorithm_version = $3::text
        group by node_status
        order by count desc, label
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    community_type_distribution = await _fetch(
        """
        select community_type as label, count(*)::bigint as count
        from analytics_prompt_graph_communities
        where model_id = $1::text
          and normalization_version = $2::text
          and algorithm_version = $3::text
        group by community_type
        order by count desc, label
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    return {
        "ready": True,
        "model": {
            "model_id": model_id,
            "model_key": graph_state.get("model_key") or DEFAULT_VECTOR_MODEL_KEY,
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
            "algorithm_version": PROMPT_GRAPH_ALGORITHM_VERSION,
            "layout_algorithm": graph_state.get("layout_algorithm") or PROMPT_GRAPH_LAYOUT_ALGORITHM,
            "last_success_at": graph_state.get("last_success_at"),
            "state_updated_at": _json_value(state_updated_at),
        },
        "level": level,
        "task_type": selected_task_type,
        "selected_task_type": selected_task_type,
        "available_task_types": _rows(available_task_types),
        "min_size": min_size,
        "query": search,
        "edge_type": edge_filter,
        "summary": summary,
        "task_summary": task_summary,
        "distributions": {
            "task_type": _rows(task_distribution),
            "node_status": _rows(node_status_distribution),
            "community_type": _rows(community_type_distribution),
        },
        "graph": {
            "nodes": [_enrich_prompt_graph_node(record) for record in nodes],
            "edges": [_enrich_prompt_graph_edge(record) for record in edges],
        },
        "pagination": {"limit": limit, "total": len(nodes)},
    }


@app.get("/api/prompt-graph/communities/{community_id}")
async def prompt_graph_community_detail(
    community_id: str,
    model_id: str = Query(DEFAULT_VECTOR_MODEL_ID),
    member_limit: int = Query(30, ge=1, le=100),
    child_limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    if not await _prompt_graph_tables_ready():
        raise HTTPException(status_code=503, detail="prompt graph is not built")
    member_limit = _clamp(member_limit, 1, 100)
    child_limit = _clamp(child_limit, 1, 100)
    community = await _fetchrow(
        """
        select *
        from analytics_prompt_graph_communities
        where community_id = $1::text
          and model_id = $2::text
          and normalization_version = $3::text
          and algorithm_version = $4::text
        """,
        community_id,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
    )
    if community is None:
        raise HTTPException(status_code=404, detail="prompt graph community not found")
    children = await _fetch(
        """
        select child.community_id, child.label, child.member_count, child.avg_similarity
        from analytics_prompt_graph_communities child
        where child.parent_community_id = $1::text
          and child.model_id = $2::text
          and child.normalization_version = $3::text
          and child.algorithm_version = $4::text
        order by child.member_count desc, child.quality_score desc, child.community_id
        limit $5::int
        """,
        community_id,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
        child_limit,
    )
    members = await _fetch(
        """
        select
            m.community_id,
            m.prompt_hash,
            m.membership_type,
            m.confidence,
            m.confidence_band,
            m.member_rank,
            s.prompt,
            s.raw_prompt_representative,
            s.uses,
            s.users,
            s.quality_score,
            s.result_likes,
            s.result_dislikes,
            s.gallery_applies,
            s.prompt_unlocks,
            s.last_seen
        from analytics_prompt_graph_memberships m
        left join analytics_prompt_slim_candidates s on s.prompt_hash = m.prompt_hash
        where m.community_id = $1::text
        order by
            case when m.confidence_band = 'high' then 3 when m.confidence_band = 'medium' then 2 when m.confidence_band = 'low' then 1 else 0 end desc,
            m.confidence desc nulls last,
            m.member_rank,
            m.prompt_hash
        limit $2::int
        """,
        community_id,
        member_limit,
    )
    bridge_edges = await _fetch(
        """
        select
            case when source_community_id = $1::text then target_community_id else source_community_id end as target_community_id,
            edge_type,
            weight,
            prompt_edge_count,
            duplicate_edge_count,
            avg_similarity,
            max_similarity
        from analytics_prompt_graph_community_edges
        where model_id = $2::text
          and normalization_version = $3::text
          and algorithm_version = $4::text
          and (source_community_id = $1::text or target_community_id = $1::text)
        order by weight desc, prompt_edge_count desc
        limit $5::int
        """,
        community_id,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_GRAPH_ALGORITHM_VERSION,
        child_limit,
    )
    return {
        "model_id": model_id,
        "normalization_version": PROMPT_NORMALIZATION_VERSION,
        "algorithm_version": PROMPT_GRAPH_ALGORITHM_VERSION,
        "community": _row(community),
        "children": _rows(children),
        "members": [_enrich_prompt_graph_member(record) for record in members],
        "bridge_edges": _rows(bridge_edges),
    }


@app.get("/api/media-audit")
async def media_audit(
    days: int = Query(30, ge=0, le=MAX_ANALYTICS_DAYS),
    limit: int = Query(100, ge=1, le=300),
) -> dict[str, Any]:
    days = _clamp_days(days)
    query_days = _query_days(days)
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
        query_days,
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
