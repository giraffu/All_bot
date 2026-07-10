from __future__ import annotations

from typing import Any

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from .prompt_vectors import (
    PROMPT_TOKEN_ALIAS_SCHEMA_SQL,
    PROMPT_TOKEN_ALL_TASK,
    PROMPT_TOKEN_CUSTOM_TERM_SCHEMA_SQL,
    PROMPT_TOKEN_DELETION_SCHEMA_SQL,
    PROMPT_TOKEN_VERSION,
    normalize_prompt_token_alias_value,
    prompt_token_vector_state_key,
    prompt_token_model_scope_key,
    prompt_token_scope_label,
    prompt_token_task_scope_key,
    prompt_token_task_sort_order,
    validate_prompt_token_alias_rules,
    validate_prompt_token_custom_terms,
)
from .prompt_token_rules import build_prompt_token_rule_seed_rows
from .prompt_template_candidates import (
    PROMPT_TEMPLATE_SIMILARITY_BUCKETS,
    PROMPT_TEMPLATE_VERSION,
    ensure_prompt_template_candidate_schema,
    prompt_template_state_key,
)
from .prompt_decomposition import (
    PROMPT_DECOMPOSITION_DEFAULT_LIMIT,
    PROMPT_DECOMPOSITION_MAX_LIMIT,
    PROMPT_DECOMPOSITION_MIN_TOKEN_PROMPT_COUNT,
    PROMPT_DECOMPOSITION_SAVED_LIST_LIMIT,
    build_prompt_decomposition_token_metadata,
    dump_grouped_tokens_json,
    ensure_prompt_decomposition_schema,
    ensure_prompt_decomposition_task,
    normalize_prompt_decomposition_selected_tokens,
    prompt_decomposition_filter_groups as build_prompt_decomposition_filter_groups,
    prompt_decomposition_grouped_tokens,
)
from .analytics_common import (
    DEFAULT_LM_STUDIO_BASE_URL,
    DEFAULT_VECTOR_MODEL_ID,
    DEFAULT_VECTOR_MODEL_KEY,
    MAX_ANALYTICS_DAYS,
    PROMPT_GROUPS_ALLTIME_CTE,
    PROMPT_GROUPS_CTE,
    PROMPT_GROUPS_ROLLUP_CTE,
    PROMPT_NORMALIZATION_VERSION,
    PROMPT_ROLLUP_PERIODS,
    PROMPT_SLIM_SORTS,
    PROMPT_SLIM_SOURCE_SCOPES,
    PROMPT_SLIM_STAGES,
    PROMPT_VECTOR_RESUME_LOG,
    ROOT_DIR,
    _active_prompt_vector_resume_process,
    _clamp,
    _clamp_days,
    _classify_refs,
    _collapse_text,
    _database_url,
    _execute,
    _enrich_prompt_group,
    _enrich_prompt_slim_row,
    _extract_refs,
    _fetch,
    _fetchrow,
    _gather_limited,
    _input_requirements,
    _is_prompt_vector_refresh_lock_held,
    _json_value,
    _media_url,
    _normalize_prompt_text,
    _pool,
    _prompt_mart_status_or_error,
    _prompt_slim_ready_or_error,
    _prompt_vector_data_dir,
    _prompt_vector_resume_status,
    _prompt_vector_tables_ready,
    _query_days,
    _row,
    _rows,
    set_prompt_vector_resume_process,
)


router = APIRouter()


def _coerce_iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


PROMPT_TOKEN_SORTS = {
    "prompt_count": "prompt_count desc, use_count desc, token",
    "use_count": "use_count desc, prompt_count desc, token",
    "user_count": "user_count desc, prompt_count desc, token",
    "token": "token asc",
}
PROMPT_TOKEN_MAX_PAGE = 10_000_000
PROMPT_TOKEN_DEFAULT_MIN_PROMPT_COUNT = 5
PROMPT_TOKEN_MAX_MIN_PROMPT_COUNT = 100_000
PROMPT_TEMPLATE_SORTS = {
    "score": "quality_score desc, prompt_count desc, use_count desc, template_key",
    "prompt_count": "prompt_count desc, quality_score desc, template_key",
    "use_count": "use_count desc, prompt_count desc, template_key",
    "user_count": "user_count desc, prompt_count desc, template_key",
    "latest": "latest_prompt_at desc nulls last, prompt_count desc, template_key",
}
PROMPT_TEMPLATE_DEFAULT_MIN_PROMPTS = 20
PROMPT_TEMPLATE_MAX_MIN_PROMPTS = 100_000
PROMPT_TEMPLATE_REVIEW_MARKS_DEFAULT_LIMIT = 50
PROMPT_TEMPLATE_REVIEW_MARKS_MAX_LIMIT = 500
PROMPT_TEMPLATE_REFRESH_LOG = ROOT_DIR / "data" / "prompt_template_candidates" / "refresh.log"
PROMPT_TEMPLATE_REVIEW_STATUSES = {"all", "processed", "unprocessed", "low_quality"}
PROMPT_TEMPLATE_MARK_PROCESSED_STATUSES = {"all", "processed", "unprocessed"}

_prompt_template_refresh_process: Any | None = None
_prompt_template_refresh_started_at: str | None = None
_prompt_template_refresh_last_exit: dict[str, Any] | None = None


def _prompt_token_scope(task_type: str | None, model_key: str | None) -> dict[str, str]:
    raw_task = (task_type or "").strip()
    task = prompt_token_task_scope_key(raw_task) if raw_task else ""
    model = (model_key or "").strip()
    if model and not task:
        raise HTTPException(status_code=400, detail="task_type is required when model_key is set")
    if model:
        scope_key = prompt_token_model_scope_key(task, model)
    elif task:
        scope_key = task
    else:
        scope_key = PROMPT_TOKEN_ALL_TASK
    return {
        "key": scope_key,
        "task_type": task,
        "model_key": model,
        "label": prompt_token_scope_label(scope_key, task_type=task, model_key=model),
    }


async def _prompt_token_filter_options(selected_task_type: str | None) -> dict[str, Any]:
    task_rows = await _fetch(
        """
        select distinct on (parent_task_type)
            parent_task_type as value,
            coalesce(scope_label, parent_task_type) as label
        from analytics_prompt_token_stats
        where normalization_version = $1::text
          and token_version = $2::text
          and scope_kind = 'task'
          and parent_task_type is not null
        order by parent_task_type, refreshed_at desc
        """,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_TOKEN_VERSION,
    )
    task_filter = (selected_task_type or "").strip()
    model_rows = []
    if task_filter:
        model_rows = await _fetch(
            """
            select distinct on (parent_task_type, model_key)
                parent_task_type as task_type,
                model_key as value,
                coalesce(model_label, model_key) as label,
                task_type as scope_key
            from analytics_prompt_token_stats
            where normalization_version = $1::text
              and token_version = $2::text
              and scope_kind = 'model'
              and parent_task_type = $3::text
              and model_key is not null
            order by parent_task_type, model_key, refreshed_at desc
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            task_filter,
        )
    tasks = _rows(task_rows)
    tasks.sort(key=lambda row: (prompt_token_task_sort_order(row.get("value")), str(row.get("label") or "")))
    return {
        "tasks": tasks,
        "models": _rows(model_rows),
    }


async def _prompt_token_tables_ready() -> bool:
    return (await _prompt_token_tables_status()).get("ready", False)


async def _prompt_token_tables_status() -> dict[str, bool]:
    ready = _row(
        await _fetchrow(
            """
            select
                to_regclass('public.analytics_prompt_token_stats') is not null
                and to_regclass('public.analytics_prompt_token_prompts') is not null
                as ready,
                to_regclass('public.analytics_prompt_token_deleted_rules') is not null
                as deletion_ready,
                to_regclass('public.analytics_prompt_token_scope_summary') is not null
                as scope_summary_ready
            """
        )
    )
    return {
        "ready": bool(ready.get("ready")),
        "deletion_ready": bool(ready.get("deletion_ready")),
        "scope_summary_ready": bool(ready.get("scope_summary_ready")),
    }


async def _prompt_template_tables_status() -> dict[str, bool]:
    ready = _row(
        await _fetchrow(
            """
            select
                to_regclass('public.analytics_prompt_template_candidates') is not null
                and to_regclass('public.analytics_prompt_template_candidate_prompts') is not null
                as ready,
                to_regclass('public.analytics_prompt_template_state') is not null
                as state_ready
            """
        )
    )
    return {
        "ready": bool(ready.get("ready")),
        "state_ready": bool(ready.get("state_ready")),
    }


async def _ensure_prompt_template_schema() -> None:
    pool = await _pool()
    async with pool.acquire() as conn:
        await ensure_prompt_template_candidate_schema(conn)


def _active_prompt_template_refresh_process() -> Any | None:
    global _prompt_template_refresh_process
    global _prompt_template_refresh_last_exit
    process = _prompt_template_refresh_process
    if process is None:
        return None
    poll = getattr(process, "poll", None)
    return_code = poll() if callable(poll) else getattr(process, "returncode", None)
    if return_code is None:
        return process
    _prompt_template_refresh_last_exit = {
        "pid": process.pid,
        "returncode": return_code,
        "finished_at": datetime.now().isoformat(),
    }
    _prompt_template_refresh_process = None
    return None


def _set_prompt_template_refresh_process(process: Any) -> None:
    global _prompt_template_refresh_process
    global _prompt_template_refresh_started_at
    global _prompt_template_refresh_last_exit
    _prompt_template_refresh_process = process
    _prompt_template_refresh_started_at = datetime.now().isoformat()
    _prompt_template_refresh_last_exit = None


def _prompt_template_refresh_status() -> dict[str, Any]:
    process = _active_prompt_template_refresh_process()
    return {
        "running": bool(process),
        "pid": process.pid if process else None,
        "started_at": _prompt_template_refresh_started_at if process else None,
        "last_exit": _prompt_template_refresh_last_exit,
        "log_path": str(PROMPT_TEMPLATE_REFRESH_LOG),
    }


async def _prompt_template_state() -> dict[str, Any]:
    keys = [
        prompt_template_state_key("template_count"),
        prompt_template_state_key("prompt_links"),
        prompt_template_state_key("scanned_prompts"),
        prompt_template_state_key("matched_links"),
        prompt_template_state_key("refreshed_at"),
    ]
    table_status = await _prompt_template_tables_status()
    if not table_status.get("state_ready"):
        return {
            "template_count": 0,
            "prompt_links": 0,
            "scanned_prompts": 0,
            "matched_links": 0,
            "refreshed_at": None,
            "refresh": _prompt_template_refresh_status(),
        }
    rows = _rows(
        await _fetch(
            """
            select key, value, updated_at
            from analytics_prompt_template_state
            where key = any($1::text[])
            """,
            keys,
        )
    )
    return {
        "template_count": int(_state_value(rows, keys[0]) or 0),
        "prompt_links": int(_state_value(rows, keys[1]) or 0),
        "scanned_prompts": int(_state_value(rows, keys[2]) or 0),
        "matched_links": int(_state_value(rows, keys[3]) or 0),
        "refreshed_at": _state_value(rows, keys[4]),
        "refresh": _prompt_template_refresh_status(),
    }


def _prompt_decomposition_scope(task_type: str | None) -> dict[str, str]:
    try:
        task = ensure_prompt_decomposition_task(task_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "key": prompt_token_task_scope_key(task),
        "task_type": prompt_token_task_scope_key(task),
        "label": prompt_token_scope_label(prompt_token_task_scope_key(task), task_type=task, model_key=""),
    }


async def _prompt_decomposition_token_metadata() -> dict[str, Any]:
    await _ensure_prompt_token_alias_schema()
    await _ensure_prompt_token_custom_term_schema()
    alias_rows = _rows(
        await _fetch(
            """
            select representative_token, category_label, subcategory_label
            from analytics_prompt_token_alias_rules
            where enabled
            order by sort_order, id
            """
        )
    )
    custom_rows = _rows(
        await _fetch(
            """
            select term, category_label, subcategory_label
            from analytics_prompt_token_custom_terms
            where enabled
            order by sort_order, id
            """
        )
    )
    return build_prompt_decomposition_token_metadata(custom_rows, alias_rows)


async def _prompt_decomposition_saved_rows(scope_key: str, *, limit: int = PROMPT_DECOMPOSITION_SAVED_LIST_LIMIT) -> tuple[int, list[dict[str, Any]]]:
    pool = await _pool()
    async with pool.acquire() as conn:
        await ensure_prompt_decomposition_schema(conn)
    total_row = _row(
        await _fetchrow(
            """
            select count(*)::bigint as total
            from analytics_prompt_decomposition_saved_templates
            where scope_key = $1::text
            """,
            scope_key,
        )
    )
    rows = _rows(
        await _fetch(
            """
            select
                id,
                scope_key,
                task_type,
                title,
                prompt_hash,
                prompt,
                selected_tokens,
                tokens,
                grouped_tokens,
                uses,
                users,
                quality_score,
                last_seen,
                created_at,
                updated_at
            from analytics_prompt_decomposition_saved_templates
            where scope_key = $1::text
            order by updated_at desc, id desc
            limit $2::int
            """,
            scope_key,
            limit,
        )
    )
    return int(total_row.get("total") or 0), rows


async def _prompt_token_scope_candidate_count(scope_key: str, *, summary_ready: bool) -> int:
    if summary_ready:
        summary_row = _row(
            await _fetchrow(
                """
                select candidate_count
                from analytics_prompt_token_scope_summary
                where normalization_version = $1::text
                  and token_version = $2::text
                  and task_type = $3::text
                """,
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_TOKEN_VERSION,
                scope_key,
            )
        )
        if summary_row:
            return int(summary_row.get("candidate_count") or 0)
    fallback_row = _row(
        await _fetchrow(
            """
            select count(*)::bigint as candidate_count
            from analytics_prompt_token_prompts
            where normalization_version = $1::text
              and token_version = $2::text
              and scopes @> array[$3::text]
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            scope_key,
        )
    )
    return int(fallback_row.get("candidate_count") or 0)


