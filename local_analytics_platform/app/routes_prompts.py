from __future__ import annotations

from typing import Any

import asyncio
import json
import os
import subprocess
import sys

from fastapi import APIRouter, HTTPException, Query  # noqa: F401

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


def _prompt_vector_resume_log() -> Any:
    main_module = sys.modules.get("local_analytics_platform.app.main")
    if main_module is None:
        return PROMPT_VECTOR_RESUME_LOG
    return getattr(main_module, "PROMPT_VECTOR_RESUME_LOG", PROMPT_VECTOR_RESUME_LOG)


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
    sample_limit = max(limit * 100, 20000)
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
    (
        summary_record,
        group_records,
        length_distribution,
        task_type_distribution,
        reuse_distribution,
        template_scope_distribution,
        rows,
    ) = await _gather_limited(
        4,
        summary_task,
        group_records_task,
        length_distribution_task,
        task_type_distribution_task,
        reuse_distribution_task,
        template_scope_distribution_task,
        rows_task,
    )
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
    (
        summary_record,
        rows,
        stage_distribution,
        reason_distribution,
        task_type_distribution,
        source_distribution,
        length_distribution,
    ) = await _gather_limited(
        4,
        summary_task,
        rows_task,
        stage_distribution_task,
        reason_distribution_task,
        task_type_distribution_task,
        source_distribution_task,
        length_distribution_task,
    )
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
            },
            "distributions": {"task_type": [], "status": []},
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
        },
        "resume": _prompt_vector_resume_status(),
    }