async def _ensure_prompt_token_alias_schema() -> None:
    for statement in PROMPT_TOKEN_ALIAS_SCHEMA_SQL:
        await _execute(statement)


async def _ensure_prompt_token_custom_term_schema() -> None:
    for statement in PROMPT_TOKEN_CUSTOM_TERM_SCHEMA_SQL:
        await _execute(statement)


async def _ensure_prompt_token_deletion_schema() -> None:
    for statement in PROMPT_TOKEN_DELETION_SCHEMA_SQL:
        await _execute(statement)


def _normalize_prompt_token_api_value(value: str | None) -> str:
    token = normalize_prompt_token_alias_value(value)
    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    return token


def _state_value(rows: list[dict[str, Any]], key: str) -> str | None:
    for row in rows:
        if row.get("key") != key:
            continue
        value = row.get("value")
        if value is None:
            return None
        return str(value).strip('"')
    return None


async def _prompt_token_alias_status() -> dict[str, Any]:
    keys = [
        prompt_token_vector_state_key("prompt_token_alias_rules_updated_at"),
        prompt_token_vector_state_key("prompt_token_alias_applied_at"),
        prompt_token_vector_state_key("prompt_token_alias_rule_count"),
        prompt_token_vector_state_key("prompt_token_alias_map_count"),
    ]
    rows = _rows(
        await _fetch(
            """
            select key, value, updated_at
            from analytics_prompt_vector_state
            where key = any($1::text[])
            """,
            keys,
        )
    )
    rules_updated_at = _state_value(rows, keys[0])
    last_applied_at = _state_value(rows, keys[1])
    return {
        "rules_updated_at": rules_updated_at,
        "last_applied_at": last_applied_at,
        "rule_count": int(_state_value(rows, keys[2]) or 0),
        "alias_count": int(_state_value(rows, keys[3]) or 0),
        "pending": bool(rules_updated_at and (not last_applied_at or rules_updated_at > last_applied_at)),
        "resume": _prompt_vector_resume_status(),
    }


async def _prompt_token_custom_term_status() -> dict[str, Any]:
    keys = [
        prompt_token_vector_state_key("prompt_token_custom_terms_updated_at"),
        prompt_token_vector_state_key("prompt_token_custom_terms_applied_at"),
        prompt_token_vector_state_key("prompt_token_custom_term_count"),
    ]
    rows = _rows(
        await _fetch(
            """
            select key, value, updated_at
            from analytics_prompt_vector_state
            where key = any($1::text[])
            """,
            keys,
        )
    )
    rules_updated_at = _state_value(rows, keys[0])
    last_applied_at = _state_value(rows, keys[1])
    return {
        "rules_updated_at": rules_updated_at,
        "last_applied_at": last_applied_at,
        "term_count": int(_state_value(rows, keys[2]) or 0),
        "pending": bool(rules_updated_at and (not last_applied_at or rules_updated_at > last_applied_at)),
        "resume": _prompt_vector_resume_status(),
    }


async def _mark_prompt_token_alias_rules_updated() -> str:
    updated_at = datetime.now(timezone.utc).isoformat()
    await _execute(
        """
        insert into analytics_prompt_vector_state (key, value, updated_at)
        values ($1::text, $2::text, now())
        on conflict (key) do update set value = excluded.value, updated_at = now()
        """,
        prompt_token_vector_state_key("prompt_token_alias_rules_updated_at"),
        updated_at,
    )
    return updated_at


async def _mark_prompt_token_custom_terms_updated() -> str:
    updated_at = datetime.now(timezone.utc).isoformat()
    await _execute(
        """
        insert into analytics_prompt_vector_state (key, value, updated_at)
        values ($1::text, $2::text, now())
        on conflict (key) do update set value = excluded.value, updated_at = now()
        """,
        prompt_token_vector_state_key("prompt_token_custom_terms_updated_at"),
        updated_at,
    )
    return updated_at


def _prompt_vector_resume_log() -> Any:
    main_module = sys.modules.get("local_analytics_platform.app.main")
    if main_module is None:
        return PROMPT_VECTOR_RESUME_LOG
    return getattr(main_module, "PROMPT_VECTOR_RESUME_LOG", PROMPT_VECTOR_RESUME_LOG)


async def _start_prompt_token_rebuild(statement_timeout_ms: int) -> dict[str, Any]:
    if _active_prompt_vector_resume_process() is not None or _is_prompt_vector_refresh_lock_held():
        return {
            "status": "running",
            "message": "已有向量化或词元重建任务在运行",
            "resume": _prompt_vector_resume_status(),
        }

    command = [
        sys.executable,
        "-m",
        "app.refresh_prompt_vectors",
        "--tokens-only",
        "--statement-timeout-ms",
        str(statement_timeout_ms),
        "--data-dir",
        _prompt_vector_data_dir(),
    ]
    resume_log = _prompt_vector_resume_log()
    resume_log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LOCAL_ANALYTICS_DATABASE_URL"] = _database_url()
    try:
        with resume_log.open("ab") as log_handle:
            process = await asyncio.to_thread(
                _start_prompt_vector_resume_process,
                command,
                cwd=str(ROOT_DIR),
                env=env,
                log_handle=log_handle,
            )
    except Exception as exc:  # pragma: no cover - surfaced to the UI.
        raise HTTPException(status_code=500, detail=f"failed to start prompt token rebuild: {type(exc).__name__}") from exc

    set_prompt_vector_resume_process(process)
    return {
        "status": "started",
        "message": "已开始重建词元统计",
        "pid": process.pid,
        "log_path": str(resume_log),
    }


def _start_prompt_vector_resume_process(
    command: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    log_handle,
):
    main_module = sys.modules.get("local_analytics_platform.app.main")
    subprocess_module = getattr(main_module, "subprocess", subprocess)
    return subprocess_module.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=log_handle,
        stderr=subprocess_module.STDOUT,
        start_new_session=True,
    )


@router.get("/api/prompts")
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
    return await _build_prompts_payload(
        days=days,
        limit=limit,
        page=page,
        task_type=task_type,
        template_scope=template_scope,
        q=q,
        min_users=min_users,
        min_uses=min_uses,
        sort=sort,
    )


async def _build_prompts_payload(
    *,
    days: int,
    limit: int,
    page: int,
    task_type: str | None,
    template_scope: str,
    q: str | None,
    min_users: int,
    min_uses: int,
    sort: str,
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
    sample_limit = max(limit * 100, 20000)
    tasks = _start_prompts_payload_tasks(
        groups_cte=groups_cte,
        common_args=common_args,
        sort=sort,
        limit=limit,
        offset=offset,
        query_days=query_days,
        sample_limit=sample_limit,
        task_filter=task_filter,
        template_scope=template_scope,
    )
    (
        summary_record,
        group_records,
        length_distribution,
        task_type_distribution,
        reuse_distribution,
        template_scope_distribution,
        rows,
    ) = await _gather_limited(4, *tasks)
    return _build_prompts_response(
        days=days,
        limit=limit,
        page=page,
        task_filter=task_filter,
        template_scope=template_scope,
        search=search,
        min_users=min_users,
        min_uses=min_uses,
        sort=sort,
        mart_status=mart_status,
        offset=offset,
        summary_record=summary_record,
        group_records=group_records,
        length_distribution=length_distribution,
        task_type_distribution=task_type_distribution,
        reuse_distribution=reuse_distribution,
        template_scope_distribution=template_scope_distribution,
        rows=rows,
    )


def _start_prompts_payload_tasks(
    *,
    groups_cte: str,
    common_args: tuple[Any, ...],
    sort: str,
    limit: int,
    offset: int,
    query_days: int,
    sample_limit: int,
    task_filter: str | None,
    template_scope: str,
) -> tuple[Any, ...]:
    summary_task = _fetchrow(
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
    group_records_task = _fetch(
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
    length_distribution_task = _fetch(
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
    task_type_distribution_task = _fetch(
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
    reuse_distribution_task = _fetch(
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
    template_scope_distribution_task = _fetch(
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
    rows_task = _fetch(
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
    return (
        summary_task,
        group_records_task,
        length_distribution_task,
        task_type_distribution_task,
        reuse_distribution_task,
        template_scope_distribution_task,
        rows_task,
    )


def _build_prompts_response(
    *,
    days: int,
    limit: int,
    page: int,
    task_filter: str | None,
    template_scope: str,
    search: str,
    min_users: int,
    min_uses: int,
    sort: str,
    mart_status: dict[str, Any],
    offset: int,
    summary_record: Any,
    group_records: Any,
    length_distribution: Any,
    task_type_distribution: Any,
    reuse_distribution: Any,
    template_scope_distribution: Any,
    rows: Any,
) -> dict[str, Any]:
    summary = _row(summary_record)
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


@router.get("/api/prompts/{prompt_hash}/variants")
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


@router.get("/api/prompt-template-candidates")
async def prompt_template_candidates(
    task_type: str | None = Query(None),
    model_key: str | None = Query(None),
    q: str | None = Query(None),
    similarity_bucket: str | None = Query(None),
    review_status: str = Query("all"),
    page: int = Query(1, ge=1, le=PROMPT_TOKEN_MAX_PAGE),
    limit: int = Query(40, ge=1, le=100),
    sort: str = Query("score"),
    min_prompts: int = Query(PROMPT_TEMPLATE_DEFAULT_MIN_PROMPTS, ge=1, le=PROMPT_TEMPLATE_MAX_MIN_PROMPTS),
    include_filters: bool = Query(True),
) -> dict[str, Any]:
    table_status = await _prompt_template_tables_status()
    scope = _prompt_token_scope(task_type, model_key)
    filters = {"tasks": [], "models": []}
    if not table_status.get("ready"):
        return {
            "ready": False,
            "message": "prompt template candidates are not built; run python -m app.refresh_prompt_template_candidates",
            "summary": {
                "template_count": 0,
                "prompt_links": 0,
                "scanned_prompts": 0,
                "matched_links": 0,
                "refreshed_at": None,
                "refresh": _prompt_template_refresh_status(),
            },
            "rows": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "has_next": False},
            "scope": scope,
            "filters": filters,
            "query": (q or "").strip().casefold(),
            "sort": sort,
            "min_prompts": min_prompts,
            "similarity_bucket": (similarity_bucket or "").strip(),
            "review_status": (review_status or "all").strip(),
        }
    await _ensure_prompt_template_schema()
    page = _clamp(page, 1, PROMPT_TOKEN_MAX_PAGE)
    limit = _clamp(limit, 1, 100)
    min_prompts = _clamp(min_prompts, 1, PROMPT_TEMPLATE_MAX_MIN_PROMPTS)
    sort = (sort or "score").strip()
    if sort not in PROMPT_TEMPLATE_SORTS:
        raise HTTPException(status_code=400, detail="invalid prompt template sort")
    search = (q or "").strip().casefold()
    similarity_filter = (similarity_bucket or "").strip()
    if similarity_filter and similarity_filter not in PROMPT_TEMPLATE_SIMILARITY_BUCKETS:
        raise HTTPException(status_code=400, detail="invalid prompt template similarity bucket")
    review_filter = (review_status or "all").strip() or "all"
    if review_filter not in PROMPT_TEMPLATE_REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="invalid prompt template review status")
    filters = await _prompt_token_filter_options(scope["task_type"]) if include_filters else filters
    offset = (page - 1) * limit
    selected_scope = scope["key"] if scope["task_type"] or scope["model_key"] else None
    search_sql = "candidate.template_title || ' ' || candidate.slot_signature || ' ' || array_to_string(candidate.tokens, ' ')"

    total_row = _row(
        await _fetchrow(
            f"""
            with marked as (
                select template_key, count(*)::bigint as marked_prompt_count
                from analytics_prompt_template_candidate_review_marks
                where template_version = $1::text
                group by template_key
            ),
            template_marks as (
                select template_key, low_quality, low_quality_marked_at
                from analytics_prompt_template_candidate_template_review_marks
                where template_version = $1::text
                  and low_quality is true
            )
            select count(*)::bigint as total
            from analytics_prompt_template_candidates candidate
            left join marked on marked.template_key = candidate.template_key
            left join template_marks on template_marks.template_key = candidate.template_key
            where candidate.template_version = $1::text
              and ($2::text is null or candidate.scope_key = $2::text)
              and ($3::text is null or position($3::text in casefold({search_sql})) > 0)
              and candidate.prompt_count >= $4::bigint
              and ($5::text = '' or candidate.similarity_bucket = $5::text)
              and (
                  $6::text = 'all'
                  or (
                      $6::text = 'processed'
                      and (coalesce(marked.marked_prompt_count, 0) > 0 or coalesce(template_marks.low_quality, false))
                  )
                  or (
                      $6::text = 'unprocessed'
                      and coalesce(marked.marked_prompt_count, 0) = 0
                      and not coalesce(template_marks.low_quality, false)
                  )
                  or ($6::text = 'low_quality' and coalesce(template_marks.low_quality, false))
              )
            """,
            PROMPT_TEMPLATE_VERSION,
            selected_scope,
            search,
            min_prompts,
            similarity_filter,
            review_filter,
        )
    )
    rows = await _fetch(
        f"""
        with marked as (
            select template_key, count(*)::bigint as marked_prompt_count
            from analytics_prompt_template_candidate_review_marks
            where template_version = $1::text
            group by template_key
        ),
        template_marks as (
            select template_key, low_quality, low_quality_marked_at
            from analytics_prompt_template_candidate_template_review_marks
            where template_version = $1::text
              and low_quality is true
        )
        select
            candidate.template_key,
            candidate.scope_key,
            candidate.scope_kind,
            candidate.scope_label,
            candidate.parent_task_type,
            candidate.model_key,
            candidate.model_label,
            candidate.template_title,
            candidate.token_slots,
            candidate.tokens,
            candidate.prompt_count,
            candidate.use_count,
            candidate.user_count,
            candidate.quality_score,
            candidate.similarity_bucket,
            candidate.similarity_score,
            candidate.similarity_metrics,
            coalesce(marked.marked_prompt_count, 0)::bigint as marked_prompt_count,
            coalesce(template_marks.low_quality, false) as low_quality,
            template_marks.low_quality_marked_at,
            (
                coalesce(marked.marked_prompt_count, 0) > 0
                or coalesce(template_marks.low_quality, false)
            ) as processed,
            candidate.latest_prompt_at,
            candidate.refreshed_at
        from analytics_prompt_template_candidates candidate
        left join marked on marked.template_key = candidate.template_key
        left join template_marks on template_marks.template_key = candidate.template_key
        where candidate.template_version = $1::text
          and ($2::text is null or candidate.scope_key = $2::text)
          and ($3::text is null or position($3::text in casefold({search_sql})) > 0)
          and candidate.prompt_count >= $4::bigint
          and ($5::text = '' or candidate.similarity_bucket = $5::text)
          and (
              $6::text = 'all'
              or (
                  $6::text = 'processed'
                  and (coalesce(marked.marked_prompt_count, 0) > 0 or coalesce(template_marks.low_quality, false))
              )
              or (
                  $6::text = 'unprocessed'
                  and coalesce(marked.marked_prompt_count, 0) = 0
                  and not coalesce(template_marks.low_quality, false)
              )
              or ($6::text = 'low_quality' and coalesce(template_marks.low_quality, false))
          )
        order by {PROMPT_TEMPLATE_SORTS[sort]}
        limit $7::int
        offset $8::int
        """,
        PROMPT_TEMPLATE_VERSION,
        selected_scope,
        search,
        min_prompts,
        similarity_filter,
        review_filter,
        limit,
        offset,
    )
    total = int(total_row.get("total") or 0)
    return {
        "ready": True,
        "summary": await _prompt_template_state(),
        "rows": _rows(rows),
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": offset + limit < total,
        },
        "scope": scope,
        "filters": filters,
        "filters_included": include_filters,
        "query": search,
        "sort": sort,
        "min_prompts": min_prompts,
        "similarity_bucket": similarity_filter,
        "review_status": review_filter,
    }


@router.get("/api/prompt-template-candidates/{template_key}/prompts")
async def prompt_template_candidate_prompts(
    template_key: str,
    page: int = Query(1, ge=1, le=PROMPT_TOKEN_MAX_PAGE),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    table_status = await _prompt_template_tables_status()
    if not table_status.get("ready"):
        raise HTTPException(
            status_code=503,
            detail="prompt template candidates are not built; run python -m app.refresh_prompt_template_candidates",
        )
    await _ensure_prompt_template_schema()
    page = _clamp(page, 1, PROMPT_TOKEN_MAX_PAGE)
    limit = _clamp(limit, 1, 100)
    key = (template_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="template_key is required")
    summary = _row(
        await _fetchrow(
            """
            with marked as (
                select template_key, count(*)::bigint as marked_prompt_count
                from analytics_prompt_template_candidate_review_marks
                where template_version = $1::text
                  and template_key = $2::text
                group by template_key
            ),
            template_marks as (
                select template_key, low_quality, low_quality_marked_at
                from analytics_prompt_template_candidate_template_review_marks
                where template_version = $1::text
                  and template_key = $2::text
                  and low_quality is true
            )
            select
                candidate.template_key,
                candidate.scope_key,
                candidate.scope_kind,
                candidate.scope_label,
                candidate.parent_task_type,
                candidate.model_key,
                candidate.model_label,
                candidate.template_title,
                candidate.token_slots,
                candidate.tokens,
                candidate.prompt_count,
                candidate.use_count,
                candidate.user_count,
                candidate.quality_score,
                candidate.similarity_bucket,
                candidate.similarity_score,
                candidate.similarity_metrics,
                coalesce(marked.marked_prompt_count, 0)::bigint as marked_prompt_count,
                coalesce(template_marks.low_quality, false) as low_quality,
                template_marks.low_quality_marked_at,
                (
                    coalesce(marked.marked_prompt_count, 0) > 0
                    or coalesce(template_marks.low_quality, false)
                ) as processed,
                candidate.latest_prompt_at,
                candidate.refreshed_at
            from analytics_prompt_template_candidates candidate
            left join marked on marked.template_key = candidate.template_key
            left join template_marks on template_marks.template_key = candidate.template_key
            where candidate.template_version = $1::text
              and candidate.template_key = $2::text
            """,
            PROMPT_TEMPLATE_VERSION,
            key,
        )
    )
    if not summary:
        return {
            "ready": True,
            "template_key": key,
            "summary": None,
            "rows": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "has_next": False},
        }
    offset = (page - 1) * limit
    rows = await _fetch(
        """
        select
            prompts.prompt_hash,
            prompts.prompt,
            prompts.tokens,
            prompts.token_slots,
            prompts.task_types,
            prompts.scopes,
            prompts.uses,
            prompts.users,
            prompts.quality_score,
            prompts.last_seen,
            prompts.rank,
            (marks.prompt_hash is not null) as review_checked,
            marks.marked_at as review_marked_at
        from analytics_prompt_template_candidate_prompts prompts
        left join analytics_prompt_template_candidate_review_marks marks
          on marks.template_version = prompts.template_version
         and marks.template_key = prompts.template_key
         and marks.prompt_hash = prompts.prompt_hash
        where prompts.template_version = $1::text
          and prompts.template_key = $2::text
        order by prompts.rank
        limit $3::int
        offset $4::int
        """,
        PROMPT_TEMPLATE_VERSION,
        key,
        limit,
        offset,
    )
    items = []
    for record in rows:
        item = _row(record)
        item["prompt_preview"] = _collapse_text(item.get("prompt"), 320)
        items.append(item)
    total = int(summary.get("prompt_count") or 0)
    return {
        "ready": True,
        "template_key": key,
        "summary": summary,
        "rows": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": offset + limit < total,
        },
    }


@router.post("/api/prompt-template-candidates/template-review-marks")
async def save_prompt_template_candidate_template_review_mark(payload: dict[str, Any]) -> dict[str, Any]:
    template_key = str(payload.get("template_key") or "").strip()
    low_quality = bool(payload.get("low_quality"))
    if not template_key:
        raise HTTPException(status_code=400, detail="template_key is required")

    pool = await _pool()
    async with pool.acquire() as conn:
        await ensure_prompt_template_candidate_schema(conn)
        template_row = _row(
            await conn.fetchrow(
                """
                select template_key
                from analytics_prompt_template_candidates
                where template_version = $1::text
                  and template_key = $2::text
                limit 1
                """,
                PROMPT_TEMPLATE_VERSION,
                template_key,
            )
        )
        if not template_row:
            raise HTTPException(status_code=404, detail="template candidate not found")

        if low_quality:
            mark_row = _row(
                await conn.fetchrow(
                    """
                    insert into analytics_prompt_template_candidate_template_review_marks (
                        template_version,
                        template_key,
                        low_quality,
                        low_quality_marked_at,
                        updated_at
                    )
                    values ($1::text, $2::text, true, now(), now())
                    on conflict (template_version, template_key) do update set
                        low_quality = true,
                        low_quality_marked_at = coalesce(
                            analytics_prompt_template_candidate_template_review_marks.low_quality_marked_at,
                            now()
                        ),
                        updated_at = now()
                    returning template_key, low_quality, low_quality_marked_at
                    """,
                    PROMPT_TEMPLATE_VERSION,
                    template_key,
                )
            )
        else:
            await conn.execute(
                """
                delete from analytics_prompt_template_candidate_template_review_marks
                where template_version = $1::text
                  and template_key = $2::text
                """,
                PROMPT_TEMPLATE_VERSION,
                template_key,
            )
            mark_row = {"template_key": template_key, "low_quality": False, "low_quality_marked_at": None}

        count_row = _row(
            await conn.fetchrow(
                """
                select count(*)::bigint as marked_prompt_count
                from analytics_prompt_template_candidate_review_marks
                where template_version = $1::text
                  and template_key = $2::text
                """,
                PROMPT_TEMPLATE_VERSION,
                template_key,
            )
        )

    marked_count = int(count_row.get("marked_prompt_count") or 0)
    saved_low_quality = bool(mark_row.get("low_quality"))
    return {
        "status": "saved",
        "template_key": mark_row.get("template_key") or template_key,
        "low_quality": saved_low_quality,
        "low_quality_marked_at": mark_row.get("low_quality_marked_at"),
        "marked_prompt_count": marked_count,
        "processed": marked_count > 0 or saved_low_quality,
    }


@router.get("/api/prompt-template-candidates/review-marks")
async def prompt_template_candidate_review_marks(
    task_type: str | None = Query(None),
    model_key: str | None = Query(None),
    q: str | None = Query(None),
    similarity_bucket: str | None = Query(None),
    processed_status: str = Query("all"),
    page: int = Query(1, ge=1, le=PROMPT_TOKEN_MAX_PAGE),
    limit: int = Query(PROMPT_TEMPLATE_REVIEW_MARKS_DEFAULT_LIMIT, ge=1, le=PROMPT_TEMPLATE_REVIEW_MARKS_MAX_LIMIT),
) -> dict[str, Any]:
    table_status = await _prompt_template_tables_status()
    scope = _prompt_token_scope(task_type, model_key)
    search = (q or "").strip().casefold()
    similarity_filter = (similarity_bucket or "").strip()
    processed_filter = (processed_status or "all").strip() or "all"
    if similarity_filter and similarity_filter not in PROMPT_TEMPLATE_SIMILARITY_BUCKETS:
        raise HTTPException(status_code=400, detail="invalid prompt template similarity bucket")
    if processed_filter not in PROMPT_TEMPLATE_MARK_PROCESSED_STATUSES:
        raise HTTPException(status_code=400, detail="invalid prompt template review mark status")
    if not table_status.get("ready"):
        return {
            "ready": False,
            "message": "prompt template candidates are not built; run python -m app.refresh_prompt_template_candidates",
            "summary": {"marked_prompt_count": 0, "processed_prompt_count": 0, "unprocessed_prompt_count": 0},
            "rows": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "has_next": False},
            "scope": scope,
            "query": search,
            "similarity_bucket": similarity_filter,
            "processed_status": processed_filter,
        }
    await _ensure_prompt_template_schema()
    page = _clamp(page, 1, PROMPT_TOKEN_MAX_PAGE)
    limit = _clamp(limit, 1, PROMPT_TEMPLATE_REVIEW_MARKS_MAX_LIMIT)
    selected_scope = scope["key"] if scope["task_type"] or scope["model_key"] else None
    offset = (page - 1) * limit
    search_sql = (
        "coalesce(candidate.template_title, '') || ' ' || coalesce(marks.prompt, '') || ' ' "
        "|| coalesce(marks.prompt_hash, '') || ' ' || array_to_string(marks.tokens, ' ')"
    )
    total_row = _row(
        await _fetchrow(
            f"""
            select
                count(*) filter (
                    where $5::text = 'all'
                       or ($5::text = 'processed' and marks.review_processed is true)
                       or ($5::text = 'unprocessed' and marks.review_processed is not true)
                )::bigint as total,
                count(*) filter (where marks.review_processed is true)::bigint as processed_prompt_count,
                count(*) filter (where marks.review_processed is not true)::bigint as unprocessed_prompt_count
            from analytics_prompt_template_candidate_review_marks marks
            join analytics_prompt_template_candidates candidate
              on candidate.template_version = marks.template_version
             and candidate.template_key = marks.template_key
            where marks.template_version = $1::text
              and ($2::text is null or candidate.scope_key = $2::text)
              and ($3::text is null or position($3::text in casefold({search_sql})) > 0)
              and ($4::text = '' or candidate.similarity_bucket = $4::text)
            """,
            PROMPT_TEMPLATE_VERSION,
            selected_scope,
            search,
            similarity_filter,
            processed_filter,
        )
    )
    rows = await _fetch(
        f"""
        select
            candidate.template_key,
            candidate.template_title,
            candidate.scope_key,
            candidate.scope_label,
            candidate.parent_task_type,
            candidate.model_key,
            candidate.model_label,
            candidate.prompt_count,
            candidate.similarity_bucket,
            candidate.similarity_score,
            marks.prompt_hash,
            marks.prompt,
            marks.tokens,
            marks.token_slots,
            marks.task_types,
            marks.scopes,
            marks.uses,
            marks.users,
            marks.quality_score,
            marks.last_seen,
            marks.review_processed,
            marks.review_processed_at,
            marks.marked_at,
            marks.updated_at
        from analytics_prompt_template_candidate_review_marks marks
        join analytics_prompt_template_candidates candidate
          on candidate.template_version = marks.template_version
         and candidate.template_key = marks.template_key
        where marks.template_version = $1::text
          and ($2::text is null or candidate.scope_key = $2::text)
          and ($3::text is null or position($3::text in casefold({search_sql})) > 0)
          and ($4::text = '' or candidate.similarity_bucket = $4::text)
          and (
              $5::text = 'all'
              or ($5::text = 'processed' and marks.review_processed is true)
              or ($5::text = 'unprocessed' and marks.review_processed is not true)
          )
        order by marks.review_processed asc, marks.marked_at desc, marks.quality_score desc, marks.prompt_hash
        limit $6::int
        offset $7::int
        """,
        PROMPT_TEMPLATE_VERSION,
        selected_scope,
        search,
        similarity_filter,
        processed_filter,
        limit,
        offset,
    )
    items = []
    for record in rows:
        item = _row(record)
        item["prompt_preview"] = _collapse_text(item.get("prompt"), 420)
        items.append(item)
    total = int(total_row.get("total") or 0)
    return {
        "ready": True,
        "summary": {
            "marked_prompt_count": total,
            "processed_prompt_count": int(total_row.get("processed_prompt_count") or 0),
            "unprocessed_prompt_count": int(total_row.get("unprocessed_prompt_count") or 0),
        },
        "rows": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": offset + limit < total,
        },
        "scope": scope,
        "query": search,
        "similarity_bucket": similarity_filter,
        "processed_status": processed_filter,
    }


@router.post("/api/prompt-template-candidates/review-marks")
async def save_prompt_template_candidate_review_mark(payload: dict[str, Any]) -> dict[str, Any]:
    template_key = str(payload.get("template_key") or "").strip()
    prompt_hash = str(payload.get("prompt_hash") or "").strip()
    checked = bool(payload.get("checked"))
    if not template_key:
        raise HTTPException(status_code=400, detail="template_key is required")
    if not prompt_hash:
        raise HTTPException(status_code=400, detail="prompt_hash is required")

    pool = await _pool()
    async with pool.acquire() as conn:
        await ensure_prompt_template_candidate_schema(conn)
        prompt_row = _row(
            await conn.fetchrow(
                """
                select
                    prompts.template_key,
                    prompts.prompt_hash,
                    prompts.scope_key,
                    prompts.prompt,
                    prompts.tokens,
                    prompts.token_slots,
                    prompts.task_types,
                    prompts.scopes,
                    prompts.uses,
                    prompts.users,
                    prompts.quality_score,
                    prompts.last_seen
                from analytics_prompt_template_candidate_prompts prompts
                join analytics_prompt_template_candidates candidate
                  on candidate.template_version = prompts.template_version
                 and candidate.template_key = prompts.template_key
                where prompts.template_version = $1::text
                  and prompts.template_key = $2::text
                  and prompts.prompt_hash = $3::text
                limit 1
                """,
                PROMPT_TEMPLATE_VERSION,
                template_key,
                prompt_hash,
            )
        )
        if not prompt_row:
            raise HTTPException(status_code=404, detail="template prompt not found")
        if checked:
            await conn.execute(
                """
                insert into analytics_prompt_template_candidate_review_marks (
                    template_version,
                    template_key,
                    prompt_hash,
                    scope_key,
                    prompt,
                    tokens,
                    token_slots,
                    task_types,
                    scopes,
                    uses,
                    users,
                    quality_score,
                    last_seen,
                    marked_at,
                    updated_at
                )
                values (
                    $1::text,
                    $2::text,
                    $3::text,
                    $4::text,
                    $5::text,
                    $6::text[],
                    $7::jsonb,
                    $8::text[],
                    $9::text[],
                    $10::bigint,
                    $11::bigint,
                    $12::numeric,
                    $13::timestamptz,
                    now(),
                    now()
                )
                on conflict (template_version, template_key, prompt_hash) do update set
                    scope_key = excluded.scope_key,
                    prompt = excluded.prompt,
                    tokens = excluded.tokens,
                    token_slots = excluded.token_slots,
                    task_types = excluded.task_types,
                    scopes = excluded.scopes,
                    uses = excluded.uses,
                    users = excluded.users,
                    quality_score = excluded.quality_score,
                    last_seen = excluded.last_seen,
                    updated_at = now()
                """,
                PROMPT_TEMPLATE_VERSION,
                template_key,
                prompt_hash,
                str(prompt_row.get("scope_key") or ""),
                str(prompt_row.get("prompt") or ""),
                [str(value) for value in (prompt_row.get("tokens") or []) if str(value)],
                json.dumps(_json_object(prompt_row.get("token_slots")), ensure_ascii=False),
                [str(value) for value in (prompt_row.get("task_types") or []) if str(value)],
                [str(value) for value in (prompt_row.get("scopes") or []) if str(value)],
                int(prompt_row.get("uses") or 0),
                int(prompt_row.get("users") or 0),
                prompt_row.get("quality_score") or 0,
                _coerce_iso_datetime(prompt_row.get("last_seen")),
            )
        else:
            await conn.execute(
                """
                delete from analytics_prompt_template_candidate_review_marks
                where template_version = $1::text
                  and template_key = $2::text
                  and prompt_hash = $3::text
                """,
                PROMPT_TEMPLATE_VERSION,
                template_key,
                prompt_hash,
            )
        count_row = _row(
            await conn.fetchrow(
                """
                select
                    count(*)::bigint as marked_prompt_count,
                    coalesce(
                        (
                            select template_marks.low_quality
                            from analytics_prompt_template_candidate_template_review_marks template_marks
                            where template_marks.template_version = $1::text
                              and template_marks.template_key = $2::text
                              and template_marks.low_quality is true
                            limit 1
                        ),
                        false
                    ) as low_quality,
                    (
                        select template_marks.low_quality_marked_at
                        from analytics_prompt_template_candidate_template_review_marks template_marks
                        where template_marks.template_version = $1::text
                          and template_marks.template_key = $2::text
                          and template_marks.low_quality is true
                        limit 1
                    ) as low_quality_marked_at
                from analytics_prompt_template_candidate_review_marks
                where template_version = $1::text
                  and template_key = $2::text
                """,
                PROMPT_TEMPLATE_VERSION,
                template_key,
            )
        )
    marked_count = int(count_row.get("marked_prompt_count") or 0)
    low_quality = bool(count_row.get("low_quality"))
    return {
        "status": "saved" if checked else "removed",
        "template_key": template_key,
        "prompt_hash": prompt_hash,
        "review_checked": checked,
        "marked_prompt_count": marked_count,
        "low_quality": low_quality,
        "low_quality_marked_at": count_row.get("low_quality_marked_at"),
        "processed": marked_count > 0 or low_quality,
    }


@router.post("/api/prompt-template-candidates/review-marks/processed")
async def save_prompt_template_candidate_review_mark_processed(payload: dict[str, Any]) -> dict[str, Any]:
    template_key = str(payload.get("template_key") or "").strip()
    prompt_hash = str(payload.get("prompt_hash") or "").strip()
    processed = bool(payload.get("processed"))
    if not template_key:
        raise HTTPException(status_code=400, detail="template_key is required")
    if not prompt_hash:
        raise HTTPException(status_code=400, detail="prompt_hash is required")

    pool = await _pool()
    async with pool.acquire() as conn:
        await ensure_prompt_template_candidate_schema(conn)
        row = _row(
            await conn.fetchrow(
                """
                update analytics_prompt_template_candidate_review_marks
                set
                    review_processed = $4::boolean,
                    review_processed_at = case when $4::boolean then now() else null end,
                    updated_at = now()
                where template_version = $1::text
                  and template_key = $2::text
                  and prompt_hash = $3::text
                returning template_key, prompt_hash, review_processed, review_processed_at
                """,
                PROMPT_TEMPLATE_VERSION,
                template_key,
                prompt_hash,
                processed,
            )
        )
    if not row:
        raise HTTPException(status_code=404, detail="review mark not found")
    return {
        "status": "saved",
        "template_key": row.get("template_key") or template_key,
        "prompt_hash": row.get("prompt_hash") or prompt_hash,
        "review_processed": bool(row.get("review_processed")),
        "review_processed_at": row.get("review_processed_at"),
    }


@router.post("/api/prompt-template-candidates/refresh")
async def refresh_prompt_template_candidates_api(
    statement_timeout_ms: int = Query(3_600_000, ge=60_000, le=24 * 60 * 60 * 1000),
) -> dict[str, Any]:
    process = _active_prompt_template_refresh_process()
    if process is not None:
        return {
            "status": "running",
            "message": "已有模板候选刷新任务在运行",
            "refresh": _prompt_template_refresh_status(),
        }
    if _active_prompt_vector_resume_process() is not None or _is_prompt_vector_refresh_lock_held():
        return {
            "status": "running",
            "message": "已有向量化或词元重建任务在运行",
            "refresh": _prompt_template_refresh_status(),
            "resume": _prompt_vector_resume_status(),
        }
    command = [
        sys.executable,
        "-m",
        "app.refresh_prompt_template_candidates",
        "--statement-timeout-ms",
        str(statement_timeout_ms),
    ]
    PROMPT_TEMPLATE_REFRESH_LOG.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LOCAL_ANALYTICS_DATABASE_URL"] = _database_url()
    try:
        with PROMPT_TEMPLATE_REFRESH_LOG.open("ab") as log_handle:
            process = await asyncio.to_thread(
                _start_prompt_vector_resume_process,
                command,
                cwd=str(ROOT_DIR),
                env=env,
                log_handle=log_handle,
            )
    except Exception as exc:  # pragma: no cover - surfaced to the UI.
        raise HTTPException(
            status_code=500,
            detail=f"failed to start prompt template refresh: {type(exc).__name__}",
        ) from exc
    _set_prompt_template_refresh_process(process)
    return {
        "status": "started",
        "message": "已开始刷新模板候选",
        "pid": process.pid,
        "log_path": str(PROMPT_TEMPLATE_REFRESH_LOG),
        "refresh": _prompt_template_refresh_status(),
    }


@router.get("/api/prompt-decomposition")
async def prompt_decomposition(
    task_type: str | None = Query("edit"),
    q: str | None = Query(None),
    selected_tokens: str | None = Query(None),
    page: int = Query(1, ge=1, le=PROMPT_TOKEN_MAX_PAGE),
    limit: int = Query(PROMPT_DECOMPOSITION_DEFAULT_LIMIT, ge=1, le=PROMPT_DECOMPOSITION_MAX_LIMIT),
    include_filters: bool = Query(True),
) -> dict[str, Any]:
    scope = _prompt_decomposition_scope(task_type)
    table_status = await _prompt_token_tables_status()
    if not table_status.get("ready"):
        return {
            "ready": False,
            "message": "prompt token tables are not built; run python -m app.refresh_prompt_vectors --tokens-only",
            "scope": scope,
            "selected_tokens": [],
            "summary": {
                "candidate_count": 0,
                "matched_prompt_count": 0,
                "saved_template_count": 0,
                "token_filter_count": 0,
                "refreshed_at": None,
            },
            "filters": {"groups": []},
            "filters_included": include_filters,
            "rows": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "has_next": False},
        }

    page = _clamp(page, 1, PROMPT_TOKEN_MAX_PAGE)
    limit = _clamp(limit, 1, PROMPT_DECOMPOSITION_MAX_LIMIT)
    search = (q or "").strip().casefold() or None
    selected = normalize_prompt_decomposition_selected_tokens(selected_tokens)
    offset = (page - 1) * limit
    metadata = await _prompt_decomposition_token_metadata()
    token_rows = _rows(
        await _fetch(
            """
            select token, prompt_count, use_count, user_count, refreshed_at
            from analytics_prompt_token_stats
            where normalization_version = $1::text
              and token_version = $2::text
              and task_type = $3::text
              and prompt_count >= $4::bigint
              and not exists (
                  select 1
                  from analytics_prompt_token_deleted_rules deleted
                  where deleted.token = analytics_prompt_token_stats.token
              )
            order by prompt_count desc, token
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            scope["key"],
            PROMPT_DECOMPOSITION_MIN_TOKEN_PROMPT_COUNT,
        )
    )
    allowed_tokens = {row.get("token") for row in token_rows if row.get("token") in metadata}
    selected = [token for token in selected if token in allowed_tokens]
    filters = {
        "groups": build_prompt_decomposition_filter_groups(token_rows, metadata),
    } if include_filters else {"groups": []}
    candidate_count = await _prompt_token_scope_candidate_count(
        scope["key"],
        summary_ready=table_status.get("scope_summary_ready", False),
    )
    total_row = _row(
        await _fetchrow(
            """
            select count(*)::bigint as total
            from analytics_prompt_token_prompts
            where normalization_version = $1::text
              and token_version = $2::text
              and scopes @> array[$3::text]
              and ($4::text is null or position($4::text in casefold(prompt)) > 0)
              and ($5::text[] = '{}'::text[] or tokens @> $5::text[])
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            scope["key"],
            search,
            selected,
        )
    )
    rows = _rows(
        await _fetch(
            """
            select
                prompt_hash,
                prompt,
                tokens,
                task_types,
                scopes,
                char_count,
                coalesce((scope_uses ->> $4::text)::bigint, uses) as uses,
                coalesce((scope_users ->> $4::text)::bigint, users) as users,
                quality_score,
                last_seen
            from analytics_prompt_token_prompts
            where normalization_version = $1::text
              and token_version = $2::text
              and scopes @> array[$3::text]
              and ($5::text is null or position($5::text in casefold(prompt)) > 0)
              and ($6::text[] = '{}'::text[] or tokens @> $6::text[])
            order by quality_score desc, uses desc, users desc, prompt_hash
            limit $7::int
            offset $8::int
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            scope["key"],
            scope["key"],
            search,
            selected,
            limit,
            offset,
        )
    )
    prompt_items: list[dict[str, Any]] = []
    selected_set = set(selected)
    for row in rows:
        tokens = [str(value) for value in (row.get("tokens") or [])]
        grouped_tokens = prompt_decomposition_grouped_tokens(tokens, metadata)
        prompt_items.append(
            {
                **row,
                "prompt_preview": _collapse_text(row.get("prompt") or "", 240),
                "matched_tokens": [token for token in tokens if token in selected_set],
                "grouped_tokens": grouped_tokens,
            }
        )

    saved_total, _ = await _prompt_decomposition_saved_rows(scope["key"], limit=1)
    latest_refreshed_at = max((row.get("refreshed_at") for row in token_rows if row.get("refreshed_at")), default=None)
    total = int(total_row.get("total") or 0)
    return {
        "ready": True,
        "scope": scope,
        "query": search or "",
        "selected_tokens": selected,
        "filters": filters,
        "filters_included": include_filters,
        "summary": {
            "candidate_count": candidate_count,
            "matched_prompt_count": total,
            "saved_template_count": saved_total,
            "token_filter_count": len(selected),
            "refreshed_at": latest_refreshed_at,
            "min_token_prompt_count": PROMPT_DECOMPOSITION_MIN_TOKEN_PROMPT_COUNT,
        },
        "rows": prompt_items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": offset + limit < total,
        },
    }


@router.get("/api/prompt-decomposition/saved")
async def prompt_decomposition_saved(
    task_type: str | None = Query("edit"),
    limit: int = Query(PROMPT_DECOMPOSITION_SAVED_LIST_LIMIT, ge=1, le=100),
) -> dict[str, Any]:
    scope = _prompt_decomposition_scope(task_type)
    total, rows = await _prompt_decomposition_saved_rows(scope["key"], limit=limit)
    for row in rows:
        row["prompt_preview"] = _collapse_text(row.get("prompt") or "", 240)
    return {
        "scope": scope,
        "total": total,
        "rows": rows,
    }


@router.post("/api/prompt-decomposition/saved")
async def save_prompt_decomposition_template(payload: dict[str, Any]) -> dict[str, Any]:
    scope = _prompt_decomposition_scope(payload.get("task_type") or "edit")
    prompt_hash = str(payload.get("prompt_hash") or "").strip()
    title = str(payload.get("title") or "").strip()
    if not prompt_hash:
        raise HTTPException(status_code=400, detail="prompt_hash is required")
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    selected = normalize_prompt_decomposition_selected_tokens(payload.get("selected_tokens"))
    metadata = await _prompt_decomposition_token_metadata()
    pool = await _pool()
    async with pool.acquire() as conn:
        await ensure_prompt_decomposition_schema(conn)
        prompt_row = _row(
            await conn.fetchrow(
                """
                select
                    prompt_hash,
                    prompt,
                    tokens,
                    coalesce((scope_uses ->> $4::text)::bigint, uses) as uses,
                    coalesce((scope_users ->> $4::text)::bigint, users) as users,
                    quality_score,
                    last_seen
                from analytics_prompt_token_prompts
                where normalization_version = $1::text
                  and token_version = $2::text
                  and prompt_hash = $3::text
                  and scopes @> array[$4::text]
                limit 1
                """,
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_TOKEN_VERSION,
                prompt_hash,
                scope["key"],
            )
        )
        if not prompt_row:
            raise HTTPException(status_code=404, detail="prompt not found for decomposition scope")
        tokens = [str(value) for value in (prompt_row.get("tokens") or [])]
        grouped_tokens = prompt_decomposition_grouped_tokens(tokens, metadata)
        await conn.execute(
            """
            insert into analytics_prompt_decomposition_saved_templates (
                scope_key,
                task_type,
                title,
                prompt_hash,
                prompt,
                selected_tokens,
                tokens,
                grouped_tokens,
                uses,
                users,
                quality_score,
                last_seen,
                created_at,
                updated_at
            )
            values (
                $1::text,
                $2::text,
                $3::text,
                $4::text,
                $5::text,
                $6::text[],
                $7::text[],
                $8::jsonb,
                $9::bigint,
                $10::bigint,
                $11::numeric,
                $12::timestamptz,
                now(),
                now()
            )
            on conflict (scope_key, prompt_hash) do update set
                task_type = excluded.task_type,
                title = excluded.title,
                prompt = excluded.prompt,
                selected_tokens = excluded.selected_tokens,
                tokens = excluded.tokens,
                grouped_tokens = excluded.grouped_tokens,
                uses = excluded.uses,
                users = excluded.users,
                quality_score = excluded.quality_score,
                last_seen = excluded.last_seen,
                updated_at = now()
            """,
            scope["key"],
            scope["task_type"],
            title,
            prompt_hash,
            str(prompt_row.get("prompt") or ""),
            selected,
            tokens,
            dump_grouped_tokens_json(grouped_tokens),
            int(prompt_row.get("uses") or 0),
            int(prompt_row.get("users") or 0),
            prompt_row.get("quality_score") or 0,
            _coerce_iso_datetime(prompt_row.get("last_seen")),
        )
        saved_row = _row(
            await conn.fetchrow(
                """
                select
                    id,
                    scope_key,
                    task_type,
                    title,
                    prompt_hash,
                    prompt,
                    selected_tokens,
                    tokens,
                    grouped_tokens,
                    uses,
                    users,
                    quality_score,
                    last_seen,
                    created_at,
                    updated_at
                from analytics_prompt_decomposition_saved_templates
                where scope_key = $1::text
                  and prompt_hash = $2::text
                """,
                scope["key"],
                prompt_hash,
            )
        )
    saved_row["prompt_preview"] = _collapse_text(saved_row.get("prompt") or "", 240)
    return {
        "status": "saved",
        "scope": scope,
        "row": saved_row,
    }


@router.delete("/api/prompt-decomposition/saved/{saved_id}")
async def delete_prompt_decomposition_template(saved_id: int) -> dict[str, Any]:
    pool = await _pool()
    async with pool.acquire() as conn:
        await ensure_prompt_decomposition_schema(conn)
        deleted = _row(
            await conn.fetchrow(
                """
                delete from analytics_prompt_decomposition_saved_templates
                where id = $1::bigint
                returning id, scope_key, prompt_hash
                """,
                saved_id,
            )
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="saved template not found")
    return {
        "status": "deleted",
        "id": int(deleted.get("id") or 0),
        "scope_key": deleted.get("scope_key") or "",
        "prompt_hash": deleted.get("prompt_hash") or "",
    }


@router.get("/api/prompt-slim")
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
    tasks = _start_prompt_slim_tasks(
        filtered_cte=filtered_cte,
        common_args=common_args,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    (
        summary_record,
        rows,
        stage_distribution,
        reason_distribution,
        task_type_distribution,
        source_distribution,
        length_distribution,
    ) = await _gather_limited(4, *tasks)
    return _build_prompt_slim_response(
        limit=limit,
        page=page,
        stage_filter=stage_filter,
        task_filter=task_filter,
        source_filter=source_filter,
        reason_filter=reason_filter,
        search=search,
        min_users=min_users,
        min_uses=min_uses,
        sort=sort,
        offset=offset,
        summary_record=summary_record,
        rows=rows,
        stage_distribution=stage_distribution,
        reason_distribution=reason_distribution,
        task_type_distribution=task_type_distribution,
        source_distribution=source_distribution,
        length_distribution=length_distribution,
    )


def _start_prompt_slim_tasks(
    *,
    filtered_cte: str,
    common_args: tuple[Any, ...],
    sort: str,
    limit: int,
    offset: int,
) -> tuple[Any, ...]:
    summary_task = _fetchrow(
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
    rows_task = _fetch(
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
    stage_distribution_task = _fetch(
        f"""
        {filtered_cte}
        select 'prompt_slim_stage_distribution' as row_type, quality_stage as label, count(*)::bigint as count
        from filtered
        group by quality_stage
        order by count desc, label
        """,
        *common_args,
    )
    reason_distribution_task = _fetch(
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
    task_type_distribution_task = _fetch(
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
    source_distribution_task = _fetch(
        f"""
        {filtered_cte}
        select 'prompt_slim_source_distribution' as row_type, source_scope as label, count(*)::bigint as count
        from filtered, unnest(source_scopes) as source_scope
        group by source_scope
        order by count desc, label
        """,
        *common_args,
    )
    length_distribution_task = _fetch(
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
    return (
        summary_task,
        rows_task,
        stage_distribution_task,
        reason_distribution_task,
        task_type_distribution_task,
        source_distribution_task,
        length_distribution_task,
    )


def _build_prompt_slim_response(
    *,
    limit: int,
    page: int,
    stage_filter: str,
    task_filter: str | None,
    source_filter: str | None,
    reason_filter: str | None,
    search: str,
    min_users: int,
    min_uses: int,
    sort: str,
    offset: int,
    summary_record: Any,
    rows: Any,
    stage_distribution: Any,
    reason_distribution: Any,
    task_type_distribution: Any,
    source_distribution: Any,
    length_distribution: Any,
) -> dict[str, Any]:
    summary = _row(summary_record)
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


@router.get("/api/prompt-token-aliases")
async def prompt_token_aliases() -> dict[str, Any]:
    await _ensure_prompt_token_alias_schema()
    rows = _rows(
        await _fetch(
            """
            select
                id,
                representative_token,
                alias_tokens,
                aliases_text,
                category_key,
                category_label,
                subcategory_key,
                subcategory_label,
                source,
                seed_batch,
                enabled,
                sort_order,
                updated_at
            from analytics_prompt_token_alias_rules
            where enabled
            order by sort_order, id
            """
        )
    )
    return {
        "rows": [
            {
                "id": row.get("id"),
                "representative": row.get("representative_token") or "",
                "aliases": row.get("alias_tokens") or [],
                "aliases_text": row.get("aliases_text") or "，".join(row.get("alias_tokens") or []),
                "category_key": row.get("category_key") or "",
                "category_label": row.get("category_label") or "",
                "subcategory_key": row.get("subcategory_key") or "",
                "subcategory_label": row.get("subcategory_label") or "",
                "source": row.get("source") or "",
                "seed_batch": row.get("seed_batch") or "",
                "enabled": bool(row.get("enabled", True)),
                "sort_order": int(row.get("sort_order") or 0),
                "updated_at": row.get("updated_at"),
            }
            for row in rows
        ],
        "status": await _prompt_token_alias_status(),
    }


@router.put("/api/prompt-token-aliases")
async def save_prompt_token_aliases(payload: dict[str, Any]) -> dict[str, Any]:
    raw_rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(raw_rows, list):
        raise HTTPException(status_code=400, detail="rows must be an array")
    try:
        rules = validate_prompt_token_alias_rules(raw_rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    serialized_rows = [
        {
            "representative_token": rule.representative,
            "alias_tokens": list(rule.aliases),
            "aliases_text": "，".join(rule.aliases),
            "category_key": rule.category_key,
            "category_label": rule.category_label,
            "subcategory_key": rule.subcategory_key,
            "subcategory_label": rule.subcategory_label,
            "source": rule.source,
            "seed_batch": rule.seed_batch,
            "enabled": rule.enabled,
            "sort_order": index,
        }
        for index, rule in enumerate(rules)
    ]
    await _ensure_prompt_token_alias_schema()
    await _execute(
        """
        with incoming as (
            select *
            from jsonb_to_recordset($1::jsonb) as row(
                representative_token text,
                alias_tokens text[],
                aliases_text text,
                category_key text,
                category_label text,
                subcategory_key text,
                subcategory_label text,
                source text,
                seed_batch text,
                enabled boolean,
                sort_order integer
            )
        ),
        deleted as (
            delete from analytics_prompt_token_alias_rules
            returning 1
        )
        insert into analytics_prompt_token_alias_rules (
            representative_token,
            alias_tokens,
            aliases_text,
            category_key,
            category_label,
            subcategory_key,
            subcategory_label,
            source,
            seed_batch,
            enabled,
            sort_order,
            created_at,
            updated_at
        )
        select
            representative_token,
            alias_tokens,
            aliases_text,
            coalesce(category_key, ''),
            coalesce(category_label, ''),
            coalesce(subcategory_key, ''),
            coalesce(subcategory_label, ''),
            coalesce(source, ''),
            coalesce(seed_batch, ''),
            coalesce(enabled, true),
            coalesce(sort_order, 0),
            now(),
            now()
        from incoming
        order by sort_order, representative_token
        """,
        json.dumps(serialized_rows, ensure_ascii=False),
    )
    await _mark_prompt_token_alias_rules_updated()
    return {
        "status": "saved",
        "row_count": len(serialized_rows),
        "alias_count": sum(len(row["alias_tokens"]) for row in serialized_rows),
        "rows": [
            {
                "representative": row["representative_token"],
                "aliases": row["alias_tokens"],
                "aliases_text": row["aliases_text"],
                "category_key": row["category_key"],
                "category_label": row["category_label"],
                "subcategory_key": row["subcategory_key"],
                "subcategory_label": row["subcategory_label"],
                "source": row["source"],
                "seed_batch": row["seed_batch"],
                "enabled": row["enabled"],
                "sort_order": row["sort_order"],
            }
            for row in serialized_rows
        ],
        "alias_status": await _prompt_token_alias_status(),
    }


@router.get("/api/prompt-token-custom-terms")
async def prompt_token_custom_terms() -> dict[str, Any]:
    await _ensure_prompt_token_custom_term_schema()
    rows = _rows(
        await _fetch(
            """
            select
                id,
                term,
                category_key,
                category_label,
                subcategory_key,
                subcategory_label,
                source,
                seed_batch,
                notes,
                enabled,
                sort_order,
                updated_at
            from analytics_prompt_token_custom_terms
            where enabled
            order by sort_order, id
            """
        )
    )
    return {
        "rows": [
            {
                "id": row.get("id"),
                "term": row.get("term") or "",
                "category_key": row.get("category_key") or "",
                "category_label": row.get("category_label") or "",
                "subcategory_key": row.get("subcategory_key") or "",
                "subcategory_label": row.get("subcategory_label") or "",
                "source": row.get("source") or "",
                "seed_batch": row.get("seed_batch") or "",
                "notes": row.get("notes") or "",
                "enabled": bool(row.get("enabled", True)),
                "sort_order": int(row.get("sort_order") or 0),
                "updated_at": row.get("updated_at"),
            }
            for row in rows
        ],
        "status": await _prompt_token_custom_term_status(),
    }


@router.put("/api/prompt-token-custom-terms")
async def save_prompt_token_custom_terms(payload: dict[str, Any]) -> dict[str, Any]:
    raw_rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(raw_rows, list):
        raise HTTPException(status_code=400, detail="rows must be an array")
    try:
        rules = validate_prompt_token_custom_terms(raw_rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    serialized_rows = [
        {
            "term": rule.term,
            "category_key": rule.category_key,
            "category_label": rule.category_label,
            "subcategory_key": rule.subcategory_key,
            "subcategory_label": rule.subcategory_label,
            "source": rule.source,
            "seed_batch": rule.seed_batch,
            "notes": rule.notes,
            "enabled": rule.enabled,
            "sort_order": index,
        }
        for index, rule in enumerate(rules)
    ]
    await _ensure_prompt_token_custom_term_schema()
    await _execute(
        """
        with incoming as (
            select *
            from jsonb_to_recordset($1::jsonb) as row(
                term text,
                category_key text,
                category_label text,
                subcategory_key text,
                subcategory_label text,
                source text,
                seed_batch text,
                notes text,
                enabled boolean,
                sort_order integer
            )
        ),
        deleted as (
            delete from analytics_prompt_token_custom_terms
            returning 1
        )
        insert into analytics_prompt_token_custom_terms (
            term,
            category_key,
            category_label,
            subcategory_key,
            subcategory_label,
            source,
            seed_batch,
            notes,
            enabled,
            sort_order,
            created_at,
            updated_at
        )
        select
            term,
            coalesce(category_key, ''),
            coalesce(category_label, ''),
            coalesce(subcategory_key, ''),
            coalesce(subcategory_label, ''),
            coalesce(source, ''),
            coalesce(seed_batch, ''),
            coalesce(notes, ''),
            coalesce(enabled, true),
            coalesce(sort_order, 0),
            now(),
            now()
        from incoming
        order by sort_order, term
        """,
        json.dumps(serialized_rows, ensure_ascii=False),
    )
    await _mark_prompt_token_custom_terms_updated()
    return {
        "status": "saved",
        "row_count": len(serialized_rows),
        "rows": serialized_rows,
        "custom_term_status": await _prompt_token_custom_term_status(),
    }


def _serialize_prompt_token_custom_rule(rule: Any, index: int) -> dict[str, Any]:
    return {
        "term": rule.term,
        "category_key": rule.category_key,
        "category_label": rule.category_label,
        "subcategory_key": rule.subcategory_key,
        "subcategory_label": rule.subcategory_label,
        "source": rule.source,
        "seed_batch": rule.seed_batch,
        "notes": rule.notes,
        "enabled": rule.enabled,
        "sort_order": index,
    }


def _serialize_prompt_token_alias_rule(rule: Any, index: int) -> dict[str, Any]:
    return {
        "representative_token": rule.representative,
        "alias_tokens": list(rule.aliases),
        "aliases_text": "，".join(rule.aliases),
        "category_key": rule.category_key,
        "category_label": rule.category_label,
        "subcategory_key": rule.subcategory_key,
        "subcategory_label": rule.subcategory_label,
        "source": rule.source,
        "seed_batch": rule.seed_batch,
        "enabled": rule.enabled,
        "sort_order": index,
    }


@router.post("/api/prompt-token-rules/overwrite-generated")
async def overwrite_generated_prompt_token_rules() -> dict[str, Any]:
    await _ensure_prompt_token_alias_schema()
    await _ensure_prompt_token_custom_term_schema()
    await _ensure_prompt_token_deletion_schema()
    token_rows = _rows(
        await _fetch(
            """
            select token, token_kind, prompt_count, use_count, user_count
            from analytics_prompt_token_stats
            where normalization_version = $1::text
              and token_version = $2::text
              and task_type = $3::text
            order by prompt_count desc, token
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            PROMPT_TOKEN_ALL_TASK,
        )
    )
    generated = build_prompt_token_rule_seed_rows(token_rows)
    try:
        custom_rules = validate_prompt_token_custom_terms(generated["custom_terms"])
        alias_rules = validate_prompt_token_alias_rules(generated["alias_rules"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    custom_rows = [_serialize_prompt_token_custom_rule(rule, index) for index, rule in enumerate(custom_rules)]
    alias_rows = [_serialize_prompt_token_alias_rule(rule, index) for index, rule in enumerate(alias_rules)]
    updated_at = datetime.now(timezone.utc).isoformat()
    report = {
        **generated["report"],
        "seed_batch": generated["seed_batch"],
        "custom_term_count": len(custom_rows),
        "alias_rule_count": len(alias_rows),
        "alias_token_count": sum(len(row["alias_tokens"]) for row in alias_rows),
    }
    await _execute(
        """
        with incoming_custom as (
            select *
            from jsonb_to_recordset($1::jsonb) as row(
                term text,
                category_key text,
                category_label text,
                subcategory_key text,
                subcategory_label text,
                source text,
                seed_batch text,
                notes text,
                enabled boolean,
                sort_order integer
            )
        ),
        incoming_alias as (
            select *
            from jsonb_to_recordset($2::jsonb) as row(
                representative_token text,
                alias_tokens text[],
                aliases_text text,
                category_key text,
                category_label text,
                subcategory_key text,
                subcategory_label text,
                source text,
                seed_batch text,
                enabled boolean,
                sort_order integer
            )
        ),
        deleted_token_rules as (
            delete from analytics_prompt_token_deleted_rules returning 1
        ),
        deleted_custom as (
            delete from analytics_prompt_token_custom_terms returning 1
        ),
        deleted_alias as (
            delete from analytics_prompt_token_alias_rules returning 1
        ),
        inserted_custom as (
            insert into analytics_prompt_token_custom_terms (
                term,
                category_key,
                category_label,
                subcategory_key,
                subcategory_label,
                source,
                seed_batch,
                notes,
                enabled,
                sort_order,
                created_at,
                updated_at
            )
            select
                term,
                coalesce(category_key, ''),
                coalesce(category_label, ''),
                coalesce(subcategory_key, ''),
                coalesce(subcategory_label, ''),
                coalesce(source, ''),
                coalesce(seed_batch, ''),
                coalesce(notes, ''),
                coalesce(enabled, true),
                coalesce(sort_order, 0),
                now(),
                now()
            from incoming_custom
            order by sort_order, term
            returning 1
        ),
        inserted_alias as (
            insert into analytics_prompt_token_alias_rules (
                representative_token,
                alias_tokens,
                aliases_text,
                category_key,
                category_label,
                subcategory_key,
                subcategory_label,
                source,
                seed_batch,
                enabled,
                sort_order,
                created_at,
                updated_at
            )
            select
                representative_token,
                alias_tokens,
                aliases_text,
                coalesce(category_key, ''),
                coalesce(category_label, ''),
                coalesce(subcategory_key, ''),
                coalesce(subcategory_label, ''),
                coalesce(source, ''),
                coalesce(seed_batch, ''),
                coalesce(enabled, true),
                coalesce(sort_order, 0),
                now(),
                now()
            from incoming_alias
            order by sort_order, representative_token
            returning 1
        ),
        state_values(key, value) as (
            values
                ($4::text, $3::text),
                ($5::text, $3::text),
                ($6::text, $3::text),
                ($7::text, $8::text)
        )
        insert into analytics_prompt_vector_state (key, value, updated_at)
        select key, value, now()
        from state_values
        on conflict (key) do update set value = excluded.value, updated_at = now()
        """,
        json.dumps(custom_rows, ensure_ascii=False),
        json.dumps(alias_rows, ensure_ascii=False),
        updated_at,
        prompt_token_vector_state_key("prompt_token_custom_terms_updated_at"),
        prompt_token_vector_state_key("prompt_token_alias_rules_updated_at"),
        prompt_token_vector_state_key("prompt_token_rule_seed_overwrite_at"),
        prompt_token_vector_state_key("prompt_token_rule_seed_report"),
        json.dumps(report, ensure_ascii=False, default=str),
    )
    return {
        "status": "overwritten",
        "message": "已覆盖指定词元、词元映射和词元删除表，待重建生效",
        "report": report,
        "custom_terms": {
            "rows": custom_rows,
            "status": await _prompt_token_custom_term_status(),
        },
        "aliases": {
            "rows": [
                {
                    "representative": row["representative_token"],
                    "aliases": row["alias_tokens"],
                    "aliases_text": row["aliases_text"],
                    "category_key": row["category_key"],
                    "category_label": row["category_label"],
                    "subcategory_key": row["subcategory_key"],
                    "subcategory_label": row["subcategory_label"],
                    "source": row["source"],
                    "seed_batch": row["seed_batch"],
                    "enabled": row["enabled"],
                    "sort_order": row["sort_order"],
                }
                for row in alias_rows
            ],
            "status": await _prompt_token_alias_status(),
        },
        "deletions": {"rows": [], "total": 0},
    }


@router.post("/api/prompt-token-custom-terms/rebuild")
async def rebuild_prompt_token_custom_terms(
    statement_timeout_ms: int = Query(3_600_000, ge=60_000, le=24 * 60 * 60 * 1000),
) -> dict[str, Any]:
    payload = await _start_prompt_token_rebuild(statement_timeout_ms)
    payload["alias_status"] = await _prompt_token_alias_status()
    payload["custom_term_status"] = await _prompt_token_custom_term_status()
    return payload


@router.post("/api/prompt-token-aliases/rebuild")
async def rebuild_prompt_token_aliases(
    statement_timeout_ms: int = Query(3_600_000, ge=60_000, le=24 * 60 * 60 * 1000),
) -> dict[str, Any]:
    payload = await _start_prompt_token_rebuild(statement_timeout_ms)
    payload["alias_status"] = await _prompt_token_alias_status()
    payload["custom_term_status"] = await _prompt_token_custom_term_status()
    return payload


@router.get("/api/prompt-tokens")
async def prompt_tokens(
    q: str | None = Query(None),
    task_type: str | None = Query(None),
    model_key: str | None = Query(None),
    page: int = Query(1, ge=1, le=PROMPT_TOKEN_MAX_PAGE),
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query("prompt_count"),
    min_prompt_count: int = Query(PROMPT_TOKEN_DEFAULT_MIN_PROMPT_COUNT, ge=1, le=PROMPT_TOKEN_MAX_MIN_PROMPT_COUNT),
    include_filters: bool = Query(True),
) -> dict[str, Any]:
    scope = _prompt_token_scope(task_type, model_key)
    table_status = await _prompt_token_tables_status()
    if not table_status.get("ready"):
        return {
            "ready": False,
            "message": "prompt token tables are not built; run python -m app.refresh_prompt_vectors --tokens-only",
            "summary": {
                "candidate_count": 0,
                "token_count": 0,
                "refreshed_at": None,
            },
            "rows": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "has_next": False},
            "scope": scope,
            "filters": {"tasks": [], "models": []},
            "min_prompt_count": min_prompt_count,
        }

    page = _clamp(page, 1, PROMPT_TOKEN_MAX_PAGE)
    limit = _clamp(limit, 1, 200)
    min_prompt_count = _clamp(min_prompt_count, 1, PROMPT_TOKEN_MAX_MIN_PROMPT_COUNT)
    sort = (sort or "prompt_count").strip()
    if sort not in PROMPT_TOKEN_SORTS:
        raise HTTPException(status_code=400, detail="invalid prompt token sort")
    search = (q or "").strip().casefold()
    offset = (page - 1) * limit
    deletion_filter = (
        """
              and not exists (
                  select 1
                  from analytics_prompt_token_deleted_rules deleted
                  where deleted.token = analytics_prompt_token_stats.token
              )
        """
        if table_status.get("deletion_ready")
        else ""
    )
    candidate_count = await _prompt_token_scope_candidate_count(
        scope["key"],
        summary_ready=table_status.get("scope_summary_ready", False),
    )

    summary = _row(
        await _fetchrow(
            f"""
            select
                $4::bigint as candidate_count,
                count(*)::bigint as token_count,
                count(*) filter (where prompt_count >= $5::bigint)::bigint as filtered_token_count,
                max(refreshed_at) as refreshed_at
            from analytics_prompt_token_stats
            where normalization_version = $1::text
              and token_version = $2::text
              and task_type = $3::text
              {deletion_filter}
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            scope["key"],
            candidate_count,
            min_prompt_count,
        )
    )
    filters = await _prompt_token_filter_options(scope["task_type"]) if include_filters else {"tasks": [], "models": []}
    total_record = _row(
        await _fetchrow(
            f"""
            select count(*)::bigint as total
            from analytics_prompt_token_stats
            where normalization_version = $1::text
              and token_version = $2::text
              and task_type = $3::text
              and ($4::text is null or position($4::text in casefold(token)) > 0)
              and prompt_count >= $5::bigint
              {deletion_filter}
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            scope["key"],
            search,
            min_prompt_count,
        )
    )
    total = int(total_record.get("total") or 0)
    rows = await _fetch(
        f"""
        select
            token,
            token_kind,
            prompt_count,
            use_count,
            user_count,
            refreshed_at,
            round(
                prompt_count::numeric * 100
                / nullif($6::numeric, 0),
                4
            ) as prompt_share
        from analytics_prompt_token_stats
        where normalization_version = $1::text
          and token_version = $2::text
          and task_type = $3::text
          and ($4::text is null or position($4::text in casefold(token)) > 0)
          and prompt_count >= $5::bigint
          {deletion_filter}
        order by {PROMPT_TOKEN_SORTS[sort]}
        limit $7::int
        offset $8::int
        """,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_TOKEN_VERSION,
        scope["key"],
        search,
            min_prompt_count,
            candidate_count,
            limit,
            offset,
    )
    return {
        "ready": True,
        "query": search,
        "sort": sort,
        "min_prompt_count": min_prompt_count,
        "scope": scope,
        "filters": filters,
        "filters_included": include_filters,
        "summary": summary,
        "rows": _rows(rows),
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": offset + limit < total,
        },
    }


@router.get("/api/prompt-token-prompts")
async def prompt_token_prompts(
    token: str = Query(..., min_length=1),
    task_type: str | None = Query(None),
    model_key: str | None = Query(None),
    page: int = Query(1, ge=1, le=PROMPT_TOKEN_MAX_PAGE),
    limit: int = Query(20, ge=1, le=100),
    min_prompt_count: int = Query(PROMPT_TOKEN_DEFAULT_MIN_PROMPT_COUNT, ge=1, le=PROMPT_TOKEN_MAX_MIN_PROMPT_COUNT),
) -> dict[str, Any]:
    scope = _prompt_token_scope(task_type, model_key)
    table_status = await _prompt_token_tables_status()
    if not table_status.get("ready"):
        raise HTTPException(
            status_code=503,
            detail="prompt token tables are not built; run python -m app.refresh_prompt_vectors --tokens-only",
        )
    token_filter = token.strip().casefold()
    if not token_filter:
        raise HTTPException(status_code=400, detail="token is required")
    page = _clamp(page, 1, PROMPT_TOKEN_MAX_PAGE)
    limit = _clamp(limit, 1, 100)
    min_prompt_count = _clamp(min_prompt_count, 1, PROMPT_TOKEN_MAX_MIN_PROMPT_COUNT)
    offset = (page - 1) * limit
    deletion_filter = (
        """
              and not exists (
                  select 1
                  from analytics_prompt_token_deleted_rules deleted
                  where deleted.token = analytics_prompt_token_stats.token
              )
        """
        if table_status.get("deletion_ready")
        else ""
    )

    summary = _row(
        await _fetchrow(
            f"""
            select
                token,
                token_kind,
                prompt_count,
                use_count,
                user_count,
                refreshed_at
            from analytics_prompt_token_stats
            where normalization_version = $1::text
              and token_version = $2::text
              and task_type = $3::text
              and token = $4::text
              and prompt_count >= $5::bigint
              {deletion_filter}
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            scope["key"],
            token_filter,
            min_prompt_count,
        )
    )
    if not summary:
        return {
            "ready": True,
            "token": token_filter,
            "scope": scope,
            "summary": {
                "token": token_filter,
                "prompt_count": 0,
                "use_count": 0,
                "user_count": 0,
            },
            "rows": [],
            "pagination": {"page": page, "limit": limit, "total": 0, "has_next": False},
            "min_prompt_count": min_prompt_count,
        }
    total = int(summary.get("prompt_count") or 0)
    prompt_rows = await _fetch(
        """
        select
            prompt_hash,
            prompt,
            tokens,
            task_types,
            scopes,
            char_count,
            coalesce((scope_uses ->> $4::text)::bigint, uses) as uses,
            coalesce((scope_users ->> $4::text)::bigint, users) as users,
            quality_score,
            last_seen
        from analytics_prompt_token_prompts
        where normalization_version = $1::text
          and token_version = $2::text
          and tokens @> array[$3::text]
          and scopes @> array[$4::text]
        order by quality_score desc, uses desc, users desc, prompt_hash
        limit $5::int
        offset $6::int
        """,
        PROMPT_NORMALIZATION_VERSION,
        PROMPT_TOKEN_VERSION,
        token_filter,
        scope["key"],
        limit,
        offset,
    )
    prompt_items = [_row(record) for record in prompt_rows]
    other_token_candidates: list[str] = []
    seen_other_tokens: set[str] = set()
    for item in prompt_items:
        for value in (item.get("tokens") or []):
            token_value = str(value)
            if token_value == token_filter or token_value in seen_other_tokens:
                continue
            seen_other_tokens.add(token_value)
            other_token_candidates.append(token_value)
    allowed_other_tokens: set[str] = set()
    if other_token_candidates:
        allowed_rows = await _fetch(
            f"""
            select token
            from analytics_prompt_token_stats
            where normalization_version = $1::text
              and token_version = $2::text
              and task_type = $3::text
              and prompt_count >= $4::bigint
              and token = any($5::text[])
              {deletion_filter}
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            scope["key"],
            min_prompt_count,
            other_token_candidates,
        )
        allowed_other_tokens = {str(row["token"]) for row in allowed_rows}
    rows = []
    for item in prompt_items:
        prompt = item.get("prompt") or ""
        tokens = [str(value) for value in (item.get("tokens") or [])]
        item["prompt_preview"] = _collapse_text(prompt, 260)
        item["tokens"] = tokens
        item["other_tokens"] = [
            value for value in tokens if value != token_filter and value in allowed_other_tokens
        ]
        rows.append(item)
    return {
        "ready": True,
        "token": token_filter,
        "scope": scope,
        "summary": summary,
        "rows": rows,
        "min_prompt_count": min_prompt_count,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "has_next": offset + limit < total,
        },
    }


@router.get("/api/prompt-token-deletions")
async def prompt_token_deletions() -> dict[str, Any]:
    await _ensure_prompt_token_deletion_schema()
    rows = _rows(
        await _fetch(
            """
            select
                deleted.token,
                deleted.deleted_at,
                deleted.updated_at,
                stats.token_kind,
                stats.prompt_count,
                stats.use_count,
                stats.user_count,
                stats.refreshed_at
            from analytics_prompt_token_deleted_rules deleted
            left join analytics_prompt_token_stats stats
              on stats.normalization_version = $1::text
             and stats.token_version = $2::text
             and stats.task_type = $3::text
             and stats.token = deleted.token
            order by deleted.updated_at desc, deleted.token
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            PROMPT_TOKEN_ALL_TASK,
        )
    )
    return {
        "rows": rows,
        "total": len(rows),
    }


@router.post("/api/prompt-token-deletions")
async def delete_prompt_token(payload: dict[str, Any]) -> dict[str, Any]:
    token = _normalize_prompt_token_api_value(str(payload.get("token") or ""))
    await _ensure_prompt_token_deletion_schema()
    await _execute(
        """
        insert into analytics_prompt_token_deleted_rules (token, deleted_at, updated_at)
        values ($1::text, now(), now())
        on conflict (token) do update set
            deleted_at = excluded.deleted_at,
            updated_at = now()
        """,
        token,
    )
    return {
        "status": "deleted",
        "token": token,
    }


@router.post("/api/prompt-token-deletions/restore")
async def restore_prompt_token(payload: dict[str, Any]) -> dict[str, Any]:
    token = _normalize_prompt_token_api_value(str(payload.get("token") or ""))
    await _ensure_prompt_token_deletion_schema()
    await _execute(
        """
        delete from analytics_prompt_token_deleted_rules
        where token = $1::text
        """,
        token,
    )
    return {
        "status": "restored",
        "token": token,
    }


@router.post("/api/prompt-vectors/resume")
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
        "--skip-token-refresh",
    ]
    task_filter = (task_type or "").strip()
    if task_filter:
        command.extend(["--task-type", task_filter])

    resume_log = _prompt_vector_resume_log()
    resume_log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LOCAL_ANALYTICS_DATABASE_URL"] = _database_url()
    try:
        with resume_log.open("ab") as log_handle:
            process = await asyncio.to_thread(
                _start_prompt_vector_resume_process,
                command,
                cwd=str(ROOT_DIR),
                env=env,
                log_handle=log_handle,
            )
    except Exception as exc:  # pragma: no cover - surfaced to the UI.
        raise HTTPException(status_code=500, detail=f"failed to start prompt vector refresh: {type(exc).__name__}") from exc

    set_prompt_vector_resume_process(process)
    return {
        "status": "started",
        "message": "已开始续跑缺失向量",
        "pid": process.pid,
        "log_path": str(resume_log),
    }


@router.get("/api/prompt-vectors")
async def prompt_vector_status(model_id: str = Query(DEFAULT_VECTOR_MODEL_ID)) -> dict[str, Any]:
    if not await _prompt_vector_tables_ready():
        return {
            "ready": False,
            "message": (
                "prompt vector tables are not built; run "
                "python -m app.refresh_prompt_vectors --embed-only"
            ),
            "model": {
                "model_id": model_id,
                "model_key": DEFAULT_VECTOR_MODEL_KEY,
                "normalization_version": PROMPT_NORMALIZATION_VERSION,
            },
            "summary": {
                "candidate_count": 0,
                "embedded_count": 0,
                "pending_count": 0,
                "failed_count": 0,
                "embedding_coverage": 0,
                "latest_embedded_at": None,
                "token_count": 0,
                "token_stats_refreshed_at": None,
            },
            "distributions": {"task_type": [], "status": [], "tokens": []},
            "tokens": {
                "version": PROMPT_TOKEN_VERSION,
                "total": 0,
                "refreshed_at": None,
            },
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
                    from analytics_prompt_embeddings
                    where model_id = $1::text
                      and normalization_version = $2::text
                      and status = 'error'
                ), 0)::bigint as failed_count,
                (
                    select max(embedded_at)
                    from analytics_prompt_embeddings
                    where model_id = $1::text
                      and normalization_version = $2::text
                      and status = 'embedded'
                ) as latest_embedded_at
            """,
            model_id,
            PROMPT_NORMALIZATION_VERSION,
        )
    )
    candidate_count = float(summary.get("candidate_count") or 0)
    embedded_count = float(summary.get("embedded_count") or 0)
    summary["pending_count"] = max(0, int(candidate_count) - int(embedded_count))
    summary["embedding_coverage"] = round((embedded_count / candidate_count * 100) if candidate_count else 0, 2)

    token_stats_ready = bool(
        _row(
            await _fetchrow(
                "select to_regclass('public.analytics_prompt_token_stats') is not null as ready"
            )
        ).get("ready")
    )
    token_summary: dict[str, Any] = {
        "token_count": 0,
        "token_stats_refreshed_at": None,
    }
    token_distribution: list[Any] = []
    if token_stats_ready:
        token_summary = _row(
            await _fetchrow(
                """
                select
                    count(*)::bigint as token_count,
                    max(refreshed_at) as token_stats_refreshed_at
                from analytics_prompt_token_stats
                where normalization_version = $1::text
                  and token_version = $2::text
                  and task_type = $3::text
                """,
                PROMPT_NORMALIZATION_VERSION,
                PROMPT_TOKEN_VERSION,
                PROMPT_TOKEN_ALL_TASK,
            )
        )
        token_distribution = await _fetch(
            """
            select
                token as label,
                prompt_count as count,
                use_count,
                user_count,
                token_kind
            from analytics_prompt_token_stats
            where normalization_version = $1::text
              and token_version = $2::text
              and task_type = $3::text
            order by prompt_count desc, use_count desc, token
            limit 80
            """,
            PROMPT_NORMALIZATION_VERSION,
            PROMPT_TOKEN_VERSION,
            PROMPT_TOKEN_ALL_TASK,
        )
    summary.update(token_summary)

    task_distribution = await _fetch(
        """
        select task_type as label, count(*)::bigint as count
        from analytics_prompt_embeddings
        where model_id = $1::text
          and normalization_version = $2::text
          and status = 'embedded'
        group by task_type
        order by count desc, label
        limit 80
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
    )
    status_distribution = await _fetch(
        """
        select status as label, count(*)::bigint as count
        from analytics_prompt_embeddings
        where model_id = $1::text
          and normalization_version = $2::text
        group by status
        order by count desc, label
        """,
        model_id,
        PROMPT_NORMALIZATION_VERSION,
    )
    return {
        "ready": True,
        "model": {
            "model_id": model_id,
            "model_key": vector_state.get("model_key") or DEFAULT_VECTOR_MODEL_KEY,
            "normalization_version": PROMPT_NORMALIZATION_VERSION,
            "embedding_dim": vector_state.get("embedding_dim"),
            "last_success_at": vector_state.get("last_success_at"),
            "last_error": vector_state.get("last_error"),
            "state_updated_at": _json_value(state_updated_at),
        },
        "summary": summary,
        "distributions": {
            "task_type": _rows(task_distribution),
            "status": _rows(status_distribution),
            "tokens": _rows(token_distribution),
        },
        "tokens": {
            "version": PROMPT_TOKEN_VERSION,
            "total": summary.get("token_count") or 0,
            "refreshed_at": summary.get("token_stats_refreshed_at"),
        },
        "resume": _prompt_vector_resume_status(),
    }
